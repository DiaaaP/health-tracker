import json
import os
import sqlite3
from pathlib import Path


DEFAULT_DATABASE_PATH = Path(__file__).with_name("sana.db")
DATABASE_PATH = Path(os.getenv("SANA_DB_PATH", DEFAULT_DATABASE_PATH))


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _add_column_if_missing(
    connection: sqlite3.Connection, table: str, column: str, declaration: str
) -> None:
    columns = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                mood TEXT NOT NULL,
                energy TEXT NOT NULL,
                symptoms TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS periods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT NOT NULL,
                end_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _add_column_if_missing(
            connection, "daily_logs", "user_id", "INTEGER REFERENCES users(id)"
        )
        _add_column_if_missing(
            connection, "periods", "user_id", "INTEGER REFERENCES users(id)"
        )
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
            CREATE INDEX IF NOT EXISTS idx_daily_logs_owner_date
                ON daily_logs(user_id, entry_date);
            CREATE INDEX IF NOT EXISTS idx_periods_owner_start
                ON periods(user_id, start_date);
            """
        )


def row_to_log(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["symptoms"] = json.loads(result["symptoms"])
    return result


def row_to_user(row: sqlite3.Row) -> dict:
    """Return only public user fields; never expose password_hash."""
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "created_at": row["created_at"],
    }
