# Update Header

**Action ID:** `action.book.set.header`
**Plugin class:** `UpdateHeaders`
**Type:** General (all books)
**Feature flag:** `MANAGE_VOLUME`

## Description

Parses a pasted cURL command (or raw HTTP headers) and writes the extracted headers to the server's `headers.json` file. This is used to supply authenticated session headers so download plugins can access content that requires a logged-in browser session.

## Arguments

| Name | ID | Type | Required | Description |
|---|---|---|---|---|
| Headers | `headers` | long string | Yes | cURL-format headers copied from browser DevTools |

## What It Does

1. Receives the raw header string (typically copied from a browser's "Copy as cURL" DevTools option).
2. Calls `parse_curl_headers()` to extract key-value header pairs.
3. Writes the parsed headers to `headers.json` in the configured volume folder.
4. Subsequent download tasks load `headers.json` automatically to authenticate their HTTP requests.
