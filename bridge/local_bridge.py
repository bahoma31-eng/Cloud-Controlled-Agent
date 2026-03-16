#!/usr/bin/env python3
"""
bridge/local_bridge.py
~~~~~~~~~~~~~~~~~~~~~~
Local Bridge Script V2 - Auto-Execute Mode

يربط جهازك المحلي بالوكيل السحابي عبر GitHub.
الموافقة تتم من Notion، والسكريبت ينفذ تلقائيا بدون تدخل محلي.

التدفق:
    1. الوكيل يصف المهمة في Notion
    2. المستخدم يوافق في Notion
    3. الوكيل يكتب المهمة في inbox/local_task.json
    4. هذا السكريبت يكتشفها وينفذها تلقائيا
    5. النتيجة ترفع الى outbox/
    6. الوكيل يقرأ النتيجة

الاستخدام:
    python bridge/local_bridge.py
"""

import os
import sys
import json
import time
import base64
import subprocess
import hashlib
from datetime import datetime, timezone

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("Missing libraries. Run: pip install requests python-dotenv")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

REPO_OWNER = os.getenv("REPO_OWNER", "bahoma31-eng")
REPO_NAME = os.getenv("REPO_NAME", "Cloud-Controlled-Agent")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

TASK_FILE = "inbox/local_task.json"
RESULT_DIR = "outbox"
POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_SECONDS", "10"))
COMMAND_TIMEOUT = int(os.getenv("BRIDGE_TIMEOUT", "120"))

GITHUB_API_BASE = "https://api.github.com"

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
        "User-Agent": "Local-Bridge-Agent-V2",
    }

def _content_url(path):
    return GITHUB_API_BASE + "/repos/" + REPO_OWNER + "/" + REPO_NAME + "/contents/" + path

def gh_get_file(path):
    try:
        r = requests.get(_content_url(path), headers=_headers(), timeout=20)
        if r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return content, data.get("sha")
        elif r.status_code != 404:
            _log("!", "GitHub GET " + path + " -> " + str(r.status_code))
    except Exception as e:
        _log("!", "Error reading " + path + ": " + str(e))
    return None, None

def gh_put_file(path, content, message):
    try:
        url = _content_url(path)
        r_old = requests.get(url, headers=_headers(), timeout=20)
        sha = r_old.json().get("sha") if r_old.status_code == 200 else None
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha
        r = requests.put(url, headers=_headers(), json=payload, timeout=30)
        return r.status_code in (200, 201)
    except Exception as e:
        _log("!", "Error uploading " + path + ": " + str(e))
        return False


# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------
def execute_command(engine, content, timeout):
    try:
        engine_upper = engine.upper()
        if engine_upper == "PYTHON":
            cmd = ["python", "-c", content]
        elif engine_upper == "POWERSHELL":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", content]
        elif engine_upper == "BASH":
            cmd = ["bash", "-c", content]
        elif engine_upper == "CMD":
            cmd = ["cmd", "/c", content]
        else:
            return 1, "Unsupported engine: " + engine

        p = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        stdout = (p.stdout or b"").decode("utf-8", errors="replace")
        stderr = (p.stderr or b"").decode("utf-8", errors="replace")
        output = stdout
        if stderr:
            output = output + "\n[STDERR]\n" + stderr
        return p.returncode, output.strip()

    except subprocess.TimeoutExpired:
        return 124, "Timeout expired after " + str(timeout) + "s"
    except FileNotFoundError:
        return 1, "Engine '" + engine + "' not found on this system"
    except Exception as e:
        return 1, "Execution error: " + str(e)


# ---------------------------------------------------------------------------
# Main loop - AUTO EXECUTE (no local confirmation needed)
# ---------------------------------------------------------------------------
def main():
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN is missing! Add it to .env file")
        sys.exit(1)

    _header("Local Bridge Agent V2.0 - Auto Execute Mode")
    print("  Repo      : " + REPO_OWNER + "/" + REPO_NAME)
    print("  Task file : " + TASK_FILE)
    print("  Polling   : every " + str(POLL_INTERVAL) + "s")
    print("  Timeout   : " + str(COMMAND_TIMEOUT) + "s")
    print()
    print("  >> Auto-execute enabled.")
    print("  >> Approval happens in Notion, not here.")
    print("  >> Press Ctrl+C to stop.")
    _footer()

    last_task_hash = None
    task_count = 0

    while True:
        try:
            raw, _ = gh_get_file(TASK_FILE)

            if not raw or raw.strip().lower() in ("waiting", "null", "", "{}"):
                time.sleep(POLL_INTERVAL)
                continue

            # Parse task
            try:
                task = json.loads(raw)
            except json.JSONDecodeError:
                time.sleep(POLL_INTERVAL)
                continue

            # Skip if already processed
            task_hash = hashlib.md5(raw.encode()).hexdigest()
            if task_hash == last_task_hash:
                time.sleep(POLL_INTERVAL)
                continue

            # ---- AUTO EXECUTE ----
            task_count += 1
            task_id = str(task.get("task_id", "?"))
            engine = task.get("engine", "PYTHON")
            command = task.get("command", "")
            description = task.get("description", "No description")
            timeout = task.get("timeout", COMMAND_TIMEOUT)

            _header("Task #" + str(task_count) + " received [" + task_id + "]")
            print("  Description : " + description)
            print("  Engine      : " + engine)
            print("  Timeout     : " + str(timeout) + "s")
            _line("-")
            print("  Command:")
            for line in command.split("\n"):
                print("    " + line)
            _line("-")

            _log(">>", "Executing...")

            rc, output = execute_command(engine, command, timeout)

            # Display result
            status_word = "SUCCESS" if rc == 0 else "FAILED"
            _log("<<", "Result: " + status_word + " (exit code: " + str(rc) + ")")
            _line("-")
            print("Output:")
            print(output[:3000])
            _footer()

            # Upload result to GitHub
            result = {
                "task_id": task_id,
                "status": status_word,
                "return_code": rc,
                "engine": engine,
                "description": description,
                "command_preview": command[:500],
                "output": output[:5000],
                "timestamp": _now(),
                "executed_on": "local_machine",
            }

            result_name = RESULT_DIR + "/bridge_result_" + str(int(time.time())) + ".json"
            if gh_put_file(
                result_name,
                json.dumps(result, ensure_ascii=False, indent=2),
                "Bridge: executed task " + task_id,
            ):
                _log("OK", "Result uploaded -> " + result_name)
            else:
                _log("!!", "Failed to upload result")

            # Clear task file
            gh_put_file(TASK_FILE, "waiting", "Bridge: task processed")
            last_task_hash = task_hash

            _log("..", "Waiting for next task...")
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print()
            _log("--", "Bridge stopped. Goodbye!")
            break
        except Exception as e:
            _log("!!", "Unexpected error: " + str(e))
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
