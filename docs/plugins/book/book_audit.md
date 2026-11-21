# Book Audit

**Action ID:** `action.book.audit`
**Plugin class:** `BookAuditPlugin`
**Type:** General (all books)
**Feature flag:** `MANAGE_VOLUME`

## Description

Read-only audit that scans the book library for four categories of common problems. The mode argument selects which audit to run.

## Arguments

| Name | ID | Type | Default | Options | Description |
|---|---|---|---|---|---|
| Mode | `mode` | select | `aspect` | `aspect`, `split_images`, `dup_books`, `dup_chapters` | Which audit to run |
| Date Limit | `date_limit` | select | `0` (No Limit) | `0`, `1`, `2`, `3`, `5`, `10`, `20`, `30` | Only audit books whose `last_date` is within this many days of today. `0` = no filtering. |

## Modes

### `aspect` — Wrong Aspect Ratio
Scans every page-style book for images that are more than 3× taller than the book's normal portrait page (stacked images). Uses the median aspect ratio of middle pages as the baseline. Landscape images are excluded from the baseline. Reports any chapter that has stacked images via `WARN` log entries.

### `split_images` — Split Images
Detects chapters where images were cut in half unequally. Looks for repeating pairs where a tall image is immediately followed by a shorter image of the same width (within 2% tolerance), requiring at least 3 consecutive such pairs. Only page-style books are checked. Reports affected chapter IDs per book via `WARN` log entries.

### `dup_books` — Duplicate Books
Compares books against each other to find books with nearly identical content. Fingerprints the first 10 images of each book's first chapter using pHash. Two books are flagged as duplicates if 6 or more images match (pHash distance ≤ 10). Reports pairs via `WARN` log entries.

### `dup_chapters` — Duplicate Chapters
Finds chapters that are decimal variants of an integer chapter (e.g. `0001.5` vs `0001`) and checks whether their image content overlaps by 90% or more. Reports suspected duplicate chapter groups via `WARN` log entries.

## Output

All findings are emitted as `WARN`-level log entries with a structured prefix:

- `ASPECT book=<id> chapter=<id> images=[...] threshold=<n> (normal=<n>)`
- `SPLIT_IMAGES book=<id> chapters=[...]`
- `DUP_BOOKS book_a=<id> book_b=<id> matches=<n>/<total>`
- `DUP_CHAPTERS book=<id> int_chapter=<id> dec_chapters=[...] overlap=<pct>%`
