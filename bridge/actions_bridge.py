#!/usr/bin/env python3
"""
bridge/actions_bridge.py
~~~~~~~~~~~~~~~~~~~~~~~~
Actions Bridge Script V3.0 - GitHub Actions Edition

يعمل هذا السكريبت مرة واحدة فقط داخل GitHub Actions (بدون polling).
يقرأ المهمة من inbox/local_task.json، ينفذها، ويرفع النتيجة إلى outbox/.

الفرق عن local_bridge.py:
- لا يوجد polling - يُشغَّل مباشرةً عبر workflow
- GITHUB_TOKEN يُقرأ من بيئة GitHub Actions تلقائياً
- لا حاجة لملف .env
- مُحسَّن لبيئة Linux (Ubuntu) في GitHub Actions
- POWERSHELL يُحوَّل تلقائياً إلى BASH

التدفق:
1. الوكيل يكتب المهمة في inbox/local_task.json
2. الـ push يُطلق workflow تلقائياً
3. هذا السكريبت يُنفَّذ مرة واحدة وينتهي
4. النتيجة ترفع إلى outbox/
5. الوكيل يقرأ النتيجة

المحركات المدعومة:
- PYTHON : تنفيذ كود Python
- BASH   : تنفيذ أوامر Bash
- POWERSHELL: يُحوَّل تلقائياً إلى BASH (Linux فقط)
- CMD   : غير مدعوم على Linux
- ANALYZER: استدعاء CodeAnalyzer إذا كان المسار متاحاً

الاستخدام:
python bridge/actions_bridge.py
"""

import os
import sys
import json
import time
import base64
import subprocess
import hashlib
import shutil
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("Missing library. Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration — كل القيم تأتي من environment variables أو GitHub Actions
# ---------------------------------------------------------------------------
REPO_OWNER      = os.getenv("REPO_OWNER", "bahoma31-eng")
REPO_NAME       = os.getenv("REPO_NAME", "Cloud-Controlled-Agent")
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")

TASK_FILE       = "inbox/local_task.json"
RESULT_DIR      = "outbox"
COMMAND_TIMEOUT = int(os.getenv("BRIDGE_TIMEOUT", "120"))
BRANCH_NAME     = os.getenv("BRIDGE_BRANCH", "main")

# CodeAnalyzer — اختياري، مدعوم إن وُجد مسار صالح
CODE_ANALYZER_PATH = os.getenv("CODE_ANALYZER_PATH", "")

GITHUB_API_BASE = "https://api.github.com"

# حدود طول المخرجات
CONSOLE_OUTPUT_LIMIT = 3000
RESULT_OUTPUT_LIMIT  = 5000

# قيم تعني "لا توجد مهمة معلّقة"
TASK_IDLE_STATES = {"waiting", "null", "", "{}"}

# ---------------------------------------------------------------------------
# Terminal UI
# ---------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).isoformat()

def _local_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _line(char="=", length=70):
    print(char * length)

def _header(title):
    print()
    _line()
    print("  " + title)
    _line("-")

def _footer():
    _line()
    print()

def _log(icon, msg):
    print("[" + _local_time() + "] " + icon + " " + msg)

# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------
def _headers():
    return {
        "Authorization": "token " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "Actions-Bridge-Agent-V3",
    }

def _content_url(path):
    return f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"

def gh_get_file(path):
    try:
        r = requests.get(_content_url(path), headers=_headers(), timeout=20)
        if r.status_code == 200:
            data = r.json()
            encoded = data.get("content", "")
            decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
            return decoded, data.get("sha")
        if r.status_code != 404:
            _log("!", f"GitHub GET {path} -> {r.status_code}: {r.text[:300]}")
    except Exception as e:
        _log("!", f"Error reading {path}: {e}")
    return None, None

def gh_put_file(path, content, message):
    try:
        url = _content_url(path)

        r_old = requests.get(url, headers=_headers(), timeout=20)
        sha = None
        if r_old.status_code == 200:
            sha = r_old.json().get("sha")
        elif r_old.status_code not in (200, 404):
            _log("!", f"GitHub preflight GET {path} -> {r_old.status_code}: {r_old.text[:300]}")

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": BRANCH_NAME,
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(url, headers=_headers(), json=payload, timeout=30)
        if r.status_code in (200, 201):
            return True

        _log("!", f"GitHub PUT {path} -> {r.status_code}: {r.text[:400]}")
        return False
    except Exception as e:
        _log("!", f"Error uploading {path}: {e}")
        return False

# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------
def _which_or_none(binary_name):
    return shutil.which(binary_name)

def _validate_timeout(raw_timeout, default_value):
    try:
        value = int(raw_timeout)
        if value <= 0:
            return default_value
        return value
    except Exception:
        return default_value

def _join_output(stdout_text, stderr_text):
    out = (stdout_text or "").strip()
    err = (stderr_text or "").strip()

    if out and err:
        return f"{out}\n\n[STDERR]\n{err}"
    if err and not out:
        return f"[STDERR]\n{err}"
    return out

def _run_process(cmd, timeout, cwd, use_shell=False):
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        shell=use_shell,
    )
    return p.returncode, (p.stdout or ""), (p.stderr or "")

