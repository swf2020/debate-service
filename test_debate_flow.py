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
            "pro_2_rebuttal",
            "con_2_rebuttal",
            "pro_3_argument",
            "con_3_argument",
            "free_debate",
            "pro_3_closing",
            "con_3_closing",
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
            ("pro_2_rebuttal", "con_1_opening"),
            ("con_2_rebuttal", "pro_2_rebuttal"),
            ("pro_3_argument", "con_2_rebuttal"),
            ("con_3_argument", "pro_3_argument"),
            ("free_debate", "con_3_argument"),
            ("pro_3_closing", "free_debate"),
            ("con_3_closing", "pro_3_closing"),
            ("judge_verdict", "con_3_closing"),
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
            "pro_2_rebuttal",
            "con_2_rebuttal",
            "pro_3_argument",
            "con_3_argument",
            "free_debate",
            "pro_3_closing",
            "con_3_closing",
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

        async def _mock_run_phase(self_ref, key, phase, agent, ctx):
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

            # 3 pro + 3 con = 6 speeches for 1 round
            self.assertEqual(speak_count, 6,
                             f"Expected 6 speeches, got {speak_count}")
            self.assertGreater(
                self.flow.state.current_round,
                self.flow.state.total_rounds,
            )

        asyncio.run(_run())

    def test_multi_round_inner_body_re_runs(self):
        speak_count = 0

        async def _mock_run_phase(self_ref, key, phase, agent, ctx):
            nonlocal speak_count
            speak_count += 1
            return f"Speech from {key}"

        async def _run():
            self.flow.state.total_rounds = 2
            self.flow.state.current_round = 1
            with patch("debate_flow.create_pro_agent") as mock_pro, \
                 patch("debate_flow.create_con_agent") as mock_con, \
                 patch.object(DebateFlow, "_run_agent_phase", _mock_run_phase):

                mock_pro.return_value = _make_mock_agent()
                mock_con.return_value = _make_mock_agent()
                await self.flow.free_debate()

            # Round 1: 6 free debate + 4 inner body = 10
            # Round 2: 6 free debate                = 6
            # Total:                                  16
            self.assertEqual(speak_count, 16,
                             f"Expected 16 speeches, got {speak_count}")
            self.assertGreater(
                self.flow.state.current_round,
                self.flow.state.total_rounds,
            )

        asyncio.run(_run())


class TestJudgeVerdict(unittest.TestCase):
    """Tests for judge_verdict() JSON parsing and SSE / DB persistence."""

    def setUp(self):
        self.flow = DebateFlow(debate_id="test-verdict")
        self.flow.state.topic = "test topic"
        self.flow.state.total_rounds = 2
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
