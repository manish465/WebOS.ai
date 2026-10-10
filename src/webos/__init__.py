"""
WebOS.ai — Autonomous Browser Operating Runtime
"""

__version__ = "0.1.0"

from webos.types import (
    BoundingBox,
    ElementCandidate,
    BrowserAction,
    VerificationResult,
    ObservationRecord,
    ModelResponse,
)
from webos.runtime import WebRuntime
from webos.gateway.key_ring import KeyRing
from webos.gateway.sanitizer import PIISanitizer

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
