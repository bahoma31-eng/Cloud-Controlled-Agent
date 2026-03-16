#!/usr/bin/env python3
"""
bridge/local_bridge.py
~~~~~~~~~~~~~~~~~~~~~~
Local Bridge Script — يربط جهازك المحلي بالوكيل السحابي عبر GitHub.

السكريبت يراقب ملف المهام على GitHub، ويعرض لك كل مهمة قبل تنفيذها.
لن يُنفَّذ أي شيء بدون موافقتك الصريحة.

الاستخدام:
    python bridge/local_bridge.py

المتغيرات المطلوبة في .env:
    GITHUB_TOKEN
    REPO_OWNER  (اختياري، افتراضي: bahoma31-eng)
    REPO_NAME   (اختياري، افتراضي: Cloud-Controlled-Agent)
"""

import os
import sys
import json
import time
import base64
import subprocess
import hashlib
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("مكتبات مفقودة. شغّل: pip install requests python-dotenv")
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

# ANSI colors
_R = "\033[0m"
_C = "\033[96m"
_G = "\033[92m"
_Y = "\033[93m"
_RED = "\033[91m"
_M = "\033[95m"
_B = "\033[1m"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _box(title, content, color=_C):
    border = color + "=" * 70 + _R
    print(f"\n{border}")
    print(f"{color}{_B}  {title}{_R}")
    print(color + "-" * 70 + _R)
    print(content.strip())
    print(f"{border}\n")


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------
def _headers():
    return {
        "Authorization": "token " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "Local-Bridge-Agent",
    }


def _content_url(path):
    return GITHUB_API_BASE + "/repos/" + REPO_OWNER + "/" + REPO_NAME + "/contents/" + path


def gh_get_file(path):
    """Return (content_str, sha) or (None, None)."""
    try:
        r = requests.get(_content_url(path), headers=_headers(), timeout=20)
        if r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return content, data.get("sha")
        elif r.status_code == 404:
            pass  # File doesn't exist yet
        else:
            print(f"{_RED}[GitHub] GET {path} -> {r.status_code}{_R}")
    except Exception as e:
        print(f"{_RED}خطأ في قراءة {path}: {e}{_R}")
    return None, None


def gh_put_file(path, content, message):
    """Create or update a file on GitHub."""
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
        print(f"{_RED}خطأ في رفع {path}: {e}{_R}")
        return False


# ---------------------------------------------------------------------------
# Task execution (with manual confirmation)
# ---------------------------------------------------------------------------
def execute_command(engine, content, timeout):
    """Execute a command locally. Returns (returncode, output)."""
    try:
        if engine.upper() == "POWERSHELL":
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", content]
        elif engine.upper() == "BASH":
            cmd = ["bash", "-c", content]
        elif engine.upper() == "PYTHON":
            cmd = ["python", "-c", content]
        elif engine.upper() == "CMD":
            cmd = ["cmd", "/c", content]
        else:
            return 1, "محرك غير مدعوم: " + engine

        p = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        stdout = (p.stdout or b"").decode("utf-8", errors="replace")
        stderr = (p.stderr or b"").decode("utf-8", errors="replace")
        return p.returncode, (stdout + ("\n" + stderr if stderr else "")).strip()

    except subprocess.TimeoutExpired:
        return 124, "انتهت مهلة التنفيذ (TimeoutExpired)"
    except FileNotFoundError:
        return 1, "المحرك '" + engine + "' غير متوفر على هذا النظام"
    except Exception as e:
        return 1, "خطأ في التنفيذ: " + str(e)


def ask_confirmation(task):
    """Display task details and ask for user confirmation."""
    _box(
        "مهمة جديدة وردت من الوكيل السحابي",
        "المعرف  : " + str(task.get("task_id", "?")) + "\n"
        "الوصف   : " + str(task.get("description", "بدون وصف")) + "\n"
        "المحرك  : " + str(task.get("engine", "?")) + "\n"
        "المهلة  : " + str(task.get("timeout", COMMAND_TIMEOUT)) + " ثانية",
        _M,
    )

    print(_Y + _B + "الأمر المطلوب تنفيذه:" + _R)
    print(_Y + "-" * 70 + _R)
    print(task.get("command", ""))
    print(_Y + "-" * 70 + _R)

    print("\n" + _G + "[y]" + _R + " تنفيذ   " + _RED + "[n]" + _R + " تخطي   " + _C + "[e]" + _R + " تعديل ثم تنفيذ   " + _RED + "[q]" + _R + " إنهاء البريدج")
    while True:
        choice = input("\n" + _B + "اختيارك > " + _R).strip().lower()
        if choice in ("y", "n", "e", "q", ""):
            return choice if choice else "n"
        print("  اختيار غير صالح. استخدم y / n / e / q")


