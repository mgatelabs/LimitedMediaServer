# De-Duplicate Music

**Action ID:** `action.deduplicate.music`
**Plugin class:** `CleanFolderTask`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Cleans up a music folder by removing duplicate tracks, stripping leading numbers from filenames, or comparing against another folder to find overlap.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| Mode | `mode` | select | No | `dupes` | See modes below |
| Other Folder | `other_folder_id` | select | No | — | Second folder to compare against (used in `dupes` mode) |

## Modes

| Value | Description |
|---|---|
| `dupes` | Find and remove tracks that are duplicated within the folder, or exist in the "Other Folder" if one is specified |
| `dupes_artist_title` | Detect duplicates by matching artist + title metadata rather than file content |
| `front_numbers` | Strip leading track numbers from filenames (e.g. `01 - Song.mp3` → `Song.mp3`) |

## What It Does

1. Scans the target folder for audio files.
2. Depending on mode, either compares file content/metadata for duplicates or rewrites filenames.
3. Removes duplicate files or renames files in place.
4. Updates database records to reflect removed or renamed files.
