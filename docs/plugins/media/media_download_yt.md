# Save Video from YouTube

**Action ID:** `action.download.yt`
**Plugin class:** `DownloadYtPlugin`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Downloads a video from YouTube (or any yt-dlp supported site) and saves it as an MP4 in a media folder.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| URL | `url` | URL | Yes | — | YouTube (or compatible) video URL |
| Destination | `dest` | select | No | `primary` | `primary` or `archive` |

## What It Does

1. Invokes yt-dlp, preferring the best available MP4 format.
2. Saves the downloaded file into the target media folder.
3. Creates a database record and generates a preview thumbnail.
