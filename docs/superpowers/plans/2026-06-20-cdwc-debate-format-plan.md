# CDWC Debate Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor debate-service from 3v3 standard format to CDWC (新国辩) 4v4 format with dual-agent cross-examination, 11 phases, and single-round flow.

**Architecture:** Complete rewrite of `debate_flow.py` replacing multi-round `while True` loop with linear 11-phase chain. New `cross_examine()` method supporting dual-agent Q&A with LLM-autonomous termination (max 4 rounds). `agents.py` extended to 4 debaters per side + 5-dimension judge scoring. `models.py` extended with `format` field, new SSE event types. Frontend upgraded to 4×2 grid + cross-examination panel.

**Tech Stack:** Python 3.13, FastAPI, crewAI, DeepSeek-v4-pro, SSE, SQLite, vanilla JS/CSS

---

### Task 1: Extend Agent Roles (4v4 + 5-dimension judge)

**Files:**
- Modify: `agents.py:276-393`

- [ ] **Step 1: Add PRO_ROLES[4] and CON_ROLES[4]**

In `agents.py`, replace PRO_ROLES (lines 276-311) to add position 4:

```python
PRO_ROLES = {
    1: {
        "role": "正方一辩",
        "goal": "开篇立论：清晰阐述正方核心观点，建立论证框架，为后续辩论奠定基础",
        "backstory": """你是一位经验丰富的辩论一辩手，擅长开篇立论。你的任务是在规定时间内清晰地阐述正方立场，建立完整的论证框架。你需要：
1. 明确提出正方的核心观点和定义
2. 构建清晰的论证结构（2-3个核心论点）
3. 用事实和逻辑支撑每个论点
4. 预判反方可能的反驳并预留回应空间
你的发言应该结构清晰、逻辑严密、语言有力。""",
    },
    2: {
        "role": "正方二辩",
        "goal": "驳论反击：针对反方一辩的立论进行有力反驳，同时强化正方论证",
        "backstory": """你是一位犀利的辩论二辩手，擅长驳论和反击。你的任务是在反方一辩立论后，针对其论证中的漏洞和问题进行有力反驳。你需要：
1. 仔细分析反方一辩的论证，找出逻辑漏洞、事实错误或推理跳跃
2. 逐一驳斥反方的核心论点
3. 在反驳的同时，进一步强化正方的论证
4. 为正方三辩的质询做铺垫
你的发言应该精准、犀利，直击要害。""",
    },
    3: {
        "role": "正方三辩",
        "goal": "质询与小结：对反方一/二辩进行质询，并在质询后进行小结",
        "backstory": """你是一位锐利的辩论三辩手，擅长质询和小结。在质询阶段，你需要：
1. 针对反方一辩或二辩的核心论点设计精准的质询问题
2. 通过追问暴露对方论证中的逻辑漏洞和事实错误
3. 控制质询节奏，在达到目的后适时结束质询
在质询小结阶段，你需要：
1. 总结质询中暴露的对方论证问题
2. 将质询成果转化为正方论证的有力支撑
3. 为正方四辩的总结陈词做铺垫
你的质询应该精准、有力，小结应该清晰、系统。""",
    },
    4: {
        "role": "正方四辩",
        "goal": "总结陈词：回顾全场辩论，总结正方核心立场，做最终陈述",
        "backstory": """你是一位沉稳的辩论四辩手，擅长总结陈词。你的任务是辩论的最后做总结陈词。你需要：
1. 回顾整场辩论的核心争议点
2. 总结正方在立论、驳论、质询中的核心论证
3. 指出反方论证中的根本性问题
4. 升华辩题，做有说服力和感染力的最终陈述
你的发言应该全面、深刻、有力，为正方画上完美的句号。""",
    },
}
```

Replace CON_ROLES (lines 313-348) with 4 positions:

```python
CON_ROLES = {
    1: {
        "role": "反方一辩",
        "goal": "开篇立论：清晰阐述反方核心观点，挑战正方立场，建立反方论证框架",
        "backstory": """你是一位经验丰富的辩论一辩手，擅长开篇立论。你的任务是在规定时间内清晰地阐述反方立场，建立完整的论证框架。你需要：
1. 明确提出反方的核心观点和定义
2. 构建清晰的论证结构（2-3个核心论点）
3. 用事实和逻辑支撑每个论点
4. 直接回应正方一辩的立论，指出其问题
你的发言应该结构清晰、逻辑严密、语言有力。""",
    },
    2: {
        "role": "反方二辩",
        "goal": "驳论反击：针对正方二辩的驳论进行再反驳，同时强化反方论证",
        "backstory": """你是一位犀利的辩论二辩手，擅长驳论和反击。你的任务是在正方二辩驳论后，针对其反驳进行再反驳。你需要：
1. 分析正方二辩的反驳，指出其中的逻辑问题
2. 维护并强化反方一辩的立论
3. 对正方论证进行更深入的质疑
4. 为反方三辩的质询做铺垫
你的发言应该精准、犀利，直击要害。""",
    },
    3: {
        "role": "反方三辩",
        "goal": "质询与小结：对正方一/二辩进行质询，并在质询后进行小结",
        "backstory": """你是一位锐利的辩论三辩手，擅长质询和小结。在质询阶段，你需要：
1. 针对正方一辩或二辩的核心论点设计精准的质询问题
2. 通过追问暴露对方论证中的逻辑漏洞和事实错误
3. 控制质询节奏，在达到目的后适时结束质询
在质询小结阶段，你需要：
1. 总结质询中暴露的对方论证问题
2. 将质询成果转化为反方论证的有力支撑
3. 为反方四辩的总结陈词做铺垫
你的质询应该精准、有力，小结应该清晰、系统。""",
    },
    4: {
        "role": "反方四辩",
        "goal": "总结陈词：回顾全场辩论，总结反方核心立场，做最终陈述",
        "backstory": """你是一位沉稳的辩论四辩手，擅长总结陈词。你的任务是辩论的最后做总结陈词。你需要：
1. 回顾整场辩论的核心争议点
2. 总结反方在立论、驳论、质询中的核心论证
3. 指出正方论证中的根本性问题
4. 升华辩题，做有说服力和感染力的最终陈述
你的发言应该全面、深刻、有力，为反方画上完美的句号。""",
    },
}
```

