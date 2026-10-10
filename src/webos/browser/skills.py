"""
Self-Healing Skill Engine and Replayable Action Graphs.
"""

import json
import uuid
import datetime
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple
from webos.browser.cdp_client import CDPClient
from webos.storage.db import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class SkillStep:
    step_name: str
    primary_selector: str
    aria_role: Optional[str] = None
    accessible_name: Optional[str] = None
    text_match: Optional[str] = None
    action_type: str = "click"
    value: Optional[str] = None


@dataclass
class SiteSkill:
    skill_id: str
    domain: str
    task_name: str
    steps: List[SkillStep]
    success_rate: float = 1.0
    last_verified: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class SkillManager:
    """Manages recording, replay, and self-healing anchor resolution for browser skills."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    def save_skill(
        self, domain: str, task_name: str, steps: List[SkillStep]
    ) -> str:
        """Stores a new or updated skill graph in SQLite."""
        skill_id = f"{domain.lower()}:{task_name.lower()}"
        steps_data = [asdict(s) for s in steps]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        conn = self.db_manager.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO site_skills 
                (skill_id, domain, task_name, action_graph_json, success_rate, last_verified)
                VALUES (?, ?, ?, ?, 1.0, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    action_graph_json = excluded.action_graph_json,
                    last_verified = excluded.last_verified
                """,
                (skill_id, domain.lower(), task_name.lower(), json.dumps(steps_data), now),
            )
        return skill_id

    def load_skill(self, domain: str, task_name: str) -> Optional[SiteSkill]:
        """Retrieves a stored skill by domain and task name."""
        skill_id = f"{domain.lower()}:{task_name.lower()}"
        conn = self.db_manager.get_connection()
        row = conn.execute(
            """
            SELECT skill_id, domain, task_name, action_graph_json, success_rate, last_verified
            FROM site_skills
            WHERE skill_id = ?
            """,
            (skill_id,),
        ).fetchone()

        if not row:
            return None

        steps_data = json.loads(row["action_graph_json"])
        steps = [SkillStep(**s) for s in steps_data]

        return SiteSkill(
            skill_id=row["skill_id"],
            domain=row["domain"],
            task_name=row["task_name"],
            steps=steps,
            success_rate=row["success_rate"],
            last_verified=row["last_verified"],
        )

    async def resolve_step_element(
        self, cdp: CDPClient, step: SkillStep
    ) -> Tuple[Optional[str], bool]:
        """
        Attempts to locate the element using multi-tier anchors:
        1. Primary selector (0 tokens, fastest)
        2. Accessible role + Name fallback
        3. Text match fallback
        
        Returns: (working_selector, is_self_healed)
        """
        # Tier 1: Test primary selector
        check_primary = f"""
        (() => {{
            const el = document.querySelector({json.dumps(step.primary_selector)});
            return el !== null;
        }})()
        """
        if await cdp.evaluate(check_primary):
            return (step.primary_selector, False)

        logger.info(
            "Primary selector '%s' failed for step '%s'. Attempting secondary anchors...",
            step.primary_selector,
            step.step_name,
        )

        # Tier 2: Accessible Role + Name Fallback
        if step.aria_role and step.accessible_name:
            role_script = f"""
            (() => {{
                const targetRole = {json.dumps(step.aria_role.lower())};
                const targetName = {json.dumps(step.accessible_name.lower())};
                const elements = Array.from(document.querySelectorAll(`[role="${{targetRole}}"], button, a, input`));
                for (let el of elements) {{
                    const label = (el.getAttribute('aria-label') || el.innerText || el.value || '').toLowerCase().trim();
                    if (label.includes(targetName)) {{
                        // Generate a robust unique path selector
                        if (el.id) return `#${{el.id}}`;
                        if (el.name) return `${{el.tagName.toLowerCase()}}[name="${{el.name}}"]`;
                        return `${{el.tagName.toLowerCase()}}[aria-label="${{el.getAttribute('aria-label')}}"]`;
                    }}
                }}
                return null;
            }})()
            """
            healed_selector = await cdp.evaluate(role_script)
            if healed_selector:
                logger.info("Self-healing triggered! Found via ARIA anchor: '%s'", healed_selector)
                return (healed_selector, True)

        # Tier 3: Pure text match fallback
        if step.text_match:
            text_script = f"""
            (() => {{
                const targetText = {json.dumps(step.text_match.lower())};
                const elements = Array.from(document.querySelectorAll('button, a, span, label'));
                for (let el of elements) {{
                    if (el.innerText && el.innerText.toLowerCase().trim().includes(targetText)) {{
                        if (el.id) return `#${{el.id}}`;
                        return `${{el.tagName.toLowerCase()}}:contains("${{el.innerText.trim()}}")`;
                    }}
                }}
                return null;
            }})()
            """
            healed_text_selector = await cdp.evaluate(text_script)
            if healed_text_selector:
                logger.info("Self-healing triggered! Found via text match: '%s'", healed_text_selector)
                return (healed_text_selector, True)

        return (None, False)

    def heal_step(
        self, skill: SiteSkill, step_index: int, new_selector: str
    ) -> None:
        """Updates the primary selector with the self-healed selector in storage."""
        if 0 <= step_index < len(skill.steps):
            skill.steps[step_index].primary_selector = new_selector
            self.save_skill(skill.domain, skill.task_name, skill.steps)
            logger.info("Persisted healed selector into skill '%s'", skill.skill_id)
