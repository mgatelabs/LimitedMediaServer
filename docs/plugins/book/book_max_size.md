# Max Size

**Action ID:** `action.book.max.size`
**Plugin class:** `MaxSizePlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

## Description

Scans every chapter of a book and resizes any WEBP image whose width or height exceeds the configured limits. Aspect ratio is always preserved. Images already within bounds are left untouched. Useful for reducing storage and bandwidth when source images are oversized for the target display.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book to process |
| Max Width | `max_width` | string | Conditional | Maximum image width in pixels. Leave blank for unbounded. |
| Max Height | `max_height` | string | Conditional | Maximum image height in pixels. Leave blank for unbounded. |

**At least one of Max Width or Max Height must be provided.** Both may be provided together.

## What It Does

1. Loads all chapters for the given book.
2. For each chapter, iterates over every `.webp` file in the chapter folder.
3. Opens each image and checks its dimensions:
   - If width > Max Width (when set) **or** height > Max Height (when set), the image is resized.
   - Images already within both limits are skipped.
4. Resizing uses `Image.thumbnail(box, Image.LANCZOS)`:
   - `thumbnail` only ever scales **down** — it will never enlarge an image.
   - Aspect ratio is always preserved; the image fits within the given box without cropping.
   - LANCZOS is the highest-quality downscaling filter available in Pillow (windowed sinc, minimises aliasing).
5. The resized image is written back to the same path as WEBP lossless.
6. Reports per-chapter progress. Respects cancellation between chapters.
7. After all chapters are processed, chains `UpdateSingleBookStats` via `run_after` to rebuild DB records and regenerate chapter preview thumbnails.

## Resize Behaviour

| Max Width | Max Height | Effect |
|-----------|------------|--------|
| 1200 | _(blank)_ | Width capped at 1200px; height scales proportionally |
| _(blank)_ | 2000 | Height capped at 2000px; width scales proportionally |
| 1200 | 2000 | Image fits within a 1200×2000 box; the larger dimension drives the scale |

## Notes

- Only `.webp` files are processed; other formats in the chapter folder are ignored.
- Because `thumbnail` never upscales, images smaller than the limits are always left unchanged.
- Chapter folders that do not exist on disk are silently skipped.