- [ ] **Step 2: Update JUDGE_ROLE to 5 dimensions**

Replace lines 352-376:

```python
JUDGE_ROLE = {
    "role": "裁判",
    "goal": "公正评判：根据双方论证质量、逻辑严谨度、证据支撑、质询有效性和表达清晰度进行综合评分和裁决",
    "backstory": """你是一位资深辩论裁判，具有丰富的评判经验。你的任务是在辩论结束后，根据以下五个维度对双方进行评分：

**评分维度（每项1-10分，满分50分）：**

1. **论证严谨度（1-10分）**：论点的逻辑结构是否严密，推论是否合理，是否存在逻辑谬误
2. **数据与事实支撑（1-10分）**：论证是否有充分的数据、案例和事实作为支撑，引用的来源是否可靠
3. **反驳有效性（1-10分）**：针对对方论证的反驳是否有效、是否准确回应了对方的核心论点
4. **质询有效性（1-10分）**：质询阶段提问的精准度和有效性，对方回答的质量
5. **表达清晰度（1-10分）**：语言表达是否清晰、有条理，是否有效传达了核心观点

你需要：
1. 仔细回顾整场辩论的全过程
2. 按照上述五个维度分别给正方和反方打分
3. 给出每个维度的具体评分理由
4. 计算双方总分，判定胜负（总分高者获胜，平局为draw）
5. 输出JSON格式的裁决结果

裁决JSON格式：
{
  "pro_scores": {"论证严谨度": N, "数据与事实支撑": N, "反驳有效性": N, "质询有效性": N, "表达清晰度": N, "total": N},
  "con_scores": {"论证严谨度": N, "数据与事实支撑": N, "反驳有效性": N, "质询有效性": N, "表达清晰度": N, "total": N},
  "winner": "pro" | "con" | "draw",
  "summary": "综合评语..."
}""",
}
```

- [ ] **Step 3: Update PHASE_CONTEXT for CDWC phases**

Replace lines 382-393:

```python
PHASE_CONTEXT = {
    "pro_opening": "你是正方一辩，现在进行开篇立论。请阐述正方的核心观点和论证框架。",
    "con_opening": "你是反方一辩，现在进行开篇立论。请阐述反方的核心观点，并回应正方一辩的立论。",
    "pro_rebuttal": "你是正方二辩，现在进行驳论。针对反方一辩的立论进行反驳。",
    "con_rebuttal": "你是反方二辩，现在进行驳论。针对正方二辩的驳论进行再反驳。",
    "pro_cross_examine": "你是正方三辩，现在对反方一辩或二辩进行质询。请设计精准的问题，通过追问暴露对方论证中的逻辑漏洞。质询最多4轮，达成目的后请说"感谢，质询到此结束"来结束质询。",
    "con_cross_examine": "你是反方三辩，现在对正方一辩或二辩进行质询。请设计精准的问题，通过追问暴露对方论证中的逻辑漏洞。质询最多4轮，达成目的后请说"感谢，质询到此结束"来结束质询。",
    "pro_cross_summary": "你是正方三辩，现在进行质询小结。请总结质询中暴露的对方论证问题，将质询成果转化为正方论证的支撑。",
    "con_cross_summary": "你是反方三辩，现在进行质询小结。请总结质询中暴露的对方论证问题，将质询成果转化为反方论证的支撑。",
    "free_debate": "现在是自由辩论环节。你可以自由发言，反驳对方观点或强化本方论证。",
    "pro_closing": "你是正方四辩，现在进行总结陈词。请回顾整场辩论，总结正方核心立场，做最终的、有说服力的陈述。",
    "con_closing": "你是反方四辩，现在进行总结陈词。请回顾整场辩论，总结反方核心立场，做最终的、有说服力的陈述。",
    "verdict": "你是裁判，请基于整场辩论的表现，按照评分维度进行综合评分和裁决。输出JSON格式的裁决结果。",
}
```

- [ ] **Step 4: Run tests to verify agents module still works**

```bash
python -m pytest test_agents.py -v
```

Expected: All agent creation tests pass (role constants tests may need updating for new position counts).

