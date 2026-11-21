# Process Routes

Base path: `/process`

Manages the background task queue — submitting plugin jobs, monitoring progress, controlling workers, and downloading logs.

---

## Authentication & Feature Flags

| Flag | Description |
|---|---|
| `VIEW_PROCESSES` | Read task status and download logs |
| `MANAGE_PROCESSES` | Cancel, promote, clean, and change log levels |
| `MANAGE_APP` | Stop or restart the server process |

---

## Task Lifecycle

```
Plugin submitted via /add/plugin
        ↓
Task queued in TaskManager (status: waiting)
        ↓
Worker thread calls get_task_queue():
  - Top task weight-blocked → queue is held until capacity frees (barrier semantics)
  - Top task lock-blocked   → skip it, try next task so workers stay busy
  - Task fits and lock free → acquired atomically, task dispatched
        ↓
Task calls run(db_session), updates progress/percent, writes log entries
        ↓
Task finishes (finished=true, worked/failure/warning flags set), lock released
        ↓
Task stays in finished list until /clean or /sweep removes it
```

---

## Endpoints

### Submit a Plugin Task

**`POST /process/add/plugin`**

Submits a plugin action to the task queue. The request body must contain a single `bundle` field with a JSON string.

**Form fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `bundle` | JSON string | Yes | Serialised `{ "id": "<action_id>", "args": { ... } }` |

**Bundle `args` reserved keys:**

| Key | Type | Default | Description |
|---|---|---|---|
| `_logging_level` | int | `20` | Log verbosity: `0`=TRACE, `10`=DEBUG, `20`=INFO, `30`=WARN, `40`=ERROR, `50`=CRIT |
| `_duplicate_checking` | `"y"` / `"n"` | `"y"` | Skip submission if an identical task is already queued |

All other keys in `args` are plugin-specific — see `docs/plugins/` for each plugin's argument list.

**Success response:**
```json
{ "task_id": 42 }
```
When the plugin returns multiple tasks (e.g. Download All Books), `task_id` is absent and the message reports how many were added vs skipped.

**Errors:** `400` invalid JSON · `401` insufficient feature flags · plugin `process_action_args` validation failures.

---

### Get All Task Status

**`POST /process/status/all`**  
**`POST /process/status/all/with/<extra_method_call>`**

Returns a paginated list of all tasks in the queue.

**`extra_method_call` values:**

| Value | Behaviour |
|---|---|
| *(omitted)* or `NONE` | Return all tasks |
| `ACTIVE` | Return only tasks that are currently running (not finished, not waiting) |
| `HARD` | Remove all finished tasks, then return remaining *(requires `MANAGE_PROCESSES`)* |
| `SOFT` | Remove finished tasks that did no work, then return remaining *(requires `MANAGE_PROCESSES`)* |

**Form fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `page` | int | `0` | Zero-based page index |
| `page_size` | int | `20` | Results per page (max 150) |

**Success response:**
```json
{
  "page": 0,
  "pages": 3,
  "total": 52,
  "weight": 4,
  "workers": [
    {
      "index": 1,
      "name": "Kevin",
      "status": "running",
      "job": 42,
      "job_name": "BookDeduplicate",
      "job_description": "Scan duplicates: my-book",
      "last_seen": 1706000000.0
    }
  ],
  "tasks": [
    {
      "id": 42,
      "name": "BookDeduplicate",
      "description": "Scan duplicates: my-book",
      "progress": 75.0,
      "percent": 100.0,
      "finished": false,
      "waiting": false,
      "failure": false,
      "warning": false,
      "worked": false,
      "logging": 20,
      "log": [ /* last 2 entries only */ ],
      "delay_duration": 1.2,
      "running_duration": 30.5,
      "total_duration": 31.7,
      "init_timestamp": "2024-01-15 14:30:00",
      "start_timestamp": "2024-01-15 14:30:01",
      "end_timestamp": null,
      "book_id": "my-book",
      "folder_id": null,
      "folder_name": null,
      "folder_img": null,
      "priority": 5,
      "weight": 1
    }
  ]
}
```

> The `log` field in the list view contains only the **last 2 entries**. Use `/status/<task_id>` for the full log.

**Worker object shape:**

| Field | Description |
|---|---|
| `index` | Sequential worker number assigned at spawn |
| `name` | Human-readable name assigned at spawn (e.g. `"Kevin"`, `"Ringo"`) — chosen from a pool of 32 names, suffixed with a number if the pool is exhausted |
| `status` | `"idle"` · `"running"` · `"dead"` |
| `job` | Task ID currently being executed, or `0` if idle |
| `job_name` | Name of the task being executed, or `null` if idle |
| `job_description` | Description of the task being executed, or `null` if idle |
| `last_seen` | Unix timestamp of the last time the worker updated its state — used to detect stale/dead workers |
| `uptime` | Seconds since the worker thread was spawned |

---

### Get Single Task Status

**`POST /process/status/<task_id>`**

Returns full details for one task, with optional log pagination.

**URL parameter:** `task_id` — integer task ID returned by `/add/plugin`.

**Form fields (all optional):**

| Field | Type | Default | Description |
|---|---|---|---|
| `log_page_size` | int | `0` | Entries per page; `0` = return all entries |
| `log_page` | int | `0` | Zero-based page index into the log (clamped to valid range) |

