"""
SQLite persistence layer for the debate service.

All functions open a fresh connection via :func:`get_db` and close it in a
``finally`` block.  JSON fields (``pro_skills``, ``con_skills``, ``verdict``)
are stored as TEXT columns and serialised/deserialised with ``json``.
"""

from __future__ import annotations

import json
import os

import aiosqlite

DB_PATH = os.environ.get("DEBATE_DB_PATH", "debate.db")


# ── Connection helpers ──────────────────────────────────────────────────────


async def get_db() -> aiosqlite.Connection:
    """Create a new connection with WAL mode and foreign keys enabled."""
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    db.row_factory = aiosqlite.Row
    return db


# ── Startup / shutdown ──────────────────────────────────────────────────────


async def init_db() -> None:
    """Create tables and index if they don't exist. Migrate existing DBs."""
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS debates (
                id           TEXT PRIMARY KEY,
                topic        TEXT NOT NULL,
                total_rounds INT DEFAULT 2,
                status       TEXT DEFAULT 'running',
                pro_skills   TEXT,
                con_skills   TEXT,
                judge_skill  TEXT,
                winner       TEXT,
                verdict      TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at  DATETIME
            );

            CREATE TABLE IF NOT EXISTS speeches (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                debate_id  TEXT NOT NULL,
                debater    TEXT NOT NULL,
                phase      TEXT NOT NULL,
                round_num  INT NOT NULL,
                thinking   TEXT,
                content    TEXT NOT NULL,
                seq        INT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (debate_id) REFERENCES debates(id)
            );

            CREATE INDEX IF NOT EXISTS idx_speeches_debate_id
                ON speeches(debate_id);
        """)
        await db.commit()

        # Migrate: add columns if missing (safe for fresh + existing DBs)
        existing = await db.execute("PRAGMA table_info(debates)")
        columns = {row[1] for row in await existing.fetchall()}

        if "current_debater" not in columns:
            await db.execute(
                "ALTER TABLE debates ADD COLUMN current_debater TEXT DEFAULT ''"
            )
        if "debater_status" not in columns:
            await db.execute(
                "ALTER TABLE debates ADD COLUMN debater_status TEXT DEFAULT '{}'"
            )
        await db.commit()
    finally:
        await db.close()


async def close_db() -> None:
    """No-op -- each connection is closed after use."""
    pass


# ── Debates CRUD ────────────────────────────────────────────────────────────


async def create_debate(
    id: str,
    topic: str,
    total_rounds: int,
    pro_skills: dict,
    con_skills: dict,
    judge_skill: str | None,
) -> None:
    """INSERT a new debate row."""
    db = await get_db()
    try:
        default_status = json.dumps({
            "pro_1": "waiting", "pro_2": "waiting", "pro_3": "waiting",
            "con_1": "waiting", "con_2": "waiting", "con_3": "waiting",
            "judge": "waiting",
        })
        await db.execute(
            """
            INSERT INTO debates (id, topic, total_rounds, pro_skills, con_skills,
                                 judge_skill, current_debater, debater_status)
            VALUES (?, ?, ?, ?, ?, ?, '', ?)
            """,
            (id, topic, total_rounds, json.dumps(pro_skills),
             json.dumps(con_skills), judge_skill, default_status),
        )
        await db.commit()
    finally:
        await db.close()


async def update_debate_status(id: str, status: str) -> None:
    """UPDATE status.

    If *status* is ``'finished'``, also set ``finished_at = CURRENT_TIMESTAMP``.
    """
    db = await get_db()
    try:
        if status == "finished":
            await db.execute(
                """
                UPDATE debates
                SET status = ?, finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, id),
            )
        else:
            await db.execute(
                "UPDATE debates SET status = ? WHERE id = ?",
                (status, id),
            )
        await db.commit()
    finally:
        await db.close()


async def set_verdict(id: str, winner: str, verdict: dict) -> None:
    """UPDATE winner, verdict (as JSON string), and set status to ``'finished'``."""
    db = await get_db()
    try:
        await db.execute(
            """
            UPDATE debates
            SET winner = ?, verdict = ?, status = 'finished', finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (winner, json.dumps(verdict), id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_active_debate() -> dict | None:
    """Return the most recent debate with status != 'finished'.

    Returns ``None`` when no active debate exists.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM debates WHERE status != 'finished' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_debate(row)
    finally:
        await db.close()


async def get_debate(debate_id: str) -> dict | None:
    """SELECT a debate by id.

    Parses ``pro_skills``, ``con_skills``, and ``verdict`` from JSON strings.
    Returns ``None`` if not found.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM debates WHERE id = ?",
            (debate_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_debate(row)
    finally:
        await db.close()


def _row_to_debate(row: aiosqlite.Row) -> dict:
    """Convert a raw debates row to a dict, parsing JSON columns."""
    d = dict(row)
    for col in ("pro_skills", "con_skills", "verdict", "debater_status"):
        raw = d.get(col)
        if raw is not None:
            d[col] = json.loads(raw)
    return d


async def get_all_debates() -> list[dict]:
    """SELECT all debates, ordered by created_at DESC."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, topic, status, total_rounds, winner, created_at, "
            "finished_at FROM debates ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Speeches CRUD ───────────────────────────────────────────────────────────


async def insert_speech(
    debate_id: str,
    debater: str,
    phase: str,
    round_num: int,
    thinking: str | None,
    content: str,
    seq: int,
) -> int:
    """INSERT a speech row.  Returns the auto-incremented id."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            INSERT INTO speeches (debate_id, debater, phase, round_num, thinking, content, seq)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (debate_id, debater, phase, round_num, thinking, content, seq),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def get_speeches(debate_id: str) -> list[dict]:
    """SELECT all speeches for a debate, ORDER BY seq.  Returns list of dicts."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM speeches WHERE debate_id = ? ORDER BY seq",
            (debate_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()
