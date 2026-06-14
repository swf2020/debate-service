# Debate Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 6-debater + 1-judge AI debate system using crewAI Flow + FastAPI + SSE streaming.

**Architecture:** crewAI Flow orchestrates debate phases (@start/@listen/@router). Each phase runs an Agent (pro_1/2/3, con_1/2/3) via `agent.execute_task()` in a thread pool. step_callback captures thinking (AgentAction.thought) and speech (AgentFinish.output), pushing them to SSEBridge which bridges threads to asyncio.Queue for FastAPI SSE. SQLite persists all speeches.

**Tech Stack:** FastAPI, crewAI Flow, DeepSeek-v4-pro, SQLite (aiosqlite), SSE, vanilla HTML/JS

**Design spec:** `docs/superpowers/specs/2026-06-14-debate-service-design.md`

---

## File Structure

```
debate-service/
├── requirements.txt
├── .env
├── main.py              # FastAPI app, routes, SSE, lifespan
├── debate_flow.py       # crewAI Flow subclass (orchestration)
├── agents.py            # Agent factories + step_callback
├── sse_bridge.py        # Thread-safe agent→SSE bridge
├── db.py                # SQLite schema + CRUD
├── models.py            # Pydantic models (state, SSE events, API)
├── skill_loader.py      # Huashu-nuwa SKILL.md loader
└── static/
    ├── index.html        # 3x2 debate grid + config panel
    └── app.js            # EventSource SSE consumer
```

---

### Task 1: Create project skeleton

**Files:** `debate-service/requirements.txt`, `debate-service/.env`

- [ ] **Step 1: Create directory and requirements.txt**

```
debate-service/
```

```txt
# requirements.txt
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
crewai>=1.14.0
aiosqlite>=0.20.0
pydantic>=2.0
python-dotenv>=1.0
```

- [ ] **Step 2: Create .env**

```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEBATE_DB_PATH=debate.db
```

- [ ] **Step 3: Install dependencies**

