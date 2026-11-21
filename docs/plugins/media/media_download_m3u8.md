# Save Video from M3U8

**Action ID:** `action.download.m3u8`
**Plugin class:** `DownloadM3u8Plugin`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Downloads an HLS/M3U8 video stream and saves it as an MP4 file using ffmpeg.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| URL | `url` | URL | Yes | — | M3U8 playlist URL |
| Filename | `filename` | string | Yes | — | Output filename (without extension) |
| Location | `dest` | select | No | `primary` | `primary` or `archive` |

## What It Does

1. Passes the M3U8 URL directly to ffmpeg with stream-copy mode (no re-encode).
2. Saves the output as an MP4 in the target folder.
3. Creates a database record and generates a preview thumbnail.

For encrypted streams or playlists that require custom segment handling, use **Save Video from M3U8 (Ex)** instead.
