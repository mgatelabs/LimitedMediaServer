# Update MP3 Tags

**Action ID:** `action.update.mp3.tags.folder`
**Plugin class:** `Mp3TagFolderTask`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Updates ID3 metadata tags for all audio files in a folder. Artist and title are extracted from the filename; album, genre, and year can be supplied explicitly. Also strips embedded YouTube codes from filenames when present.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Genre | `genre` | string | No | Genre tag to write to all files |
| Album | `album` | string | No | Album tag to write to all files |
| Year | `year` | string | No | Year tag to write to all files |

## What It Does

1. Scans the folder for audio files (MP3 and compatible formats).
2. Parses artist and title from each filename (expects `Artist - Title` or similar conventions).
3. Strips any trailing YouTube video code from the filename if present.
4. Writes the parsed artist/title plus any supplied genre, album, and year to the file's ID3 tags.
5. Renames the file if the cleaned filename differs from the original.
