import sqlite3
from datetime import datetime, timezone
from typing import Iterable


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str, default_access_code: str) -> None:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE NOT NULL,
            phone TEXT,
            full_name TEXT,
            username TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO NOTHING
        """,
        ("access_code", default_access_code),
    )
    conn.commit()
    conn.close()


def get_access_code(db_path: str) -> str:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", ("access_code",))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return ""
    return str(row["value"])


def set_access_code(db_path: str, code: str) -> None:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        ("access_code", code),
    )
    conn.commit()
    conn.close()


def upsert_user(db_path: str, tg_id: int, phone: str, full_name: str, username: str) -> int:
    conn = _connect(db_path)
    cur = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO users(tg_id, phone, full_name, username, created_at)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET
            phone = excluded.phone,
            full_name = excluded.full_name,
            username = excluded.username
        """,
        (tg_id, phone, full_name, username, created_at),
    )
    cur.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    return int(row["id"]) if row else 0


def record_login(db_path: str, user_id: int) -> None:
    conn = _connect(db_path)
    cur = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur.execute("INSERT INTO logins(user_id, ts) VALUES(?, ?)", (user_id, ts))
    conn.commit()
    conn.close()


def list_users(db_path: str, limit: int = 50) -> Iterable[sqlite3.Row]:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tg_id, phone, full_name, username, created_at
        FROM users
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_logins(db_path: str, limit: int = 50) -> Iterable[sqlite3.Row]:
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT l.ts, u.tg_id, u.full_name, u.username, u.phone
        FROM logins l
        JOIN users u ON u.id = l.user_id
        ORDER BY l.ts DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows
