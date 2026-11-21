# Check Space

**Action ID:** `action.disk.check`
**Plugin class:** `CheckDiskStatusPlugin`
**Type:** General
**Feature flag:** Admin

## Description

Reports disk usage statistics for all system partitions and detailed size breakdowns for each configured storage path (primary, archive, and book storage).

## Arguments

None.

## What It Does

1. Calls `psutil.disk_partitions()` and logs usage (total, used, free, percent) for every mounted partition.
2. Calculates the total size of the primary media storage folder and the archive folder.
3. Calculates the total size of the book storage folder and lists the **top 25 largest sub-folders** within it.
4. All results are logged as `ALWAYS`-level entries, visible regardless of the task's logging level setting.
