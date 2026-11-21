# Convert Chapters

**Action ID:** `action.convert.chapters`
**Plugin class:** `ConvertChaptersPlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

## Description

Renames chapter folders that use the legacy `chapter-X` naming convention to the standard zero-padded numeric format (`000X`). Also renames the associated preview image in `.previews/`. After renaming, triggers an Update Cache task to rebuild the book's DB definition.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book whose chapters to convert |

## What It Does

1. Loads all chapters for the given book from the database.
2. For each chapter whose `chapter_id` starts with `chapter-`, extracts the numeric suffix and builds a zero-padded replacement name (e.g. `chapter-7` → `0007`).
3. Renames the chapter folder on disk.
4. Renames the preview file at `.previews/<old_id>.webp` to `.previews/<new_id>.webp` if it exists.
5. Updates the chapter record in the database.
6. On completion, chains an `UpdateSingleBookStats` task to regenerate the book cache.
