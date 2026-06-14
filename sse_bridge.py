"""
Thread-safe singleton bridge that relays crewAI agent callbacks (running in
ThreadPoolExecutor worker threads) to asyncio SSE clients (running in the
FastAPI event loop).

Usage::

    from sse_bridge import sse_bridge

    # 1. On FastAPI startup (main.py lifespan):
    sse_bridge.set_loop(asyncio.get_running_loop())

    # 2. In an SSE endpoint (main.py):
    q = sse_bridge.subscribe(debate_id)
    try:
        while True:
            data = await q.get()
            yield data
    finally:
        sse_bridge.unsubscribe(debate_id, q)

    # 3. In agent callbacks (debate_flow.py):
    from sse_bridge import sse_bridge
    sse_bridge.push(debate_id, SSEThinkingChunk(...))
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel


class SSEBridge:
    """Thread-safe bridge between agent threads and asyncio SSE streams.

    This is a singleton — use the module-level ``sse_bridge`` instance.
    """

    _instance: SSEBridge | None = None

    def __new__(cls) -> SSEBridge:
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._queues: dict[str, list[asyncio.Queue[str]]] = {}
            obj._loop: asyncio.AbstractEventLoop | None = None
            cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the main event loop.

        Must be called exactly once during FastAPI lifespan startup.
        All subsequent ``push()`` calls will schedule work on *loop*.
        """
        self._loop = loop

    # ------------------------------------------------------------------
    # Subscriber management (called from asyncio context)
    # ------------------------------------------------------------------

    def subscribe(self, debate_id: str) -> asyncio.Queue[str]:
        """Register a new SSE subscriber for *debate_id*.

        Returns an ``asyncio.Queue`` that the caller should ``await q.get()``
        on in a loop.
        """
        if debate_id not in self._queues:
            self._queues[debate_id] = []
        q: asyncio.Queue[str] = asyncio.Queue()
        self._queues[debate_id].append(q)
        return q

    def unsubscribe(self, debate_id: str, q: asyncio.Queue[str]) -> None:
        """Remove *q* from the subscriber list for *debate_id*.

        Safe to call even if *q* has already been removed or the debate
        does not exist.
        """
        if debate_id in self._queues:
            try:
                self._queues[debate_id].remove(q)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Pushing events (thread-safe — called from agent threads)
    # ------------------------------------------------------------------

    def push(self, debate_id: str, event: BaseModel) -> None:
        """Serialize *event* to SSE wire format and enqueue it to every
        subscriber of *debate_id*.

        This method is thread-safe: it uses ``call_soon_threadsafe`` to
        schedule ``Queue.put_nowait`` on the main event loop.
        """
        if self._loop is None or debate_id not in self._queues:
            return

        data = f"data: {event.model_dump_json()}\n\n"

        for q in self._queues[debate_id]:
            self._loop.call_soon_threadsafe(q.put_nowait, data)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def remove_debate(self, debate_id: str) -> None:
        """Drop all subscriber queues for *debate_id*.

        Call this when a debate finishes (normally or with an error) to
        release resources.
        """
        self._queues.pop(debate_id, None)


# Module-level singleton — import this everywhere else.
sse_bridge: SSEBridge = SSEBridge()
