# Media Info

**Action ID:** `action.file.info`
**Plugin class:** `MediaInfoForFilePlugin`
**Type:** Media file
**Feature flag:** File access

## Description

Displays detailed media information for a video or audio file by probing it with ffmpeg.

## Arguments

None beyond the implicit file selection.

## What It Does

1. Runs `ffprobe` (via ffmpeg) on the file.
2. Logs the parsed stream information — container format, video codec, resolution, frame rate, audio codec, bitrate, duration, etc. — as structured log entries.
