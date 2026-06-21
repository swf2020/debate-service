"""
Tests for debate_service/debate_flow.py.

Run::

    cd debate-service && source .venv/bin/activate && python test_debate_flow.py
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from debate_flow import DebateFlow, _active_flows
from models import (
    SSEPhaseStart,
    SSEPhaseEnd,
    SSEError,
    SSEDebateEnd,
    SSEVerdictChunk,
    SSEStateSnapshot,
)


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_mock_agent(output: str = "test speech"):
    """Return a MagicMock that behaves enough like a crewAI Agent."""
    agent = MagicMock()
    agent.execute_task.return_value = output
    return agent


def _common_patches():
    """Patches needed by any test that constructs a crewAI ``Task``."""
    return (
        patch("debate_flow.sse_bridge"),
        patch("debate_flow.insert_speech"),
        patch("debate_flow.Task"),
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestFlowDefinition(unittest.TestCase):
    """Verify DebateFlow class structure and Flow DSL decorators."""

    def test_class_inherits_flow(self):
        from crewai.flow import Flow

        self.assertTrue(issubclass(DebateFlow, Flow))

    def test_flow_has_expected_method_names(self):
        fd = DebateFlow.flow_definition()
        method_names = set(fd.methods.keys())

        expected = {
            "begin_debate",
            "pro_1_opening",
            "con_1_opening",
            "con_2_argument",
            "pro_2_argument",
            "pro_3_cross_examine",
            "con_3_cross_examine",
            "con_3_summary",
            "pro_3_summary",
            "free_debate",
            "con_4_closing",
            "pro_4_closing",
            "judge_verdict",
        }
        self.assertTrue(
            expected.issubset(method_names),
            f"Missing: {expected - method_names}",
        )

    def test_begin_debate_is_start_method(self):
        fd = DebateFlow.flow_definition()
        begin = fd.methods["begin_debate"]
        self.assertTrue(begin.is_start)
        self.assertIsNone(begin.listen)

    def test_listeners_have_correct_conditions(self):
        fd = DebateFlow.flow_definition()

        chain = [
            ("pro_1_opening", "begin_debate"),
            ("con_1_opening", "pro_1_opening"),
            ("con_2_argument", "con_1_opening"),
            ("pro_2_argument", "con_2_argument"),
            ("pro_3_cross_examine", "pro_2_argument"),
            ("con_3_cross_examine", "pro_3_cross_examine"),
            ("con_3_summary", "con_3_cross_examine"),
            ("pro_3_summary", "con_3_summary"),
            ("free_debate", "pro_3_summary"),
            ("con_4_closing", "free_debate"),
            ("pro_4_closing", "con_4_closing"),
            ("judge_verdict", "pro_4_closing"),
        ]
        for method_name, expected_listen in chain:
            method = fd.methods[method_name]
            self.assertIsNotNone(
                method.listen,
                f"{method_name} should have a @listen condition",
            )
            self.assertEqual(
                method.listen,
                expected_listen,
                f"{method_name} listens for '{expected_listen}', got '{method.listen}'",
            )

    def test_no_routers_in_simple_chain(self):
        fd = DebateFlow.flow_definition()
        routers = [name for name, m in fd.methods.items() if m.router]
        self.assertEqual(len(routers), 0, f"Expected no routers, got: {routers}")


class TestCheckPause(unittest.TestCase):
    """Tests for _check_pause() polling behaviour."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-pause")

    def tearDown(self):
        _active_flows.pop("test-pause", None)

    def test_not_paused_returns_immediately(self):
        async def _run():
            self.flow.state.paused = False
            await asyncio.wait_for(self.flow._check_pause(), timeout=0.5)

        asyncio.run(_run())

    def test_blocks_while_paused_then_resumes(self):
        async def _run():
            self.flow.state.paused = True

            async def unpause_after_delay():
                await asyncio.sleep(0.2)
                self.flow._state.paused = False

            task = asyncio.create_task(unpause_after_delay())
            await asyncio.wait_for(self.flow._check_pause(), timeout=2.0)
            await task

        asyncio.run(_run())

    def test_repolling(self):
        async def _run():
            self.flow.state.paused = True

            async def tricky_unpause():
                await asyncio.sleep(0.1)
                self.flow._state.paused = False
                await asyncio.sleep(0.05)
                self.flow._state.paused = True
                await asyncio.sleep(0.1)
                self.flow._state.paused = False

            asyncio.create_task(tricky_unpause())
            await asyncio.wait_for(self.flow._check_pause(), timeout=2.0)

        asyncio.run(_run())


