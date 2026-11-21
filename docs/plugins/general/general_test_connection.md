# Test URL

**Action ID:** `action.test.url`
**Plugin class:** `UpdateHeaders`
**Type:** General
**Feature flag:** Admin

## Description

Tests connectivity to a URL and validates its content type. Useful for verifying that a source is reachable and returning the expected data before configuring a download job.

## Arguments

| Name | ID | Type | Required | Default | Description |
|---|---|---|---|---|---|
| URL | `url` | URL | Yes | — | The URL to test |
| Referer | `referer` | string | No | — | Optional `Referer` header to include in the request |
| Content Type | `content_type` | select | No | `html` | `html` = validate as a web page; `image` = validate as an image file |

## What It Does

1. Downloads the URL using the internal curl implementation, including the referer header if provided.
2. If `content_type=html`: checks that the response contains valid HTML markup.
3. If `content_type=image`: attempts to open the response body as an image.
4. Logs the response size and a success/failure verdict.
