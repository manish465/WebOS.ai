"""
1-Click Clipboard prompt generator for web ChatGPT / Claude fallback.
"""

from typing import Optional, Dict, Any
import json


class ClipboardPromptGenerator:
    """Formats prompts into clean, delimited Markdown for manual web LLM execution."""

    @staticmethod
    def generate(
        prompt: str,
        system_prompt: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Constructs a structured, human-readable prompt block."""
        parts = ["# WebOS.ai Automation Request\n"]

        if system_prompt:
            parts.append(f"## System Role\n{system_prompt.strip()}\n")

        if context_data:
            formatted_context = json.dumps(context_data, indent=2)
            parts.append(f"## Page Context / Input Data\n```json\n{formatted_context}\n```\n")

        parts.append(f"## User Goal / Task\n{prompt.strip()}\n")
        parts.append(
            "## Expected Output\n"
            "Please return ONLY valid JSON matching the requested schema. "
            "Do not include conversational preamble or markdown explanations outside the code block."
        )

        return "\n".join(parts)
