"""Tests for debate_service.agents."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from crewai import Agent
from crewai.agents.parser import AgentAction, AgentFinish

from agents import (
    CON_ROLES,
    JUDGE_ROLE,
    PHASE_CONTEXT,
    PRO_ROLES,
    _make_llm,
    _make_step_callback,
    create_agent,
    create_con_agent,
    create_judge_agent,
    create_pro_agent,
)
from models import SSEThinkingChunk, SSESpeechChunk


class TestMakeLLM(unittest.TestCase):
    """Tests for _make_llm()"""

    def test_returns_LLM_object(self):
        """_make_llm returns a crewAI LLM object with expected attributes."""
        llm = _make_llm()
        self.assertTrue(hasattr(llm, "model"))
        self.assertTrue(hasattr(llm, "api_key"))
        self.assertTrue(hasattr(llm, "base_url"))

    def test_model_is_deepseek(self):
        """LLM uses deepseek-v4-pro model (prefix stripped by crewAI)."""
        llm = _make_llm()
        self.assertEqual(llm.model, "deepseek-v4-pro")


class TestMakeStepCallback(unittest.TestCase):
    """Tests for _make_step_callback()"""

    def setUp(self):
        self.debate_id = "test-debate-123"
        self.debater_key = "pro_1"

    def test_returns_callable(self):
        """_make_step_callback returns a callable."""
        cb = _make_step_callback(self.debate_id, self.debater_key)
        self.assertTrue(callable(cb))

    @patch("agents.sse_bridge")
    def test_agent_action_pushes_thinking_chunk(self, mock_bridge):
        """AgentAction with thought pushes SSEThinkingChunk via sse_bridge."""
        cb = _make_step_callback(self.debate_id, self.debater_key)
        action = AgentAction(
            thought="This is my thinking process",
            tool="some_tool",
            tool_input="some_input",
            text="some_text",
        )
        cb(action)

        mock_bridge.push.assert_called_once()
        call_args = mock_bridge.push.call_args
        self.assertEqual(call_args[0][0], self.debate_id)
        chunk = call_args[0][1]
        self.assertIsInstance(chunk, SSEThinkingChunk)
        self.assertEqual(chunk.debate_id, self.debate_id)
        self.assertEqual(chunk.debater, self.debater_key)
        self.assertEqual(chunk.content, "This is my thinking process")

    @patch("agents.sse_bridge")
    def test_agent_action_empty_thought_does_not_push(self, mock_bridge):
        """AgentAction with empty thought does not push an SSE chunk."""
        cb = _make_step_callback(self.debate_id, self.debater_key)
        action = AgentAction(
            thought="",
            tool="some_tool",
            tool_input="some_input",
            text="some_text",
        )
        cb(action)
        mock_bridge.push.assert_not_called()

    @patch("agents.sse_bridge")
    def test_agent_finish_pushes_thinking_chunk(self, mock_bridge):
        """AgentFinish with thought pushes SSEThinkingChunk via sse_bridge.

        Speech content is streamed in real-time by _install_stream_hook
        patching LLM._emit_stream_chunk_event, NOT from step_callback.
        """
        cb = _make_step_callback(self.debate_id, self.debater_key)
        finish = AgentFinish(
            thought="Final thought",
            output="This is the final speech output.",
            text="This is the final speech output.",
        )
        cb(finish)

        mock_bridge.push.assert_called_once()
        call_args = mock_bridge.push.call_args
        self.assertEqual(call_args[0][0], self.debate_id)
        chunk = call_args[0][1]
        self.assertIsInstance(chunk, SSEThinkingChunk)
        self.assertEqual(chunk.debate_id, self.debate_id)
        self.assertEqual(chunk.debater, self.debater_key)
        self.assertEqual(chunk.content, "Final thought")

    @patch("agents.sse_bridge")
    def test_agent_finish_empty_output_does_not_push(self, mock_bridge):
        """AgentFinish with empty output does not push an SSE chunk."""
        cb = _make_step_callback(self.debate_id, self.debater_key)
        finish = AgentFinish(thought="", output="", text="")
        cb(finish)
        mock_bridge.push.assert_not_called()


class TestCreateAgent(unittest.TestCase):
    """Tests for create_agent()"""

    def setUp(self):
        self.debate_id = "test-debate-456"
        self.llm = _make_llm()

    def test_returns_Agent_instance(self):
        """create_agent returns a crewAI Agent."""
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="Test topic",
            skill_name=None,
            llm=self.llm,
        )
        self.assertIsInstance(agent, Agent)

    def test_sets_role_goal_backstory(self):
        """Agent has the correct role, goal, and backstory."""
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="AI should be regulated",
            skill_name=None,
            llm=self.llm,
        )
        self.assertEqual(agent.role, PRO_ROLES[1]["role"])
        self.assertEqual(agent.goal, PRO_ROLES[1]["goal"])
        # Backstory starts with the base backstory
        self.assertIn("你是一位经验丰富的辩论一辩手", agent.backstory)

    def test_sets_llm(self):
        """Agent uses the provided LLM (same model)."""
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="Test",
            skill_name=None,
            llm=self.llm,
        )
        self.assertEqual(agent.llm.model, self.llm.model)

    def test_sets_step_callback(self):
        """Agent has a callable step_callback set."""
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="Test",
            skill_name=None,
            llm=self.llm,
        )
        self.assertTrue(callable(agent.step_callback))

    def test_verbose_is_false(self):
        """Agent has verbose=False to avoid console noise."""
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="Test",
            skill_name=None,
            llm=self.llm,
        )
        self.assertFalse(agent.verbose)


class TestCreateProAgent(unittest.TestCase):
    """Tests for create_pro_agent()"""

    def test_returns_Agent(self):
        """create_pro_agent returns a crewAI Agent."""
        agent = create_pro_agent(
            debate_id="debate-1",
            position=1,
            topic="Test topic",
            skill_name=None,
        )
        self.assertIsInstance(agent, Agent)

    def test_role_is_pro_first_debater(self):
        """Position 1 creates 正方一辩."""
        agent = create_pro_agent(
            debate_id="debate-1",
            position=1,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "正方一辩")

    def test_position_2_role(self):
        """Position 2 creates 正方二辩."""
        agent = create_pro_agent(
            debate_id="debate-1",
            position=2,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "正方二辩")

    def test_position_3_role(self):
        """Position 3 creates 正方三辩."""
        agent = create_pro_agent(
            debate_id="debate-1",
            position=3,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "正方三辩")

    def test_position_4_role(self):
        """Position 4 creates 正方四辩."""
        agent = create_pro_agent(
            debate_id="debate-1",
            position=4,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "正方四辩")

    def test_goal_is_set(self):
        """Agent goal matches PRO_ROLES definition."""
        agent = create_pro_agent(
            debate_id="debate-1",
            position=2,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.goal, PRO_ROLES[2]["goal"])


class TestCreateConAgent(unittest.TestCase):
    """Tests for create_con_agent()"""

    def test_returns_Agent(self):
        """create_con_agent returns a crewAI Agent."""
        agent = create_con_agent(
            debate_id="debate-1",
            position=1,
            topic="Test topic",
            skill_name=None,
        )
        self.assertIsInstance(agent, Agent)

    def test_role_is_con_first_debater(self):
        """Position 1 creates 反方一辩."""
        agent = create_con_agent(
            debate_id="debate-1",
            position=1,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "反方一辩")

    def test_position_2_role(self):
        """Position 2 creates 反方二辩."""
        agent = create_con_agent(
            debate_id="debate-1",
            position=2,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "反方二辩")

    def test_position_3_role(self):
        """Position 3 creates 反方三辩."""
        agent = create_con_agent(
            debate_id="debate-1",
            position=3,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "反方三辩")

    def test_position_4_role(self):
        """Position 4 creates 反方四辩."""
        agent = create_con_agent(
            debate_id="debate-1",
            position=4,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "反方四辩")

    def test_goal_is_set(self):
        """Agent goal matches CON_ROLES definition."""
        agent = create_con_agent(
            debate_id="debate-1",
            position=2,
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.goal, CON_ROLES[2]["goal"])


class TestCreateJudgeAgent(unittest.TestCase):
    """Tests for create_judge_agent()"""

    def test_returns_Agent(self):
        """create_judge_agent returns a crewAI Agent."""
        agent = create_judge_agent(
            debate_id="debate-1",
            topic="Test topic",
            skill_name=None,
        )
        self.assertIsInstance(agent, Agent)

    def test_role_is_judge(self):
        """Judge agent has role 裁判."""
        agent = create_judge_agent(
            debate_id="debate-1",
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.role, "裁判")

    def test_goal_is_set(self):
        """Judge agent goal matches JUDGE_ROLE definition."""
        agent = create_judge_agent(
            debate_id="debate-1",
            topic="Test",
            skill_name=None,
        )
        self.assertEqual(agent.goal, JUDGE_ROLE["goal"])

    def test_backstory_includes_scoring_dimensions(self):
        """Judge backstory includes the scoring criteria."""
        agent = create_judge_agent(
            debate_id="debate-1",
            topic="Test",
            skill_name=None,
        )
        self.assertIn("论证严谨度", agent.backstory)
        self.assertIn("裁判", agent.backstory)


class TestBuildBackstoryWithSkillIntegration(unittest.TestCase):
    """Tests for skill integration in agent creation."""

    def setUp(self):
        self.debate_id = "test-debate-skill"
        self.llm = _make_llm()

    def test_agent_without_skill_uses_base_backstory(self):
        """Without skill, backstory is unchanged base backstory."""
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="Test",
            skill_name=None,
            llm=self.llm,
        )
        self.assertEqual(agent.backstory, PRO_ROLES[1]["backstory"])

    def test_agent_with_nonexistent_skill_uses_base_backstory(self):
        """With a nonexistent skill, backstory falls back to base."""
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="Test",
            skill_name="not-a-real-perspective",
            llm=self.llm,
        )
        self.assertEqual(agent.backstory, PRO_ROLES[1]["backstory"])

    def test_agent_with_real_skill_has_extended_backstory(self):
        """With a real skill, backstory includes the skill content."""
        from skill_loader import list_available_skills

        skills = list_available_skills()
        if not skills:
            self.skipTest("No real perspective skills found on this machine")

        skill_name = skills[0]["name"]
        agent = create_agent(
            debate_id=self.debate_id,
            debater_key="pro_1",
            role_info=PRO_ROLES[1],
            topic="Test",
            skill_name=skill_name,
            llm=self.llm,
        )
        self.assertIn(PRO_ROLES[1]["backstory"], agent.backstory)
        self.assertIn(f"## 你的思维框架（来自 {skill_name}）", agent.backstory)
        self.assertGreater(len(agent.backstory), len(PRO_ROLES[1]["backstory"]))


class TestPhaseContext(unittest.TestCase):
    """Tests for PHASE_CONTEXT constant."""

    def test_has_all_twelve_phases(self):
        """PHASE_CONTEXT contains all 12 expected phases."""
        expected_phases = {
            "pro_opening",
            "con_opening",
            "pro_rebuttal",
            "con_rebuttal",
            "pro_cross_examine",
            "con_cross_examine",
            "pro_cross_summary",
            "con_cross_summary",
            "free_debate",
            "pro_closing",
            "con_closing",
            "verdict",
        }
        self.assertEqual(set(PHASE_CONTEXT.keys()), expected_phases)

    def test_all_values_are_non_empty_strings(self):
        """Every phase context is a non-empty string."""
        for key, value in PHASE_CONTEXT.items():
            self.assertIsInstance(value, str, f"PHASE_CONTEXT['{key}'] is not str")
            self.assertGreater(len(value), 0, f"PHASE_CONTEXT['{key}'] is empty")


class TestRolesConstants(unittest.TestCase):
    """Tests for PRO_ROLES, CON_ROLES, JUDGE_ROLE constants."""

    def test_pro_roles_has_four_positions(self):
        """PRO_ROLES has keys 1, 2, 3, 4."""
        self.assertEqual(set(PRO_ROLES.keys()), {1, 2, 3, 4})

    def test_con_roles_has_four_positions(self):
        """CON_ROLES has keys 1, 2, 3, 4."""
        self.assertEqual(set(CON_ROLES.keys()), {1, 2, 3, 4})

    def test_each_pro_role_has_required_keys(self):
        """Each PRO_ROLES entry has role, goal, backstory."""
        for pos, info in PRO_ROLES.items():
            self.assertIn("role", info)
            self.assertIn("goal", info)
            self.assertIn("backstory", info)
            self.assertIsInstance(info["role"], str)
            self.assertIsInstance(info["goal"], str)
            self.assertIsInstance(info["backstory"], str)

    def test_each_con_role_has_required_keys(self):
        """Each CON_ROLES entry has role, goal, backstory."""
        for pos, info in CON_ROLES.items():
            self.assertIn("role", info)
            self.assertIn("goal", info)
            self.assertIn("backstory", info)
            self.assertIsInstance(info["role"], str)
            self.assertIsInstance(info["goal"], str)
            self.assertIsInstance(info["backstory"], str)

    def test_judge_role_has_required_keys(self):
        """JUDGE_ROLE has role, goal, backstory."""
        self.assertIn("role", JUDGE_ROLE)
        self.assertIn("goal", JUDGE_ROLE)
        self.assertIn("backstory", JUDGE_ROLE)


if __name__ == "__main__":
    unittest.main()
