#!/usr/bin/env python3
"""
bridge/local_bridge.py
~~~~~~~~~~~~~~~~~~~~~~
Local Bridge Script — يربط جهازك المحلي بالوكيل السحابي عبر GitHub.

السكريبت يراقب ملف المهام على GitHub، ويعرض لك كل مهمة قبل تنفيذها.
لن يُنفَّذ أي شيء بدون موافقتك الصريحة.

الاستخدام:
    python bridge/local_bridge.py

المتطيرات المطلوبة في .env:
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
    print("❌ مكتبات مفقودة. شغّل: pip install requests python-dotenv")
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

# ANSI colors
_R = "\033[0m"   # Reset
_C = "\033[96m"  # Cyan
_G = "\033[92m"  # Green
_Y = "\033[93m"  # Yellow
_RED = "\033[91m" # Red
_M = "\033[95m"  # Magenta
_B = "\033[1m"   # Bold


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _box(title: str, content: str, color: str = _C) -> None:
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
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Local-Bridge-Agent",
    }


def _content_url(path: str) -> str:
    return f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"


def gh_get_file(path: str):
    """Return (content_str, sha) or (None, None)."""
    try:
        r = requests.get(_content_url(path), headers=_headers(), timeout=20)
        if r.status_code == 200:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return content, data.get("sha")
    except Exception as e:
        print(f"{_RED}❌ خطأ في قراءة {path}: {e}{_R}")
    return None, None


def gh_put_file(path: str, content: str, message: str) -> bool:
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
        print(f"{_RED}❌ خطأ في رفع {path}: {e}{_R}")
        return False


# ---------------------------------------------------------------------------
# Task execution (with manual confirmation)
# ---------------------------------------------------------------------------
def execute_command(engine: str, content: str, timeout: int) -> tuple:
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
            return 1, f"محرك غير مدعوم: {engine}"

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
        return 124, "⏱️ انتهت مهلة التنفيذ (TimeoutExpired)"
    except FileNotFoundError:
        return 1, f"❌ المحرك '{engine}' غير متوفر على هذا النظام"
    except Exception as e:
        return 1, f"❌ خطأ في التنفيذ: {e}"


def ask_confirmation(task: dict) -> str:
    """Display task details and ask for user confirmation.
    
    Returns:
        'y' = execute, 'n' = skip, 'e' = edit then execute, 'q' = quit
    """
    _box(
        "📨 مهمة جديدة وردت من الوكيل السحابي",
        f"المعرّف  : {task.get('task_id', '?')}\n"
        f"الوصف   : {task.get('description', 'بدون وصف')}\n"
        f"المحرك  : {task.get('engine', '?')}\n"
        f"المهلة  : {task.get('timeout', COMMAND_TIMEOUT)} ثانية",
        _M,
    )

    print(f"{_Y}{_B}📜 الأمر المطلوب تنفيذه:{_R}")
    print(f"{_Y}" + "-" * 70 + _R)
    print(task.get("command", ""))
    print(f"{_Y}" + "-" * 70 + _R)

    print(f"\n{_G}[y]{_R} تنفيذ   {_RED}[n]{_R} تخطي   {_C}[e]{_R} تعديل ثم تنفيذ   {_RED}[q]{_R} إنهاء البريدج")
    while True:
        choice = input(f"\n{_B}اختيارك ▸ {_R}").strip().lower()
        if choice in ("y", "n", "e", "q", ""):
            return choice if choice else "n"
        print("  ⚠️  اختيار غير صالح. استخدم y / n / e / q")


def edit_command(original: str) -> str:
    """Allow user to edit the command before execution."""
    print(f"\n{_C}📝 أدخل الأمر المعدّل (اكتب 'done' في سطر جديد للإنهاء):{_R}")
    lines = []
    while True:
        line = input()
        if line.strip().lower() == "done":
            break
        lines.append(line)
    edited = "\n".join(lines)
    if not edited.strip():
        print(f"{_Y}⚠️ الأمر فارغ، سيتم استخدام الأمر الأصلي.{_R}")
        return original
    return edited


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    # Startup checks
    if not GITHUB_TOKEN:
        print(f"{_RED}❌ GITHUB_TOKEN مفقود! أضفه في ملف .env{_R}")
        sys.exit(1)

    _box(
        "🌉 Local Bridge Agent V1.0",
        f"المستودع    : {REPO_OWNER}/{REPO_NAME}\n"
        f"ملف المهام  : {TASK_FILE}\n"
        f"فترة الفحص  : كل {POLL_INTERVAL} ثانية\n"
        f"مهلة التنفيذ : {COMMAND_TIMEOUT} ثانية\n\n"
        "⚡ الجسر يعمل الآن... في انتظار المهام.\n"
        "🛡️  لن يُنفَّذ أي أمر بدون موافقتك الصريحة.\n"
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
                print(f"\n{_Y}👋 إيقاف الجسر. مع السلامة!{_R}")
                break

            if choice == "n":
                print(f"{_Y}⏭️  تم تخطي المهمة.{_R}")
                last_task_hash = task_hash
                # Mark as skipped
                result = {
                    "task_id": task.get("task_id"),
                    "status": "SKIPPED",
                    "message": "تم تخطي المهمة من قبل المستخدم",
                    "timestamp": _now(),
                }
                result_name = f"{RESULT_DIR}/bridge_result_{int(time.time())}.json"
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

            print(f"\n{_G}⚡ جارٍ التنفيذ...{_R}")
            rc, output = execute_command(engine, command, timeout)

            # Display result
            status = "✅ نجح" if rc == 0 else "❌ فشل"
            _box(
                f"📊 نتيجة التنفيذ — {status}",
                f"كود الخروج : {rc}\n"
                f"المخرجات:\n{output[:3000]}",
                _G if rc == 0 else _RED,
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

            result_name = f"{RESULT_DIR}/bridge_result_{int(time.time())}.json"
            if gh_put_file(
                result_name,
                json.dumps(result, ensure_ascii=False, indent=2),
                f"Bridge: executed task {task.get('task_id', '?')}",
            ):
                print(f"{_G}📤 تم رفع النتيجة إلى {result_name}{_R}")
            else:
                print(f"{_RED}⚠️ فشل رفع النتيجة إلى GitHub{_R}")

            # Clear task file
            gh_put_file(TASK_FILE, "waiting", "Bridge: task processed")
            last_task_hash = task_hash

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print(f"\n\n{_Y}👋 تم إيقاف الجسر. مع السلامة!{_R}")
            break
        except Exception as e:
            print(f"{_RED}❌ خطأ غير متوقع: {e}{_R}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
