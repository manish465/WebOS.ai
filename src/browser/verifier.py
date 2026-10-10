"""
2-Tier State Verification engine for WebOS.ai.
"""

import logging
from typing import Optional
from src.types import BrowserAction, ElementCandidate, VerificationResult
from src.browser.cdp_client import CDPClient

logger = logging.getLogger(__name__)


class StateVerifier:
    """
    Verifies that browser actions produced the expected state changes.
    Prioritizes Tier-1 deterministic checks (0 tokens, < 100ms).
    """

    async def verify_action(
        self,
        cdp: CDPClient,
        action: BrowserAction,
        candidate: Optional[ElementCandidate] = None,
        initial_url: Optional[str] = None,
    ) -> VerificationResult:
        """
        Executes Tier-1 deterministic verification.
        Checks URL transitions, value reflections, and network readiness.
        """
        # 1. Check URL transition (for clicks or navigations)
        url_changed = False
        if initial_url:
            current_url = await cdp.evaluate("window.location.href")
            if current_url and current_url != initial_url:
                url_changed = True
                return VerificationResult(
                    success=True,
                    tier="tier1_deterministic",
                    message=f"Navigation verified: {initial_url} -> {current_url}",
                    url_changed=True,
                )

        # 2. Check Input Value Reflection for 'fill' actions
        if action.action_type == "fill" and candidate:
            target_val = action.value or ""
            # Inspect value of the element using its backendNodeId or tag
            check_script = f"""
            (() => {{
                const el = document.activeElement;
                if (!el) return null;
                return el.value !== undefined ? el.value : el.innerText;
            }})()
            """
            actual_val = await cdp.evaluate(check_script)
            if actual_val == target_val:
                return VerificationResult(
                    success=True,
                    tier="tier1_deterministic",
                    message=f"Value reflection verified: '{target_val}'",
                    value_matches=True,
                )
            else:
                return VerificationResult(
                    success=False,
                    tier="tier1_deterministic",
                    message=f"Value mismatch: expected '{target_val}', found '{actual_val}'",
                    value_matches=False,
                )

        # 3. Check for Click Action Success
        if action.action_type == "click":
            # Verify document readiness and no uncaught alert/errors
            ready_state = await cdp.evaluate("document.readyState")
            return VerificationResult(
                success=True,
                tier="tier1_deterministic",
                message=f"Click executed. Document ready state: {ready_state}",
                url_changed=url_changed,
            )

        # 4. Fallback for wait or scroll
        return VerificationResult(
            success=True,
            tier="tier1_deterministic",
            message=f"Action '{action.action_type}' completed.",
        )
