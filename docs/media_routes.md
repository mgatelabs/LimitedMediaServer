# media_routes.py - Media File Management API

This module provides a RESTful API for managing media files (images, videos, etc.) organized in a folder hierarchy. Features include:
- List and browse folders/files
- Date-based file queries (`list/by-date`)
- Folder CRUD operations
- File CRUD operations and management
- File uploads
- Image conversion/preview generation
- Per-folder generic key/value pairs (`keys/*`)

## Blueprint
```python
media_blueprint = Blueprint('media', __name__)
```

---

## Media Listing Routes

### `GET /list` (POST)
Retrieves a list of folders, files, and information from the Media service.

**Authentication:** Requires `VIEW_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `folder_id` | string | No | '' | Folder to list (empty = root) |
| `offset` | int | No | 0 | Pagination offset |
| `limit` | int | No | 20 | Max items per page |
| `rating` | int | No | 0 | Max content rating to include |
| `sort` | string | No | 'AZ' | Sort order: 'AZ', 'ZA' name; 'DA', 'DD' date; 'FA', 'FD' filesize |
| `filter_text` | string | No | '' | Keyword search |
| `required_tags` | string | No | 0 | Bitmask of required tags |
| `hidden_tags` | string | No | 0 | Bitmask of hidden tags |

**Response (with folder_id):**
```json
{
  "success": "",
  "data": {
    "info": {"id": "folder_id", "name": "Folder Name", "rating": 0, "created": "YYYYMMDD", ...},
    "paging": {"total": 100, "offset": 0},
    "folders": [{"id": "...", "name": "...", "rating": 0}],
    "files": [{"id": "...", "name": "file.ext", "mime_type": "..."}]
  }
}
```

**Response (root):**
Same as above, but `info` shows root metadata, `folders` lists top-level folders.

---

### `GET /list/by-date` (POST)
Retrieves a list of files created within a date range from the Media service.

**Authentication:** Requires `VIEW_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | Yes | - | Start date in YYYYMMDD format |
| `end_date` | string | Yes | - | End date in YYYYMMDD format |
| `offset` | int | No | 0 | Pagination offset |
| `limit` | int | No | 20 | Max items per page |
| `rating` | int | No | 0 | Max content rating to include |
| `sort` | string | No | 'DA' | Sort order: 'AZ', 'ZA', 'DA', 'DD', 'FA', 'FD |

**Response:**
```json
{
  "success": "",
  "data": {
    "info": {},
    "paging": {"total": 50, "offset": 0},
    "folders": [],
    "files": [{"id": "...", "name": "file.ext", "mime_type": "...", "folder_name": "...", "rating": 0}]
  }
}
```

---

## Folder Management Routes

### `GET /folder` (POST)
Gets the details of a folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder ID to retrieve |

---

### `GET /folder/post` (POST)
Creates a new media folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `parent_id` | string | No | Parent folder ID (empty = root) |
| `name` | string | Yes | Folder name |
| `rating` | int | Yes | Content rating |
| `fast_tags` | string | No | Fast tag bitmask |
| `info_url` | string | No | Info URL |
| `active` | boolean | No | Whether folder is active |
| `group_id` | int | No | Security group ID |
| `tags` | string | No | Comma-separated tags |

**Validation:**
- Rating must be in `COMMON_MEDIA_RATINGS`
- Sub-folders inherit group security from parent
- Rating cannot be lower than parent folder's rating

---

### `GET /folder/put` (POST)
Updates an existing media folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:** Same as `/folder/post`. Also requires:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder ID to update |

---

### `GET /folder/delete` (POST)
Deletes a media folder. Must be empty (no sub-folders or files).

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder ID to delete |

---

### `GET /folder/move` (POST)
Moves a folder to a different parent or to root.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_id` | string | Yes | Source folder ID |
| `folder_id` | string | No | Target folder ID (empty = root) |

---

### `GET /folder/activate` (POST)
Activates a folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder ID to activate |

---

### `GET /folder/inactivate` (POST)
Inactivates a folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder ID to inactivate |

---

## File Management Routes

### `GET /file` (POST)
Gets the details of a file.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | string | Yes | File ID to retrieve |

---

### `GET /file/put` (POST)
Updates a file's name or MIME type.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | string | Yes | File ID to update |
| `filename` | string | Yes | New filename |
| `mime_type` | string | Yes | New MIME type (must be valid) |

---

### `GET /file/progress` (POST)
Updates the progress for a watched file.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | string | Yes | File ID |
| `progress` | float | Yes | Progress value (0.0 - 1.0) |

---

### `GET /file/migrate` (POST)
Migrates a file between primary and archive storage folders.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | string | Yes | File ID to migrate |
| `force_archive` | boolean | No | Force archive state (defaults to toggle) |

---

### `GET /file/delete` (POST)
Deletes a file from the database and filesystem.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | string | Yes | File ID to delete |

---

### `GET /file/move` (POST)
Moves a file to a different folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_id` | string | Yes | File ID to move |
| `folder_id` | string | Yes | Target folder ID |

---

## Upload Routes

### `GET /folder/upload/file` (POST)
Uploads a file to a folder. Stores the file as `{file_uuid}.dat`.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Target folder ID |
| `file` | file | Yes | File to upload (form-data) |

---

### `GET /folder/upload/note` (POST)
Uploads a note as a text file.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Target folder ID |
| `note_text` | string | Yes | Note content |

---

## Folder Key Value Routes

Manage generic key/value pairs stored per folder. Each row is unique per `folder_id` + `key` + `purpose`. The key is locked once created and cannot be modified; only the value and purpose can be updated.

**Access:** All routes require the `MANAGE_MEDIA` feature flag plus rating and group access to the target folder (same checks as the other folder management routes).

---

### `GET /keys/list` (POST)
Retrieves all key/value rows stored for a folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder whose key values to list |

**Response:**
```json
{
  "success": "",
  "data": {
    "items": [{"id": 1, "folder": "folder_id", "key": "my_key", "value": "my_value", "purpose": 1}]
  }
}
```

---

### `GET /keys/get` (POST)
Retrieves a single key/value row for a folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder owning the row |
| `row_id` | int | Yes | Key value row ID to retrieve |

**Response:**
```json
{
  "success": "",
  "data": {
    "info": {"id": 1, "folder": "folder_id", "key": "my_key", "value": "my_value", "purpose": 1}
  }
}
```

---

### `GET /keys/insert` (POST)
Adds a key/value row for a folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder owning the new row |
| `key` | string | Yes | Key (must be unique per folder + key + purpose) |
| `value` | string | No | Value (stored as NULL when blank) |
| `purpose` | int | No | Purpose (defaults to `MEDIA_FOLDER_KEY_PURPOSE_DEFAULT` = 1) |

**Response:**
```json
{
  "success": "Key added successfully",
  "data": {"id": 1}
}
```

**Failure:** Returns a failure response if a row for the same folder/key/purpose already exists.

---

### `GET /keys/update` (POST)
Updates an existing key/value row for a folder. The key is locked and cannot be modified.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder owning the row |
| `row_id` | int | Yes | Key value row ID to update |
| `value` | string | No | New value (stored as NULL when blank) |
| `purpose` | int | No | New purpose (unchanged when omitted) |

**Response:**
```json
{
  "success": "Key updated successfully",
  "data": {}
}
```

---

### `GET /keys/delete` (POST)
Removes a key/value row for a folder.

**Authentication:** Requires `MANAGE_MEDIA` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string | Yes | Folder owning the row |
| `row_id` | int | Yes | Key value row ID to delete |

**Response:**
```json
{
  "success": "Key removed successfully",
  "data": {}
}
```
