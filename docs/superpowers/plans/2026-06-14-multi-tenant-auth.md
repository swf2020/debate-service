# Multi-Tenant Auth & Admin Role — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JWT-based user registration/login, multi-tenant debate isolation, and admin role with dedicated admin page.

**Architecture:** New `auth.py` module handles bcrypt hashing + PyJWT token lifecycle. FastAPI dependency injection (`get_current_user` / `get_admin_user`) protects routes. `users` table added to SQLite; `debates` gets `user_id` FK. Frontend adds auth forms to `index.html` and a new `admin.html`.

**Tech Stack:** bcrypt>=4.0, PyJWT>=2.8, FastAPI (existing), aiosqlite (existing)

---

### Task 1: Install new dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add bcrypt and PyJWT to requirements.txt**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
crewai>=1.14.0
aiosqlite>=0.20.0
pydantic>=2.0
python-dotenv>=1.0
bcrypt>=4.0
PyJWT>=2.8
```

- [ ] **Step 2: Install dependencies**

Run: `pip install bcrypt>=4.0 PyJWT>=2.8`
Expected: packages install without error

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add bcrypt and PyJWT dependencies"
```

---

### Task 2: DB migration — users table + debates.user_id column

**Files:**
- Modify: `db.py:34-83` (init_db function)

- [ ] **Step 1: Add users table and debates.user_id migration to init_db**

In `db.py`, replace the `init_db` function. Add users table creation and user_id migration logic:

```python
async def init_db() -> None:
    """Create tables and index if they don't exist. Migrate existing DBs."""
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin      INTEGER DEFAULT 0,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS debates (
                id           TEXT PRIMARY KEY,
                topic        TEXT NOT NULL,
                total_rounds INT DEFAULT 2,
                status       TEXT DEFAULT 'running',
                pro_skills   TEXT,
                con_skills   TEXT,
                judge_skill  TEXT,
                winner       TEXT,
                verdict      TEXT,
                user_id      TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at  DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS speeches (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                debate_id  TEXT NOT NULL,
                debater    TEXT NOT NULL,
                phase      TEXT NOT NULL,
                round_num  INT NOT NULL,
                thinking   TEXT,
                content    TEXT NOT NULL,
                seq        INT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (debate_id) REFERENCES debates(id)
            );

            CREATE INDEX IF NOT EXISTS idx_speeches_debate_id
                ON speeches(debate_id);
        """)
        await db.commit()

        # Migrate: add columns if missing (safe for fresh + existing DBs)
        existing = await db.execute("PRAGMA table_info(debates)")
        columns = {row[1] for row in await existing.fetchall()}

        if "current_debater" not in columns:
            await db.execute(
                "ALTER TABLE debates ADD COLUMN current_debater TEXT DEFAULT ''"
            )
        if "debater_status" not in columns:
            await db.execute(
                "ALTER TABLE debates ADD COLUMN debater_status TEXT DEFAULT '{}'"
            )
        if "user_id" not in columns:
            await db.execute(
                "ALTER TABLE debates ADD COLUMN user_id TEXT REFERENCES users(id)"
            )
        await db.commit()
    finally:
        await db.close()
```

- [ ] **Step 2: Run existing DB tests to verify migration doesn't break**

Run: `python test_db.py`
Expected: ALL TESTS PASSED

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "feat: add users table and debates.user_id FK migration"
```

---

### Task 3: DB functions for user CRUD

**Files:**
- Modify: `db.py` (append new functions after `_row_to_debate`)

- [ ] **Step 1: Add user CRUD functions to db.py**

Append after the `_row_to_debate` function (before `# ── Speeches CRUD` section):

```python
# ── Users CRUD ──────────────────────────────────────────────────────────────


async def create_user(username: str, password_hash: str, is_admin: bool = False) -> str:
    """INSERT a new user. Returns the user id."""
    import uuid as _uuid
    user_id = str(_uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            (user_id, username, password_hash, int(is_admin)),
        )
        await db.commit()
        return user_id
    finally:
        await db.close()


async def get_user_by_username(username: str) -> dict | None:
    """SELECT a user by username. Returns None if not found."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def get_user_by_id(user_id: str) -> dict | None:
    """SELECT a user by id. Returns None if not found."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def get_all_users() -> list[dict]:
    """SELECT all users with debate counts. Admin only."""
    db = await get_db()
    try:
        cursor = await db.execute("""
            SELECT u.*, COUNT(d.id) as debate_count
            FROM users u
            LEFT JOIN debates d ON d.user_id = u.id
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
```

- [ ] **Step 2: Add get_debates_by_user function**

Append after `get_all_debates`:

```python
async def get_debates_by_user(user_id: str) -> list[dict]:
    """SELECT all debates for a given user, ordered by created_at DESC."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, topic, status, total_rounds, winner, created_at, "
            "finished_at FROM debates WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
```

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "feat: add user CRUD functions and get_debates_by_user"
```

---

### Task 4: Modify existing DB functions for user_id support

**Files:**
- Modify: `db.py:96-124` (create_debate), `db.py:169-185` (get_active_debate), `db.py:218-230` (get_all_debates)

- [ ] **Step 1: Update create_debate to accept user_id**

Replace the `create_debate` function signature and INSERT:

```python
async def create_debate(
    id: str,
    topic: str,
    total_rounds: int,
    pro_skills: dict,
    con_skills: dict,
    judge_skill: str | None,
    user_id: str,
) -> None:
    """INSERT a new debate row."""
    db = await get_db()
    try:
        default_status = json.dumps({
            "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting",
            "con_1": "waiting", "con_2": "waiting", "con_3": "waiting",
            "judge": "waiting",
        })
        await db.execute(
            """
            INSERT INTO debates (id, topic, total_rounds, pro_skills, con_skills,
                                 judge_skill, user_id, current_debater, debater_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, '', ?)
            """,
            (id, topic, total_rounds, json.dumps(pro_skills),
             json.dumps(con_skills), judge_skill, user_id, default_status),
        )
        await db.commit()
    finally:
        await db.close()
