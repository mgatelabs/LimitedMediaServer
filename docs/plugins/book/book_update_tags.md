# Update Tags

Two plugins live in this file covering bulk and single-book tag updates.

---

## Update Tags (All Books)

**Action ID:** `action.books.tags`
**Plugin class:** `CheckAllTagsTask`
**Type:** General (all books)
**Feature flag:** `MANAGE_VOLUME`

### Description

Fetches tags from each book's processor and writes them to the database. Only targets active books that currently have no tags assigned. Optionally filtered to a specific processor.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Filter | `filter` | select | `*` | Processor to target; `*` = all processors |

### What It Does

1. Queries all active books without tags, optionally filtered by processor.
2. For each book, calls the processor's tag-fetching logic.
3. Updates the `Book.tags` field in the database.
4. Calls `sync_book_tags()` to keep the global tag table consistent.

---

## Update Tags (Single Book)

**Action ID:** `action.book.tags`
**Plugin class:** `UpdateSingleTagsTask`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

### Description

Fetches and stores tags for a single book from its configured processor.

### Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book whose tags to update |

### What It Does

Only runs if the book is currently active. Calls the processor's tag-fetching logic, saves the result to `Book.tags`, and calls `sync_book_tags()`.
