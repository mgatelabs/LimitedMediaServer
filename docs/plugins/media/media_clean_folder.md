# Check Integrity

Two plugins live in this file covering folder-level and library-wide integrity checks.

---

## Check Integrity (Folder)

**Action ID:** `action.integrity.folder`
**Plugin class:** `CheckFolderIntegrityTask`
**Type:** Media folder
**Feature flag:** Folder access

### Description

Validates a single media folder: checks that all referenced files exist on disk, verifies that archive/primary drive assignments are correct, and confirms preview images are properly linked.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Fix Issues | `fix` | select | `n` | `y` = automatically repair detected problems |

### What It Does

1. Checks each file record against disk — flags missing files.
2. Detects mismatches between a file's recorded storage location (primary vs archive) and its actual disk location.
3. Verifies that preview images exist and are linked to the correct file.
4. With `fix=y`: moves misplaced files, relinks orphaned previews, and removes stale records.

---

## Check Integrity (All)

**Action ID:** `action.integrity.all`
**Plugin class:** `CheckAllFolderIntegrityTask`
**Type:** Media library-wide
**Feature flag:** Admin

### Description

Runs the integrity check across the entire media library, including scanning for unreferenced files on disk and orphaned preview images.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Fix Issues | `fix` | select | `n` | `y` = automatically repair detected problems |
| Check files | `chkfiles` | select | `n` | `y` = scan disk for files not referenced in the database |
| Restore Folder | `restore_folder` | select | `n` | `y` = attempt to restore missing folder records from disk |

### What It Does

Same as the folder variant but iterates every folder in the library. Additionally scans both primary and archive storage roots for unreferenced files and orphaned preview images when `chkfiles=y`.