- [ ] **Step 5: Update test_agents.py for new constants**

Update tests that validate role counts:
- `TestRolesConstants::test_pro_roles_has_three_positions` → rename to `test_pro_roles_has_four_positions`, change assertion
- `TestRolesConstants::test_con_roles_has_three_positions` → rename to `test_con_roles_has_four_positions`, change assertion
- `TestCreateJudgeAgent::test_backstory_includes_scoring_dimensions` → update expected dimension count

```python
def test_pro_roles_has_four_positions(self):
    self.assertEqual(len(PRO_ROLES), 4)
    for i in range(1, 5):
        self.assertIn(i, PRO_ROLES)
        self.assertIn("role", PRO_ROLES[i])
        self.assertIn("goal", PRO_ROLES[i])
        self.assertIn("backstory", PRO_ROLES[i])

def test_con_roles_has_four_positions(self):
    self.assertEqual(len(CON_ROLES), 4)
    for i in range(1, 5):
        self.assertIn(i, CON_ROLES)
        self.assertIn("role", CON_ROLES[i])
        self.assertIn("goal", CON_ROLES[i])
        self.assertIn("backstory", CON_ROLES[i])
```

- [ ] **Step 6: Commit**

```bash
git add agents.py test_agents.py
git commit -m "feat: extend agent roles to 4v4 CDWC format with 5-dimension judge scoring"
```

---

### Task 2: Extend Data Models (format, cross-examination SSE events, 4v4 state)

**Files:**
- Modify: `models.py:20-53,59-74,84-100,104-211`

- [ ] **Step 1: Add format and cross_examine fields to DebateState**

In `models.py`, update `DebateState` (lines 20-53):

```python
class DebateState(FlowState):
    """Persistent state for a single debate run.

    Used as ``self.state`` inside ``DebateFlow`` methods.
    """

    topic: str = ""
    format: str = "cdwc"       # NEW: "cdwc" | "standard"
    total_rounds: int = 1
    current_round: int = 1
    current_phase: str = ""
    current_debater: str = ""

    # NEW: cross-examination tracking
    cross_examine_round: int = 0       # current round within cross-examine (1-4)
    cross_examine_examiner: str = ""   # who is asking questions
    cross_examine_target: str = ""     # who is answering (con_1 or con_2)

    pro_skills: dict = Field(
        default_factory=lambda: {"debater_1": None,
                                 "debater_2": None,
                                 "debater_3": None,
                                 "debater_4": None}   # NEW: debater_4
    )
    con_skills: dict = Field(
        default_factory=lambda: {"debater_1": None,
                                 "debater_2": None,
                                 "debater_3": None,
                                 "debater_4": None}   # NEW: debater_4
    )
    judge_skill: str | None = None

    debate_history: list[dict] = Field(default_factory=list)
    paused: bool = False
    debater_status: dict[str, str] = Field(default_factory=lambda: {
        "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting", "pro_4": "waiting",
        "con_1": "waiting", "con_2": "waiting", "con_3": "waiting", "con_4": "waiting",
        "judge": "waiting",
    })
    verdict: dict | None = None
    winner: str | None = None
    id: str = ""
```

- [ ] **Step 2: Update SkillConfig to include debater_4**

```python
class SkillConfig(BaseModel):
    """Skills assigned to each debater slot for one side (pro or con)."""

    debater_1: str | None = None
    debater_2: str | None = None
    debater_3: str | None = None
    debater_4: str | None = None   # NEW
```

- [ ] **Step 3: Add format field to StartDebateRequest and DebateSummary**

```python
class StartDebateRequest(BaseModel):
    """Payload to start a new debate."""

    topic: str
    format: str = Field(default="cdwc")   # NEW: "cdwc" | "standard"
    rounds: int = Field(default=1, ge=1, le=3)
    pro_skills: SkillConfig = Field(default_factory=SkillConfig)
    con_skills: SkillConfig = Field(default_factory=SkillConfig)
    judge_skill: str | None = None
```

In `DebateSummary`, add:
```python
format: str = "standard"
```

- [ ] **Step 4: Add SSE event models for cross-examination**

After `SSESpeechChunk`, add:

```python
class SSECrossQChunk(BaseModel):
    type: Literal["cross_q_chunk"] = "cross_q_chunk"
    debate_id: str
    examiner: str         # pro_3 or con_3
    target: str           # who is being asked (con_1, con_2, etc.)
    content: str
    round: int            # 1-4

class SSECrossAChunk(BaseModel):
    type: Literal["cross_a_chunk"] = "cross_a_chunk"
    debate_id: str
    responder: str        # the person answering
    content: str
    round: int            # 1-4
```

Update `SSEHistoryReplay` to include `format`:
```python
format: str = "standard"
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest test_models.py -v
```

Expected: Model creation tests pass. Update any failing tests that check old SkillConfig / SSE structure.

- [ ] **Step 6: Commit**

```bash
git add models.py test_models.py
git commit -m "feat: add CDWC models — format, cross-examination SSE events, 4v4 state"
```

---

### Task 3: Database Migration (add format and speech_type columns)

**Files:**
- Modify: `db.py:91-107,120-149,361-383`

- [ ] **Step 1: Add migration in init_db()**

