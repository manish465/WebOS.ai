"""
Episodic observation memory for tracking and retrieving past user inputs.
"""

from typing import Optional, List
import datetime
from src.types import ObservationRecord
from src.storage.db import DatabaseManager


class EpisodicMemory:
    """Stores and retrieves historical observations with recency and domain context."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    def log_observation(self, record: ObservationRecord) -> int:
        """Logs a new field observation into persistent storage."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        with conn:
            cursor.execute(
                """
                INSERT INTO episodic_observations 
                (timestamp, domain, url, field_label, entered_value, field_type, context_tag)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.timestamp.isoformat(),
                    record.domain.lower(),
                    record.url,
                    record.field_label.strip(),
                    record.entered_value,
                    record.field_type,
                    record.context_tag,
                ),
            )
            return cursor.lastrowid

    def get_latest_value(
        self, field_label: str, domain: Optional[str] = None
    ) -> Optional[str]:
        """
        Retrieves the most relevant past value for a given field label.
        Priority:
        1. Exact domain match ordered by newest timestamp.
        2. Recency fallback across any domain ordered by newest timestamp.
        """
        conn = self.db_manager.get_connection()
        clean_label = field_label.strip()

        if domain:
            row = conn.execute(
                """
                SELECT entered_value FROM episodic_observations
                WHERE LOWER(field_label) = LOWER(?) AND domain = LOWER(?)
                ORDER BY timestamp DESC LIMIT 1
                """,
                (clean_label, domain.strip()),
            ).fetchone()
            if row:
                return row["entered_value"]

        # Recency fallback across all domains
        row = conn.execute(
            """
            SELECT entered_value FROM episodic_observations
            WHERE LOWER(field_label) = LOWER(?)
            ORDER BY timestamp DESC LIMIT 1
            """,
            (clean_label,),
        ).fetchone()

        return row["entered_value"] if row else None

    def query_history(
        self, field_label: str, limit: int = 5
    ) -> List[ObservationRecord]:
        """Returns historical entries for a given label in reverse chronological order."""
        conn = self.db_manager.get_connection()
        rows = conn.execute(
            """
            SELECT timestamp, domain, url, field_label, entered_value, field_type, context_tag
            FROM episodic_observations
            WHERE LOWER(field_label) = LOWER(?)
            ORDER BY timestamp DESC LIMIT ?
            """,
            (field_label.strip(), limit),
        ).fetchall()

        results = []
        for row in rows:
            results.append(
                ObservationRecord(
                    timestamp=datetime.datetime.fromisoformat(row["timestamp"]),
                    domain=row["domain"],
                    url=row["url"],
                    field_label=row["field_label"],
                    entered_value=row["entered_value"],
                    field_type=row["field_type"],
                    context_tag=row["context_tag"],
                )
            )
        return results
