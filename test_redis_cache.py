"""
Unit tests for redis_cache module.

Uses unittest.mock to avoid requiring a real Redis instance.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_mock_redis_client():
    """Create a mock redis.asyncio.Redis with ``ping`` that succeeds.

    Uses MagicMock (not AsyncMock) because some redis methods like
    ``pipeline()`` are synchronous.  Only truly async methods are set
    to AsyncMock explicitly.
    """
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    return client


# ── Tests for RedisCache ─────────────────────────────────────────────────────

# Patch the redis import INSIDE redis_cache module.
# redis_cache does: import redis.asyncio as redis
# So the target is: redis_cache.redis.Redis
REDIS_PATCH = "redis_cache.redis.Redis"


class TestRedisCacheConnection:
    """Test Redis connection lifecycle."""

    @patch(REDIS_PATCH)
    def test_init_connects_with_pool(self, MockRedis):
        """Redis URL configured -> connect with connection pool."""
        client = _make_mock_redis_client()
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")

        assert cache.enabled is True
        assert cache._redis is client
        MockRedis.from_url.assert_called_once_with(
            "redis://localhost:6379/0", max_connections=10, decode_responses=False
        )

    def test_init_no_url_disables_cache(self):
        """Empty REDIS_URL -> cache disabled."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url="")
        assert cache.enabled is False

    def test_init_none_url_disables_cache(self):
        """None REDIS_URL -> cache disabled."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        assert cache.enabled is False

    @patch(REDIS_PATCH)
    def test_init_connection_failure_disables(self, MockRedis):
        """Connection error -> cache disabled gracefully."""
        MockRedis.from_url.side_effect = Exception("Connection refused")

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://down:6379/0")
        assert cache.enabled is False

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_close_cleanup(self, MockRedis):
        """close() releases Redis connection via aclose()."""
        client = _make_mock_redis_client()
        client.aclose = AsyncMock()
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.close()
        client.aclose.assert_awaited_once()


class TestCacheSpeeches:
    """Test speech caching operations."""

    SPEECHES = [
        {"id": 1, "debate_id": "d1", "debater": "pro_1", "phase": "pro_opening",
         "round_num": 1, "thinking": "deep thoughts", "content": "Hello world",
         "seq": 1, "speech_type": "opening", "role_id": "pro_1:pro_opening"},
        {"id": 2, "debate_id": "d1", "debater": "con_1", "phase": "con_opening",
         "round_num": 1, "thinking": "counter thoughts", "content": "No way",
         "seq": 2, "speech_type": "opening", "role_id": "con_1:con_opening"},
    ]

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_cache_speeches_writes_both_keys(self, MockRedis):
        """cache_speeches writes full + summary keys with TTL."""
        client = _make_mock_redis_client()
        client.set = AsyncMock()
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.cache_speeches("d1", self.SPEECHES)

        assert client.set.call_count == 2

        calls = client.set.call_args_list
        # First call: full key
        assert calls[0][0][0] == "debate:d1:speeches"
        full_data = json.loads(calls[0][0][1])
        assert len(full_data) == 2
        assert "thinking" in full_data[0]

        # Second call: summary key (no thinking)
        assert calls[1][0][0] == "debate:d1:summary"
        summary_data = json.loads(calls[1][0][1])
        assert len(summary_data) == 2
        assert "thinking" not in summary_data[0]

        # TTL
        for call in calls:
            assert call[1]["ex"] == 86400

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_cache_speeches_empty_skips(self, MockRedis):
        """Empty speeches list -> no cache write."""
        client = _make_mock_redis_client()
        client.set = AsyncMock()
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.cache_speeches("d1", [])

        client.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_speeches_disabled_skips(self):
        """Cache disabled -> cache_speeches is no-op."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        # Should not raise
        await cache.cache_speeches("d1", self.SPEECHES)

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_cache_speeches_exception_handled(self, MockRedis):
        """Redis error during write -> exception caught, not raised."""
        client = _make_mock_redis_client()
        client.set = AsyncMock(side_effect=Exception("Redis down"))
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        # Should not raise
        await cache.cache_speeches("d1", self.SPEECHES)


