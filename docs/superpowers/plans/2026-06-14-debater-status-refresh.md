# Debater Status & Page Refresh Persistence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-debater 3-state status persistence and a history list view so debater status survives page refresh and users can browse past debates.

**Architecture:** Add `current_debater` + `debater_status` fields to `DebateState` and `SSEHistoryReplay`; push `SSEStateSnapshot` on every status transition; frontend reads `debater_status` dict to render per-cell badges. New `GET /api/debates` endpoint + history list UI on page load.

**Tech Stack:** Python/FastAPI, crewAI Flow, aiosqlite, vanilla JS, SSE

---

### Task 1: Add new models

**Files:**
- Modify: `models.py:19-47` (DebateState), `models.py:153-168` (SSEHistoryReplay)
- Create new classes after line 168 in `models.py`

- [ ] **Step 1: Add `current_debater` + `debater_status` to `DebateState`**

In `models.py`, replace the `DebateState` class (lines 20-47):

```python
class DebateState(FlowState):
    """Persistent state for a single debate run.

    Used as ``self.state`` inside ``DebateFlow`` methods.
    """

    topic: str = ""
    total_rounds: int = 1
    current_round: int = 1
    current_phase: str = ""
    current_debater: str = ""

    pro_skills: dict = Field(
        default_factory=lambda: {"debater_1": "munger-perspective",
                                 "debater_2": None,
                                 "debater_3": None}
    )
    con_skills: dict = Field(
        default_factory=lambda: {"debater_1": None,
                                 "debater_2": None,
                                 "debater_3": None}
    )
    judge_skill: str | None = None

    debate_history: list[dict] = Field(default_factory=list)
    paused: bool = False
    debater_status: dict[str, str] = Field(default_factory=lambda: {
        "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting",
        "con_1": "waiting", "con_2": "waiting", "con_3": "waiting",
        "judge": "waiting",
    })
    verdict: dict | None = None
    winner: str | None = None
    id: str = ""
```

- [ ] **Step 2: Add `current_debater` + `debater_status` to `SSEHistoryReplay`**

In `models.py`, replace the `SSEHistoryReplay` class (lines 153-168):

```python
class SSEHistoryReplay(BaseModel):
    """Sent on SSE reconnect to restore past speeches."""

    type: Literal["history_replay"] = "history_replay"
    debate_id: str
    topic: str
    total_rounds: int
    current_round: int
    current_phase: str
    current_debater: str = ""
    paused: bool
    status: str
    pro_skills: dict = Field(default_factory=dict)
    con_skills: dict = Field(default_factory=dict)
    judge_skill: str | None = None
    debater_status: dict[str, str] = Field(default_factory=dict)
    speeches: list[dict] = Field(default_factory=list)
```

- [ ] **Step 3: Add `SSEStateSnapshot` and `DebateListItem` classes**

Append after `SSEHistoryReplay` (after line 168):

```python
class SSEStateSnapshot(BaseModel):
    """Pushed on every debater status change (speaking/done/waiting)."""

    type: Literal["state_snapshot"] = "state_snapshot"
    debate_id: str
    current_round: int
    total_rounds: int
    current_phase: str
    current_debater: str
    debater_status: dict[str, str]
    paused: bool


class DebateListItem(BaseModel):
    """Single debate row in the history list response."""

    id: str
    topic: str
    status: str
    total_rounds: int
    winner: str | None = None
    created_at: str
    finished_at: str | None = None
```

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
python -m pytest test_agents.py test_debate_flow.py -v
```

Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add models.py
git commit -m "feat: add current_debater, debater_status, SSEStateSnapshot, DebateListItem models"
```

---

### Task 2: DB migration + `get_all_debates`

**Files:**
- Modify: `db.py:34-71` (init_db), `db.py:82-109` (create_debate), `db.py:194-201` (_row_to_debate)
- Add new function after `get_active_debate` in `db.py`

