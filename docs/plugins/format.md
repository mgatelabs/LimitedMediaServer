# Plugin Documentation Format Guide

This file defines the standard format for plugin documentation files under `docs/plugins/`.

---

## File Location

- One file per plugin source file, named to match: `book_convert_format.py` → `book_convert_format.md`
- Place under the subdirectory matching the plugin category: `book/`, `media/`, `general/`
- If a single source file contains multiple plugin classes, document all of them in one file (see the multi-plugin layout below)

---

## Single-Plugin Layout

```markdown
# Plugin Display Name

**Action ID:** `action.category.name`
**Plugin class:** `ClassName`
**Type:** Book-specific | Book-general (all books) | Media | General
**Feature flag:** `FEATURE_FLAG_NAME`

## Description

One short paragraph explaining what this plugin does and when you would use it.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| Book ID | `book_id` | string | Yes | — | ... |
| Some Flag | `flag` | select | No | `n` | ... |
| Free Text | `value` | string | Conditional | — | ... |

## What It Does

Numbered steps describing the task execution in order.

1. ...
2. ...

## Notes

Optional section. Use for caveats, edge cases, or behaviour that is non-obvious from the description alone.
```

---

## Multi-Plugin Layout

When a single `.py` file contains more than one plugin class, use a single `# Title` heading for the file, then `---` separators between plugins. Each plugin gets `## Plugin Name` as its heading, with `###` for its sub-sections.

```markdown
# File Topic

Brief sentence explaining that this file contains multiple related plugins.

---

## First Plugin Name

**Action ID:** `action.category.first`
**Plugin class:** `FirstPlugin`
**Type:** ...
**Feature flag:** ...

### Description
### Arguments
### What It Does

---

## Second Plugin Name

**Action ID:** `action.category.second`
...
```

---

## Arguments Table Columns

Include only the columns that are relevant — omit `Default` for plugins with no defaults, omit `Options` for plugins with no select fields.

| Column | When to include | Values |
|--------|----------------|--------|
| Name | Always | Human-readable label |
| ID | Always | The `arg_id` string used in code |
| Type | Always | `string`, `select`, `longstring`, `filename`, `url` |
| Required | When any arg is optional | `Yes`, `No`, `Conditional` |
| Default | When any arg has a default | The default value, or `—` for none |
| Options | For `select` type fields | Comma-separated list of valid values |
| Description | Always | What the arg does |

**Conditional** means the arg is optional on its own but a rule applies (e.g. "at least one of X or Y must be provided"). State the rule in a note below the table.

---

## Argument Types

| Type | Notes |
|------|-------|
| `string` | Single-line text input. Validated as integer in code where needed — note the constraint in the description. |
| `select` | Dropdown with a fixed list. Always document valid values and the default. |
| `longstring` | Multi-line text, e.g. for JSON input. |
| `filename` | File picker. |
| `url` | URL input field. |

---

## "What It Does" Section

Write numbered steps that follow the task's `run()` method in order. Include:

- How it traverses the data (all books, one book, one chapter)
- What it reads, transforms, and writes
- Whether it respects cancellation (`is_cancelled` check between chapters)
- What it does on completion (`run_after`, DB commit, preview regeneration)

Keep each step to one sentence. Use sub-bullets for detail if a step is complex.

---

## Optional Sections

Add these only when they add real value:

| Section | When to use |
|---------|------------|
| **Modes** | Plugin has a `mode` select arg that fundamentally changes behaviour |
| **Format** | Plugin accepts structured input (e.g. JSON) that needs its own example |
| **Output** | Plugin emits structured log output the caller needs to parse |
| **Notes** | Edge cases, non-obvious constraints, or performance caveats |
| **Resize / Algorithm** | Plugin uses a specific algorithm worth documenting (filter quality, threshold) |

---

## Style Rules

- Use backticks for all IDs, field names, filenames, and code values: `` `book_id` ``, `` `0001.5` ``, `` `WEBP` ``
- Bold for UI label references: **Action ID**, **Plugin class**
- Prefer plain numbered lists over prose paragraphs in "What It Does"
- Do not document internal implementation details (class internals, helper function names) unless they affect observable behaviour
- Keep descriptions factual — say what the plugin does, not what it "tries to" do
