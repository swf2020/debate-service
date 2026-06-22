"""
Unit tests for SSEHistoryReplay verdict/winner fields.
"""
import json

import pytest
from models import SSEHistoryReplay


class TestSSEHistoryReplayVerdict:
    """Test that SSEHistoryReplay handles verdict and winner fields."""

    VERDICT = {
        "winner": "pro",
        "pro_scores": {"论证严谨度": 9, "total": 42},
        "con_scores": {"论证严谨度": 7, "total": 35},
        "summary": "正方获胜。",
    }

    def test_serialize_with_verdict(self):
        """SSEHistoryReplay with verdict -> JSON includes verdict and winner."""
        replay = SSEHistoryReplay(
            debate_id="d1",
            topic="Test",
            total_rounds=3,
            current_round=3,
            current_phase="verdict",
            paused=False,
            status="finished",
            verdict=self.VERDICT,
            winner="pro",
        )
        data = json.loads(replay.model_dump_json())
        assert data["type"] == "history_replay"
        assert data["verdict"] == self.VERDICT
        assert data["winner"] == "pro"

    def test_serialize_without_verdict(self):
        """SSEHistoryReplay without verdict -> JSON omits null verdict/winner."""
        replay = SSEHistoryReplay(
            debate_id="d2",
            topic="Test 2",
            total_rounds=3,
            current_round=1,
            current_phase="pro_opening",
            paused=False,
            status="running",
        )
        data = json.loads(replay.model_dump_json())
        assert data["type"] == "history_replay"
        assert data["verdict"] is None
        assert data["winner"] is None

    def test_deserialize_with_verdict(self):
        """JSON with verdict -> parsed SSEHistoryReplay has verdict fields."""
        json_str = json.dumps({
            "type": "history_replay",
            "debate_id": "d1",
            "topic": "Test",
            "format": "cdwc",
            "total_rounds": 3,
            "current_round": 3,
            "current_phase": "verdict",
            "paused": False,
            "status": "finished",
            "pro_skills": {},
            "con_skills": {},
            "debater_status": {"judge": "done"},
            "speeches": [],
            "verdict": self.VERDICT,
            "winner": "pro",
        })
        replay = SSEHistoryReplay.model_validate_json(json_str)
        assert replay.verdict == self.VERDICT
        assert replay.winner == "pro"

    def test_backward_compatible(self):
        """Old JSON without verdict/winner -> default to None."""
        json_str = json.dumps({
            "type": "history_replay",
            "debate_id": "d1",
            "topic": "Test",
            "format": "cdwc",
            "total_rounds": 3,
            "current_round": 3,
            "current_phase": "verdict",
            "paused": False,
            "status": "finished",
            "pro_skills": {},
            "con_skills": {},
            "debater_status": {},
            "speeches": [],
        })
        replay = SSEHistoryReplay.model_validate_json(json_str)
        assert replay.verdict is None
        assert replay.winner is None
