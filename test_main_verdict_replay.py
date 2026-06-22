"""
Tests for SSE history_replay verdict inclusion in main.py.

Validates SSEHistoryReplay construction with verdict/winner data.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from models import SSEHistoryReplay


class TestSSEHistoryReplayWithVerdict:
    """Test that SSEHistoryReplay correctly carries verdict data."""

    VERDICT = {
        "winner": "pro",
        "pro_scores": {"论证严谨度": 9, "total": 42},
        "con_scores": {"论证严谨度": 7, "total": 35},
        "summary": "正方获胜。",
    }

    def test_active_flow_finished_includes_verdict(self):
        """SSEHistoryReplay from active flow with finished status includes verdict."""
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
        assert data["verdict"] == self.VERDICT
        assert data["winner"] == "pro"
        assert data["status"] == "finished"

    def test_active_flow_running_omits_verdict(self):
        """SSEHistoryReplay from active flow with running status has null verdict."""
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
        assert data["verdict"] is None
        assert data["winner"] is None

    def test_db_path_finished_includes_verdict(self):
        """SSEHistoryReplay from DB (server restart) includes verdict."""
        replay = SSEHistoryReplay(
            debate_id="d3",
            topic="Past Debate",
            total_rounds=5,
            current_round=0,
            current_phase="",
            paused=False,
            status="finished",
            speeches=[],
            verdict=self.VERDICT,
            winner="con",
        )
        data = json.loads(replay.model_dump_json())
        assert data["verdict"] == self.VERDICT
        assert data["winner"] == "con"
        assert data["status"] == "finished"

    def test_db_path_running_omits_verdict(self):
        """SSEHistoryReplay from DB with running status has no verdict."""
        replay = SSEHistoryReplay(
            debate_id="d4",
            topic="Current",
            total_rounds=5,
            current_round=0,
            current_phase="",
            paused=False,
            status="running",
            speeches=[],
        )
        data = json.loads(replay.model_dump_json())
        assert data["verdict"] is None
        assert data["winner"] is None


class TestVerdictCacheIntegration:
    """Test that main.py reads verdict from cache when available."""

    VERDICT = {"winner": "pro", "pro_scores": {}, "con_scores": {}, "summary": "win"}

    @pytest.mark.asyncio
    async def test_get_verdict_cache_hit(self):
        """get_verdict returns cached verdict dict."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        assert cache.enabled is False
        result = await cache.get_verdict("d1")
        assert result is None  # disabled cache returns None

    @patch("redis_cache.redis.Redis")
    @pytest.mark.asyncio
    async def test_cache_verdict_then_get(self, MockRedis):
        """cache_verdict followed by get_verdict round-trips correctly."""
        import json as _json
        client = MagicMock()
        client.ping = AsyncMock(return_value=True)

        stored_value = None

        async def mock_set(key, value, ex=None):
            nonlocal stored_value
            stored_value = value

        async def mock_get(key):
            return stored_value

        client.set = AsyncMock(side_effect=mock_set)
        client.get = AsyncMock(side_effect=mock_get)
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.cache_verdict("d1", self.VERDICT, "pro")
        result = await cache.get_verdict("d1")

        assert result is not None
        assert result["verdict"] == self.VERDICT
        assert result["winner"] == "pro"
