"""
Tests for db.py — SQLite persistence layer.

Uses a temporary file-backed database to avoid polluting the working directory.
Each test cleans up after itself by removing the temp file.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import traceback

# ── Swap DB_PATH to a temporary file ────────────────────────────────────────

_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
TMP_DB = _tmp.name
_tmp.close()

import db  # noqa: E402

db.DB_PATH = TMP_DB  # redirect all connections to our temp file


# ── Test helpers ────────────────────────────────────────────────────────────


def ok(label: str) -> None:
    print(f"  OK  {label}")


def fail(label: str, msg: str) -> None:
    print(f"  FAIL  {label}: {msg}")
    # Keep going — collect all failures.


async def run_tests() -> int:
    """Run all tests.  Returns the number of failures."""
    failures = 0

    # ── init_db ─────────────────────────────────────────────────────────
    print("\n=== init_db ===")
    try:
        await db.init_db()
        # Verify tables exist by querying sqlite_master
        conn = await db.get_db()
        try:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row["name"] for row in await cur.fetchall()}
            assert "debates" in tables, f"debates table missing; got {tables}"
            assert "speeches" in tables, f"speeches table missing; got {tables}"
            ok("tables created")

            cur2 = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_speeches_debate_id'"
            )
            assert await cur2.fetchone() is not None, "index not found"
            ok("index created")
        finally:
            await conn.close()
    except Exception as exc:
        fail("init_db", str(exc))
        failures += 1

    # ── create_debate ───────────────────────────────────────────────────
    print("\n=== create_debate ===")
    try:
        await db.create_debate(
            id="deb-1",
            topic="AI safety",
            total_rounds=2,
            pro_skills={"debater_1": None, "debater_2": "karpathy-llm-wiki"},
            con_skills={"debater_1": "munger-perspective"},
            judge_skill="stop-slop",
        )
        ok("inserted debate deb-1")

        debate = await db.get_debate("deb-1")
        assert debate is not None, "get_debate returned None"
        assert debate["topic"] == "AI safety"
        assert debate["total_rounds"] == 2
        assert debate["status"] == "running"
        assert debate["pro_skills"] == {"debater_1": None, "debater_2": "karpathy-llm-wiki"}
        assert debate["con_skills"] == {"debater_1": "munger-perspective"}
        assert debate["judge_skill"] == "stop-slop"
        assert debate["winner"] is None
        assert debate["verdict"] is None
        ok("create_debate + get_debate match")
    except Exception as exc:
        fail("create_debate", str(exc))
        failures += 1

    # ── get_debate — not found ──────────────────────────────────────────
    print("\n=== get_debate (missing) ===")
    try:
        result = await db.get_debate("nonexistent")
        assert result is None, f"expected None, got {result}"
        ok("returns None for missing debate")
    except Exception as exc:
        fail("get_debate missing", str(exc))
        failures += 1

    # ── insert_speech ───────────────────────────────────────────────────
    print("\n=== insert_speech ===")
    try:
        speech_id = await db.insert_speech(
            debate_id="deb-1",
            debater="pro",
            phase="opening",
            round_num=1,
            thinking="Let me think...",
            content="AI safety is critical.",
            seq=1,
        )
        assert isinstance(speech_id, int) and speech_id > 0, \
            f"expected positive int, got {speech_id!r}"
        ok(f"speech inserted with id={speech_id}")

        speech_id2 = await db.insert_speech(
            debate_id="deb-1",
            debater="con",
            phase="opening",
            round_num=1,
            thinking=None,
            content="I disagree.",
            seq=2,
        )
        assert speech_id2 == speech_id + 1, \
            f"expected id={speech_id + 1}, got {speech_id2}"
        ok("auto-increment works")
    except Exception as exc:
        fail("insert_speech", str(exc))
        failures += 1

    # ── get_speeches — order by seq ─────────────────────────────────────
    print("\n=== get_speeches (ordering) ===")
    try:
        speeches = await db.get_speeches("deb-1")
        assert len(speeches) == 2, f"expected 2 speeches, got {len(speeches)}"
        assert speeches[0]["seq"] == 1
        assert speeches[1]["seq"] == 2
        assert speeches[0]["content"] == "AI safety is critical."
        assert speeches[1]["content"] == "I disagree."
        assert speeches[0]["debate_id"] == "deb-1"
        assert speeches[0]["debater"] == "pro"
        assert speeches[0]["thinking"] == "Let me think..."
        assert speeches[1]["thinking"] is None
        ok("speeches returned in seq order with correct fields")
    except Exception as exc:
        fail("get_speeches ordering", str(exc))
        failures += 1

    # ── get_speeches — empty ────────────────────────────────────────────
    print("\n=== get_speeches (empty) ===")
    try:
        empty = await db.get_speeches("deb-nonexistent")
        assert empty == [], f"expected empty list, got {empty}"
        ok("returns [] for debate with no speeches")
    except Exception as exc:
        fail("get_speeches empty", str(exc))
        failures += 1

    # ── update_debate_status ────────────────────────────────────────────
    print("\n=== update_debate_status ===")
    try:
        await db.update_debate_status("deb-1", "paused")
        debate = await db.get_debate("deb-1")
        assert debate is not None
        assert debate["status"] == "paused"
        assert debate["finished_at"] is None, \
            "finished_at should be None for non-finished status"
        ok("status updated to paused, finished_at remains None")
    except Exception as exc:
        fail("update_debate_status paused", str(exc))
        failures += 1

    # ── update_debate_status — finished sets finished_at ────────────────
    print("\n=== update_debate_status (finished) ===")
    try:
        await db.update_debate_status("deb-1", "finished")
        debate = await db.get_debate("deb-1")
        assert debate is not None
        assert debate["status"] == "finished"
        assert debate["finished_at"] is not None, \
            "finished_at should be set when status=finished"
        ok("status updated to finished, finished_at is set")
    except Exception as exc:
        fail("update_debate_status finished", str(exc))
        failures += 1

    # ── set_verdict ─────────────────────────────────────────────────────
    print("\n=== set_verdict ===")
    try:
        # Reset deb-1 to running first for a clean test
        conn = await db.get_db()
        try:
            await conn.execute(
                "UPDATE debates SET status='running', finished_at=NULL WHERE id='deb-1'"
            )
            await conn.commit()
        finally:
            await conn.close()

        verdict_data = {"winner": "pro", "reason": "Stronger arguments", "scores": {"pro": 8, "con": 5}}
        await db.set_verdict("deb-1", "pro", verdict_data)

        debate = await db.get_debate("deb-1")
        assert debate is not None
        assert debate["winner"] == "pro"
        assert debate["verdict"] == verdict_data
        assert debate["status"] == "finished"
        assert debate["finished_at"] is not None
        ok("set_verdict updates winner / verdict / status / finished_at")
    except Exception as exc:
        fail("set_verdict", str(exc))
        failures += 1

    # ── JSON round-trip (null / non-null) ───────────────────────────────
    print("\n=== JSON round-trip ===")
    try:
        await db.create_debate(
            id="deb-json",
            topic="JSON test",
            total_rounds=1,
            pro_skills={},
            con_skills={"debater_1": "some-skill", "debater_2": None},
            judge_skill=None,
        )
        debate = await db.get_debate("deb-json")
        assert debate is not None
        assert debate["pro_skills"] == {}
        assert debate["con_skills"] == {"debater_1": "some-skill", "debater_2": None}
        assert debate["judge_skill"] is None
        assert debate["verdict"] is None
        ok("JSON fields round-trip correctly (empty dict, null values)")
    except Exception as exc:
        fail("JSON round-trip", str(exc))
        failures += 1

    return failures


def main() -> int:
    print("=" * 50)
    print("db.py test suite")
    print("=" * 50)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        failures = loop.run_until_complete(run_tests())
    finally:
        loop.close()
        # Cleanup temp file
        try:
            os.unlink(TMP_DB)
        except OSError:
            pass

    print()
    if failures:
        print(f"  ** {failures} test(s) FAILED **")
    else:
        print("  ** ALL TESTS PASSED **")
    print()
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
