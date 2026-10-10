"""
Model router managing local inference, cloud failover, and clipboard fallback.
"""

import logging
from typing import Optional, Dict, Any
import httpx
from src.types import ModelResponse
from src.gateway.sanitizer import PIISanitizer
from src.gateway.key_ring import KeyRing
from src.gateway.providers import (
    BaseProvider,
    LocalLlamaProvider,
    GeminiFlashProvider,
    GroqProvider,
)
from src.gateway.clipboard import ClipboardPromptGenerator

logger = logging.getLogger(__name__)


class ModelRouter:
    """Dispatches model requests through local, cloud, and fallback channels."""

    def __init__(
        self,
        key_ring: Optional[KeyRing] = None,
        sanitizer: Optional[PIISanitizer] = None,
        local_provider: Optional[BaseProvider] = None,
    ) -> None:
        self.key_ring = key_ring or KeyRing()
        self.sanitizer = sanitizer or PIISanitizer()
        self.local_provider = local_provider or LocalLlamaProvider()

    async def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        prefer_local: bool = True,
        allow_cloud: bool = True,
    ) -> ModelResponse:
        """
        Executes model query with automatic multi-tier fallback:
        1. Local 3B Model (if requested and accessible)
        2. Free-tier Cloud Pool (sanitized with PII air-gap)
        3. 1-Click Clipboard Markdown Prompt (when all keys exhausted)
        """
        # 1. Try Local Model
        if prefer_local and self.local_provider:
            try:
                return await self.local_provider.generate(
                    prompt=prompt, system_prompt=system_prompt
                )
            except Exception as e:
                logger.warning("Local model unavailable, falling back to cloud: %s", e)

        # 2. Try Cloud Pool with Privacy Air-Gap
        if allow_cloud and self.key_ring.has_available_keys():
            sanitized_prompt, prompt_map = self.sanitizer.redact(prompt)
            sanitized_system = None
            system_map = {}
            if system_prompt:
                sanitized_system, system_map = self.sanitizer.redact(system_prompt)
            merged_map = {**prompt_map, **system_map}

            # Attempt cloud providers via key ring
            while True:
                key_info = self.key_ring.acquire_key()
                if not key_info:
                    break

                provider_name, api_key = key_info
                try:
                    provider: BaseProvider
                    if provider_name == "gemini":
                        provider = GeminiFlashProvider(api_key=api_key)
                    elif provider_name == "groq":
                        provider = GroqProvider(api_key=api_key)
                    else:
                        continue

                    response = await provider.generate(
                        prompt=sanitized_prompt, system_prompt=sanitized_system
                    )
                    # Rehydrate sanitized tokens locally
                    response.content = self.sanitizer.rehydrate(
                        response.content, merged_map
                    )
                    return response

                except httpx.HTTPStatusError as err:
                    if err.response.status_code == 429:
                        logger.warning("Rate limit hit on %s. Rotating key...", provider_name)
                        self.key_ring.record_failure(provider_name, api_key, is_rate_limit=True)
                    else:
                        logger.error("HTTP error on %s: %s", provider_name, err)
                        self.key_ring.record_failure(provider_name, api_key, is_rate_limit=False)
                except Exception as err:
                    logger.error("Provider %s error: %s", provider_name, err)
                    self.key_ring.record_failure(provider_name, api_key, is_rate_limit=False)

        # 3. Final Fallback: 1-Click Clipboard Prompt
        logger.info("Cloud and local routes exhausted. Generating clipboard prompt fallback.")
        clipboard_text = ClipboardPromptGenerator.generate(
            prompt=prompt, system_prompt=system_prompt
        )
        return ModelResponse(
            content=clipboard_text,
            model_used="clipboard_fallback",
            tokens_prompt=0,
            tokens_completion=0,
            latency_ms=0.0,
            is_fallback=True,
        )
