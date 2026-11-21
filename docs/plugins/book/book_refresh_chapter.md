# Refresh Chapter

**Action ID:** `action.book.refresh.chapter`
**Plugin class:** `RefreshChapterPlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

## Description

Opens and re-saves every image in a single chapter without changing content or filenames. Useful when images have become corrupted, contain invalid metadata, or were written with a sub-optimal encoder — a lossless round-trip through Pillow normalises the file on disk.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book containing the chapter |
| Chapter | `chapter_id` | string | Yes | The chapter to refresh, e.g. `0001` or `0012.5` |

## What It Does

1. Resolves the chapter folder: `<volume_folder>/<book_id>/<chapter_id>/`.
2. Lists every file whose extension is in the supported set (`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`).
3. For each file: opens it with Pillow, calls `img.load()` to force a full decode, then writes it back to the same path losslessly (WEBP lossless for `.webp`, PNG for all others).
4. Files that cannot be opened are logged as warnings and skipped; the task continues.
5. Reports per-file progress.
6. After all images are processed, chains `UpdateSingleBookStats` via `run_after` to rebuild the chapter DB record and regenerate the chapter preview thumbnail.

## Notes

- No files are renamed or deleted — the chapter index is unchanged.
- The re-save is always lossless: WEBP files stay WEBP lossless; all other formats are written as PNG.
- If the chapter folder does not exist, the plugin returns an error at task-creation time and no task is queued.
