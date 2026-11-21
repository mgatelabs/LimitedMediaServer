# Check Book Status

Two plugins share this action name and live in the same file.

---

## Check Book Status (All Books)

**Action ID:** `action.books.status`
**Plugin class:** `CheckAllStatusTask`
**Type:** General (all books)
**Feature flag:** `MANAGE_VOLUME`

### Description

Checks whether every active book in the library is still publishing new content, with an optional filter to limit checks to a specific processor.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Filter | `filter` | select | `*` | Processor to check; `*` runs against all processors |

### What It Does

1. Queries all active books, optionally filtered by processor ID.
2. For each book, calls the processor's `ia_active()` method to determine if the series is still publishing.
3. If a book is no longer active, updates its `active` flag in the database.
4. Creates one `CheckBookStatusTask` per book and queues them individually so they can run in parallel.

---

## Check Book Status (Single Book)

**Action ID:** `action.book.status`
**Plugin class:** `UpdateSingleStatusTask`
**Type:** Book-specific
**Feature flag:** `MANAGE_VOLUME`

### Description

Checks whether a single book is still publishing.

### Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | The book to check |

### What It Does

Same as the all-books variant but scoped to one book. Only creates a task if the book is currently marked active.
