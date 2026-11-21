# Merge Images

**Action ID:** `action.book.merge.images`
**Plugin class:** `BookMergeImagesPlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

## Description

Merges multiple images within a single chapter into single vertically-stacked images, according to a JSON-defined list of groups. Useful for reassembling pages that were incorrectly split. Each group's images are composited in order from top to bottom and written back to the first filename in the group; the remaining source files are removed from disk and the chapter record is updated.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book containing the chapter |
| Chapter ID | `chapter_id` | string | Yes | The chapter whose images will be merged |
| Merge Groups | `merge_groups` | long string | Yes | JSON array of groups; each group is an array of 2+ filenames to stack vertically |

## Merge Groups Format

```json
[
  ["0001.webp", "0002.webp"],
  ["0005.webp", "0006.webp", "0007.webp"]
]
```

Each inner array is one merge operation. All images in a group must have the same width. The result is written to the first filename in the group; all other files in the group are deleted.

## What It Does

Operates in two phases:

**Phase 1 — Disk merges (no DB writes)**

For each group:

1. Validates all filenames exist on disk — skips the group with a `WARN` if any are missing.
2. Opens all images and checks that their widths match — skips the group with a `WARN` if there is a mismatch.
3. Stacks images vertically in the order listed, compositing them into a single image.
4. Writes the result to `temp.webp` in the chapter folder (lossless WEBP).
5. Deletes all original files in the group from disk.
6. Renames `temp.webp` to the first filename in the group.

If one group fails, the remaining groups still run. Any `temp.webp` left over from a failed group is cleaned up before Phase 2.

**Phase 2 — Renumber and update DB (single commit)**

After all groups have been processed:

1. Renumbers all remaining files in the chapter folder sequentially from `0001` to close any gaps left by the deleted images (e.g. `0001, 0003, 0006` → `0001, 0002, 0003`). This maximises compression efficiency in the stored filename list.
2. Updates the chapter's `image_names` and `page_count` in the database with the renumbered file list.
3. Commits once.

## Notes

- Groups are processed in the order they appear in the JSON. If one group fails, the remaining groups still run.
- The output file always uses the first filename's extension as its name (e.g. if the first file is `0001.webp`, the merged result is `0001.webp`).
- Images are converted to RGB before compositing, so RGBA/palette-mode inputs are handled safely.
