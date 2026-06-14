# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the service (starts on http://localhost:8080)
python main.py

# Restart the service (kill existing + start fresh)
lsof -ti:8080 | xargs kill -9 2>/dev/null; sleep 1 && python /Users/sunwenfei/Desktop/workspace/debate-service/main.py

# Run all tests
pytest -v

# Run a single test file
pytest test_debate_flow.py -v

# Run a specific test
pytest test_agents.py -v -k "test_create_pro_agent"
```

## Architecture

6 AI debaters (3 pro + 3 con) + 1 judge, orchestrated by crewAI Flow, served via FastAPI with SSE streaming to a vanilla HTML/JS frontend. LLM: DeepSeek-v4-pro via OpenAI-compatible API.

### Data flow

```
FastAPI POST /api/debate/start
  → creates DebateFlow (crewAI Flow[DebateState])
  → asyncio.create_task(_run_debate) launches flow.kickoff_async()
  → each phase method: _run_agent_phase()
      → agent.execute_task() runs in ThreadPoolExecutor (via asyncio.to_thread)
      → step_callback pushes SSEThinkingChunk on AgentAction.thought
      → LLM streaming hook (_install_stream_hook) pushes SSESpeechChunk per token
      → SSEBridge (thread-safe singleton) bridges threads → asyncio.Queue → SSE client
      → speech persisted to SQLite via _persist_speech()
```

### Key modules

- **`main.py`**: FastAPI app — lifespan (DB init + SSEBridge loop setup), routes (`/api/debate/start`, `/{id}/stream`, `/{id}/pause`, `/{id}/resume`, `/{id}`), error handlers (400 for validation errors instead of default 422), `GET /api/skills` lists available persona skills
- **`debate_flow.py`**: Core orchestration. `DebateFlow(Flow[DebateState])` chains phases via `@start()` / `@listen`. Module-level `_active_flows: dict[str, DebateFlow]` for pause/resume access. Multi-round: free_debate() contains a `while True` loop that handles inner-round (rebuttal→argument) repeats, avoiding crewAI's broken `or_()`/cyclic routing
- **`agents.py`**: Agent factories (`create_pro_agent`, `create_con_agent`, `create_judge_agent`). `step_callback` receives `AgentAction | AgentFinish` from crewAI's ReAct loop. `_install_stream_hook` monkey-patches `LLM._emit_stream_chunk_event` per-instance to capture streaming tokens before they hit crewAI's event bus — this is the real-time speech path. Speech is NOT chunked post-hoc
- **`sse_bridge.py`**: Singleton `SSEBridge` — `push()` is thread-safe (`call_soon_threadsafe`), `subscribe()`/`unsubscribe()` manage per-debate asyncio.Queues. Module-level `sse_bridge` instance used everywhere
- **`models.py`**: All Pydantic models including `DebateState(FlowState)` (crewAI requires FlowState subclass), request/response models, and SSE event models with Literal `type` fields for JSON dispatch
- **`db.py`**: aiosqlite with WAL mode + foreign keys. Each function opens/closes its own connection. JSON columns (`pro_skills`, `con_skills`, `verdict`) stored as TEXT, parsed via `json.loads` in `_row_to_debate()`
- **`skill_loader.py`**: Scans `~/.claude/skills/*-perspective/SKILL.md`, loads persona skill content, appends to agent backstory via `build_backstory_with_skill()`

### Debate flow phases

```
begin_debate → pro_1_opening → con_1_opening → pro_2_rebuttal → con_2_rebuttal
→ pro_3_argument → con_3_argument → free_debate (3 pro/con exchanges per round;
  if more rounds remain, re-runs rebuttal→argument sub-chain internally)
→ pro_3_closing → con_3_closing → judge_verdict
```

Free debate: round-robin `(i % 3) + 1` picks which debater speaks each exchange. All 6 debaters can participate.

### Judge scoring

4 dimensions × 10 points each = 40 max per side: 论证严谨度, 数据与事实支撑, 反驳有效性, 表达清晰度. Judge outputs JSON, parsed from markdown code blocks (` ```json ... ``` `) with fallback to raw parse. Highest total wins (pro/con/draw).

### SSE event types

`phase_start` → `thinking_chunk` (gray, collapsed) → `speech_chunk` (white, streamed via typewriter renderer at 25ms intervals in JS) → `phase_end`. Plus: `verdict_chunk`, `paused`, `resumed`, `debate_end`, `error`, `history_replay` (sent on SSE reconnect to restore state).

### Pause/resume

`POST /pause` sets `flow.state.paused = True` → `_check_pause()` in `_run_agent_phase()` polls `self.state.paused` every 0.5s via `asyncio.sleep`. Blocks before each phase begins. Resume clears the flag.

### Frontend reconnection

`GET /api/debate/active` returns the most recent unfinished debate. On page load, frontend checks this, restores past speeches from DB, and reconnects SSE. `SSEHistoryReplay` event sent first on SSE connect with full speech history.

### Database

Two tables: `debates` (id, topic, total_rounds, status, pro_skills/con_skills/judge_skill as JSON TEXT, winner, verdict as JSON TEXT, timestamps) and `speeches` (debate_id FK, debater, phase, round_num, thinking, content, seq). Index on `speeches.debate_id`.

### Environment

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEBATE_DB_PATH=debate.db
```

### Key patterns

- crewAI `Flow.kickoff_async()` runs each `@listen` method as a coroutine, but `agent.execute_task()` is synchronous — always wrap in `asyncio.to_thread()`
- `_persist_speech()` is fire-and-forget (not awaited) to avoid blocking the flow. It captures `loop.create_task()` from SSEBridge's stored loop
- Speech streaming uses per-instance method patching on `LLM._emit_stream_chunk_event`, NOT chunking output after the fact. The `stream=True` param + monkey-patch is the only reliable path for real-time tokens with crewAI's DeepSeek provider
- crewAI `or_()` / cyclic `@listen` routing has known `_fired_or_listeners` suppression bugs — the project avoids them entirely, using explicit while-loop + direct `_run_agent_phase()` calls inside `free_debate()`
