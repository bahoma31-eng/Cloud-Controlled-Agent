"""
agent/worker.py
~~~~~~~~~~~~~~~
Task execution engine.

The Worker receives a serialized task payload, executes it via
PowerShell or Python subprocess, and returns a structured report.
"""

import os
import tempfile
import subprocess
import logging
from typing import Optional, Tuple, Dict

from agent.config import COMMAND_TIMEOUT
from agent.plan_engine import now_iso, parse_task_payload
from agent.github_api import build_remote_libs
from agent import ui

logger = logging.getLogger("cloud-agent.worker")


# ------------------------------------------------------------------
# Engine runners
# ------------------------------------------------------------------

def _run_powershell(command: str, timeout: int) -> Tuple[int, str]:
    """Execute a PowerShell command and return (returncode, output)."""
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        stdout = (p.stdout or b"").decode("utf-8", errors="replace")
        stderr = (p.stderr or b"").decode("utf-8", errors="replace")
        return p.returncode, (stdout + ("\n" + stderr if stderr else "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "TimeoutExpired"
    except Exception as e:
        return 1, f"Execution error: {e}"


def _run_python(code: str, timeout: int) -> Tuple[int, str]:
    """Execute a Python script (with injected remote libs) and return (returncode, output)."""
    fd, path = tempfile.mkstemp(prefix="agent_step_", suffix=".py", text=True)
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_remote_libs() + "\n\n" + code)
        p = subprocess.run(
            ["python", path],
            capture_output=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        stdout = (p.stdout or b"").decode("utf-8", errors="replace")
        stderr = (p.stderr or b"").decode("utf-8", errors="replace")
        return p.returncode, (stdout + ("\n" + stderr if stderr else "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "TimeoutExpired"
    except Exception as e:
        return 1, f"Python execution error: {e}"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def execute(tasks_raw: str) -> Optional[str]:
    """Parse *tasks_raw*, run the appropriate engine, and return a report string.

    Returns ``None`` if the payload is unparseable.
    """
    task = parse_task_payload(tasks_raw)
    if not task:
        return None

    engine = task["engine"]
    content = task["content"]

    if engine == "POWERSHELL":
        rc, out = _run_powershell(content, COMMAND_TIMEOUT)
    elif engine == "PYTHON":
        rc, out = _run_python(content, COMMAND_TIMEOUT)
    else:
        rc, out = 1, f"Unsupported engine: {engine}"

    report = (
        f"--- EXECUTION REPORT ---\n"
        f"TIME: {now_iso()}\n"
        f"TASK_ID: {task['task_id']}\n"
        f"ENGINE: {engine}\n"
        f"MODE: {task['mode']}\n"
        f"RETURN_CODE: {rc}\n"
        f"CONTENT_PREVIEW:\n{content[:1200]}\n"
        f"OUTPUT:\n{out}\n"
        f"--- END REPORT ---\n"
    )

    ui.print_worker_report(task["task_id"], report)
    return report
