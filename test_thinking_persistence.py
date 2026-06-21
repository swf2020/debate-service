"""
Tests for thinking content accumulation and DB persistence.

When a debater finishes speaking, both thinking content and speech content
must be persisted to the database. Thinking content arrives as streaming
chunks from two sources:
1. _ThinkingStreamWrapper — intercepts DeepSeek reasoning_content
2. _make_step_callback — captures AgentAction.thought from crewAI

These chunks must be accumulated per-debater and then retrieved when
the flow calls _persist_speech.
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch, MagicMock

from agents import (
    accumulate_thinking,
    get_and_clear_thinking,
    _current_debater_ctx,
    set_current_thinking_debater,
    reset_current_thinking_debater,
)


class TestThinkingAccumulation(unittest.TestCase):
    """Tests for accumulate_thinking / get_and_clear_thinking."""

    def setUp(self):
        # Clean up any leftover state
        import agents
        agents._thinking_buffer.clear()

    def tearDown(self):
        import agents
        agents._thinking_buffer.clear()

    def test_accumulate_single_chunk(self):
        """Single chunk is stored correctly."""
        accumulate_thinking("deb-1", "pro_1", "Hello")
        result = get_and_clear_thinking("deb-1", "pro_1")
        self.assertEqual(result, "Hello")

    def test_accumulate_multiple_chunks(self):
        """Multiple chunks are concatenated in order."""
        accumulate_thinking("deb-1", "pro_1", "Hello ")
        accumulate_thinking("deb-1", "pro_1", "World")
        accumulate_thinking("deb-1", "pro_1", "!")
        result = get_and_clear_thinking("deb-1", "pro_1")
        self.assertEqual(result, "Hello World!")

    def test_get_and_clear_removes_buffer(self):
        """After get_and_clear, the buffer is empty."""
        accumulate_thinking("deb-1", "pro_1", "test")
        get_and_clear_thinking("deb-1", "pro_1")
        result = get_and_clear_thinking("deb-1", "pro_1")
        self.assertEqual(result, "")

    def test_no_accumulation_returns_empty(self):
        """get_and_clear returns '' for debater with no thinking."""
        result = get_and_clear_thinking("deb-1", "unknown")
        self.assertEqual(result, "")

    def test_different_debaters_isolated(self):
        """Different debaters have separate buffers."""
        accumulate_thinking("deb-1", "pro_1", "pro thinks")
        accumulate_thinking("deb-1", "con_1", "con thinks")
        self.assertEqual(get_and_clear_thinking("deb-1", "pro_1"), "pro thinks")
        self.assertEqual(get_and_clear_thinking("deb-1", "con_1"), "con thinks")

    def test_different_debates_isolated(self):
        """Different debates have separate buffers."""
        accumulate_thinking("deb-1", "pro_1", "debate 1")
        accumulate_thinking("deb-2", "pro_1", "debate 2")
        self.assertEqual(get_and_clear_thinking("deb-1", "pro_1"), "debate 1")
        self.assertEqual(get_and_clear_thinking("deb-2", "pro_1"), "debate 2")

    def test_concurrent_accumulation(self):
        """Multiple threads can accumulate thinking simultaneously."""
        errors = []
        def worker(thread_id, n_chunks):
            try:
                for i in range(n_chunks):
                    accumulate_thinking("deb-1", "pro_1", f"T{thread_id}C{i} ")
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=worker, args=(t, 100)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        result = get_and_clear_thinking("deb-1", "pro_1")
        # Verify all threads contributed
        for t in range(8):
            self.assertIn(f"T{t}C", result)

    def test_unicode_content_preserved(self):
        """Chinese characters are preserved correctly."""
        accumulate_thinking("deb-1", "pro_1", "我认为")
        accumulate_thinking("deb-1", "pro_1", "这个观点")
        result = get_and_clear_thinking("deb-1", "pro_1")
        self.assertEqual(result, "我认为这个观点")

    def test_empty_chunk_not_accumulated(self):
        """Empty string chunks are ignored."""
        accumulate_thinking("deb-1", "pro_1", "")
        accumulate_thinking("deb-1", "pro_1", "real")
        result = get_and_clear_thinking("deb-1", "pro_1")
        self.assertEqual(result, "real")


class TestThinkingStepCallbackAccumulation(unittest.TestCase):
    """Verify step_callback accumulates thinking to buffer."""

    def setUp(self):
        import agents
        agents._thinking_buffer.clear()

    def tearDown(self):
        import agents
        agents._thinking_buffer.clear()

    @patch("agents.sse_bridge")
    def test_agent_action_accumulates_thinking(self, mock_bridge):
        """AgentAction.thought is accumulated to the thinking buffer."""
        from agents import _make_step_callback
        from crewai.agents.parser import AgentAction

        cb = _make_step_callback("deb-test", "pro_2")
        action = AgentAction(
            thought="Analyzing opponent argument...",
            tool="some_tool",
            tool_input="{}",
            text="text",
        )
        cb(action)
        result = get_and_clear_thinking("deb-test", "pro_2")
        self.assertEqual(result, "Analyzing opponent argument...")

    @patch("agents.sse_bridge")
    def test_agent_finish_accumulates_thinking(self, mock_bridge):
        """AgentFinish.thought is accumulated to the thinking buffer."""
        from agents import _make_step_callback
        from crewai.agents.parser import AgentFinish

        cb = _make_step_callback("deb-test", "con_1")
        finish = AgentFinish(
            thought="Ready to deliver conclusion",
            output="Final speech",
            text="Final speech",
        )
        cb(finish)
        result = get_and_clear_thinking("deb-test", "con_1")
        self.assertEqual(result, "Ready to deliver conclusion")

    @patch("agents.sse_bridge")
    def test_empty_thought_not_accumulated(self, mock_bridge):
        """Empty thought does not add to buffer."""
        from agents import _make_step_callback
        from crewai.agents.parser import AgentAction

        cb = _make_step_callback("deb-test", "pro_1")
        action = AgentAction(thought="", tool="t", tool_input="{}", text="")
        cb(action)
        result = get_and_clear_thinking("deb-test", "pro_1")
        self.assertEqual(result, "")


class TestThinkingContextVarPropagation(unittest.TestCase):
    """Verify context var still works for thinking interceptor."""

    def setUp(self):
        import agents
        agents._thinking_buffer.clear()

    def tearDown(self):
        import agents
        agents._thinking_buffer.clear()

    def test_set_and_get_context(self):
        """Context var is set and readable."""
        token = set_current_thinking_debater("deb-x", "pro_3")
        ctx = _current_debater_ctx.get(None)
        self.assertEqual(ctx, ("deb-x", "pro_3"))
        reset_current_thinking_debater(token)
        self.assertIsNone(_current_debater_ctx.get(None))

    def test_context_reset_restores_previous(self):
        """Context reset restores previous value correctly."""
        token1 = set_current_thinking_debater("deb-1", "pro_1")
        token2 = set_current_thinking_debater("deb-1", "con_1")
        self.assertEqual(_current_debater_ctx.get(None), ("deb-1", "con_1"))
        reset_current_thinking_debater(token2)
        self.assertEqual(_current_debater_ctx.get(None), ("deb-1", "pro_1"))
        reset_current_thinking_debater(token1)
        self.assertIsNone(_current_debater_ctx.get(None))


class TestFlowPersistsThinkingToDB(unittest.TestCase):
    """Integration: verify _persist_speech passes accumulated thinking to insert_speech."""

    def setUp(self):
        import agents
        agents._thinking_buffer.clear()

    def tearDown(self):
        import agents
        agents._thinking_buffer.clear()

    def test_persist_speech_receives_thinking(self):
        """_persist_speech passes accumulated thinking content to insert_speech."""
        import asyncio
        from unittest.mock import patch
        from debate_flow import DebateFlow

        # Create flow and set state attributes (state property has no setter)
        flow = DebateFlow("deb-persist")
        flow.state.topic = "test"
        flow.state.total_rounds = 1
        flow.state.current_round = 1
        flow.state.id = "deb-persist"

        async def _run():
            with patch("debate_flow.insert_speech") as mock_insert:
                mock_insert.return_value = 1
                await flow._persist_speech("pro_1", "free_debate", "深度思考内容", "自由辩论发言", "free_debate")
                mock_insert.assert_called_once()
                kwargs = mock_insert.call_args.kwargs
                self.assertEqual(kwargs["thinking"], "深度思考内容",
                                 "thinking content should be passed to insert_speech")
                self.assertEqual(kwargs["content"], "自由辩论发言",
                                 "speech content should be passed to insert_speech")
                self.assertEqual(kwargs["speech_type"], "free_debate",
                                 "speech_type should be free_debate")

        asyncio.run(_run())

    def test_get_and_clear_then_persist_flow(self):
        """After accumulate + get_and_clear, buffer is empty for next phase."""
        accumulate_thinking("deb-persist", "pro_1", "thinking round 1")
        result = get_and_clear_thinking("deb-persist", "pro_1")
        self.assertEqual(result, "thinking round 1")

        # Buffer should be clear
        result2 = get_and_clear_thinking("deb-persist", "pro_1")
        self.assertEqual(result2, "")

        # Next phase accumulates independently
        accumulate_thinking("deb-persist", "pro_1", "thinking round 2")
        result3 = get_and_clear_thinking("deb-persist", "pro_1")
        self.assertEqual(result3, "thinking round 2")

    def test_free_debate_multi_speaker_persistence(self):
        """Each free debate speaker's thinking persists independently."""
        # Simulate free debate: pro_1 → con_1 → pro_2 (3 exchanges)
        import asyncio
        from unittest.mock import patch
        from debate_flow import DebateFlow

        flow = DebateFlow("deb-fd")
        flow.state.topic = "test"
        flow.state.total_rounds = 1
        flow.state.current_round = 1
        flow.state.id = "deb-fd"

        # Round 1: pro_1 thinks and speaks
        accumulate_thinking("deb-fd", "pro_1", "pro1的思考")
        # Round 1: con_1 thinks and speaks
        accumulate_thinking("deb-fd", "con_1", "con1的思考")
        # Round 2: pro_2 thinks and speaks
        accumulate_thinking("deb-fd", "pro_2", "pro2的思考")

        async def _run():
            with patch("debate_flow.insert_speech") as mock_insert:
                mock_insert.return_value = 1

                # Persist pro_1
                t1 = get_and_clear_thinking("deb-fd", "pro_1")
                await flow._persist_speech("pro_1", "free_debate", t1, "pro1发言", "free_debate")

                # Persist con_1
                t2 = get_and_clear_thinking("deb-fd", "con_1")
                await flow._persist_speech("con_1", "free_debate", t2, "con1发言", "free_debate")

                # Persist pro_2
                t3 = get_and_clear_thinking("deb-fd", "pro_2")
                await flow._persist_speech("pro_2", "free_debate", t3, "pro2发言", "free_debate")

                self.assertEqual(mock_insert.call_count, 3)

                # Check each call's thinking arg via kwargs
                calls = mock_insert.call_args_list
                self.assertEqual(calls[0].kwargs["thinking"], "pro1的思考")
                self.assertEqual(calls[0].kwargs["content"], "pro1发言")
                self.assertEqual(calls[1].kwargs["thinking"], "con1的思考")
                self.assertEqual(calls[1].kwargs["content"], "con1发言")
                self.assertEqual(calls[2].kwargs["thinking"], "pro2的思考")
                self.assertEqual(calls[2].kwargs["content"], "pro2发言")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