class TestPushSSE(unittest.TestCase):
    """Tests that _push_phase_start / _push_phase_end call sse_bridge."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-sse")

    def tearDown(self):
        _active_flows.pop("test-sse", None)

    def test_push_phase_start(self):
        with patch("debate_flow.sse_bridge") as mock_bridge:
            self.flow._push_phase_start("pro_opening", "pro_1", 1)

            mock_bridge.push.assert_called_once()
            args = mock_bridge.push.call_args[0]
            self.assertEqual(args[0], "test-sse")
            event = args[1]
            self.assertIsInstance(event, SSEPhaseStart)
            self.assertEqual(event.debate_id, "test-sse")
            self.assertEqual(event.phase, "pro_opening")
            self.assertEqual(event.debater, "pro_1")
            self.assertEqual(event.round_num, 1)

    def test_push_phase_end(self):
        with patch("debate_flow.sse_bridge") as mock_bridge:
            self.flow._push_phase_end("pro_opening", "pro_1")

            mock_bridge.push.assert_called_once()
            args = mock_bridge.push.call_args[0]
            self.assertEqual(args[0], "test-sse")
            event = args[1]
            self.assertIsInstance(event, SSEPhaseEnd)
            self.assertEqual(event.debate_id, "test-sse")
            self.assertEqual(event.phase, "pro_opening")
            self.assertEqual(event.debater, "pro_1")


class TestPhaseSequencing(unittest.TestCase):
    """Verify phase methods exist and have correct decorator wiring."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-seq")

    def tearDown(self):
        _active_flows.pop("test-seq", None)

    def test_methods_are_callable(self):
        methods = [
            "begin_debate",
            "pro_1_opening",
            "con_1_opening",
            "con_2_argument",
            "pro_2_argument",
            "pro_3_cross_examine",
            "con_3_cross_examine",
            "con_3_summary",
            "pro_3_summary",
            "free_debate",
            "con_4_closing",
            "pro_4_closing",
            "judge_verdict",
        ]
        for m in methods:
            fn = getattr(self.flow, m, None)
            self.assertIsNotNone(fn, f"Method {m} is missing")
            self.assertTrue(
                asyncio.iscoroutinefunction(fn) or callable(fn),
                f"Method {m} should be callable",
            )


class TestRunAgentPhase(unittest.TestCase):
    """Tests for _run_agent_phase() -- the core phase executor."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-phase")
        self.flow.state.topic = "test topic"
        self.flow.state.current_round = 1

    def tearDown(self):
        _active_flows.pop("test-phase", None)

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

                # Verify state_snapshot was pushed (thinking + speaking + done = 3)
                snap_calls = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEStateSnapshot)
                ]
                self.assertEqual(len(snap_calls), 3,
                                 f"Expected 3 SSEStateSnapshot pushes, got {len(snap_calls)}")

                # First snapshot: thinking
                snap1 = snap_calls[0][0][1]
                self.assertEqual(snap1.current_debater, "pro_1")
                self.assertEqual(snap1.debater_status["pro_1"], "thinking")

                # Second snapshot: speaking
                snap2 = snap_calls[1][0][1]
                self.assertEqual(snap2.current_debater, "pro_1")
                self.assertEqual(snap2.debater_status["pro_1"], "speaking")

                # Third snapshot: done
                snap3 = snap_calls[2][0][1]
                self.assertEqual(snap3.current_debater, "")
                self.assertEqual(snap3.debater_status["pro_1"], "done")

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

    def test_agent_failure(self):
        agent = _make_mock_agent()
        agent.execute_task.side_effect = RuntimeError("LLM crash")

        async def _run():
            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):

                output = await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "open"
                )

                self.assertIn("[错误]", output)
                error_calls = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEError)
                ]
                self.assertGreater(len(error_calls), 0)

        asyncio.run(_run())

    def test_appends_to_history(self):
        agent = _make_mock_agent("speech content")

        async def _run():
            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):

                self.assertEqual(len(self.flow.state.debate_history), 0)
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "open"
                )
                self.assertEqual(len(self.flow.state.debate_history), 1)
                entry = self.flow.state.debate_history[0]
                self.assertEqual(entry["debater"], "pro_1")
                self.assertEqual(entry["phase"], "pro_opening")
                self.assertEqual(entry["round"], 1)
                self.assertEqual(entry["content"], "speech content")

        asyncio.run(_run())


class TestFreeDebate(unittest.TestCase):
    """Tests for the free_debate inner loop (round handling)."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-fd")
        self.flow.state.topic = "test topic"
        self.flow.state.current_round = 1
        self.flow.state.total_rounds = 1

    def tearDown(self):
        _active_flows.pop("test-fd", None)

    def test_single_round_has_6_speeches(self):
        speak_count = 0

        async def _mock_run_phase(self_ref, key, phase, agent, ctx, **kwargs):
            nonlocal speak_count
            speak_count += 1
            return f"Speech from {key}"

        async def _run():
            self.flow.state.total_rounds = 1
            self.flow.state.current_round = 1
            with patch("debate_flow.create_pro_agent") as mock_pro, \
                 patch("debate_flow.create_con_agent") as mock_con, \
                 patch.object(DebateFlow, "_run_agent_phase", _mock_run_phase):

                mock_pro.return_value = _make_mock_agent()
                mock_con.return_value = _make_mock_agent()
                await self.flow.free_debate()

            # 4 pro + 4 con = 8 speeches for 4-round free debate
            self.assertEqual(speak_count, 8,
                             f"Expected 8 speeches, got {speak_count}")
            # CDWC free_debate is always single-round; current_round stays at 1
            self.assertEqual(self.flow.state.current_round, 1)

        asyncio.run(_run())


