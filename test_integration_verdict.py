"""
Integration tests for end-to-end verdict caching and replay flow.

Verifies: debate finish → cache_verdict → SSEHistoryReplay includes verdict.
"""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from models import SSEHistoryReplay


class TestVerdictEndToEnd:
    """Test the full verdict data flow from judge to replay."""

    VERDICT = {
        "winner": "pro",
        "pro_scores": {
            "论证严谨度": 9, "数据与事实支撑": 8,
            "反驳有效性": 7, "表达清晰度": 8, "质询表现": 7,
            "total": 39,
        },
        "con_scores": {
            "论证严谨度": 7, "数据与事实支撑": 6,
            "反驳有效性": 5, "表达清晰度": 7, "质询表现": 6,
            "total": 31,
        },
        "summary": "正方论点更充分，证据链完整。",
    }

    @patch("redis_cache.redis.Redis")
    @pytest.mark.asyncio
    async def test_cache_verdict_and_replay_roundtrip(self, MockRedis):
        """Full roundtrip: cache verdict → read from cache → build SSEHistoryReplay."""
        from unittest.mock import AsyncMock

        # Setup mock Redis
        store = {}
        client = MagicMock()
        client.ping = AsyncMock(return_value=True)

        async def mock_set(key, value, ex=None):
            store[key] = value
        async def mock_get(key):
            return store.get(key)
        client.set = AsyncMock(side_effect=mock_set)
        client.get = AsyncMock(side_effect=mock_get)
        MockRedis.from_url.return_value = client

        # Step 1: Cache verdict (simulating judge_verdict finish)
        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.cache_verdict("debate-1", self.VERDICT, "pro")

        # Step 2: Read verdict from cache (simulating SSE reconnect)
        verdict_data = await cache.get_verdict("debate-1")
        assert verdict_data is not None
        assert verdict_data["verdict"] == self.VERDICT
        assert verdict_data["winner"] == "pro"

        # Step 3: Build SSEHistoryReplay with verdict (simulating main.py)
        replay = SSEHistoryReplay(
            debate_id="debate-1",
            topic="AI Safety",
            total_rounds=3,
            current_round=3,
            current_phase="verdict",
            paused=False,
            status="finished",
            speeches=[],
            verdict=verdict_data["verdict"],
            winner=verdict_data["winner"],
        )
        data = json.loads(replay.model_dump_json())

        # Step 4: Verify frontend can render verdict from replay
        assert data["verdict"]["winner"] == "pro"
        assert data["winner"] == "pro"
        assert data["status"] == "finished"
        assert "pro_scores" in data["verdict"]
        assert "con_scores" in data["verdict"]

        # Step 5: Simulate debate delete — invalidate should clear all
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[None])
        client.pipeline.return_value = pipe
        client.delete = AsyncMock()
        await cache.invalidate_debate("debate-1")
        # Verdict key should be in the delete call
        assert client.delete.called
        args = client.delete.call_args[0]
        assert "debate:debate-1:verdict" in args

    @patch("redis_cache.redis.Redis")
    @pytest.mark.asyncio
    async def test_cache_miss_fallback_to_db(self, MockRedis):
        """On cache miss, caller gets None and should fall back to DB."""
        client = MagicMock()
        client.ping = AsyncMock(return_value=True)
        client.get = AsyncMock(return_value=None)
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_verdict("debate-2")
        assert result is None  # Caller falls back to DB

    @pytest.mark.asyncio
    async def test_sse_history_replay_without_verdict_handled(self):
        """SSEHistoryReplay without verdict is valid for running debates."""
        # Simulate reconnect to running debate (no verdict yet)
        replay = SSEHistoryReplay(
            debate_id="debate-3",
            topic="Running Debate",
            total_rounds=3,
            current_round=1,
            current_phase="pro_opening",
            paused=False,
            status="running",
            speeches=[],
        )
        data = json.loads(replay.model_dump_json())
        assert data["verdict"] is None
        assert data["winner"] is None
        # Frontend should NOT render verdict (verified by vitest)
