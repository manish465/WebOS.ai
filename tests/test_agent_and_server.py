"""
Tests for WebOS AutonomousBrowserAgent and Server.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from webos.runtime import WebRuntime
from webos.agent import AutonomousBrowserAgent
from webos.types import ElementCandidate, BoundingBox


@pytest.mark.asyncio
async def test_agent_navigation_extraction():
    runtime = MagicMock(spec=WebRuntime)
    runtime.cdp = MagicMock()
    runtime.cdp.is_connected = True
    runtime.get_current_url = AsyncMock(return_value="https://google.com")
    runtime.navigate = AsyncMock()
    runtime.get_screenshot = AsyncMock(return_value="fake_b64")

    agent = AutonomousBrowserAgent(runtime)
    url = agent._extract_navigation_url("please go to wikipedia.org and find something")
    assert url == "https://wikipedia.org"


@pytest.mark.asyncio
async def test_agent_search_query_extraction():
    runtime = MagicMock(spec=WebRuntime)
    agent = AutonomousBrowserAgent(runtime)
    query = agent._extract_search_query("search for mechanical keyboards")
    assert query == "mechanical keyboards"


@pytest.mark.asyncio
async def test_agent_click_target_extraction():
    runtime = MagicMock(spec=WebRuntime)
    agent = AutonomousBrowserAgent(runtime)
    target = agent._extract_click_target("click on the login button")
    assert target == "login button"


@pytest.mark.asyncio
async def test_agent_execution_stream():
    runtime = MagicMock(spec=WebRuntime)
    runtime.cdp = MagicMock()
    runtime.cdp.is_connected = True
    runtime.get_current_url = AsyncMock(return_value="https://news.ycombinator.com")
    runtime.observe = AsyncMock(
        return_value=[
            ElementCandidate(
                candidate_id=1,
                backend_node_id=123,
                role="link",
                name="Hacker News",
                box=BoundingBox(x=0, y=0, width=100, height=20),
            )
        ]
    )
    runtime.get_screenshot = AsyncMock(return_value="fake_b64")
    runtime.cdp.evaluate = AsyncMock(return_value=["Top Story"])

    agent = AutonomousBrowserAgent(runtime)
    events = []
    async for event in agent.execute_instruction("summarize the page"):
        events.append(event)

    assert len(events) > 0
    answer_events = [e for e in events if e.get("type") == "answer"]
    assert len(answer_events) == 1
