# Burn Subtitles

Three plugins live in this file covering single-file, multi-file, and folder-level subtitle burning.

---

## Burn Subtitles (File)

**Action ID:** `action.file.subtitle`
**Plugin class:** `SubtitleForFilePlugin`
**Type:** Media file
**Feature flag:** File access

### Description

Burns a subtitle track into a single video file (hard subtitles), producing a new encoded file.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Offset | `offset` | string | `0` | Subtitle timing offset in milliseconds |
| Postfix | `postfix` | string | — | Suffix to append to the output filename |
| Preset | `ffmpeg_preset` | select | `medium` | ffmpeg encoding speed preset |
| CRF | `ffmpeg_crf` | string | `23` | Constant Rate Factor |
| Audio Bitrate | `ffmpeg_abr` | string | `128k` | Audio bitrate |
| Audio Mix | `ffmpeg_mix` | select | — | Audio channel mixing mode |
| Location | `dest` | select | `primary` | `primary` or `archive` for the output file |
| Clean Up | `cleanup` | select | `keep` | `keep`, `purge`, or `rename` for the original |

### What It Does

Re-encodes the video with the subtitle track burned in using ffmpeg's subtitle filter. Applies the timing offset before burning. Handles the original according to the `cleanup` setting.

---

## Burn Subtitles (Files)

**Action ID:** `action.files.subtitle`
**Plugin class:** `SubtitleForFilesPlugin`
**Type:** Media files (multiple)
**Feature flag:** File access

### Description

Same as Burn Subtitles (File) but processes a comma-separated list of file IDs.

### Arguments

Same as Burn Subtitles (File).

---

## Burn Subtitles (Folder)

**Action ID:** `action.folder.subtitle`
**Plugin class:** `SubtitleForFolderPlugin`
**Type:** Media folder
**Feature flag:** Folder access

### Description

Burns subtitles into all video files in a folder that have an associated subtitle track.

### Arguments

Same as Burn Subtitles (File) — applied uniformly to all eligible files in the folder.