In `db.py`, after the existing migration block (line ~107), add:

```python
# Migrate: add CDWC format columns
if "format" not in columns:
    await db.execute(
        "ALTER TABLE debates ADD COLUMN format TEXT NOT NULL DEFAULT 'standard'"
    )
if "speech_type" not in columns:
    # Check speeches table
    speech_cols_raw = await db.execute("PRAGMA table_info(speeches)")
    speech_cols = {row[1] for row in await speech_cols_raw.fetchall()}
    if "speech_type" not in speech_cols:
        await db.execute(
            "ALTER TABLE speeches ADD COLUMN speech_type TEXT NOT NULL DEFAULT 'opening'"
        )
```

- [ ] **Step 2: Update create_debate() to accept and store format**

```python
async def create_debate(
    id: str,
    topic: str,
    total_rounds: int,
    pro_skills: dict,
    con_skills: dict,
    judge_skill: str | None,
    user_id: str,
    format: str = "cdwc",  # NEW param
) -> None:
    """INSERT a new debate row."""
    db = await get_db()
    try:
        default_status = json.dumps({
            "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting", "pro_4": "waiting",
            "con_1": "waiting", "con_2": "waiting", "con_3": "waiting", "con_4": "waiting",
            "judge": "waiting",
        })
        await db.execute(
            """
            INSERT INTO debates (id, topic, total_rounds, format, pro_skills, con_skills,
                                 judge_skill, user_id, current_debater, debater_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?)
            """,
            (id, topic, total_rounds, format, json.dumps(pro_skills),
             json.dumps(con_skills), judge_skill, user_id, default_status),
        )
        await db.commit()
    finally:
        await db.close()
```

- [ ] **Step 3: Update insert_speech() to accept speech_type**

```python
async def insert_speech(
    debate_id: str,
    debater: str,
    phase: str,
    round_num: int,
    thinking: str | None,
    content: str,
    seq: int,
    speech_type: str = "opening",  # NEW param
) -> int:
    """INSERT a speech row.  Returns the auto-incremented id."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            INSERT INTO speeches (debate_id, debater, phase, round_num, thinking, content, seq, speech_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (debate_id, debater, phase, round_num, thinking, content, seq, speech_type),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()
```

- [ ] **Step 4: Run DB tests**

```bash
python -m pytest test_db.py -v
```

Expected: All DB tests pass.

- [ ] **Step 5: Commit**

```bash
git add db.py test_db.py
git commit -m "feat: migrate DB for CDWC — format, speech_type columns"
```

---

### Task 4: Rewrite debate_flow.py for CDWC 11-phase chain

**Files:**
- Create: `debate_flow_cdwc.py` (rewrite of debate_flow.py)
- Rename: `debate_flow.py` → `debate_flow_standard.py` (backup)

- [ ] **Step 1: Rename old flow file**

```bash
mv debate_flow.py debate_flow_standard.py
```

- [ ] **Step 2: Write new debate_flow.py — imports and class skeleton**

```python
"""
Debate Flow — CDWC (新国辩) format orchestration.

4 pro + 4 con + 1 judge.  11 phases: opening → rebuttal → cross-examine
→ cross-summary → free debate → closing → verdict.  Single round.
"""

from __future__ import annotations

import asyncio
import json
import os

from crewai import Task
from crewai.flow import Flow, listen, start

from models import (
    SSEPhaseStart,
    SSEPhaseEnd,
    SSEDebateEnd,
    SSEError,
    SSEVerdictChunk,
    SSESpeechChunk,
    SSEStateSnapshot,
    SSECrossQChunk,
    SSECrossAChunk,
    DebateState,
)
from sse_bridge import sse_bridge
from agents import (
    create_pro_agent,
    create_con_agent,
    create_judge_agent,
    PHASE_CONTEXT,
    set_current_thinking_debater,
    reset_current_thinking_debater,
    register_first_speech_callback,
    unregister_first_speech_callback,
)
from db import insert_speech, set_verdict

DB_PATH = os.environ.get("DEBATE_DB_PATH", "debate.db")

_active_flows: dict[str, "DebateFlow"] = {}
```

- [ ] **Step 3: Write DebateFlow class with helpers**

Same `__init__`, `_check_pause`, `_push_phase_start`, `_push_phase_end`, `_push_state_snapshot`, `_persist_speech`, `_run_agent_phase` as before, but update `_persist_speech` to accept `speech_type` and pass it to `insert_speech`:

```python
async def _persist_speech(
    self,
    debater: str,
    phase: str,
    thinking: str | None,
    content: str,
    speech_type: str = "opening",
) -> None:
    self._speech_seq += 1
    try:
        await insert_speech(
            debate_id=self.debate_id,
            debater=debater,
            phase=phase,
            round_num=self.state.current_round,
            thinking=thinking,
            content=content,
            seq=self._speech_seq,
            speech_type=speech_type,
        )
    except Exception as exc:
        print(f"[DB] Failed to persist speech: {exc}")
```

- [ ] **Step 4: Write cross_examine method**

