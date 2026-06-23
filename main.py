"""
FastAPI application for the debate service.

Routes for debate lifecycle, SSE streaming, and static file serving.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

try:
    __import__("pysqlite3")
    import sys

    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.staticfiles import StaticFiles


class NoCacheStaticFiles(StaticFiles):
    """Serve static files with no-cache headers to avoid stale browser cache."""
    async def __call__(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"cache-control"] = b"no-cache, no-store, must-revalidate"
                message["headers"] = [(k, v) for k, v in headers.items()]
            await send(message)
        await super().__call__(scope, receive, send_wrapper)
from pydantic import ValidationError

from auth import create_access_token, get_admin_user, get_current_user, hash_password, verify_password
from debate_flow import DebateFlow, _active_flows
from db import (
    create_debate,
    create_user,
    delete_debate as db_delete_debate,
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
    SSEStateSnapshot,
    StartDebateRequest,
    StartDebateResponse,
    UserInfo,
)
from redis_cache import get_redis
from skill_loader import list_available_skills
from sse_bridge import sse_bridge


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, Redis, set event loop on SSE bridge."""
    await init_db()
    sse_bridge.set_loop(asyncio.get_event_loop())
    get_redis()  # Init Redis singleton (gracefully degrades if unavailable)
    yield
    # Shutdown: close Redis connection pool
    cache = get_redis()
    await cache.close()


app = FastAPI(title="Debate Service", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", NoCacheStaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main debate UI page."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Debate Service</h1><p>index.html not found</p>")


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@app.get("/api/skills")
async def get_skills():
    """List available huashu-nuwa perspective skills."""
    skills = list_available_skills()
    return {"skills": skills}


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
        token="",
        user=UserInfo(
            id=current_user["user_id"],
            username=current_user["username"],
            is_admin=current_user["is_admin"],
        ),
    )


# ---------------------------------------------------------------------------
# Active debate check (for page-refresh reconnection)
# ---------------------------------------------------------------------------


@app.get("/api/debates")
async def list_debates(current_user: dict = Depends(get_current_user)):
    """Return all debates for the current user, ordered by created_at DESC."""
    rows = await get_all_debates(user_id=current_user["user_id"])
    return {"debates": [dict(r) for r in rows]}


@app.get("/api/debate/active")
async def get_active(current_user: dict = Depends(get_current_user)):
    """Return the most recent unfinished debate for the current user.

    Used by the frontend on page load to detect whether a debate is still
    in progress and should be reconnected to.
    """
    debate = await get_active_debate(user_id=current_user["user_id"])
    if not debate:
        return {"active": False, "debate": None}

    speeches = await get_speeches(debate["id"])
    debate["speeches"] = [dict(s) for s in speeches]
    return {"active": True, "debate": debate}


# ---------------------------------------------------------------------------
# Debate lifecycle
# ---------------------------------------------------------------------------


@app.post("/api/debate/start")
async def start_debate(req: StartDebateRequest, current_user: dict = Depends(get_current_user)):
    """Create a new debate and launch the Flow in background."""
    debate_id = str(uuid.uuid4())

    # Persist debate in DB
    await create_debate(
        id=debate_id,
        topic=req.topic,
        total_rounds=req.rounds,
        pro_skills=req.pro_skills.model_dump(),
        con_skills=req.con_skills.model_dump(),
        judge_skill=req.judge_skill,
        format=req.format,
        user_id=current_user["user_id"],
    )

    # Create Flow
    flow = DebateFlow(debate_id)
    flow.state.topic = req.topic
    flow.state.format = req.format
    flow.state.total_rounds = req.rounds
    flow.state.pro_skills = req.pro_skills.model_dump()
    flow.state.con_skills = req.con_skills.model_dump()
    flow.state.judge_skill = req.judge_skill
    flow.state.id = debate_id

    # Register for pause/resume
    _active_flows[debate_id] = flow

    # Launch Flow in background
    asyncio.create_task(_run_debate(debate_id, flow))

    return StartDebateResponse(debate_id=debate_id, status="running")


async def _run_debate(debate_id: str, flow: DebateFlow):
    """Run the debate Flow in background. Handle errors gracefully."""
    try:
        await flow.kickoff_async()
    except Exception as e:
        sse_bridge.push(
            debate_id,
            SSEError(
                debate_id=debate_id,
                message=f"辩论执行异常: {str(e)}",
            ),
        )
        await update_debate_status(debate_id, "finished")
    finally:
        # Cache speeches to Redis for fast replay
        try:
            speeches = await get_speeches(debate_id)
            if speeches:
                cache = get_redis()
                await cache.cache_speeches(debate_id, [dict(s) for s in speeches])
        except Exception:
            pass  # Cache write failure is non-fatal

        sse_bridge.remove_debate(debate_id)
        _active_flows.pop(debate_id, None)