def edit_command(original):
    """Allow user to edit the command before execution."""
    print("\n" + _C + "أدخل الأمر المعدّل (اكتب 'done' في سطر جديد للإنهاء):" + _R)
    lines = []
    while True:
        line = input()
        if line.strip().lower() == "done":
            break
        lines.append(line)
    edited = "\n".join(lines)
    if not edited.strip():
        print(_Y + "الأمر فارغ، سيتم استخدام الأمر الأصلي." + _R)
        return original
    return edited


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    # Startup checks
    if not GITHUB_TOKEN:
        print(_RED + "GITHUB_TOKEN مفقود! أضفه في ملف .env" + _R)
        sys.exit(1)

    _box(
        "Local Bridge Agent V1.0",
        "المستودع    : " + REPO_OWNER + "/" + REPO_NAME + "\n"
        "ملف المهام  : " + TASK_FILE + "\n"
        "فترة الفحص  : كل " + str(POLL_INTERVAL) + " ثانية\n"
        "مهلة التنفيذ : " + str(COMMAND_TIMEOUT) + " ثانية\n\n"
        "الجسر يعمل الآن... في انتظار المهام.\n"
        "لن يُنفَّذ أي أمر بدون موافقتك الصريحة.\n"
        "   اضغط Ctrl+C للإيقاف.",
        _G,
    )

    last_task_hash = None

    while True:
        try:
            # Check for new task
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

            # Skip if already processed (by content hash)
            task_hash = hashlib.md5(raw.encode()).hexdigest()
            if task_hash == last_task_hash:
                time.sleep(POLL_INTERVAL)
                continue

            # ---- MANUAL CONFIRMATION ----
            choice = ask_confirmation(task)

            if choice == "q":
                print("\n" + _Y + "إيقاف الجسر. مع السلامة!" + _R)
                break

            if choice == "n":
                print(_Y + "تم تخطي المهمة." + _R)
                last_task_hash = task_hash
                result = {
                    "task_id": task.get("task_id"),
                    "status": "SKIPPED",
                    "message": "تم تخطي المهمة من قبل المستخدم",
                    "timestamp": _now(),
                }
                result_name = RESULT_DIR + "/bridge_result_" + str(int(time.time())) + ".json"
                gh_put_file(result_name, json.dumps(result, ensure_ascii=False, indent=2), "Bridge: task skipped by user")
                gh_put_file(TASK_FILE, "waiting", "Bridge: task processed")
                time.sleep(POLL_INTERVAL)
                continue

            command = task.get("command", "")
            if choice == "e":
                command = edit_command(command)

            # ---- EXECUTE ----
            engine = task.get("engine", "POWERSHELL")
            timeout = task.get("timeout", COMMAND_TIMEOUT)

            print("\n" + _G + "جارٍ التنفيذ..." + _R)
            rc, output = execute_command(engine, command, timeout)

            # Display result
            status_text = "نجح" if rc == 0 else "فشل"
            result_color = _G if rc == 0 else _RED
            _box(
                "نتيجة التنفيذ — " + status_text,
                "كود الخروج : " + str(rc) + "\n"
                "المخرجات:\n" + output[:3000],
                result_color,
            )

            # Upload result to GitHub
            result = {
                "task_id": task.get("task_id"),
                "status": "SUCCESS" if rc == 0 else "FAILED",
                "return_code": rc,
                "engine": engine,
                "command_preview": command[:500],
                "output": output[:5000],
                "timestamp": _now(),
                "executed_on": "local_machine",
            }

            result_name = RESULT_DIR + "/bridge_result_" + str(int(time.time())) + ".json"
            if gh_put_file(
                result_name,
                json.dumps(result, ensure_ascii=False, indent=2),
                "Bridge: executed task " + str(task.get("task_id", "?")),
            ):
                print(_G + "تم رفع النتيجة إلى " + result_name + _R)
            else:
                print(_RED + "فشل رفع النتيجة إلى GitHub" + _R)

            # Clear task file
            gh_put_file(TASK_FILE, "waiting", "Bridge: task processed")
            last_task_hash = task_hash

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n" + _Y + "تم إيقاف الجسر. مع السلامة!" + _R)
            break
        except Exception as e:
            print(_RED + "خطأ غير متوقع: " + str(e) + _R)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
