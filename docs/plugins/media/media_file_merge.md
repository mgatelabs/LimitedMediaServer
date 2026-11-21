# Merge Files

**Action ID:** `action.files.merge`
**Plugin class:** `MergeFilesPlugin`
**Type:** Media files (multiple)
**Feature flag:** File access

## Description

Merges a set of media files into a single file. Each file is probed with ffprobe; the file with the best video stream (highest resolution, then bitrate) supplies the video, and the file with the best audio stream (highest bitrate, then channel count) supplies the audio. The two streams are re-encoded into a single MP4 named after the video source file with a `_merge` suffix.

## Arguments

| Name | ID | Type | Required | Default | Options | Description |
|---|---|---|---|---|---|---|
| File ID | `file_id` | string | Yes | — | — | Comma-separated list of file IDs to merge |
| Preset | `ffmpeg_preset` | select | Yes | — | ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow | ffmpeg encoding speed preset |
| CRF | `ffmpeg_crf` | select | Yes | — | 18–25 | Constant Rate Factor — lower = higher quality, larger file |
| Audio Bitrate | `ffmpeg_abr` | select | Yes | — | 64, 80, 96, 112, 128, 160, 192 | Audio bitrate in kbps |
| Mix-down | `ffmpeg_mix` | select | Yes | `f` | stereo, mono | Audio channel mix-down mode |
| Max Resolution | `ffmpeg_res` | select | No | `src` | src, 4k, 2k, 1080, 720, 320 | Limit output resolution; source keeps original dimensions |
| Postfix | `postfix` | string | No | `_merge` | — | Suffix added before the extension of the output filename |
| Location | `dest` | select | Yes | `primary` | primary, archive | Disk where the merged file is stored |
| Clean Up | `cleanup` | select | No | `keep` | keep, purge, rename | What to do with the source files after a successful merge |

## What It Does

1. Loads each selected file and keeps only files with a `video/` mime type; non-video files are skipped with a warning.
2. Probes each file with ffprobe; files that fail the probe or contain no video and no audio streams are skipped with a warning.
3. Picks the best video stream across all files (highest width × height, ties broken by video bitrate) and the best audio stream (highest audio bitrate, ties broken by channel count).
4. Runs a single local ffmpeg job that maps the chosen video and audio streams (from one or two inputs) and re-encodes them to H.264 + AAC into a temporary file. If no file contains audio, the output is video-only.
5. Registers the temporary file as a new media file in the folder of the video source, named `<video source name><postfix>.mp4`, and moves it into place.
6. Applies the cleanup action (`keep`, `purge`, or `rename`) to every source file used in the merge.
7. Generates a preview thumbnail at the 40% mark, resized to 256px WEBP.

## Notes

- The merge always runs locally; the remote encoder only supports single-input encodes.
- If the best video and best audio come from the same file, it is passed as a single input to ffmpeg.
- `-shortest` is applied so the output ends when either stream ends.
- A single file that contains both a video and an audio stream is a valid input: it will still produce a `_merge` output file.