```python
async def _cross_examine(
    self,
    examiner_key: str,
    phase: str,
    target_keys: list[str],
    examiner_agent,
    target_agents: dict[str, Agent],
    context: str,
) -> None:
    """Run CDWC cross-examination: examiner asks, target answers, up to 4 rounds.

    LLM autonomously ends by signaling (e.g. "感谢，质询到此结束").
    Max 4 rounds enforced.

    examiner_key: e.g. "pro_3"
    target_keys: e.g. ["con_1", "con_2"]
    examiner_agent: the asking agent
    target_agents: dict of {key: Agent} for targets
    """
    await self._check_pause()

    for key in self.state.debater_status:
        if self.state.debater_status[key] in ("thinking", "speaking"):
            self.state.debater_status[key] = "done"
    self.state.current_debater = examiner_key
    self.state.current_phase = phase
    self.state.cross_examine_round = 0

    self._push_phase_start(phase, examiner_key, self.state.current_round)
    self._push_state_snapshot()

    debate_context = f"\n\n辩题：{self.state.topic}"
    for entry in self.state.debate_history[-10:]:
        debate_context += (
            f"\n[{entry['debater']} - {entry['phase']}]:\n"
            f"{entry['content']}\n"
        )

    for rnd in range(1, 5):  # max 4 rounds
        self.state.cross_examine_round = rnd

        # --- Examiner asks ---
        self.state.debater_status[examiner_key] = "thinking"
        self._push_state_snapshot()

        q_context = f"{context}\n这是第{rnd}轮质询。{debate_context}"
        q_task = Task(
            description=PHASE_CONTEXT.get(phase, "") + q_context,
            expected_output="质询提问",
            agent=examiner_agent,
        )

        think_token = set_current_thinking_debater(self.debate_id, examiner_key)
        self.state.debater_status[examiner_key] = "speaking"
        try:
            result = await asyncio.to_thread(examiner_agent.execute_task, q_task)
            q_output = str(result) if result else ""
        except Exception as exc:
            sse_bridge.push(self.debate_id, SSEError(
                debate_id=self.debate_id,
                message=f"{examiner_key} 质询失败: {exc}",
            ))
            break
        finally:
            reset_current_thinking_debater(think_token)
            unregister_first_speech_callback(self.debate_id, examiner_key)

        sse_bridge.push(self.debate_id, SSECrossQChunk(
            debate_id=self.debate_id,
            examiner=examiner_key,
            target=" / ".join(target_keys),
            content=q_output,
            round=rnd,
        ))

        self.state.debate_history.append({
            "debater": examiner_key,
            "phase": phase,
            "round": self.state.current_round,
            "content": q_output,
        })
        await self._persist_speech(examiner_key, phase, None, q_output, speech_type="cross_q")

        # Check for LLM autonomous termination
        if "质询到此结束" in q_output or "质询结束" in q_output:
            break

        # --- Target answers ---
        # Ask target debater (rotate between targets)
        target_key = target_keys[(rnd - 1) % len(target_keys)]
        target_agent = target_agents.get(target_key)
        if not target_agent:
            continue

        self.state.debater_status[target_key] = "thinking"
        self._push_state_snapshot()

        a_context = (
            f"对方三辩向你提出了以下问题，请简短有力地回答：\n{q_output}\n\n"
            f"{debate_context}"
        )
        a_task = Task(
            description=(
                f"你是{'正方' if target_key.startswith('pro') else '反方'}辩手，"
                f"现在对方三辩正在向你质询。请简短有力地回答对方的问题。"
                + a_context
            ),
            expected_output="简短的回答",
            agent=target_agent,
        )

        think_token2 = set_current_thinking_debater(self.debate_id, target_key)
        self.state.debater_status[target_key] = "speaking"
        try:
            result = await asyncio.to_thread(target_agent.execute_task, a_task)
            a_output = str(result) if result else ""
        except Exception as exc:
            sse_bridge.push(self.debate_id, SSEError(
                debate_id=self.debate_id,
                message=f"{target_key} 回答失败: {exc}",
            ))
            continue
        finally:
            reset_current_thinking_debater(think_token2)
            unregister_first_speech_callback(self.debate_id, target_key)

        sse_bridge.push(self.debate_id, SSECrossAChunk(
            debate_id=self.debate_id,
            responder=target_key,
            content=a_output,
            round=rnd,
        ))

        self.state.debate_history.append({
            "debater": target_key,
            "phase": f"{phase}_response",
            "round": self.state.current_round,
            "content": a_output,
        })
        await self._persist_speech(target_key, phase + "_response", None, a_output, speech_type="cross_a")

    self.state.debater_status[examiner_key] = "done"
    self.state.current_debater = ""
    self._push_phase_end(phase, examiner_key)
    self._push_state_snapshot()
```

- [ ] **Step 5: Write 11 phase methods**