```bash
cd debate-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 4: Commit**

```bash
git add debate-service/requirements.txt debate-service/.env
git commit -m "feat: add debate-service skeleton"
```

---

### Task 2: models.py — All Pydantic models

**File:** `debate-service/models.py`

Define all data models in one file:
- `DebateState(FlowState)` — topic, total_rounds, current_round, current_phase, pro_skills, con_skills, judge_skill, debate_history, paused, verdict, winner, id
- `SkillConfig(BaseModel)` — debater_1/2/3 as Optional[str]
- `StartDebateRequest(BaseModel)` — topic, rounds(1-3), pro_skills, con_skills, judge_skill
- `StartDebateResponse(BaseModel)` — debate_id, status
- `DebateSummary(BaseModel)` — all debate fields + speeches list
- SSE event models: `SSEPhaseStart`, `SSEThinkingChunk`, `SSESpeechChunk`, `SSEPhaseEnd`, `SSEVerdictChunk`, `SSEPaused`, `SSEResumed`, `SSEDebateEnd`, `SSEError` — each with `type` literal and `debate_id`

Key: SSE events serialize via `model_dump_json()` for the SSE wire format.

- [ ] **Step 1: Write models.py with all classes**
- [ ] **Step 2: Write test_models.py and verify defaults/serialization**
- [ ] **Step 3: Commit**

---

### Task 3: sse_bridge.py — Thread-safe agent→SSE bridge

**File:** `debate-service/sse_bridge.py`

`SSEBridge` singleton class:
- `_queues: dict[str, list[asyncio.Queue[str]]]` — per-debate subscriber queues
- `set_loop(loop)` — store main event loop (called at startup)
- `subscribe(debate_id) -> asyncio.Queue` — create queue for new SSE client
- `unsubscribe(debate_id, q)` — remove subscriber
- `push(debate_id, event: BaseModel)` — thread-safe: serializes to `"data: {json}\n\n"` and enqueues via `asyncio.run_coroutine_threadsafe()`
- `remove_debate(debate_id)` — cleanup

Module-level singleton: `sse_bridge = SSEBridge()`

- [ ] **Step 1: Write sse_bridge.py**
- [ ] **Step 2: Test push/subscribe/unsubscribe with test event loop**
- [ ] **Step 3: Commit**

---

### Task 4: db.py — SQLite persistence

**File:** `debate-service/db.py`

Pattern: `get_db()` creates new aiosqlite connection with WAL mode + foreign keys. Each function: `db = await get_db()` / try / finally `await db.close()`.

Functions:
- `init_db()` — CREATE TABLE IF NOT EXISTS debates + speeches + index
- `close_db()` — pass
- `create_debate(id, topic, rounds, pro_skills, con_skills, judge_skill)` — INSERT
- `update_debate_status(id, status)` — UPDATE status, set finished_at if finished
- `set_verdict(id, winner, verdict_dict)` — UPDATE winner/verdict/status
- `insert_speech(debate_id, debater, phase, round_num, thinking, content, seq)` — INSERT
- `get_speeches(debate_id)` — SELECT ORDER BY seq
- `get_debate(debate_id)` — SELECT + JSON parse skills/verdict

Tables match design spec (debates + speeches).

- [ ] **Step 1: Write db.py**
- [ ] **Step 2: Test init_db + create_debate + insert_speech + get_speeches**
- [ ] **Step 3: Commit**

---

### Task 5: skill_loader.py — Load huashu-nuwa persona skills

**File:** `debate-service/skill_loader.py`

Functions:
- `list_available_skills() -> list[dict]` — scan `~/.claude/skills/` for `*-perspective/` dirs with SKILL.md
- `load_perspective_skill(skill_name) -> str | None` — read SKILL.md content
- `build_backstory_with_skill(base_backstory, skill_name) -> str` — append skill content to backstory

Skill content injected as: `"## 你的思维框架（来自 {skill_name}）\n\n{skill_content}"`

- [ ] **Step 1: Write skill_loader.py**
- [ ] **Step 2: Test with real skill directory or mock**
- [ ] **Step 3: Commit**

---

### Task 6: agents.py — Agent factories with step_callback

**File:** `debate-service/agents.py`

Key design: `step_callback` receives `AgentAction | AgentFinish`. On AgentAction → push `SSEThinkingChunk`. On AgentFinish → push `SSESpeechChunk` (chunked into 80-char pieces for streaming effect).

Functions:
- `_make_llm() -> LLM` — DeepSeek-v4-pro via `LLM(model="deepseek/deepseek-v4-pro", api_key=..., base_url=...)`
- `_make_step_callback(debate_id, debater_key) -> Callable` — pushes thinking/speech SSE events
- `create_pro_agent(debate_id, position, topic, skill_name) -> Agent` — roles: 一辩立论/二辩驳论/三辩深入论证+总结
- `create_con_agent(debate_id, position, topic, skill_name) -> Agent` — mirror of pro
- `create_judge_agent(debate_id, topic, skill_name) -> Agent` — verdict + scoring

Default backstories in Chinese for each role. Skill injected via `build_backstory_with_skill()`.

- [ ] **Step 1: Write agents.py**
- [ ] **Step 2: Test agent creation with/without skill, verify step_callback wiring**
- [ ] **Step 3: Commit**

---

### Task 7: debate_flow.py — Flow orchestration (core)

**File:** `debate-service/debate_flow.py`

`DebateFlow(Flow[DebateState])` class:

Phases (matching design spec):

```
@start()          begin_debate()      — init state
@listen           pro_1_opening()     — 正方一辩立论
@listen           con_1_opening()     — 反方一辩立论
@listen           pro_2_rebuttal()    — 正方二辩驳论
@listen           con_2_rebuttal()    — 反方二辩驳论
@listen           pro_3_argument()    — 正方三辩深入论证
@listen           con_3_argument()    — 反方三辩深入论证
@listen           free_debate()       — 交替 3 回合自由辩论
@listen           check_next_round()  — router: "repeat" or "closing"
@listen("repeat") repeat_round()      — trigger next round
@listen("closing") pro_3_closing()    — 正方总结
@listen           con_3_closing()     — 反方总结
@listen           judge_verdict()     — 裁判评分+裁决
```

Each phase method:
1. `await self._check_pause()` — blocks while paused
2. `_push_phase_start(phase, debater, round)`
3. Build agent via `_build_agent(side, position)`
4. Create Task with debate context (prev speeches injected for rebuttal context)
5. `await asyncio.to_thread(agent.execute_task, task, context="")`
6. Append to `self.state.debate_history`
7. `_persist_speech()` — fire-and-forget via `loop.create_task()`
8. `_push_phase_end(phase, debater)`

Free debate: pro-con alternating for 3 exchanges, any debater (round-robin by `(i % 3) + 1`).

Pause: `_check_pause()` polls `self.state.paused` with `asyncio.sleep(0.5)`.

Judge: builds full transcript, tasks judge agent to output JSON with scores, parses and persists verdict.

Module-level: `_active_flows: dict[str, DebateFlow]` for pause/resume access.

- [ ] **Step 1: Write debate_flow.py**
- [ ] **Step 2: Write test_debate_flow.py — mock agents, test phase sequencing**
- [ ] **Step 3: Commit**

---

### Task 8: main.py — FastAPI application

**File:** `debate-service/main.py`

- lifespan: `init_db()` + `sse_bridge.set_loop()` at startup
- `GET /` → serve index.html
- `GET /api/skills` → list available perspective skills
- `POST /api/debate/start` → create debate in DB, launch flow via `asyncio.create_task(run_debate())`
- `GET /api/debate/{id}/stream` → SSE: subscribe to bridge, yield events
- `POST /api/debate/{id}/pause` → set `flow.state.paused = True`, update DB, push paused event
- `POST /api/debate/{id}/resume` → set `flow.state.paused = False`, update DB, push resumed event
- `GET /api/debate/{id}` → return debate summary with speeches
- `StaticFiles` mount for `/static`
- ValueError exception handler → JSON 400

Run debate in background: `asyncio.create_task(flow.kickoff_async(inputs={...}))`

- [ ] **Step 1: Write main.py**
- [ ] **Step 2: Test with uvicorn, verify routes respond**
- [ ] **Step 3: Commit**

---

### Task 9: static/index.html — Frontend page

**File:** `debate-service/static/index.html`

Single page with:
- **Config panel**: topic input, rounds select, 6 debater skill selects (3 pro × 3 con), judge skill select, start button
- **Control bar**: round/phase info, pause/resume buttons
- **Debate grid**: 3 rows × 2 columns (pro_1|con_1, pro_2|con_2, pro_3|con_3)
  - Each cell: debater name + status badge + collapsible thinking section (gray, `<details>`) + speech content (white)
  - Active speaker cell highlighted with border color
- **Verdict section**: scores table (pro/con side by side), winner badge, judge summary

CSS inline in `<style>`. Dark theme (#1a1a2e background).

- [ ] **Step 1: Write index.html with all sections**
- [ ] **Step 2: Verify layout in browser**
- [ ] **Step 3: Commit**

---

### Task 10: static/app.js — SSE consumer + UI logic

**File:** `debate-service/static/app.js`

Functions:
- `loadSkills()` — fetch `/api/skills`, populate selects
- `startDebate()` — POST `/api/debate/start`, show grid, connect SSE
- `connectSSE(debateId)` — `new EventSource()`, `onmessage` → parse JSON → dispatch
- `handleSSEMessage(msg)` — switch on msg.type:
  - `phase_start` → highlight cell, clear previous, set control info
  - `thinking_chunk` → append to `#thinking-{debater}`, scroll
  - `speech_chunk` → append to `#speech-{debater}`, scroll
  - `phase_end` → mark done
  - `verdict_chunk` → show verdict section with scores
  - `paused`/`resumed` → toggle buttons
  - `debate_end` → close EventSource
  - `error` → console.error