```

- [ ] **Step 2: Update get_active_debate to accept optional user_id filter**

```python
async def get_active_debate(user_id: str | None = None) -> dict | None:
    """Return the most recent debate with status != 'finished'.

    If *user_id* is provided, filters to that user's debates only.
    Returns ``None`` when no active debate exists.
    """
    db = await get_db()
    try:
        if user_id:
            cursor = await db.execute(
                "SELECT * FROM debates WHERE status != 'finished' AND user_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM debates WHERE status != 'finished' "
                "ORDER BY created_at DESC LIMIT 1"
            )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_debate(row)
    finally:
        await db.close()
```

- [ ] **Step 3: Update get_all_debates to accept optional user_id filter**

```python
async def get_all_debates(user_id: str | None = None) -> list[dict]:
    """SELECT all debates, ordered by created_at DESC.

    If *user_id* is provided, filters to that user's debates only.
    """
    db = await get_db()
    try:
        if user_id:
            cursor = await db.execute(
                "SELECT id, topic, status, total_rounds, winner, created_at, "
                "finished_at FROM debates WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
        else:
            cursor = await db.execute(
                "SELECT id, topic, status, total_rounds, winner, created_at, "
                "finished_at FROM debates ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
```

- [ ] **Step 4: Commit**

```bash
git add db.py
git commit -m "feat: add user_id param to create_debate, get_active_debate, get_all_debates"
```

---

### Task 5: Create auth module (auth.py)

**Files:**
- Create: `auth.py`

- [ ] **Step 1: Write auth.py — password hashing, JWT, FastAPI dependencies**

```python
"""
Authentication module: bcrypt password hashing, JWT token management,
and FastAPI dependency injection for current user / admin user.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_hex(32))
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "24"))
JWT_ALGORITHM = "HS256"

if not os.environ.get("JWT_SECRET_KEY"):
    import warnings
    warnings.warn(
        "JWT_SECRET_KEY not set. Using random key — all tokens invalid on restart.",
        RuntimeWarning,
    )


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Returns the hash as a string."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, username: str, is_admin: bool) -> str:
    """Create a JWT access token with user claims."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. Raises on invalid/expired token."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract and validate JWT from Authorization header.

    Returns a dict with keys: user_id, username, is_admin.
    Raises HTTPException(401) on missing/invalid token.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "user_id": payload["sub"],
        "username": payload["username"],
        "is_admin": payload.get("is_admin", False),
    }


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency: require admin role on top of valid auth.

    Returns the same user dict as get_current_user.
    Raises HTTPException(403) if user is not admin.
    """
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

- [ ] **Step 2: Quick verification — hash_password and JWT round-trip**

Run: `python -c "
from auth import hash_password, verify_password, create_access_token, decode_access_token
h = hash_password('test123')
assert verify_password('test123', h)
assert not verify_password('wrong', h)
token = create_access_token('u1', 'alice', True)
payload = decode_access_token(token)
assert payload['sub'] == 'u1'
assert payload['username'] == 'alice'
assert payload['is_admin'] == True
print('OK: auth functions work')
"`
Expected: `OK: auth functions work`

- [ ] **Step 3: Commit**

```bash
git add auth.py
git commit -m "feat: add auth module with bcrypt hashing and JWT dependencies"
```

---

### Task 6: Add auth models to models.py

**Files:**
- Modify: `models.py`

- [ ] **Step 1: Add auth request/response models**

Append to `models.py` after the existing models:

```python
# ── Auth models ──────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Payload for user registration."""
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=4, max_length=128)


class LoginRequest(BaseModel):
    """Payload for user login."""
    username: str
    password: str


class UserInfo(BaseModel):
    """Public user info returned in auth responses."""
    id: str
    username: str
    is_admin: bool


class AuthResponse(BaseModel):
    """Response for register/login endpoints."""
    token: str
    user: UserInfo


class AdminUserItem(BaseModel):
    """User row in admin panel list."""
    id: str
    username: str
    is_admin: bool
    debate_count: int
    created_at: str
```

- [ ] **Step 2: Verify models serialize correctly**

Run: `python -c "
from models import RegisterRequest, LoginRequest, AuthResponse, UserInfo, AdminUserItem
r = RegisterRequest(username='alice', password='pass1234')
assert r.username == 'alice'
u = UserInfo(id='1', username='alice', is_admin=False)
a = AuthResponse(token='t', user=u)
print(a.model_dump_json())
m = AdminUserItem(id='1', username='alice', is_admin=False, debate_count=5, created_at='2026-01-01')
print(m.model_dump_json())
print('OK')
"`
Expected: JSON output, no errors

- [ ] **Step 3: Commit**

```bash
git add models.py
git commit -m "feat: add auth request/response models (RegisterRequest, LoginRequest, AuthResponse, UserInfo, AdminUserItem)"
```

