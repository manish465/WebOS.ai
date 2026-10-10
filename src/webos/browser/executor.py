"""
Action executor primitives using Chrome DevTools Protocol input dispatch.
"""

import asyncio
import logging
from typing import Optional
from webos.types import BrowserAction, ElementCandidate
from webos.browser.cdp_client import CDPClient

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes deterministic low-level browser actions (clicks, keystrokes, uploads)."""

    async def execute(
        self,
        cdp: CDPClient,
        action: BrowserAction,
        candidate: Optional[ElementCandidate] = None,
    ) -> bool:
        """Executes a BrowserAction against the target element."""
        action.validate()

        if action.action_type == "click":
            if not candidate or not candidate.box:
                raise ValueError("Click action requires an ElementCandidate with valid bounding box.")
            return await self._click(cdp, candidate)

        elif action.action_type == "fill":
            if not candidate:
                raise ValueError("Fill action requires a target ElementCandidate.")
            return await self._fill(cdp, candidate, action.value or "")

        elif action.action_type == "upload":
            if not candidate or not action.file_path:
                raise ValueError("Upload action requires an ElementCandidate and file_path.")
            return await self._upload(cdp, candidate, action.file_path)

        elif action.action_type == "scroll":
            delta_y = int(action.value or "300")
            return await self._scroll(cdp, delta_y=delta_y)

        elif action.action_type == "wait":
            wait_time = float(action.value or "1.0")
            await asyncio.sleep(wait_time)
            return True

        else:
            raise NotImplementedError(f"Action type '{action.action_type}' is not supported.")

    async def _click(self, cdp: CDPClient, candidate: ElementCandidate) -> bool:
        """Dispatches native mouse events to the center of the element's box."""
        box = candidate.box
        assert box is not None
        cx = box.center_x
        cy = box.center_y

        # Scroll into view if needed
        try:
            await cdp.send("DOM.scrollIntoViewIfNeeded", {"backendNodeId": candidate.backend_node_id})
        except Exception:
            pass

        # Mouse press
        await cdp.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": cx,
                "y": cy,
                "button": "left",
                "clickCount": 1,
            },
        )
        # Mouse release
        await cdp.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": cx,
                "y": cy,
                "button": "left",
                "clickCount": 1,
            },
        )
        return True

    async def _fill(self, cdp: CDPClient, candidate: ElementCandidate, text: str) -> bool:
        """Focuses the field, clears it, and types new text."""
        # Focus element
        if candidate.box:
            await self._click(cdp, candidate)
        else:
            await cdp.send("DOM.focus", {"backendNodeId": candidate.backend_node_id})

        # Select all and clear existing content
        await cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "commands": ["selectAll"]})
        await cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace"})
        await cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace"})

        # Insert new text
        await cdp.send("Input.insertText", {"text": text})
        return True

    async def _upload(self, cdp: CDPClient, candidate: ElementCandidate, file_path: str) -> bool:
        """Attaches a local file directly to a file input element."""
        await cdp.send(
            "DOM.setFileInputFiles",
            {
                "files": [file_path],
                "backendNodeId": candidate.backend_node_id,
            },
        )
        return True

    async def _scroll(self, cdp: CDPClient, delta_y: int = 300) -> bool:
        """Dispatches mouseWheel event to scroll vertically."""
        await cdp.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": 200,
                "y": 200,
                "deltaX": 0,
                "deltaY": delta_y,
            },
        )
        return True