```python
class DebateFlow(Flow[DebateState]):
    """Orchestrates a CDWC-format debate (8 debaters + 1 judge)."""

    def __init__(self, debate_id: str, **kwargs):
        super().__init__(**kwargs)
        self.debate_id = debate_id
        self._speech_seq = 0
        _active_flows[debate_id] = self

    # ── helpers (same as standard, defined above) ──

    @start()
    async def begin_debate(self) -> None:
        self.state.current_phase = "begin"
        self.state.current_round = 1
        self.state.current_debater = ""
        self.state.debater_status = {
            "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting", "pro_4": "waiting",
            "con_1": "waiting", "con_2": "waiting", "con_3": "waiting", "con_4": "waiting",
            "judge": "waiting",
        }
        self._push_state_snapshot()

    @listen("begin_debate")
    async def pro_1_opening(self) -> str:
        agent = create_pro_agent(self.debate_id, 1, self.state.topic,
                                 self.state.pro_skills.get("debater_1"))
        return await self._run_agent_phase("pro_1", "pro_opening", agent,
            "请进行开篇立论。", speech_type="opening")

    @listen("pro_1_opening")
    async def con_1_opening(self) -> str:
        agent = create_con_agent(self.debate_id, 1, self.state.topic,
                                 self.state.con_skills.get("debater_1"))
        return await self._run_agent_phase("con_1", "con_opening", agent,
            "请进行开篇立论，并回应正方一辩的立论。", speech_type="opening")

    @listen("con_1_opening")
    async def pro_2_rebuttal(self) -> str:
        agent = create_pro_agent(self.debate_id, 2, self.state.topic,
                                 self.state.pro_skills.get("debater_2"))
        return await self._run_agent_phase("pro_2", "pro_rebuttal", agent,
            "请针对反方一辩的立论进行驳论。", speech_type="rebuttal")

    @listen("pro_2_rebuttal")
    async def con_2_rebuttal(self) -> str:
        agent = create_con_agent(self.debate_id, 2, self.state.topic,
                                 self.state.con_skills.get("debater_2"))
        return await self._run_agent_phase("con_2", "con_rebuttal", agent,
            "请针对正方二辩的驳论进行再反驳。", speech_type="rebuttal")

    @listen("con_2_rebuttal")
    async def pro_3_cross_examine(self) -> None:
        examiner = create_pro_agent(self.debate_id, 3, self.state.topic,
                                    self.state.pro_skills.get("debater_3"))
        targets = {
            "con_1": create_con_agent(self.debate_id, 1, self.state.topic,
                                      self.state.con_skills.get("debater_1")),
            "con_2": create_con_agent(self.debate_id, 2, self.state.topic,
                                      self.state.con_skills.get("debater_2")),
        }
        await self._cross_examine(
            "pro_3", "pro_cross_examine", ["con_1", "con_2"],
            examiner, targets,
            "请对反方一辩或二辩进行质询。",
        )

    @listen("pro_3_cross_examine")
    async def con_3_cross_examine(self) -> None:
        examiner = create_con_agent(self.debate_id, 3, self.state.topic,
                                    self.state.con_skills.get("debater_3"))
        targets = {
            "pro_1": create_pro_agent(self.debate_id, 1, self.state.topic,
                                      self.state.pro_skills.get("debater_1")),
            "pro_2": create_pro_agent(self.debate_id, 2, self.state.topic,
                                      self.state.pro_skills.get("debater_2")),
        }
        await self._cross_examine(
            "con_3", "con_cross_examine", ["pro_1", "pro_2"],
            examiner, targets,
            "请对正方一辩或二辩进行质询。",
        )

    @listen("con_3_cross_examine")
    async def pro_3_summary(self) -> str:
        agent = create_pro_agent(self.debate_id, 3, self.state.topic,
                                 self.state.pro_skills.get("debater_3"))
        return await self._run_agent_phase("pro_3", "pro_cross_summary", agent,
            "请进行质询小结。", speech_type="cross_summary")

    @listen("pro_3_summary")
    async def con_3_summary(self) -> str:
        agent = create_con_agent(self.debate_id, 3, self.state.topic,
                                 self.state.con_skills.get("debater_3"))
        return await self._run_agent_phase("con_3", "con_cross_summary", agent,
            "请进行质询小结。", speech_type="cross_summary")

    @listen("con_3_summary")
    async def free_debate(self) -> None:
        """Single-round free debate: 4 debaters per side, 3 exchanges each."""
        await self._check_pause()
        self.state.current_phase = "free_debate"

        for i in range(3):
            # Pro
            pro_pos = (i % 4) + 1
            pro_agent = create_pro_agent(
                self.debate_id, pro_pos, self.state.topic,
                self.state.pro_skills.get(f"debater_{pro_pos}"),
            )
            await self._run_agent_phase(
                f"pro_{pro_pos}", "free_debate", pro_agent,
                f"自由辩论第{i + 1}回合，请正方发言。",
                speech_type="free_debate",
            )

            # Con
            con_pos = (i % 4) + 1
            con_agent = create_con_agent(
                self.debate_id, con_pos, self.state.topic,
                self.state.con_skills.get(f"debater_{con_pos}"),
            )
            await self._run_agent_phase(
                f"con_{con_pos}", "free_debate", con_agent,
                f"自由辩论第{i + 1}回合，请反方回应。",
                speech_type="free_debate",
            )

    @listen("free_debate")
    async def con_4_closing(self) -> str:
        """反方四辩先总结（新国辩规则）."""
        agent = create_con_agent(self.debate_id, 4, self.state.topic,
                                 self.state.con_skills.get("debater_4"))
        return await self._run_agent_phase("con_4", "con_closing", agent,
            "请进行总结陈词，回顾整场辩论，总结反方核心立场。", speech_type="closing")

    @listen("con_4_closing")
    async def pro_4_closing(self) -> str:
        agent = create_pro_agent(self.debate_id, 4, self.state.topic,
                                 self.state.pro_skills.get("debater_4"))
        return await self._run_agent_phase("pro_4", "pro_closing", agent,
            "请进行总结陈词，回顾整场辩论，总结正方核心立场。", speech_type="closing")

    @listen("pro_4_closing")
    async def judge_verdict(self) -> None:
        """裁判评分 + 裁决 + 持久化（与旧版相同逻辑但使用5维度）."""
        # (same as old judge_verdict but with 5-dimension scores)
        await self._check_pause()
        self.state.current_phase = "verdict"
        self._push_phase_start("verdict", "judge", self.state.current_round)

        transcript = (
            f"# 辩论记录\n\n"
            f"辩题：{self.state.topic}\n"
            f"赛制：新国辩(CDWC)\n\n"
        )
        for entry in self.state.debate_history:
            transcript += (
                f"## [{entry['debater']}] {entry['phase']}\n{entry['content']}\n\n"
            )

        agent = create_judge_agent(self.debate_id, self.state.topic, self.state.judge_skill)

        task = Task(
            description=(
                PHASE_CONTEXT["verdict"] + f"\n\n辩题：{self.state.topic}\n\n{transcript}"
            ),
            expected_output="JSON格式的裁决结果",
            agent=agent,
        )

        try:
            result = await asyncio.to_thread(agent.execute_task, task)
            output = str(result) if result else "{}"
        except Exception as exc:
            sse_bridge.push(self.debate_id, SSEError(
                debate_id=self.debate_id, message=f"裁判裁决失败: {exc}",
            ))
            output = '{"winner": "draw", "pro_scores": {}, "con_scores": {}, "summary": "裁决失败"}'

        try:
            if "```json" in output:
                json_str = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                json_str = output.split("```")[1].split("```")[0].strip()
            else:
                json_str = output.strip()
            verdict = json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            verdict = {"winner": "draw", "pro_scores": {}, "con_scores": {}, "summary": output}

        winner = verdict.get("winner", "draw")
        await set_verdict(self.debate_id, winner, verdict)

        sse_bridge.push(self.debate_id, SSEVerdictChunk(
            debate_id=self.debate_id,
            content=verdict.get("summary", ""),
            scores=verdict,
        ))

        self._push_phase_end("verdict", "judge")
        self.state.verdict = verdict
        self.state.winner = winner
        sse_bridge.push(self.debate_id, SSEDebateEnd(debate_id=self.debate_id, verdict=verdict))
        _active_flows.pop(self.debate_id, None)
