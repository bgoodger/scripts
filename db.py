"""SQLite database layer for the 360 feedback tool."""

import os
import sqlite3
import json
from datetime import datetime, date
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "./360_feedback.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                slack_id  TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                manager_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                giver_id     TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                content      TEXT NOT NULL,
                situation    TEXT,
                categories   TEXT,      -- JSON array of strings
                feedback_type TEXT,     -- 'strength' | 'growth' | 'both'
                quarter      TEXT NOT NULL,
                created_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS self_reflections (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                quarter    TEXT NOT NULL,
                content    TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, quarter)
            );

            CREATE TABLE IF NOT EXISTS goals (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                quarter    TEXT NOT NULL,
                content    TEXT NOT NULL,
                completed  INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a            TEXT NOT NULL,
                user_b            TEXT NOT NULL,
                channel_id        TEXT,
                week              TEXT NOT NULL,  -- 'YYYY-Www'
                interaction_count INTEGER DEFAULT 1,
                UNIQUE(user_a, user_b, week)
            );

            CREATE TABLE IF NOT EXISTS nudge_log (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  TEXT NOT NULL,
                peer_id  TEXT NOT NULL,
                week     TEXT NOT NULL,
                sent_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, peer_id, week)
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                quarter      TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                generated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, quarter)
            );
        """)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def upsert_user(slack_id: str, name: str, manager_id: Optional[str] = None) -> None:
    with _get_conn() as conn:
        if manager_id:
            conn.execute(
                """INSERT INTO users (slack_id, name, manager_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(slack_id) DO UPDATE SET name=excluded.name, manager_id=excluded.manager_id""",
                (slack_id, name, manager_id),
            )
        else:
            conn.execute(
                """INSERT INTO users (slack_id, name)
                   VALUES (?, ?)
                   ON CONFLICT(slack_id) DO UPDATE SET name=excluded.name""",
                (slack_id, name),
            )


def set_manager(user_id: str, manager_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE users SET manager_id=? WHERE slack_id=?",
            (manager_id, user_id),
        )


def get_user(slack_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE slack_id=?", (slack_id,)).fetchone()
        return dict(row) if row else None


def get_all_users() -> list:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

def save_feedback(
    giver_id: str,
    recipient_id: str,
    content: str,
    situation: Optional[str],
    categories: list,
    feedback_type: str,
    quarter: str,
) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO feedback
               (giver_id, recipient_id, content, situation, categories, feedback_type, quarter)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (giver_id, recipient_id, content, situation, json.dumps(categories), feedback_type, quarter),
        )
        # Invalidate cached summary for this recipient
        conn.execute("DELETE FROM summaries WHERE user_id=? AND quarter=?", (recipient_id, quarter))
        return cur.lastrowid


def get_feedback_for_user(user_id: str, quarter: str) -> list:
    """Return feedback received by user_id, including who gave it."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT f.*, u.name AS giver_name
               FROM feedback f
               LEFT JOIN users u ON u.slack_id = f.giver_id
               WHERE f.recipient_id=? AND f.quarter=?
               ORDER BY f.created_at DESC""",
            (user_id, quarter),
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["categories"] = json.loads(item["categories"] or "[]")
            result.append(item)
        return result


def get_feedback_given_by(user_id: str, quarter: str) -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT f.*, u.name AS recipient_name
               FROM feedback f
               LEFT JOIN users u ON u.slack_id = f.recipient_id
               WHERE f.giver_id=? AND f.quarter=?
               ORDER BY f.created_at DESC""",
            (user_id, quarter),
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["categories"] = json.loads(item["categories"] or "[]")
            result.append(item)
        return result


def get_feedback_count_for_user(user_id: str, quarter: str) -> dict:
    with _get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as c FROM feedback WHERE recipient_id=? AND quarter=?",
            (user_id, quarter),
        ).fetchone()["c"]
        givers = conn.execute(
            "SELECT COUNT(DISTINCT giver_id) as c FROM feedback WHERE recipient_id=? AND quarter=?",
            (user_id, quarter),
        ).fetchone()["c"]
        return {"total": total, "unique_givers": givers}


