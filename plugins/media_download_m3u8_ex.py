import argparse
import base64
import json
import os.path
import platform
import shlex
import shutil
import subprocess
from datetime import date as date_type, datetime
from time import sleep

from flask_sqlalchemy.session import Session

from batch_curl import download_image_batch
from curl_utils import custom_curl_get, read_temp_file, read_header_file, is_cloudflare_block
from feature_flags import MANAGE_MEDIA
from file_utils import is_valid_url, temporary_folder
from html_utils import get_headers
from m3u8_parser import M3u8Playlist
from media_probe import get_file_formats
from media_queries import find_folder_by_id, insert_file
from media_utils import get_data_for_mediafile
from plugin_methods import plugin_filename_arg, plugin_url_arg, plugin_select_arg, plugin_select_values
from plugin_system import ActionMediaFolderPlugin
from plugins.media_download_file import DownloadFileJob
from strip_png_prefix import strip_png_prefix_from_directory
from text_utils import is_blank
from thread_utils import TaskWrapper
from utility import random_sleep


def _cloudflare_retry_curl(url: str, headers, dest_file: str,
                            task_wrapper: TaskWrapper, label: str = 'file') -> bool:
    _MAX_CF_RETRIES = 0
    for attempt in range(_MAX_CF_RETRIES + 1):
        if not custom_curl_get(url, headers, dest_file, task_wrapper):
            task_wrapper.set_warning(True)
            return False
        if not is_cloudflare_block(dest_file):
            task_wrapper.set_warning(False)
            return True
        if attempt == _MAX_CF_RETRIES:
            break
        task_wrapper.set_warning(True)
        delay = 360
        jitter = 35
        task_wrapper.warn(
            f'Cloudflare block on {label} (attempt {attempt + 1}/{_MAX_CF_RETRIES}) '
            f'— waiting ~{delay}s before retry'
        )
        task_wrapper.warn(f'Cloudflare blocked URL: {url}')
        random_sleep(delay + jitter, delay - jitter, task_wrapper)

    task_wrapper.error(f'Cloudflare block persisted after {_MAX_CF_RETRIES} retries on {label}')
    return False


def _log_tracker_payload(task_wrapper: TaskWrapper, folder_id: str, filename: str,
                          url: str, origin: str) -> None:
    stem = filename.rsplit('.', 1)[0] if '.' in filename else filename
    group = {
        "n": stem,
        "t": "m3u8_vtt",
        "folder_id": folder_id,
        "items": [
            {"t": "STREAM", "url": url, "origin": origin}
        ]
    }
    payload = base64.b64encode(json.dumps([group]).encode('utf-8')).decode('utf-8')
    task_wrapper.warn(f'Tracker payload to re-submit: {payload}')


