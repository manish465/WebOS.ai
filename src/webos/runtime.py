"""
Master WebRuntime orchestrating Browser, Storage, and Model Gateway subsystems.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import datetime

from webos.types import (
    BoundingBox,
    ElementCandidate,
    BrowserAction,
    VerificationResult,
    ObservationRecord,
    ModelResponse,
)
from webos.storage.db import DatabaseManager
from webos.storage.episodic import EpisodicMemory
from webos.storage.flight_recorder import FlightRecorder
from webos.gateway.key_ring import KeyRing
from webos.gateway.sanitizer import PIISanitizer
from webos.gateway.router import ModelRouter
from webos.gateway.providers import LocalLlamaProvider, BaseProvider
from webos.browser.cdp_client import CDPClient
from webos.browser.perception import PerceptionPruner
from webos.browser.executor import ActionExecutor
from webos.browser.verifier import StateVerifier
from webos.browser.hud import HUDOverlay
from webos.browser.skills import SkillManager, SkillStep, SiteSkill

logger = logging.getLogger(__name__)


class WebRuntime:
    """
    Unified operating substrate for autonomous browser automation.
    Exposes a high-level API for domain plugins (e.g., JobPilot.ai).
    """

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        key_ring: Optional[KeyRing] = None,
        local_provider: Optional[BaseProvider] = None,
    ) -> None:
        # Storage Subsystem
        self.db = DatabaseManager(db_path=db_path)
        self.episodic = EpisodicMemory(self.db)
        self.flight_recorder = FlightRecorder(self.db)
        self.skills = SkillManager(self.db)

        # Model Gateway Subsystem
        self.key_ring = key_ring or KeyRing()
        self.sanitizer = PIISanitizer()
        self.router = ModelRouter(
            key_ring=self.key_ring,
            sanitizer=self.sanitizer,
            local_provider=local_provider or LocalLlamaProvider(),
        )

        # Browser Engine Subsystem
        self.cdp = CDPClient()
        self.pruner = PerceptionPruner()
        self.executor = ActionExecutor()
        self.verifier = StateVerifier()
        self.hud = HUDOverlay()

        self._active_session_id: Optional[str] = None

    async def connect(
        self, host: str = "127.0.0.1", port: int = 9222, target_index: int = 0
    ) -> str:
        """Connects to real Chrome profile via CDP and injects the HUD overlay."""
        target_id = await self.cdp.connect(host=host, port=port, target_index=target_index)
        try:
            await self.hud.inject_hud(self.cdp)
        except Exception as e:
            logger.warning("Could not inject HUD overlay: %s", e)

        # Start a flight recorder telemetry session
        current_url = await self.get_current_url()
        domain = current_url.split("//")[-1].split("/")[0] if current_url else "unknown"
        self._active_session_id = self.flight_recorder.start_session(domain=domain)
        return target_id

    async def open_tab(self, url: str) -> str:
        """Opens a brand new tab in Chrome with the given URL, switches to it, and brings Chrome to the front."""
        target_data = await self.cdp.create_new_tab(url)
        try:
            await self.hud.inject_hud(self.cdp)
        except Exception as e:
            logger.debug("Could not inject HUD in new tab: %s", e)
        await asyncio.sleep(1.0)
        return str(target_data.get("id", ""))

    async def navigate(self, url: str, open_new_if_needed: bool = False) -> None:
        """Navigates to the specified URL and brings the Chrome window to the front."""
        if open_new_if_needed:
            targets = await self.cdp.get_all_page_targets()
            domain = url.split("//")[-1].split("/")[0].lower()
            matching = [t for t in targets if domain in t.get("url", "").lower()]
            if matching:
                await self.cdp.activate_tab(matching[0]["id"])
                await self.cdp.bring_to_front()
                return
            else:
                await self.open_tab(url)
                return

        await self.hud.set_status(self.cdp, f"Navigating to {url}...")
        await self.cdp.send("Page.navigate", {"url": url})
        await self.cdp.bring_to_front()
        # Wait for page load event
        await asyncio.sleep(0.8)
        await self.hud.set_status(self.cdp, "Ready")

    async def get_current_url(self) -> str:
        """Retrieves the active window URL."""
        if not self.cdp.is_connected:
            return ""
        val = await self.cdp.evaluate("window.location.href")
        return str(val or "")

    async def perform_search(self, query: str, max_retries: int = 15, retry_interval: float = 0.4) -> bool:
        """
        Locates the primary search input on the active page (supports Amazon, Google,
        YouTube, Wikipedia, GitHub, and any e-commerce/search site), inputs the query,
        and submits the search form. Dynamically polls until DOM search element is ready.
        """
        import json
        escaped_query = json.dumps(query)
        script = f"""
        (() => {{
            const query = {escaped_query};
            const selectors = [
                '#twotabsearchtextbox',
                'input[name="field-keywords"]',
                'textarea[name="q"]',
                'input[name="q"]',
                'input[name="search"]',
                'input[type="search"]',
                'input[placeholder*="search" i]',
                'input[aria-label*="search" i]',
                'input[id*="search" i]',
                'input[name*="search" i]',
                'input[type="text"]'
            ];
            for (const sel of selectors) {{
                const el = document.querySelector(sel);
                if (el && (el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0)) {{
                    el.focus();
                    el.value = query;
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    const form = el.form || el.closest('form');
                    if (form) {{
                        if (typeof form.requestSubmit === 'function') {{
                            form.requestSubmit();
                        }} else {{
                            form.submit();
                        }}
                    }} else {{
                        el.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        el.dispatchEvent(new KeyboardEvent('keypress', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                        el.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
                    }}
                    return {{ success: true, selector: sel }};
                }}
            }}
            return {{ success: false }};
        }})()
        """
        for _ in range(max_retries):
            try:
                res = await self.cdp.evaluate(script)
                if res and isinstance(res, dict) and res.get("success"):
                    # Dispatch native Enter key via CDP to guarantee form submission
                    try:
                        await self.cdp.send(
                            "Input.dispatchKeyEvent",
                            {"type": "rawKeyDown", "windowsVirtualKeyCode": 13, "unmodifiedText": "\\r", "text": "\\r"},
                        )
                        await self.cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13})
                    except Exception:
                        pass
                    return True
            except Exception:
                pass
            await asyncio.sleep(retry_interval)

        return False

    async def get_screenshot(self, format: str = "jpeg", quality: int = 70) -> str:
        """Captures a base64-encoded screenshot of the active browser viewport."""
        if not self.cdp.is_connected:
            return ""
        try:
            res = await self.cdp.send(
                "Page.captureScreenshot",
                {"format": format, "quality": quality},
            )
            return res.get("data", "")
        except Exception as e:
            logger.warning("Failed to capture screenshot: %s", e)
            return ""

    async def observe(self, max_candidates: int = 30) -> List[ElementCandidate]:
        """
        Extracts visible, interactive candidates from the active page
        using 0 LLM tokens in < 100ms.
        """
        await self.hud.set_status(self.cdp, "Scanning elements...")
        candidates = await self.pruner.extract_candidates(
            self.cdp, max_candidates=max_candidates
        )
        await self.hud.set_status(self.cdp, f"Found {len(candidates)} candidates")
        return candidates

    async def perceive(self, max_candidates: int = 30) -> List[ElementCandidate]:
        """Plugin compatibility alias for observe()."""
        return await self.observe(max_candidates=max_candidates)

    async def execute(
        self,
        action: BrowserAction,
        intent: Optional[str] = None,
        candidate: Optional[ElementCandidate] = None,
    ) -> VerificationResult:
        """Plugin compatibility alias for execute_step()."""
        act_intent = intent or f"{action.action_type} #{action.target_candidate_id or ''}"
        return await self.execute_step(act_intent, action, candidate=candidate)

    async def ground_intent(
        self, intent: str, candidates: List[ElementCandidate]
    ) -> Optional[ElementCandidate]:
        """
        Uses compact candidate list and intent prompt to identify target element.
        Falls back to deterministic name/role heuristic if model is unavailable.
        """
        if not candidates:
            return None

        # 1. Deterministic Fast Path (Exact Name/Role match, 0 tokens)
        norm_intent = intent.lower().strip()
        for c in candidates:
            if c.name and (norm_intent in c.name.lower() or c.name.lower() in norm_intent):
                return c

        # 2. Local 3B Classifier Prompt
        compact_list = [c.to_compact_dict() for c in candidates[:25]]
        prompt = (
            f"Given these interactive web elements:\n{compact_list}\n\n"
            f"Which element ID matches the user intent: '{intent}'?\n"
            f"Respond with ONLY the integer ID."
        )
        try:
            resp = await self.router.query(prompt=prompt, prefer_local=True, allow_cloud=False)
            digits = "".join(filter(str.isdigit, resp.content))
            if digits:
                chosen_id = int(digits)
                for c in candidates:
                    if c.candidate_id == chosen_id:
                        return c
        except Exception as e:
            logger.warning("Grounding model query failed: %s", e)

        # Fallback to first clickable or editable candidate
        return candidates[0]

    async def execute_step(
        self,
        intent: str,
        action: BrowserAction,
        candidate: Optional[ElementCandidate] = None,
        initial_url: Optional[str] = None,
    ) -> VerificationResult:
        """
        Executes a browser action, verifies state change, and updates episodic memory.
        """
        await self.hud.set_status(self.cdp, f"Executing: {intent}...")
        init_url = initial_url or await self.get_current_url()

        # Execute
        await self.executor.execute(self.cdp, action, candidate)

        # Verify
        result = await self.verifier.verify_action(
            self.cdp, action, candidate=candidate, initial_url=init_url
        )

        if self._active_session_id:
            self.flight_recorder.record_step(self._active_session_id)

        # Log successful input to episodic memory
        if result.success and action.action_type == "fill" and candidate:
            current_url = await self.get_current_url()
            domain = current_url.split("//")[-1].split("/")[0] if current_url else "unknown"
            self.episodic.log_observation(
                ObservationRecord(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    domain=domain,
                    url=current_url,
                    field_label=candidate.name or intent,
                    entered_value=action.value or "",
                    field_type="text",
                )
            )

        status_msg = "Step Verified ✓" if result.success else f"Step Warning: {result.message}"
        await self.hud.set_status(self.cdp, status_msg)
        return result

    async def close(self) -> None:
        """Closes browser connections and persistent storage."""
        if self._active_session_id:
            self.flight_recorder.end_session(
                session_id=self._active_session_id, status="completed"
            )
        await self.cdp.close()
        self.db.close()
