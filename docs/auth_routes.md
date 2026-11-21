# auth_routes.go - Authentication API

This module provides authentication endpoints including:
- Login with username/password or token/PIN
- Hard session (PIN-based) authentication setup
- JWT token renewal

## Blueprint
```python
auth_blueprint = Blueprint('auth', __name__)
```

---

## Internal Functions

### `generate_auth_result(user: User)`
Generates a JWT token and sets it as an HTTP-only cookie.

**Creates:**
- JWT payload: `{'uid': user.id, 'username': user.username, 'limits': {...}, 'features': features, 'exp': expiration_time}`
- Cookie: `access_token` with configurable expiration, `httponly=True`, `secure=CONFIG_USE_HTTPS`, `samesite='strict'`

### `attempt_standard_auth(username: str, password: str)`
Standard username/password authentication.

**Returns:** Auth response with JWT token on success, failure response with 401 on invalid credentials.

### `attempt_token_auth(token: str, pin: str)`
Token/PIN-based "hard" authentication. Invalid attempts expire the token.

---

## Routes

### `POST /login`
Handles login requests with username/password or token/PIN pairs.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `username` | string | Conditional | Username (with password) |
| `password` | string | Conditional | Password (with username) |
| `token` | string | Conditional | Hard session token (with pin) |
| `pin` | string | Conditional | PIN for hard session auth (with token) |

**Logic:**
- If `username` and `password` present: uses standard auth
- If `token` and `pin` present: uses hard session auth

---

### `POST /hard`
Generates a new hard session (PIN-based) token for added security.

**Authentication:** Requires `HARD_SESSIONS` feature flag.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pin` | string | Yes | PIN to set |
| `pin2` | string | Yes | PIN confirmation (must match) |

**Response:**
```json
{
  "success": "Token Generated",
  "data": {"token": "random_token_string"}
}
```

---

### `POST /renew`
Renews the user's JWT token and cookie.

**Authentication:** Requires user authentication.

**Response:**
```json
{
  "success": "Operation complete",
  "data": {"token": "new_jwt_token"}
}
```
