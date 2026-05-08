import sqlite3
from pathlib import Path


DB_PATH = Path("debug_history.sqlite3")


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                error_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                error_type TEXT,
                category TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def clear_history():
    with get_connection() as connection:
        connection.execute("DELETE FROM analyses")


def save_analysis(title, error_text, summary, error_type="", category=""):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO analyses (title, error_text, summary, error_type, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title[:180], error_text, summary, error_type, category),
        )


def fetch_history(limit=10):
    with get_connection() as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, title, summary, error_type, category, created_at
            FROM analyses
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def count_history():
    with get_connection() as connection:
        row = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()

    return row[0] if row else 0


def fetch_analysis(analysis_id):
    with get_connection() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT id, title, error_text, summary, error_type, category, created_at
            FROM analyses
            WHERE id = ?
            """,
            (analysis_id,),
        ).fetchone()

    return dict(row) if row else None
