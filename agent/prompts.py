"""
agent/prompts.py
~~~~~~~~~~~~~~~~
All LLM prompts in one place.

Centralizing prompts makes them easy to audit, translate, version,
and swap without touching business logic.
"""


def plan_generation_prompt(
    goal: str, current_plan: str, logs_joined: str
) -> str:
    """Prompt sent to the Supervisor to generate or refine the mission plan."""
    return (
        "You are a strict DevOps Supervisor.\n"
        "Return ONLY a valid markdown plan in this exact structure:\n"
        "# MISSION PLAN\n"
        "GOAL: ...\nSTATE: PROCESSING\nUPDATED_AT: ...\n\n"
        "Then one or more sections:\n"
        "## STEP N\nTITLE: ...\nSTATUS: PENDING|IN_PROGRESS|DONE|RETRY\n"
        "ENGINE: AUTO|POWERSHELL|PYTHON\n"
        "SUCCESS_CRITERIA:\n- ...\nCOMMAND_HINT:\n- ...\nRETRIES: 0\n\n"
        "Then:\n## NOTES\n- ...\n\n"
        "Rules:\n"
        "- Keep already DONE steps as DONE.\n"
        "- Ensure there is at least one PENDING/RETRY step if mission not complete.\n"
        "- Keep plan human-readable and organized.\n"
        "- No code block fences.\n\n"
        f"GOAL:\n{goal}\n\n"
        f"CURRENT_PLAN:\n{current_plan}\n\n"
        f"LATEST_LOGS:\n{logs_joined}\n"
    )


def execution_planner_prompt(
    goal: str,
    step_id: int,
    step_title: str,
    step_status: str,
    success_criteria: str,
    command_hint: str,
    logs_joined: str,
) -> str:
    """Prompt sent to the Planner to build an executable command for a step."""
    return (
        "You are an execution planner.\n"
        "Return EXACT format (no markdown fences):\n"
        "ENGINE: POWERSHELL|PYTHON\n"
        "MODE: COMMAND|SCRIPT\n"
        "CONTENT_START\n"
        "... executable content ...\n"
        "CONTENT_END\n\n"
        "CRITICAL RULES FOR PYTHON ENGINE (GITHUB FILE MANIPULATION):\n"
        "You have a built-in library strictly injected with ONLY these exact 4 functions:\n"
        "  1. get_file_content(path)\n"
        "  2. put_file_content(path, content, message)\n"
        "  3. delete_file_content(path, message)\n"
        "  4. list_github_directory(path)\n"
        "DO NOT use any other external APIs. DO NOT hallucinate fake functions. "
        "Use ONLY these 4 functions to interact with the repository.\n\n"
        "Rules:\n"
        "- Choose POWERSHELL for OS/file shell tasks.\n"
        "- Choose PYTHON for multi-step logic/parsing or using the 4 Github built-in functions.\n"
        "- Content must be directly executable.\n\n"
        f"GOAL: {goal}\n"
        f"STEP_ID: {step_id}\n"
        f"STEP_TITLE: {step_title}\n"
        f"STEP_STATUS: {step_status}\n"
        f"SUCCESS_CRITERIA: {success_criteria}\n"
        f"COMMAND_HINT: {command_hint}\n"
        f"PREVIOUS_LOGS:\n{logs_joined}\n"
    )


def judge_prompt(
    goal: str,
    step_id: int,
    success_criteria: str,
    report_text: str,
) -> str:
    """Prompt sent to the Judge to evaluate step execution results."""
    return (
        "You are a strict validator.\n"
        "Return EXACT format:\n"
        "VERDICT: PASS|FAIL\n"
        "REASON: one short sentence\n"
        "UPDATE_HINT: one short sentence\n\n"
        f"GOAL: {goal}\n"
        f"STEP_ID: {step_id}\n"
        f"SUCCESS_CRITERIA: {success_criteria}\n"
        f"REPORT:\n{report_text[:5000]}\n"
    )
