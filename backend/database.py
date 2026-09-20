import json
import os
import sqlite3
from pathlib import Path


DEFAULT_DATABASE_PATH = Path(__file__).with_name("sana.db")
DATABASE_PATH = Path(os.getenv("SANA_DB_PATH", DEFAULT_DATABASE_PATH))


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


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
            """
        )


def row_to_log(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["symptoms"] = json.loads(result["symptoms"])
    return result
