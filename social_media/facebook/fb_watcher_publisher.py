#!/usr/bin/env python3
"""
fb_watcher_publisher.py
-----------------------
يراقب مجلد media-pipeline/output في مستودع GitHub،
وعند العثور على صورة أو فيديو يقوم بنشره على فيسبوك،
ثم ينقله إلى media-pipeline/processed داخل نفس المستودع.
"""
import base64
import io
import json
import logging
import mimetypes
import os
import sys
import time
from pathlib import PurePosixPath

import requests
from dotenv import load_dotenv

# =========================
# Load .env file
# =========================
load_dotenv()

# =========================
# GitHub configuration
# =========================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "bahoma31-eng")
GITHUB_REPO = os.getenv("GITHUB_REPO", "Cloud-Controlled-Agent")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_OUTPUT_PATH = os.getenv("GITHUB_OUTPUT_PATH", "media-pipeline/output")
GITHUB_PROCESSED_PATH = os.getenv("GITHUB_PROCESSED_PATH", "media-pipeline/processed")
GITHUB_API_BASE = "https://api.github.com"

# =========================
# Polling interval
# =========================
POLL_INTERVAL_SECONDS = int(os.getenv("FB_POLL_INTERVAL_SECONDS", "20"))

# =========================
# Supported media types
# =========================
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}

# =========================
# Facebook / tokens config
# =========================
SOCIAL_TOKENS_PATH = os.getenv(
    "SOCIAL_TOKENS_PATH",
    "social_media/social_tokens.json"
)
FB_CAPTION = os.getenv(
    "FB_CAPTION",
    "عرض اليوم جاهز! اطلب الآن عبر واتساب أو تواصل معنا على صفحاتنا."
)
GRAPH_API_BASE = os.getenv("FB_GRAPH_API_BASE", "https://graph.facebook.com/v19.0")

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("fb-watcher-publisher")

# ملفات تمت معالجتها (SHA) لتجنب إعادة النشر — يُحمَّل من ملف ويُحفظ فيه
_PROCESSED_LOG = os.getenv("FB_PROCESSED_LOG", "social_media/facebook/.processed_shas.json")
_processed_shas: set = set()