---

### Task 7: Add auth API routes to main.py

**Files:**
- Modify: `main.py` (imports and new routes)

- [ ] **Step 1: Update imports in main.py**

Add to the imports section after existing imports:

```python
from auth import get_admin_user, get_current_user, hash_password, verify_password, create_access_token
from db import (
    create_debate,
    create_user,
    get_active_debate,
    get_all_debates,
    get_all_users,
    get_debate,
    get_debates_by_user,
    get_speeches,
    get_user_by_username,
    init_db,
    update_debate_status,
)
from models import (
    AdminUserItem,
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    SSEError,
    SSEHistoryReplay,
    SSEPaused,
    SSEResumed,
    StartDebateRequest,
    StartDebateResponse,
    UserInfo,
)
```

- [ ] **Step 2: Add health endpoint**

Add after the skills section:

```python
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    """Health check endpoint (public)."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@app.post("/api/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    """Register a new user. Returns JWT token."""
    existing = await get_user_by_username(req.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    is_admin = req.username in os.environ.get("ADMIN_USERS", "").split(",")
    hashed = hash_password(req.password)
    user_id = await create_user(req.username, hashed, is_admin)

    token = create_access_token(user_id, req.username, is_admin)
    return AuthResponse(
        token=token,
        user=UserInfo(id=user_id, username=req.username, is_admin=is_admin),
    )


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """Authenticate user and return JWT token."""
    user = await get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user["id"], user["username"], bool(user["is_admin"]))
    return AuthResponse(
        token=token,
        user=UserInfo(
            id=user["id"],
            username=user["username"],
            is_admin=bool(user["is_admin"]),
        ),
    )


@app.get("/api/auth/me", response_model=AuthResponse)
async def me(current_user: dict = Depends(get_current_user)):
    """Return current authenticated user info."""
    return AuthResponse(
        token="",  # don't re-issue token on me check
        user=UserInfo(
            id=current_user["user_id"],
            username=current_user["username"],
            is_admin=current_user["is_admin"],
        ),
    )
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add auth endpoints (register, login, me) and health check"
```

---

### Task 8: Protect existing debate routes with JWT

**Files:**
- Modify: `main.py` (all `/api/debate/*` routes)

- [ ] **Step 1: Protect GET /api/debates**

Replace `list_debates`:

```python
@app.get("/api/debates")
async def list_debates(current_user: dict = Depends(get_current_user)):
    """Return all debates for the current user, ordered by created_at DESC."""
    rows = await get_all_debates(user_id=current_user["user_id"])
    return {"debates": [dict(r) for r in rows]}
```

- [ ] **Step 2: Protect GET /api/debate/active**

Replace `get_active`:

```python
@app.get("/api/debate/active")
async def get_active(current_user: dict = Depends(get_current_user)):
    """Return the most recent unfinished debate for the current user."""
    debate = await get_active_debate(user_id=current_user["user_id"])
    if not debate:
        return {"active": False, "debate": None}

    speeches = await get_speeches(debate["id"])
    debate["speeches"] = [dict(s) for s in speeches]
    return {"active": True, "debate": debate}
```

- [ ] **Step 3: Protect POST /api/debate/start**

Replace `start_debate` signature — add `current_user` dependency and pass `user_id`:

```python
@app.post("/api/debate/start")
async def start_debate(req: StartDebateRequest, current_user: dict = Depends(get_current_user)):
    """Create a new debate and launch the Flow in background."""
    debate_id = str(uuid.uuid4())

    await create_debate(
        id=debate_id,
        topic=req.topic,
        total_rounds=req.rounds,
        pro_skills=req.pro_skills.model_dump(),
        con_skills=req.con_skills.model_dump(),
        judge_skill=req.judge_skill,
        user_id=current_user["user_id"],
    )

    flow = DebateFlow(debate_id)
    flow.state.topic = req.topic
    flow.state.total_rounds = req.rounds
    flow.state.pro_skills = req.pro_skills.model_dump()
    flow.state.con_skills = req.con_skills.model_dump()
    flow.state.judge_skill = req.judge_skill
    flow.state.id = debate_id

    _active_flows[debate_id] = flow
    asyncio.create_task(_run_debate(debate_id, flow))

    return StartDebateResponse(debate_id=debate_id, status="running")
```

- [ ] **Step 4: Add ownership verification helper**

Add before the stream endpoint:

```python
async def _verify_ownership_or_admin(debate_id: str, current_user: dict) -> dict:
    """Verify the current user owns the debate or is admin. Returns the debate."""
    debate = await get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    is_admin = current_user.get("is_admin", False)
    is_owner = debate.get("user_id") == current_user["user_id"]
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Access denied")

    return debate
```

- [ ] **Step 5: Protect GET /api/debate/{id}/stream, pause, resume, get_detail**

Add `current_user` dependency and call `_verify_ownership_or_admin` at the top of each:

```python
@app.get("/api/debate/{debate_id}/stream")
async def stream_debate(debate_id: str, current_user: dict = Depends(get_current_user)):
    """SSE endpoint: stream debate events to the client."""
    debate = await _verify_ownership_or_admin(debate_id, current_user)

    # ... rest of function unchanged
```

```python
@app.post("/api/debate/{debate_id}/pause")
async def pause_debate(debate_id: str, current_user: dict = Depends(get_current_user)):
    """Pause a running debate."""
    await _verify_ownership_or_admin(debate_id, current_user)
    flow = _active_flows.get(debate_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Debate not found or already finished")

    flow.state.paused = True
    await update_debate_status(debate_id, "paused")
    sse_bridge.push(debate_id, SSEPaused(debate_id=debate_id))
    return {"status": "paused"}
```

