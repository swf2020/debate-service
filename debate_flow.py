"""
Debate Flow — CDWC (新国辩) format orchestration.

4 pro + 4 con + 1 judge.  12 phases: opening -> argument -> cross-examine
-> cross-summary -> free debate -> closing -> verdict.  Single round.
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
    SSECrossQChunk,
    SSECrossAChunk,
    SSEStateSnapshot,
    SSEDebaterStatusChange,
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
    set_current_role,
    reset_current_role,
    get_and_clear_thinking,
    register_speech_chunk_callback,
    unregister_speech_chunk_callback,
)
from db import insert_speech, update_speech_content, set_verdict
from redis_cache import get_redis

DB_PATH = os.environ.get("DEBATE_DB_PATH", "debate.db")

_active_flows: dict[str, "DebateFlow"] = {}

# Per-debater partial speech buffer for real-time DB persistence.
# Key: "{debate_id}:{debater_key}" -> list[str] of accumulated chunks.
_partial_buffers: dict[str, list[str]] = {}


class DebateFlow(Flow[DebateState]):
    """Orchestrates a CDWC-format debate (8 debaters + 1 judge)."""

    def __init__(self, debate_id: str, **kwargs):
        super().__init__(**kwargs)
        self.debate_id = debate_id
        self._speech_seq = 0
        _active_flows[debate_id] = self

    # -- helpers ----------------------------------------------------------

    async def _check_pause(self) -> None:
        """Block while self.state.paused is True, polling every 0.5 s."""
        while self.state.paused:
            await asyncio.sleep(0.5)

    def _push_phase_start(self, phase: str, debater: str, round_num: int) -> None:
        role_id = f"{debater}:{phase}"
        sse_bridge.push(
            self.debate_id,
            SSEPhaseStart(
                debate_id=self.debate_id,
                phase=phase,
                debater=debater,
                round_num=round_num,
                role_id=role_id,
            ),
        )

    def _push_phase_end(self, phase: str, debater: str) -> None:
        sse_bridge.push(
            self.debate_id,
            SSEPhaseEnd(
                debate_id=self.debate_id,
                phase=phase,
                debater=debater,
            ),
        )

    def _push_state_snapshot(self) -> None:
        """Push debater status snapshot to frontend."""
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
                cross_examine_examiner=self.state.cross_examine_examiner,
                cross_examine_target=self.state.cross_examine_target,
            ),
        )

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

    async def _run_agent_phase(
        self,
        debater_key: str,
        phase: str,
        agent,
        context: str,
        speech_type: str = "opening",
    ) -> str:
        """Run a single agent phase end-to-end.

        1. Check pause
        2. Update state tracking (current_debater, debater_status)
        3. Push ``phase_start`` and ``state_snapshot`` SSE events
        4. Build a ``Task`` with debate history as context
        5. Execute agent in a thread pool (``agent.execute_task`` is sync)
        6. Push ``phase_end`` SSE event
        7. Append to ``debate_history``
        8. Persist speech to SQLite

        Returns the agent's output string.
        """
        await self._check_pause()

        # Clear any stale thinking/speaking status from other debaters
        for key in self.state.debater_status:
            if key != debater_key and self.state.debater_status[key] in ("thinking", "speaking"):
                self.state.debater_status[key] = "done"

        self.state.current_phase = phase
        self.state.current_debater = debater_key
        self.state.debater_status[debater_key] = "thinking"
        self._push_phase_start(phase, debater_key, self.state.current_round)
        self._push_state_snapshot()

        # Build task description with full context
        task_description = PHASE_CONTEXT.get(phase, "")
        task_description += f"\n\n辩题：{self.state.topic}"

        if self.state.debate_history:
            task_description += "\n\n## 之前的辩论记录\n"
            for entry in self.state.debate_history[-10:]:
                task_description += (
                    f"\n[{entry['debater']} - {entry['phase']}]:\n"
                    f"{entry['content']}\n"
                )

        task_description += f"\n\n{context}"

        task = Task(
            description=task_description,
            expected_output="你的发言内容",
            agent=agent,
        )

        self.state.debater_status[debater_key] = "speaking"
        self._push_state_snapshot()

        role_id = f"{debater_key}:{phase}"
        role_token = set_current_role(phase, role_id)

        # ── Real-time DB persistence setup ──
        buffer_key = f"{self.debate_id}:{debater_key}"
        _partial_buffers[buffer_key] = []
        speech_id = await insert_speech(
            debate_id=self.debate_id,
            debater=debater_key,
            phase=phase,
            round_num=self.state.current_round,
            thinking=None,
            content="",
            seq=self._speech_seq + 1,
            speech_type=speech_type,
        )
        self._speech_seq += 1

        def on_chunk(chunk: str) -> None:
            buf = _partial_buffers.get(buffer_key)
            if buf is not None:
                buf.append(chunk)
        register_speech_chunk_callback(self.debate_id, debater_key, on_chunk)

        async def flush_loop():
            while True:
                await asyncio.sleep(0.5)
                buf = _partial_buffers.get(buffer_key)
                if buf:
                    try:
                        await update_speech_content(speech_id, content="".join(buf))
                    except Exception:
                        pass

        flush_task = asyncio.create_task(flush_loop())

        try:
            try:
                try:
                    token = set_current_thinking_debater(self.debate_id, debater_key)
                    try:
                        result = await asyncio.to_thread(agent.execute_task, task)
                        output = str(result) if result else ""
                    finally:
                        reset_current_thinking_debater(token)
                except Exception as exc:
                    sse_bridge.push(
                        self.debate_id,
                        SSEError(
                            debate_id=self.debate_id,
                            message=f"{debater_key} 执行失败: {exc}",
                        ),
                    )
                    output = f"[错误] {debater_key} 发言失败"
            finally:
                reset_current_role(role_token)
        finally:
            flush_task.cancel()
            unregister_speech_chunk_callback(self.debate_id, debater_key)
            _partial_buffers.pop(buffer_key, None)

        self._push_phase_end(phase, debater_key)

        self.state.debate_history.append(
            {
                "debater": debater_key,
                "phase": phase,
                "round": self.state.current_round,
                "content": output,
            }
        )

        self.state.debater_status[debater_key] = "done"
        self.state.current_debater = ""
        self._push_state_snapshot()

        thinking = get_and_clear_thinking(self.debate_id, debater_key)
        try:
            await update_speech_content(speech_id, content=output, thinking=thinking)
        except Exception as exc:
            print(f"[DB] Failed to persist speech: {exc}")
        return output

    async def _cross_examine(
        self,
        examiner_key: str,
        phase: str,
        target_keys: list[str],
        make_examiner: callable,
        make_targets: dict[str, callable],
        context: str,
    ) -> None:
        """Run CDWC cross-examination: examiner asks, target answers, up to 4 rounds.

        Creates fresh agents per round (aligns with _run_agent_phase pattern).
        LLM autonomously ends by signaling (e.g. "感谢，质询到此结束").
        Max 4 rounds enforced.
        """
        await self._check_pause()

        for key in self.state.debater_status:
            if self.state.debater_status[key] in ("thinking", "speaking"):
                self.state.debater_status[key] = "done"

        self.state.current_debater = examiner_key
        self.state.current_phase = phase
        self.state.cross_examine_round = 0

        # Build debate context for both sides
        debate_context = f"\n\n辩题：{self.state.topic}"
        for entry in self.state.debate_history[-10:]:
            debate_context += (
                f"\n[{entry['debater']} - {entry['phase']}]:\n"
                f"{entry['content']}\n"
            )

        response_phase = f"{phase}_response"
        answered_targets: set[str] = set()

        for rnd in range(1, 5):
            await self._check_pause()
            self.state.cross_examine_round = rnd

            # Create fresh agents per round (avoids crewAI state corruption from reuse)
            examiner_agent = make_examiner()
            target_key = target_keys[(rnd - 1) % len(target_keys)]
            target_agent = make_targets.get(target_key, lambda: None)()

            # --- Examiner asks ---
            self.state.debater_status[examiner_key] = "thinking"
            self.state.current_debater = examiner_key
            self.state.cross_examine_examiner = examiner_key
            self._push_phase_start(phase, examiner_key, self.state.current_round)
            self._push_state_snapshot()

            q_context = f"{context}\n这是第{rnd}轮质询。{debate_context}"
            q_task = Task(
                description=PHASE_CONTEXT.get(phase, "") + q_context,
                expected_output="质询提问",
                agent=examiner_agent,
            )

            self.state.debater_status[examiner_key] = "speaking"
            self._push_state_snapshot()
            sse_bridge.push(self.debate_id, SSEDebaterStatusChange(
                debate_id=self.debate_id,
                debater=examiner_key,
                status="speaking",
            ))

            role_id = f"{examiner_key}:{phase}"
            role_token = set_current_role(phase, role_id)

            # ── Real-time DB persistence for cross-Q ──
            q_buffer_key = f"{self.debate_id}:{examiner_key}"
            _partial_buffers[q_buffer_key] = []
            q_speech_id = await insert_speech(
                debate_id=self.debate_id,
                debater=examiner_key,
                phase=phase,
                round_num=self.state.current_round,
                thinking=None,
                content="",
                seq=self._speech_seq + 1,
                speech_type="cross_q",
            )
            self._speech_seq += 1

            def on_q_chunk(chunk: str) -> None:
                buf = _partial_buffers.get(q_buffer_key)
                if buf is not None:
                    buf.append(chunk)
            register_speech_chunk_callback(self.debate_id, examiner_key, on_q_chunk)

            async def q_flush_loop():
                while True:
                    await asyncio.sleep(0.5)
                    buf = _partial_buffers.get(q_buffer_key)
                    if buf:
                        try:
                            await update_speech_content(q_speech_id, content="".join(buf))
                        except Exception:
                            pass

            q_flush_task = asyncio.create_task(q_flush_loop())

            try:
                try:
                    try:
                        token = set_current_thinking_debater(self.debate_id, examiner_key)
                        try:
                            result = await asyncio.wait_for(
                                asyncio.to_thread(examiner_agent.execute_task, q_task),
                                timeout=300,
                            )
                            q_output = str(result) if result else ""
                        finally:
                            reset_current_thinking_debater(token)
                    except Exception as exc:
                        sse_bridge.push(
                            self.debate_id,
                            SSEError(
                                debate_id=self.debate_id,
                                message=f"{examiner_key} 质询失败: {exc}",
                            ),
                        )
                        break
                finally:
                    reset_current_role(role_token)
            finally:
                q_flush_task.cancel()
                try:
                    await q_flush_task
                except asyncio.CancelledError:
                    pass
                unregister_speech_chunk_callback(self.debate_id, examiner_key)
                _partial_buffers.pop(q_buffer_key, None)

            sse_bridge.push(
                self.debate_id,
                SSECrossQChunk(
                    debate_id=self.debate_id,
                    examiner=examiner_key,
                    target=" / ".join(target_keys),
                    content=q_output,
                    round=rnd,
                ),
            )

            self.state.debate_history.append(
                {
                    "debater": examiner_key,
                    "phase": phase,
                    "round": self.state.current_round,
                    "content": q_output,
                }
            )
            q_thinking = get_and_clear_thinking(self.debate_id, examiner_key)
            try:
                await update_speech_content(q_speech_id, content=q_output, thinking=q_thinking)
            except Exception as exc:
                print(f"[DB] Failed to persist cross-Q speech: {exc}")

            # --- Target answers ---
            if not target_agent:
                continue
            answered_targets.add(target_key)

            self.state.debater_status[target_key] = "thinking"
            self.state.current_debater = target_key
            self.state.cross_examine_target = target_key
            self.state.current_phase = response_phase
            self._push_phase_start(response_phase, target_key, self.state.current_round)
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

            self.state.debater_status[target_key] = "speaking"
            self._push_state_snapshot()
            sse_bridge.push(self.debate_id, SSEDebaterStatusChange(
                debate_id=self.debate_id,
                debater=target_key,
                status="speaking",
            ))

            resp_role_id = f"{target_key}:{response_phase}"
            resp_role_token = set_current_role(response_phase, resp_role_id)

            # ── Real-time DB persistence for cross-A ──
            a_buffer_key = f"{self.debate_id}:{target_key}"
            _partial_buffers[a_buffer_key] = []
            a_speech_id = await insert_speech(
                debate_id=self.debate_id,
                debater=target_key,
                phase=phase + "_response",
                round_num=self.state.current_round,
                thinking=None,
                content="",
                seq=self._speech_seq + 1,
                speech_type="cross_a",
            )
            self._speech_seq += 1

            def on_a_chunk(chunk: str) -> None:
                buf = _partial_buffers.get(a_buffer_key)
                if buf is not None:
                    buf.append(chunk)
            register_speech_chunk_callback(self.debate_id, target_key, on_a_chunk)

            async def a_flush_loop():
                while True:
                    await asyncio.sleep(0.5)
                    buf = _partial_buffers.get(a_buffer_key)
                    if buf:
                        try:
                            await update_speech_content(a_speech_id, content="".join(buf))
                        except Exception:
                            pass

            a_flush_task = asyncio.create_task(a_flush_loop())

            try:
                try:
                    try:
                        token = set_current_thinking_debater(self.debate_id, target_key)
                        try:
                            result = await asyncio.wait_for(
                                asyncio.to_thread(target_agent.execute_task, a_task),
                                timeout=300,
                            )
                            a_output = str(result) if result else ""
                        finally:
                            reset_current_thinking_debater(token)
                    except Exception as exc:
                        sse_bridge.push(
                            self.debate_id,
                            SSEError(
                                debate_id=self.debate_id,
                                message=f"{target_key} 回答失败: {exc}",
                            ),
                        )
                        continue
                finally:
                    reset_current_role(resp_role_token)
            finally:
                a_flush_task.cancel()
                try:
                    await a_flush_task
                except asyncio.CancelledError:
                    pass
                unregister_speech_chunk_callback(self.debate_id, target_key)
                _partial_buffers.pop(a_buffer_key, None)

            sse_bridge.push(
                self.debate_id,
                SSECrossAChunk(
                    debate_id=self.debate_id,
                    responder=target_key,
                    content=a_output,
                    round=rnd,
                    role_id=resp_role_id,
                ),
            )

            self.state.debate_history.append(
                {
                    "debater": target_key,
                    "phase": f"{phase}_response",
                    "round": self.state.current_round,
                    "content": a_output,
                }
            )
            a_thinking = get_and_clear_thinking(self.debate_id, target_key)
            try:
                await update_speech_content(a_speech_id, content=a_output, thinking=a_thinking)
            except Exception as exc:
                print(f"[DB] Failed to persist cross-A speech: {exc}")

            self.state.debater_status[target_key] = "done"

            # Restore phase context after target answers
            self.state.current_phase = phase

            # Only allow termination after all targets have answered at least once
            if len(answered_targets) >= len(target_keys):
                if "质询到此结束" in q_output or "质询结束" in q_output:
                    break

        # Cleanup
        self.state.debater_status[examiner_key] = "done"
        self.state.current_debater = ""
        self.state.cross_examine_examiner = ""
        self.state.cross_examine_target = ""
        self._push_phase_end(phase, examiner_key)
        self._push_state_snapshot()

    # -- CDWC phase chain (correct order per 新国辩 rules) ----------------

    @start()
    async def begin_debate(self) -> None:
        """Initialize debate state -- round = 1, phase = begin."""
        self.state.current_phase = "begin"
        self.state.current_round = 1
        self.state.current_debater = ""
        self.state.debater_status = {
            "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting", "pro_4": "waiting",
            "con_1": "waiting", "con_2": "waiting", "con_3": "waiting", "con_4": "waiting",
            "judge": "waiting",
        }
        self._push_state_snapshot()

    # ── 立论环节 ──────────────────────────────────────────────────────

    @listen("begin_debate")
    async def pro_1_opening(self) -> str:
        """正方一辩 -- 开篇立论."""
        agent = create_pro_agent(
            self.debate_id, 1, self.state.topic,
            self.state.pro_skills.get("debater_1"),
            phase="pro_opening",
        )
        return await self._run_agent_phase(
            "pro_1", "pro_opening", agent, "请进行开篇立论。",
            speech_type="opening",
        )

    @listen("pro_1_opening")
    async def con_1_opening(self) -> str:
        """反方一辩 -- 开篇立论."""
        agent = create_con_agent(
            self.debate_id, 1, self.state.topic,
            self.state.con_skills.get("debater_1"),
            phase="con_opening",
        )
        return await self._run_agent_phase(
            "con_1", "con_opening", agent,
            "请进行开篇立论，并回应正方一辩的立论。",
            speech_type="opening",
        )

    # ── 申论环节（反方先发言）──────────────────────────────────────────

    @listen("con_1_opening")
    async def con_2_argument(self) -> str:
        """反方二辩 -- 申论（深化反方论证）."""
        agent = create_con_agent(
            self.debate_id, 2, self.state.topic,
            self.state.con_skills.get("debater_2"),
            phase="con_argument",
        )
        return await self._run_agent_phase(
            "con_2", "con_argument", agent,
            "请在反方一辩立论框架基础上，选择核心论点进行深入展开。",
            speech_type="argument",
        )

    @listen("con_2_argument")
    async def pro_2_argument(self) -> str:
        """正方二辩 -- 申论（深化正方论证，回应反方申论）."""
        agent = create_pro_agent(
            self.debate_id, 2, self.state.topic,
            self.state.pro_skills.get("debater_2"),
            phase="pro_argument",
        )
        return await self._run_agent_phase(
            "pro_2", "pro_argument", agent,
            "请深化正方论证，同时回应反方二辩的申论。",
            speech_type="argument",
        )

    # ── 质询环节 ──────────────────────────────────────────────────────

    @listen("pro_2_argument")
    async def pro_3_cross_examine(self) -> None:
        """正方三辩 -- 对反方二/三辩进行质询."""
        await self._cross_examine(
            "pro_3", "pro_cross_examine", ["con_2", "con_3"],
            make_examiner=lambda: create_pro_agent(
                self.debate_id, 3, self.state.topic,
                self.state.pro_skills.get("debater_3"),
                phase="pro_cross_examine",
            ),
            make_targets={
                "con_2": lambda: create_con_agent(
                    self.debate_id, 2, self.state.topic,
                    self.state.con_skills.get("debater_2"),
                    phase="pro_cross_examine_response",
                ),
                "con_3": lambda: create_con_agent(
                    self.debate_id, 3, self.state.topic,
                    self.state.con_skills.get("debater_3"),
                    phase="pro_cross_examine_response",
                ),
            },
            context="请对反方二辩或三辩进行质询。",
        )

    @listen("pro_3_cross_examine")
    async def con_3_cross_examine(self) -> None:
        """反方三辩 -- 对正方二/三辩进行质询."""
        await self._cross_examine(
            "con_3", "con_cross_examine", ["pro_2", "pro_3"],
            make_examiner=lambda: create_con_agent(
                self.debate_id, 3, self.state.topic,
                self.state.con_skills.get("debater_3"),
                phase="con_cross_examine",
            ),
            make_targets={
                "pro_2": lambda: create_pro_agent(
                    self.debate_id, 2, self.state.topic,
                    self.state.pro_skills.get("debater_2"),
                    phase="con_cross_examine_response",
                ),
                "pro_3": lambda: create_pro_agent(
                    self.debate_id, 3, self.state.topic,
                    self.state.pro_skills.get("debater_3"),
                    phase="con_cross_examine_response",
                ),
            },
            context="请对正方二辩或三辩进行质询。",
        )

    # ── 质询小结（反方先发言）──────────────────────────────────────────

    @listen("con_3_cross_examine")
    async def con_3_summary(self) -> str:
        """反方三辩 -- 质询小结."""
        agent = create_con_agent(
            self.debate_id, 3, self.state.topic,
            self.state.con_skills.get("debater_3"),
            phase="con_cross_summary",
        )
        return await self._run_agent_phase(
            "con_3", "con_cross_summary", agent,
            "请进行质询小结，总结质询中暴露的正方论证问题。",
            speech_type="cross_summary",
        )

    @listen("con_3_summary")
    async def pro_3_summary(self) -> str:
        """正方三辩 -- 质询小结."""
        agent = create_pro_agent(
            self.debate_id, 3, self.state.topic,
            self.state.pro_skills.get("debater_3"),
            phase="pro_cross_summary",
        )
        return await self._run_agent_phase(
            "pro_3", "pro_cross_summary", agent,
            "请进行质询小结，总结质询中暴露的反方论证问题。",
            speech_type="cross_summary",
        )

    # ── 自由辩论（正方先发言，双方交替，辩手次序不限，4轮）─────────────

    @listen("pro_3_summary")
    async def free_debate(self) -> None:
        """自由辩论：正方先发言，双方交替，4轮。8位辩手均可参与。"""
        await self._check_pause()
        self.state.current_phase = "free_debate"

        for i in range(4):
            # Pro speaks first each round
            pro_pos = (i % 4) + 1
            pro_agent = create_pro_agent(
                self.debate_id, pro_pos, self.state.topic,
                self.state.pro_skills.get(f"debater_{pro_pos}"),
                phase="free_debate",
            )
            await self._run_agent_phase(
                f"pro_{pro_pos}", "free_debate", pro_agent,
                f"自由辩论第{i + 1}回合，请正方发言。",
                speech_type="free_debate",
            )

            # Con responds
            con_pos = (i % 4) + 1
            con_agent = create_con_agent(
                self.debate_id, con_pos, self.state.topic,
                self.state.con_skills.get(f"debater_{con_pos}"),
                phase="free_debate",
            )
            await self._run_agent_phase(
                f"con_{con_pos}", "free_debate", con_agent,
                f"自由辩论第{i + 1}回合，请反方回应。",
                speech_type="free_debate",
            )

    # ── 总结陈词（反方先发言）──────────────────────────────────────────

    @listen("free_debate")
    async def con_4_closing(self) -> str:
        """反方四辩先总结（新国辩规则）."""
        agent = create_con_agent(
            self.debate_id, 4, self.state.topic,
            self.state.con_skills.get("debater_4"),
            phase="con_closing",
        )
        return await self._run_agent_phase(
            "con_4", "con_closing", agent,
            "请进行总结陈词，回顾整场辩论，总结反方核心立场。",
            speech_type="closing",
        )

    @listen("con_4_closing")
    async def pro_4_closing(self) -> str:
        """正方四辩最后总结."""
        agent = create_pro_agent(
            self.debate_id, 4, self.state.topic,
            self.state.pro_skills.get("debater_4"),
            phase="pro_closing",
        )
        return await self._run_agent_phase(
            "pro_4", "pro_closing", agent,
            "请进行总结陈词，回顾整场辩论，总结正方核心立场，并回应反方四辩的总结。",
            speech_type="closing",
        )

    # ── 裁判裁决 ──────────────────────────────────────────────────────

    @listen("pro_4_closing")
    async def judge_verdict(self) -> None:
        """裁判评分 + 裁决 + 持久化."""
        await self._check_pause()

        self.state.current_phase = "verdict"
        self.state.debater_status["judge"] = "thinking"
        self._push_phase_start("verdict", "judge", self.state.current_round)
        self._push_state_snapshot()

        # Build full transcript
        transcript = (
            f"# 辩论记录\n\n"
            f"辩题：{self.state.topic}\n"
            f"赛制：新国辩(CDWC)\n\n"
        )
        for entry in self.state.debate_history:
            transcript += (
                f"## [{entry['debater']}] {entry['phase']}\n{entry['content']}\n\n"
            )

        agent = create_judge_agent(
            self.debate_id, self.state.topic, self.state.judge_skill,
            phase="verdict",
        )

        task = Task(
            description=(
                PHASE_CONTEXT["verdict"]
                + f"\n\n辩题：{self.state.topic}\n\n{transcript}"
            ),
            expected_output="JSON格式的裁决结果",
            agent=agent,
        )

        self.state.debater_status["judge"] = "speaking"
        self._push_state_snapshot()

        role_token = set_current_role("verdict", "judge:verdict")
        try:
            try:
                result = await asyncio.to_thread(agent.execute_task, task)
                output = str(result) if result else "{}"
            except Exception as exc:
                sse_bridge.push(
                    self.debate_id,
                    SSEError(
                        debate_id=self.debate_id,
                        message=f"裁判裁决失败: {exc}",
                    ),
                )
                output = (
                    '{"winner": "draw", "pro_scores": {},'
                    ' "con_scores": {}, "summary": "裁决失败"}'
                )
        finally:
            reset_current_role(role_token)

        # --- Parse JSON from LLM output ---
        try:
            if "```json" in output:
                json_str = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                json_str = output.split("```")[1].split("```")[0].strip()
            else:
                json_str = output.strip()
            verdict = json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            verdict = {
                "winner": "draw",
                "pro_scores": {},
                "con_scores": {},
                "summary": output,
            }

        winner = verdict.get("winner", "draw")

        # Persist
        await set_verdict(self.debate_id, winner, verdict)

        # Cache verdict to Redis for instant replay
        try:
            cache = get_redis()
            await cache.cache_verdict(self.debate_id, verdict, winner)
        except Exception:
            pass  # Cache write failure is non-fatal

        sse_bridge.push(
            self.debate_id,
            SSEVerdictChunk(
                debate_id=self.debate_id,
                content=verdict.get("summary", ""),
                scores=verdict,
            ),
        )

        self._push_phase_end("verdict", "judge")
        self.state.verdict = verdict
        self.state.winner = winner
        self.state.debater_status["judge"] = "done"
        self._push_state_snapshot()

        sse_bridge.push(
            self.debate_id,
            SSEDebateEnd(debate_id=self.debate_id, verdict=verdict),
        )

        _active_flows.pop(self.debate_id, None)
