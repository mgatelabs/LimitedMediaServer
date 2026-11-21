# Save Music from YouTube

**Action ID:** `action.download.yt.music`
**Plugin class:** `DownloadMusicFromYtTask`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Downloads audio from a YouTube URL as MP3, optionally splitting by chapter markers. Extracts and embeds album art into the resulting files.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| URL | `url` | URL | Yes | — | YouTube URL |
| Output | `split_chapters` | select | No | `false` | `true` = split into individual files by chapter timestamps |
| Destination | `dest` | select | No | `primary` | `primary` or `archive` |

## What It Does

1. Invokes yt-dlp to extract audio as MP3.
2. If `split_chapters=true`, splits the audio into separate files at each chapter marker.
3. Downloads the video thumbnail and embeds it as album art in each MP3.
4. Creates database records and previews for all output files.