```python
@app.post("/api/debate/{debate_id}/resume")
async def resume_debate(debate_id: str, current_user: dict = Depends(get_current_user)):
    """Resume a paused debate."""
    await _verify_ownership_or_admin(debate_id, current_user)
    flow = _active_flows.get(debate_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Debate not found or already finished")

    flow.state.paused = False
    await update_debate_status(debate_id, "running")
    sse_bridge.push(debate_id, SSEResumed(debate_id=debate_id))
    return {"status": "running"}
```

```python
@app.get("/api/debate/{debate_id}")
async def get_debate_detail(debate_id: str, current_user: dict = Depends(get_current_user)):
    """Get debate detail with all speeches for history replay."""
    debate = await _verify_ownership_or_admin(debate_id, current_user)

    speeches = await get_speeches(debate_id)
    debate_dict = dict(debate)
    debate_dict["speeches"] = [dict(s) for s in speeches]
    return debate_dict
```

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: protect all debate routes with JWT auth and ownership verification"
```

---

### Task 9: Add admin API routes

**Files:**
- Modify: `main.py` (append admin routes before error handlers section)

- [ ] **Step 1: Add admin routes**

```python
# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@app.get("/api/admin/users")
async def admin_list_users(admin: dict = Depends(get_admin_user)):
    """List all users with debate counts. Admin only."""
    users = await get_all_users()
    return {
        "users": [
            AdminUserItem(
                id=u["id"],
                username=u["username"],
                is_admin=bool(u["is_admin"]),
                debate_count=u.get("debate_count", 0),
                created_at=str(u.get("created_at", "")),
            ) for u in users
        ]
    }


@app.get("/api/admin/users/{user_id}/debates")
async def admin_user_debates(user_id: str, admin: dict = Depends(get_admin_user)):
    """List all debates for a specific user. Admin only."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    debates = await get_debates_by_user(user_id)
    return {"user": user["username"], "debates": [dict(d) for d in debates]}


@app.get("/api/admin/debates")
async def admin_all_debates(admin: dict = Depends(get_admin_user)):
    """List all debates across all users. Admin only."""
    rows = await get_all_debates()
    return {"debates": [dict(r) for r in rows]}
```

- [ ] **Step 2: Serve admin.html page**

Add a route for the admin page:

```python
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """Serve the admin panel page."""
    admin_path = os.path.join(static_dir, "admin.html")
    if os.path.exists(admin_path):
        with open(admin_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Admin Panel</h1><p>admin.html not found</p>")
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add admin API routes (users list, user debates, all debates)"
```

---

### Task 10: Update test_db.py for user functions

**Files:**
- Modify: `test_db.py`

- [ ] **Step 1: Add user tests to test_db.py**

Append a new test section before the `return failures` line in `run_tests`:

```python
    # ── user CRUD ────────────────────────────────────────────────────────
    print("\n=== user CRUD ===")
    try:
        user_id = await db.create_user("alice", "$2b$12$hashed", is_admin=False)
        assert user_id, f"expected non-empty user id, got {user_id!r}"
        ok(f"created user alice with id={user_id}")

        user = await db.get_user_by_username("alice")
        assert user is not None, "get_user_by_username returned None"
        assert user["username"] == "alice"
        assert user["password_hash"] == "$2b$12$hashed"
        assert user["is_admin"] == 0
        ok("get_user_by_username returns correct fields")

        user2 = await db.get_user_by_id(user_id)
        assert user2 is not None
        assert user2["username"] == "alice"
        ok("get_user_by_id returns correct user")

        missing = await db.get_user_by_username("nobody")
        assert missing is None
        ok("get_user_by_username returns None for missing user")

        user_id2 = await db.create_user("bob", "$2b$12$hash2", is_admin=True)
        users = await db.get_all_users()
        assert len(users) >= 2
        ok(f"get_all_users returns {len(users)} users with debate counts")
    except Exception as exc:
        fail("user CRUD", str(exc))
        failures += 1

    # ── debate user_id FK ────────────────────────────────────────────────
    print("\n=== debate user_id FK ===")
    try:
        await db.create_debate(
            id="deb-user-1",
            topic="User scoped debate",
            total_rounds=1,
            pro_skills={},
            con_skills={},
            judge_skill=None,
            user_id=user_id,
        )
        ok("created debate with user_id")

        debates = await db.get_all_debates(user_id=user_id)
        assert any(d["id"] == "deb-user-1" for d in debates), "debate not found for user"
        ok("get_all_debates filters by user_id")

        active = await db.get_active_debate(user_id=user_id)
        assert active is not None
        assert active["id"] == "deb-user-1"
        ok("get_active_debate filters by user_id")

        user_debates = await db.get_debates_by_user(user_id)
        assert any(d["id"] == "deb-user-1" for d in user_debates)
        ok("get_debates_by_user returns correct debates")
    except Exception as exc:
        fail("debate user_id FK", str(exc))
        failures += 1
```

- [ ] **Step 2: Run db tests**

Run: `python test_db.py`
Expected: ALL TESTS PASSED

- [ ] **Step 3: Commit**

```bash
git add test_db.py
git commit -m "test: add user CRUD and debate user_id FK tests"
```

---

### Task 11: Create test_auth.py

**Files:**
- Create: `test_auth.py`

- [ ] **Step 1: Write test_auth.py with FastAPI TestClient tests for auth endpoints**

```python
"""
Tests for auth module and auth endpoints.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_tmp_db = tempfile.mktemp(suffix=".auth_test.db")
os.environ["DEBATE_DB_PATH"] = _tmp_db
os.environ["DEEPSEEK_API_KEY"] = "test-key-mock"
os.environ["ADMIN_USERS"] = "admin"

