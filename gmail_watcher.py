#!/usr/bin/env python3
"""
gmail_watcher.py
~~~~~~~~~~~~~~~~
يراقب Gmail كل فترة، يبحث فقط عن آخر إيميل من bahoma31@gmail.com
يحوّله إلى مهمة JSON عبر Groq ويكتبها في GitHub،
ثم ينفذ الأمر محلياً ويرسل تقرير HTML بالنتيجة.
"""
import os, sys, time, json, imaplib, email, base64, re, subprocess, smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    print("Run: pip install requests python-dotenv")
    sys.exit(1)

load_dotenv()

# ── إعدادات ──────────────────────────────────────────────
GMAIL_ADDRESS    = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PW     = os.getenv("GMAIL_APP_PASSWORD", "")
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
GITHUB_TOKEN     = os.getenv("GITHUB_TOKEN", "")
REPO_OWNER       = os.getenv("REPO_OWNER", "")
REPO_NAME        = os.getenv("REPO_NAME", "")
BRANCH           = os.getenv("BRIDGE_BRANCH", "main")
POLL             = int(os.getenv("GMAIL_POLL_SECONDS", "30"))
GROQ_MODEL       = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# المرسل الوحيد المعتمد
TRUSTED_SENDER   = "bahoma31@gmail.com"

TASK_FILE        = "inbox/local_task.json"
API_BASE         = "https://api.github.com"

GROQ_PROMPT = """أنت مساعد يحول طلبات البريد الإلكتروني إلى مهام برمجية.

استخرج من الرسالة التالية مهمة وأعد JSON فقط بهذا الشكل:
{
  "task_id": "email-TIMESTAMP",
  "engine": "PYTHON أو BASH",
  "command": "الأمر القابل للتنفيذ",
  "description": "وصف قصير",
  "timeout": 60
}

قواعد:
- engine: استخدم PYTHON للحسابات والبيانات، BASH للأوامر النظام
- command: كود قابل للتنفيذ مباشرة، بدون markdown
- إذا الطلب غير واضح أو غير آمن، اجعل command: echo "Task not understood"
- أعد JSON فقط بدون أي نص إضافي

الرسالة:
"""

def ts(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def log(icon, msg): print(f"[{ts()}] {icon} {msg}", flush=True)

def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Gmail-Watcher"
    }

def gh_get_sha(path):
    url = f"{API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    r = requests.get(url, headers=gh_headers(), timeout=15)
    if r.status_code == 200:
        return r.json().get("sha")
    return None

def gh_put(path, content, msg):
    url = f"{API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"
    sha = gh_get_sha(path)
    payload = {
        "message": msg,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": BRANCH
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=gh_headers(), json=payload, timeout=20)
    return r.status_code in (200, 201)

def groq_parse(subject, body):
    text = f"الموضوع: {subject}\n\nالمحتوى:\n{body[:2000]}"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": GROQ_PROMPT + text}],
        "temperature": 0.1,
        "max_tokens": 500
    }
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers=headers, json=payload, timeout=30)
    if r.status_code != 200:
        log("!", f"Groq error: {r.status_code} {r.text[:200]}")
        return None
    content = r.json()["choices"][0]["message"]["content"].strip()
    match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(content)

def decode_str(s):
    parts = decode_header(s)
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="replace")
        else:
            result += part
    return result

def safe_decode(payload, charset):
    if not payload:
        return ""
    charset = (charset or "utf-8").lower()
    if charset in ("unknown-8bit", "x-unknown", "unknown"):
        charset = "latin-1"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return payload.decode(enc, errors="replace")
            except Exception:
                continue
    return payload.decode("utf-8", errors="replace")

def get_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body += safe_decode(payload, part.get_content_charset())
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = safe_decode(payload, msg.get_content_charset())
    return body.strip()

