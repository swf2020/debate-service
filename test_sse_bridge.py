"""
Tests for debate-service/sse_bridge.py.

Run::

    cd debate-service && source .venv/bin/activate && python test_sse_bridge.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import traceback
from contextlib import contextmanager

from models import SSEPhaseStart, SSEThinkingChunk, SSESpeechChunk
from sse_bridge import SSEBridge, sse_bridge

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def run_test(name: str, fn):
    print(f"\n=== {name} ===")
    try:
        fn()
    except Exception:
        global failed
        failed += 1
        traceback.print_exc()
        print(f"  FAIL  {name} (unhandled exception)")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


@contextmanager
def _loop_context():
    """Provide a running event loop for tests that need ``asyncio.Queue``."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _reset(bridge: SSEBridge) -> None:
    """Wipe internal state so each test starts cleanly."""
    bridge._queues = {}
    bridge._loop = None


def _flush(loop: asyncio.AbstractEventLoop) -> None:
    """Run loop briefly to flush callbacks scheduled via
    ``call_soon_threadsafe``.

    ``push()`` uses ``call_soon_threadsafe`` which places the callback on
    the event loop's ready queue but does *not* execute it until the loop
    runs.  This helper runs one iteration to drain those callbacks.
    """
    loop.run_until_complete(asyncio.sleep(0))


# ------------------------------------------------------------------
# 1. Singleton
# ------------------------------------------------------------------


def test_1_singleton():
    b1 = SSEBridge()
    b2 = SSEBridge()
    check("SSEBridge() returns same instance", b1 is b2)
    check("module-level sse_bridge is same instance", sse_bridge is b1)


# ------------------------------------------------------------------
# 2. Subscribe
# ------------------------------------------------------------------


def test_2_subscribe_creates_queue():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context():
        q = bridge.subscribe("debate-001")
        check("returns asyncio.Queue", isinstance(q, asyncio.Queue))
        check("queue is empty", q.empty())
        check("queue registered under debate-001", q in bridge._queues["debate-001"])
        check("len(_queues[debate-001]) == 1", len(bridge._queues["debate-001"]) == 1)


# ------------------------------------------------------------------
# 3. Multiple subscribers
# ------------------------------------------------------------------


def test_3_multiple_subscribers():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context():
        q1 = bridge.subscribe("debate-001")
        q2 = bridge.subscribe("debate-001")
        q3 = bridge.subscribe("debate-001")
        check("three queues created", len(bridge._queues["debate-001"]) == 3)
        check("q1 distinct from q2", q1 is not q2)
        check("q2 distinct from q3", q2 is not q3)
        # Verify all three exist in the list
        check("q1 in list", q1 in bridge._queues["debate-001"])
        check("q2 in list", q2 in bridge._queues["debate-001"])
        check("q3 in list", q3 in bridge._queues["debate-001"])


# ------------------------------------------------------------------
# 4. Unsubscribe
# ------------------------------------------------------------------


def test_4_unsubscribe():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context():
        q1 = bridge.subscribe("debate-001")
        q2 = bridge.subscribe("debate-001")
        bridge.unsubscribe("debate-001", q1)
        check("q1 removed", q1 not in bridge._queues["debate-001"])
        check("q2 still present", q2 in bridge._queues["debate-001"])
        check("len is 1 after removal", len(bridge._queues["debate-001"]) == 1)

        # Removing again should be a no-op
        bridge.unsubscribe("debate-001", q1)
        check("double remove is no-op", len(bridge._queues["debate-001"]) == 1)

        # Removing from non-existent debate is a no-op
        bridge.unsubscribe("nonexistent", q1)
        check("unsubscribe unknown debate is no-op", True)

        # Removing a queue that was never added is a no-op
        orphan_q: asyncio.Queue[str] = asyncio.Queue()
        bridge.unsubscribe("debate-001", orphan_q)
        check("unsubscribe orphan queue is no-op", len(bridge._queues["debate-001"]) == 1)


# ------------------------------------------------------------------
# 5. Push formats SSE data correctly
# ------------------------------------------------------------------


def test_5_push_formats_sse():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context() as loop:
        bridge.set_loop(loop)
        q = bridge.subscribe("debate-001")

        event = SSEPhaseStart(
            debate_id="debate-001", phase="opening", debater="pro_1", round_num=1
        )
        bridge.push("debate-001", event)
        _flush(loop)

        check("1 item in queue after push", q.qsize() == 1)

        item = q.get_nowait()
        expected = f"data: {event.model_dump_json()}\n\n"
        check("SSE format is 'data: <json>\\n\\n'", item == expected)

        # Verify the JSON payload round-trips correctly
        payload = item.removeprefix("data: ").removesuffix("\n\n")
        parsed = json.loads(payload)
        check("JSON type field", parsed["type"] == "phase_start")
        check("JSON debate_id field", parsed["debate_id"] == "debate-001")


# ------------------------------------------------------------------
# 6. Multiple subscribers all receive the same data
# ------------------------------------------------------------------