```

- [ ] **Step 6: Update _run_agent_phase to accept speech_type**

Add `speech_type: str = "opening"` parameter and pass it through to `_persist_speech`.

- [ ] **Step 7: Run flow tests**

```bash
python -m pytest test_debate_flow.py -v
```

Expected: Tests may need updating for new phase names (pro_argument → pro_cross_examine, pro_closing → con_4_closing+pro_4_closing). Update test assertions.

- [ ] **Step 8: Commit**

```bash
git add debate_flow.py debate_flow_standard.py test_debate_flow.py
git commit -m "feat: rewrite debate flow for CDWC 11-phase with cross-examination"
```

---

### Task 5: Update main.py for CDWC format routing

**Files:**
- Modify: `main.py:201-232`

- [ ] **Step 1: Update /api/debate/start to pass format to DB and Flow**

```python
@app.post("/api/debate/start")
async def start_debate(req: StartDebateRequest, current_user: dict = Depends(get_current_user)):
    """Create a new debate and launch the Flow in background."""
    debate_id = str(uuid.uuid4())

    await create_debate(
        id=debate_id,
        topic=req.topic,
        total_rounds=1 if req.format == "cdwc" else req.rounds,
        pro_skills=req.pro_skills.model_dump(),
        con_skills=req.con_skills.model_dump(),
        judge_skill=req.judge_skill,
        user_id=current_user["user_id"],
        format=req.format,
    )

    flow = DebateFlow(debate_id)
    flow.state.topic = req.topic
    flow.state.format = req.format
    flow.state.total_rounds = 1 if req.format == "cdwc" else req.rounds
    flow.state.pro_skills = req.pro_skills.model_dump()
    flow.state.con_skills = req.con_skills.model_dump()
    flow.state.judge_skill = req.judge_skill
    flow.state.id = debate_id

    _active_flows[debate_id] = flow
    asyncio.create_task(_run_debate(debate_id, flow))

    return StartDebateResponse(debate_id=debate_id, status="running")
