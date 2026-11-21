# Generate Previews

Four plugins live in this file covering folder, library-wide, single-file, and multi-file preview generation.

---

## Generate Previews (Folder)

**Action ID:** `action.generate.previews.folder`
**Plugin class:** `MakePreviewsForFolderPlugin`
**Type:** Media folder
**Feature flag:** Folder access

### Description

Generates thumbnail preview images for all video files in a folder.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Force | `force` | select | `false` | `true` = regenerate previews that already exist |
| Place | `place` | select | `10` | Percentage into the video to capture the thumbnail (10–90%) |

### What It Does

Iterates every video file in the folder. For each file without a preview (or all files if `force=true`), seeks to the specified position and captures a frame as a WebP thumbnail.

---

## Generate Previews (All)

**Action ID:** `action.generate.previews.all`
**Plugin class:** `MakePreviewsForAllPlugin`
**Type:** Media library-wide
**Feature flag:** Admin

### Description

Generates or regenerates preview thumbnails for every video file across the entire media library.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Place | `place` | select | `10` | Percentage into the video to capture the thumbnail (10–90%) |

---

## Generate Previews (File)

**Action ID:** `action.generate.previews.file`
**Plugin class:** `MakePreviewForFilePlugin`
**Type:** Media file
**Feature flag:** File access

### Description

Generates or regenerates the preview thumbnail for a single file.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Place | `place` | select | `10` | Percentage into the video to capture the thumbnail (10–90%) |

---

## Generate Previews (Files)

**Action ID:** `action.generate.previews.files`
**Plugin class:** `MakePreviewsForFilesPlugin`
**Type:** Media files (multiple)
**Feature flag:** File access

### Description

Generates or regenerates preview thumbnails for a comma-separated list of files.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Place | `place` | select | `10` | Percentage into the video to capture the thumbnail (10–90%) |
