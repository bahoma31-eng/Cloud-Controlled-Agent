#!/usr/bin/env python3
"""
termux_agent.py - Local Executor + Log Writer + Email Reporter
يراقب inbox/local_task.json -> ينفذ -> يكتب output/log.json -> يرسل ايميل
"""
import os
import sys
import json
import time
import base64
import subprocess
import hashlib
import shutil
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("Run: pip install requests python-dotenv")
    sys.exit(1)

load_dotenv()

REPO_OWNER    = os.getenv("REPO_OWNER", "bahoma31-eng")
REPO_NAME     = os.getenv("REPO_NAME",  "Cloud-Controlled-Agent")
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
GMAIL_USER    = os.getenv("GMAIL_USER", "bahoma31@gmail.com")
GMAIL_PASS    = os.getenv("GMAIL_APP_PASSWORD", "")
TASK_FILE     = "inbox/local_task.json"
LOG_FILE      = "output/log.json"
POLL_INTERVAL = int(os.getenv("BRIDGE_POLL_SECONDS", "10"))
TIMEOUT       = int(os.getenv("BRIDGE_TIMEOUT", "120"))
BRANCH        = os.getenv("BRIDGE_BRANCH", "main")
API_BASE      = "https://api.github.com"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def now_local():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(icon, msg):
    print("[" + now_local() + "] " + icon + " " + msg)


def gh_headers():
    return {
        "Authorization": "token " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "TermuxAgent-v1"
    }


def content_url(path):
    return API_BASE + "/repos/" + REPO_OWNER + "/" + REPO_NAME + "/contents/" + path


def gh_get(path):
    try:
        r = requests.get(content_url(path), headers=gh_headers(), timeout=20)
        if r.status_code == 200:
            d = r.json()
            content = base64.b64decode(d["content"]).decode("utf-8", errors="replace")
            return content, d.get("sha")
    except Exception as e:
        log("!", str(e))
    return None, None


def gh_put(path, content, message):
    try:
        r_old = requests.get(content_url(path), headers=gh_headers(), timeout=20)
        sha = r_old.json().get("sha") if r_old.status_code == 200 else None
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": BRANCH
        }
        if sha:
            payload["sha"] = sha
        r = requests.put(content_url(path), headers=gh_headers(), json=payload, timeout=30)
        return r.status_code in (200, 201)
    except Exception as e:
        log("!", str(e))
        return False


def run_cmd(engine, command):
    e = engine.upper()
    try:
        if e == "PYTHON":
            py = shutil.which("python3") or shutil.which("python")
            p = subprocess.run([py, "-c", command], capture_output=True, text=True, timeout=TIMEOUT)
        elif e in ("BASH", "POWERSHELL"):
            if e == "POWERSHELL":
                log("**", "POWERSHELL redirected to BASH on Termux")
            bash = shutil.which("bash")
            p = subprocess.run([bash, "-c", command], capture_output=True, text=True, timeout=TIMEOUT)
        elif e == "SH":
            p = subprocess.run(["sh", "-c", command], capture_output=True, text=True, timeout=TIMEOUT)
        else:
            return 1, "Unsupported engine: " + engine

        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if out and err:
            return p.returncode, out + "\n[STDERR]\n" + err
        return p.returncode, out or err or "(no output)"

    except subprocess.TimeoutExpired:
        return 124, "Timeout after " + str(TIMEOUT) + "s"
    except Exception as ex:
        return 1, str(ex)


def send_email(subject, html_body):
    if not GMAIL_PASS:
        log("!", "GMAIL_APP_PASSWORD not set — skipping email")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = GMAIL_USER
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_PASS)
            s.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        log("OK", "Email report sent!")
    except Exception as e:
        log("!", "Email failed: " + str(e))


def build_html(task_id, status, engine, description, output, ts):
    color = "#2ecc71" if status == "SUCCESS" else "#e74c3c"
    safe_output = output[:3000].replace("<", "&lt;").replace(">", "&gt;")
    html = (
        "<html><body style=\"font-family:monospace;background:#1e1e1e;color:#ddd;padding:20px\">"
        "<h2 style=\"color:" + color + "\">Termux Agent Report — " + status + "</h2>"
        "<table style=\"border-collapse:collapse;width:100%\">"
        "<tr><td style=\"padding:8px;color:#aaa\">Task ID</td><td style=\"padding:8px\">" + task_id + "</td></tr>"
        "<tr><td style=\"padding:8px;color:#aaa\">Engine</td><td style=\"padding:8px\">" + engine + "</td></tr>"
        "<tr><td style=\"padding:8px;color:#aaa\">Description</td><td style=\"padding:8px\">" + description + "</td></tr>"
        "<tr><td style=\"padding:8px;color:#aaa\">Time</td><td style=\"padding:8px\">" + ts + "</td></tr>"
        "</table>"
        "<h3 style=\"color:#f39c12\">Output:</h3>"
        "<pre style=\"background:#111;padding:15px;border-radius:8px;color:#2ecc71;overflow-x:auto\">" + safe_output + "</pre>"
        "<p style=\"color:#666;font-size:12px\">Sent by termux_agent.py — " + REPO_OWNER + "/" + REPO_NAME + "</p>"
        "</body></html>"
    )
    return html


def main():
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN missing in .env!")
        sys.exit(1)

    log(">>", "Termux Agent started — watching " + TASK_FILE)
    last_hash = None

    while True:
        try:
            raw, _ = gh_get(TASK_FILE)

            if not raw or raw.strip().lower() in ("waiting", "null", "", "{}"):
                time.sleep(POLL_INTERVAL)
                continue

            try:
                task = json.loads(raw)
            except Exception:
                time.sleep(POLL_INTERVAL)
                continue

            h = hashlib.md5(raw.encode("utf-8")).hexdigest()
            if h == last_hash:
                time.sleep(POLL_INTERVAL)
                continue

            task_id     = str(task.get("task_id", "?"))
            engine      = task.get("engine", "PYTHON")
            command     = task.get("command", "")
            description = task.get("description", "")

            log(">>", "Task [" + task_id + "] — " + description)
            log(">>", "Engine: " + engine)

            rc, output = run_cmd(engine, command)
            status = "SUCCESS" if rc == 0 else "FAILED"
            ts = now_utc()

            log("OK" if rc == 0 else "!!", status + " (rc=" + str(rc) + ")")
            print(output[:1000])

            log_data = {
                "task_id":     task_id,
                "status":      status,
                "return_code": rc,
                "engine":      engine,
                "description": description,
                "output":      output[:5000],
                "timestamp":   ts,
                "agent":       "termux_agent.py"
            }

            if gh_put(LOG_FILE,
                      json.dumps(log_data, ensure_ascii=False, indent=2),
                      "Agent: log task " + task_id):
                log("OK", "Log written -> " + LOG_FILE)

            send_email(
                "[Termux Agent] " + status + " — " + description[:50],
                build_html(task_id, status, engine, description, output, ts)
            )

            gh_put(TASK_FILE, "waiting", "Agent: task " + task_id + " done")
            last_hash = h
            log("..", "Waiting for next task...\n")
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log("--", "Stopped.")
            break
        except Exception as e:
            log("!!", str(e))
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
