"""
Integration tests for master WebRuntime class.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from webos import WebRuntime, BrowserAction, ElementCandidate, BoundingBox
from webos.types import ModelResponse


@pytest.fixture
def runtime():
    rt = WebRuntime(db_path=":memory:")
    yield rt


@pytest.mark.asyncio
async def test_runtime_ground_intent_deterministic(runtime):
    box = BoundingBox(x=10, y=10, width=50, height=20)
    candidates = [
        ElementCandidate(candidate_id=1, backend_node_id=1, role="button", name="Cancel", box=box),
        ElementCandidate(candidate_id=2, backend_node_id=2, role="button", name="Submit Application", box=box),
        ElementCandidate(candidate_id=3, backend_node_id=3, role="textbox", name="Full Name", box=box),
    ]

    # Exact intent matching
    target = await runtime.ground_intent("Submit Application", candidates)
    assert target is not None
    assert target.candidate_id == 2


@pytest.mark.asyncio
async def test_runtime_ground_intent_model(runtime):
    box = BoundingBox(x=10, y=10, width=50, height=20)
    candidates = [
        ElementCandidate(candidate_id=1, backend_node_id=1, role="textbox", name="Primary Contact", box=box),
        ElementCandidate(candidate_id=2, backend_node_id=2, role="textbox", name="Work Experience", box=box),
    ]

    # Mock the router to return candidate ID 1
    mock_resp = ModelResponse(
        content="Candidate 1",
        model_used="mock-model",
        tokens_prompt=10,
        tokens_completion=2,
        latency_ms=10.0,
    )
    with patch.object(runtime.router, "query", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = mock_resp
        target = await runtime.ground_intent("Phone number field", candidates)

        assert target is not None
        assert target.candidate_id == 1


@pytest.mark.asyncio
async def test_runtime_execute_step_and_episodic_logging(runtime):
    box = BoundingBox(x=10, y=10, width=50, height=20)
    candidate = ElementCandidate(
        candidate_id=1, backend_node_id=10, role="textbox", name="Years of Experience", box=box
    )
    action = BrowserAction(action_type="fill", target_candidate_id=1, value="5")

    # Mock CDP and browser subsystems
    async def mock_eval(script):
        if "location.href" in script:
            return "https://jobs.lever.co/company/apply"
        return "5"

    runtime.cdp.evaluate = AsyncMock(side_effect=mock_eval)
    runtime.executor.execute = AsyncMock(return_value=True)

    with patch.object(runtime, "get_current_url", new_callable=AsyncMock) as mock_url:
        mock_url.return_value = "https://jobs.lever.co/company/apply"

        result = await runtime.execute_step(
            intent="Fill Years of Experience",
            action=action,
            candidate=candidate,
        )

        assert result.success is True
        assert result.value_matches is True

        # Verify episodic memory logged this entry!
        logged_val = runtime.episodic.get_latest_value("Years of Experience")
        assert logged_val == "5"


@pytest.mark.asyncio
async def test_runtime_close(tmp_path):
    test_db = tmp_path / "test_runtime.db"
    rt = WebRuntime(db_path=test_db)
    rt.cdp.close = AsyncMock()
    session_id = rt.flight_recorder.start_session("example.com")
    rt._active_session_id = session_id
    await rt.close()

    rt.cdp.close.assert_called_once()
    session = rt.flight_recorder.get_session(session_id)
    # Session recorded as completed
    assert session is not None
    assert session["status"] == "completed"
    rt.db.close()
