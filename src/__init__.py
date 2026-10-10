"""
WebOS.ai — Autonomous Browser Operating Runtime
"""

__version__ = "0.1.0"

from src.types import (
    BoundingBox,
    ElementCandidate,
    BrowserAction,
    VerificationResult,
    ObservationRecord,
    ModelResponse,
)
from src.runtime import WebRuntime
from src.gateway.key_ring import KeyRing
from src.gateway.sanitizer import PIISanitizer

__all__ = [
    "WebRuntime",
    "BoundingBox",
    "ElementCandidate",
    "BrowserAction",
    "VerificationResult",
    "ObservationRecord",
    "ModelResponse",
    "KeyRing",
    "PIISanitizer",
]
