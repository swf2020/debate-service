# Debater Status & Page Refresh Persistence

**Date**: 2026-06-14
**Status**: draft

## Overview

Improve debater status display (waiting/speaking/done) with per-debater persistence, add history list view on page load, and ensure state survives page refresh.

## Current Problems

1. Status badges only reflect "等待" or "发言中" during SSE events; on reconnect, `restoreSpeeches()` marks all debaters with speech as "已完成" — no mid-speech tracking
2. `checkActiveDebate()` only finds **unfinished** debates; completed ones don't auto-restore
3. `SSEHistoryReplay` lacks `current_debater` and per-debater status — frontend can't restore active speaker state
4. No way to browse past debates from the UI

## Design

### Data Model Changes

**`models.py` — `DebateState` new fields:**

```python
current_debater: str = ""  # e.g. "pro_1", "" when idle
debater_status: dict[str, str] = Field(default_factory=lambda: {
    "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting",
    "con_1": "waiting", "con_2": "waiting", "con_3": "waiting",
    "judge": "waiting",
})
```

Status values: `"waiting"` | `"speaking"` | `"done"`

**`models.py` — `SSEHistoryReplay` new fields:**

```python
current_debater: str = ""
debater_status: dict[str, str] = Field(default_factory=dict)
```

**`models.py` — New `SSEStateSnapshot` event:**

```python
class SSEStateSnapshot(BaseModel):
    type: Literal["state_snapshot"] = "state_snapshot"
    debate_id: str
    current_round: int
    total_rounds: int
    current_phase: str
    current_debater: str
    debater_status: dict[str, str]
    paused: bool
```

Replaces the current ad-hoc "state_snapshot" in app.js (line 342) with a proper model.

**`models.py` — New debate list models:**

```python
class DebateListItem(BaseModel):
    id: str
    topic: str
    status: str
    total_rounds: int
    winner: str | None = None
    created_at: str
    finished_at: str | None = None
```

### State Transitions (debate_flow.py)

In `_run_agent_phase()`:

1. **Before execution**: set `state.current_debater = debater_key`, `state.debater_status[debater_key] = "speaking"`, push `SSEStateSnapshot`
2. **After execution**: set `state.debater_status[debater_key] = "done"`, `state.current_debater = ""`, push `SSEStateSnapshot`
3. In `begin_debate()`: initialize all `debater_status` to `"waiting"`

### Database Changes

**`debates` table — new columns:**

- `current_debater TEXT DEFAULT ''`
- `debater_status TEXT DEFAULT '{}'` (JSON)

**Migration strategy**: `init_db()` checks `PRAGMA table_info(debates)` for existing columns, runs `ALTER TABLE ADD COLUMN` for missing ones. Handles both fresh installs and existing databases.

**`db.py` — New `get_all_debates()`:**

```python
async def get_all_debates():
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, topic, status, total_rounds, winner, created_at, finished_at "
            "FROM debates ORDER BY created_at DESC"
        )
        return await cursor.fetchall()
```

**`db.py` — Update `create_debate()` and `_row_to_debate()`** to handle new columns.

### API Changes

**New: `GET /api/debates`**

Returns all debates ordered by `created_at DESC`. Response: `{"debates": [...]}` with id, topic, status, total_rounds, winner, created_at, finished_at.

**Modified: `GET /api/debate/active`**

Include `current_debater` and `debater_status` in response.

**Modified: `GET /api/debate/{debate_id}/stream`**

`SSEHistoryReplay` includes `current_debater` and `debater_status`.

### Frontend Changes

**New: History List View** (page load default)

- Fetch `GET /api/debates` + `GET /api/debate/active`
- Show active/running debates in top section ("进行中的辩论"), historical in bottom section
- Each item: topic, status, round info, timestamp, action button ("进入" for live, "查看回放" for finished)
- "开始新辩论" button at top opens config panel

**Modified: Status badge rendering**

Replace hardcoded status strings in `phase_start`/`phase_end` handlers with `debater_status` dict from `SSEStateSnapshot`:

| Status | Badge text | CSS class |
|--------|-----------|-----------|
| `waiting` | 等待中 | `status-badge` (gray) |
| `speaking` | 发言中 | `status-badge active-badge` (blue pulse) |
| `done` | 已完成 | `status-badge done-badge` (green) |

**Modified: `handleSSEMessage()`**

- Handle `state_snapshot` event: iterate `msg.debater_status`, update each cell's badge
- Keep `phase_start` for cell highlight + round/phase info (no longer sets status text)
- Keep `phase_end` for deactivating cell highlight

**Modified: `restoreSpeeches()`**

Use `debater_status` from `SSEHistoryReplay` to set individual badges, not blanket "已完成".

**Debate view reuse**: Single debate grid works for both live SSE and historical replay. Finished debates load full data via `GET /api/debate/{id}` with speeches.

### Event Flow

```
Page Load
  └→ GET /api/debates + GET /api/debate/active
      └→ Render history list
          ├─ User clicks "开始新辩论" → config panel → start → live grid + SSE
          ├─ User clicks "进入" on active debate → live grid + SSE
          └─ User clicks "查看回放" on finished → grid + GET /api/debate/{id}

Live Debate SSE:
  phase_start (cell highlight)
  → state_snapshot (debater_status: {pro_1: "speaking", ...})
  → thinking_chunk, speech_chunk (content streaming)
  → state_snapshot (debater_status: {pro_1: "done", ...})
  → phase_end (deactivate highlight)
  ...
  → verdict_chunk → debate_end

Page Refresh during live debate:
  → history list shows debate as active
  → user enters → SSE reconnects
  → history_replay event restores all speeches + debater_status
  → frontend restores correct per-debater badges
```

### CSS Changes

Existing `.status-badge`, `.active-badge`, `.done-badge` classes already defined in `index.html:199-215`. Reuse as-is. Add history list styles:

- `.history-list`: panel container with sections
- `.history-item`: card row with flex layout
- `.history-item-meta`: topic/status/date info
- `.history-item-action`: enter/view button

### Files Affected

| File | Changes |
|------|---------|
| `models.py` | `DebateState` new fields, `SSEHistoryReplay` new fields, new `SSEStateSnapshot`, new `DebateListItem` |
| `debate_flow.py` | Status transitions in `_run_agent_phase()`, init in `begin_debate()`, push `SSEStateSnapshot` |
| `db.py` | Migration for new columns, `get_all_debates()`, update `create_debate()` |
| `main.py` | `GET /api/debates`, update `/api/debate/active`, update SSE replay construction |
| `static/app.js` | History list, `state_snapshot` handler, status badge from dict, `restoreSpeeches` fix |
| `static/index.html` | History list HTML + CSS |
| `test_agents.py` | No changes needed |
| `test_debate_flow.py` | Test new status transitions |

### Testing

- Unit: `test_debate_flow.py` — verify `debater_status` transitions in `_run_agent_phase()`
- Unit: `test_models.py` — `SSEStateSnapshot` serialization
- Manual: start debate, refresh mid-speech, verify status badges restore correctly
- Manual: finish debate, refresh page, verify it appears in history list with full replay
