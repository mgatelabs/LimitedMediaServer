import logging
import subprocess
import json

from plugin_methods import plugin_select_arg, plugin_select_values
from thread_utils import TaskWrapper, NoOpTaskWrapper

FFMPEG_PRESET = plugin_select_arg('Preset', 'ffmpeg_preset', 'medium', plugin_select_values(
    'ultrafast: Minimal compression; very fast but produces large files.', 'ultrafast', 'superfast', 'superfast',
    'veryfast', 'veryfast', 'faster', 'faster', 'fast', 'fast', 'medium (default): Balanced between speed and quality.',
    'medium', 'slow', 'slow', 'slower', 'slower',
    'veryslow: Maximum compression; slowest but produces smaller files with high quality.', 'veryslow'),
                                  'The presets prioritize encoding speed vs. compression efficiency (file size and quality). From fastest to slowest (and lowest to highest quality)', 'com')
FFMPEG_PRESET_VALUES = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']

FFMPEG_CRF = plugin_select_arg('Constant Rate Factor', 'ffmpeg_crf', '23',
                               plugin_select_values('18 (Higher Quality)', '18', '19', '19', '20', '20', '21', '21',
                                                    '22', '22', '23 (Default)',
                                                    '23', '24', '24', '25 (Lower Quality)', '25'),
                               'Key parameter for controlling the quality and file size of videos', 'com')
FFMPEG_CRF_VALUES = ['18', '19', '20', '21', '22', '23', '24', '25']

FFMPEG_AUDIO_BIT = plugin_select_arg('Audio Bit Rate', 'ffmpeg_abr', '128',
                               plugin_select_values('64', '64', '80', '80', '96', '96', '112', '112',
                                                    '128', '128', '160',
                                                    '160', '192', '192'),
                               'Key parameter for controlling the audio quality and file size of videos', 'com')

FFMPEG_AUDIO_BIT_RATE_VALUES = ['64', '80', '96', '112', '128', '160', '192']


FFMPEG_STEREO = plugin_select_arg('Mix-down', 'ffmpeg_mix', 'f',
                               plugin_select_values('Stereo', 't', 'Mono', 'f'),
                               'Key parameter for controlling the audio channels and file size of videos', 'com')

FFMPEG_STEREO_VALUES = ['f', 't']


def get_ffmpeg_f_argument_from_mimetype(mime: str) -> str:
    if mime == 'video/mp4':
        return 'mp4'
    if mime == 'video/webm':
        return 'webm'
    if mime == 'video/x-matroska':
        return 'mkv'
    if mime == 'video/quicktime':
        return 'mov'
    if mime == 'video/x-msvideo':
        return 'avi'
    if mime == 'video/ogg':
        return 'ogg'
    if mime == 'video/mpeg' or mime == 'video/mpg':
        return 'mpeg'
    return 'mp4'


def encode_video(input_file, output_file, input_format=None, ffmpeg_preset: str = 'medium', constant_rate_factor=23,
                 stereo=True, audio_bitrate=128, log: TaskWrapper = NoOpTaskWrapper()) -> bool:
    try:
        # Construct the FFMPEG command
        command = ["ffmpeg"]

        # Add the input format if specified
        if input_format:
            command.extend(["-f", input_format])

        channels = 1
        if stereo:
            channels = 2

        command.extend([
            "-y", "-i", input_file,
            "-vf", "scale='min(3840,iw)':-2",
            "-c:v", "libx264",
            "-preset", ffmpeg_preset,
            "-profile:v", "high",
            "-level", "4.2",
            "-pix_fmt", "yuv420p",
            "-crf", str(constant_rate_factor),
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            "-ac", str(channels),
            output_file
        ])

        # Run the command and wait for it to complete
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Check if the process was successful
        if result.returncode != 0:
            log.error("FFMPEG failed with the following error:")
            log.error(result.stderr)
            return False

        log.info("FFMPEG completed successfully!")
        return True

    except Exception as e:
        log.error(f"An error occurred: {e}")
        logging.exception(e)
        return False


def burn_subtitles_to_video(input_file, srt_file, output_file, offset:int = 0, input_format='mp4',
                            ffmpeg_preset: str = 'medium', constant_rate_factor: int = 23, stereo=True,
                            audio_bitrate=128, log: TaskWrapper = NoOpTaskWrapper()):
    try:

        # Construct the FFMPEG command
        command = ["ffmpeg"]

        # Add the input format if specified
        if input_format:
            command.extend(["-f", input_format])

        channels = 1
        if stereo:
            channels = 2

        command.extend([
            "-y", "-i", input_file,
            "-vf", f"scale='min(3840,iw)':-2,subtitles={srt_file}",
            "-c:v", "libx264",
            "-preset", ffmpeg_preset,
            "-profile:v", "high",
            "-level", "4.2",
            "-pix_fmt", "yuv420p",
            "-crf", str(constant_rate_factor),
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            "-ac", str(channels),
            output_file
        ])

        # Run the command and wait for it to complete
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Check if the process was successful
        if result.returncode != 0:
            log.error("FFMPEG failed with the following error:")
            log.error(result.stderr)
            return False

        log.info("FFMPEG completed successfully!")
        return True

    except Exception as e:
        log.error(f"An error occurred: {e}")
        logging.exception(e)
        return False

# Utilities

def get_video_duration(input_file, input_format: str):
    result = subprocess.run(['ffmpeg', "-f", input_format, '-i', input_file], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    # Extract duration from ffmpeg output
    duration_line = [line for line in result.stderr.decode().split('\n') if 'Duration' in line]
    if not duration_line:
        raise ValueError("Could not determine video duration")
    duration_str = duration_line[0].split(',')[0].split('Duration: ')[1]
    h, m, s = map(float, duration_str.split(':'))
    return int(h * 3600 + m * 60 + s)


def generate_video_thumbnail(input_file, input_format: str, output_file, percentage):
    # Get the video duration
    duration = get_video_duration(input_file, input_format)
    # Calculate the time at the specified percentage
    time = duration * percentage / 100
    # Extract the frame at the calculated time and save as PNG
    subprocess.run(['ffmpeg', '-ss', str(time), "-f", input_format, '-i', input_file, '-frames:v', '1', output_file, '-y'], check=True)


def get_media_info(file_path: str, logger: TaskWrapper):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        file_path
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        logger.set_failure()
        logger.error(f"Error: {result.stderr}")
        return None

    try:
        metadata = json.loads(result.stdout)

        info = {
            "format": metadata.get("format", {}).get("format_name", "Unknown"),
            "duration": metadata.get("format", {}).get("duration", "Unknown"),
            "bit_rate": metadata.get("format", {}).get("bit_rate", "Unknown"),
            "streams": []
        }

        for stream in metadata.get("streams", []):
            stream_info = {
                "codec": stream.get("codec_name", "Unknown"),
                "type": stream.get("codec_type", "Unknown"),
                "bit_rate": stream.get("bit_rate", "Unknown")
            }

            if stream_info["type"] == "video":
                stream_info.update({
                    "width": stream.get("width", "Unknown"),
                    "height": stream.get("height", "Unknown"),
                    "fps": eval(stream.get("avg_frame_rate", "0/1")) if stream.get("avg_frame_rate") else "Unknown"
                })

            if stream_info["type"] == "audio":
                stream_info.update({
                    "channels": stream.get("channels", "Unknown"),
                    "sample_rate": stream.get("sample_rate", "Unknown")
                })

            info["streams"].append(stream_info)

        logger.info(json.dumps(info))

        return info

    except json.JSONDecodeError:
        print("Error decoding JSON output")
        return None