def _load_processed_shas():
    """يحمّل قائمة الـ SHAs المعالجة من الملف إن وُجد."""
    try:
        with open(_PROCESSED_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                _processed_shas.update(data)
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("تعذّر تحميل سجل المعالجة: %s", exc)


def _save_processed_shas():
    """يحفظ قائمة الـ SHAs المعالجة في الملف."""
    try:
        os.makedirs(os.path.dirname(_PROCESSED_LOG) or ".", exist_ok=True)
        with open(_PROCESSED_LOG, "w", encoding="utf-8") as f:
            json.dump(list(_processed_shas), f)
    except Exception as exc:
        logger.warning("تعذّر حفظ سجل المعالجة: %s", exc)


# =========================
# Helpers
# =========================

def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _is_supported(filename: str) -> bool:
    ext = PurePosixPath(filename).suffix.lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS or ext in SUPPORTED_VIDEO_EXTENSIONS


def _is_video(filename: str) -> bool:
    return PurePosixPath(filename).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def _guess_mime(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    if mt:
        return mt
    if _is_video(filename):
        return "video/mp4"
    return "image/jpeg"


# =========================
# GitHub API operations
# =========================

def github_list_output() -> list:
    """
    يعيد قائمة الملفات الموجودة في GITHUB_OUTPUT_PATH.
    كل عنصر هو dict يحتوي على: name, sha, download_url, path
    """
    url = (
        f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{GITHUB_OUTPUT_PATH}?ref={GITHUB_BRANCH}"
    )
    try:
        r = requests.get(url, headers=_github_headers(), timeout=30)
        if r.status_code == 404:
            logger.info("مجلد output غير موجود بعد في المستودع: %s", GITHUB_OUTPUT_PATH)
            return []
        r.raise_for_status()
        items = r.json()
        if not isinstance(items, list):
            return []
        return [i for i in items if i.get("type") == "file" and _is_supported(i.get("name", ""))]
    except Exception as exc:
        logger.error("خطأ عند قراءة قائمة الملفات من GitHub: %s", exc)
        return []


def github_download_file(item: dict) -> bytes | None:
    """
    يُنزّل محتوى الملف من المستودع.
    يستخدم download_url أو يفك ترميز المحتوى من content API.
    """
    download_url = item.get("download_url")
    if download_url:
        try:
            r = requests.get(download_url, headers=_github_headers(), timeout=120)
            r.raise_for_status()
            return r.content
        except Exception as exc:
            logger.error("خطأ عند تنزيل %s: %s", item.get("name"), exc)
            return None

    # احتياطي: استخدام contents API
    url = (
        f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{item['path']}?ref={GITHUB_BRANCH}"
    )
    try:
        r = requests.get(url, headers=_github_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        # GitHub API يُضيف فواصل أسطر داخل ترميز base64 — نزيلها قبل الفك
        content_b64 = data.get("content", "").replace("\n", "")
        return base64.b64decode(content_b64)
    except Exception as exc:
        logger.error("خطأ عند تنزيل %s (fallback): %s", item.get("name"), exc)
        return None


def github_move_to_processed(item: dict, file_bytes: bytes) -> bool:
    """
    ينقل الملف من output إلى processed في المستودع:
    1. يرفع الملف إلى processed
    2. يحذف الملف من output
    """
    name = item["name"]
    dest_path = f"{GITHUB_PROCESSED_PATH}/{name}"
    src_path = item["path"]
    src_sha = item["sha"]

    # 1) رفع إلى processed
    put_url = (
        f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{dest_path}"
    )

    # تحقق إذا الملف موجود مسبقاً في processed (للحصول على SHA القديم)
    existing_sha = None
    try:
        chk = requests.get(put_url + f"?ref={GITHUB_BRANCH}", headers=_github_headers(), timeout=15)
        if chk.status_code == 200:
            existing_sha = chk.json().get("sha")
            # إضافة timestamp للاسم لتجنب التعارض
            stem = PurePosixPath(name).stem
            suffix = PurePosixPath(name).suffix
            ts = int(time.time())
            dest_path = f"{GITHUB_PROCESSED_PATH}/{stem}_{ts}{suffix}"
            put_url = (
                f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
                f"/contents/{dest_path}"
            )
            existing_sha = None
    except Exception:
        pass

    put_body: dict = {
        "message": f"move {name} to processed",
        "content": base64.b64encode(file_bytes).decode(),
        "branch": GITHUB_BRANCH,
    }
    if existing_sha:
        put_body["sha"] = existing_sha

    try:
        r = requests.put(put_url, headers=_github_headers(), json=put_body, timeout=60)
        if r.status_code not in (200, 201):
            logger.error("فشل رفع %s إلى processed: HTTP %s | %s", name, r.status_code, r.text[:2000])
            return False
        logger.info("تم رفع %s إلى processed: %s", name, dest_path)
    except Exception as exc:
        logger.error("خطأ عند رفع %s إلى processed: %s", name, exc)
        return False

    # 2) حذف من output
    del_url = (
        f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{src_path}"
    )
    del_body = {
        "message": f"remove {name} from output after publishing",
        "sha": src_sha,
        "branch": GITHUB_BRANCH,
    }
    try:
        r = requests.delete(del_url, headers=_github_headers(), json=del_body, timeout=30)
        if r.status_code not in (200, 204):
            logger.error("فشل حذف %s من output: HTTP %s | %s", name, r.status_code, r.text[:2000])
            return False
        logger.info("تم حذف %s من output بنجاح.", name)
    except Exception as exc:
        logger.error("خطأ عند حذف %s من output: %s", name, exc)
        return False

    return True


# =========================
# Token loading
# =========================

def load_tokens() -> dict:
    p_path = SOCIAL_TOKENS_PATH
    try:
        with open(p_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"social_tokens.json غير موجود: {p_path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"خطأ في تحليل social_tokens.json: {exc}")

    if "facebook_access_token" not in data or "facebook_page_id" not in data:
        raise ValueError("social_tokens.json يجب أن يحتوي على facebook_access_token و facebook_page_id")
    return data


# =========================
# Facebook publishing
# =========================

def publish_photo(tokens: dict, filename: str, file_bytes: bytes, caption: str) -> tuple[bool, str]:
    page_id = str(tokens["facebook_page_id"])
    access_token = str(tokens["facebook_access_token"])
    url = f"{GRAPH_API_BASE}/{page_id}/photos"
    mime = _guess_mime(filename)
    try:
        files = {"source": (filename, io.BytesIO(file_bytes), mime)}
        data = {"caption": caption, "access_token": access_token}
        r = requests.post(url, data=data, files=files, timeout=300)
        if r.status_code in (200, 201):
            return True, r.text
        return False, f"HTTP {r.status_code}: {r.text[:2000]}"
    except Exception as exc:
        return False, f"Exception: {exc}"


def publish_video(tokens: dict, filename: str, file_bytes: bytes, caption: str) -> tuple[bool, str]:
    page_id = str(tokens["facebook_page_id"])
    access_token = str(tokens["facebook_access_token"])
    url = f"{GRAPH_API_BASE}/{page_id}/videos"
    mime = _guess_mime(filename)
    try:
        files = {"source": (filename, io.BytesIO(file_bytes), mime)}
        data = {"description": caption, "access_token": access_token}
        r = requests.post(url, data=data, files=files, timeout=600)
        if r.status_code in (200, 201):
            return True, r.text
        return False, f"HTTP {r.status_code}: {r.text[:2000]}"
    except Exception as exc:
        return False, f"Exception: {exc}"


# =========================
# Main scan loop
# =========================

def scan_and_publish_once(tokens: dict):
    items = github_list_output()

    if not items:
        logger.info("لا توجد ملفات وسائط في %s/%s", GITHUB_REPO, GITHUB_OUTPUT_PATH)
        return

    for item in items:
        sha = item.get("sha", "")
        name = item.get("name", "")

        if sha in _processed_shas:
            logger.debug("تم تخطي %s (تمت معالجته مسبقاً)", name)
            continue

        logger.info("تم العثور على: %s (sha=%s)", name, sha[:8])

        file_bytes = github_download_file(item)
        if file_bytes is None:
            logger.error("فشل تنزيل %s، سيتم تخطيه.", name)
            continue

        caption = FB_CAPTION

        if _is_video(name):
            logger.info("فيديو مكتشف: %s — جارٍ النشر على فيسبوك...", name)
            ok, msg = publish_video(tokens, name, file_bytes, caption)
        else:
            logger.info("صورة مكتشفة: %s — جارٍ النشر على فيسبوك...", name)
            ok, msg = publish_photo(tokens, name, file_bytes, caption)

        if ok:
            logger.info("تم النشر بنجاح: %s", name)
            moved = github_move_to_processed(item, file_bytes)
            if moved:
                _processed_shas.add(sha)
                _save_processed_shas()
                logger.info("تم نقل %s إلى processed في المستودع.", name)
            else:
                logger.warning("النشر نجح لكن فشل نقل %s إلى processed.", name)
                # نضيف SHA لتجنب إعادة النشر حتى لو فشل النقل
                _processed_shas.add(sha)
                _save_processed_shas()
        else:
            logger.error("فشل النشر لـ %s | %s", name, msg)


def main():
    _load_processed_shas()
    logger.info("=== fb-watcher-publisher يعمل (GitHub API mode) ===")
    logger.info("GitHub Token: %s", "✓ موجود" if GITHUB_TOKEN else "✗ غير موجود — قراءة الملفات العامة فقط")
    logger.info("المستودع: %s/%s@%s", GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH)
    logger.info("مجلد المراقبة: %s", GITHUB_OUTPUT_PATH)
    logger.info("مجلد المعالجة: %s", GITHUB_PROCESSED_PATH)
    logger.info("فترة الاستطلاع: %s ثانية", POLL_INTERVAL_SECONDS)
    logger.info("ملف التوكنز: %s", SOCIAL_TOKENS_PATH)

    try:
        tokens = load_tokens()
    except Exception as e:
        logger.error("لا يمكن تحميل التوكنز: %s", e)
        sys.exit(2)

    while True:
        try:
            scan_and_publish_once(tokens)
        except Exception as exc:
            logger.exception("خطأ غير متوقع: %s", exc)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