def execute_command(engine, content, timeout):
    """
    يرجع:
    (return_code: int, output_text: str)
    """
    engine_upper = str(engine or "").strip().upper()
    timeout_value = _validate_timeout(timeout, COMMAND_TIMEOUT)
    cwd = os.getcwd()

    try:
        if engine_upper == "PYTHON":
            py = _which_or_none("python3") or _which_or_none("python")
            if not py:
                return 1, "Engine 'PYTHON' not found on this system (python3/python missing)."
            cmd = [py, "-c", content]
            rc, stdout, stderr = _run_process(cmd, timeout_value, cwd)

        elif engine_upper in ("BASH", "SH"):
            bash = _which_or_none("bash") or _which_or_none("sh")
            if not bash:
                return 1, "Engine 'BASH' not found on this system."
            cmd = [bash, "-c", content]
            rc, stdout, stderr = _run_process(cmd, timeout_value, cwd)

        elif engine_upper == "POWERSHELL":
            # على Linux: حاول pwsh أولاً، وإلا حوّل إلى bash
            ps = _which_or_none("pwsh")
            if ps:
                cmd = [ps, "-NonInteractive", "-NoProfile", "-Command", content]
                rc, stdout, stderr = _run_process(cmd, timeout_value, cwd)
            else:
                _log(">>", "POWERSHELL not available; redirecting to BASH automatically.")
                bash = _which_or_none("bash") or _which_or_none("sh")
                if not bash:
                    return 1, "Neither pwsh nor bash found on this system."
                cmd = [bash, "-c", content]
                rc, stdout, stderr = _run_process(cmd, timeout_value, cwd)

        elif engine_upper == "CMD":
            return 1, (
                "Engine 'CMD' is not supported in GitHub Actions (Linux environment). "
                "Use BASH or PYTHON instead."
            )

        elif engine_upper == "ANALYZER":
            if not CODE_ANALYZER_PATH or not os.path.isdir(CODE_ANALYZER_PATH):
                return 1, (
                    f"CodeAnalyzer directory not found: '{CODE_ANALYZER_PATH}'. "
                    "Set the CODE_ANALYZER_PATH environment variable / secret."
                )

            analyzer_script = os.path.join(CODE_ANALYZER_PATH, "code_analyzer.py")
            if not os.path.isfile(analyzer_script):
                return 1, f"CodeAnalyzer script not found: {analyzer_script}"

            target_path = content.strip()
            if not target_path:
                return 1, "ANALYZER engine requires target path in 'command' field."

            if not os.path.exists(target_path):
                return 1, f"Target path does not exist: {target_path}"

            py = _which_or_none("python3") or _which_or_none("python")
            if not py:
                return 1, "Engine 'PYTHON' not found on this system (required for ANALYZER)."

            _log(">>", f"CodeAnalyzer: analyzing {target_path}")

            analyze_code = (
                "import sys, json\n"
                "sys.path.insert(0, " + repr(CODE_ANALYZER_PATH) + ")\n"
                "from code_analyzer import CodeAnalyzer\n"
                "ca = CodeAnalyzer(" + repr(target_path) + ")\n"
                "ca.scan()\n"
                "findings = ca.get_findings_json()\n"
                "print(json.dumps(findings, ensure_ascii=False, indent=2))\n"
            )
            cmd = [py, "-c", analyze_code]
            rc, stdout, stderr = _run_process(cmd, timeout_value, CODE_ANALYZER_PATH)

            _log("<<", f"CodeAnalyzer finished (exit code: {rc})")

        else:
            return 1, f"Unsupported engine: {engine}"

        output = _join_output(stdout, stderr)
        if not output.strip():
            output = "(no output)"
        return rc, output

    except subprocess.TimeoutExpired:
        return 124, f"Timeout expired after {timeout_value}s"
    except FileNotFoundError:
        return 1, f"Engine '{engine}' not found on this system"
    except Exception as e:
        return 1, f"Execution error: {e}"

