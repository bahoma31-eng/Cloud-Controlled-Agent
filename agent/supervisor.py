"""
agent/supervisor.py
~~~~~~~~~~~~~~~~~~~
The Supervisor orchestrates the entire mission lifecycle:

1. Detect new missions and reset state.
2. Evaluate incoming execution reports (Judge).
3. Refine the plan via LLM.
4. Dispatch the next task to the Worker.

This module contains the high-level LLM-backed helpers that were
previously mixed into the monolithic V12 script.
"""

import re
import logging
from typing import List, Dict, Tuple, Optional

from agent.llm_client import LLMClient
from agent.prompts import (
    plan_generation_prompt,
    execution_planner_prompt,
    judge_prompt,
)

logger = logging.getLogger("cloud-agent.supervisor")


class Supervisor:
    """LLM-powered mission supervisor."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    # ------------------------------------------------------------------
    # Plan generation / refinement
    # ------------------------------------------------------------------
    def generate_or_refine_plan(
        self,
        goal: str,
        current_plan: str,
        reports: List[Tuple[str, str]],
    ) -> str:
        """Ask the LLM to produce or update a mission plan."""
        logs_joined = (
            "\n\n".join(
                [f"[{name}]\n{txt[:2000]}" for name, txt in reports[-4:]]
            )
            or "No logs."
        )
        prompt = plan_generation_prompt(goal, current_plan, logs_joined)
        return self._llm.call(
            [{"role": "user", "content": prompt}], temperature=0.3
        )

    # ------------------------------------------------------------------
    # Execution planning for a single step
    # ------------------------------------------------------------------
    def build_execution(
        self,
        goal: str,
        step: Dict,
        reports: List[Tuple[str, str]],
    ) -> Dict:
        """Return {ENGINE, MODE, CONTENT} for the given step."""
        logs_joined = (
            "\n\n".join(
                [f"[{name}]\n{txt[:1600]}" for name, txt in reports[-3:]]
            )
            or "No logs."
        )
        prompt = execution_planner_prompt(
            goal=goal,
            step_id=step.get("id"),
            step_title=step.get("TITLE"),
            step_status=step.get("STATUS"),
            success_criteria=str(step.get("SUCCESS_CRITERIA")),
            command_hint=str(step.get("COMMAND_HINT")),
            logs_joined=logs_joined,
        )
        result = self._llm.call(
            [{"role": "user", "content": prompt}], temperature=0.0
        )

        # Parse structured response
        out: Dict = {}
        for line in result.splitlines():
            if line.startswith("ENGINE:"):
                out["ENGINE"] = line.split(":", 1)[1].strip()
            if line.startswith("MODE:"):
                out["MODE"] = line.split(":", 1)[1].strip()
        content_match = re.search(
            r"CONTENT_START\s*(.*?)\s*CONTENT_END", result, re.DOTALL
        )
        out["CONTENT"] = content_match.group(1).strip() if content_match else ""

        # Fallback for malformed responses
        if not ("ENGINE" in out and "MODE" in out and out.get("CONTENT")):
            logger.warning("Planner returned malformed output — using fallback.")
            return {
                "ENGINE": "POWERSHELL",
                "MODE": "COMMAND",
                "CONTENT": 'Write-Output "Planner output malformed"',
            }
        return {
            "ENGINE": out["ENGINE"].upper(),
            "MODE": out["MODE"].upper(),
            "CONTENT": out["CONTENT"],
        }

    # ------------------------------------------------------------------
    # Step result judgement
    # ------------------------------------------------------------------
    def judge_step(
        self,
        goal: str,
        step: Dict,
        report_text: str,
    ) -> Dict:
        """Return {verdict, reason, hint} after evaluating a report."""
        prompt = judge_prompt(
            goal=goal,
            step_id=step.get("id"),
            success_criteria=str(step.get("SUCCESS_CRITERIA")),
            report_text=report_text,
        )
        raw = self._llm.call(
            [{"role": "user", "content": prompt}], temperature=0.0
        )

        verdict = re.search(r"^VERDICT:\s*(PASS|FAIL)$", raw, re.MULTILINE)
        reason = re.search(r"^REASON:\s*(.*)$", raw, re.MULTILINE)
        hint = re.search(r"^UPDATE_HINT:\s*(.*)$", raw, re.MULTILINE)

        return {
            "verdict": verdict.group(1) if verdict else "FAIL",
            "reason": reason.group(1).strip() if reason else "No reason.",
            "hint": hint.group(1).strip() if hint else "Retry.",
        }
