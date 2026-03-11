from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DATA_DIR, DB_PATH


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    scope TEXT,
    assumptions TEXT,
    status TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS research_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    domain TEXT,
    notes TEXT,
    retrieved_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    source_url TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    task TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'task',
    status TEXT NOT NULL,
    parent_task_id INTEGER,
    notes TEXT,
    due_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES research_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    ref_id TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def ensure_db() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "kind" not in task_columns:
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN kind TEXT NOT NULL DEFAULT 'task'")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc):
                    raise
        if "parent_task_id" not in task_columns:
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN parent_task_id INTEGER")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc):
                    raise
        if "notes" not in task_columns:
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc):
                    raise
    return DB_PATH


@contextmanager
def connect() -> sqlite3.Connection:
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