class DownloadM3u8PluginEx(ActionMediaFolderPlugin):
    """
    Download from YTube
    """
    AI_QUICK_DESCRIPTION = ('Advanced HLS (M3U8) downloader that fetches the playlist and all its '
                            'segments with resilient curl-based downloading (retries, HTTP/2, '
                            'Cloudflare handling) and assembles them into an MP4 without re-encoding.')
    AI_LONG_DESCRIPTION = (
        'A more robust version of the M3U8 downloader for protected or unreliable streams. '
        'Instead of handing the .m3u8 URL directly to ffmpeg, it first downloads the playlist '
        'itself, then downloads every video segment via a custom, batched curl downloader with '
        'automatic retries (up to 7 rounds), optional HTTP/2, and Cloudflare anti-bot detection '
        'and retry. It also resolves AES-128 encrypted streams by fetching the decryption key '
        'files and the initialization map, and it substitutes stand-in segments for a small '
        'number of missing ones (except for encrypted streams, where a wrong segment would '
        'corrupt the output). The segments are then stitched into an MP4 container with ffmpeg '
        'in stream-copy mode (no re-encode). If fewer than ~97% of segments can be retrieved '
        'the download is aborted. The result is registered as video/mp4 and moved into the '
        'chosen disk (Primary or Archive). Linux-only (requires the curl toolchain). Required '
        'arguments: URL (the .m3u8 manifest), Origin (the referring page), and Filename. '
        'HTTP2 and Location are optional.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'dlm3u8ex'

    def get_sort(self):
        return {'id': 'media_dl.m3u8.ex', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Save Video from M3u8 (Ex)'

    def get_action_id(self):
        return 'action.download.m3u8.ex'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_url_arg('URL', 'url', 'The link to the m3u8 file.', '', 'yes', "url", 'origin', 'Origin')
        )

        result.append(
            plugin_filename_arg('Filename', 'filename', 'The name of the file.')
        )

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_url_arg('Origin', 'origin', 'The origin for the Url.', '', 'no', "Origin")
        )

        result.append(
            plugin_select_arg('HTTP2', 'http2', '0',
                              plugin_select_values('Yes', '1', 'No', '0'), '', 'media',
                              adv='Y')
        )

        return result

    def process_action_args(self, args):
        results = []

        if 'url' not in args or args['url'] is None or args['url'] == '':
            results.append('url is required')

        if 'origin' not in args or args['origin'] is None or args['origin'] == '':
            results.append('origin is required')

        if 'filename' not in args or args['filename'] is None or args['filename'] == '':
            results.append('filename is required')

        if not is_valid_url(args['url']):
            results.append('url is not valid url')

        if not is_valid_url(args['origin']):
            results.append('origin is not valid url')

        if 'dest' not in args or is_blank(args['dest']):
            results.append('dest is required')
        elif not (args['dest'] == 'primary' or args['dest'] == 'archive'):
            results.append('Invalid dest value')

        if 'http2' not in args or is_blank(args['http2']):
            results.append('http2 is required')
        elif not (args['http2'] == '0' or args['http2'] == '1'):
            results.append('Invalid http2 value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def is_ready(self):
        return super().is_ready() and platform.system() == 'Linux'

    def create_task(self, db_session: Session, args):
        filename = args['filename']
        return DownloadM3u8JobEx("Download M3u8", f'Downloading {filename} from M3u8 to folder ' + args['folder_id'],
                                 args['folder_id'], filename, args['url'].strip(), args['origin'].strip(), args['dest'],
                                 self.primary_path, self.archive_path, self.temp_path, args['http2'] == '1')


class DownloadM3u8SubtitlePluginEx(ActionMediaFolderPlugin):
    """
    Download from YTube
    """
    AI_QUICK_DESCRIPTION = ('Same advanced M3U8 downloader as the (Ex) variant, optionally also '
                            'fetching a companion .vtt subtitle file into the same folder.')
    AI_LONG_DESCRIPTION = (
        'Downloads an HLS video stream using the same advanced method as the M3u8 (Ex) plugin '
        '- batched curl segment downloads with retries, HTTP/2, and Cloudflare handling, then '
        'stitched into an MP4 by ffmpeg in stream-copy mode. In addition, it can retrieve a '
        'separate subtitle file from its own URL and save it to the same media folder as '
        '<filename>.vtt, so the video and its WebVTT subtitles land together. The video and '
        'subtitle parts are independent: if only one of the URL/origin pairs is valid, only '
        'that part is downloaded. As with the (Ex) variant this is Linux-only. Required '
        'arguments: Filename, M3u8 URL, and M3u8 Origin. Optionally supply Subtitle URL and '
        'Subtitle Origin to also grab the .vtt file. HTTP2 and Location are optional.')

    def __init__(self):
        super().__init__()
        self.prefix_lang_id = 'dlm3u8exsub'

    def get_sort(self):
        return {'id': 'media_dl.m3u8.ex.sub', 'sequence': 1}

    def add_args(self, parser: argparse):
        pass

    def use_args(self, args):
        pass

    def get_action_name(self):
        return 'Download M3u8 (Ex) & Subtitle'

    def get_action_id(self):
        return 'action.download.m3u8.ex.sub'

    def get_action_icon(self):
        return 'download'

    def get_action_args(self):
        result = super().get_action_args()

        result.append(
            plugin_select_arg('Location', 'dest', 'primary',
                              plugin_select_values('Primary Disk', 'primary', 'Archive Disk', 'archive'), '', 'media',
                              adv='Y')
        )

        result.append(
            plugin_filename_arg('Filename', 'filename', 'The name of the file.')
        )

        result.append(
            plugin_url_arg('Subtitle URL', 'sub_url', 'The link to the m3u8 file.', '', 'yes', "url", 'sub_origin', 'Origin')
        )

        result.append(
            plugin_url_arg('M3u8 URL', 'url', 'The link to the m3u8 file.', '', 'yes', "url", 'origin', "Origin")
        )

        result.append(
            plugin_url_arg('Subtitle Origin', 'sub_origin', 'The origin for the Url.', '', 'no', "Origin")
        )

        result.append(
            plugin_url_arg('M3u8 Origin', 'origin', 'The origin for the Url.', '', 'no', "Origin")
        )

        result.append(
            plugin_select_arg('HTTP2', 'http2', '0',
                              plugin_select_values('Yes', '1', 'No', '0'), '', 'media',
                              adv='Y')
        )

        return result

    def process_action_args(self, args):
        results = []

        if 'url' not in args or args['url'] is None or args['url'] == '':
            results.append('url is required')

        if 'origin' not in args or args['origin'] is None or args['origin'] == '':
            results.append('origin is required')

        if 'filename' not in args or args['filename'] is None or args['filename'] == '':
            results.append('filename is required')

        results_m3u8 = []
        results_file = []

        if not is_valid_url(args['url']):
            results_m3u8.append('url is not valid url')

        if not is_valid_url(args['origin']):
            results_m3u8.append('origin is not valid url')

        if not is_valid_url(args['sub_url']):
            results_file.append('subtitle url is not valid url')

        if not is_valid_url(args['sub_origin']):
            results_file.append('subtitle origin is not valid url')

        if len(results_m3u8) == 0 or len(results_file) == 0:
            # If one side is good, we can ignore the other errors
            results_m3u8 = []
            results_file = []

        results.extend(results_m3u8)
        results.extend(results_file)

        if 'dest' not in args or is_blank(args['dest']):
            results.append('dest is required')
        elif not (args['dest'] == 'primary' or args['dest'] == 'archive'):
            results.append('Invalid dest value')

        if 'http2' not in args or is_blank(args['http2']):
            results.append('http2 is required')
        elif not (args['http2'] == '0' or args['http2'] == '1'):
            results.append('Invalid http2 value')

        if len(results) > 0:
            return results
        return None

    def get_feature_flags(self):
        return MANAGE_MEDIA

    def is_ready(self):
        return super().is_ready() and platform.system() == 'Linux'

    def create_task(self, db_session: Session, args):
        filename = args['filename']

        jobs = []

        if is_valid_url(args['url']) and is_valid_url(args['origin']):
            jobs.append(
                DownloadM3u8JobEx("Download M3u8", f'Downloading {filename} from M3u8 to folder ' + args['folder_id'],
                                  args['folder_id'], filename, args['url'].strip(), args['origin'].strip(),
                                  args['dest'], self.primary_path, self.archive_path, self.temp_path, args['http2'] == '1'))

        if is_valid_url(args['sub_url']) and is_valid_url(args['sub_origin']):
            jobs.append(
                DownloadFileJob("Download File", f'Downloading {filename}.vtt from Web to folder ' + args['folder_id'],
                                args['folder_id'], filename + '.vtt', args['sub_url'], args['sub_origin'].strip(),
                                args['dest'],
                                'gcurl',
                                self.primary_path,
                                self.archive_path,
                                self.temp_path))
        return jobs


def _validate_downloaded_segments(entries, temp_folder: str, encrypted: bool,
                                   task_wrapper: TaskWrapper, total_segments: int,
                                   confirmed_count_ref: list, rejected_count_ref: list) -> None:
    for entry in entries:
        seg_file = os.path.join(temp_folder, entry.local_name)

        if not os.path.exists(seg_file):
            entry.valid = False
            entry.missing = True
            continue

        file_size = os.path.getsize(seg_file)
        if file_size < 50 * 1024:
            try:
                with open(seg_file, 'r', encoding='utf-8') as fh:
                    fh.read(4096)
                os.remove(seg_file)
                entry.valid = False
                entry.missing = True
                rejected_count_ref[0] += 1
                continue
            except (UnicodeDecodeError, OSError):
                pass

        if encrypted:
            entry.determined_extension = 'ts'
            entry.valid = True
            entry.missing = False
        else:
            available_format = get_file_formats(seg_file, task_wrapper)
            if available_format is None:
                valid_format = False
                determined_ext = 'mp4'
            elif available_format == 'mp4':
                valid_format = True
                determined_ext = 'mp4'
            else:
                valid_format = True
                determined_ext = available_format

            if determined_ext == 'png_pipe':
                determined_ext = 'ts'

            idx = int(entry.local_name.split('_')[1].split('.')[0])
            new_seg_path = os.path.join(temp_folder, f'seg_{idx}.{determined_ext}')
            shutil.move(seg_file, new_seg_path)

            entry.determined_extension = determined_ext
            entry.valid = valid_format
            entry.missing = False

        if entry.valid:
            confirmed_count_ref[0] += 1
            task_wrapper.update_progress(100.0 * (confirmed_count_ref[0] / total_segments))


def _batch_download_segments(segments: list, temp_folder: str, headers,
                              encrypted: bool, task_wrapper: TaskWrapper,
                              use_http2: bool = True) -> bool:
    _MAX_RETRIES = 7
    _RETRY_WAIT = 15
    _MIN_BATCH_SUCCESS_RATE = 0.25
    _COMPLETION_RATE = 0.97
    total = len(segments)

    batch = [{'file': entry.local_name, 'url': entry.uri} for entry in segments]

    # Use the file count as progress
    task_wrapper.expected_files_count = total
    task_wrapper.expected_files_as_progress = True

    task_wrapper.info(f'Batch downloading {total} segments (HTTP/2={use_http2})')
    download_image_batch(batch, temp_folder, headers=headers, parallel_max=4 if use_http2 else 1, use_http2=use_http2)



    confirmed_count_ref = [0]
    rejected_count_ref = [0]
    _validate_downloaded_segments(segments, temp_folder, encrypted, task_wrapper, total, confirmed_count_ref, rejected_count_ref)
    if rejected_count_ref[0] > 0:
        task_wrapper.warn(f'{rejected_count_ref[0]}/{total} segments rejected as HTML/error responses on first attempt')

    succeeded_initial = sum(1 for e in segments if not e.missing)
    if succeeded_initial < max(1, int(total * _MIN_BATCH_SUCCESS_RATE)):
        task_wrapper.error(
            f'Only {succeeded_initial}/{total} segments downloaded on first attempt '
            f'(< {int(_MIN_BATCH_SUCCESS_RATE * 100)}%) — aborting, playlist is likely invalid'
        )
        task_wrapper.expected_files_as_progress = False
        return False

    for retry_num in range(1, _MAX_RETRIES + 1):
        missing = [e for e in segments if e.missing]
        if not missing:
            break

        succeeded_so_far = sum(1 for e in segments if not e.missing)
        if succeeded_so_far >= int(total * _COMPLETION_RATE):
            task_wrapper.info(f'{succeeded_so_far}/{total} segments present (>= {int(_COMPLETION_RATE * 100)}%) — skipping further retries')
            break

        task_wrapper.info(f'Retry {retry_num}/{_MAX_RETRIES}: {len(missing)} missing segments')
        random_sleep(_RETRY_WAIT, _RETRY_WAIT - 2, task_wrapper)

        batch = [{'file': entry.local_name, 'url': entry.uri} for entry in missing]
        download_image_batch(batch, temp_folder, headers=headers, parallel_max=16 if use_http2 else 1, use_http2=use_http2)

        prev_missing_count = len(missing)
        retry_rejected_ref = [0]
        _validate_downloaded_segments(missing, temp_folder, encrypted, task_wrapper, total, confirmed_count_ref, retry_rejected_ref)
        if retry_rejected_ref[0] > 0:
            task_wrapper.warn(f'Retry {retry_num}: {retry_rejected_ref[0]}/{prev_missing_count} segments rejected as HTML/error responses')
        rejected_count_ref[0] += retry_rejected_ref[0]

        recovered = sum(1 for e in missing if not e.missing)
        if recovered < max(1, int(prev_missing_count * _MIN_BATCH_SUCCESS_RATE)):
            task_wrapper.error(
                f'Retry {retry_num}: only {recovered}/{prev_missing_count} segments recovered '
                f'(< {int(_MIN_BATCH_SUCCESS_RATE * 100)}%) — aborting'
            )
            task_wrapper.expected_files_as_progress = False
            return False

    task_wrapper.expected_files_as_progress = False

    succeeded = sum(1 for e in segments if not e.missing)
    if rejected_count_ref[0] > 0:
        task_wrapper.warn(f'{rejected_count_ref[0]} total segments were HTML/error responses across all attempts')
    if succeeded < int(total * _COMPLETION_RATE):
        task_wrapper.error(
            f'Only {succeeded}/{total} segments downloaded after all retries '
            f'(< {int(_COMPLETION_RATE * 100)}%) — download failed'
        )
        return False

    return True


def file_to_hex_string(filepath):
    with open(filepath, "rb") as f:
        data = f.read()
    hex_string = data.hex()
    return hex_string


class DownloadM3u8JobEx(TaskWrapper):
    def __init__(self, name, description, folder_id, filename, url, origin, dest, primary_path, archive_path, temp_path,
                 useHttp2=False):
        super().__init__(name, description)
        self.folder_id = folder_id
        self.filename = filename
        url_list = [u.strip() for u in (url or '').split(';') if u.strip()]
        origin_list = [o.strip() for o in (origin or '').split(';')] if origin else []
        while len(origin_list) < len(url_list):
            origin_list.append('')
        self.url = ';'.join(url_list)
        self.origin = ';'.join(origin_list)
        self.dest = dest
        self.primary_path = primary_path
        self.archive_path = archive_path
        self.temp_path = temp_path
        self.ref_folder_id = folder_id
        self.useHttp2 = useHttp2
        if useHttp2:
            self.weight = 90

    def run(self, db_session: Session):

        if is_blank(self.primary_path) or is_blank(self.archive_path) or is_blank(self.temp_path):
            self.critical('This feature is not ready.  Please configure the app properties and restart the server.')

        source_row = find_folder_by_id(self.folder_id, db_session)
        if source_row is None:
            self.critical('Source Folder not found')
            self.set_failure()
            return

        self.ref_folder_name = source_row.name if hasattr(source_row, 'name') else str(source_row.id)
        self.ref_folder_preview = source_row.preview == True

        is_archive = self.dest == 'archive'

        with temporary_folder(self.temp_path, self) as temp_folder:

            self.debug(f'temp folder: {temp_folder}')

            temp_m3u8_file = os.path.join(temp_folder, 'download.m3u8')
            made_m3u8_file = os.path.join(temp_folder, 'remade.m3u8')
            temp_file = os.path.join(temp_folder, 'download.mp4')

            url_list = [u.strip() for u in self.url.split(';') if u.strip()]
            origin_list = [o.strip() for o in self.origin.split(';')] if self.origin else []
            while len(origin_list) < len(url_list):
                origin_list.append('')

            if not url_list:
                self.error('Could not download m3u8')
                self.set_failure()
                return

            playlist_ready = False
            for index, (stream_url, stream_origin) in enumerate(zip(url_list, origin_list)):
                if stream_origin and not is_valid_url(stream_origin):
                    stream_origin = stream_url

                if index > 0:
                    self.warn(f'File failed to download, trying alternative source: {index + 1}/{len(url_list)}')
                    random_sleep(12, 12, self)

                headers = get_headers(stream_url, True, self, False, stream_origin)

                if headers is None:
                    self.error('Unable to get Headers, stopping')
                    continue

                if not _cloudflare_retry_curl(stream_url, headers, temp_m3u8_file, self, 'm3u8 playlist') \
                        or not os.path.exists(temp_m3u8_file) or os.path.getsize(temp_m3u8_file) <= 0:
                    if os.path.exists(temp_m3u8_file):
                        try:
                            os.remove(temp_m3u8_file)
                        except OSError:
                            pass
                    continue

                self.url = stream_url
                self.origin = stream_origin
                playlist_ready = True
                break

            if not playlist_ready:
                self.error("Failed to download m3u8.")
                _log_tracker_payload(self, self.folder_id, self.filename, ';'.join(url_list), ';'.join(origin_list))
                self.set_failure()
                return

            response_text = read_temp_file(temp_m3u8_file)
            base_url = self.url.rsplit("/", 1)[0] + "/"
            playlist = M3u8Playlist.parse(response_text, base_url)

            self.debug(f'Playlist: {len(playlist.segments())} segments, '
                       f'{len(playlist.key_entries())} keys, '
                       f'{len(playlist.map_entries())} maps')

            # --- Phase 1: download key files ---
            for entry in playlist.key_entries():
                self.info(f'Found Key Definition: {entry.method}')
                self.debug(entry.raw_line)
                key_path = os.path.join(temp_folder, entry.local_name)
                if not _cloudflare_retry_curl(entry.uri, headers, key_path, self, 'encryption key'):
                    self.error("Failed to download encryption key.")
                    _log_tracker_payload(self, self.folder_id, self.filename, self.url, self.origin)
                    self.set_failure()
                    return None
                self.debug(f"Decryption key fetched from: {entry.uri}")

            # --- Phase 2: download map files ---
            for entry in playlist.map_entries():
                self.info('Found Map Definition')
                self.debug(entry.raw_line)
                map_path = os.path.join(temp_folder, entry.local_name)
                if not _cloudflare_retry_curl(entry.uri, headers, map_path, self, 'map file'):
                    self.error("Failed to download map file.")
                    _log_tracker_payload(self, self.folder_id, self.filename, self.url, self.origin)
                    self.set_failure()
                    return None
                self.debug(f"Map file fetched from: {entry.uri}")

            encrypted = playlist.has_encryption()
            segments = playlist.segments()
            total = len(segments)

            # --- Phase 3: download segments ---
            self.info(f'Downloading {total} segments')
            if not _batch_download_segments(segments, temp_folder, headers, encrypted, self, self.useHttp2):
                self.set_failure()
                return None

            # --- Phase 3b: resolve missing segments ---
            missing_segments = [e for e in segments if e.missing]
            if missing_segments:
                self.info(f'{len(missing_segments)} missing segment(s) to resolve')

                # Build index of valid downloaded segments for stand-in lookup.
                # Each entry: (segment_index, absolute_file_path, extension)
                valid_index: list[tuple[int, str, str]] = []
                for idx, entry in enumerate(segments):
                    if not entry.missing and entry.valid and entry.determined_extension:
                        valid_index.append((idx, os.path.join(temp_folder, entry.effective_name), entry.determined_extension))

                if not valid_index:
                    self.warn('No valid segments available to use as stand-ins; all missing segments will be dropped')
                else:
                    for idx, entry in enumerate(segments):
                        if not entry.missing:
                            continue

                        if encrypted:
                            # AES-128 CBC: each segment uses a unique IV derived
                            # from its sequence number.  Substituting a different
                            # segment's ciphertext with the wrong IV produces
                            # completely garbled output, so we drop it instead.
                            self.warn(f'{entry.local_name} is missing in encrypted stream — dropping (IV mismatch would corrupt output)')
                            continue

                        # Find the nearest valid segment — prefer the closest one
                        # before this index, fall back to the closest one after.
                        best = min(valid_index, key=lambda v: abs(v[0] - idx))
                        _, src_path, src_ext = best

                        standin_name = f'seg_{idx}.{src_ext}'
                        standin_path = os.path.join(temp_folder, standin_name)

                        try:
                            shutil.copy2(src_path, standin_path)
                            entry.determined_extension = src_ext
                            entry.valid = True
                            self.debug(f'{entry.local_name} missing — substituted with stand-in from seg index {best[0]}')
                        except OSError:
                            self.warn(f'Could not copy stand-in for {entry.local_name}, dropping segment')

            # --- Phase 4: write rewritten playlist and run ffmpeg ---
            strip_png_prefix_from_directory(temp_folder, self)
            playlist.write(made_m3u8_file)

            arguments = ['ffmpeg', '-allowed_extensions', 'ALL', '-nostdin', '-i', made_m3u8_file, '-c', 'copy',
                         temp_file]

            if self.can_trace():
                self.trace(shlex.join(arguments))

            process = subprocess.Popen(arguments, cwd=temp_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            return_code = str(process.returncode)

            if return_code == '0' and os.path.exists(temp_file) and os.path.isfile(temp_file):

                file_size = os.path.getsize(temp_file)

                if file_size > 0:

                    self.info(f'Found file with size {file_size}')

                    created_time = os.path.getctime(temp_file)
                    created_datetime = datetime.fromtimestamp(created_time)

                    new_file = insert_file(source_row.id, self.filename, 'video/mp4', is_archive, False, file_size,
                                           created_datetime, db_session)

                    dest_path = get_data_for_mediafile(new_file, self.primary_path, self.archive_path)
                    shutil.move(str(temp_file), str(dest_path))

                    source_row.last_date = date_type.today()
                    db_session.commit()

                    self.set_worked()
                    self.set_finished()
                else:
                    self.set_failure()
                    self.error("Could not find MP4 file (0 len)")
            else:
                self.error(f'Return Code {return_code}')
                self.error(stderr.decode('utf-8'))
                self.set_failure()
                sleep(35)