from main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestRegister:
    def test_register_new_user(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "alice", "password": "secret123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "alice"
        assert data["user"]["is_admin"] is False

    def test_register_admin_user(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "admin", "password": "admin123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["is_admin"] is True

    def test_register_duplicate(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "alice", "password": "another"
        })
        assert resp.status_code == 409

    def test_register_short_username(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "a", "password": "password"
        })
        assert resp.status_code == 400

    def test_register_short_password(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "charlie", "password": "ab"
        })
        assert resp.status_code == 400


class TestLogin:
    def test_login_success(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "secret123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "alice"

    def test_login_wrong_password(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "alice", "password": "wrongpass"
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "nobody", "password": "whatever"
        })
        assert resp.status_code == 401


class TestMe:
    def test_me_with_valid_token(self, client):
        # Register to get a token
        reg = client.post("/api/auth/register", json={
            "username": "bob", "password": "bob1234"
        })
        token = reg.json()["token"]

        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "bob"

    def test_me_without_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, client):
        resp = client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid.token.here"
        })
        assert resp.status_code == 401
```

- [ ] **Step 2: Run auth tests**

Run: `pytest test_auth.py -v`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add test_auth.py
git commit -m "test: add auth endpoint tests (register, login, me)"
```

---

### Task 12: Update test_main.py for auth protection

**Files:**
- Modify: `test_main.py`

- [ ] **Step 1: Add auth header helper and fix existing test fixtures**

At the top of `test_main.py`, after imports, add a helper and update the `auto_cleanup` fixture to also create a test user:

