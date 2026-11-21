import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH") or os.getenv("DATABASE_PATH", "./data/chatbot.db"))


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, filename TEXT NOT NULL, stored_path TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS document_roles(document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE, role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE, PRIMARY KEY(document_id,role_id));
        CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL, content TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS quota_logs(id INTEGER PRIMARY KEY, model TEXT NOT NULL, prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)


def rows(query, params=()):
    with connect() as db:
        return [dict(r) for r in db.execute(query, params).fetchall()]


def one(query, params=()):
    with connect() as db:
        row = db.execute(query, params).fetchone()
        return dict(row) if row else None


def execute(query, params=()):
    with connect() as db:
        cur = db.execute(query, params)
        return cur.lastrowid


def set_document_roles(document_id, role_ids):
    with connect() as db:
        db.execute("DELETE FROM document_roles WHERE document_id=?", (document_id,))
        db.executemany("INSERT OR IGNORE INTO document_roles(document_id,role_id) VALUES (?,?)", [(document_id, x) for x in role_ids])