def test_6_push_to_multiple_subscribers():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context() as loop:
        bridge.set_loop(loop)
        q1 = bridge.subscribe("debate-001")
        q2 = bridge.subscribe("debate-001")

        event = SSEThinkingChunk(
            debate_id="debate-001", debater="pro_1", content="Hmm, let me think..."
        )
        bridge.push("debate-001", event)
        _flush(loop)

        expected = f"data: {event.model_dump_json()}\n\n"
        check("q1 received data", q1.get_nowait() == expected)
        check("q2 received data", q2.get_nowait() == expected)
        check("both queues now empty", q1.empty() and q2.empty())


# ------------------------------------------------------------------
# 7. Push is a no-op when no loop is set
# ------------------------------------------------------------------


def test_7_push_noop_without_loop():
    bridge = SSEBridge()
    _reset(bridge)
    bridge._loop = None
    with _loop_context():
        q = bridge.subscribe("debate-001")
        event = SSESpeechChunk(
            debate_id="debate-001", debater="pro_1", content="Hello world"
        )
        bridge.push("debate-001", event)
        check("queue is empty when no loop set", q.empty())


# ------------------------------------------------------------------
# 8. Push is a no-op when debate_id does not exist
# ------------------------------------------------------------------


def test_8_push_noop_unknown_debate():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context() as loop:
        bridge.set_loop(loop)
        bridge.subscribe("debate-001")
        event = SSESpeechChunk(
            debate_id="debate-999", debater="pro_1", content="Hello"
        )
        bridge.push("debate-999", event)
        check("no queues created for unknown debate", "debate-999" not in bridge._queues)


# ------------------------------------------------------------------
# 9. Thread-safe push (simulates agent thread calling push)
# ------------------------------------------------------------------


def test_9_thread_safe_push():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context() as loop:
        bridge.set_loop(loop)
        q = bridge.subscribe("debate-001")

        event = SSEThinkingChunk(
            debate_id="debate-001", debater="con_1", content="I disagree because..."
        )
        expected = f"data: {event.model_dump_json()}\n\n"

        # Simulate an agent thread calling push()
        t = threading.Thread(target=bridge.push, args=("debate-001", event))
        t.start()
        t.join()
        _flush(loop)

        check("1 item after thread push", q.qsize() == 1)
        check("thread push data correct", q.get_nowait() == expected)


# ------------------------------------------------------------------
# 10. remove_debate cleans up
# ------------------------------------------------------------------


def test_10_remove_debate():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context():
        bridge.subscribe("debate-001")
        bridge.subscribe("debate-002")

        check("debate-001 exists", "debate-001" in bridge._queues)
        check("debate-002 exists", "debate-002" in bridge._queues)

        bridge.remove_debate("debate-001")
        check("debate-001 removed", "debate-001" not in bridge._queues)
        check("debate-002 still exists", "debate-002" in bridge._queues)

        # Removing again is a no-op (dict.pop with default)
        bridge.remove_debate("debate-001")
        check("double remove is no-op", True)

        # Removing non-existent debate is a no-op
        bridge.remove_debate("nonexistent")
        check("remove unknown debate is no-op", True)


# ------------------------------------------------------------------
# 11. Multiple debate IDs are isolated
# ------------------------------------------------------------------


def test_11_debate_isolation():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context() as loop:
        bridge.set_loop(loop)
        q_a = bridge.subscribe("debate-A")
        q_b = bridge.subscribe("debate-B")

        event_a = SSEPhaseStart(
            debate_id="debate-A", phase="opening", debater="pro_1", round_num=1
        )
        event_b = SSEPhaseStart(
            debate_id="debate-B", phase="opening", debater="con_1", round_num=1
        )

        bridge.push("debate-A", event_a)
        _flush(loop)
        check("debate-A queue has 1 item", q_a.qsize() == 1)
        check("debate-B queue is empty", q_b.empty())

        bridge.push("debate-B", event_b)
        _flush(loop)
        check("debate-B queue has 1 item", q_b.qsize() == 1)

        data_a = q_a.get_nowait()
        data_b = q_b.get_nowait()
        check("push to A only reaches A", "debate-A" in data_a)
        check("push to B only reaches B", "debate-B" in data_b)


# ------------------------------------------------------------------
# 12. set_loop does not raise
# ------------------------------------------------------------------


def test_12_set_loop():
    bridge = SSEBridge()
    _reset(bridge)
    with _loop_context() as loop:
        bridge.set_loop(loop)
        check("loop was stored", bridge._loop is loop)


# ------------------------------------------------------------------
# run all
# ------------------------------------------------------------------


def main():
    run_test("Singleton pattern", test_1_singleton)
    run_test("Subscribe creates queue", test_2_subscribe_creates_queue)
    run_test("Multiple subscribers", test_3_multiple_subscribers)
    run_test("Unsubscribe", test_4_unsubscribe)
    run_test("Push formats SSE data", test_5_push_formats_sse)
    run_test("Push to multiple subscribers", test_6_push_to_multiple_subscribers)
    run_test("Push is noop without loop", test_7_push_noop_without_loop)
    run_test("Push is noop unknown debate", test_8_push_noop_unknown_debate)
    run_test("Thread-safe push", test_9_thread_safe_push)
    run_test("remove_debate cleanup", test_10_remove_debate)
    run_test("Debate isolation", test_11_debate_isolation)
    run_test("set_loop", test_12_set_loop)

    print(f"\n{'=' * 40}")
    print(f"  Passed: {passed}  |  Failed: {failed}")
    print(f"{'=' * 40}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