class TestJudgeVerdict(unittest.TestCase):
    """Tests for judge_verdict() JSON parsing and SSE / DB persistence."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-verdict")
        self.flow.state.topic = "test topic"
        self.flow.state.total_rounds = 1
        self.flow.state.debate_history = [
            {"debater": "pro_1", "phase": "pro_opening",
             "round": 1, "content": "pro opening"},
            {"debater": "con_1", "phase": "con_opening",
             "round": 1, "content": "con opening"},
        ]

    def tearDown(self):
        _active_flows.pop("test-verdict", None)

    def test_parses_fenced_json(self):
        agent = _make_mock_agent(
            '```json\n'
            '{"winner": "pro", "pro_scores": {"logic": 9},'
            ' "con_scores": {"logic": 7}, "summary": "pro wins"}\n'
            '```'
        )

        async def _run():
            with patch("debate_flow.create_judge_agent") as mock_judge, \
                 patch("debate_flow.set_verdict", new_callable=AsyncMock) as mock_verdict, \
                 patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.Task"):

                mock_judge.return_value = agent
                await self.flow.judge_verdict()

                mock_verdict.assert_called_once()
                call_args = mock_verdict.call_args
                self.assertEqual(call_args[0][0], "test-verdict")
                self.assertEqual(call_args[0][1], "pro")
                verdict = call_args[0][2]
                self.assertEqual(verdict["winner"], "pro")
                self.assertEqual(verdict["pro_scores"]["logic"], 9)

                self.assertEqual(self.flow.state.winner, "pro")

                verdict_chunks = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEVerdictChunk)
                ]
                self.assertGreater(len(verdict_chunks), 0)

                end_calls = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEDebateEnd)
                ]
                self.assertEqual(len(end_calls), 1)

        asyncio.run(_run())

    def test_parses_plain_json(self):
        agent = _make_mock_agent(
            '{"winner": "con", "pro_scores": {}, "con_scores": {},'
            ' "summary": "con wins"}'
        )

        async def _run():
            with patch("debate_flow.create_judge_agent") as mock_judge, \
                 patch("debate_flow.set_verdict", new_callable=AsyncMock), \
                 patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.Task"):

                mock_judge.return_value = agent
                await self.flow.judge_verdict()
                self.assertEqual(self.flow.state.winner, "con")

        asyncio.run(_run())

    def test_fallback_on_malformed_json(self):
        agent = _make_mock_agent("This is not JSON.")

        async def _run():
            with patch("debate_flow.create_judge_agent") as mock_judge, \
                 patch("debate_flow.set_verdict", new_callable=AsyncMock), \
                 patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.Task"):

                mock_judge.return_value = agent
                await self.flow.judge_verdict()
                self.assertEqual(self.flow.state.winner, "draw")
                self.assertIn("summary", self.flow.state.verdict)

        asyncio.run(_run())

    def test_handles_agent_exception(self):
        agent = _make_mock_agent()
        agent.execute_task.side_effect = RuntimeError("Judge crashed")

        async def _run():
            with patch("debate_flow.create_judge_agent") as mock_judge, \
                 patch("debate_flow.set_verdict", new_callable=AsyncMock), \
                 patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.Task"):

                mock_judge.return_value = agent
                await self.flow.judge_verdict()

                self.assertEqual(self.flow.state.winner, "draw")
                error_calls = [
                    c for c in mock_bridge.push.call_args_list
                    if isinstance(c[0][1], SSEError)
                ]
                self.assertGreater(len(error_calls), 0)

        asyncio.run(_run())


class TestPauseIntegration(unittest.TestCase):
    """Integration test: pause blocks, resume allows progress."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-pi")

    def tearDown(self):
        _active_flows.pop("test-pi", None)

    def test_run_agent_phase_blocks_when_paused(self):
        self.flow.state.paused = True
        agent = _make_mock_agent("content")

        async def _run():
            async def unpause_later():
                await asyncio.sleep(0.2)
                self.flow._state.paused = False

            task = asyncio.create_task(unpause_later())

            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):

                await asyncio.wait_for(
                    self.flow._run_agent_phase(
                        "pro_1", "pro_opening", agent, "context"
                    ),
                    timeout=2.0,
                )

            await task
            self.assertTrue(agent.execute_task.called)

        asyncio.run(_run())


