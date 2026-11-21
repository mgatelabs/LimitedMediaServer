# Test

**Action ID:** `action.test`
**Plugin class:** `TestTask`
**Type:** General
**Feature flag:** Admin

## Description

A developer utility task that demonstrates the task system's logging and progress tracking behaviour. Not intended for production use.

## Arguments

None.

## What It Does

Runs a 60-iteration loop where each iteration:
1. Sleeps for 1 second.
2. Calls `update_progress()` with the current percentage.
3. Logs one entry at each of `WARN`, `INFO`, `DEBUG`, and `TRACE` levels.
4. Checks `is_cancelled` and stops early if the task has been cancelled.