```python
# Add to imports:
from auth import create_access_token

# Add after the TestClient fixture:
@pytest.fixture(scope="module")
def auth_headers():
    """Create a JWT for a test user to use in authenticated requests."""
    token = create_access_token("test-user-id", "testuser", is_admin=False)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_headers():
    """Create a JWT for an admin test user."""
    token = create_access_token("admin-id", "adminuser", is_admin=True)
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: Update TestStartDebate to pass auth headers**

All `client.post("/api/debate/start", ...)` calls must now include `headers=auth_headers`. Update the mock patches to include `create_access_token` if needed.

Due to the Mock patches, we need to ensure `get_current_user` dependency is properly handled. In FastAPI TestClient, dependencies are resolved normally — but since we're mocking `create_debate` (which now requires `user_id`), the dependency chain still works because the JWT in the header is real and `create_access_token` uses the same `JWT_SECRET_KEY`.

Update test methods to pass headers:

```python
class TestStartDebate:
    @patch("main.create_debate")
    @patch("main.DebateFlow")
    @patch("main.asyncio.create_task")
    def test_start_creates_debate_and_returns_id(
        self, mock_create_task, mock_flow_cls, mock_create_db, client, auth_headers
    ):
        mock_create_db.return_value = None
        mock_flow_cls.return_value = MagicMock()

        response = client.post("/api/debate/start", json={
            "topic": "Test topic",
            "rounds": 1,
        }, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "debate_id" in data
        assert data["status"] == "running"

    def test_start_without_auth(self, client):
        response = client.post("/api/debate/start", json={
            "topic": "Test topic",
            "rounds": 1,
        })
        assert response.status_code == 401
```

- [ ] **Step 3: Update other test classes**

Update TestActiveDebate, TestDebates, TestPauseResume, TestDebateDetail to pass `auth_headers`. Add "without auth" test cases where appropriate.

Key pattern for each test method: add `auth_headers` parameter and pass `headers=auth_headers` to client calls.

- [ ] **Step 4: Run main tests**

Run: `pytest test_main.py -v`
Expected: existing tests pass with auth headers, new "without auth" tests pass

Note: Some test methods that mock `get_active_debate` or `get_debate` may need `user_id` returned in the mock debate dict. Add `"user_id": "test-user-id"` to mock return values.

- [ ] **Step 5: Commit**

```bash
git add test_main.py
git commit -m "test: update main tests with JWT auth headers"
```

---

### Task 13: Update test_models.py for new auth models

**Files:**
- Modify: `test_models.py`

- [ ] **Step 1: Add auth model tests**

Append to `test_models.py`:

```python
from models import RegisterRequest, LoginRequest, AuthResponse, UserInfo, AdminUserItem


class TestRegisterRequest(unittest.TestCase):
    def test_valid_register(self):
        r = RegisterRequest(username="alice", password="pass1234")
        self.assertEqual(r.username, "alice")
        self.assertEqual(r.password, "pass1234")

    def test_username_too_short(self):
        with self.assertRaises(Exception):
            RegisterRequest(username="a", password="pass1234")

    def test_password_too_short(self):
        with self.assertRaises(Exception):
            RegisterRequest(username="alice", password="abc")


class TestAuthResponse(unittest.TestCase):
    def test_serialize(self):
        u = UserInfo(id="1", username="alice", is_admin=False)
        r = AuthResponse(token="jwt.token.here", user=u)
        data = json.loads(r.model_dump_json())
        self.assertEqual(data["token"], "jwt.token.here")
        self.assertEqual(data["user"]["username"], "alice")


class TestAdminUserItem(unittest.TestCase):
    def test_with_debate_count(self):
        item = AdminUserItem(
            id="u1", username="alice", is_admin=False,
            debate_count=5, created_at="2026-06-14"
        )
        self.assertEqual(item.debate_count, 5)
```

- [ ] **Step 2: Run model tests**

Run: `pytest test_models.py -v`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add test_models.py
git commit -m "test: add auth model tests"
```

---

### Task 14: Frontend — add login/register forms to index.html

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add auth section CSS styles**

Insert after existing header styles in `<style>` block:

```css
  /* ── Auth Panel ── */
  #auth-panel {
    background: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 32px;
    max-width: 400px;
    margin: 0 auto;
    text-align: center;
  }
  #auth-panel.hidden { display: none; }
  .auth-tabs { display: flex; margin-bottom: 20px; }
  .auth-tab {
    flex: 1; padding: 10px; cursor: pointer;
    background: #1a1a2e; border: 1px solid #2a2a4a; color: #888;
    font-size: 0.95rem;
  }
  .auth-tab:first-child { border-radius: 8px 0 0 8px; }
  .auth-tab:last-child { border-radius: 0 8px 8px 0; }
  .auth-tab.active { background: #bb86fc; color: #1a1a2e; border-color: #bb86fc; }
  .auth-form { display: flex; flex-direction: column; gap: 12px; }
  .auth-form.hidden { display: none; }
  .auth-form input {
    padding: 12px; border-radius: 8px; border: 1px solid #2a2a4a;
    background: #1a1a2e; color: #e2e2e2; font-size: 0.95rem;
  }
  .auth-form button {
    padding: 12px; border-radius: 8px; border: none;
    background: #bb86fc; color: #1a1a2e; font-size: 1rem; font-weight: 600;
    cursor: pointer;
  }
  .auth-error { color: #cf6679; font-size: 0.85rem; min-height: 20px; }
  .auth-success { color: #03dac6; font-size: 0.85rem; min-height: 20px; }

  /* ── User Bar ── */
  #user-bar {
    display: flex; justify-content: flex-end; align-items: center;
    gap: 12px; padding: 8px 0; margin-bottom: 12px;
    border-bottom: 1px solid #2a2a4a;
  }
  #user-bar.hidden { display: none; }
  #user-bar .username { color: #bb86fc; font-weight: 600; }
  #user-bar .admin-link { color: #03dac6; text-decoration: none; font-size: 0.85rem; }
  #user-bar button {
    padding: 4px 12px; border-radius: 6px; border: 1px solid #2a2a4a;
    background: transparent; color: #888; cursor: pointer; font-size: 0.85rem;
  }
  #main-content.hidden { display: none; }
```

- [ ] **Step 2: Add auth panel HTML after `<div class="container">`**

```html
  <div class="container">

    <!-- Auth Panel (shown when not logged in) -->
    <div id="auth-panel">
      <div class="auth-tabs">
        <div class="auth-tab active" data-tab="login">登录</div>
        <div class="auth-tab" data-tab="register">注册</div>
      </div>
      <form id="login-form" class="auth-form" onsubmit="handleLogin(event)">
        <input type="text" id="login-username" placeholder="用户名" required autocomplete="username">
        <input type="password" id="login-password" placeholder="密码" required autocomplete="current-password">
        <button type="submit">登录</button>
        <div class="auth-error" id="login-error"></div>
      </form>
      <form id="register-form" class="auth-form hidden" onsubmit="handleRegister(event)">
        <input type="text" id="register-username" placeholder="用户名 (2-50字符)" required minlength="2" maxlength="50" autocomplete="username">
        <input type="password" id="register-password" placeholder="密码 (至少4字符)" required minlength="4" maxlength="128" autocomplete="new-password">
        <button type="submit">注册</button>
        <div class="auth-error" id="register-error"></div>
        <div class="auth-success" id="register-success"></div>
      </form>
    </div>

    <!-- User Bar (shown when logged in) -->
    <div id="user-bar" class="hidden">
      <span class="username" id="current-username"></span>
      <a class="admin-link hidden" id="admin-link" href="/admin" target="_blank">管理面板</a>
      <button onclick="logout()">退出</button>
    </div>

    <!-- Main Content (shown when logged in) -->
    <div id="main-content" class="hidden">
      <!-- existing content: header, config panel, history panel, debate stage, etc. -->
```

**Important**: Move the existing `<header>`, `#config-panel`, `#history-panel`, `#debate-stage` etc. INSIDE `#main-content`, and close the `</div>` for `#main-content` before the closing `</div>` of `.container`.

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: add login/register forms and user bar to index.html"
```

---

### Task 15: Frontend — add auth logic to app.js

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add auth state and functions at the top of app.js**

```javascript
// ---- Auth State ----
let currentUser = null;

function getToken() {
    return localStorage.getItem('debate_token');
}

function setToken(token) {
    localStorage.setItem('debate_token', token);
}

function clearToken() {
    localStorage.removeItem('debate_token');
}

// ---- Auth UI ----

function showAuthPanel() {
    document.getElementById('auth-panel').classList.remove('hidden');
    document.getElementById('user-bar').classList.add('hidden');
    document.getElementById('main-content').classList.add('hidden');
}

function showMainUI(user) {
    currentUser = user;
    document.getElementById('auth-panel').classList.add('hidden');
    document.getElementById('user-bar').classList.remove('hidden');
    document.getElementById('main-content').classList.remove('hidden');
    document.getElementById('current-username').textContent = user.username;

    if (user.is_admin) {
        document.getElementById('admin-link').classList.remove('hidden');
    }

    loadSkills();
    loadDebateList();
}

// ---- Auth API ----

async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errEl = document.getElementById('login-error');
    errEl.textContent = '';

    try {
        const resp = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            errEl.textContent = data.detail || 'Login failed';
            return;
        }
        setToken(data.token);
        showMainUI(data.user);
    } catch (err) {
        errEl.textContent = 'Network error: ' + err.message;
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value;
    const errEl = document.getElementById('register-error');
    const succEl = document.getElementById('register-success');
    errEl.textContent = '';
    succEl.textContent = '';

    try {
        const resp = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            errEl.textContent = data.detail || 'Registration failed';
            return;
        }
        succEl.textContent = '注册成功！正在登录...';
        setToken(data.token);
        setTimeout(() => showMainUI(data.user), 500);
    } catch (err) {
        errEl.textContent = 'Network error: ' + err.message;
    }
}

