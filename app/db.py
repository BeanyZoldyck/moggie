from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import load_config

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_sessions (
    id TEXT PRIMARY KEY,
    game_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    game_type TEXT NOT NULL,
    score INTEGER NOT NULL,
    rank INTEGER,
    label TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES game_sessions(id),
    FOREIGN KEY(player_id) REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    player_id TEXT,
    kind TEXT NOT NULL,
    storage_mode TEXT NOT NULL,
    uri TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES game_sessions(id),
    FOREIGN KEY(player_id) REFERENCES players(id)
);

CREATE INDEX IF NOT EXISTS idx_scores_game_score
ON scores(game_type, score DESC, created_at ASC);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.executescript(SCHEMA)
        connection.commit()


def main() -> int:
    config = load_config()
    initialize_database(config.db_path)
    print(f"Initialized Moggie database at {config.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
