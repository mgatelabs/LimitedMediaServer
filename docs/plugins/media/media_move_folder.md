# Move Folder

**Action ID:** `action.move.folder`
**Plugin class:** `MoveFolderTask`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Moves a media folder to a new parent folder within the library, applying content rating and permission checks before the move.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Destination | `dest_id` | select | Yes | ID of the destination parent folder |

## What It Does

1. Validates that the current user has access to both the source and destination folders.
2. Checks that content ratings are compatible.
3. Moves the folder record to the new parent in the database.
4. Physically moves files on disk to the new path.
5. Updates all file path references in the database.