def execute_task(task):
    """ينفذ الأمر محلياً ويعيد النتيجة."""
    engine  = task.get("engine", "BASH").upper()
    command = task.get("command", "")
    timeout = int(task.get("timeout", 60))

    log("⚙️", f"Executing [{engine}]: {command[:80]}")
    start = time.time()
    try:
        if engine == "PYTHON":
            result = subprocess.run(
                ["python3", "-c", command],
                capture_output=True, text=True, timeout=timeout
            )
        else:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=timeout
            )
        elapsed = round(time.time() - start, 2)
        stdout  = result.stdout.strip()
        stderr  = result.stderr.strip()
        code    = result.returncode
        status  = "✅ Success" if code == 0 else "❌ Failed"
        log("📊", f"Exit code: {code} | Time: {elapsed}s")
        return {"status": status, "stdout": stdout, "stderr": stderr,
                "exit_code": code, "elapsed": elapsed}
    except subprocess.TimeoutExpired:
        return {"status": "⏰ Timeout", "stdout": "", "stderr": "Command timed out",
                "exit_code": -1, "elapsed": timeout}
    except Exception as e:
        return {"status": "💥 Error", "stdout": "", "stderr": str(e),
                "exit_code": -1, "elapsed": 0}

def build_html_report(task, result):
    """يبني تقرير HTML جميل."""
    now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    description = task.get("description", "")
    engine      = task.get("engine", "BASH")
    command     = task.get("command", "")
    status      = result["status"]
    stdout      = result["stdout"] or "(لا يوجد مخرجات)"
    stderr      = result["stderr"] or "(لا توجد أخطاء)"
    elapsed     = result["elapsed"]
    exit_code   = result["exit_code"]

    status_color = "#22c55e" if result["exit_code"] == 0 else "#ef4444"
    if "Timeout" in status:
        status_color = "#f59e0b"

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background:#f1f5f9; margin:0; padding:20px; color:#1e293b; }}
  .card {{ background:#fff; border-radius:12px; padding:28px; max-width:680px; margin:auto;
           box-shadow:0 4px 24px rgba(0,0,0,0.08); }}
  .header {{ display:flex; align-items:center; gap:12px; margin-bottom:24px; border-bottom:2px solid #e2e8f0; padding-bottom:16px; }}
  .header h1 {{ font-size:1.4rem; margin:0; color:#0f172a; }}
  .badge {{ display:inline-block; padding:4px 14px; border-radius:999px; font-size:0.85rem;
            font-weight:600; color:#fff; background:{status_color}; }}
  .section {{ margin-bottom:18px; }}
  .label {{ font-size:0.78rem; font-weight:700; color:#64748b; text-transform:uppercase;
            letter-spacing:0.05em; margin-bottom:6px; }}
  .value {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;
            padding:10px 14px; font-size:0.95rem; white-space:pre-wrap; word-break:break-all; }}
  .output {{ background:#0f172a; color:#86efac; border-radius:8px; padding:14px 18px;
             font-family:monospace; font-size:0.9rem; white-space:pre-wrap; word-break:break-all; }}
  .error  {{ background:#fff1f2; color:#be123c; border:1px solid #fecdd3; border-radius:8px;
             padding:14px 18px; font-family:monospace; font-size:0.9rem; white-space:pre-wrap; }}
  .meta   {{ display:flex; gap:20px; flex-wrap:wrap; margin-top:20px; padding-top:16px;
             border-top:1px solid #e2e8f0; font-size:0.82rem; color:#94a3b8; }}
  .meta span b {{ color:#475569; }}
  .footer {{ text-align:center; margin-top:24px; font-size:0.78rem; color:#94a3b8; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <span style="font-size:2rem;">🤖</span>
    <div>
      <h1>تقرير تنفيذ المهمة</h1>
      <span class="badge">{status}</span>
    </div>
  </div>

  <div class="section">
    <div class="label">📋 وصف المهمة</div>
    <div class="value">{description}</div>
  </div>

  <div class="section">
    <div class="label">💻 الأمر المنفَّذ ({engine})</div>
    <div class="output">{command}</div>
  </div>

  <div class="section">
    <div class="label">📤 المخرجات</div>
    <div class="output">{stdout}</div>
  </div>

  {"" if not result["stderr"] else f'<div class="section"><div class="label">⚠️ الأخطاء</div><div class="error">{stderr}</div></div>'}

  <div class="meta">
    <span>⏱️ الوقت: <b>{elapsed}s</b></span>
    <span>🔢 كود الخروج: <b>{exit_code}</b></span>
    <span>🕐 التاريخ: <b>{now}</b></span>
  </div>

  <div class="footer">
    تم التنفيذ تلقائياً بواسطة Cloud-Controlled-Agent 🚀
  </div>
</div>
</body>
</html>"""
    return html

def send_report_email(to_addr, subject, html_body):
    """يرسل التقرير HTML بالإيميل."""
    log("📨", f"Sending HTML report to {to_addr}...")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 تقرير: {subject}"
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = to_addr
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PW)
            server.sendmail(GMAIL_ADDRESS, to_addr, msg.as_string())

        log("✉️", f"Report sent successfully to {to_addr}")
        return True
    except Exception as e:
        log("!", f"Failed to send email: {e}")
        return False

def check_gmail():
    """يبحث عن آخر إيميل من TRUSTED_SENDER فقط، يتجاهل الباقي."""
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PW)
    mail.select("inbox")

    status, data = mail.search(None, f'(UNSEEN FROM "{TRUSTED_SENDER}")')

    if status != "OK" or not data[0]:
        log("💤", f"No new email from {TRUSTED_SENDER}")
        mail.logout()
        return None

    ids = data[0].split()
    log("📬", f"Found {len(ids)} unread email(s) from {TRUSTED_SENDER}")

    latest_id = ids[-1]

    for eid in ids[:-1]:
        mail.store(eid, "+FLAGS", "\\Seen")
        log("⏭", f"Skipped older email id={eid.decode()}")

    status, msg_data = mail.fetch(latest_id, "(RFC822)")
    if status != "OK":
        mail.logout()
        return None

    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    subject = decode_str(msg.get("Subject", "No subject"))
    body    = get_body(msg)

    log("📧", f"Processing: Subject: {subject[:80]}")

    mail.store(latest_id, "+FLAGS", "\\Seen")
    mail.logout()

    return {"sender": TRUSTED_SENDER, "subject": subject, "body": body}

def main():
    missing = []
    if not GMAIL_ADDRESS:  missing.append("GMAIL_ADDRESS")
    if not GMAIL_APP_PW:   missing.append("GMAIL_APP_PASSWORD")
    if not GROQ_API_KEY:   missing.append("GROQ_API_KEY")
    if not GITHUB_TOKEN:   missing.append("GITHUB_TOKEN")
    if missing:
        print(f"Missing in .env: {', '.join(missing)}")
        sys.exit(1)

    print("=" * 55)
    print("Gmail Watcher - Groq Edition")
    print(f"Watching : {GMAIL_ADDRESS}")
    print(f"Trusted  : {TRUSTED_SENDER}")
    print(f"Polling  : {POLL}s")
    print(f"Groq     : {GROQ_MODEL}")
    print(f"Repo     : {REPO_OWNER}/{REPO_NAME}")
    print("Mode     : Latest email only + HTML report reply")
    print("Press Ctrl+C to stop")
    print("=" * 55)

    while True:
        try:
            task_info = check_gmail()

            if task_info:
                log("🤖", "Sending to Groq for parsing...")
                try:
                    task = groq_parse(task_info["subject"], task_info["body"])
                    if not task:
                        log("!", "Groq returned empty result")
                    else:
                        task["task_id"]          = f"email-{int(time.time())}"
                        task["source"]           = "gmail"
                        task["from"]             = task_info["sender"]
                        task["original_subject"] = task_info["subject"]

                        log("✅", f"Task parsed: {task.get('description', '?')}")
                        log("🔧", f"Engine: {task.get('engine')} | Command: {str(task.get('command', ''))[:80]}")

                        # ① كتابة المهمة في GitHub
                        ok = gh_put(TASK_FILE,
                                    json.dumps(task, ensure_ascii=False, indent=2),
                                    f"Gmail Watcher: task from {task_info['sender']}")
                        if ok:
                            log("🚀", f"Task written to GitHub: {TASK_FILE}")
                        else:
                            log("!!", "Failed to write task to GitHub")

                        # ② تنفيذ الأمر محلياً
                        exec_result = execute_task(task)

                        # ③ بناء تقرير HTML وإرساله
                        html = build_html_report(task, exec_result)
                        send_report_email(
                            to_addr=TRUSTED_SENDER,
                            subject=task_info["subject"],
                            html_body=html
                        )

                except json.JSONDecodeError as e:
                    log("!", f"JSON parse error: {e}")
                except Exception as e:
                    log("!", f"Error processing email: {e}")

            time.sleep(POLL)

        except KeyboardInterrupt:
            print()
            log("--", "Gmail Watcher stopped. Goodbye!")
            break
        except imaplib.IMAP4.error as e:
            log("!", f"IMAP error: {e}")
            time.sleep(POLL * 2)
        except Exception as e:
            log("!!", f"Unexpected error: {e}")
            time.sleep(POLL)

if __name__ == "__main__":
    main()