class TestGetSpeeches:
    """Test speech retrieval."""

    SPEECHES = [
        {"id": 1, "debate_id": "d1", "debater": "pro_1", "content": "Hi",
         "thinking": "th", "phase": "pro_opening", "round_num": 1,
         "seq": 1, "speech_type": "opening"},
    ]

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_get_speeches_hit(self, MockRedis):
        """Cache hit -> return parsed speeches."""
        client = _make_mock_redis_client()
        client.get = AsyncMock(return_value=json.dumps(self.SPEECHES))
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_speeches("d1")

        assert result is not None
        assert len(result) == 1
        assert result[0]["content"] == "Hi"

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_get_speeches_miss(self, MockRedis):
        """Cache miss -> return None."""
        client = _make_mock_redis_client()
        client.get = AsyncMock(return_value=None)
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_speeches("d1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_speeches_disabled_returns_none(self):
        """Cache disabled -> always return None."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        result = await cache.get_speeches("d1")
        assert result is None

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_get_speeches_exception_returns_none(self, MockRedis):
        """Redis error -> return None (caller falls back to SQLite)."""
        client = _make_mock_redis_client()
        client.get = AsyncMock(side_effect=Exception("Redis down"))
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_speeches("d1")
        assert result is None


class TestGetSpeechesSummary:
    """Test summary retrieval."""

    SUMMARIES = [
        {"id": 1, "debate_id": "d1", "debater": "pro_1", "content": "Hi",
         "phase": "pro_opening", "round_num": 1, "seq": 1,
         "speech_type": "opening", "role_id": "pro_1:pro_opening"},
    ]

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_get_summary_hit(self, MockRedis):
        """Cache hit -> return parsed summaries."""
        client = _make_mock_redis_client()
        client.get = AsyncMock(return_value=json.dumps(self.SUMMARIES))
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_speeches_summary("d1")

        assert result is not None
        assert len(result) == 1
        assert "thinking" not in result[0]


class TestGetBatchSummaries:
    """Test batch summary retrieval."""

    SUMMARIES_1 = [{"debater": "pro_1", "content": "Hi"}]
    SUMMARIES_2 = [{"debater": "con_1", "content": "No"}]

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_all_hit(self, MockRedis):
        """All cached -> return from Redis without SQLite."""
        client = _make_mock_redis_client()
        # pipeline() returns a Pipeline — .get() is sync, .execute() is async
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[
            json.dumps(self.SUMMARIES_1),
            json.dumps(self.SUMMARIES_2),
        ])
        client.pipeline.return_value = pipe
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_batch_summaries(["d1", "d2"])

        assert result is not None
        assert "d1" in result
        assert "d2" in result
        assert result["d1"] == self.SUMMARIES_1
        assert result["d2"] == self.SUMMARIES_2

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_all_miss_returns_none(self, MockRedis):
        """All miss -> return None (caller queries SQLite)."""
        client = _make_mock_redis_client()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, None])
        client.pipeline.return_value = pipe
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_batch_summaries(["d1", "d2"])

        assert result is None

    @pytest.mark.asyncio
    async def test_disabled(self):
        """Cache disabled -> return None."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        result = await cache.get_batch_summaries(["d1"])
        assert result is None

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_partial_hit(self, MockRedis):
        """Some cached, some miss -> return only hits."""
        client = _make_mock_redis_client()
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=[
            json.dumps(self.SUMMARIES_1),
            None,
        ])
        client.pipeline.return_value = pipe
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        result = await cache.get_batch_summaries(["d1", "d2"])

        assert result is not None
        assert "d1" in result
        assert "d2" not in result


class TestInvalidateDebate:
    """Test cache invalidation."""

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_invalidate_deletes_both_keys(self, MockRedis):
        """invalidate_debate removes speeches, summary, and verdict keys."""
        client = _make_mock_redis_client()
        client.delete = AsyncMock(return_value=1)
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.invalidate_debate("d1")

        client.delete.assert_called_once_with(
            "debate:d1:speeches", "debate:d1:summary", "debate:d1:verdict"
        )

    @pytest.mark.asyncio
    async def test_invalidate_disabled_skips(self):
        """Cache disabled -> no-op."""
        from redis_cache import RedisCache
        cache = RedisCache(redis_url=None)
        # Should not raise
        await cache.invalidate_debate("d1")

    @patch(REDIS_PATCH)
    @pytest.mark.asyncio
    async def test_invalidate_exception_handled(self, MockRedis):
        """Redis error during delete -> exception caught."""
        client = _make_mock_redis_client()
        client.delete = AsyncMock(side_effect=Exception("Redis down"))
        MockRedis.from_url.return_value = client

        from redis_cache import RedisCache
        cache = RedisCache(redis_url="redis://localhost:6379/0")
        # Should not raise
        await cache.invalidate_debate("d1")


class TestGlobalSingleton:
    """Test module-level singleton pattern."""

    def teardown_method(self):
        """Reset singleton between tests."""
        import redis_cache
        redis_cache._redis_cache = None

    def test_get_redis_creates_singleton(self):
        """get_redis with URL creates singleton."""
        import redis_cache
        redis_cache._redis_cache = None

        with patch("redis_cache.RedisCache") as MockCache:
            mock_instance = MockCache.return_value
            mock_instance.enabled = True
            result = redis_cache.get_redis("redis://localhost:6379/0")
            assert result is mock_instance
            MockCache.assert_called_once_with(redis_url="redis://localhost:6379/0")

    def test_get_redis_returns_existing(self):
        """Second call returns same instance regardless of URL."""
        import redis_cache
        existing = MagicMock()
        redis_cache._redis_cache = existing

        result = redis_cache.get_redis("redis://other:6379/0")
        assert result is existing