# ---------------------------------------------------------------------------
# Ownership helper
# ---------------------------------------------------------------------------


async def _verify_ownership_or_admin(debate_id: str, current_user: dict) -> dict:
    """Verify the current user owns the debate or is admin. Returns the debate dict."""
    debate = await get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    is_admin = current_user.get("is_admin", False)
    is_owner = debate.get("user_id") == current_user["user_id"]
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Access denied")

    return debate


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@app.delete("/api/debate/{debate_id}")
async def delete_debate(debate_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a debate and its speeches. Owner or admin only."""
    await _verify_ownership_or_admin(debate_id, current_user)

    flow = _active_flows.pop(debate_id, None)
    if flow:
        sse_bridge.remove_debate(debate_id)

    await db_delete_debate(debate_id)

    # Invalidate Redis cache
    cache = get_redis()
    await cache.invalidate_debate(debate_id)

    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------


@app.get("/api/debate/{debate_id}/stream")
async def stream_debate(debate_id: str, current_user: dict = Depends(get_current_user)):
    """SSE endpoint: stream debate events to the client."""
    debate = await _verify_ownership_or_admin(debate_id, current_user)

    async def event_generator():
        queue = sse_bridge.subscribe(debate_id)
        try:
            # Send full history replay so frontend can restore all past speeches
            speeches = await get_speeches(debate_id)
            if debate_id in _active_flows:
                flow = _active_flows[debate_id]
                state = flow.state
                replay = SSEHistoryReplay(
                    debate_id=debate_id,
                    topic=state.topic,
                    format=state.format,
                    total_rounds=state.total_rounds,
                    current_round=state.current_round,
                    current_phase=state.current_phase,
                    current_debater=state.current_debater,
                    paused=state.paused,
                    status="paused" if state.paused else "running",
                    pro_skills=state.pro_skills,
                    con_skills=state.con_skills,
                    judge_skill=state.judge_skill,
                    debater_status=state.debater_status,
                    speeches=[dict(s) for s in speeches],
                    verdict=state.verdict,
                    winner=state.winner,
                )
                yield f"data: {replay.model_dump_json()}\n\n"

                # If a speech is in progress, send state_snapshot so frontend
                # can activate the correct role box (without clearing content).
                if state.current_debater and state.debater_status.get(state.current_debater) == "speaking":
                    snapshot = SSEStateSnapshot(
                        debate_id=debate_id,
                        current_round=state.current_round,
                        total_rounds=state.total_rounds,
                        current_phase=state.current_phase,
                        current_debater=state.current_debater,
                        debater_status=state.debater_status,
                        paused=state.paused,
                        cross_examine_examiner=state.cross_examine_examiner,
                        cross_examine_target=state.cross_examine_target,
                    )
                    yield f"data: {snapshot.model_dump_json()}\n\n"
            elif speeches:
                # Flow not in memory (server restart) but debate exists in DB
                debate = await get_debate(debate_id)
                if debate:
                    # Try Redis cache first for verdict, fall back to DB
                    cache = get_redis()
                    verdict_data = await cache.get_verdict(debate_id)
                    if verdict_data is None:
                        verdict_data = {
                            "verdict": debate.get("verdict"),
                            "winner": debate.get("winner"),
                        }
                        # Backfill cache if verdict exists in DB
                        if verdict_data["verdict"]:
                            await cache.cache_verdict(
                                debate_id,
                                verdict_data["verdict"],
                                verdict_data["winner"] or "",
                            )

                    replay = SSEHistoryReplay(
                        debate_id=debate_id,
                        topic=debate.get("topic", ""),
                        format=debate.get("format", "cdwc"),
                        total_rounds=debate.get("total_rounds", 1),
                        current_round=0,
                        current_phase="",
                        current_debater="",
                        paused=False,
                        status=debate.get("status", "finished"),
                        pro_skills=debate.get("pro_skills", {}),
                        con_skills=debate.get("con_skills", {}),
                        judge_skill=debate.get("judge_skill"),
                        debater_status=debate.get("debater_status", {}),
                        speeches=[dict(s) for s in speeches],
                        verdict=verdict_data.get("verdict"),
                        winner=verdict_data.get("winner"),
                    )
                    yield f"data: {replay.model_dump_json()}\n\n"

            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield data
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"

                # If flow was removed (server restart), close stream
                if debate_id not in _active_flows:
                    yield f"data: {json.dumps({'type': 'debate_end', 'debate_id': debate_id, 'verdict': {}})}\n\n"
                    break

                # Check if debate is finished (clean exit)
                debate_status = await get_debate(debate_id)
                if debate_status and debate_status.get("status") == "finished":
                    while not queue.empty():
                        try:
                            data = queue.get_nowait()
                            yield data
                        except asyncio.QueueEmpty:
                            break
                    break
        finally:
            sse_bridge.unsubscribe(debate_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# History / detail
# ---------------------------------------------------------------------------


@app.get("/api/debate/{debate_id}")
async def get_debate_detail(debate_id: str, current_user: dict = Depends(get_current_user)):
    """Get debate detail with all speeches for history replay."""
    debate = await _verify_ownership_or_admin(debate_id, current_user)

    # Try Redis cache first for speeches
    cache = get_redis()
    speeches = await cache.get_speeches(debate_id)
    if speeches is None:
        # Cache miss — fall back to SQLite and backfill cache
        rows = await get_speeches(debate_id)
        speeches = [dict(r) for r in rows]
        if speeches:
            await cache.cache_speeches(debate_id, speeches)

    # Try Redis cache first for verdict, fall back to DB
    verdict_data = await cache.get_verdict(debate_id)
    if verdict_data is None:
        debate_dict = dict(debate)
        verdict = debate_dict.get("verdict")
        winner = debate_dict.get("winner")
        if verdict:
            await cache.cache_verdict(debate_id, verdict, winner or "")
    else:
        debate_dict = dict(debate)
        debate_dict["verdict"] = verdict_data.get("verdict")
        debate_dict["winner"] = verdict_data.get("winner")

    debate_dict["speeches"] = speeches
    return debate_dict


# ---------------------------------------------------------------------------
# Batch speeches (preload for history page)
# ---------------------------------------------------------------------------


@app.get("/api/debate/speeches/batch")
async def batch_speeches(ids: str = "", current_user: dict = Depends(get_current_user)):
    """Return speech summaries for multiple debates.

    Query: ``?ids=id1,id2,id3``
    Returns ``{speeches: {id1: [...], id2: [...]}}`` with summaries
    (no thinking field) for each debate.  Misses are simply omitted.

    Tries Redis first for each debate; falls back to SQLite for misses
    and backfills the cache.
    """
    debate_ids = [did.strip() for did in ids.split(",") if did.strip()]
    if not debate_ids:
        return {"speeches": {}, "verdicts": {}}

    cache = get_redis()
    result: dict[str, list[dict]] = {}
    all_ids = list(debate_ids)  # preserve full list for verdict phase

    # Phase 1: try Redis batch
    if cache.enabled:
        cached = await cache.get_batch_summaries(debate_ids)
        if cached:
            result.update(cached)
            # Only query SQLite for ids not in cache
            debate_ids = [did for did in debate_ids if did not in cached]

    # Phase 2: SQLite fallback for remaining (cache miss or disabled)
    for did in debate_ids:
        try:
            rows = await get_speeches(did)
            rows = [dict(r) for r in rows]
            if rows:
                result[did] = rows
                # Backfill cache asynchronously
                if cache.enabled:
                    await cache.cache_speeches(did, rows)
        except Exception:
            pass  # Skip debates that fail to load

    # ── Fetch verdicts ──
    verdicts: dict[str, dict] = {}

    # Phase V1: try Redis batch for verdicts
    remaining_vids = list(all_ids)
    if cache.enabled:
        cached_verdicts = await cache.get_batch_verdicts(all_ids)
        if cached_verdicts:
            verdicts.update(cached_verdicts)
            remaining_vids = [did for did in all_ids if did not in cached_verdicts]

    # Phase V2: SQLite fallback for verdicts
    for did in remaining_vids:
        try:
            debate = await get_debate(did)
            if debate:
                v = debate.get("verdict")
                w = debate.get("winner")
                if v:
                    verdicts[did] = {"verdict": v, "winner": w or ""}
                    if cache.enabled:
                        await cache.cache_verdict(did, v, w or "")
        except Exception:
            pass

    return {"speeches": result, "verdicts": verdicts}


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
    user = await get_user_by_username(user_id)
    if not user:
        # Try by id
        from db import get_user_by_id as _get_user
        user = await _get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    debates = await get_debates_by_user(user_id)
    return {"user": user["username"], "debates": [dict(d) for d in debates]}


@app.get("/api/admin/debates")
async def admin_all_debates(admin: dict = Depends(get_admin_user)):
    """List all debates across all users. Admin only."""
    rows = await get_all_debates()
    return {"debates": [dict(r) for r in rows]}


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(admin: dict = Depends(get_admin_user)):
    """Serve the admin panel page. Admin only."""
    admin_path = os.path.join(static_dir, "admin.html")
    if os.path.exists(admin_path):
        with open(admin_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Admin Panel</h1><p>admin.html not found</p>")


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    """FastAPI request validation errors => 400 (not the default 422)."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
