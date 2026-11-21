# Encode File

Two plugins live in this file covering single-file and multi-file encoding.

---

## Encode File

**Action ID:** `action.file.encode`
**Plugin class:** `EncodeForFilePlugin`
**Type:** Media file
**Feature flag:** File access

### Description

Re-encodes a video file using ffmpeg with configurable quality and audio settings.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Preset | `ffmpeg_preset` | select | `medium` | ffmpeg encoding speed preset (e.g. `fast`, `medium`, `slow`) |
| CRF | `ffmpeg_crf` | string | `23` | Constant Rate Factor — lower = higher quality, larger file |
| Audio Bitrate | `ffmpeg_abr` | string | `128k` | Audio bitrate |
| Audio Mix | `ffmpeg_mix` | select | — | Audio channel mixing mode |
| Postfix | `postfix` | string | — | Suffix to append to the output filename |
| Clean Up | `cleanup` | select | `keep` | `keep` = keep original; `purge` = delete original; `rename` = rename original |

### What It Does

Re-encodes the file with H.264 video and AAC audio using the specified ffmpeg parameters. On completion handles the original file according to the `cleanup` setting.

---

## Encode Files

**Action ID:** `action.files.encode`
**Plugin class:** `EncodeForFilesPlugin`
**Type:** Media files (multiple)
**Feature flag:** File access

### Description

Same as Encode File but processes a comma-separated list of file IDs.

### Arguments

Same as Encode File, plus the implicit multi-file selection of comma-separated IDs.
