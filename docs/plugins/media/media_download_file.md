# Save File from Web

**Action ID:** `action.download.file`
**Plugin class:** `DownloadFilePlugin`
**Type:** Media folder
**Feature flag:** Folder access

## Description

Downloads a single file from a URL and imports it into a media folder.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| URL | `url` | URL | Yes | — | Direct download URL |
| Filename | `filename` | string | Yes | — | Filename to save the file as |
| Location | `dest` | select | No | `primary` | `primary` or `archive` |
| Origin | `origin` | string | No | — | Referer/origin URL to include in request headers |
| Method | `meth` | select | No | `system` | `system` = system curl; `gcurl` = internal curl implementation |

## What It Does

1. Validates the URL.
2. Downloads the file using the selected method (system curl or internal curl), including the origin as a referer header if provided.
3. Saves the file with the given filename into the target folder at the chosen storage location.
4. Creates a database record and generates a preview thumbnail.