- [ ] **Step 1: Add migration logic to `init_db()`**

In `db.py`, replace `init_db()` (lines 34-71):

```python
async def init_db() -> None:
    """Create tables and index if they don't exist. Migrate existing DBs."""
    db = await get_db()
    try:
        await db.executescript("""
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
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at  DATETIME
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
        await db.commit()
    finally:
        await db.close()
```

- [ ] **Step 2: Update `create_debate()` to include new columns**

Replace `create_debate()` (lines 82-109):

```python
async def create_debate(
    id: str,
    topic: str,
    total_rounds: int,
    pro_skills: dict,
    con_skills: dict,
    judge_skill: str | None,
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
                                 judge_skill, current_debater, debater_status)
            VALUES (?, ?, ?, ?, ?, ?, '', ?)
            """,
            (id, topic, total_rounds, json.dumps(pro_skills),
             json.dumps(con_skills), judge_skill, default_status),
        )
        await db.commit()
    finally:
        await db.close()
```

- [ ] **Step 3: Update `_row_to_debate()` to parse `debater_status`**

Replace `_row_to_debate()` (lines 194-201):

```python
def _row_to_debate(row: aiosqlite.Row) -> dict:
    """Convert a raw debates row to a dict, parsing JSON columns."""
    d = dict(row)
    for col in ("pro_skills", "con_skills", "verdict", "debater_status"):
        raw = d.get(col)
        if raw is not None:
            d[col] = json.loads(raw)
    return d
```

- [ ] **Step 4: Add `get_all_debates()` function**

Append after `_row_to_debate()` (after line 201):

```python
async def get_all_debates() -> list[dict]:
    """SELECT all debates, ordered by created_at DESC."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, topic, status, total_rounds, winner, created_at, "
            "finished_at FROM debates ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
```

- [ ] **Step 5: Run tests to verify no regressions**

```bash
python -m pytest test_debate_flow.py -v
```

Expected: All tests pass with migrated DB schema.

- [ ] **Step 6: Commit**

```bash
git add db.py
git commit -m "feat: add DB migration for debater_status + get_all_debates"
```

---

### Task 3: Status transitions in debate_flow.py

**Files:**
- Modify: `debate_flow.py:13-30` (imports), `debate_flow.py:104-177` (_run_agent_phase), `debate_flow.py:181-185` (begin_debate)
- Add new helper method

- [ ] **Step 1: Add `SSEStateSnapshot` to imports**

Replace the import block (lines 22-30):

```python
from models import (
    SSEPhaseStart,
    SSEPhaseEnd,
    SSEDebateEnd,
    SSEError,
    SSEVerdictChunk,
    SSESpeechChunk,
    SSEStateSnapshot,
    DebateState,
)
```

- [ ] **Step 2: Add `_push_state_snapshot()` helper**

Add after `_push_phase_end()` (after line 81):

```python
    def _push_state_snapshot(self) -> None:
        sse_bridge.push(
            self.debate_id,
            SSEStateSnapshot(
                debate_id=self.debate_id,
                current_round=self.state.current_round,
                total_rounds=self.state.total_rounds,
                current_phase=self.state.current_phase,
                current_debater=self.state.current_debater,
                debater_status=self.state.debater_status,
                paused=self.state.paused,
            ),
        )
```

- [ ] **Step 3: Add status transitions to `_run_agent_phase()`**

In `_run_agent_phase()`, after `await self._check_pause()` (after line 123), add status transition:

```python
        await self._check_pause()

        self.state.current_phase = phase
        self.state.current_debater = debater_key
        self.state.debater_status[debater_key] = "speaking"
        self._push_state_snapshot()
        self._push_phase_start(phase, debater_key, self.state.current_round)
```

After `self._push_phase_end(phase, debater_key)` (after line 165), add done transition:

