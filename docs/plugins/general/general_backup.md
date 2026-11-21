# Backup

**Action ID:** `action.backup`
**Plugin class:** `BackupPlugin`
**Type:** General
**Feature flag:** Admin
**Requires config:** `PLUGIN.BACKUP.PATH`

## Description

Creates a timestamped backup of the server's database and configuration to the configured backup path.

## Arguments

None.

## What It Does

1. Reads the backup destination from `PLUGIN.BACKUP.PATH` (must be a writable folder).
2. Creates a timestamped subfolder (e.g. `backup_20240115_143022`).
3. Calls `perform_backup()` to copy the database file and any configuration files into the subfolder.
