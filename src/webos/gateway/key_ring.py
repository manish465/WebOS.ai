"""
Resilient key ring and rate-limit manager for free-tier cloud LLM providers.
"""

import time
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass, field


@dataclass
class KeySlot:
    provider: str
    api_key: str
    rpm_limit: int
    rpd_limit: int
    request_timestamps: List[float] = field(default_factory=list)
    cooldown_until: float = 0.0

    def is_available(self, now: float) -> bool:
        if now < self.cooldown_until:
            return False
        # Clean timestamps older than 60 seconds for RPM check
        self.request_timestamps = [
            ts for ts in self.request_timestamps if now - ts < 60.0
        ]
        return len(self.request_timestamps) < self.rpm_limit

    def record_use(self, now: float) -> None:
        self.request_timestamps.append(now)

    def trigger_cooldown(self, cooldown_seconds: float) -> None:
        self.cooldown_until = time.time() + cooldown_seconds


class KeyRing:
    """Manages a pool of free-tier API keys with rate-limit tracking and automatic failover."""

    def __init__(self) -> None:
        self._slots: List[KeySlot] = []

    def register_key(
        self,
        provider: str,
        api_key: str,
        rpm_limit: int = 15,
        rpd_limit: int = 1500,
    ) -> None:
        """Adds an API key to the rotation pool."""
        self._slots.append(
            KeySlot(
                provider=provider.lower().strip(),
                api_key=api_key.strip(),
                rpm_limit=rpm_limit,
                rpd_limit=rpd_limit,
            )
        )

    def acquire_key(
        self, provider: Optional[str] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Retrieves the next available (provider, api_key) tuple that is not on cooldown or rate-limited.
        If a specific provider is requested, filters by provider name.
        """
        now = time.time()
        for slot in self._slots:
            if provider and slot.provider != provider.lower().strip():
                continue
            if slot.is_available(now):
                slot.record_use(now)
                return (slot.provider, slot.api_key)
        return None

    def record_failure(
        self,
        provider: str,
        api_key: str,
        is_rate_limit: bool = True,
        cooldown_seconds: float = 60.0,
    ) -> None:
        """Puts a specific key into temporary cooldown (e.g. on HTTP 429)."""
        for slot in self._slots:
            if slot.provider == provider.lower().strip() and slot.api_key == api_key:
                slot.trigger_cooldown(cooldown_seconds if is_rate_limit else 10.0)
                break

    def has_available_keys(self, provider: Optional[str] = None) -> bool:
        """Checks if at least one key is ready to serve requests right now."""
        now = time.time()
        for slot in self._slots:
            if provider and slot.provider != provider.lower().strip():
                continue
            if slot.is_available(now):
                return True
        return False