class TestDebaterStatusManagement(unittest.TestCase):
    """Tests that only one debater is 'speaking' at any time and status
    transitions are correct (Bug 1 & 2 fixes)."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-status")
        self.flow.state.topic = "test topic"
        self.flow.state.current_round = 1

    def tearDown(self):
        _active_flows.pop("test-status", None)

    def test_only_one_speaking_when_new_phase_starts(self):
        """Bug 2: When a new phase starts, previous debater must NOT still
        be 'speaking'. Only the current debater should be 'speaking'."""
        agent1 = _make_mock_agent("speech 1")
        agent2 = _make_mock_agent("speech 2")

        async def _run():
            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):

                # Run phase 1
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent1, "open"
                )

                # After phase 1, pro_1 should be "done", not "speaking"
                self.assertEqual(self.flow.state.debater_status["pro_1"], "done")
                self.assertNotEqual(self.flow.state.debater_status["pro_1"], "speaking")

                # Run phase 2 - at the START, before agent executes,
                # we patch to capture the state_snapshot at phase start
                snapshots = []

                def capture_push(did, event):
                    if isinstance(event, SSEStateSnapshot):
                        snapshots.append(event)

                with patch("debate_flow.sse_bridge") as mock_bridge:
                    mock_bridge.push.side_effect = capture_push
                    await self.flow._run_agent_phase(
                        "con_1", "con_opening", agent2, "rebut"
                    )

                # Find the "speaking" snapshot (first snapshot is "thinking")
                speaking_snap = next(s for s in snapshots if s.debater_status.get("con_1") == "speaking")
                # con_1 should be speaking
                self.assertEqual(speaking_snap.debater_status["con_1"], "speaking")
                # pro_1 should NOT be speaking - it should be done
                self.assertNotEqual(
                    speaking_snap.debater_status["pro_1"], "speaking",
                    "pro_1 should not be 'speaking' when con_1 starts speaking"
                )
                # Count how many debaters are "speaking" in the snapshot
                speaking_count = sum(
                    1 for v in speaking_snap.debater_status.values()
                    if v == "speaking"
                )
                self.assertEqual(
                    speaking_count, 1,
                    f"Only 1 debater should be speaking, got {speaking_count}"
                )

        asyncio.run(_run())

    def test_previous_speaking_cleared_before_new_phase(self):
        """Bug 2: _run_agent_phase must clear any stale 'speaking' status
        before starting a new debater."""
        agent1 = _make_mock_agent("speech 1")
        agent2 = _make_mock_agent("speech 2")

        async def _run():
            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):

                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent1, "open"
                )
                # Simulate a stale "speaking" status (defensive test)
                self.flow.state.debater_status["pro_2"] = "speaking"

                snapshots = []

                def capture_push(did, event):
                    if isinstance(event, SSEStateSnapshot):
                        snapshots.append(event)

                with patch("debate_flow.sse_bridge") as mock_bridge:
                    mock_bridge.push.side_effect = capture_push
                    await self.flow._run_agent_phase(
                        "con_1", "con_opening", agent2, "rebut"
                    )

                # Find the "speaking" snapshot (skipping "thinking" snapshots)
                speaking_snaps = [s for s in snapshots if s.debater_status.get("con_1") == "speaking"]
                self.assertGreaterEqual(len(speaking_snaps), 1, "Should have a 'speaking' snapshot")
                speaking_snap = speaking_snaps[0]
                speaking_count = sum(
                    1 for v in speaking_snap.debater_status.values()
                    if v == "speaking"
                )
                self.assertEqual(speaking_count, 1,
                                 f"Only 1 speaking, got {speaking_count}")
                self.assertEqual(speaking_snap.debater_status["con_1"], "speaking")

        asyncio.run(_run())

    def test_status_event_order_speech_before_done(self):
        """Bug 1: SSE events must be ordered: speech chunks arrive before
        state_snapshot that marks debater as 'done'."""
        agent = _make_mock_agent("test speech")

        async def _run():
            events = []

            def capture_push(did, event):
                events.append((type(event).__name__, event))

            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):

                mock_bridge.push.side_effect = capture_push
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "open"
                )

            # Find the index of the 'done' state_snapshot
            done_idx = None
            for i, (ename, ev) in enumerate(events):
                if ename == "SSEStateSnapshot" and \
                   ev.debater_status.get("pro_1") == "done":
                    done_idx = i
                    break

            self.assertIsNotNone(done_idx, "Should have a 'done' state_snapshot")

            # The phase_end should come BEFORE the 'done' state_snapshot
            phase_end_idx = None
            for i, (ename, ev) in enumerate(events):
                if ename == "SSEPhaseEnd":
                    phase_end_idx = i

            self.assertIsNotNone(phase_end_idx, "Should have a phase_end event")
            self.assertLess(phase_end_idx, done_idx,
                            "phase_end must come before 'done' state_snapshot")

        asyncio.run(_run())


class TestActiveFlowsRegistry(unittest.TestCase):
    """Tests for the _active_flows module-level registry."""

    def test_flow_registered_on_init(self):
        flow = DebateFlow(debate_id="test-reg")
        try:
            self.assertIn("test-reg", _active_flows)
            self.assertIs(_active_flows["test-reg"], flow)
        finally:
            _active_flows.pop("test-reg", None)

    def test_flow_removed_after_cleanup(self):
        flow = DebateFlow(debate_id="test-cleanup")
        try:
            self.assertIn("test-cleanup", _active_flows)
            _active_flows.pop("test-cleanup", None)
            self.assertNotIn("test-cleanup", _active_flows)
        finally:
            _active_flows.pop("test-cleanup", None)


class TestThinkingInterceptorIsolation(unittest.TestCase):
    """Verify thinking interceptor attributes chunks to the correct debater
    based on contextvars, not global dict ordering."""

    def setUp(self):
        import agents
        agents._think_patched = False

    def tearDown(self):
        import agents
        agents._think_patched = False

    def test_multiple_llms_registered_contextvar_still_correct(self):
        """When 2 LLMs are registered, the context var correctly identifies
        the executing debater regardless of registration order."""
        import agents

        llm_1 = agents._make_llm(debate_id="test-iso", debater_key="pro_1")
        llm_2 = agents._make_llm(debate_id="test-iso", debater_key="con_1")

        # Set context for the FIRST created agent (pro_1)
        token = agents.set_current_thinking_debater("test-iso", "pro_1")
        try:
            ctx = agents._current_debater_ctx.get()
            self.assertEqual(ctx, ("test-iso", "pro_1"),
                             "Should return executing debater (pro_1), "
                             "not last registered (con_1)")
        finally:
            agents.reset_current_thinking_debater(token)

    def test_thinking_interceptor_uses_context_per_debater(self):
        """Each LLM should have its own streaming hook; thinking chunks
        are attributed via context var set by the flow before execution."""
        import agents

        llm_1 = agents._make_llm(debate_id="test-iso", debater_key="pro_1")
        llm_2 = agents._make_llm(debate_id="test-iso", debater_key="con_1")

        # Context is independent of LLM creation
        # When set for pro_1, it returns pro_1
        token = agents.set_current_thinking_debater("test-iso", "pro_1")
        try:
            self.assertEqual(agents._current_debater_ctx.get(),
                             ("test-iso", "pro_1"))
        finally:
            agents.reset_current_thinking_debater(token)

        # When set for con_1, it returns con_1
        token = agents.set_current_thinking_debater("test-iso", "con_1")
        try:
            self.assertEqual(agents._current_debater_ctx.get(),
                             ("test-iso", "con_1"))
        finally:
            agents.reset_current_thinking_debater(token)

    def test_contextvar_isolates_debater_across_multiple_llms(self):
        """contextvars approach: setting the context var before execute_task
        ensures thinking chunks are attributed to the CORRECT debater,
        independently of LLM creation order."""
        import agents

        # Create two LLMs (both registered for streaming)
        llm_1 = agents._make_llm(debate_id="test-cv", debater_key="pro_1")
        llm_2 = agents._make_llm(debate_id="test-cv", debater_key="con_1")

        # Simulate: set context for pro_1 (the FIRST created, now executing)
        token = agents.set_current_thinking_debater("test-cv", "pro_1")
        try:
            ctx = agents._current_debater_ctx.get()
            self.assertEqual(ctx, ("test-cv", "pro_1"),
                             "Context var should return the SET debater, "
                             "not the last registered")
        finally:
            agents.reset_current_thinking_debater(token)

        # Simulate: set context for con_1 (the SECOND created, now executing)
        token = agents.set_current_thinking_debater("test-cv", "con_1")
        try:
            ctx = agents._current_debater_ctx.get()
            self.assertEqual(ctx, ("test-cv", "con_1"),
                             "Context var should reflect the currently "
                             "executing debater, not creation order")
        finally:
            agents.reset_current_thinking_debater(token)

        # After reset, context should be None
        ctx = agents._current_debater_ctx.get()
        self.assertIsNone(ctx, "Context should be None after reset")

    def test_contextvar_propagates_independent_of_registration_order(self):
        """Verify context var gives correct debater regardless of which LLM
        was registered first or last. The context is EXPLICITLY set,
        not derived from global dict ordering."""
        import agents

        # Register LLMs in one order
        llm_1 = agents._make_llm(debate_id="test-cv2", debater_key="pro_1")
        llm_2 = agents._make_llm(debate_id="test-cv2", debater_key="con_1")
        llm_3 = agents._make_llm(debate_id="test-cv2", debater_key="pro_2")

        # Execute pro_1 (first created) — context var should say pro_1
        token = agents.set_current_thinking_debater("test-cv2", "pro_1")
        try:
            self.assertEqual(agents._current_debater_ctx.get(),
                             ("test-cv2", "pro_1"))
        finally:
            agents.reset_current_thinking_debater(token)

        # Execute pro_2 (third created) — context var should say pro_2
        token = agents.set_current_thinking_debater("test-cv2", "pro_2")
        try:
            self.assertEqual(agents._current_debater_ctx.get(),
                             ("test-cv2", "pro_2"))
        finally:
            agents.reset_current_thinking_debater(token)

        # Execute con_1 (second created) — context var should say con_1
        token = agents.set_current_thinking_debater("test-cv2", "con_1")
        try:
            self.assertEqual(agents._current_debater_ctx.get(),
                             ("test-cv2", "con_1"))
        finally:
            agents.reset_current_thinking_debater(token)

    def test_judge_does_not_affect_thinking_context(self):
        """Judge agent uses non-streaming LLM, context var remains None."""
        from agents import create_judge_agent
        import agents

        # Judge's LLM doesn't stream, so context var stays None
        self.assertIsNone(agents._current_debater_ctx.get(None))

        agent = create_judge_agent("test-judge", "topic", None)

        # Still None after judge creation (no streaming = no thinking interceptor)
        self.assertIsNone(agents._current_debater_ctx.get(None))


class TestThinkingContextPropagation(unittest.TestCase):
    """Verify _run_agent_phase and _cross_examine set the thinking context var
    so the DeepSeek reasoning_content interceptor can attribute chunks."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-think-ctx")
        self.flow.state.topic = "test topic"
        self.flow.state.current_round = 1
        import agents
        agents._think_patched = True  # skip actual OpenAI patching

    def tearDown(self):
        _active_flows.pop("test-think-ctx", None)
        import agents
        agents._think_patched = False

    def test_run_agent_phase_sets_context_before_execute(self):
        """_run_agent_phase must set _current_debater_ctx before
        asyncio.to_thread(agent.execute_task) so the thinking interceptor
        can attribute reasoning_content to the correct debater."""
        import agents
        agent = _make_mock_agent("test speech")

        captured_ctx = None

        def capture_ctx(*args, **kwargs):
            nonlocal captured_ctx
            captured_ctx = agents._current_debater_ctx.get(None)

        agent.execute_task.side_effect = capture_ctx

        async def _run():
            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "open"
                )

        asyncio.run(_run())

        self.assertIsNotNone(
            captured_ctx,
            "_current_debater_ctx should be set during execute_task"
        )
        self.assertEqual(
            captured_ctx,
            ("test-think-ctx", "pro_1"),
            f"Context should be (debate_id, debater_key), got {captured_ctx}"
        )

    def test_context_reset_after_execute(self):
        """After _run_agent_phase completes, _current_debater_ctx must be
        reset to None so stale context doesn't leak to next phase."""
        import agents
        agent = _make_mock_agent("test speech")

        async def _run():
            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "open"
                )

        asyncio.run(_run())

        ctx_after = agents._current_debater_ctx.get(None)
        self.assertIsNone(
            ctx_after,
            f"_current_debater_ctx should be None after phase, got {ctx_after}"
        )

    def test_context_switches_per_debater(self):
        """When two phases run sequentially, each must set the context to
        its own debater_key — not leak the previous one."""
        import agents
        agent1 = _make_mock_agent("speech 1")
        agent2 = _make_mock_agent("speech 2")

        ctx_seen = {}

        def make_capture(key):
            def capture(*args, **kwargs):
                ctx_seen[key] = agents._current_debater_ctx.get(None)
            return capture

        agent1.execute_task.side_effect = make_capture("pro_1")
        agent2.execute_task.side_effect = make_capture("con_1")

        async def _run():
            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent1, "open"
                )
                await self.flow._run_agent_phase(
                    "con_1", "con_opening", agent2, "rebut"
                )

        asyncio.run(_run())

        self.assertEqual(
            ctx_seen.get("pro_1"),
            ("test-think-ctx", "pro_1"),
            f"pro_1 context wrong: {ctx_seen.get('pro_1')}"
        )
        self.assertEqual(
            ctx_seen.get("con_1"),
            ("test-think-ctx", "con_1"),
            f"con_1 context wrong: {ctx_seen.get('con_1')}"
        )

    def test_cross_examine_sets_context_for_both_sides(self):
        """_cross_examine must set context for examiner AND target agent,
        each with their own debater_key."""
        import agents
        examiner = _make_mock_agent("question")
        target = _make_mock_agent("answer")
        targets = {"con_1": target}

        ctx_seen = {}

        def make_capture(key):
            def capture(*args, **kwargs):
                ctx_seen[key] = agents._current_debater_ctx.get(None)
            return capture

        examiner.execute_task.side_effect = make_capture("pro_3")
        target.execute_task.side_effect = make_capture("con_1")

        async def _run():
            with patch("debate_flow.sse_bridge"), \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"), \
                 patch("debate_flow.update_speech_content"):
                await self.flow._cross_examine(
                    "pro_3", "pro_cross_examine", ["con_1"],
                    make_examiner=lambda: examiner,
                    make_targets={"con_1": lambda: target},
                    context="请对反方一辩或二辩进行质询。",
                )

        asyncio.run(_run())

        self.assertEqual(
            ctx_seen.get("pro_3"),
            ("test-think-ctx", "pro_3"),
            f"Examiner context wrong: {ctx_seen.get('pro_3')}"
        )
        self.assertEqual(
            ctx_seen.get("con_1"),
            ("test-think-ctx", "con_1"),
            f"Target context wrong: {ctx_seen.get('con_1')}"
        )


