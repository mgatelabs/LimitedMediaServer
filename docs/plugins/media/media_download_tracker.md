# Import from Media Tracker

Two plugins live in this file.

---

## Import from Media Tracker (Folder)

**Action ID:** `action.download.tracker`
**Plugin class:** `DownloadTrackerPlugin`
**Type:** Media folder
**Feature flag:** Folder access

### Description

Accepts a base64-encoded JSON payload from the Media Tracker tool and creates the appropriate download jobs (M3U8 or direct file) for each item in the payload.

### Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| Tracker Payload | `payload` | string | Yes | — | Base64-encoded JSON from the Media Tracker |
| Location | `dest` | select | No | `primary` | `primary` or `archive` |
| M3u8 Method | `m3u8_meth` | select | No | `ex` | `ex` = advanced M3U8 handler; `simple` = basic ffmpeg |

### What It Does

1. Base64-decodes and parses the tracker JSON payload.
2. For each item in the payload, determines whether it is an M3U8 stream or a direct file URL.
3. Creates a `DownloadM3u8JobEx` / `DownloadM3u8Job` or `DownloadFileJob` accordingly.
4. All jobs are queued to run against the target folder.

---

## Import from Media Tracker (Global)

**Action ID:** `action.download.tracker.global`
**Plugin class:** `DownloadTrackerMediaPlugin`
**Type:** Media library-wide
**Feature flag:** Admin

### Description

Same as the folder-scoped variant but can target any folder in the library via a folder picker argument.

### Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| Tracker Payload | `payload` | string | Yes | — | Base64-encoded JSON from the Media Tracker |
| Folder | `folder_id` | select | No | — | Destination folder (chosen from library) |
| Location | `dest` | select | No | `primary` | `primary` or `archive` |
| M3u8 Method | `m3u8_meth` | select | No | `ex` | `ex` or `simple` |
