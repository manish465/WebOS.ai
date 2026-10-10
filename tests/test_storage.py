"""
Unit tests for WebOS.ai types and storage engine.
"""

import pytest
import datetime
from pathlib import Path
from src.types import (
    BoundingBox,
    ElementCandidate,
    BrowserAction,
    VerificationResult,
    ObservationRecord,
    ModelResponse,
)
from src.storage.db import DatabaseManager
from src.storage.episodic import EpisodicMemory
from src.storage.flight_recorder import FlightRecorder


# --- Types Tests ---

def test_bounding_box():
    box = BoundingBox(x=10.0, y=20.0, width=100.0, height=50.0)
    assert box.center_x == 60.0
    assert box.center_y == 45.0
    assert box.is_visible() is True

    invisible_box = BoundingBox(x=0.0, y=0.0, width=0.0, height=0.0)
    assert invisible_box.is_visible() is False


def test_element_candidate_compact_dict():
    box = BoundingBox(x=10.0, y=10.0, width=50.0, height=20.0)
    candidate = ElementCandidate(
        candidate_id=1,
        backend_node_id=101,
        role="button",
        name="Submit",
        value=None,
        box=box,
        is_clickable=True,
        is_editable=False,
    )
    compact = candidate.to_compact_dict()
    assert compact == {"id": 1, "role": "button", "name": "Submit"}


def test_browser_action_validation():
    valid_click = BrowserAction(action_type="click", target_candidate_id=1)
    assert valid_click.validate() is True

    valid_fill = BrowserAction(action_type="fill", target_candidate_id=2, value="test")
    assert valid_fill.validate() is True

    with pytest.raises(ValueError, match="requires a 'value'"):
        BrowserAction(action_type="fill", target_candidate_id=2, value=None).validate()

    with pytest.raises(ValueError, match="requires a 'file_path'"):
        BrowserAction(action_type="upload", target_candidate_id=3, file_path=None).validate()


# --- Storage Tests ---

@pytest.fixture
def memory_db():
    db = DatabaseManager(db_path=":memory:")
    yield db
    db.close()


def test_database_initialization(memory_db):
    conn = memory_db.get_connection()
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "episodic_observations" in tables
    assert "flight_recorder_sessions" in tables
    assert "site_skills" in tables


def test_episodic_memory_logging_and_retrieval(memory_db):
    memory = EpisodicMemory(memory_db)
    now = datetime.datetime.now(datetime.timezone.utc)

    rec1 = ObservationRecord(
        timestamp=now - datetime.timedelta(days=2),
        domain="amazon.com",
        url="https://amazon.com/jobs",
        field_label="Notice Period",
        entered_value="60 days",
        field_type="text",
    )
    rec2 = ObservationRecord(
        timestamp=now - datetime.timedelta(days=1),
        domain="stripe.com",
        url="https://stripe.com/jobs",
        field_label="Notice Period",
        entered_value="30 days",
        field_type="text",
    )
    rec3 = ObservationRecord(
        timestamp=now,
        domain="startup.io",
        url="https://startup.io/apply",
        field_label="Notice Period",
        entered_value="Immediate",
        field_type="text",
    )

    memory.log_observation(rec1)
    memory.log_observation(rec2)
    memory.log_observation(rec3)

    # 1. Exact domain query: should return 30 days for Stripe even though startup.io is newer
    stripe_val = memory.get_latest_value("Notice Period", domain="stripe.com")
    assert stripe_val == "30 days"

    # 2. General query without domain: should return newest entry ("Immediate")
    newest_val = memory.get_latest_value("Notice Period")
    assert newest_val == "Immediate"

    # 3. History query: should return all 3 sorted descending
    history = memory.query_history("Notice Period", limit=5)
    assert len(history) == 3
    assert history[0].entered_value == "Immediate"
    assert history[1].entered_value == "30 days"
    assert history[2].entered_value == "60 days"


def test_flight_recorder_session_lifecycle(memory_db):
    recorder = FlightRecorder(memory_db)

    # 1. Start session
    session_id = recorder.start_session(domain="lever.co")
    session = recorder.get_session(session_id)
    assert session is not None
    assert session["status"] == "running"
    assert session["steps_count"] == 0
    assert session["domain"] == "lever.co"

    # 2. Record steps
    recorder.record_step(session_id)
    recorder.record_step(session_id)
    session = recorder.get_session(session_id)
    assert session["steps_count"] == 2

    # 3. End session
    recorder.end_session(
        session_id=session_id,
        status="failed",
        failure_reason="Element not interactable",
        screenshot_path="/tmp/error.png",
    )
    session = recorder.get_session(session_id)
    assert session["status"] == "failed"
    assert session["failure_reason"] == "Element not interactable"
    assert session["screenshot_path"] == "/tmp/error.png"
    assert session["end_time"] is not None
