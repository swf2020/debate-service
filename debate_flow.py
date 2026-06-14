"""
Debate Flow — core orchestration for the debate service.

Uses crewAI's Flow DSL to chain: begin_debate -> pro_1_opening -> con_1_opening
-> pro_2_rebuttal -> con_2_rebuttal -> pro_3_argument -> con_3_argument
-> free_debate (handles rounds 1..N internally) -> pro_3_closing
-> con_3_closing -> judge_verdict.

Each phase pushes SSE events via the thread-safe SSEBridge, persists
speeches to SQLite, and respects the pause/resume flag in DebateState.
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
    DebateState,
)
from sse_bridge import sse_bridge
from agents import (
    create_pro_agent,
    create_con_agent,
    create_judge_agent,
    PHASE_CONTEXT,
)
from db import insert_speech, set_verdict

DB_PATH = os.environ.get("DEBATE_DB_PATH", "debate.db")

# Module-level registry so main.py can locate flows for pause / resume.
_active_flows: dict[str, "DebateFlow"] = {}


class DebateFlow(Flow[DebateState]):
    """Orchestrates a full Chinese-style debate (6 debaters + 1 judge)."""

    def __init__(self, debate_id: str, **kwargs):
        super().__init__(**kwargs)
        self.debate_id = debate_id
        self._speech_seq = 0
        _active_flows[debate_id] = self

    # ── helpers ──────────────────────────────────────────────────────────

    async def _check_pause(self) -> None:
        """Block while ``self.state.paused`` is True, polling every 0.5 s."""
        while self.state.paused:
            await asyncio.sleep(0.5)

    def _push_phase_start(self, phase: str, debater: str, round_num: int) -> None:
        sse_bridge.push(
            self.debate_id,
            SSEPhaseStart(
                debate_id=self.debate_id,
                phase=phase,
                debater=debater,
                round_num=round_num,
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

    async def _persist_speech(
        self,
        debater: str,
        phase: str,
        thinking: str | None,
        content: str,
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
            )
        except Exception as exc:
            print(f"[DB] Failed to persist speech: {exc}")

    async def _run_agent_phase(
        self,
        debater_key: str,
        phase: str,
        agent,
        context: str,
    ) -> str:
        """Run a single agent phase end-to-end.

        1. Check pause
        2. Push ``phase_start`` SSE event
        3. Build a ``Task`` with debate history as context
        4. Execute agent in a thread pool (``agent.execute_task`` is sync)
        5. Push ``phase_end`` SSE event
        6. Append to ``debate_history``
        7. Persist speech to SQLite

        Returns the agent's output string.
        """
        await self._check_pause()

        self.state.current_phase = phase
        self._push_phase_start(phase, debater_key, self.state.current_round)

        # Build task description with full context
        task_description = PHASE_CONTEXT.get(phase, "")
        task_description += f"\n\n辩题：{self.state.topic}"
        task_description += f"\n\n当前轮次：第{self.state.current_round}轮"

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

        try:
            result = await asyncio.to_thread(agent.execute_task, task)
            output = str(result) if result else ""
        except Exception as exc:
            sse_bridge.push(
                self.debate_id,
                SSEError(
                    debate_id=self.debate_id,
                    message=f"{debater_key} 执行失败: {exc}",
                ),
            )
            output = f"[错误] {debater_key} 发言失败"

        # Speech chunks are streamed in real-time by the LLM streaming hook
        # installed in agents._install_stream_hook — no post-hoc chunking needed.

        self._push_phase_end(phase, debater_key)

        self.state.debate_history.append(
            {
                "debater": debater_key,
                "phase": phase,
                "round": self.state.current_round,
                "content": output,
            }
        )

        await self._persist_speech(debater_key, phase, None, output)
        return output

    # ── Flow phase methods (linear chain, no or_ / cyclic routing) ──────

    @start()
    async def begin_debate(self) -> None:
        """Initialize debate state — round = 1, phase = begin."""
        self.state.current_phase = "begin"
        self.state.current_round = 1

    @listen("begin_debate")
    async def pro_1_opening(self) -> str:
        """正方一辩 — 开篇立论."""
        agent = create_pro_agent(
            self.debate_id, 1, self.state.topic,
            self.state.pro_skills.get("debater_1"),
        )
        return await self._run_agent_phase(
            "pro_1", "pro_opening", agent, "请进行开篇立论。"
        )

    @listen("pro_1_opening")
    async def con_1_opening(self) -> str:
        """反方一辩 — 开篇立论."""
        agent = create_con_agent(
            self.debate_id, 1, self.state.topic,
            self.state.con_skills.get("debater_1"),
        )
        return await self._run_agent_phase(
            "con_1", "con_opening", agent,
            "请进行开篇立论，并回应正方一辩的立论。"
        )

    @listen("con_1_opening")
    async def pro_2_rebuttal(self) -> str:
        """正方二辩 — 驳论."""
        agent = create_pro_agent(
            self.debate_id, 2, self.state.topic,
            self.state.pro_skills.get("debater_2"),
        )
        return await self._run_agent_phase(
            "pro_2", "pro_rebuttal", agent,
            "请针对反方一辩的立论进行驳论。"
        )

    @listen("pro_2_rebuttal")
    async def con_2_rebuttal(self) -> str:
        """反方二辩 — 驳论."""
        agent = create_con_agent(
            self.debate_id, 2, self.state.topic,
            self.state.con_skills.get("debater_2"),
        )
        return await self._run_agent_phase(
            "con_2", "con_rebuttal", agent,
            "请针对正方二辩的驳论进行再反驳。"
        )

    @listen("con_2_rebuttal")
    async def pro_3_argument(self) -> str:
        """正方三辩 — 深入论证."""
        agent = create_pro_agent(
            self.debate_id, 3, self.state.topic,
            self.state.pro_skills.get("debater_3"),
        )
        return await self._run_agent_phase(
            "pro_3", "pro_argument", agent,
            "请进行深入论证。"
        )

    @listen("pro_3_argument")
    async def con_3_argument(self) -> str:
        """反方三辩 — 深入论证."""
        agent = create_con_agent(
            self.debate_id, 3, self.state.topic,
            self.state.con_skills.get("debater_3"),
        )
        return await self._run_agent_phase(
            "con_3", "con_argument", agent,
            "请进行深入论证。"
        )

    @listen("con_3_argument")
    async def free_debate(self) -> None:
        """自由辩论 + inner-round loop.

        Runs 3 pro/con alternating exchanges per round.  After the free
        debate, increments ``current_round``.  If more rounds remain,
        re-runs the round body (pro_2 rebuttal through con_3 argument)
        via direct ``_run_agent_phase`` calls, then loops again.

        This avoids complex ``or_()`` / cyclic Flow DSL routing that has
        known issues with ``_fired_or_listeners`` suppression.
        """
        while True:
            await self._check_pause()
            self.state.current_phase = "free_debate"

            # ---- free debate exchanges (3 turns) ----
            for i in range(3):
                # Pro
                pro_pos = (i % 3) + 1
                pro_agent = create_pro_agent(
                    self.debate_id, pro_pos, self.state.topic,
                    self.state.pro_skills.get(f"debater_{pro_pos}"),
                )
                await self._run_agent_phase(
                    f"pro_{pro_pos}", "free_debate", pro_agent,
                    f"自由辩论第{i + 1}回合，请正方发言。",
                )

                # Con
                con_pos = (i % 3) + 1
                con_agent = create_con_agent(
                    self.debate_id, con_pos, self.state.topic,
                    self.state.con_skills.get(f"debater_{con_pos}"),
                )
                await self._run_agent_phase(
                    f"con_{con_pos}", "free_debate", con_agent,
                    f"自由辩论第{i + 1}回合，请反方回应。",
                )

            # ---- check for more rounds ----
            self.state.current_round += 1
            if self.state.current_round > self.state.total_rounds:
                break

            # ---- re-run round body for next round ----
            # pro_2 rebuttal
            agent = create_pro_agent(
                self.debate_id, 2, self.state.topic,
                self.state.pro_skills.get("debater_2"),
            )
            await self._run_agent_phase(
                "pro_2", "pro_rebuttal", agent,
                "请针对反方在这一轮的发言进行驳论。",
            )

            # con_2 rebuttal
            agent = create_con_agent(
                self.debate_id, 2, self.state.topic,
                self.state.con_skills.get("debater_2"),
            )
            await self._run_agent_phase(
                "con_2", "con_rebuttal", agent,
                "请针对正方二辩的驳论进行再反驳。",
            )

            # pro_3 argument
            agent = create_pro_agent(
                self.debate_id, 3, self.state.topic,
                self.state.pro_skills.get("debater_3"),
            )
            await self._run_agent_phase(
                "pro_3", "pro_argument", agent,
                "请进行深入论证。",
            )

            # con_3 argument
            agent = create_con_agent(
                self.debate_id, 3, self.state.topic,
                self.state.con_skills.get("debater_3"),
            )
            await self._run_agent_phase(
                "con_3", "con_argument", agent,
                "请进行深入论证。",
            )
            # loop back to free debate

    @listen("free_debate")
    async def pro_3_closing(self) -> str:
        """正方三辩 — 总结陈词."""
        agent = create_pro_agent(
            self.debate_id, 3, self.state.topic,
            self.state.pro_skills.get("debater_3"),
        )
        return await self._run_agent_phase(
            "pro_3", "pro_closing", agent,
            "请进行总结陈词，回顾整场辩论，总结正方核心立场。"
        )

    @listen("pro_3_closing")
    async def con_3_closing(self) -> str:
        """反方三辩 — 总结陈词."""
        agent = create_con_agent(
            self.debate_id, 3, self.state.topic,
            self.state.con_skills.get("debater_3"),
        )
        return await self._run_agent_phase(
            "con_3", "con_closing", agent,
            "请进行总结陈词，回顾整场辩论，总结反方核心立场。"
        )

    @listen("con_3_closing")
    async def judge_verdict(self) -> None:
        """裁判 — 评分 + 裁决 + 持久化."""
        await self._check_pause()

        self.state.current_phase = "verdict"
        self._push_phase_start("verdict", "judge", self.state.current_round)

        # Build full transcript
        transcript = (
            f"# 辩论记录\n\n"
            f"辩题：{self.state.topic}\n"
            f"轮次：{self.state.total_rounds}轮\n\n"
        )
        for entry in self.state.debate_history:
            transcript += (
                f"## [{entry['debater']}] {entry['phase']}"
                f" (第{entry['round']}轮)\n{entry['content']}\n\n"
            )

        agent = create_judge_agent(
            self.debate_id, self.state.topic, self.state.judge_skill,
        )

        task = Task(
            description=(
                PHASE_CONTEXT["verdict"]
                + f"\n\n辩题：{self.state.topic}\n\n{transcript}"
            ),
            expected_output="JSON格式的裁决结果",
            agent=agent,
        )

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

        sse_bridge.push(
            self.debate_id,
            SSEDebateEnd(debate_id=self.debate_id, verdict=verdict),
        )

        _active_flows.pop(self.debate_id, None)
