"""
Unit tests for WebOS.ai CDP Client, 0-Token Perception Pruner, and Action Executor.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.types import ElementCandidate, BoundingBox, BrowserAction
from src.browser.cdp_client import CDPClient
from src.browser.perception import PerceptionPruner
from src.browser.executor import ActionExecutor


# --- CDP Client Tests ---

@pytest.mark.asyncio
async def test_cdp_client_send_and_future_resolution():
    client = CDPClient()
    mock_ws = AsyncMock()
    client.ws = mock_ws
    client._connected = True

    # Simulate sending a command
    send_task = asyncio.create_task(client.send("Page.navigate", {"url": "https://example.com"}))
    await asyncio.sleep(0.01)

    # Inbound response matching msg_id=1
    client._pending_requests[1].set_result({"frameId": "123"})
    result = await send_task

    assert result == {"frameId": "123"}
    mock_ws.send.assert_called_once()


@pytest.mark.asyncio
async def test_cdp_client_event_listeners():
    client = CDPClient()
    events_received = []

    def on_load(params):
        events_received.append(params)

    client.on("Page.loadEventFired", on_load)
    # Trigger event dispatch manually
    client._event_listeners["Page.loadEventFired"][0]({"timestamp": 1234.5})

    assert len(events_received) == 1
    assert events_received[0]["timestamp"] == 1234.5


# --- Perception Pruner Tests ---

def test_perception_quad_parsing():
    # 8-float quad: top-left (10, 20), top-right (110, 20), bottom-right (110, 70), bottom-left (10, 70)
    quad = [10.0, 20.0, 110.0, 20.0, 110.0, 70.0, 10.0, 70.0]
    box = PerceptionPruner._parse_quad_box(quad)

    assert box is not None
    assert box.x == 10.0
    assert box.y == 20.0
    assert box.width == 100.0
    assert box.height == 50.0
    assert box.center_x == 60.0
    assert box.center_y == 45.0


@pytest.mark.asyncio
async def test_perception_extract_candidates_filtering():
    pruner = PerceptionPruner()
    mock_cdp = AsyncMock()

    # Mock AXTree with 3 nodes:
    # 1. Interactive Button with valid box
    # 2. Non-interactive Paragraph (should be ignored)
    # 3. Interactive Input with 0x0 invisible box (should be culled)
    mock_ax_tree = {
        "nodes": [
            {
                "backendDOMNodeId": 101,
                "role": {"value": "button"},
                "name": {"value": "Apply Now"},
            },
            {
                "backendDOMNodeId": 102,
                "role": {"value": "StaticText"},
                "name": {"value": "Some text"},
            },
            {
                "backendDOMNodeId": 103,
                "role": {"value": "textbox"},
                "name": {"value": "Hidden Input"},
            },
        ]
    }

    async def mock_cdp_send(method, params=None):
        if method == "Accessibility.getFullAXTree":
            return mock_ax_tree
        if method == "DOM.getBoxModel":
            node_id = params.get("backendNodeId")
            if node_id == 101:
                # Valid box (width=100, height=40)
                return {"model": {"content": [0.0, 0.0, 100.0, 0.0, 100.0, 40.0, 0.0, 40.0]}}
            elif node_id == 103:
                # 0x0 invisible box
                return {"model": {"content": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}}
        return {}

    mock_cdp.send.side_effect = mock_cdp_send

    candidates = await pruner.extract_candidates(mock_cdp, max_candidates=10)

    # Only node 101 should survive the filter
    assert len(candidates) == 1
    assert candidates[0].candidate_id == 1
    assert candidates[0].backend_node_id == 101
    assert candidates[0].role == "button"
    assert candidates[0].name == "Apply Now"
    assert candidates[0].is_clickable is True


# --- Action Executor Tests ---

@pytest.mark.asyncio
async def test_executor_click():
    executor = ActionExecutor()
    mock_cdp = AsyncMock()

    box = BoundingBox(x=100.0, y=200.0, width=50.0, height=20.0)
    candidate = ElementCandidate(
        candidate_id=1,
        backend_node_id=10,
        role="button",
        name="Submit",
        box=box,
    )
    action = BrowserAction(action_type="click", target_candidate_id=1)

    success = await executor.execute(mock_cdp, action, candidate)
    assert success is True

    # Center is at (125.0, 210.0)
    calls = mock_cdp.send.call_args_list
    mouse_calls = [c for c in calls if c[0][0] == "Input.dispatchMouseEvent"]
    assert len(mouse_calls) == 2  # mousePressed and mouseReleased
    assert mouse_calls[0][0][1]["x"] == 125.0
    assert mouse_calls[0][0][1]["y"] == 210.0


@pytest.mark.asyncio
async def test_executor_fill():
    executor = ActionExecutor()
    mock_cdp = AsyncMock()

    box = BoundingBox(x=50.0, y=50.0, width=100.0, height=30.0)
    candidate = ElementCandidate(
        candidate_id=2,
        backend_node_id=20,
        role="textbox",
        name="Email",
        box=box,
    )
    action = BrowserAction(action_type="fill", target_candidate_id=2, value="test@domain.com")

    success = await executor.execute(mock_cdp, action, candidate)
    assert success is True

    calls = mock_cdp.send.call_args_list
    text_calls = [c for c in calls if c[0][0] == "Input.insertText"]
    assert len(text_calls) == 1
    assert text_calls[0][0][1]["text"] == "test@domain.com"


@pytest.mark.asyncio
async def test_executor_upload():
    executor = ActionExecutor()
    mock_cdp = AsyncMock()

    candidate = ElementCandidate(
        candidate_id=3,
        backend_node_id=30,
        role="button",
        name="Upload Resume",
    )
    action = BrowserAction(
        action_type="upload", target_candidate_id=3, file_path="/path/to/resume.pdf"
    )

    success = await executor.execute(mock_cdp, action, candidate)
    assert success is True

    mock_cdp.send.assert_called_with(
        "DOM.setFileInputFiles",
        {"files": ["/path/to/resume.pdf"], "backendNodeId": 30},
    )
