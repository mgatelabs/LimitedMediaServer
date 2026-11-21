# VTT to SRT

Two plugins live in this file covering single-file and multi-file subtitle conversion.

---

## VTT to SRT (File)

**Action ID:** `action.file.vrt2str`
**Plugin class:** `Vtt2SrtForFilePlugin`
**Type:** Media file
**Feature flag:** File access

### Description

Converts a WebVTT (`.vtt`) subtitle file to SubRip (`.srt`) format, optionally adjusting all timestamps by an offset.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Offset | `offset` | string | `0` | Timestamp offset in milliseconds to apply to all cue times |

### What It Does

1. Reads the VTT file.
2. Parses all cue timestamps and text.
3. Applies the millisecond offset to every timestamp.
4. Writes the output as a `.srt` file alongside the original.

---

## VTT to SRT (Files)

**Action ID:** `action.files.vrt2str`
**Plugin class:** `Vtt2SrtForFilesPlugin`
**Type:** Media files (multiple)
**Feature flag:** File access

### Description

Same as VTT to SRT (File) but processes a comma-separated list of file IDs.

### Arguments

Same as VTT to SRT (File).