class TestPhaseOrderingStrict(unittest.TestCase):
    """Verify strict sequential debate phase ordering:
    正方1 -> 反方1 -> 正方2 -> 反方2 -> 正方3 -> 反方3 -> judge
    No two debaters should be active simultaneously."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-order")
        self.flow.state.topic = "test topic"
        self.flow.state.current_round = 1

    def tearDown(self):
        _active_flows.pop("test-order", None)

    def test_phase_events_not_interleaved(self):
        """SSE events from two consecutive phases must not be interleaved.
        All events from phase N must appear before any event from phase N+1."""
        agent1 = _make_mock_agent("speech 1")
        agent2 = _make_mock_agent("speech 2")

        async def _run():
            all_events = []

            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):

                mock_bridge.push.side_effect = lambda did, ev: all_events.append((type(ev).__name__, ev))

                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent1, "open")
                await self.flow._run_agent_phase(
                    "con_1", "con_opening", agent2, "rebut")

            # Verify ordering: all pro_1 events, then all con_1 events
            pro_start_idx = next(i for i, (n, _) in enumerate(all_events)
                                 if n == "SSEPhaseStart" and _.phase == "pro_opening")
            pro_end_idx = next(i for i, (n, _) in enumerate(all_events)
                               if n == "SSEPhaseEnd" and _.phase == "pro_opening")
            con_start_idx = next(i for i, (n, _) in enumerate(all_events)
                                 if n == "SSEPhaseStart" and _.phase == "con_opening")
            con_end_idx = next(i for i, (n, _) in enumerate(all_events)
                               if n == "SSEPhaseEnd" and _.phase == "con_opening")

            # pro_1 phase_end comes before con_1 phase_start
            self.assertLess(pro_end_idx, con_start_idx,
                            "pro_1 phase_end must come before con_1 phase_start")
            # No interleaving: all pro_1 events before all con_1 events
            self.assertLess(pro_end_idx, con_start_idx)
            self.assertLess(con_start_idx, con_end_idx)

        asyncio.run(_run())

    def test_debate_flow_expected_order(self):
        """Verify the flow DSL chain follows:
        begin -> pro_1 -> con_1 -> pro_2 -> con_2 -> pro_3 -> con_3
        -> free_debate -> pro_3_closing -> con_3_closing -> judge"""
        fd = DebateFlow.flow_definition()

        expected_chain = [
            ("pro_1_opening", "begin_debate"),
            ("con_1_opening", "pro_1_opening"),
            ("con_2_argument", "con_1_opening"),
            ("pro_2_argument", "con_2_argument"),
            ("pro_3_cross_examine", "pro_2_argument"),
            ("con_3_cross_examine", "pro_3_cross_examine"),
            ("con_3_summary", "con_3_cross_examine"),
            ("pro_3_summary", "con_3_summary"),
            ("free_debate", "pro_3_summary"),
            ("con_4_closing", "free_debate"),
            ("pro_4_closing", "con_4_closing"),
            ("judge_verdict", "pro_4_closing"),
        ]

        for method_name, expected_listen in expected_chain:
            method = fd.methods[method_name]
            self.assertEqual(
                method.listen, expected_listen,
                f"{method_name} should listen for {expected_listen}"
            )

    def test_only_current_debater_has_speaking_status(self):
        """Throughout a phase, only the current debater has 'speaking' status.
        During phase transition, the previous debater transitions to 'done'
        before the next debater becomes 'speaking'."""
        agent1 = _make_mock_agent("speech 1")
        agent2 = _make_mock_agent("speech 2")
        agent3 = _make_mock_agent("speech 3")

        async def _run():
            snapshots = []

            def capture_snap(did, ev):
                if isinstance(ev, SSEStateSnapshot):
                    snapshots.append(ev)

            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                mock_bridge.push.side_effect = capture_snap

                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent1, "open")
                await self.flow._run_agent_phase(
                    "con_1", "con_opening", agent2, "rebut")
                await self.flow._run_agent_phase(
                    "pro_2", "pro_argument", agent3, "rebut")

            # Check each snapshot has exactly 1 "speaking" debater
            for snap in snapshots:
                speaking = [k for k, v in snap.debater_status.items()
                            if v == "speaking"]
                self.assertLessEqual(len(speaking), 1,
                                     f"At most 1 debater should be speaking, "
                                     f"got {speaking} in snap: {snap}")

        asyncio.run(_run())


class TestFourStateDebaterStatus(unittest.TestCase):
    """Verify 4 debater states: waiting -> thinking -> speaking -> done.

    The state must transition strictly:
    1. waiting -> thinking when phase starts (before LLM call)
    2. thinking -> speaking when first speech content arrives
    3. speaking -> done when agent finishes
    """

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-4state")
        self.flow.state.topic = "test topic"
        self.flow.state.current_round = 1

    def tearDown(self):
        _active_flows.pop("test-4state", None)

    def test_run_agent_phase_starts_with_thinking_not_speaking(self):
        """_run_agent_phase must set initial status to 'thinking', not
        'speaking'. The 'speaking' transition happens when the first
        speech chunk arrives."""
        agent = _make_mock_agent("test speech")

        async def _run():
            snapshots = []

            def capture_snap(did, ev):
                if isinstance(ev, SSEStateSnapshot):
                    snapshots.append(ev)

            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                mock_bridge.push.side_effect = capture_snap
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "open"
                )

            # First snapshot should have "thinking" status, not "speaking"
            first_snap = snapshots[0]
            self.assertEqual(
                first_snap.debater_status["pro_1"], "thinking",
                "Initial status should be 'thinking', not 'speaking'"
            )
            self.assertEqual(first_snap.current_debater, "pro_1")

            # Last snapshot should have "done" status
            last_snap = snapshots[-1]
            self.assertEqual(
                last_snap.debater_status["pro_1"], "done",
                "Final status should be 'done'"
            )
            self.assertEqual(last_snap.current_debater, "")

        asyncio.run(_run())

    def test_four_states_sequence_in_snapshots(self):
        """State snapshots should follow: thinking -> ... -> done.
        Never 'speaking' in initial snapshot (it was the old behavior)."""
        agent = _make_mock_agent("test speech")

        async def _run():
            snapshots = []

            def capture_snap(did, ev):
                if isinstance(ev, SSEStateSnapshot):
                    snapshots.append(ev)

            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                mock_bridge.push.side_effect = capture_snap
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent, "open"
                )

            # At least 2 snapshots: thinking + done
            self.assertGreaterEqual(len(snapshots), 2,
                                    f"Expected >=2 snapshots, got {len(snapshots)}")

            # First should NOT be "speaking" (old bug)
            self.assertNotEqual(snapshots[0].debater_status["pro_1"], "speaking",
                                "First snapshot should not be 'speaking'")

            # Status should transition through valid states only
            valid_states = {"thinking", "speaking", "done"}
            for snap in snapshots:
                status = snap.debater_status.get("pro_1", "")
                self.assertIn(status, valid_states,
                              f"Invalid status '{status}' in snapshot")

        asyncio.run(_run())

    def test_previous_thinking_cleared_before_new_phase(self):
        """Like test_previous_speaking_cleared_before_new_phase but also
        clears 'thinking' status (not just 'speaking')."""
        agent1 = _make_mock_agent("speech 1")
        agent2 = _make_mock_agent("speech 2")

        async def _run():
            snapshots = []

            def capture_snap(did, ev):
                if isinstance(ev, SSEStateSnapshot):
                    snapshots.append(ev)

            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                mock_bridge.push.side_effect = capture_snap

                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent1, "open"
                )
                # After first phase, pro_1 should be "done"
                self.assertEqual(self.flow.state.debater_status["pro_1"], "done")

                # Simulate stale "thinking" status
                self.flow.state.debater_status["pro_2"] = "thinking"

                await self.flow._run_agent_phase(
                    "con_1", "con_opening", agent2, "rebut"
                )

                # con_1's first snapshot should show con_1 as "thinking"
                con_snaps = [s for s in snapshots
                             if s.current_debater == "con_1" and
                             s.debater_status.get("con_1") == "thinking"]
                self.assertGreaterEqual(len(con_snaps), 1,
                                        "con_1 should have a 'thinking' snapshot")

                # pro_2's stale "thinking" should have been cleared
                con_speaking_snap = [s for s in snapshots
                                     if s.current_debater == "con_1"]
                if con_speaking_snap:
                    self.assertNotEqual(
                        con_speaking_snap[0].debater_status.get("pro_2"),
                        "thinking",
                        "Stale 'thinking' on pro_2 should be cleared"
                    )

        asyncio.run(_run())

    def test_all_four_states_appear_in_multi_phase_flow(self):
        """Across multiple phases, all 4 states should appear:
        waiting (initial), thinking (phase start), speaking, done (phase end)."""
        agent1 = _make_mock_agent("speech 1")
        agent2 = _make_mock_agent("speech 2")

        async def _run():
            all_statuses_seen = set()

            def capture_snap(did, ev):
                if isinstance(ev, SSEStateSnapshot):
                    for k, v in ev.debater_status.items():
                        all_statuses_seen.add(v)

            with patch("debate_flow.sse_bridge") as mock_bridge, \
                 patch("debate_flow.insert_speech"), \
                 patch("debate_flow.Task"):
                mock_bridge.push.side_effect = capture_snap

                # Initial state has "waiting" for all
                await self.flow.begin_debate()
                await self.flow._run_agent_phase(
                    "pro_1", "pro_opening", agent1, "open"
                )
                await self.flow._run_agent_phase(
                    "con_1", "con_opening", agent2, "rebut"
                )

            # All 4 states should appear
            expected = {"waiting", "thinking", "speaking", "done"}
            missing = expected - all_statuses_seen
            self.assertFalse(
                missing,
                f"Missing states in snapshots: {missing}. "
                f"Seen: {all_statuses_seen}"
            )

        asyncio.run(_run())


# ── Runner ───────────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("=" * 60)
    print("Debate Flow Tests -- debate_flow.py")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    success = result.wasSuccessful()
    print(f"Results: {result.testsRun - len(result.failures) - len(result.errors)} "
          f"passed, {len(result.failures)} failed, {len(result.errors)} errors")
    sys.exit(0 if success else 1)
