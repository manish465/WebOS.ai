"""
Unit tests for WebOS.ai State Verifier, HUD Overlay, and Self-Healing Skills.
"""

import pytest
from unittest.mock import AsyncMock
from src.types import BrowserAction, ElementCandidate, BoundingBox
from src.storage.db import DatabaseManager
from src.browser.verifier import StateVerifier
from src.browser.hud import HUDOverlay
from src.browser.skills import SkillManager, SkillStep, SiteSkill


# --- Verifier Tests ---

@pytest.mark.asyncio
async def test_verifier_url_change():
    verifier = StateVerifier()
    mock_cdp = AsyncMock()
    mock_cdp.evaluate.return_value = "https://example.com/next-page"

    action = BrowserAction(action_type="click", target_candidate_id=1)
    res = await verifier.verify_action(
        mock_cdp, action, initial_url="https://example.com/login"
    )

    assert res.success is True
    assert res.url_changed is True
    assert "Navigation verified" in res.message


@pytest.mark.asyncio
async def test_verifier_fill_value_reflection_success():
    verifier = StateVerifier()
    mock_cdp = AsyncMock()
    mock_cdp.evaluate.return_value = "manish@example.com"

    candidate = ElementCandidate(
        candidate_id=1, backend_node_id=10, role="textbox", name="Email"
    )
    action = BrowserAction(action_type="fill", target_candidate_id=1, value="manish@example.com")

    res = await verifier.verify_action(mock_cdp, action, candidate=candidate)

    assert res.success is True
    assert res.value_matches is True
    assert "Value reflection verified" in res.message


@pytest.mark.asyncio
async def test_verifier_fill_value_reflection_mismatch():
    verifier = StateVerifier()
    mock_cdp = AsyncMock()
    mock_cdp.evaluate.return_value = ""  # Value was not populated

    candidate = ElementCandidate(
        candidate_id=1, backend_node_id=10, role="textbox", name="Email"
    )
    action = BrowserAction(action_type="fill", target_candidate_id=1, value="manish@example.com")

    res = await verifier.verify_action(mock_cdp, action, candidate=candidate)

    assert res.success is False
    assert res.value_matches is False
    assert "Value mismatch" in res.message


# --- HUD Overlay Tests ---

@pytest.mark.asyncio
async def test_hud_status_update():
    hud = HUDOverlay()
    mock_cdp = AsyncMock()

    await hud.set_status(mock_cdp, "Filling Application...")
    mock_cdp.evaluate.assert_called_once()
    call_script = mock_cdp.evaluate.call_args[0][0]
    assert "Filling Application..." in call_script


@pytest.mark.asyncio
async def test_hud_pause_and_recording():
    hud = HUDOverlay()
    mock_cdp = AsyncMock()

    # Test is_paused check
    mock_cdp.evaluate.return_value = True
    paused = await hud.is_paused(mock_cdp)
    assert paused is True

    # Test disable_recording event retrieval
    mock_events = [
        {"type": "click", "tag": "button", "id": "submit-btn", "value": "Submit"}
    ]
    mock_cdp.evaluate.return_value = mock_events
    recorded = await hud.disable_recording(mock_cdp)
    assert len(recorded) == 1
    assert recorded[0]["id"] == "submit-btn"


# --- Skill Manager & Self-Healing Tests ---

@pytest.fixture
def memory_db():
    db = DatabaseManager(db_path=":memory:")
    yield db
    db.close()


def test_skill_save_and_load(memory_db):
    manager = SkillManager(memory_db)
    steps = [
        SkillStep(
            step_name="Click Apply",
            primary_selector="#apply-btn",
            aria_role="button",
            accessible_name="Apply Now",
            action_type="click",
        ),
        SkillStep(
            step_name="Fill Name",
            primary_selector="input[name='full_name']",
            aria_role="textbox",
            accessible_name="Full Name",
            action_type="fill",
            value="Manish",
        ),
    ]

    skill_id = manager.save_skill(domain="greenhouse.io", task_name="apply_job", steps=steps)
    assert skill_id == "greenhouse.io:apply_job"

    loaded = manager.load_skill(domain="greenhouse.io", task_name="apply_job")
    assert loaded is not None
    assert len(loaded.steps) == 2
    assert loaded.steps[0].primary_selector == "#apply-btn"
    assert loaded.steps[1].value == "Manish"


@pytest.mark.asyncio
async def test_skill_self_healing_resolution(memory_db):
    manager = SkillManager(memory_db)
    mock_cdp = AsyncMock()

    step = SkillStep(
        step_name="Submit Form",
        primary_selector="#old-broken-id",
        aria_role="button",
        accessible_name="Submit Application",
        action_type="click",
    )

    # Simulate: Primary selector check returns False (element not found by old ID)
    # But secondary ARIA check returns "#new-healed-button"
    async def mock_evaluate(script):
        if "#old-broken-id" in script:
            return False
        if "targetRole" in script and "targetName" in script:
            return "#new-healed-button"
        return None

    mock_cdp.evaluate.side_effect = mock_evaluate

    resolved_sel, is_healed = await manager.resolve_step_element(mock_cdp, step)

    assert is_healed is True
    assert resolved_sel == "#new-healed-button"

    # Persist the self-healed step
    skill = SiteSkill(
        skill_id="test:submit",
        domain="test",
        task_name="submit",
        steps=[step],
    )
    manager.heal_step(skill, step_index=0, new_selector="#new-healed-button")

    # Verify that database has been updated with the healed selector
    reloaded = manager.load_skill("test", "submit")
    assert reloaded is not None
    assert reloaded.steps[0].primary_selector == "#new-healed-button"
