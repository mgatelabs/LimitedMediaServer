# Book Info

**Action ID:** `action.book.info`
**Plugin class:** `UpdateAllTagsTask`
**Type:** General (all books)
**Feature flag:** `MANAGE_VOLUME`

## Description

Dumps a JSON summary of all books in the library to the task log. Useful for auditing or exporting the current book list.

## Arguments

None.

## What It Does

1. Queries all books visible to the current user (respecting content rating limits).
2. For each book collects: `id`, `name`, `active`, `processor`, and `updated` (ISO date).
3. Logs the full list as a single JSON string at `INFO` level.

## Output JSON Shape

```json
[
  {
    "id": "my-book",
    "name": "My Book",
    "active": true,
    "proc": "SomeProcessor",
    "updated": "2024-01-15"
  }
]
```