**Success response:**
```json
{
  "task": {
    "id": 42,
    "name": "BookDeduplicate",
    "description": "Scan duplicates: my-book",
    "progress": 100.0,
    "percent": 100.0,
    "finished": true,
    "waiting": false,
    "failure": false,
    "warning": false,
    "worked": true,
    "logging": 20,
    "log": [ { "s": 20, "time": "2024-01-15 14:30:45", "text": "..." } ],
    "log_total": 150,
    "log_pages": 15,
    "log_page": 0,
    "log_page_size": 10,
    "delay_duration": 1.2,
    "running_duration": 120.3,
    "total_duration": 121.5,
    "init_timestamp": "2024-01-15 14:30:00",
    "start_timestamp": "2024-01-15 14:30:01",
    "end_timestamp": "2024-01-15 14:32:01",
    "book_id": "my-book",
    "folder_id": null,
    "priority": 5,
    "weight": 1
  }
}
```

**Log entry shape:**

| Field | Description |
|---|---|
| `s` | Severity: `0`=TRACE, `10`=DEBUG, `20`=INFO, `30`=WARN, `40`=ERROR, `50`=CRIT, `100`=ALWAYS |
| `time` | Timestamp string (`YYYY-MM-DD HH:MM:SS`) |
| `text` | Log message |

**Errors:** `404` task not found.

---

### Download Task Log

**`POST /process/log/download/<task_id>`**

Downloads the complete task log as a file attachment.

**URL parameter:** `task_id` — integer task ID.

**Form fields:**

| Field | Type | Default | Options | Description |
|---|---|---|---|---|
| `format` | string | `md` | `md`, `json` | Download format |

**Filename format:** `<TaskName>_YYYYMMDD_HHMMSS.md` or `.json`  
Non-alphanumeric characters in the task name are replaced with underscores.

**Markdown format** — a table with `Time`, `Level`, and `Message` columns:
```markdown
# BookDeduplicate
**Description:** Scan duplicates: my-book
**Task ID:** 42

| Time | Level | Message |
|---|---|---|
| 2024-01-15 14:30:01 | INFO | Executing Task |
| 2024-01-15 14:30:01 | INFO | Executed by admin (1) |
...
```

**JSON format** — full task metadata with the raw log array:
```json
{
  "id": 42,
  "name": "BookDeduplicate",
  "description": "Scan duplicates: my-book",
  "log": [
    { "s": 20, "time": "2024-01-15 14:30:01", "text": "Executing Task" }
  ]
}
```

**Errors:** `404` task not found.

---

### Cancel a Task

**`POST /process/cancel/<task_id>`**  
*Requires `MANAGE_PROCESSES`*

Signals a running task to stop at its next cancellation check point. Tasks check `is_cancelled` between iterations and stop cleanly — they are not killed immediately.

**Errors:** `404` task not found.

---

### Change Task Log Level

**`POST /process/logging/<task_id>`**  
*Requires `MANAGE_PROCESSES`*

Changes the minimum severity level for log entries on a running or queued task. Entries below the threshold are silently discarded.

**Form fields:**

| Field | Type | Required | Values | Description |
|---|---|---|---|---|
| `level` | int | Yes | `0`, `10`, `20`, `30`, `40`, `50` | New minimum log level |

**Errors:** `400` missing/invalid level · `404` task not found.

---

### Promote a Task

**`POST /process/promote/<task_id>`**  
*Requires `MANAGE_PROCESSES`*

Moves a waiting task to the front of the queue (priority 0).

**Errors:** `404` task not found.

---

### Purge a Single Task

**`DELETE /process/purge/<task_id>`**  
*Requires `MANAGE_PROCESSES`*

Removes one specific finished task from the list by ID. Unlike `/clean` and `/sweep` which operate
in bulk, this targets a single entry so everything else is left untouched.

Only tasks in the **finished** or **pending** list can be purged. Tasks that are actively running
must be cancelled first via `POST /cancel/<task_id>`, after which they will move to the finished
list and become purgeable.

**Success response:**
```json
{ "result": "success", "messages": [{ "id": "operation.complete" }] }
```

**Errors:** `404` if the task ID does not exist or the task is still active.

---

### Clean Finished Tasks

**`POST /process/clean`**  
*Requires `MANAGE_PROCESSES`*

Removes all finished tasks from the queue regardless of outcome.

---

### Sweep No-Work Tasks

**`POST /process/sweep`**  
*Requires `MANAGE_PROCESSES`*

Removes finished tasks that completed without doing any work (`worked=false`). Tasks that failed, warned, or produced results are kept.

---

### Add a Worker Thread

**`POST /process/add/worker`**  
*Requires `MANAGE_PROCESSES`*

Spawns an additional worker thread to increase parallel task throughput. The new worker is assigned a name from the pool of 32 names (e.g. `"Alan"`, `"Ringo"`); if all names are in use it appends a generation number (`"Alan 2"`). Workers are not persistent — they are lost on server restart. The default worker count is set by `MAX_WORKERS` in constants.

Workers poll for tasks with an adaptive idle wait starting at 1 second, increasing by 1 second per empty cycle up to a cap of 10 seconds. The wait resets to 1 second as soon as a task is picked up.

---

### Stop Server

**`POST /process/stop`**  
*Requires `MANAGE_APP`*

Immediately terminates the server process (exit code 1). The process manager (if any) is responsible for restart behaviour.

---

### Restart Server

**`POST /process/restart`**  
*Requires `MANAGE_APP`*

Immediately exits the server process with code 69, which the launcher script interprets as a restart signal.
