import json
import logging
import time
from pathlib import Path

import requests
from requests_toolbelt import MultipartEncoder

from app_queries import get_media_encoder_host, get_media_encoder_port
from thread_utils import TaskWrapper, NoOpTaskWrapper


def _build_server_url() -> str | None:
    host = get_media_encoder_host()
    if not host:
        return None
    port = get_media_encoder_port()
    return f"http://{host}:{port}"


def _poll_and_download(ticket_id: str, output_file, server_url: str, log: TaskWrapper) -> bool:
    output_path = Path(output_file)
    while True:
        time.sleep(12)
        try:
            status_resp = requests.get(f"{server_url}/status/{ticket_id}", timeout=180)
        except Exception as e:
            log.warn(f"Status poll failed: {e}")
            return False

        if status_resp.status_code != 200:
            log.warn(f"Status check returned {status_resp.status_code}")
            return False

        data = status_resp.json()
        status = data.get("status")
        progress = data.get("progress")

        if progress:
            log.update_progress(float(progress))

        if status == "done":
            log.update_progress(100)
            try:
                result = requests.get(f"{server_url}/result/{ticket_id}", stream=True, timeout=None)
                if result.status_code != 200:
                    log.error(f"Failed to download result: {result.status_code}")
                    return False
                with open(output_path, "wb") as f:
                    for chunk in result.iter_content(chunk_size=8 * 1024 * 1024):
                        f.write(chunk)
                log.info("Downloaded encoded file successfully.")
                return True
            except Exception as e:
                log.error(f"Download failed: {e}")
                logging.exception(e)
                return False
        elif status == "failed":
            log.error(f"Remote job failed: {data.get('error', 'unknown error')}")
            return False


def remote_encode(input_file, output_file, ffmpeg_preset: str = 'medium', stereo: bool = True,
                  audio_bitrate: int = 128, srt_file: str | None = None,
                  resolution: str = 'src', log: TaskWrapper = None) -> bool:
    if log is None:
        log = NoOpTaskWrapper()
    server_url = _build_server_url()
    if not server_url:
        return False

    input_path = Path(input_file)
    log.info(f"Submitting encode job to {server_url}")

    open_files = []
    try:
        options = {"ffmpeg_preset": ffmpeg_preset, "stereo": stereo, "audio_bitrate": audio_bitrate, "resolution": resolution}
        fields = {"options": json.dumps(options)}

        f_input = open(input_path, "rb")
        open_files.append(f_input)
        fields["input_file"] = (input_path.name, f_input, "application/octet-stream")

        if srt_file and Path(srt_file).exists():
            f_srt = open(srt_file, "rb")
            open_files.append(f_srt)
            fields["srt_file"] = (Path(srt_file).name, f_srt, "text/plain")

        encoder = MultipartEncoder(fields=fields)
        response = requests.post(
            f"{server_url}/start/encode",
            data=encoder,
            headers={"Content-Type": encoder.content_type},
            timeout=None,
        )
    except Exception as e:
        log.warn(f"Remote encode submission failed: {e}")
        logging.exception(e)
        return False
    finally:
        for f in open_files:
            f.close()

    if response.status_code != 200:
        log.warn(f"Server returned {response.status_code} for encode submission")
        return False

    ticket_id = response.json().get("ticket_id")
    if not ticket_id:
        log.warn("No ticket_id in encode response")
        return False
    # Remote encodes take no resources, let them pile up
    log.weight = 2

    return _poll_and_download(ticket_id, output_file, server_url, log)


def remote_defreeze(input_file, output_file, freeze_db: str = "-60dB", silence_noise: str = "-30dB",
                    min_duration: float = 1.5, force_encode: bool = False,
                    log: TaskWrapper = None) -> bool:
    if log is None:
        log = NoOpTaskWrapper()
    server_url = _build_server_url()
    if not server_url:
        return False

    input_path = Path(input_file)
    log.info(f"Submitting defreeze job to {server_url}")

    open_files = []
    try:
        options = {
            "freeze_db": freeze_db,
            "silence_noise": silence_noise,
            "min_duration": min_duration,
            "force_encode": force_encode,
        }
        fields = {"options": json.dumps(options)}

        f_input = open(input_path, "rb")
        open_files.append(f_input)
        fields["input_file"] = (input_path.name, f_input, "application/octet-stream")

        encoder = MultipartEncoder(fields=fields)
        response = requests.post(
            f"{server_url}/start/defreeze",
            data=encoder,
            headers={"Content-Type": encoder.content_type},
            timeout=None,
        )
    except Exception as e:
        log.warn(f"Remote defreeze submission failed: {e}")
        logging.exception(e)
        return False
    finally:
        for f in open_files:
            f.close()

    if response.status_code != 200:
        log.warn(f"Server returned {response.status_code} for defreeze submission")
        return False

    ticket_id = response.json().get("ticket_id")
    if not ticket_id:
        log.warn("No ticket_id in defreeze response")
        return False

    return _poll_and_download(ticket_id, output_file, server_url, log)
