"""
Redis cache layer for debate speeches.

Provides a singleton RedisCache that gracefully degrades to SQLite
when Redis is unavailable.  All public methods are no-ops when
``enabled`` is ``False``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_TTL = 86400  # 24 hours
SUMMARY_FIELDS = {"id", "debate_id", "debater", "phase", "round_num",
                  "content", "seq", "speech_type", "role_id"}


def _make_summary(speech: dict) -> dict:
    """Strip thinking and created_at fields to produce a lightweight summary."""
    return {k: v for k, v in speech.items() if k in SUMMARY_FIELDS}


# ── RedisCache ───────────────────────────────────────────────────────────────


class RedisCache:
    """Async Redis cache client for debate speeches.

    Usage::

        cache = RedisCache(redis_url="redis://localhost:6379/0")
        await cache.cache_speeches(debate_id, speeches)
        speeches = await cache.get_speeches(debate_id)  # None if miss
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis: redis.Redis | None = None
        self.enabled = False

        if not redis_url:
            logger.info("REDIS_URL not set — cache disabled")
            return

        try:
            self._redis = redis.Redis.from_url(
                redis_url,
                max_connections=10,
                decode_responses=False,
            )
            self.enabled = True
            logger.info("Redis cache initialised: %s", redis_url)
        except Exception as exc:
            logger.warning("Redis connection failed (%s) — cache disabled", exc)

    # ── Low-level helpers ────────────────────────────────────────────────

    async def _ensure_connected(self) -> bool:
        """Lightweight ping check.  Returns True if Redis is reachable."""
        if not self._redis or not self.enabled:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Release the Redis connection pool."""
        if self._redis:
            await self._redis.aclose()
            logger.info("Redis connection closed")

    # ── Public API ───────────────────────────────────────────────────────

    async def cache_speeches(self, debate_id: str, speeches: list[dict]) -> None:
        """Write full and summary speech arrays to Redis.

        No-op when cache is disabled or speeches is empty.
        Errors are logged but never raised.
        """
        if not self.enabled or not speeches:
            return

        try:
            full_key = f"debate:{debate_id}:speeches"
            summary_key = f"debate:{debate_id}:summary"

            full_json = json.dumps(speeches, ensure_ascii=False)
            summary_json = json.dumps(
                [_make_summary(s) for s in speeches],
                ensure_ascii=False,
            )

            await self._redis.set(full_key, full_json, ex=DEFAULT_TTL)  # type: ignore[union-attr]
            await self._redis.set(summary_key, summary_json, ex=DEFAULT_TTL)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Failed to cache speeches for %s: %s", debate_id, exc)

    async def get_speeches(self, debate_id: str) -> list[dict] | None:
        """Return cached full speeches, or ``None`` on miss / error."""
        if not self.enabled:
            return None

        try:
            raw = await self._redis.get(f"debate:{debate_id}:speeches")  # type: ignore[union-attr]
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis read failed for %s: %s", debate_id, exc)
            return None

    async def get_speeches_summary(self, debate_id: str) -> list[dict] | None:
        """Return cached speech summaries (no thinking), or ``None`` on miss."""
        if not self.enabled:
            return None

        try:
            raw = await self._redis.get(f"debate:{debate_id}:summary")  # type: ignore[union-attr]
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis read summary failed for %s: %s", debate_id, exc)
            return None

    async def get_batch_summaries(
        self, debate_ids: list[str]
    ) -> dict[str, list[dict]] | None:
        """Batch-fetch summaries for multiple debates using Redis pipeline.

        Returns a mapping ``{debate_id: [speech_summary, ...]}`` for all
        cached debates.  Returns ``None`` when *every* key is a miss
        (indicating that the caller should fall back to SQLite for all).

        Keys that miss are simply omitted from the returned dict.
        """
        if not self.enabled or not debate_ids:
            return None

        try:
            keys = [f"debate:{did}:summary" for did in debate_ids]
            pipe = self._redis.pipeline()  # type: ignore[union-attr]
            for k in keys:
                pipe.get(k)
            results = await pipe.execute()

            output: dict[str, list[dict]] = {}
            for did, raw in zip(debate_ids, results):
                if raw is not None:
                    output[did] = json.loads(raw)

            return output if output else None
        except Exception as exc:
            logger.warning("Redis batch read failed: %s", exc)
            return None

    async def invalidate_debate(self, debate_id: str) -> None:
        """Delete both cached keys for a debate.  No-op / error swallowed."""
        if not self.enabled:
            return

        try:
            await self._redis.delete(  # type: ignore[union-attr]
                f"debate:{debate_id}:speeches",
                f"debate:{debate_id}:summary",
            )
        except Exception as exc:
            logger.warning("Redis invalidate failed for %s: %s", debate_id, exc)


# ── Module-level singleton ───────────────────────────────────────────────────

_redis_cache: RedisCache | None = None


def get_redis(redis_url: str | None = None) -> RedisCache:
    """Return the module-level RedisCache singleton.

    On first call, create the instance using *redis_url* (which defaults
    to ``REDIS_URL`` from the environment).  Subsequent calls return the
    same instance regardless of the *redis_url* argument.
    """
    global _redis_cache
    if _redis_cache is None:
        url = redis_url if redis_url is not None else os.environ.get("REDIS_URL", "")
        _redis_cache = RedisCache(redis_url=url)
    return _redis_cache
