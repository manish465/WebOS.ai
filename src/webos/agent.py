"""
WebOS.ai — Autonomous General-Purpose Browser Agent

Translates high-level natural language instructions into verified multi-step
browser actions across any website using zero-token perception and intent grounding.
Supports optional domain plugins (e.g. JobPilot.ai).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import AsyncGenerator, Dict, Any, List, Optional
from urllib.parse import urlparse

from webos.runtime import WebRuntime
from webos.types import BrowserAction, ElementCandidate, VerificationResult

logger = logging.getLogger(__name__)


class AutonomousBrowserAgent:
    """General-purpose autonomous agent orchestrating WebRuntime."""

    def __init__(self, runtime: WebRuntime) -> None:
        self.runtime = runtime

    async def execute_instruction(
        self, instruction: str, max_steps: int = 8
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Executes a natural language instruction against the active browser session,
        yielding structured progress events for real-time UI streaming.
        """
        instruction = instruction.strip()
        if not instruction:
            yield {"type": "error", "message": "Instruction is empty."}
            return

        yield {"type": "thought", "content": f"Interpreting request: '{instruction}'"}

        # Check if Chrome is connected
        if not self.runtime.cdp.is_connected:
            yield {"type": "thought", "content": "Attempting connection to Chrome on port 9222..."}
            try:
                await self.runtime.connect(port=9222)
                yield {"type": "status", "content": "Connected to Chrome CDP session."}
            except Exception as e:
                yield {
                    "type": "error",
                    "message": (
                        f"Could not connect to Chrome on port 9222: {e}. "
                        "Please start Chrome with: chrome.exe --remote-debugging-port=9222"
                    ),
                }
                return

        # Check for @jobpilot or JobPilot plugin invocation
        lower_inst = instruction.lower()
        is_jobpilot = "@jobpilot" in lower_inst or any(
            kw in lower_inst for kw in ["jobpilot", "auto apply", "auto-apply", "apply to job", "tailor resume"]
        )
        if is_jobpilot:
            cleaned_instruction = re.sub(r"@jobpilot\b", "", instruction, flags=re.IGNORECASE).strip()
            async for event in self._handle_jobpilot_plugin(cleaned_instruction or instruction):
                yield event
            return

        # Strip optional @browser or @web mention for general browser tasks
        cleaned_instruction = re.sub(r"@(browser|web)\b", "", instruction, flags=re.IGNORECASE).strip()
        current_task = cleaned_instruction if cleaned_instruction else instruction
        lower_inst = current_task.lower()

        # General Purpose Step Execution Loop
        steps_taken = 0

        while steps_taken < max_steps:
            steps_taken += 1
            current_url = await self.runtime.get_current_url()

            # 1. Check for explicit Navigation intent
            nav_target = self._extract_navigation_url(current_task)
            if nav_target and (not current_url or nav_target.lower() not in current_url.lower()):
                yield {
                    "type": "action",
                    "step": steps_taken,
                    "action": "navigate",
                    "target": nav_target,
                    "details": f"Navigating to {nav_target}",
                }
                try:
                    await self.runtime.navigate(nav_target)
                    await asyncio.sleep(1.0)
                    new_url = await self.runtime.get_current_url()
                    screenshot = await self.runtime.get_screenshot()
                    yield {
                        "type": "observation",
                        "step": steps_taken,
                        "url": new_url,
                        "screenshot": screenshot,
                        "message": f"Successfully loaded {new_url}",
                    }
                except Exception as err:
                    yield {"type": "error", "message": f"Navigation failed: {err}"}
                    return

                # If the goal was simply to navigate, finish
                if any(lower_inst.startswith(p) for p in ["go to", "open", "visit", "navigate to"]) and not any(
                    action_word in lower_inst for action_word in ["and search", "and click", "and find", "and fill"]
                ):
                    yield {
                        "type": "answer",
                        "content": f"Successfully navigated to **{new_url}**.",
                    }
                    return

            # 2. Observe the current page candidates
            yield {"type": "thought", "content": "Perceiving interactive elements via 0-token AXTree..."}
            candidates = await self.runtime.observe(max_candidates=35)
            screenshot = await self.runtime.get_screenshot()

            yield {
                "type": "observation",
                "step": steps_taken,
                "url": await self.runtime.get_current_url(),
                "candidates_count": len(candidates),
                "candidates": [c.to_compact_dict() for c in candidates[:15]],
                "screenshot": screenshot,
            }

            # 3. Search Intent (e.g., "search for mechanical keyboards", "google quantum computing")
            search_query = self._extract_search_query(instruction)
            if search_query:
                yield {
                    "type": "thought",
                    "content": f"Identified search query intent: '{search_query}'. Locating search input candidate...",
                }
                search_box = await self._find_search_candidate(candidates)
                if search_box:
                    yield {
                        "type": "action",
                        "step": steps_taken,
                        "action": "type",
                        "target": f"#{search_box.candidate_id} ({search_box.name or search_box.role})",
                        "value": search_query,
                    }
                    action = BrowserAction(
                        action_type="type",
                        target_candidate_id=search_box.candidate_id,
                        text_value=search_query,
                    )
                    await self.runtime.execute_step(f"Type search query: {search_query}", action, candidate=search_box)
                    await asyncio.sleep(0.3)

                    # Dispatch Enter key
                    press_enter = BrowserAction(action_type="key_press", key_code="Enter")
                    await self.runtime.execute_step("Press Enter", press_enter)
                    await asyncio.sleep(1.5)

                    new_url = await self.runtime.get_current_url()
                    screenshot = await self.runtime.get_screenshot()
                    yield {
                        "type": "observation",
                        "step": steps_taken,
                        "url": new_url,
                        "screenshot": screenshot,
                        "message": f"Submitted search for '{search_query}'.",
                    }
                    yield {
                        "type": "answer",
                        "content": f"Completed search for **'{search_query}'** on **{new_url}**.",
                    }
                    return

            # 4. Click Intent (e.g., "click login", "click the first article", "click apply")
            click_target_text = self._extract_click_target(instruction)
            if click_target_text:
                yield {"type": "thought", "content": f"Searching candidate matching: '{click_target_text}'..."}
                target_cand = await self.runtime.ground_intent(click_target_text, candidates)
                if target_cand:
                    yield {
                        "type": "action",
                        "step": steps_taken,
                        "action": "click",
                        "target": f"#{target_cand.candidate_id} '{target_cand.name}' ({target_cand.role})",
                    }
                    click_action = BrowserAction(
                        action_type="click", target_candidate_id=target_cand.candidate_id
                    )
                    res = await self.runtime.execute_step(
                        f"Click '{target_cand.name}'", click_action, candidate=target_cand
                    )
                    await asyncio.sleep(1.0)
                    new_url = await self.runtime.get_current_url()
                    screenshot = await self.runtime.get_screenshot()

                    yield {
                        "type": "observation",
                        "step": steps_taken,
                        "url": new_url,
                        "screenshot": screenshot,
                        "message": f"Clicked '{target_cand.name}'. Verification: {res.message}",
                    }
                    yield {
                        "type": "answer",
                        "content": f"Successfully clicked **{target_cand.name or target_cand.role}** (#{target_cand.candidate_id}). Current URL: {new_url}",
                    }
                    return
                else:
                    yield {
                        "type": "error",
                        "message": f"Could not find an interactable element matching '{click_target_text}'.",
                    }
                    return

            # 5. Scroll Intent
            if "scroll down" in lower_inst:
                scroll_act = BrowserAction(action_type="scroll", scroll_delta_y=600)
                await self.runtime.execute_step("Scroll down", scroll_act)
                await asyncio.sleep(0.5)
                screenshot = await self.runtime.get_screenshot()
                yield {
                    "type": "observation",
                    "screenshot": screenshot,
                    "message": "Scrolled viewport down by 600px.",
                }
                yield {"type": "answer", "content": "Scrolled down the page."}
                return

            # 6. Read / Summarize / Inspect Intent
            if any(w in lower_inst for w in ["what", "summarize", "read", "extract", "inspect", "show"]):
                page_title = await self.runtime.cdp.evaluate("document.title")
                page_h1 = await self.runtime.cdp.evaluate(
                    "Array.from(document.querySelectorAll('h1, h2, h3')).slice(0, 8).map(el => el.innerText.trim()).filter(Boolean)"
                )
                yield {
                    "type": "answer",
                    "content": (
                        f"### Page Summary: {page_title}\n"
                        f"- **URL**: {current_url}\n"
                        f"- **Key Headings**:\n"
                        + "\n".join([f"  * {h}" for h in (page_h1 or [])])
                        + f"\n- **Interactive Elements Detected**: {len(candidates)} elements ready for automation."
                    ),
                }
                return

            # If no rule triggered, ask for clarification or use LLM router
            yield {
                "type": "answer",
                "content": (
                    f"Analyzed page at **{current_url}** with {len(candidates)} interactive candidates. "
                    "You can tell me to: \n"
                    "- *'Go to <website>'*\n"
                    "- *'Search for <query>'*\n"
                    "- *'Click <button or link>'*\n"
                    "- *'Scroll down'*\n"
                    "- *'Run JobPilot on this tab'*"
                ),
            }
            break

    def _extract_navigation_url(self, text: str) -> Optional[str]:
        """Extracts a target URL or domain from an instruction."""
        # 1. Direct URL regex
        url_match = re.search(r"https?://[^\s]+", text)
        if url_match:
            return url_match.group(0).rstrip(".,;")

        # 2. "go to / open / visit <domain>"
        match = re.search(
            r"(?:go to|open|visit|navigate to)\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)",
            text,
            re.IGNORECASE,
        )
        if match:
            raw_target = match.group(1).rstrip(".,;")
            if not raw_target.startswith("http"):
                return f"https://{raw_target}"
            return raw_target

        # 3. Common shortcuts
        shortcuts = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "github": "https://github.com",
            "hacker news": "https://news.ycombinator.com",
            "wikipedia": "https://www.wikipedia.org",
            "amazon": "https://www.amazon.com",
            "linkedin": "https://www.linkedin.com",
        }
        for name, url in shortcuts.items():
            if f"go to {name}" in text.lower() or f"open {name}" in text.lower():
                return url

        return None

    def _extract_search_query(self, text: str) -> Optional[str]:
        """Extracts search query from commands like 'search for X' or 'google X'."""
        patterns = [
            r"search\s+(?:for\s+)?['\"]?([^'\"?]+)['\"]?",
            r"find\s+['\"]?([^'\"?]+)['\"]?",
            r"google\s+['\"]?([^'\"?]+)['\"]?",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                query = m.group(1).strip()
                # filter out navigation commands
                if not any(query.lower().startswith(x) for x in ["http", "www.", ".com"]):
                    return query
        return None

    def _extract_click_target(self, text: str) -> Optional[str]:
        """Extracts click target text from commands like 'click on X'."""
        patterns = [
            r"click\s+(?:on\s+)?(?:the\s+)?['\"]?([^'\"]+)['\"]?",
            r"press\s+(?:the\s+)?['\"]?([^'\"]+)['\"]?",
            r"select\s+(?:the\s+)?['\"]?([^'\"]+)['\"]?",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    async def _find_search_candidate(
        self, candidates: List[ElementCandidate]
    ) -> Optional[ElementCandidate]:
        """Locates the primary search input on the page."""
        # Check for candidates with role searchbox or matching name
        for c in candidates:
            if c.role in ["searchbox", "combobox"] or (
                c.role in ["textbox", "input"]
                and any(
                    term in (c.name or "").lower()
                    for term in ["search", "query", "find", "google"]
                )
            ):
                return c

        # Fallback to any textbox/input
        for c in candidates:
            if c.role in ["textbox", "input"]:
                return c
        return None

    async def _handle_jobpilot_plugin(
        self, instruction: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Delegates career/ATS requests to the JobPilot.ai plugin."""
        yield {
            "type": "thought",
            "content": "Activating domain plugin: **JobPilot.ai** (Career Alignment & ATS Engine)...",
        }
        try:
            # Dynamic import of JobPilot plugin
            import sys
            from pathlib import Path

            # Ensure JobPilot is on sys.path
            jobpilot_path = Path("D:/DEVLOPMENT/Projects/JobPilot.ai")
            if str(jobpilot_path) not in sys.path:
                sys.path.insert(0, str(jobpilot_path))

            from src.pilot import JobPilot

            pilot = JobPilot.from_dossier_path(
                dossier_path=jobpilot_path / "dossier" / "sample_dossier.md",
                runtime=self.runtime,
            )

            yield {"type": "thought", "content": "Scanning active tab for Job Description & skills..."}
            job, analysis = await pilot.scan_active_role()

            yield {
                "type": "observation",
                "message": f"Detected role: **{job.title}** at **{job.company}** (Fit score: {int(analysis.match_score * 100)}%)",
                "matched_skills": analysis.matched_skills,
                "missing_skills": analysis.missing_skills,
            }

            yield {"type": "thought", "content": "Compiling tailored 1-page LaTeX resume with 24-line budget..."}
            pdf_path = jobpilot_path / "artifacts" / "tailored_resume.pdf"
            compilation = pilot.compile_tailored_resume(analysis, output_pdf=pdf_path)

            yield {
                "type": "action",
                "action": "compile_resume",
                "pdf": str(compilation.pdf_path),
                "pages": compilation.page_count,
            }

            yield {"type": "thought", "content": "Executing ATS form filling on active page..."}
            result = await pilot.auto_apply(
                output_dir=jobpilot_path / "artifacts",
                auto_submit=False,
            )

            screenshot = await self.runtime.get_screenshot()
            yield {
                "type": "observation",
                "screenshot": screenshot,
                "message": f"ATS Form Fill Complete. Status: {result.status}",
            }

            yield {
                "type": "answer",
                "plugin": "jobpilot",
                "content": (
                    f"### 💼 @jobpilot: Application Flow Completed\n\n"
                    f"| Metric | Details |\n"
                    f"| :--- | :--- |\n"
                    f"| **Target Opportunity** | **{job.title}** at **{job.company}** |\n"
                    f"| **ATS Platform** | `{result.ats_type}` |\n"
                    f"| **Match Score** | **{int(analysis.match_score * 100)}%** ({len(analysis.matched_skills)} matched technologies) |\n"
                    f"| **Tailored Resume** | `artifacts/{compilation.pdf_path.name}` (Guaranteed **{compilation.page_count} page**) |\n"
                    f"| **Submission Safety** | **Review Pause** (Halted before final submission) |\n\n"
                    f"**Matched Technologies:** {', '.join(analysis.matched_skills) if analysis.matched_skills else 'None'}\n\n"
                    f"*(The application form has been populated with your dossier data and tailored PDF. The active tab is waiting for your manual review.)*"
                ),
            }

        except Exception as e:
            yield {
                "type": "error",
                "message": f"JobPilot plugin execution error: {e}",
            }