```python
        self._push_phase_end(phase, debater_key)

        self.state.debater_status[debater_key] = "done"
        self.state.current_debater = ""
        self._push_state_snapshot()
```

- [ ] **Step 4: Initialize all statuses in `begin_debate()`**

Replace `begin_debate()` (lines 181-185):

```python
    @start()
    async def begin_debate(self) -> None:
        """Initialize debate state — round = 1, all debaters waiting."""
        self.state.current_phase = "begin"
        self.state.current_round = 1
        self.state.current_debater = ""
        self.state.debater_status = {
            "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting",
            "con_1": "waiting", "con_2": "waiting", "con_3": "waiting",
            "judge": "waiting",
        }
        self._push_state_snapshot()
```

- [ ] **Step 5: Run flow tests to verify status transitions**

```bash
python -m pytest test_debate_flow.py -v
```

Expected: All tests pass. Status transitions verified.

- [ ] **Step 6: Commit**

```bash
git add debate_flow.py
git commit -m "feat: add debater_status transitions in flow + SSEStateSnapshot push"
```

---

### Task 4: New API endpoints + updated replay

**Files:**
- Modify: `main.py:93-108` (get_active), `main.py:171-243` (stream_debate)

- [ ] **Step 1: Add `GET /api/debates` and update `/api/debate/active`**

In `main.py`, replace the active debate check section (lines 93-108):

```python
@app.get("/api/debates")
async def list_debates():
    """Return all debates ordered by created_at DESC."""
    rows = await get_all_debates()
    return {"debates": [dict(r) for r in rows]}


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
```

Add `get_all_debates` to the import from db (line 23):

```python
from db import (
    create_debate,
    get_active_debate,
    get_all_debates,
    get_debate,
    get_speeches,
    init_db,
    update_debate_status,
)
```

- [ ] **Step 2: Update `SSEHistoryReplay` construction in `stream_debate()`**

In `stream_debate()`, update the two `SSEHistoryReplay` constructions. Replace lines 187-199:

```python
                replay = SSEHistoryReplay(
                    debate_id=debate_id,
                    topic=state.topic,
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
                )
```

Replace lines 204-217:

```python
                    replay = SSEHistoryReplay(
                        debate_id=debate_id,
                        topic=debate.get("topic", ""),
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
                    )
```

- [ ] **Step 3: Run existing tests**

```bash
python -m pytest test_agents.py test_debate_flow.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: add GET /api/debates + updated SSE replay with debater_status"
```

---

### Task 5: Tests for new models and status transitions

**Files:**
- Create: `test_models.py`
- Modify: `test_debate_flow.py:234-323` (TestRunAgentPhase)

- [ ] **Step 1: Create `test_models.py`**

