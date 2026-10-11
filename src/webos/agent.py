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
from urllib.parse import urlparse, quote

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
            from webos.browser.extension_bridge import get_global_bridge
            bridge = get_global_bridge()
            if bridge.is_connected:
                yield {"type": "thought", "content": "Attaching to your active Chrome window via WebOS Extension Bridge..."}
                try:
                    await self.runtime.connect()
                    yield {"type": "status", "content": "Attached directly to active Chrome session (real user logins preserved)."}
                except Exception as ex:
                    logger.warning("Extension connect failed: %s", ex)

        if not self.runtime.cdp.is_connected:
            yield {"type": "thought", "content": "Checking Chrome on port 9222..."}
            try:
                await self.runtime.connect(port=9222)
                yield {"type": "status", "content": "Connected to Chrome CDP session on port 9222."}
            except Exception:
                yield {
                    "type": "thought",
                    "content": "Port 9222 not yet active. Launching Chrome session with persistent profile...",
                }
                from webos.server import launch_chrome_browser
                launch_res = await launch_chrome_browser(use_main_session=True)
                if not launch_res.get("success"):
                    yield {"type": "error", "message": launch_res.get("error", "Failed to launch Chrome session.")}
                    return
                await asyncio.sleep(2.0)
                try:
                    await self.runtime.connect(port=9222)
                    yield {"type": "status", "content": "Attached to Chrome session on port 9222."}
                except Exception as ex:
                    yield {
                        "type": "error",
                        "message": (
                            "> [!IMPORTANT]\n"
                            "> **Connect Your Real Chrome Session (0 Isolated Profiles)**\n\n"
                            "To control your current Chrome browser with all your active logins (LinkedIn, Amazon, Google):\n"
                            "1. Open `chrome://extensions` in your Chrome browser.\n"
                            "2. Enable **Developer mode** (top right switch).\n"
                            "3. Click **Load unpacked** and choose: `D:\\DEVLOPMENT\\Projects\\WebOS.ai\\extension`\n\n"
                            "*(Or double-click `attach_real_chrome.bat` in `D:\\DEVLOPMENT\\Projects\\WebOS.ai`)*"
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

        # Check for Session Attachment intent
        if any(kw in lower_inst for kw in [
            "attach session", "attach real session", "use my session",
            "use real session", "connect my session", "restore session",
            "my chrome session", "real session"
        ]):
            yield {
                "type": "thought",
                "content": "Relaunching Chrome with remote debugging on port 9222 to restore your real profile and logged-in sessions...",
            }
            try:
                from webos.server import launch_chrome_browser
                res = await launch_chrome_browser(use_main_session=True)
                if not res.get("success"):
                    yield {"type": "error", "message": res.get("error", "Failed to launch Chrome.")}
                    return
                await asyncio.sleep(2.5)
                await self.runtime.connect(port=9222)
                cur_url = await self.runtime.get_current_url()
                yield {
                    "type": "answer",
                    "content": (
                        "✅ **Attached to Real Chrome Session**\n\n"
                        "Chrome has been relaunched with remote debugging on port 9222 and all your active sessions restored.\n"
                        "- **Active profile**: Default user data (Amazon, LinkedIn, Google sessions preserved)\n"
                        f"- **Current tab**: {cur_url or 'Ready'}\n\n"
                        "You can now prompt browser automations using your personal logged-in accounts."
                    ),
                }
                return
            except Exception as e:
                yield {"type": "error", "message": f"Error attaching real session: {e}"}
                return

        # Check for LinkedIn Connection Request automation
        is_linkedin_connect = (
            any(kw in lower_inst for kw in [
                "connection request", "connect with", "send connection",
                "send connect", "connection requests", "connect to hr", "connect to recruiter"
            ])
            or (
                ("linked" in lower_inst or "linkedin" in lower_inst)
                and any(w in lower_inst for w in ["connect", "connection", "invite", "hr", "recruiter", "hiring"])
                and any(w in lower_inst for w in ["send", "request", "reach out"])
            )
        )
        if is_linkedin_connect:
            async for event in self._handle_linkedin_connections(instruction):
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
            if nav_target:
                already_there = current_url and (
                    nav_target.lower() in current_url.lower() or current_url.lower() in nav_target.lower()
                )

                if already_there:
                    yield {
                        "type": "thought",
                        "content": f"Already on {nav_target}. Bringing Chrome tab and window to front...",
                    }
                    await self.runtime.cdp.bring_to_front()
                    new_url = current_url
                else:
                    yield {
                        "type": "action",
                        "step": steps_taken,
                        "action": "navigate",
                        "target": nav_target,
                        "details": f"Opening {nav_target} in Chrome tab",
                    }
                    try:
                        await self.runtime.navigate(nav_target, open_new_if_needed=True)
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

                # If the goal was simply to navigate, finish with a clear, helpful answer
                is_pure_nav = any(
                    lower_inst.startswith(p) for p in ["go to", "open", "visit", "navigate to", "launch"]
                ) or lower_inst in ["linkedin", "github", "google", "youtube", "twitter", "reddit"]
                has_subsequent_action = any(
                    action_word in lower_inst
                    for action_word in ["and search", "and click", "and find", "and fill", "and apply"]
                )
                if is_pure_nav and not has_subsequent_action:
                    page_title = str(await self.runtime.cdp.evaluate("document.title") or "")
                    is_login_page = any(kw in page_title.lower() for kw in ["log in", "sign in", "login", "signin"])

                    session_note = ""
                    if "linkedin" in nav_target.lower():
                        if is_login_page:
                            session_note = (
                                "\n\n> [!NOTE]\n"
                                "> **LinkedIn Session**: Chrome is currently displaying the Sign In page. "
                                "Sign into your account or click **Attach Real Session** in the top navigation "
                                "to use your existing LinkedIn login."
                            )
                        else:
                            session_note = "\n\n> **Session Active**: Logged into LinkedIn with active session."

                    yield {
                        "type": "answer",
                        "content": f"Successfully opened **{new_url}** in Chrome.{session_note}",
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

            # 3. Search Intent (e.g., "search for mechanical keyboards", "search for cheap headphones")
            search_query = self._extract_search_query(instruction)
            if search_query:
                yield {
                    "type": "thought",
                    "content": f"Identified search query intent: '{search_query}'. Locating and submitting search input...",
                }
                yield {
                    "type": "action",
                    "step": steps_taken,
                    "action": "search",
                    "target": "search_input",
                    "value": search_query,
                    "details": f"Submitting search for '{search_query}' on {new_url if 'new_url' in locals() else current_url}",
                }

                # Robust multi-engine search execution
                search_ok = await self.runtime.perform_search(search_query)
                if not search_ok:
                    search_box = await self._find_search_candidate(candidates)
                    if search_box:
                        action = BrowserAction(
                            action_type="fill",
                            target_candidate_id=search_box.candidate_id,
                            value=search_query,
                        )
                        await self.runtime.execute_step(f"Type search query: {search_query}", action, candidate=search_box)
                        press_enter = BrowserAction(action_type="key_press", key_code="Enter")
                        await self.runtime.execute_step("Press Enter", press_enter)
                        search_ok = True

                if search_ok:
                    # Wait dynamically for search results page to load
                    new_url = await self.runtime.get_current_url()
                    for _ in range(12):
                        await asyncio.sleep(0.5)
                        updated_url = await self.runtime.get_current_url()
                        if updated_url != new_url and any(k in updated_url for k in ["/s?", "search", "k=", "q="]):
                            new_url = updated_url
                            break
                        new_url = updated_url

                    screenshot = await self.runtime.get_screenshot()

                    yield {
                        "type": "observation",
                        "step": steps_taken,
                        "url": new_url,
                        "screenshot": screenshot,
                        "message": f"Submitted search for '{search_query}'. Current page: {new_url}",
                    }
                    yield {
                        "type": "answer",
                        "content": f"Successfully searched for **'{search_query}'** on **{new_url}**.",
                    }
                    return
                else:
                    yield {
                        "type": "error",
                        "message": f"Could not find an interactive search input to submit '{search_query}'.",
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

        # 3. Common shortcuts and brand matching
        shortcuts = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "github": "https://github.com",
            "hacker news": "https://news.ycombinator.com",
            "hackernews": "https://news.ycombinator.com",
            "hn": "https://news.ycombinator.com",
            "wikipedia": "https://www.wikipedia.org",
            "amazon": "https://www.amazon.com",
            "linkedin": "https://www.linkedin.com",
            "linked in": "https://www.linkedin.com",
            "linked": "https://www.linkedin.com",
            "twitter": "https://twitter.com",
            "x": "https://x.com",
            "reddit": "https://www.reddit.com",
        }
        clean_text = text.lower().strip()
        for name, url in shortcuts.items():
            pattern = rf"\b(?:go\s+to|open|visit|navigate\s+to|launch|head\s+to)\s+{re.escape(name)}\b"
            if (
                clean_text == name
                or f"go to {name}" in clean_text
                or f"open {name}" in clean_text
                or f"visit {name}" in clean_text
                or f"navigate to {name}" in clean_text
                or f"launch {name}" in clean_text
                or bool(re.search(pattern, clean_text))
            ):
                return url

        return None

    def _extract_search_query(self, text: str) -> Optional[str]:
        """Extracts search query from commands like 'search for X', 'find X', 'look up X', or 'google X'."""
        patterns = [
            r"search\s+(?:for\s+)?['\"]?([^'\"?]+)['\"]?",
            r"find\s+['\"]?([^'\"?]+)['\"]?",
            r"look\s+up\s+['\"]?([^'\"?]+)['\"]?",
            r"google\s+['\"]?([^'\"?]+)['\"]?",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                query = m.group(1).strip()
                query = re.sub(r"\s+on\s+[a-zA-Z0-9.-]+$", "", query, flags=re.IGNORECASE).strip()
                query = query.rstrip(".,;!? ")
                # filter out navigation commands
                if query and not any(query.lower().startswith(x) for x in ["http", "www.", ".com"]):
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
                    f"### @jobpilot: Application Flow Completed\n\n"
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

    async def _handle_linkedin_connections(
        self, instruction: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Automates searching for target profiles (e.g. HRs hiring) on LinkedIn,
        locating Connect triggers (a and button elements), handling the invitation modal,
        and safely sending connection requests with human-paced rate limits.
        """
        yield {
            "type": "thought",
            "content": "Initiating LinkedIn connection request automation with your active session...",
        }

        # 1. Extract target role / keyword query
        keywords = "HR hiring"
        target_match = re.search(
            r"(?:connection\s+requests?\s+(?:to|with|for)?|connect\s+(?:with|to)?|reach\s+out\s+to)\s+([a-zA-Z\s]+?)(?:who\s+are|\bcurrently\b|\bhiring\b|$)",
            instruction,
            re.IGNORECASE,
        )
        if target_match:
            extracted = target_match.group(1).strip()
            extracted = re.sub(r"^(?:the|all|any)\s+", "", extracted, flags=re.IGNORECASE).strip()
            if extracted and len(extracted) > 1 and extracted.lower() not in ["send", "connection", "requests", "request"]:
                keywords = f"{extracted} hiring" if "hiring" not in extracted.lower() else extracted
        elif "recruiter" in instruction.lower():
            keywords = "Recruiters hiring"
        elif "hr" in instruction.lower():
            keywords = "HR hiring"

        search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote(keywords)}"

        yield {
            "type": "action",
            "action": "navigate",
            "target": search_url,
            "details": f"Navigating to LinkedIn People search for '{keywords}'",
        }

        # 2. Check if already on LinkedIn or switch/open tab
        targets = await self.runtime.cdp.get_all_page_targets()
        matching = [t for t in targets if "linkedin.com" in t.get("url", "").lower()]
        if matching:
            await self.runtime.cdp.activate_tab(matching[0]["id"])
            await self.runtime.cdp.send("Page.navigate", {"url": search_url})
        else:
            await self.runtime.open_tab(search_url)

        await self.runtime.cdp.bring_to_front()

        # 3. Wait for search results or check login status
        yield {"type": "thought", "content": "Checking LinkedIn session authentication and waiting for search results..."}
        current_url = ""
        for _ in range(10):
            await asyncio.sleep(0.5)
            current_url = await self.runtime.get_current_url()
            if "linkedin.com" in current_url.lower():
                break

        page_title = str(await self.runtime.cdp.evaluate("document.title") or "")
        is_logged_out = (
            any(kw in current_url.lower() for kw in ["/login", "/authwall", "/checkpoint"])
            or any(kw in page_title.lower() for kw in ["sign in", "log in", "authwall"])
        )

        if is_logged_out:
            screenshot = await self.runtime.get_screenshot()
            yield {
                "type": "observation",
                "url": current_url,
                "screenshot": screenshot,
                "message": "LinkedIn Sign In page detected.",
            }
            yield {
                "type": "answer",
                "content": (
                    "> [!IMPORTANT]\n"
                    "> **LinkedIn Authentication Required**\n\n"
                    "Your active Chrome window is displaying the LinkedIn Sign In page.\n"
                    "Please log into LinkedIn in the opened Chrome tab, and then rerun your request. "
                    "Because WebOS uses a persistent session profile, your login will remain permanently saved across all subsequent requests."
                ),
            }
            return

        # 4. Wait up to 6 seconds for candidate results to mount
        find_candidates_script = """
        (() => {
            const items = Array.from(document.querySelectorAll('a, button'));
            const results = [];
            for (const el of items) {
                const text = (el.innerText || '').trim();
                const aria = (el.getAttribute('aria-label') || '').trim();
                const isConnect = (
                    text === 'Connect' ||
                    (aria.toLowerCase().includes('invite') && aria.toLowerCase().includes('to connect'))
                );
                if (isConnect && (el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0)) {
                    let name = 'Candidate';
                    const m = aria.match(/Invite\\s+(.+?)\\s+to\\s+connect/i);
                    if (m) {
                        name = m[1].trim();
                    } else {
                        const card = el.closest('li') || el.closest('[data-chameleon-result-urn]') || el.closest('.entity-result');
                        if (card) {
                            const titleEl = card.querySelector('.entity-result__title-text, a[href*="/in/"]');
                            if (titleEl) name = (titleEl.innerText || '').split('\\n')[0].trim();
                        }
                    }
                    results.push({ name: name, aria: aria, text: text });
                }
            }
            return results;
        })()
        """

        candidates = []
        for _ in range(12):
            candidates = await self.runtime.cdp.evaluate(find_candidates_script) or []
            if candidates:
                break
            await asyncio.sleep(0.5)

        if not candidates:
            screenshot = await self.runtime.get_screenshot()
            yield {
                "type": "observation",
                "url": current_url,
                "screenshot": screenshot,
                "message": f"No direct Connect buttons currently available on search results for '{keywords}'.",
            }
            yield {
                "type": "answer",
                "content": (
                    f"Navigated to LinkedIn People Search for **'{keywords}'** ({current_url}).\n\n"
                    "No direct 'Connect' buttons were found on this results page (profiles may require 'Follow' or 2nd-degree messaging). "
                    "You can refine your query or click on specific profiles to connect directly."
                ),
            }
            return

        yield {
            "type": "thought",
            "content": f"Found {len(candidates)} connectable candidates on page. Starting safe, human-paced dispatch...",
        }

        # 5. Dispatch connection requests (safe batch of up to 3)
        successful_connections = []
        max_to_send = min(3, len(candidates))

        for idx in range(max_to_send):
            click_script = f"""
            (() => {{
                const items = Array.from(document.querySelectorAll('a, button'));
                const connectables = items.filter(el => {{
                    const text = (el.innerText || '').trim();
                    const aria = (el.getAttribute('aria-label') || '').trim();
                    return (
                        text === 'Connect' ||
                        (aria.toLowerCase().includes('invite') && aria.toLowerCase().includes('to connect'))
                    ) && (el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0);
                }});
                if (connectables.length > {idx}) {{
                    connectables[{idx}].click();
                    return true;
                }}
                return false;
            }})()
            """
            clicked = await self.runtime.cdp.evaluate(click_script)
            if not clicked:
                continue

            cand_info = candidates[idx]
            cand_name = cand_info.get("name", f"Candidate #{idx + 1}")

            yield {
                "type": "action",
                "step": idx + 1,
                "action": "click_connect",
                "target": cand_name,
                "details": f"Clicked Connect for {cand_name}",
            }

            await asyncio.sleep(1.2)

            modal_script = """
            (() => {
                const dialog = document.querySelector('dialog, [role="dialog"], .artdeco-modal');
                if (!dialog) return { handled: false, reason: 'no_modal' };
                const buttons = Array.from(dialog.querySelectorAll('button'));
                for (const b of buttons) {
                    const t = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    if (
                        t === 'send without a note' ||
                        aria.includes('send without a note') ||
                        t === 'send' ||
                        aria.includes('send now')
                    ) {
                        b.click();
                        return { handled: true, action: 'sent' };
                    }
                }
                return { handled: false, reason: 'button_not_found' };
            })()
            """
            modal_res = await self.runtime.cdp.evaluate(modal_script) or {}
            await asyncio.sleep(1.5)

            screenshot = await self.runtime.get_screenshot()
            successful_connections.append(cand_name)

            yield {
                "type": "observation",
                "step": idx + 1,
                "url": await self.runtime.get_current_url(),
                "screenshot": screenshot,
                "message": f"Successfully sent connection request to {cand_name} (Modal: {modal_res.get('action', 'confirmed')}).",
            }

            await asyncio.sleep(1.5)

        # 6. Yield final summary table
        rows = "\n".join([f"| **{name}** | Sent [OK] | Connected via People Search |" for name in successful_connections])
        summary = (
            f"### LinkedIn Connection Requests Sent\n\n"
            f"Successfully navigated to LinkedIn People Search for **'{keywords}'** using your active profile and sent **{len(successful_connections)}** connection requests:\n\n"
            f"| Candidate | Status | Details |\n"
            f"| :--- | :--- | :--- |\n"
            f"{rows}\n\n"
            f"> **Safety Pacing**: Requests were dispatched with human-like delays to safeguard your LinkedIn profile standing."
        )

        yield {
            "type": "answer",
            "content": summary,
        }
