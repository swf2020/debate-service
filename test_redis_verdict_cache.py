"""
Unit tests for Redis verdict cache methods.

Uses unittest.mock to avoid requiring a real Redis instance.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_cache import RedisCache

REDIS_PATCH = "redis_cache.redis.Redis"


def _make_mock_redis_client():
    """Create a mock redis.asyncio.Redis with ping that succeeds."""
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    return client


class TestCacheVerdict:
    """Test verdict caching."""

    VERDICT = {
        "winner": "pro",
        "pro_scores": {"论证严谨度": 9, "数据与事实支撑": 8, "反驳有效性": 7,
                       "表达清晰度": 8, "质询表现": 7, "total": 39},
        "con_scores": {"论证严谨度": 7, "数据与事实支撑": 6, "反驳有效性": 5,
                       "表达清晰度": 7, "质询表现": 6, "total": 31},
        "summary": "正方论点更充分，证据链更完整。",
    }

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_cache_verdict_writes_with_ttl(self, MockRedis):
        """cache_verdict writes verdict JSON under debate:{id}:verdict with TTL."""
        client = _make_mock_redis_client()
        client.set = AsyncMock()
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.cache_verdict("d1", self.VERDICT, "pro")

        client.set.assert_called_once()
        args, kwargs = client.set.call_args
        assert args[0] == "debate:d1:verdict"
        data = json.loads(args[1])
        assert data["winner"] == "pro"
        assert data["verdict"] == self.VERDICT
        assert kwargs["ex"] == 86400

    @pytest.mark.asyncio
    async def test_cache_verdict_disabled_skips(self):
        """Cache disabled -> cache_verdict is no-op."""
        cache = RedisCache(redis_url=None)
        # Should not raise
        await cache.cache_verdict("d1", self.VERDICT, "pro")

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_cache_verdict_empty_verdict_skips(self, MockRedis):
        """Empty verdict -> no cache write."""
        client = _make_mock_redis_client()
        client.set = AsyncMock()
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.cache_verdict("d1", {}, "")

        client.set.assert_not_called()

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_cache_verdict_exception_handled(self, MockRedis):
        """Redis error during write -> exception caught, not raised."""
        client = _make_mock_redis_client()
        client.set = AsyncMock(side_effect=Exception("Redis down"))
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        # Should not raise
        await cache.cache_verdict("d1", self.VERDICT, "pro")


class TestGetVerdict:
    """Test verdict retrieval."""

    VERDICT = {
        "winner": "pro",
        "pro_scores": {"total": 39},
        "con_scores": {"total": 31},
        "summary": "正方获胜。",
    }

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_get_verdict_hit(self, MockRedis):
        """Cache hit -> return dict with 'verdict' and 'winner' keys."""
        cached = json.dumps({"verdict": self.VERDICT, "winner": "pro"})
        client = _make_mock_redis_client()
        client.get = AsyncMock(return_value=cached)
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_verdict("d1")

        assert result is not None
        assert result["verdict"] == self.VERDICT
        assert result["winner"] == "pro"

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_get_verdict_miss(self, MockRedis):
        """Cache miss -> return None."""
        client = _make_mock_redis_client()
        client.get = AsyncMock(return_value=None)
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_verdict("d1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_verdict_disabled_returns_none(self):
        """Cache disabled -> always return None."""
        cache = RedisCache(redis_url=None)
        result = await cache.get_verdict("d1")
        assert result is None

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_get_verdict_exception_returns_none(self, MockRedis):
        """Redis error -> return None (caller falls back to SQLite)."""
        client = _make_mock_redis_client()
        client.get = AsyncMock(side_effect=Exception("Redis down"))
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_verdict("d1")
        assert result is None


class TestGetBatchVerdicts:
    """Test batch verdict retrieval."""

    VERDICT_1 = {"verdict": {"winner": "pro", "summary": "p wins"}, "winner": "pro"}
    VERDICT_2 = {"verdict": {"winner": "con", "summary": "c wins"}, "winner": "con"}

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_all_hit(self, MockRedis):
        """All cached -> return from Redis."""
        client = _make_mock_redis_client()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[
            json.dumps(self.VERDICT_1),
            json.dumps(self.VERDICT_2),
        ])
        client.pipeline.return_value = pipe
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_batch_verdicts(["d1", "d2"])

        assert result is not None
        assert "d1" in result
        assert "d2" in result
        assert result["d1"] == self.VERDICT_1
        assert result["d2"] == self.VERDICT_2

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_all_miss_returns_none(self, MockRedis):
        """All miss -> return None."""
        client = _make_mock_redis_client()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, None])
        client.pipeline.return_value = pipe
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_batch_verdicts(["d1", "d2"])

        assert result is None

    @pytest.mark.asyncio
    async def test_disabled(self):
        """Cache disabled -> return None."""
        cache = RedisCache(redis_url=None)
        result = await cache.get_batch_verdicts(["d1"])
        assert result is None

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_partial_hit(self, MockRedis):
        """Some cached, some miss -> return only hits."""
        client = _make_mock_redis_client()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[
            json.dumps(self.VERDICT_1),
            None,
        ])
        client.pipeline.return_value = pipe
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_batch_verdicts(["d1", "d2"])

        assert result is not None
        assert "d1" in result
        assert "d2" not in result


class TestInvalidateDebateExtended:
    """Test that invalidate_debate also removes verdict key."""

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_invalidate_deletes_verdict_key(self, MockRedis):
        """invalidate_debate removes speeches, summary, AND verdict keys."""
        client = _make_mock_redis_client()
        client.delete = AsyncMock(return_value=1)
        MockRedis.from_url.return_value = client

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.invalidate_debate("d1")

        client.delete.assert_called_once_with(
            "debate:d1:speeches", "debate:d1:summary", "debate:d1:verdict"
        )