```python
"""Tests for debate_service.models — new SSEStateSnapshot + DebateListItem."""

from __future__ import annotations

import json
import unittest

from models import SSEStateSnapshot, DebateListItem, DebateState, SSEHistoryReplay


class TestSSEStateSnapshot(unittest.TestCase):
    """Tests for SSEStateSnapshot model."""

    def test_default_type_is_state_snapshot(self):
        snap = SSEStateSnapshot(
            debate_id="test-1",
            current_round=1,
            total_rounds=3,
            current_phase="pro_opening",
            current_debater="pro_1",
            debater_status={"pro_1": "speaking"},
            paused=False,
        )
        self.assertEqual(snap.type, "state_snapshot")

    def test_serializes_to_json(self):
        snap = SSEStateSnapshot(
            debate_id="test-1",
            current_round=2,
            total_rounds=3,
            current_phase="free_debate",
            current_debater="con_2",
            debater_status={
                "pro_1": "done", "pro_2": "done", "pro_3": "waiting",
                "con_1": "done", "con_2": "speaking", "con_3": "waiting",
                "judge": "waiting",
            },
            paused=True,
        )
        data = json.loads(snap.model_dump_json())
        self.assertEqual(data["type"], "state_snapshot")
        self.assertEqual(data["debate_id"], "test-1")
        self.assertEqual(data["current_debater"], "con_2")
        self.assertEqual(data["debater_status"]["con_2"], "speaking")
        self.assertTrue(data["paused"])


class TestDebateListItem(unittest.TestCase):
    """Tests for DebateListItem model."""

    def test_minimal_item(self):
        item = DebateListItem(
            id="abc",
            topic="Test",
            status="running",
            total_rounds=2,
            created_at="2026-06-14T10:00:00",
        )
        self.assertEqual(item.id, "abc")
        self.assertIsNone(item.winner)
        self.assertIsNone(item.finished_at)

    def test_finished_item_with_winner(self):
        item = DebateListItem(
            id="xyz",
            topic="AI safety",
            status="finished",
            total_rounds=1,
            winner="pro",
            created_at="2026-06-13T09:00:00",
            finished_at="2026-06-13T09:30:00",
        )
        self.assertEqual(item.winner, "pro")
        self.assertEqual(item.status, "finished")


class TestDebateStateNewFields(unittest.TestCase):
    """Tests for new fields on DebateState."""

    def test_default_current_debater_is_empty(self):
        state = DebateState()
        self.assertEqual(state.current_debater, "")

    def test_default_debater_status_all_waiting(self):
        state = DebateState()
        self.assertEqual(state.debater_status["pro_1"], "waiting")
        self.assertEqual(state.debater_status["con_3"], "waiting")
        self.assertEqual(state.debater_status["judge"], "waiting")
        self.assertEqual(len(state.debater_status), 7)


class TestSSEHistoryReplayNewFields(unittest.TestCase):
    """Tests for new fields on SSEHistoryReplay."""

    def test_default_current_debater_is_empty(self):
        replay = SSEHistoryReplay(
            debate_id="d1",
            topic="t",
            total_rounds=1,
            current_round=1,
            current_phase="",
            paused=False,
            status="running",
        )
        self.assertEqual(replay.current_debater, "")
        self.assertEqual(replay.debater_status, {})

    def test_can_set_debater_status(self):
        replay = SSEHistoryReplay(
            debate_id="d1",
            topic="t",
            total_rounds=1,
            current_round=1,
            current_phase="pro_opening",
            current_debater="pro_1",
            paused=False,
            status="running",
            debater_status={"pro_1": "speaking", "pro_2": "waiting"},
        )
        self.assertEqual(replay.current_debater, "pro_1")
        self.assertEqual(replay.debater_status["pro_1"], "speaking")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run new model tests**

```bash
python -m pytest test_models.py -v
```

Expected: 7 tests pass.

- [ ] **Step 3: Add status transition assertions to `TestRunAgentPhase.test_basic_flow`**

In `test_debate_flow.py`, replace the existing `test_basic_flow` method (lines 245-280):

```python
    def test_basic_flow(self):
        agent = _make_mock_agent("test speech content.")

        async def _run():
            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech") as mock_db, \
                 patch("debate_flow.Task"):

                output = await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "Please open."
                )

                self.assertEqual(output, "test speech content.")

                # Verify state_snapshot was pushed (speaking + done = 2)
                snap_calls = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEStateSnapshot)
                ]
                self.assertEqual(len(snap_calls), 2,
                                 f"Expected 2 SSEStateSnapshot pushes, got {len(snap_calls)}")

                # First snapshot: speaking
                snap1 = snap_calls[0][0][1]
                self.assertEqual(snap1.current_debater, "pro_1")
                self.assertEqual(snap1.debater_status["pro_1"], "speaking")

                # Second snapshot: done
                snap2 = snap_calls[1][0][1]
                self.assertEqual(snap2.current_debater, "")
                self.assertEqual(snap2.debater_status["pro_1"], "done")

                # Verify state after execution
                self.assertEqual(self.flow.state.debater_status["pro_1"], "done")
                self.assertEqual(self.flow.state.current_debater, "")

                # Verify phase_start was pushed
                start_calls = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEPhaseStart)
                ]
                self.assertEqual(len(start_calls), 1)
                self.assertEqual(start_calls[0][0][1].phase, "pro_opening")
                self.assertEqual(start_calls[0][0][1].debater, "pro_1")

                # Verify phase_end was pushed
                end_calls = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEPhaseEnd)
                ]
                self.assertEqual(len(end_calls), 1)
                self.assertEqual(end_calls[0][0][1].phase, "pro_opening")

                # Verify persist
                self.assertTrue(mock_db.called)
                self.assertTrue(agent.execute_task.called)

        asyncio.run(_run())
