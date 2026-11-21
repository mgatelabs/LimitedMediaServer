# Convert Format

**Action ID:** `action.convert.format`
**Plugin class:** `ConvertFormatPlugin`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

## Description

Converts all images in a book's chapters to lossless WebP. This also corrects each image to fit the hard WebP limit: CMYK is converted to RGB, any width above 2048 pixels is scaled down, and any image taller than 16383 pixels is split into uniform slices, with every image in the chapter renumbered sequentially afterward (0001.webp, 0002.webp, ...).

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book whose images to convert |

## What It Does

1. Loads all chapters for the given book.
2. For each chapter, converts every image file to WebP using `convert_images_to_format()`, applying the size corrections above.
3. Updates chapter records in the database to reflect new filenames after conversion.
4. Reports progress per chapter via `update_progress()`.
5. Respects cancellation between chapters.
