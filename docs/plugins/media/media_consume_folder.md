# Import Folder

**Action ID:** `action.consume.folder`
**Plugin class:** `ConsumeForFolderPlugin`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Imports media files from a local filesystem path into a destination folder in the media library.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| Folder | `folder` | string | Yes | — | Absolute path on the server to import from |
| Location | `dest` | select | No | `primary` | `primary` or `archive` — which storage drive to place files on |

## What It Does

1. Reads all files from the given source folder path.
2. Moves each file into the target media folder at the specified storage location.
3. Creates database records for each imported file.
4. Generates preview thumbnails for video files.
