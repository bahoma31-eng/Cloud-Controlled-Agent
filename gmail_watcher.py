#!/usr/bin/env python3
"""
gmail_watcher.py
~~~~~~~~~~~~~~~~
يراقب Gmail كل فترة، يبحث فقط عن آخر إيميل من bahoma31@gmail.com
يحوّله إلى مهمة JSON عبر Groq ويكتبها في GitHub.
"""
import os, sys, time, json, imaplib, email, base64, re
from email.header import decode_header
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

def check_gmail():
    """يبحث عن آخر إيميل من TRUSTED_SENDER فقط، يتجاهل الباقي."""
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PW)
    mail.select("inbox")

    # ابحث فقط عن الإيميلات من المرسل الموثوق
    status, data = mail.search(None, f'(UNSEEN FROM "{TRUSTED_SENDER}")')

    if status != "OK" or not data[0]:
        log("💤", f"No new email from {TRUSTED_SENDER}")
        mail.logout()
        return None

    ids = data[0].split()
    log("📬", f"Found {len(ids)} unread email(s) from {TRUSTED_SENDER}")

    # خذ فقط آخر إيميل (أحدث واحد)
    latest_id = ids[-1]

    # علّم جميع الإيميلات الأخرى كمقروءة (تجاهلها)
    for eid in ids[:-1]:
        mail.store(eid, "+FLAGS", "\\Seen")
        log("⏭", f"Skipped older email id={eid.decode()}")

    # اقرأ آخر إيميل
    status, msg_data = mail.fetch(latest_id, "(RFC822)")
    if status != "OK":
        mail.logout()
        return None

    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    subject = decode_str(msg.get("Subject", "No subject"))
    body = get_body(msg)

    log("📧", f"Processing: Subject: {subject[:80]}")

    # علّمه كمقروء
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
    print("Mode     : Latest email only")
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
                        task["task_id"] = f"email-{int(time.time())}"
                        task["source"] = "gmail"
                        task["from"] = task_info["sender"]
                        task["original_subject"] = task_info["subject"]

                        log("✅", f"Task parsed: {task.get('description', '?')}")
                        log("🔧", f"Engine: {task.get('engine')} | Command: {str(task.get('command', ''))[:80]}")

                        ok = gh_put(TASK_FILE,
                                    json.dumps(task, ensure_ascii=False, indent=2),
                                    f"Gmail Watcher: task from {task_info['sender']}")
                        if ok:
                            log("🚀", f"Task written to GitHub: {TASK_FILE}")
                        else:
                            log("!!", "Failed to write task to GitHub")

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
