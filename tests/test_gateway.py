"""
Unit tests for WebOS.ai Model Gateway and Privacy Air-Gap.
"""

import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from webos.types import ModelResponse
from webos.gateway.sanitizer import PIISanitizer
from webos.gateway.key_ring import KeyRing
from webos.gateway.clipboard import ClipboardPromptGenerator
from webos.gateway.providers import BaseProvider
from webos.gateway.router import ModelRouter


# --- Sanitizer Tests ---

def test_sanitizer_email_and_phone():
    sanitizer = PIISanitizer()
    raw = "My email is manish.dev@gmail.com and cell is +1 555-0199."
    sanitized, token_map = sanitizer.redact(raw)

    assert "manish.dev@gmail.com" not in sanitized
    assert "+1 555-0199" not in sanitized
    assert "<USER_EMAIL_1>" in sanitized
    assert "<USER_PHONE_1>" in sanitized

    restored = sanitizer.rehydrate(sanitized, token_map)
    assert restored == raw


def test_sanitizer_address():
    sanitizer = PIISanitizer()
    raw = "Ship to 1234 Elm Street, Apt 5."
    sanitized, token_map = sanitizer.redact(raw)

    assert "1234 Elm Street" not in sanitized
    assert "<USER_ADDRESS_1>" in sanitized

    restored = sanitizer.rehydrate(sanitized, token_map)
    assert restored == raw


# --- KeyRing Tests ---

def test_key_ring_rotation_and_cooldown():
    ring = KeyRing()
    ring.register_key("gemini", "key-alpha", rpm_limit=2)
    ring.register_key("groq", "key-beta", rpm_limit=2)

    # 1. Acquire first key
    k1 = ring.acquire_key()
    assert k1 == ("gemini", "key-alpha")

    # 2. Acquire second key (alpha still has 1 RPM remaining)
    k2 = ring.acquire_key()
    assert k2 == ("gemini", "key-alpha")

    # 3. Third request should rotate to beta since alpha exceeded 2 RPM
    k3 = ring.acquire_key()
    assert k3 == ("groq", "key-beta")

    # 4. Trigger rate limit cooldown on beta
    ring.record_failure("groq", "key-beta", is_rate_limit=True, cooldown_seconds=60.0)
    assert ring.has_available_keys() is False


# --- Clipboard Generator Tests ---

def test_clipboard_prompt_generation():
    prompt = "Fill the 'Years of Experience' field"
    system = "You are a web automation assistant."
    context = {"fields": [{"id": 1, "label": "Experience"}]}

    clipboard_text = ClipboardPromptGenerator.generate(
        prompt=prompt, system_prompt=system, context_data=context
    )

    assert "# WebOS.ai Automation Request" in clipboard_text
    assert "## System Role" in clipboard_text
    assert "You are a web automation assistant." in clipboard_text
    assert "## Page Context / Input Data" in clipboard_text
    assert '"label": "Experience"' in clipboard_text
    assert "## Expected Output" in clipboard_text


# --- Router Tests ---

class MockSuccessProvider(BaseProvider):
    async def generate(self, prompt: str, system_prompt=None):
        return ModelResponse(
            content=f"Processed: {prompt}",
            model_used="mock-success",
            tokens_prompt=10,
            tokens_completion=5,
            latency_ms=25.0,
        )


class MockFailingProvider(BaseProvider):
    async def generate(self, prompt: str, system_prompt=None):
        raise RuntimeError("Service unavailable")


@pytest.mark.asyncio
async def test_router_local_success():
    local = MockSuccessProvider()
    router = ModelRouter(local_provider=local)
    resp = await router.query(prompt="Hello local model", prefer_local=True)

    assert resp.model_used == "mock-success"
    assert "Processed: Hello local model" in resp.content
    assert resp.is_fallback is False


@pytest.mark.asyncio
async def test_router_cloud_redaction_and_rehydration():
    local = MockFailingProvider()
    ring = KeyRing()
    ring.register_key("gemini", "dummy-key")
    sanitizer = PIISanitizer()

    router = ModelRouter(key_ring=ring, sanitizer=sanitizer, local_provider=local)

    # Mock the Gemini provider's generate method
    mock_cloud_resp = ModelResponse(
        content="Applicant <USER_EMAIL_1> has been registered.",
        model_used="gemini-1.5-flash",
        tokens_prompt=15,
        tokens_completion=10,
        latency_ms=100.0,
    )

    with patch("webos.gateway.router.GeminiFlashProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_cloud_resp
        resp = await router.query(
            prompt="Register john@example.com into system", prefer_local=True
        )

        assert resp.model_used == "gemini-1.5-flash"
        # Confirm rehydration succeeded
        assert "john@example.com" in resp.content
        assert "<USER_EMAIL_1>" not in resp.content


@pytest.mark.asyncio
async def test_router_clipboard_fallback():
    local = MockFailingProvider()
    ring = KeyRing()  # No cloud keys registered
    router = ModelRouter(key_ring=ring, local_provider=local)

    resp = await router.query(
        prompt="Click the submit button", prefer_local=True, allow_cloud=True
    )

    assert resp.is_fallback is True
    assert resp.model_used == "clipboard_fallback"
    assert "# WebOS.ai Automation Request" in resp.content
    assert "Click the submit button" in resp.content
