"""
FastAPI application for the debate service.

Routes for debate lifecycle, SSE streaming, and static file serving.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from debate_flow import DebateFlow, _active_flows
from db import (
    create_debate,
    get_active_debate,
    get_debate,
    get_speeches,
    init_db,
    update_debate_status,
)
from models import (
    SSEError,
    SSEHistoryReplay,
    SSEPaused,
    SSEResumed,
    StartDebateRequest,
    StartDebateResponse,
)
from skill_loader import list_available_skills
from sse_bridge import sse_bridge


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, set event loop on SSE bridge."""
    await init_db()
    sse_bridge.set_loop(asyncio.get_event_loop())
    yield


app = FastAPI(title="Debate Service", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


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
# Active debate check (for page-refresh reconnection)
# ---------------------------------------------------------------------------


@app.get("/api/debate/active")
async def get_active():
    """Return the most recent unfinished debate, if any.

    Used by the frontend on page load to detect whether a debate is still
    in progress and should be reconnected to.
    """
    debate = await get_active_debate()
    if not debate:
        return {"active": False, "debate": None}

    speeches = await get_speeches(debate["id"])
    debate["speeches"] = [dict(s) for s in speeches]
    return {"active": True, "debate": debate}


# ---------------------------------------------------------------------------
# Debate lifecycle
# ---------------------------------------------------------------------------


@app.post("/api/debate/start")
async def start_debate(req: StartDebateRequest):
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
    )

    # Create Flow
    flow = DebateFlow(debate_id)
    flow.state.topic = req.topic
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
        sse_bridge.remove_debate(debate_id)
        _active_flows.pop(debate_id, None)


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------


@app.get("/api/debate/{debate_id}/stream")
async def stream_debate(debate_id: str):
    """SSE endpoint: stream debate events to the client."""
    # Verify debate exists
    debate = await get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

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
                    total_rounds=state.total_rounds,
                    current_round=state.current_round,
                    current_phase=state.current_phase,
                    paused=state.paused,
                    status="paused" if state.paused else "running",
                    pro_skills=state.pro_skills,
                    con_skills=state.con_skills,
                    judge_skill=state.judge_skill,
                    speeches=[dict(s) for s in speeches],
                )
                yield f"data: {replay.model_dump_json()}\n\n"
            elif speeches:
                # Flow not in memory (server restart) but debate exists in DB
                debate = await get_debate(debate_id)
                if debate:
                    replay = SSEHistoryReplay(
                        debate_id=debate_id,
                        topic=debate.get("topic", ""),
                        total_rounds=debate.get("total_rounds", 1),
                        current_round=0,
                        current_phase="",
                        paused=False,
                        status=debate.get("status", "finished"),
                        pro_skills=debate.get("pro_skills", {}),
                        con_skills=debate.get("con_skills", {}),
                        judge_skill=debate.get("judge_skill"),
                        speeches=[dict(s) for s in speeches],
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
async def pause_debate(debate_id: str):
    """Pause a running debate."""
    flow = _active_flows.get(debate_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Debate not found or already finished")

    flow.state.paused = True
    await update_debate_status(debate_id, "paused")

    sse_bridge.push(debate_id, SSEPaused(debate_id=debate_id))

    return {"status": "paused"}


@app.post("/api/debate/{debate_id}/resume")
async def resume_debate(debate_id: str):
    """Resume a paused debate."""
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
async def get_debate_detail(debate_id: str):
    """Get debate detail with all speeches for history replay."""
    debate = await get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    speeches = await get_speeches(debate_id)

    # Convert Row objects to dicts if needed
    debate_dict = dict(debate)
    debate_dict["speeches"] = [dict(s) for s in speeches]

    return debate_dict


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