# ---------------------------------------------------------------------------
# Main — single-run (no polling loop)
# ---------------------------------------------------------------------------
def main():
    if not GITHUB_TOKEN:
        print(
            "GITHUB_TOKEN is missing!\n"
            "In GitHub Actions it is injected automatically via secrets.GITHUB_TOKEN.\n"
            "Make sure the workflow file sets: env: GITHUB_TOKEN\n"
            "See docs/actions_bridge_setup.md for details."
        )
        sys.exit(1)

    _header("Actions Bridge Agent V3.0 - GitHub Actions Edition")
    print(f"  Repo      : {REPO_OWNER}/{REPO_NAME}")
    print(f"  Task file : {TASK_FILE}")
    print(f"  Timeout   : {COMMAND_TIMEOUT}s")
    print(f"  Branch    : {BRANCH_NAME}")
    print()
    print("  >> Single-run mode (no polling).")
    print("  >> Triggered by workflow event (push / workflow_dispatch).")
    print("  >> Engines: PYTHON | BASH | POWERSHELL (→BASH) | ANALYZER")
    _footer()

    raw, _ = gh_get_file(TASK_FILE)

    if not raw or raw.strip().lower() in TASK_IDLE_STATES:
        _log("..", "No pending task found in inbox. Exiting.")
        sys.exit(0)

    try:
        task = json.loads(raw)
    except json.JSONDecodeError:
        _log("!!", "Task file is not valid JSON. Exiting.")
        sys.exit(1)

    task_id     = str(task.get("task_id", "?"))
    engine      = task.get("engine", "PYTHON")
    command     = task.get("command", "")
    description = task.get("description", "No description")
    timeout     = _validate_timeout(task.get("timeout", COMMAND_TIMEOUT), COMMAND_TIMEOUT)

    _header(f"Task [{task_id}] received")
    print(f"  Description : {description}")
    print(f"  Engine      : {engine}")
    print(f"  Timeout     : {timeout}s")
    _line("-")
    print("  Command:")
    for line in str(command).splitlines() or [""]:
        print("    " + line)
    _line("-")

    _log(">>", "Executing...")
    rc, output = execute_command(engine, command, timeout)

    status_word = "SUCCESS" if rc == 0 else "FAILED"
    _log("<<", f"Result: {status_word} (exit code: {rc})")
    _line("-")
    print("Output:")
    print((output or "")[:CONSOLE_OUTPUT_LIMIT])
    _footer()

    result = {
        "task_id"        : task_id,
        "status"         : status_word,
        "return_code"    : rc,
        "engine"         : engine,
        "description"    : description,
        "command_preview": str(command)[:800],
        "output"         : (output or "")[:RESULT_OUTPUT_LIMIT],
        "timestamp"      : _now(),
        "executed_on"    : "github_actions",
        "repo"           : f"{REPO_OWNER}/{REPO_NAME}",
        "bridge_version" : "3.0",
    }

    result_name = f"{RESULT_DIR}/bridge_result_{int(time.time())}.json"
    uploaded = gh_put_file(
        result_name,
        json.dumps(result, ensure_ascii=False, indent=2),
        f"Bridge: executed task {task_id}",
    )

    if uploaded:
        _log("OK", f"Result uploaded -> {result_name}")
    else:
        _log("!!", "Failed to upload result")

    # مسح ملف المهمة بعد المعالجة
    cleared = gh_put_file(TASK_FILE, "waiting", "Bridge: task processed")
    if not cleared:
        _log("!!", f"Failed to clear {TASK_FILE}")

    _log("..", "Done.")
    # كود الخروج: 0 = نجاح، 1 = فشل (GitHub Actions لا يتعامل جيداً مع أكواد > 125)
    sys.exit(0 if rc == 0 else 1)

if __name__ == "__main__":
    main()
