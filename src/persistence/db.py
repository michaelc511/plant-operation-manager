"""SQLite connection. The location comes only from the DATABASE_URL env var (e.g. sqlite:///data/app.db)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from rag.config import ROOT  # also loads .env

SCHEMA = Path(__file__).with_name("schema.sql")

# Columns added after the first release of schema.sql: (table, column, definition).
# init_db adds any that are missing, so older databases are upgraded in place.
MIGRATIONS = [
    ("queries", "flags", "TEXT NOT NULL DEFAULT '[]'"),
    ("queries", "confidence", "TEXT"),
    ("queries", "trace", "TEXT NOT NULL DEFAULT '[]'"),
]


def db_path() -> Path:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Add it to .env, e.g. DATABASE_URL=sqlite:///data/app.db")
    if not url.startswith("sqlite:///"):
        raise RuntimeError("DATABASE_URL must be a SQLite URL starting with sqlite:///")
    path = Path(url.removeprefix("sqlite:///"))
    return path if path.is_absolute() else ROOT / path


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text())
    for table, column, definition in MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()