function logout() {
    clearToken();
    currentUser = null;
    if (eventSource) { eventSource.close(); eventSource = null; }
    showAuthPanel();
}

// ---- Auth header helper ----

function authHeaders() {
    const token = getToken();
    return token ? { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}
```

- [ ] **Step 2: Update DOMContentLoaded init**

Replace the existing `DOMContentLoaded` handler:

```javascript
document.addEventListener('DOMContentLoaded', () => {
    // Auth tab switching
    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const isLogin = tab.dataset.tab === 'login';
            document.getElementById('login-form').classList.toggle('hidden', !isLogin);
            document.getElementById('register-form').classList.toggle('hidden', isLogin);
        });
    });

    // Debate controls
    document.getElementById('start-btn').addEventListener('click', startDebate);
    document.getElementById('pause-btn').addEventListener('click', pauseDebate);
    document.getElementById('resume-btn').addEventListener('click', resumeDebate);
    document.getElementById('new-debate-btn').addEventListener('click', resetToNewDebate);
    document.getElementById('back-list-btn').addEventListener('click', showHistoryPanel);

    // Check if already logged in
    checkAuth();
});

async function checkAuth() {
    const token = getToken();
    if (!token) {
        showAuthPanel();
        return;
    }

    try {
        const resp = await fetch('/api/auth/me', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!resp.ok) {
            clearToken();
            showAuthPanel();
            return;
        }
        const data = await resp.json();
        showMainUI(data.user);
    } catch (err) {
        showAuthPanel();
    }
}
```

- [ ] **Step 3: Update all fetch calls to use authHeaders()**

Replace all `fetch('/api/...'` calls in the file with `fetch('/api/...', { headers: authHeaders() })`.

For POST requests, merge with existing body:
```javascript
// Before:
fetch('/api/debate/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
})

// After:
fetch('/api/debate/start', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
})
```

For GET requests:
```javascript
// Before:
fetch('/api/debates')

// After:
fetch('/api/debates', { headers: authHeaders() })
```

For EventSource (SSE), tokens can't be passed via headers. Use a query param approach:
```javascript
// In startDebate, when creating EventSource:
const token = getToken();
eventSource = new EventSource(`/api/debate/${debateId}/stream?token=${encodeURIComponent(token)}`);
```

Update the SSE stream endpoint in `main.py` to accept `token` query param as fallback:

```python
@app.get("/api/debate/{debate_id}/stream")
async def stream_debate(
    debate_id: str,
    token: str | None = None,
    current_user: dict = Depends(get_current_user),
):
```

But for simplicity, we change the `get_current_user` dependency to also check query params:

In `auth.py`, update `get_current_user`:

```python
async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract and validate JWT from Authorization header or ?token query param."""
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        # Fallback: check query param (for EventSource)
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication")

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "user_id": payload["sub"],
        "username": payload["username"],
        "is_admin": payload.get("is_admin", False),
    }
```

- [ ] **Step 4: Commit**

```bash
git add static/app.js auth.py
git commit -m "feat: add auth logic to app.js with login/register/logout and JWT in fetch/SSE"
```

---

### Task 16: Create admin.html admin panel page

**Files:**
- Create: `static/admin.html`

- [ ] **Step 1: Write admin.html with user list and debate drill-down**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>管理面板 - Admin Panel</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
    background: #1a1a2e; color: #e2e2e2; min-height: 100vh; line-height: 1.6;
  }
  .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
  header { text-align: center; padding: 20px 0; border-bottom: 1px solid #2a2a4a; margin-bottom: 24px; }
  header h1 { font-size: 1.4rem; color: #bb86fc; }
  header a { color: #03dac6; text-decoration: none; font-size: 0.85rem; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
  th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #2a2a4a; }
  th { color: #bb86fc; font-weight: 600; font-size: 0.85rem; }
  tr:hover { background: #16213e; }
  tr.user-row { cursor: pointer; }
  tr.expanded { background: #16213e; }
  .debate-list { padding: 0 16px 12px; }
  .debate-item {
    background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 6px;
    padding: 10px 16px; margin-bottom: 8px; display: flex; justify-content: space-between;
    align-items: center;
  }
  .debate-item .topic { font-weight: 600; }
  .debate-item .meta { font-size: 0.8rem; color: #888; }
  .status-badge {
    padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;
  }
  .status-running { background: #03dac6; color: #000; }
  .status-finished { background: #2a2a4a; color: #888; }
  .status-paused { background: #cf6679; color: #000; }
  .loading { text-align: center; color: #888; padding: 40px; }
  .error { text-align: center; color: #cf6679; padding: 40px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>系统管理面板</h1>
    <a href="/">← 返回辩论页面</a>
  </header>

  <div id="content"><div class="loading">加载中...</div></div>
</div>

<script>
const TOKEN = localStorage.getItem('debate_token');

function authHeaders() {
  return TOKEN ? { 'Authorization': 'Bearer ' + TOKEN } : {};
}

async function loadUsers() {
  const resp = await fetch('/api/admin/users', { headers: authHeaders() });
  if (resp.status === 401 || resp.status === 403) {
    document.getElementById('content').innerHTML = '<div class="error">无权访问，请使用管理员账号登录</div>';
    return;
  }
  const data = await resp.json();

  let html = '<table><thead><tr><th>用户名</th><th>角色</th><th>辩论数</th><th>注册时间</th></tr></thead><tbody>';
  data.users.forEach(u => {
    html += `<tr class="user-row" data-user-id="${u.id}" onclick="toggleDebates(this, '${u.id}')">`;
    html += `<td>${escapeHtml(u.username)}</td>`;
    html += `<td>${u.is_admin ? '管理员' : '用户'}</td>`;
    html += `<td>${u.debate_count}</td>`;
    html += `<td>${u.created_at ? u.created_at.slice(0, 10) : '-'}</td>`;
    html += '</tr>';
    html += `<tr class="debate-row" id="debates-${u.id}" style="display:none"><td colspan="4"><div class="debate-list" id="debate-list-${u.id}"></div></td></tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('content').innerHTML = html;
}

async function toggleDebates(row, userId) {
  const debateRow = document.getElementById('debates-' + userId);
  if (debateRow.style.display !== 'none') {
    debateRow.style.display = 'none';
    row.classList.remove('expanded');
    return;
  }

  debateRow.style.display = '';
  row.classList.add('expanded');

  const listEl = document.getElementById('debate-list-' + userId);
  if (listEl.children.length > 0) return; // already loaded

  listEl.innerHTML = '<div class="loading">加载中...</div>';
  const resp = await fetch(`/api/admin/users/${userId}/debates`, { headers: authHeaders() });
  const data = await resp.json();

  if (!data.debates.length) {
    listEl.innerHTML = '<div style="color:#888;padding:8px">暂无辩论</div>';
    return;
  }

  let html = '';
  data.debates.forEach(d => {
    const statusClass = d.status === 'running' ? 'status-running' : d.status === 'paused' ? 'status-paused' : 'status-finished';
    html += `<div class="debate-item">`;
    html += `<span class="topic">${escapeHtml(d.topic)}</span>`;
    html += `<span class="meta"><span class="status-badge ${statusClass}">${d.status}</span>`;
    html += ` ${d.total_rounds}轮 | 胜方: ${d.winner || '-'} | ${d.created_at ? d.created_at.slice(0, 10) : '-'}</span>`;
    html += '</div>';
  });
  listEl.innerHTML = html;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
  if (!TOKEN) {
    document.getElementById('content').innerHTML = '<div class="error">请先登录</div>';
    return;
  }
  loadUsers();
});
</script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add static/admin.html
git commit -m "feat: add admin panel page with user list and debate drill-down"
```

---

### Task 17: Manual verification & final integration test

- [ ] **Step 1: Run all tests**

Run: `pytest test_*.py -v`
Expected: all tests pass

- [ ] **Step 2: Start the server and do a full manual smoke test**

```bash
# Terminal 1: Start server
ADMIN_USERS=admin python main.py

# Terminal 2: Test register
curl -s -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"pass1234"}' | python -m json.tool

# Test login
curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"pass1234"}' | python -m json.tool

# Test protected endpoint without auth (should fail)
curl -s http://localhost:8080/api/debates
# Expected: 401

# Test protected endpoint with token
TOKEN="..." # paste from login response
curl -s http://localhost:8080/api/debates -H "Authorization: Bearer $TOKEN"

# Test admin access with non-admin
curl -s http://localhost:8080/api/admin/users -H "Authorization: Bearer $TOKEN"
# Expected: 403

# Register admin user
curl -s -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Login as admin
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Admin endpoints should work
curl -s http://localhost:8080/api/admin/users -H "Authorization: Bearer $ADMIN_TOKEN"
```

- [ ] **Step 3: Open browser and test UI flow**

1. Open `http://localhost:8080` — should see login/register panel
2. Register as new user — should auto-login and show debate UI
3. Create a debate — should work
4. Logout — should return to auth panel
5. Login with same credentials — should see previous debate in history
6. Register "admin" user — should see "管理面板" link in user bar
7. Click 管理面板 — admin.html should show all users
8. Click a user row — should expand to show their debates

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final integration fixes after manual testing"
```

---

## Verification Summary

After all tasks complete:

1. `pytest test_*.py -v` — all tests pass
2. `python main.py` starts without errors
3. Manual: register → login → create debate → logout → re-login → verify isolation
4. Manual: admin can see all users and their debates
5. Manual: non-admin cannot access admin endpoints
6. Manual: unauthenticated requests get 401
