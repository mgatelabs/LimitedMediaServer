# De-Freeze

Two plugins live in this file covering single-file and multi-file frozen video detection.

---

## De-Freeze (File)

**Action ID:** `action.defreeze.file`
**Plugin class:** `DeFreezeForFilePlugin`
**Type:** Media file
**Feature flag:** File access

### Description

Detects and removes frozen video frames and silent audio segments from a single video file. A "freeze" is a section where the video is stuck on a single frame for an abnormally long duration, often combined with a silent or near-silent audio track.

### Arguments

| Name | ID | Type | Default | Description |
|---|---|---|---|---|
| Freeze dB | `freeze_db` | string | — | Audio silence threshold in dB (e.g. `-60`) |
| Silence Noise | `silence_noise` | string | — | Noise floor level used when detecting silence |
| Min Duration | `min_duration` | string | — | Minimum duration (seconds) to qualify as a freeze segment |
| Force Encode | `force_encode` | select | `f` | `t` = always re-encode even if no freezes found |

### What It Does

1. Probes the file for frozen video segments and silent audio using ffmpeg filters.
2. Builds a cut list of frozen/silent time ranges.
3. Re-encodes the file removing those segments.
4. Replaces the original file with the cleaned version.

---

## De-Freeze (Files)

**Action ID:** `action.defreeze.files`
**Plugin class:** `DeFreezeForFilesPlugin`
**Type:** Media files (multiple)
**Feature flag:** File access

### Description

Same as De-Freeze (File) but accepts a comma-separated list of file IDs.

### Arguments

Same as De-Freeze (File), plus:

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| File IDs | `file_ids` | string | Yes | Comma-separated list of file IDs to process |
