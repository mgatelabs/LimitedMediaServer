# Sync Content

**Action ID:** `action.sync.folders`
**Plugin class:** `SyncVideos`
**Type:** Series action
**Feature flag:** Admin

## Description

Syncs video series content to a remote server over SSH/SFTP. Compares local files (both primary and archive storage) against what already exists on the remote and uploads only missing files.

## Arguments

Supplied via server command-line flags at startup (not interactive UI arguments):

| Flag | Description |
|---|---|
| `-ssh_username` | SSH username |
| `-ssh_password` | SSH password |
| `-ssh_host` | Remote hostname or IP |
| `-ssh_port` | SSH port (default `22`) |
| `-ssh_path` | Destination path on the remote server |

## What It Does

1. Queries all video series in the library.
2. For each series, creates a `CreateSyncFolderRequest` task.
3. Each task:
   - Connects to the remote via SSH/SFTP.
   - Lists all files already present at the remote path for this series.
   - Iterates local files from both primary and archive storage.
   - Uploads any file not already present on the remote.
   - Logs a count of uploaded vs skipped files per series.
   - Updates `progress` per file and respects `is_cancelled`.