# ---------------------------------------------------------------------------
# Self-reflections
# ---------------------------------------------------------------------------

def upsert_self_reflection(user_id: str, quarter: str, content: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO self_reflections (user_id, quarter, content, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, quarter) DO UPDATE
               SET content=excluded.content, updated_at=excluded.updated_at""",
            (user_id, quarter, content),
        )


def get_self_reflection(user_id: str, quarter: str) -> Optional[str]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT content FROM self_reflections WHERE user_id=? AND quarter=?",
            (user_id, quarter),
        ).fetchone()
        return row["content"] if row else None


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

def add_goal(user_id: str, quarter: str, content: str) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO goals (user_id, quarter, content) VALUES (?, ?, ?)",
            (user_id, quarter, content),
        )
        return cur.lastrowid


def toggle_goal(goal_id: int) -> bool:
    """Toggle completed status. Returns new completed state."""
    with _get_conn() as conn:
        current = conn.execute("SELECT completed FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not current:
            return False
        new_state = 0 if current["completed"] else 1
        conn.execute("UPDATE goals SET completed=? WHERE id=?", (new_state, goal_id))
        return bool(new_state)


def delete_goal(goal_id: int, user_id: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM goals WHERE id=? AND user_id=?", (goal_id, user_id))


def get_goals(user_id: str, quarter: str) -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM goals WHERE user_id=? AND quarter=? ORDER BY created_at",
            (user_id, quarter),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Interactions (for weekly nudge)
# ---------------------------------------------------------------------------

def record_interaction(user_a: str, user_b: str, channel_id: Optional[str], week: str) -> None:
    """Increment interaction count between two users for a given ISO week."""
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO interactions (user_a, user_b, channel_id, week, interaction_count)
               VALUES (?, ?, ?, ?, 1)
               ON CONFLICT(user_a, user_b, week)
               DO UPDATE SET interaction_count = interaction_count + 1""",
            (user_a, user_b, channel_id, week),
        )


def get_active_peers_for_week(user_id: str, week: str, min_interactions: int = 2) -> list:
    """Return peer slack_ids this user interacted with >= min_interactions times this week."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT user_b AS peer_id, SUM(interaction_count) AS total
               FROM interactions
               WHERE user_a=? AND week=?
               GROUP BY user_b
               HAVING total >= ?
               ORDER BY total DESC""",
            (user_id, week, min_interactions),
        ).fetchall()
        return [r["peer_id"] for r in rows]


def nudge_already_sent(user_id: str, peer_id: str, week: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM nudge_log WHERE user_id=? AND peer_id=? AND week=?",
            (user_id, peer_id, week),
        ).fetchone()
        return row is not None


def log_nudge(user_id: str, peer_id: str, week: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO nudge_log (user_id, peer_id, week) VALUES (?, ?, ?)",
            (user_id, peer_id, week),
        )


# ---------------------------------------------------------------------------
# AI Summary cache
# ---------------------------------------------------------------------------

def get_cached_summary(user_id: str, quarter: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT summary_json FROM summaries WHERE user_id=? AND quarter=?",
            (user_id, quarter),
        ).fetchone()
        if row:
            return json.loads(row["summary_json"])
        return None


def save_summary(user_id: str, quarter: str, summary: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO summaries (user_id, quarter, summary_json, generated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, quarter) DO UPDATE
               SET summary_json=excluded.summary_json, generated_at=excluded.generated_at""",
            (user_id, quarter, json.dumps(summary)),
        )


def invalidate_summary(user_id: str, quarter: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM summaries WHERE user_id=? AND quarter=?",
            (user_id, quarter),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_current_quarter() -> str:
    today = date.today()
    q = (today.month - 1) // 3 + 1
    return f"Q{q} {today.year}"
