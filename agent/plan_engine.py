"""
agent/plan_engine.py
~~~~~~~~~~~~~~~~~~~~
Plan parsing, rendering, default generation, and task-payload helpers.

The plan is a structured Markdown document stored at ``inbox/plan.md``.
This module owns the schema — every other module treats the plan as an
opaque ``Dict`` produced by ``parse_plan()``.
"""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def now_iso() -> str:
    """UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------
# Regex patterns
# ------------------------------------------------------------------
_STEP_HEADER = re.compile(r"^##\s+STEP\s+(\d+)\s*$", re.IGNORECASE)
_FIELD = re.compile(r"^([A-Z_]+):\s*(.*)$")


# ------------------------------------------------------------------
# Default plan generator
# ------------------------------------------------------------------

def default_plan(goal: str) -> str:
    """Return a clean-slate plan Markdown string for a brand-new mission."""
    return (
        "# MISSION PLAN\n"
        f"GOAL: {goal.strip()}\n"
        "STATE: PROCESSING\n"
        f"UPDATED_AT: {now_iso()}\n\n"
        "## STEP 1\n"
        "TITLE: Analyze goal and propose first executable action\n"
        "STATUS: PENDING\n"
        "ENGINE: AUTO\n"
        "SUCCESS_CRITERIA:\n"
        "- First concrete executable action is produced.\n"
        "COMMAND_HINT:\n"
        "- Generate command/script for first action.\n\n"
        "## NOTES\n"
        "- Plan generated automatically.\n"
    )


# ------------------------------------------------------------------
# Parser
# ------------------------------------------------------------------

def parse_plan(plan_md: str) -> Dict:
    """Parse a plan Markdown string into a structured dict.

    Returns::

        {
            "meta":  {"GOAL": str, "STATE": str, "UPDATED_AT": str},
            "steps": [{
                "id": int, "TITLE": str, "STATUS": str, "ENGINE": str,
                "SUCCESS_CRITERIA": [str], "COMMAND_HINT": [str], "RETRIES": int
            }, ...],
            "notes": [str, ...]
        }
    """
    lines = plan_md.splitlines()
    meta: Dict = {"GOAL": "", "STATE": "PROCESSING", "UPDATED_AT": ""}
    steps: List[Dict] = []
    notes: List[str] = []
    cur: Optional[Dict] = None
    section = "meta"
    current_list_key: Optional[str] = None

    def _flush():
        nonlocal cur
        if cur:
            cur.setdefault("SUCCESS_CRITERIA", [])
            cur.setdefault("COMMAND_HINT", [])
            cur.setdefault("RETRIES", 0)
            steps.append(cur)
            cur = None

    for line in lines:
        stripped = line.strip()

        # Skip top-level heading
        if stripped.startswith("# MISSION PLAN"):
            continue

        # Step header
        m = _STEP_HEADER.match(stripped)
        if m:
            _flush()
            section = "step"
            cur = {
                "id": int(m.group(1)),
                "TITLE": "",
                "STATUS": "PENDING",
                "ENGINE": "AUTO",
                "SUCCESS_CRITERIA": [],
                "COMMAND_HINT": [],
                "RETRIES": 0,
            }
            current_list_key = None
            continue

        # Notes section
        if stripped.startswith("## NOTES"):
            _flush()
            section = "notes"
            current_list_key = None
            continue

        # Key: Value fields
        fm = _FIELD.match(stripped)
        if fm:
            key, val = fm.group(1), fm.group(2)
            if section == "meta" and key in meta:
                meta[key] = val
            elif section == "step" and cur is not None:
                if key in ("TITLE", "STATUS", "ENGINE"):
                    cur[key] = val.strip()
                    current_list_key = None
                elif key in ("SUCCESS_CRITERIA", "COMMAND_HINT"):
                    current_list_key = key
                    if val.strip():
                        cur[key].append(val.strip())
                elif key == "RETRIES":
                    try:
                        cur["RETRIES"] = int(val.strip())
                    except ValueError:
                        cur["RETRIES"] = 0
                else:
                    current_list_key = None
            continue

        # Bullet items
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if (
                section == "step"
                and cur is not None
                and current_list_key in ("SUCCESS_CRITERIA", "COMMAND_HINT")
            ):
                cur[current_list_key].append(item)
            elif section == "notes":
                notes.append(item)

    _flush()
    return {"meta": meta, "steps": steps, "notes": notes}


# ------------------------------------------------------------------
# Renderer
# ------------------------------------------------------------------

def render_plan(plan: Dict) -> str:
    """Convert a parsed plan dict back to Markdown."""
    meta = plan["meta"]
    steps = sorted(plan["steps"], key=lambda s: s["id"])
    notes = plan.get("notes", [])

    out: List[str] = [
        "# MISSION PLAN",
        f"GOAL: {meta.get('GOAL', '')}",
        f"STATE: {meta.get('STATE', 'PROCESSING')}",
        f"UPDATED_AT: {now_iso()}",
        "",
    ]

    for s in steps:
        out.append(f"## STEP {s['id']}")
        out.append(f"TITLE: {s.get('TITLE', '')}")
        out.append(f"STATUS: {s.get('STATUS', 'PENDING')}")
        out.append(f"ENGINE: {s.get('ENGINE', 'AUTO')}")
        out.append("SUCCESS_CRITERIA:")
        for c in s.get("SUCCESS_CRITERIA", []):
            out.append(f"- {c}")
        if not s.get("SUCCESS_CRITERIA"):
            out.append("-")
        out.append("COMMAND_HINT:")
        for h in s.get("COMMAND_HINT", []):
            out.append(f"- {h}")
        if not s.get("COMMAND_HINT"):
            out.append("-")
        out.append(f"RETRIES: {s.get('RETRIES', 0)}")
        out.append("")

    out.append("## NOTES")
    for n in notes:
        out.append(f"- {n}")
    if not notes:
        out.append("-")
    out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------
# Step helpers
# ------------------------------------------------------------------

def find_next_step(steps: List[Dict]) -> Optional[Dict]:
    """Return the first step whose STATUS is actionable."""
    for s in sorted(steps, key=lambda x: x["id"]):
        if s.get("STATUS", "").upper() in ("PENDING", "RETRY", "IN_PROGRESS"):
            return s
    return None


# ------------------------------------------------------------------
# Task payload serialization
# ------------------------------------------------------------------

def build_task_payload(
    step_id: int, engine: str, mode: str, content: str
) -> str:
    """Serialize a task into the text format the Worker reads."""
    return (
        f"TASK_ID: {step_id}\n"
        f"ENGINE: {engine}\n"
        f"MODE: {mode}\n"
        "CONTENT_START\n"
        f"{content.rstrip()}\n"
        "CONTENT_END\n"
    )


def parse_task_payload(text: str) -> Optional[Dict]:
    """Deserialize a task payload. Returns None if format is invalid."""
    if not text:
        return None
    m_id = re.search(r"^TASK_ID:\s*(\d+)\s*$", text, re.MULTILINE)
    m_engine = re.search(r"^ENGINE:\s*(\w+)\s*$", text, re.MULTILINE)
    m_mode = re.search(r"^MODE:\s*(\w+)\s*$", text, re.MULTILINE)
    m_content = re.search(r"CONTENT_START\s*(.*?)\s*CONTENT_END", text, re.DOTALL)
    if not (m_id and m_engine and m_mode and m_content):
        return None
    return {
        "task_id": int(m_id.group(1)),
        "engine": m_engine.group(1).upper(),
        "mode": m_mode.group(1).upper(),
        "content": m_content.group(1).strip(),
    }
