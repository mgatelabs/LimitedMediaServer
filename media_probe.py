import subprocess
import json

from thread_utils import TaskWrapper, NoOpTaskWrapper

# Map container names to canonical extensions
FORMAT_EXTENSION_MAP = {
    "mpegts": "ts",
    "mp4": "mp4",
    "mov": "mov",
    "matroska": "mkv",
    "avi": "avi",
    "webm": "webm",
    "ogg": "ogg",
    # Add others if needed
}

def get_file_formats(filepath: str, tw: TaskWrapper = NoOpTaskWrapper()) -> str | None:
    """Return list of format names for a media file using ffprobe."""
    try:
        # Run ffprobe and get JSON output
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                filepath
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        data = json.loads(result.stdout)

        if tw.can_trace():
            tw.trace(str(data))

        # ffprobe may report multiple format aliases separated by commas
        format_name = data.get("format", {}).get("format_name", "")

        if format_name:
            primary_format = format_name.split(",")[0]
            return FORMAT_EXTENSION_MAP.get(primary_format, primary_format)

        # Secondary: fall back to stream codec info
        stream_codecs = []
        for stream in data.get("streams", []):
            codec = stream.get("codec_name")
            if codec:
                stream_codecs.append(codec)

        if stream_codecs:
            return 'ts'

        return None

    except subprocess.CalledProcessError as e:
        tw.error(f"ffprobe error: {e.stderr.strip()}")
        return None
    except FileNotFoundError:
        tw.error("ffprobe not found. Make sure FFmpeg is installed and ffprobe is in PATH.")
        return None

# Example usage:
if __name__ == "__main__":
    formats = get_file_formats("example.mp4")
    print(formats)  # e.g. ['mov', 'mp4', 'm4a', '3gp', '3g2', 'mj2']
