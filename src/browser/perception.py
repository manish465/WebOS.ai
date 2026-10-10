"""
Zero-Token Perception Pruner using Chrome DevTools Accessibility and BoxModel APIs.
"""

import logging
from typing import List, Dict, Any, Optional
from src.types import ElementCandidate, BoundingBox
from src.browser.cdp_client import CDPClient

logger = logging.getLogger(__name__)


class PerceptionPruner:
    """
    Deterministically filters the ~10,000 DOM nodes down to <= 30 relevant interactive elements
    using Accessibility Trees and Viewport Geometry without consuming any LLM tokens.
    """

    INTERACTIVE_ROLES = {
        "button",
        "link",
        "combobox",
        "textbox",
        "checkbox",
        "radio",
        "menuitem",
        "tab",
        "searchbox",
    }

    @staticmethod
    def _parse_quad_box(quad: List[float]) -> Optional[BoundingBox]:
        """Converts an 8-float quad [x1, y1, x2, y2, x3, y3, x4, y4] to BoundingBox."""
        if len(quad) < 8:
            return None
        xs = [quad[0], quad[2], quad[4], quad[6]]
        ys = [quad[1], quad[3], quad[5], quad[7]]
        min_x = min(xs)
        min_y = min(ys)
        max_x = max(xs)
        max_y = max(ys)
        width = max_x - min_x
        height = max_y - min_y
        return BoundingBox(x=min_x, y=min_y, width=width, height=height)

    async def extract_candidates(
        self, cdp: CDPClient, max_candidates: int = 30
    ) -> List[ElementCandidate]:
        """
        Extracts visible, interactive element candidates on the active page.
        Consumes 0 LLM tokens and runs in < 100ms.
        """
        # 1. Fetch Full Accessibility Tree
        ax_result = await cdp.send("Accessibility.getFullAXTree")
        nodes = ax_result.get("nodes", [])

        candidates: List[ElementCandidate] = []
        candidate_id = 1

        for node in nodes:
            # Check role
            role_obj = node.get("role", {})
            role = role_obj.get("value", "").lower() if isinstance(role_obj, dict) else str(role_obj).lower()

            if role not in self.INTERACTIVE_ROLES:
                continue

            backend_node_id = node.get("backendDOMNodeId")
            if not backend_node_id:
                continue

            # Extract accessible name
            name_obj = node.get("name", {})
            name = name_obj.get("value", "").strip() if isinstance(name_obj, dict) else str(name_obj).strip()

            # Extract value if present
            value_obj = node.get("value", {})
            val = value_obj.get("value", "") if isinstance(value_obj, dict) else str(value_obj)
            val = val.strip() if val else None

            # 2. Query Geometry via DOM.getBoxModel
            box: Optional[BoundingBox] = None
            try:
                box_res = await cdp.send(
                    "DOM.getBoxModel", {"backendNodeId": backend_node_id}
                )
                model = box_res.get("model", {})
                content_quad = model.get("content") or model.get("border")
                if content_quad:
                    box = self._parse_quad_box(content_quad)
            except Exception:
                # Element may not be rendered or detached
                continue

            if not box or not box.is_visible():
                continue

            # Check if element is off-screen (e.g. negative coords or far below view)
            if box.x + box.width < 0 or box.y + box.height < 0:
                continue

            is_editable = role in {"textbox", "searchbox", "combobox"}
            is_clickable = role in {"button", "link", "checkbox", "radio", "tab", "menuitem"}

            candidates.append(
                ElementCandidate(
                    candidate_id=candidate_id,
                    backend_node_id=backend_node_id,
                    role=role,
                    name=name,
                    value=val,
                    box=box,
                    is_clickable=is_clickable,
                    is_editable=is_editable,
                )
            )
            candidate_id += 1

            if len(candidates) >= max_candidates:
                break

        return candidates