- `pauseDebate()` / `resumeDebate()` — POST to API

- [ ] **Step 1: Write app.js**
- [ ] **Step 2: Test SSE flow with mock events in browser console**
- [ ] **Step 3: Commit**

---

### Task 11: Integration test & end-to-end verification

**File:** `debate-service/test_debate_flow.py`

Tests:
- `TestSSEBridge`: push/subscribe, subscribe/unsubscribe
- `TestSkillLoader`: without skill, missing skill, None skill
- `TestModels`: DebateState defaults, SSE event serialization
- `TestDB`: create_debate, insert_speech, get_speeches ordering

Run: `pytest debate-service/test_debate_flow.py -v`

- [ ] **Step 1: Write tests**
- [ ] **Step 2: Run tests, ensure all pass**
- [ ] **Step 3: Start service with `uvicorn main:app --reload --port 8080`**
- [ ] **Step 4: Open browser, input a debate topic, verify full flow: config → 6 debaters speak → verdict**
- [ ] **Step 5: Test pause/resume mid-debate**
- [ ] **Step 6: Test history replay via GET /api/debate/{id}**
- [ ] **Step 7: Commit**

---

## Verification

1. `pytest debate-service/test_debate_flow.py -v` — all tests pass
2. `curl -X POST http://localhost:8080/api/debate/start -H 'Content-Type: application/json' -d '{"topic":"太阳大还是地球大","rounds":1,"pro_skills":{"debater_1":null,"debater_2":null,"debater_3":null},"con_skills":{"debater_1":null,"debater_2":null,"debater_3":null},"judge_skill":null}'` — returns debate_id
3. Open `http://localhost:8080` in browser — config panel visible, skills loaded
4. Enter topic, click start — 6 debater cells appear, thinking streams gray, speech streams white
5. Verdict section shows scores + winner after debate ends
6. Pause mid-debate, resume — debate continues from pause point
