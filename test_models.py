"""Tests for debate_service.models -- new SSEStateSnapshot + DebateListItem."""

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