```

Add `SSEStateSnapshot` to imports in `test_debate_flow.py` (line 18-22):

```python
from models import (
    SSEPhaseStart,
    SSEPhaseEnd,
    SSEError,
    SSEDebateEnd,
    SSEVerdictChunk,
    SSEStateSnapshot,
)
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest test_models.py test_agents.py test_debate_flow.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add test_models.py test_debate_flow.py
git commit -m "test: add model tests + status transition assertions in flow tests"
```

---

### Task 6: Frontend — History list HTML + CSS

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add history list CSS styles**

In `static/index.html`, add before the `</style>` closing tag (before line 371):

```css
  /* ── History List ── */
  #history-panel {
    display: block;
    background: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
  }
  #history-panel.hidden { display: none; }
  #history-panel h2 {
    font-size: 1.1rem;
    color: #bb86fc;
    margin-bottom: 16px;
    letter-spacing: 1px;
  }
  .history-section-title {
    font-size: 0.85rem;
    color: #888;
    margin: 16px 0 8px;
    padding-bottom: 4px;
    border-bottom: 1px solid #2a2a4a;
  }
  .history-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    margin-bottom: 8px;
    transition: border-color 0.2s;
  }
  .history-item:hover { border-color: #3a3a5a; }
  .history-item-meta { flex: 1; min-width: 0; }
  .history-item-topic {
    font-weight: 600;
    color: #e2e2e2;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .history-item-info {
    font-size: 0.78rem;
    color: #888;
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }
  .history-status {
    font-size: 0.75rem;
    padding: 2px 8px;
    border-radius: 8px;
    font-weight: 500;
  }
  .history-status.running { background: #4fc3f7; color: #1a1a2e; }
  .history-status.paused { background: #ffd54f; color: #1a1a2e; }
  .history-status.finished { background: #2e7d32; color: #a5d6a7; }
  .history-item-action button {
    padding: 6px 16px;
    border: 1px solid #bb86fc;
    border-radius: 6px;
    background: transparent;
    color: #bb86fc;
    cursor: pointer;
    font-size: 0.85rem;
    white-space: nowrap;
    transition: background 0.2s;
  }
  .history-item-action button:hover { background: rgba(187,134,252,0.1); }
  .history-empty {
    text-align: center;
    color: #666;
    padding: 24px;
    font-size: 0.9rem;
  }
```

- [ ] **Step 2: Add history list HTML**

Add after the config panel's closing `</div>` (after line 449):

```html
    <!-- History Panel -->
    <div id="history-panel">
      <h2>辩论记录</h2>
      <div id="active-debates-section"></div>
      <div id="history-debates-section"></div>
      <div id="history-empty" class="history-empty" style="display:none;">暂无辩论记录</div>
    </div>
```

- [ ] **Step 3: Add "返回列表" button to control bar**

In the control bar (line 457-461), add a back-to-list button before the new-debate button:

```html
      <div class="control-buttons">
        <button class="ctrl-btn" id="pause-btn" disabled>暂停</button>
        <button class="ctrl-btn" id="resume-btn" disabled>继续</button>
        <button class="ctrl-btn" id="back-list-btn" style="display:none; border-color: #888; color: #888;">返回列表</button>
        <button class="ctrl-btn" id="new-debate-btn" style="display:none; border-color: #bb86fc; color: #bb86fc;">新辩论</button>
      </div>
```

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat: add history list HTML + CSS + back-to-list button"
```

---

### Task 7: Frontend — JS history list + status badge refactor

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Replace page-load init with history list**

Replace the `DOMContentLoaded` init (lines 57-66):

```javascript
// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    loadSkills();
    document.getElementById('start-btn').addEventListener('click', startDebate);
    document.getElementById('pause-btn').addEventListener('click', pauseDebate);
    document.getElementById('resume-btn').addEventListener('click', resumeDebate);
    document.getElementById('new-debate-btn').addEventListener('click', resetToNewDebate);
    document.getElementById('back-list-btn').addEventListener('click', showHistoryPanel);

    loadDebateList();
});
```

- [ ] **Step 2: Add history list functions**

Add after `clearAllCells()` (after line 493) and before `showError()`:

```javascript
// ── History List ──
async function loadDebateList() {
    try {
        const [debatesResp, activeResp] = await Promise.all([
            fetch('/api/debates'),
            fetch('/api/debate/active'),
        ]);
        const debatesData = await debatesResp.json();
        const activeData = await activeResp.json();
        const debates = debatesData.debates || [];

        const activeDebates = debates.filter(d => d.status === 'running' || d.status === 'paused');
        const historyDebates = debates.filter(d => d.status === 'finished');

        // Show history panel, hide everything else
        document.getElementById('history-panel').style.display = 'block';
        document.getElementById('config-panel').style.display = 'none';
        document.getElementById('debate-grid').style.display = 'none';
        document.getElementById('control-bar').style.display = 'none';
        document.getElementById('verdict-section').style.display = 'none';
        document.getElementById('new-debate-btn').style.display = 'none';

        // Render sections
        renderDebateSection('active-debates-section', '进行中', activeDebates);
        renderDebateSection('history-debates-section', '已完成', historyDebates);

        const emptyEl = document.getElementById('history-empty');
        emptyEl.style.display = debates.length === 0 ? 'block' : 'none';
    } catch (err) {
        console.error('Failed to load debate list:', err);
    }
}

function renderDebateSection(containerId, title, debates) {
    const container = document.getElementById(containerId);
    if (debates.length === 0) {
        container.innerHTML = '';
        return;
    }

    let html = `<div class="history-section-title">${title}</div>`;
    debates.forEach(d => {
        const statusLabels = { running: '进行中', paused: '已暂停', finished: '已完成' };
        const statusClass = d.status;
        const statusLabel = statusLabels[d.status] || d.status;
        const roundInfo = d.status === 'finished' ? '' : '';
        const timeLabel = formatTime(d.created_at);
        const actionLabel = d.status === 'finished' ? '查看回放' : '进入';
        const winnerMap = { pro: '正方胜', con: '反方胜', draw: '平局' };
        const resultText = d.winner ? ` · ${winnerMap[d.winner] || d.winner}` : '';

        html += `
            <div class="history-item">
                <div class="history-item-meta">
                    <div class="history-item-topic">${escapeHtml(d.topic)}</div>
                    <div class="history-item-info">
                        <span>${timeLabel}</span>
                        <span>${d.total_rounds}轮</span>
                        <span class="history-status ${statusClass}">${statusLabel}${resultText}</span>
                    </div>
                </div>
                <div class="history-item-action">
                    <button onclick="enterDebate('${d.id}', '${d.status}')">${actionLabel}</button>
                </div>
            </div>`;
    });
    container.innerHTML = html;
}

function formatTime(ts) {
    if (!ts) return '';
    try {
        const d = new Date(ts + 'Z');
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 1) return '刚刚';
        if (diffMins < 60) return `${diffMins}分钟前`;
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) return `${diffHours}小时前`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) return `${diffDays}天前`;
        return d.toLocaleDateString('zh-CN');
    } catch (e) {
        return ts;
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

async function enterDebate(debateId, status) {
    currentDebateId = debateId;

    // Show debate grid
    document.getElementById('history-panel').style.display = 'none';
    document.getElementById('config-panel').style.display = 'none';
    document.getElementById('debate-grid').style.display = 'grid';
    document.getElementById('control-bar').style.display = 'flex';
    document.getElementById('verdict-section').style.display = 'none';
    document.getElementById('new-debate-btn').style.display = 'inline-block';
    document.getElementById('back-list-btn').style.display = 'inline-block';

    clearAllCells();

    if (status === 'finished') {
        // Load full debate data for replay
        try {
            const resp = await fetch(`/api/debate/${debateId}`);
            const debate = await resp.json();
            document.getElementById('round-info').textContent = `共 ${debate.total_rounds} 轮`;
            document.getElementById('phase-info').textContent = '已完成';
            document.getElementById('pause-btn').disabled = true;
            document.getElementById('resume-btn').disabled = true;
            restoreSpeeches(debate.speeches || []);
            if (debate.verdict && debate.winner) {
                showVerdict(debate.verdict, debate.winner);
            }
            // All debaters done for finished debate
            updateAllStatusBadges(debate.debater_status || {});
        } catch (err) {
            showError('加载辩论失败: ' + err.message);
        }
    } else {
        // Connect SSE for live debate
        document.getElementById('pause-btn').disabled = false;
        document.getElementById('resume-btn').disabled = true;
        connectSSE(debateId);
    }
}

function updateAllStatusBadges(debaterStatus) {
    const allKeys = ['pro_1', 'pro_2', 'pro_3', 'con_1', 'con_2', 'con_3'];
    allKeys.forEach(key => {
        const status = debaterStatus[key] || 'waiting';
        setBadgeStatus(key, status);
    });
}

function setBadgeStatus(debater, status) {
    const badge = document.getElementById(`status-${debater}`);
    if (!badge) return;
    badge.classList.remove('active-badge', 'done-badge');
    if (status === 'speaking') {
        badge.textContent = '发言中';
        badge.classList.add('active-badge');
    } else if (status === 'done') {
        badge.textContent = '已完成';
        badge.classList.add('done-badge');
    } else {
        badge.textContent = '等待中';
    }
}
```

- [ ] **Step 3: Update `showHistoryPanel` function**

Add function so "返回列表" button works. Add before `clearAllCells()`:

```javascript
function showHistoryPanel() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    currentDebateId = null;
    activeSpeaker = null;
    loadDebateList();
}
```

- [ ] **Step 4: Refactor `handleSSEMessage()` for `state_snapshot` + debater_status**

Replace the `phase_start` case (lines 349-371):

```javascript
        case 'phase_start':
            // Highlight active speaker cell
            if (activeSpeaker) {
                const prevCell = document.getElementById(`cell-${activeSpeaker}`);
                if (prevCell) prevCell.classList.remove('active');
            }
            activeSpeaker = msg.debater;
            const cell = document.getElementById(`cell-${msg.debater}`);
            if (cell) cell.classList.add('active');

            updateControlInfo(msg.round_num, null, msg.phase);

            // Clear thinking/speech for this debater
            const thinkingEl = document.getElementById(`thinking-${msg.debater}`);
            if (thinkingEl) thinkingEl.textContent = '';
            const speechEl = document.getElementById(`speech-${msg.debater}`);
            if (speechEl) speechEl.textContent = '';
            clearRenderQueue(msg.debater);
            break;
```

Replace the `phase_end` case (lines 389-392):

```javascript
        case 'phase_end':
            if (activeSpeaker === msg.debater) {
                const endCell = document.getElementById(`cell-${msg.debater}`);
                if (endCell) endCell.classList.remove('active');
                activeSpeaker = null;
            }
            break;
```

Add new `state_snapshot` case after `phase_start` case (after line 371):

```javascript
        case 'state_snapshot':
            updateControlInfo(msg.current_round, msg.total_rounds, msg.current_phase);
            updateAllStatusBadges(msg.debater_status || {});
            if (msg.paused) {
                document.getElementById('pause-btn').disabled = true;
                document.getElementById('resume-btn').disabled = false;
            } else {
                document.getElementById('pause-btn').disabled = false;
                document.getElementById('resume-btn').disabled = true;
            }
            break;
```

- [ ] **Step 5: Update `restoreSpeeches()` to use `debater_status`**

Add after existing `restoreSpeeches()` function (after line 139), a new function to restore badges from debater_status. Then update the `history_replay` case in `handleSSEMessage()`:

In `history_replay` case (lines 319-339), add after `restoreSpeeches(msg.speeches || []);`:

```javascript
            updateAllStatusBadges(msg.debater_status || {});
```

- [ ] **Step 6: Update `resetToNewDebate()` to show history panel**

Replace the config panel show in `resetToNewDebate()` (line 190):

```javascript
function resetToNewDebate() {
    // Disconnect SSE
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    currentDebateId = null;
    activeSpeaker = null;

    // Show history panel
    document.getElementById('history-panel').style.display = 'none';
    document.getElementById('config-panel').style.display = 'block';
    document.getElementById('debate-grid').style.display = 'none';
    document.getElementById('control-bar').style.display = 'none';
    document.getElementById('verdict-section').style.display = 'none';
    document.getElementById('new-debate-btn').style.display = 'none';
    document.getElementById('back-list-btn').style.display = 'none';

    clearAllCells();

    // Reset buttons
    document.getElementById('pause-btn').disabled = true;
    document.getElementById('resume-btn').disabled = true;
}
```

- [ ] **Step 7: Update `startDebate()` to hide history panel**

In `startDebate()` after the successful start (after line 273), add hiding the history panel. Already handled since we set `debate-grid` display to 'grid' and config to 'none'. Add hiding history-panel:

After line 276 (`document.getElementById('debate-grid').style.display = 'grid';`), add:

```javascript
        document.getElementById('history-panel').style.display = 'none';
        document.getElementById('back-list-btn').style.display = 'inline-block';
```

- [ ] **Step 8: Update `checkActiveDebate()`**

Replace the entire function to no longer auto-enter a debate on page load — page load now always shows the history list. Replace lines 69-112:

```javascript
// Deprecated: page load now shows history list via loadDebateList()
async function checkActiveDebate() {
    // No longer auto-enter — loadDebateList() handles the initial view
    loadDebateList();
}
```

Actually, remove the `checkActiveDebate` call from `loadDebateList` — they're redundant. Keep `checkActiveDebate` as a no-op for backward compat (in case other code calls it), but remove the call from the init path.

- [ ] **Step 9: Commit**

```bash
git add static/app.js
git commit -m "feat: add history list + status badge refactor in frontend JS"
```

---

### Task 8: Final integration test & verify

- [ ] **Step 1: Run all tests**

```bash
python -m pytest test_models.py test_agents.py test_debate_flow.py -v
```

Expected: All tests pass.

- [ ] **Step 2: Start the service and verify manually**

```bash
python main.py
```

Manual checks:
1. Open `http://localhost:8080` — should see history list (empty on first run)
2. Start a new debate — grid shows, status badges update correctly
3. Refresh during a debate — history list shows debate as active, click "进入" to reconnect
4. Wait for debate to finish — verdict shows, refresh shows debate in history with "查看回放"
5. Click "查看回放" — full debate content + verdict displayed
6. Click "返回列表" — back to history list
7. Click "新辩论" from config panel — start another debate

- [ ] **Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final integration fixes for status + history"
```
