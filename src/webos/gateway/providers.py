"""
Model provider adapters for local Llama, Google Gemini, and Groq.
"""

from abc import ABC, abstractmethod
import time
import json
from typing import Optional, Dict, Any
import httpx
from webos.types import ModelResponse


class BaseProvider(ABC):
    """Abstract interface for LLM provider adapters."""

    @abstractmethod
    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> ModelResponse:
        pass


class LocalLlamaProvider(BaseProvider):
    """Adapter for locally hosted models via Ollama or llama.cpp server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "llama3.2:3b",
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> ModelResponse:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        start_time = time.time()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000.0
        return ModelResponse(
            content=data.get("response", "").strip(),
            model_used=self.model_name,
            tokens_prompt=data.get("prompt_eval_count", 0),
            tokens_completion=data.get("eval_count", 0),
            latency_ms=latency_ms,
        )


class GeminiFlashProvider(BaseProvider):
    """Adapter for Google Gemini 1.5/2.0 Flash via REST API."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-1.5-flash",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> ModelResponse:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {"contents": contents}

        start_time = time.time()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000.0
        candidates = data.get("candidates", [])
        text = ""
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            if parts:
                text = parts[0].get("text", "")

        usage = data.get("usageMetadata", {})
        return ModelResponse(
            content=text.strip(),
            model_used=self.model_name,
            tokens_prompt=usage.get("promptTokenCount", 0),
            tokens_completion=usage.get("candidatesTokenCount", 0),
            latency_ms=latency_ms,
        )


class GroqProvider(BaseProvider):
    """Adapter for Groq Cloud API (OpenAI-compatible)."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "llama-3.3-70b-versatile",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> ModelResponse:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
        }

        start_time = time.time()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        latency_ms = (time.time() - start_time) * 1000.0
        choices = data.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = data.get("usage", {})

        return ModelResponse(
            content=text.strip(),
            model_used=self.model_name,
            tokens_prompt=usage.get("prompt_tokens", 0),
            tokens_completion=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
        )
