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

# Run frontend tests (vitest)
npx vitest run
```

## Architecture

8 AI debaters (4 pro + 4 con) + 1 judge in CDWC (新国辩) format, orchestrated by crewAI Flow, served via FastAPI with SSE streaming to a vanilla HTML/JS frontend. Multi-tenant: JWT auth, debates scoped per user, admin panel. LLM: DeepSeek-v4-pro via OpenAI-compatible API.

### Data flow

```
FastAPI POST /api/debate/start (auth required)
  → creates DebateFlow (crewAI Flow[DebateState]) with format="cdwc" or "standard"
  → asyncio.create_task(_run_debate) launches flow.kickoff_async()
  → each phase method: _run_agent_phase() or _cross_examine()
      → agent.execute_task() runs in ThreadPoolExecutor (via asyncio.to_thread)
      → _cross_examine() wraps execute_task with asyncio.wait_for(timeout=300)
      → step_callback pushes SSEThinkingChunk on AgentAction.thought
      → LLM streaming hook (_install_stream_hook) pushes SSESpeechChunk per token
      → _first_speech callback (register_first_speech_callback) triggers debater
        status change on first chunk arrival (thinking → speaking)
      → OpenAI-level thinking interceptor (_install_thinking_interceptor) captures
        DeepSeek reasoning_content deltas → SSEThinkingChunk
      → SSEBridge (thread-safe singleton) bridges threads → asyncio.Queue → SSE client
      → speech persisted to SQLite via _persist_speech()
