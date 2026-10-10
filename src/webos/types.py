"""
Core data contracts and Action DSL for WebOS.ai.
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional, Dict, Any, List
import datetime


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + (self.width / 2.0)

    @property
    def center_y(self) -> float:
        return self.y + (self.height / 2.0)

    def is_visible(self) -> bool:
        return self.width > 0 and self.height > 0


@dataclass
class ElementCandidate:
    candidate_id: int
    backend_node_id: int
    role: str
    name: str
    value: Optional[str] = None
    box: Optional[BoundingBox] = None
    is_clickable: bool = True
    is_editable: bool = False
    attributes: Dict[str, str] = field(default_factory=dict)

    def to_compact_dict(self) -> Dict[str, Any]:
        """Compact dictionary format suitable for small LLM context prompts."""
        data = {
            "id": self.candidate_id,
            "role": self.role,
            "name": self.name,
        }
        if self.value:
            data["value"] = self.value
        if self.is_editable:
            data["editable"] = True
        return data


@dataclass
class BrowserAction:
    action_type: Literal["click", "fill", "type", "select", "upload", "scroll", "wait", "key_press", "press_enter"]
    target_candidate_id: Optional[int] = None
    value: Optional[str] = None
    text_value: Optional[str] = None
    file_path: Optional[str] = None
    selector_hint: Optional[str] = None
    key_code: Optional[str] = None

    def validate(self) -> bool:
        if self.value is None and self.text_value is not None:
            self.value = self.text_value
        if self.action_type in ("fill", "type") and self.value is None:
            raise ValueError(f"Action '{self.action_type}' requires a 'value'.")
        if self.action_type == "upload" and self.file_path is None:
            raise ValueError("Action 'upload' requires a 'file_path'.")
        return True


@dataclass
class VerificationResult:
    success: bool
    tier: Literal["tier1_deterministic", "tier2_semantic"]
    message: str
    url_changed: bool = False
    value_matches: bool = False
    network_settled: bool = True
    diff_summary: Optional[str] = None


@dataclass
class ObservationRecord:
    timestamp: datetime.datetime
    domain: str
    url: str
    field_label: str
    entered_value: str
    field_type: str
    context_tag: Optional[str] = None


@dataclass
class ModelResponse:
    content: str
    model_used: str
    tokens_prompt: int
    tokens_completion: int
    latency_ms: float
    is_fallback: bool = False
