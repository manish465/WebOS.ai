"""
SQLite Database Manager for WebOS.ai persistent storage.
"""

import sqlite3
from pathlib import Path
from typing import Optional


class DatabaseManager:
    """Manages SQLite database connection, initialization, and transactions."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            default_dir = Path.home() / ".webos"
            default_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = default_dir / "runtime.db"
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection: Optional[sqlite3.Connection] = None
        self.initialize_tables()

    def get_connection(self) -> sqlite3.Connection:
        """Returns active SQLite connection, creating it if needed."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            self._connection.row_factory = sqlite3.Row
            # Enable WAL mode for concurrency if not in-memory
            if str(self.db_path) != ":memory:":
                self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA foreign_keys=ON;")
        return self._connection

    def initialize_tables(self) -> None:
        """Creates the required tables if they do not exist."""
        conn = self.get_connection()
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    url TEXT NOT NULL,
                    field_label TEXT NOT NULL,
                    entered_value TEXT NOT NULL,
                    field_type TEXT NOT NULL,
                    context_tag TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_observations_domain 
                    ON episodic_observations(domain);
                CREATE INDEX IF NOT EXISTS idx_observations_label 
                    ON episodic_observations(field_label);

                CREATE TABLE IF NOT EXISTS flight_recorder_sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL,
                    steps_count INTEGER DEFAULT 0,
                    failure_reason TEXT,
                    screenshot_path TEXT
                );

                CREATE TABLE IF NOT EXISTS site_skills (
                    skill_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    action_graph_json TEXT NOT NULL,
                    success_rate REAL DEFAULT 1.0,
                    last_verified TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        """Closes the active database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