```

### Key modules

- **`main.py`**: FastAPI app — lifespan (DB init + SSEBridge loop setup), routes:
  Auth: `/api/auth/register`, `/api/auth/login`, `/api/auth/me`
  Debate: `/api/debate/start`, `/{id}/stream`, `/{id}/pause`, `/{id}/resume`, `/{id}`
  List: `/api/debates`, `/api/debate/active`
  Admin: `/api/admin/users`, `/api/admin/debates`, `/admin`
  Skills: `GET /api/skills` lists available persona skills
  Error handlers: 400 for ValidationError/RequestValidationError/ValueError (not default 422)
  All debate + admin routes require auth via `Depends(get_current_user)`. SSE uses `?token=` query param fallback.
- **`debate_flow.py`**: CDWC (新国辩) format — 8 debaters (4 pro + 4 con) + judge, 12 phases, single round. `DebateFlow(Flow[DebateState])` chains phases via `@start()` / `@listen`. Module-level `_active_flows: dict[str, DebateFlow]` for pause/resume. Cross-examination via `_cross_examine()`: agent factory pattern (`make_examiner`/`make_targets` callables) creates fresh agents each round to prevent crewAI internal state corruption. Each `execute_task` wrapped with `asyncio.wait_for(timeout=300)`. Background flush tasks properly awaited after cancel with `CancelledError` catch. `_check_pause()` called per-round inside the for loop. Free debate: round-robin among all 8 debaters, 4 exchanges.
- **`debate_flow_standard.py`**: Legacy standard format — 6 debaters (3 pro + 3 con) + judge. Multi-round support (rebuttal→argument internal loop). Used as fallback for `format="standard"` in main.py's start endpoint.
- **`agents.py`**: Agent factories (`create_pro_agent`, `create_con_agent`, `create_judge_agent`) for 8 debaters + judge. `_make_llm()` creates DeepSeek-v4-pro LLM with `stream=True` and `thinking: {type: enabled}` extra_body. `_install_stream_hook` monkey-patches `LLM._emit_stream_chunk_event` per-instance, fires `_first_speech` callback on first token to trigger debater status change (thinking → speaking). `register_first_speech_callback` / `unregister_first_speech_callback` manage per-debater status tracking. `_install_thinking_interceptor` globally patches `openai.Completions.create` to capture `reasoning_content` deltas (one-shot global patch via `_think_patched` flag). Context vars (`_current_debater_ctx`, `_current_role_ctx`) propagate debater/phase identity across threads. `_thinking_buffer` with threading.Lock accumulates thinking chunks. `_make_step_callback` pushes crewAI ReAct loop thoughts. `PHASE_ROLES` dict defines 23 distinct speaking roles with per-phase goal/backstory overrides. `PRO_ROLES` / `CON_ROLES` provide base persona backstories.
- **`auth.py`**: JWT auth with bcrypt password hashing. `create_access_token` / `decode_access_token` (HS256, 24h expiry). `get_current_user` FastAPI dependency: extracts JWT from `Authorization: Bearer` header or `?token=` query param (for SSE). `get_admin_user` dependency for admin routes. `JWT_SECRET_KEY` from env or auto-generated (warns on auto-gen).
- **`sse_bridge.py`**: Singleton `SSEBridge` — `push()` is thread-safe (`call_soon_threadsafe`), `subscribe()`/`unsubscribe()` manage per-debate asyncio.Queues. Module-level `sse_bridge` instance used everywhere.
- **`models.py`**: All Pydantic models including `DebateState(FlowState)` (crewAI requires FlowState subclass, now 4v4 debaters), request/response models, SSE event models (14 types), and auth models. SSE events: `phase_start`, `thinking_chunk`, `speech_chunk`, `cross_q_chunk`, `cross_a_chunk`, `phase_end`, `verdict_chunk`, `paused`, `resumed`, `state_snapshot`, `debater_status_change`, `debate_end`, `error`, `history_replay`. All SSE models use Literal `type` fields for JSON dispatch.
- **`db.py`**: aiosqlite with WAL mode + foreign keys. Three tables: `users` (id, username, password_hash, is_admin, created_at) and `debates` (topic, format, status, pro_skills/con_skills/judge_skill as JSON TEXT, winner, verdict as JSON TEXT, debater_status as JSON TEXT, user_id FK, timestamps) and `speeches` (debate_id FK, debater, phase, round_num, thinking, content, seq, speech_type). Auto-migration: adds `format`, `current_debater`, `debater_status`, `user_id` columns to debates; `speech_type` to speeches. Default admin account: admin/1234.
- **`skill_loader.py`**: Scans `~/.claude/skills/*-perspective/SKILL.md`, loads persona skill content, appends to agent backstory via `build_backstory_with_skill()`.

### CDWC debate flow phases (debate_flow.py)

```
begin_debate → pro_1_opening → con_1_opening → con_2_argument → pro_2_argument
→ pro_3_cross_examine (Q&A pairs, max 4 rounds, auto-terminate on "质询到此结束")
→ con_3_cross_examine (Q&A pairs, targets pro_2/pro_3)
→ con_3_summary → pro_3_summary
→ free_debate (4 exchanges, round-robin among all 8 debaters, pro speaks first each round)
→ con_4_closing → pro_4_closing → judge_verdict
```

All 8 debaters participate. Cross-examination: examiner asks → target answers → repeat up to 4 rounds. LLM autonomously signals end. Free debate: 4 rounds, each round picks a pro debater then a con debater.

### Standard debate flow phases (debate_flow_standard.py)

```
begin_debate → pro_1_opening → con_1_opening → pro_2_rebuttal → con_2_rebuttal
→ pro_3_argument → con_3_argument → free_debate (3 pro/con exchanges per round;
  if more rounds remain, re-runs rebuttal→argument sub-chain internally)
→ pro_3_closing → con_3_closing → judge_verdict
```

### Judge scoring

5 dimensions × 10 points each = 50 max per side: 论证严谨度, 数据与事实支撑, 反驳有效性, 表达清晰度, 质询表现. Judge outputs JSON, parsed from markdown code blocks (` ```json ... ``` `) with fallback to raw parse. Highest total wins (pro/con/draw).

### SSE event types

`phase_start` → `thinking_chunk` (gray, collapsed, includes DeepSeek reasoning_content) → `speech_chunk` (white, streamed via typewriter renderer at 25ms intervals in JS) → `phase_end`. Cross-examination: `cross_q_chunk` / `cross_a_chunk`. Status: `state_snapshot` (full debater_status sync), `debater_status_change` (lightweight per-debater badge update). Plus: `verdict_chunk`, `paused`, `resumed`, `debate_end`, `error`, `history_replay` (sent on SSE reconnect to restore state).

### Pause/resume

`POST /pause` sets `flow.state.paused = True` → `_check_pause()` in `_run_agent_phase()` polls `self.state.paused` every 0.5s via `asyncio.sleep`. Blocks before each phase begins, before each cross-examination round, and per-round inside the cross-examination loop. Resume clears the flag.

### Frontend

Modular JS: `app.js` (entry + event binding), `auth.js` (login/register/logout, JWT storage), `api.js` (fetch wrappers with auth headers), `debate.js` (SSE reconnection, debate lifecycle), `history.js` (debate list), `ui.js` (4x2 grid rendering, cross-examination panel, fullscreen, typewriter), `admin.js` (user/debate management). Separate `admin.html` for admin panel. `index.html` handles both auth and debate views. Tests in `static/js/__tests__/` using vitest.

### Frontend reconnection

`GET /api/debate/active` returns the most recent unfinished debate for the current user. On page load, frontend checks this, restores past speeches from DB, and reconnects SSE. `SSEHistoryReplay` event sent first on SSE connect with full speech history and current state snapshot.

### Multi-tenant auth

All debate and admin routes require JWT auth. `get_current_user` extracts JWT from `Authorization: Bearer` header. SSE endpoints accept `?token=` query param (browser EventSource doesn't support custom headers). Admin routes additionally require `is_admin=True` claim. Each debate is scoped to a user via `user_id` FK. Owner or admin can view/pause/resume.

### Database

Three tables: `users` (id, username, password_hash, is_admin, created_at), `debates` (id, topic, format, total_rounds, status, pro_skills/con_skills/judge_skill as JSON TEXT, winner, verdict as JSON TEXT, debater_status as JSON TEXT, user_id FK, timestamps), `speeches` (debate_id FK, debater, phase, round_num, thinking, content, seq, speech_type). Index on `speeches.debate_id`. Auto-migration via `PRAGMA table_info` checks. Default admin account auto-created.

### ECS deployment

Systemd timer + git polling in `deploy/`: `debate.service` runs the app, `debate-deploy.service` + `debate-deploy.timer` auto-deploy via `deploy.sh` (git fetch → check for new commits → pull + restart). `setup.sh` for initial setup (Python venv, systemd unit installation, log dirs).

### Environment

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEBATE_DB_PATH=debate.db
JWT_SECRET_KEY=<random-secret>
JWT_EXPIRE_HOURS=24
ADMIN_USERS=admin,user2
```

### Key patterns

- crewAI `Flow.kickoff_async()` runs each `@listen` method as a coroutine, but `agent.execute_task()` is synchronous — always wrap in `asyncio.to_thread()`
- Cross-examination `execute_task` calls wrapped with `asyncio.wait_for(timeout=300)` to prevent indefinite hangs. TimeoutError caught by existing `except Exception`, pushing SSEError then continuing to next phase
- `_persist_speech()` is fire-and-forget (not awaited) to avoid blocking the flow. It captures `loop.create_task()` from SSEBridge's stored loop
- Speech streaming uses per-instance method patching on `LLM._emit_stream_chunk_event`, NOT chunking output after the fact. The `stream=True` param + monkey-patch is the only reliable path for real-time tokens with crewAI's DeepSeek provider
- `_first_speech` callback (via `register_first_speech_callback`) fires on the first streaming chunk to trigger debater status change from "thinking" to "speaking". Callback auto-unregisters after first fire
- Thinking (reasoning_content) captured via global monkey-patch on `openai.Completions.create` — one-shot via `_think_patched` flag. Uses `_current_debater_ctx` contextvar for per-debater attribution
- crewAI `or_()` / cyclic `@listen` routing has known `_fired_or_listeners` suppression bugs — the project avoids them entirely, using explicit constructs
- Cross-examination: agent factory pattern (`make_examiner`/`make_targets` callables) creates fresh agents each round to prevent crewAI internal state corruption. Each `execute_task` wrapped with `asyncio.wait_for(timeout=300)`. Background flush tasks properly awaited after cancel (`CancelledError` catch). `_check_pause()` called per-round in loop
- `speech_type` column distinguishes: `opening`, `argument`, `cross_q`, `cross_a`, `cross_summary`, `free_debate`, `closing`
- `pysqlite3` override at top of `main.py` for chromadb compat on ECS (never remove this)
- All auth-protected routes use `Depends(get_current_user)`; SSE uses `?token=` fallback
- `_verify_ownership_or_admin` helper ensures users can only access their own debates (unless admin)
- 使用 /opsx:apply 实施任务时，必须采用 TDD 方式：先写失败测试，再写实现代码，每完成一个 task.md 条目就提交一次。
