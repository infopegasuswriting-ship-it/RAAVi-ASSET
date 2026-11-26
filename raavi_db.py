"""RAAVi SQLite schema and connection management (preserves legacy demo tables separately)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from raavi_bank import sync_bank_to_db

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = Path(os.getenv("RAAVI_DB", str(ROOT / "raavi.sqlite3")))

SCHEMA = """
PRAGMA foreign_keys = ON;

-- Real student accounts (kept strictly separate from legacy demo `users` table)
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    verified_at REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_codes (
    email TEXT NOT NULL,
    purpose TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    issued_at REAL NOT NULL,
    tries INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (email, purpose)
);

CREATE TABLE IF NOT EXISTS student_sessions (
    token_hash TEXT PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
);

-- Versioned question bank
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    subject TEXT NOT NULL,
    chapter TEXT NOT NULL,
    subtopic TEXT NOT NULL,
    skill TEXT NOT NULL,
    question_type TEXT NOT NULL,
    refs TEXT NOT NULL,
    stem TEXT NOT NULL,
    choices_json TEXT NOT NULL,
    answer_key TEXT NOT NULL,
    explanation TEXT NOT NULL,
    map_asset TEXT,
    underlying_facts_json TEXT NOT NULL,
    auto_status TEXT NOT NULL,
    editorial_status TEXT NOT NULL,
    validation_flags_json TEXT NOT NULL,
    current_version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_subj_ch ON questions(subject, chapter, auto_status);
CREATE INDEX IF NOT EXISTS idx_questions_family ON questions(family);

CREATE TABLE IF NOT EXISTS question_versions (
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    family TEXT NOT NULL,
    subject TEXT NOT NULL,
    chapter TEXT NOT NULL,
    subtopic TEXT NOT NULL,
    skill TEXT NOT NULL,
    question_type TEXT NOT NULL,
    refs TEXT NOT NULL,
    stem TEXT NOT NULL,
    choices_json TEXT NOT NULL,
    answer_key TEXT NOT NULL,
    explanation TEXT NOT NULL,
    map_asset TEXT,
    underlying_facts_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (question_id, version)
);

-- Student chapter test sessions, responses, lockouts, and saved reports
CREATE TABLE IF NOT EXISTS test_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    chapter TEXT NOT NULL,
    nonce TEXT NOT NULL,
    started_at REAL NOT NULL,
    completed_at REAL,
    status TEXT NOT NULL,
    items_json TEXT NOT NULL,
    option_orders_json TEXT NOT NULL,
    current_index INTEGER NOT NULL DEFAULT 0,
    UNIQUE (student_id, nonce)
);

CREATE INDEX IF NOT EXISTS idx_test_sessions_student_subj ON test_sessions(student_id, subject, started_at);

CREATE TABLE IF NOT EXISTS test_responses (
    test_session_id INTEGER NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    question_index INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    question_version INTEGER NOT NULL,
    response TEXT,
    is_correct INTEGER NOT NULL,
    is_skip INTEGER NOT NULL,
    submitted_at REAL NOT NULL,
    PRIMARY KEY (test_session_id, question_index)
);

CREATE TABLE IF NOT EXISTS family_lockouts (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    family TEXT NOT NULL,
    locked_until REAL NOT NULL,
    PRIMARY KEY (student_id, family)
);

CREATE TABLE IF NOT EXISTS fact_exposures (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    fact_id TEXT NOT NULL,
    last_seen_at REAL NOT NULL,
    PRIMARY KEY (student_id, fact_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_session_id INTEGER UNIQUE NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    chapter TEXT NOT NULL,
    status TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    completed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_student ON reports(student_id, subject, chapter, completed_at);

CREATE TABLE IF NOT EXISTS import_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at REAL NOT NULL,
    total_items INTEGER NOT NULL,
    auto_passed INTEGER NOT NULL,
    auto_flagged INTEGER NOT NULL,
    summary_json TEXT NOT NULL
);
"""


def connect_db(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB, sync_bank: bool = True) -> dict | None:
    conn = connect_db(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        if sync_bank:
            count = conn.execute("SELECT count(*) FROM questions").fetchone()[0]
            if count == 0:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    summary = sync_bank_to_db(conn)
                    conn.commit()
                    return summary
                except Exception:
                    conn.rollback()
                    raise
        return None
    finally:
        conn.close()
