# Save Video from M3U8 (Ex)

Two plugins live in this file.

---

## Save Video from M3U8 (Ex)

**Action ID:** `action.download.m3u8.ex`
**Plugin class:** `DownloadM3u8PluginEx`
**Type:** Media folder
**Feature flag:** Folder access
**Platform:** Linux only

### Description

Advanced M3U8 downloader that handles encrypted HLS streams, segment maps, and partial download recovery. Preferred over the simple M3U8 plugin for streams with `#EXT-X-KEY` encryption or non-standard segment layouts.

### Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| URL | `url` | URL | Yes | — | M3U8 playlist URL |
| Filename | `filename` | string | Yes | — | Output filename |
| Location | `dest` | select | No | `primary` | `primary` or `archive` |
| Origin | `origin` | string | No | — | Referer/origin URL for authenticated requests |

### What It Does

1. Parses the M3U8 playlist, resolving encryption keys and segment maps.
2. Downloads segments individually, retrying failed segments.
3. Decrypts encrypted segments using the key from the playlist.
4. Concatenates and muxes segments into a final MP4.
5. Creates a database record and generates a preview thumbnail.

---

## Download M3U8 (Ex) & Subtitle

**Action ID:** `action.download.m3u8.ex.sub`
**Plugin class:** `DownloadM3u8SubtitlePluginEx`
**Type:** Media folder
**Feature flag:** Folder access
**Platform:** Linux only

### Description

Combines an M3U8 (Ex) video download with a simultaneous subtitle file download in one action.

### Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Video URL | `url` | URL | Yes | M3U8 playlist URL |
| Video Filename | `filename` | string | Yes | Output filename for the video |
| Location | `dest` | select | No | `primary` or `archive` |
| Origin | `origin` | string | No | Referer for the video request |
| Subtitle URL | `sub_url` | URL | Yes | Direct URL of the subtitle file |
| Subtitle Filename | `sub_filename` | string | Yes | Output filename for the subtitle |
| Subtitle Origin | `sub_origin` | string | No | Referer for the subtitle request |

### What It Does

Creates two tasks: a `DownloadM3u8JobEx` for the video and a `DownloadFileJob` for the subtitle, queued to run together.
