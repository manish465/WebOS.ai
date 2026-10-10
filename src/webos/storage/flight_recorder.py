"""
Flight recorder telemetry for session traces, error diagnosis, and state diffs.
"""

import uuid
import datetime
from typing import Optional, Dict, Any
from webos.storage.db import DatabaseManager


class FlightRecorder:
    """Records execution sessions and failure telemetry for debugging and skill improvement."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    def start_session(self, domain: str) -> str:
        """Starts a new automation session and returns its unique ID."""
        session_id = str(uuid.uuid4())
        start_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = self.db_manager.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO flight_recorder_sessions
                (session_id, start_time, domain, status, steps_count)
                VALUES (?, ?, ?, 'running', 0)
                """,
                (session_id, start_time, domain.lower()),
            )
        return session_id

    def record_step(self, session_id: str) -> None:
        """Increments the execution step count for an active session."""
        conn = self.db_manager.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE flight_recorder_sessions
                SET steps_count = steps_count + 1
                WHERE session_id = ?
                """,
                (session_id,),
            )

    def end_session(
        self,
        session_id: str,
        status: str,
        failure_reason: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> None:
        """Finalizes a session with status, completion time, and optional failure artifacts."""
        end_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = self.db_manager.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE flight_recorder_sessions
                SET end_time = ?, status = ?, failure_reason = ?, screenshot_path = ?
                WHERE session_id = ?
                """,
                (end_time, status, failure_reason, screenshot_path, session_id),
            )

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves session telemetry by session ID."""
        conn = self.db_manager.get_connection()
        row = conn.execute(
            """
            SELECT session_id, start_time, end_time, domain, status, steps_count, failure_reason, screenshot_path
            FROM flight_recorder_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        return dict(row) if row else None
