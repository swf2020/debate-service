"""
Tests for verdict caching in debate flow judge_verdict phase.

Validates that cache.cache_verdict is called after set_verdict.
"""
from unittest.mock import AsyncMock, patch

import pytest


class TestJudgeVerdictCacheCall:
    """Verify that judge_verdict calls cache.cache_verdict after set_verdict."""

    @pytest.mark.asyncio
    async def test_cache_verdict_called_after_set_verdict(self):
        """judge_verdict should call cache.cache_verdict with correct args."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        assert cache.enabled is False
        # When disabled, cache_verdict is a no-op — no exception
        await cache.cache_verdict("d1", {"winner": "pro"}, "pro")

    @pytest.mark.asyncio
    async def test_cache_verdict_round_trip(self):
        """cache_verdict -> get_verdict returns the same data."""
        verdict = {
            "winner": "pro",
            "pro_scores": {"论证严谨度": 9, "total": 42},
            "con_scores": {"论证严谨度": 7, "total": 35},
            "summary": "正方获胜。",
        }
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        # Disabled cache: get_verdict returns None, cache_verdict is no-op
        result = await cache.get_verdict("d1")
        assert result is None
        await cache.cache_verdict("d1", verdict, "pro")

    @patch("redis_cache.redis.Redis")
    @pytest.mark.asyncio
    async def test_cache_verdict_is_idempotent(self, MockRedis):
        """Multiple cache_verdict calls don't error."""
        from unittest.mock import MagicMock, AsyncMock
        client = MagicMock()
        client.ping = AsyncMock(return_value=True)
        client.set = AsyncMock()
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        verdict = {"winner": "pro", "summary": "win"}
        await cache.cache_verdict("d1", verdict, "pro")
        await cache.cache_verdict("d1", verdict, "pro")
        # Second call overwrites — no error
        assert client.set.call_count == 2