```

- [ ] **Step 2: Run main tests**

```bash
python -m pytest test_main.py -v
```

Expected: Update test payloads to include `format: "cdwc"` and `debater_4` in skills.

- [ ] **Step 3: Commit**

```bash
git add main.py test_main.py
git commit -m "feat: add CDWC format routing to main.py"
```

---

### Task 6: Update Frontend — 4×2 Layout + Cross-Examination Panel

**Files:**
- Modify: `static/index.html`
- Modify: `static/js/app.js` (or embedded script)
- Modify: `static/styles.css`

- [ ] **Step 1: Update HTML grid to 4×2**

In `static/index.html`, change the debater grid to 4 rows:

```html
<div id="debate-grid" class="grid-4x2">
  <div id="card-pro-1" class="debater-card pro"><h3>正方一辩</h3><div class="status-badge">等待中</div><details><summary>思考过程</summary><div class="thinking"></div></details><div class="speech"></div></div>
  <div id="card-con-1" class="debater-card con"><h3>反方一辩</h3>...</div>
  <div id="card-pro-2" class="debater-card pro"><h3>正方二辩</h3>...</div>
  <div id="card-con-2" class="debater-card con"><h3>反方二辩</h3>...</div>
  <div id="card-pro-3" class="debater-card pro"><h3>正方三辩</h3>...</div>
  <div id="card-con-3" class="debater-card con"><h3>反方三辩</h3>...</div>
  <div id="card-pro-4" class="debater-card pro"><h3>正方四辩</h3>...</div>
  <div id="card-con-4" class="debater-card con"><h3>反方四辩</h3>...</div>
</div>
```

- [ ] **Step 2: Add cross-examination panel HTML**

```html
<div id="cross-examine-panel" class="cross-panel hidden">
  <div class="cross-examiner"><h3 id="cross-examiner-label"></h3><div id="cross-examiner-content"></div></div>
  <div class="cross-responder"><h3 id="cross-responder-label"></h3><div id="cross-responder-content"></div></div>
  <div class="cross-round"></div>
</div>
```

- [ ] **Step 3: Update CSS for 4×2 grid**

```css
.grid-4x2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(4, auto);
  gap: 16px;
}
```

- [ ] **Step 4: Add cross-examination panel CSS**

```css
.cross-panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  border: 2px solid #e5a100;
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
  background: #1a1a2e;
}
.cross-panel.hidden { display: none; }
.cross-examiner { border-right: 1px solid #444; padding-right: 16px; }
.cross-responder { padding-left: 16px; }
```

- [ ] **Step 5: Update JS to handle new SSE events**

In `static/js/app.js` or embedded script:
- Handle `cross_q_chunk` → populate examiner panel
- Handle `cross_a_chunk` → populate responder panel
- Show/hide cross-examination panel based on phase
- Update `debater_status` to handle pro_4/con_4
- Update skill selector dropdowns to include debater_4

- [ ] **Step 6: Update verdict display for 5 dimensions**

Add "质询有效性" column to the verdict score table.

- [ ] **Step 7: Verify frontend loads without errors**

```bash
# Start server and check console
python main.py &
curl http://localhost:8080/
```

- [ ] **Step 8: Commit**

```bash
git add static/index.html static/js/app.js static/styles.css
git commit -m "feat: upgrade frontend to 4×2 grid + cross-examination panel"
```

---

### Task 7: Update Tests for Full CDWC Flow

**Files:**
- Modify: `test_agents.py` (role count assertions)
- Modify: `test_debate_flow.py` (phase names, debater count)
- Modify: `test_main.py` (request payloads with format field)
- Modify: `test_models.py` (SkillConfig with debater_4)

- [ ] **Step 1: Run full test suite to identify all failures**

```bash
python -m pytest -v 2>&1 | grep "FAILED"
```

- [ ] **Step 2: Fix each failing test — update to CDWC expectations**

Key changes needed:
- Role count tests: 3 → 4 for pro/con
- Phase name updates: `pro_argument` → `pro_cross_examine` etc.
- Closing debaters: `pro_3`/`con_3` → `pro_4`/`con_4`
- SkillConfig object creation: add `debater_4` field
- StartDebateRequest: add `format: "cdwc"` field
- debater_status dicts: add `pro_4`/`con_4` keys
- Verdict score dimensions: 4 → 5 (add 质询有效性)

- [ ] **Step 3: Verify all tests pass**

```bash
python -m pytest -v
```

Expected: All tests green.

- [ ] **Step 4: Commit**

```bash
git add test_*.py
git commit -m "test: update all tests for CDWC 4v4 format"
```

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Start the server**

```bash
python main.py
```

- [ ] **Step 2: Send a CDWC debate start request**

```bash
curl -X POST http://localhost:8080/api/debate/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(curl -s -X POST http://localhost:8080/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"1234"}' | jq -r '.token')" \
  -d '{
    "topic": "人工智能是否威胁人类文明",
    "format": "cdwc",
    "rounds": 1,
    "pro_skills": {"debater_1": null, "debater_2": null, "debater_3": null, "debater_4": null},
    "con_skills": {"debater_1": null, "debater_2": null, "debater_3": null, "debater_4": null},
    "judge_skill": null
  }'
```

- [ ] **Step 3: Verify 11 phases execute in correct order via SSE stream**

- [ ] **Step 4: Verify cross-examination produces Q&A pairs (≤ 4 rounds)**

- [ ] **Step 5: Verify 5-dimension verdict JSON**

- [ ] **Step 6: Verify frontend 4×2 layout renders correctly**

- [ ] **Step 7: Commit any final fixes**

```bash
git add -A
git commit -m "fix: final CDWC end-to-end fixes"
```
