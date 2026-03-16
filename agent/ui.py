"""
agent/ui.py
~~~~~~~~~~~
Terminal UI helpers for pretty-printing reports, plans, and task dispatches.

Keeping all print formatting in one module makes the rest of the codebase
cleaner and allows easy replacement with a TUI library later.
"""

from agent.config import AI_PROVIDER, MODEL_ID, GITHUB_MODEL, REPO_OWNER, REPO_NAME, VERBOSE

# ------------------------------------------------------------------
# ANSI colour codes
# ------------------------------------------------------------------
_RESET = "\033[0m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_BLUE = "\033[94m"
_MAGENTA = "\033[95m"


def box(title: str, content: str, color: str = _CYAN) -> None:
    """Print *content* inside a coloured terminal box."""
    border = color + "=" * 80 + _RESET
    print(f"\n{border}")
    print(f"{color} \U0001f5a8\ufe0f  {title.upper()}{_RESET}")
    print(f"{color}" + "-" * 80 + _RESET)
    print(content.strip())
    print(f"{border}\n")


def step_progress(
    step_id: int, title: str, status: str,
    verdict: str = None, reason: str = None,
) -> None:
    """Print a step progress update with colour-coded verdict."""
    color = _BLUE
    if verdict == "PASS":
        color = _GREEN
    elif verdict == "FAIL":
        color = _RED
    msg = f"STEP {step_id}: {title}\nStatus: {status}\n"
    if verdict:
        msg += f"Verdict: {verdict}\nReason: {reason}"
    box(f"Step {step_id} Progress Update", msg, color)


def print_startup() -> None:
    """Print the startup banner."""
    model = MODEL_ID if AI_PROVIDER == "GROQ" else GITHUB_MODEL
    print("\n" + "*" * 80)
    print("*** \U0001f7e2 Cloud Controlled Agent V13 (Modular) RUNNING ***")
    print("*" * 80)
    print(f"\U0001f527 REPO     : {REPO_OWNER}/{REPO_NAME}")
    print(f"\U0001f527 PROVIDER : {AI_PROVIDER}")
    print(f"\U0001f527 MODEL    : {model}")
    print(f"\U0001f527 VERBOSE  : {'ENABLED' if VERBOSE else 'DISABLED'}")
    print("*" * 80 + "\n")


def print_init_complete() -> None:
    print("\u2705 [INIT] Initialization complete. Agent ready.")


def print_loop_iteration(counter: int, timestamp: str) -> None:
    print(f"\n\U0001f504 [MAIN LOOP] Iteration #{counter} started at {timestamp}")


def print_new_mission(goal: str) -> None:
    box("New Mission Initialized", f"Goal: {goal}\nPlan & Memory wiped clean.", _MAGENTA)


def print_mission_done() -> None:
    print("\U0001f389 [SUPERVISOR] Mission appears DONE.")


def print_worker_executing() -> None:
    print("\U0001f6e0\ufe0f  [WORKER] Executing task...")


def print_plan_status(plan_text: str) -> None:
    box("Current Plan Status", plan_text, _CYAN)


def print_dispatched_task(step_id: int, payload: str) -> None:
    box(f"Dispatching Task (Step {step_id})", payload, _GREEN)


def print_worker_report(step_id: int, report: str) -> None:
    box(f"Worker Report (Step {step_id})", report, _YELLOW)
