# Multi-Tenant Auth & Admin Role

**Date**: 2026-06-14
**Status**: draft

## Overview

Add user registration/login with JWT auth, multi-tenant debate isolation (user = tenant), and a system admin role that can view all tenants and their debates.

## Current State

- No auth system — all debates are global, no user concept
- No admin role — all endpoints are open
- Frontend has no login/register UI

## Decisions

| Decision | Choice |
|---|---|
| Auth method | Username + password, JWT bearer token |
| Tenant model | User = tenant (1 user has 1 debate space) |
| Admin config | `ADMIN_USERS` env var (comma-separated usernames) |
| Registration | Username + password only |
| Admin UI | Separate `/admin` page |

## Design

### Database Changes (`db.py`)

**New table `users`:**

```sql
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    username     TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin     INTEGER DEFAULT 0,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**`debates` table — add `user_id` FK:**

```sql
ALTER TABLE debates ADD COLUMN user_id TEXT REFERENCES users(id);
```

Existing rows get `user_id = NULL` (legacy data, admin-visible).

**New DB functions:**

- `create_user(username, password_hash, is_admin) -> str` — returns user id
- `get_user_by_username(username) -> dict | None`
- `get_user_by_id(user_id) -> dict | None`
- `get_all_users() -> list[dict]` — admin only
- `get_debates_by_user(user_id) -> list[dict]`

**Modified DB functions:**

- `create_debate()` — accepts `user_id` param
- `get_active_debate()` — accepts optional `user_id` filter
- `get_all_debates()` — accepts optional `user_id` filter

### Auth Module (new `auth.py`)

```python
# Dependencies
- bcrypt  # password hashing (direct, better maintained than passlib)
- PyJWT  # JWT encode/decode (lightweight, well-maintained)
- pydantic  # already present

# Functions
hash_password(password: str) -> str
verify_password(password: str, hash: str) -> bool
create_access_token(user_id: str, username: str, is_admin: bool) -> str
decode_access_token(token: str) -> dict

# FastAPI dependency
async def get_current_user(request: Request) -> dict  # extracts JWT from Authorization header
async def get_admin_user(current_user = Depends(get_current_user)) -> dict  # asserts is_admin
```

JWT config via env vars:
- `JWT_SECRET_KEY` (default: auto-generated random, warns on startup)
- `JWT_EXPIRE_HOURS` (default: 24)

### API Changes (`main.py`)

**New auth routes (public):**

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Create user, return JWT |
| POST | `/api/auth/login` | Verify credentials, return JWT |
| GET | `/api/auth/me` | Return current user info (protected) |

**Modified debate routes (protected with `Depends(get_current_user)`):**

All `/api/debate/*` routes now require JWT. Debates are filtered by `user_id`.

| Route | Change |
|---|---|
| `GET /api/debates` | Filter by current user's `user_id` |
| `GET /api/debate/active` | Filter by current user's `user_id` |
| `POST /api/debate/start` | Set `user_id` from current user |
| `GET /api/debate/{id}/stream` | Verify ownership or admin |
| `POST /api/debate/{id}/pause` | Verify ownership or admin |
| `POST /api/debate/{id}/resume` | Verify ownership or admin |
| `GET /api/debate/{id}` | Verify ownership or admin |

**New admin routes (protected with `Depends(get_admin_user)`):**

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/users` | List all users |
| GET | `/api/admin/users/{user_id}/debates` | List debates for a specific user |
| GET | `/api/admin/debates` | List all debates across all users |

**Public routes (no auth):**

| Method | Path | Description |
|---|---|---|
| GET | `/api/skills` | Still public |
| GET | `/api/health` | New health check |

### Models (`models.py`)

**New request/response models:**

```python
class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=4, max_length=128)

class LoginRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    token: str
    user: UserInfo

class UserInfo(BaseModel):
    id: str
    username: str
    is_admin: bool

class AdminUserItem(BaseModel):
    id: str
    username: str
    is_admin: bool
    debate_count: int
    created_at: str
```

### Frontend Changes

**`index.html`:**
- Add login/register form (tabs: 登录 / 注册), hidden when authenticated
- Add user info bar (username + logout button), hidden when not authenticated
- Main debate UI hidden until authenticated

**New `admin.html`:**
- User list table (username, debate count, created date)
- Click user row → expand to show their debates
- Back link to main page

**`app.js`:**
- `checkAuth()` — check localStorage for token, validate with `/api/auth/me`
- `login()` / `register()` — POST to auth endpoints, store JWT
- `logout()` — clear localStorage, reset UI
- All fetch calls add `Authorization: Bearer <token>` header
- Admin check: if `user.is_admin`, show "管理面板" link

### Security

- Password hashed with bcrypt
- JWT with HS256, configurable expiry
- Admin endpoints double-check `is_admin` claim
- CORS not needed (same-origin SPA)
- Token stored in localStorage (acceptable for internal tool)

### Dependencies Added

```
bcrypt>=4.0
PyJWT>=2.8
```

## Verification

1. `python -c "from auth import hash_password, verify_password; assert verify_password('test', hash_password('test'))"`
2. `pytest test_auth.py -v` — new test file covering register, login, admin guard
3. `pytest test_main.py -v` — update existing tests to pass auth
4. `pytest test_db.py -v` — update to cover new user functions
5. Manual: start server, register user, create debate, logout, re-login, verify debates are isolated
6. Manual: set `ADMIN_USERS=admin`, register admin user, verify `/admin` page shows all tenants
