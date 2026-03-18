#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import mimetypes
import base64
from pathlib import Path
from typing import Optional, Tuple, Any, List, Dict

import requests

# =========================
# GitHub repo configuration (can be overridden by env vars)
# =========================
REPO_OWNER = os.getenv("REPO_OWNER", "bahoma31-eng")
REPO_NAME = os.getenv("REPO_NAME", "Cloud-Controlled-Agent")
BRANCH = os.getenv("REPO_BRANCH", "main")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

GITHUB_API_BASE = "https://api.github.com"

# Watch "outbox" on GitHub (NOT local)
OUTBOX_DIR = os.getenv("FB_OUTBOX_DIR", "outbox").strip().strip("/")
# Move processed posts to this folder on GitHub
PROCESSED_DIR = os.getenv("FB_PROCESSED_DIR", "social_media/facebook/processed").strip().strip("/")

POLL_INTERVAL_SECONDS = int(os.getenv("FB_POLL_INTERVAL_SECONDS", "5"))

# Accept images + videos
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}

# Tokens file (passed from media_bridge.py or set directly)
SOCIAL_TOKENS_PATH = os.getenv(
    "SOCIAL_TOKENS_PATH",
    r"C:\Users\Revexn\Cloud-Controlled-Agent\social_media\social_tokens.json"
)

# Fixed caption text (you can change it)
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

def load_tokens() -> dict:
    p = Path(SOCIAL_TOKENS_PATH)
    if not p.exists():
        raise FileNotFoundError(f"social_tokens.json not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "facebook_access_token" not in data or "facebook_page_id" not in data:
        raise ValueError("social_tokens.json must contain facebook_access_token and facebook_page_id")

    return data

def die(msg: str, code: int = 2):
    logger.error(msg)
    sys.exit(code)

def gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "fb-watcher-publisher/2.0",
    }

def gh_contents_url(path: str) -> str:
    path = path.lstrip("/")
    return f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path}"

def gh_get_json(path: str, timeout: int = 60) -> Optional[Any]:
    url = gh_contents_url(path)
    r = requests.get(url, headers=gh_headers(), params={"ref": BRANCH}, timeout=timeout)
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    raise RuntimeError(f"GitHub GET failed {r.status_code}: {r.text[:2000]}")

def gh_list_dir(dir_path: str) -> List[dict]:
    data = gh_get_json(dir_path)
    return data if isinstance(data, list) else []

def is_supported_name(name: str) -> bool:
    ext = Path(name).suffix.lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS or ext in SUPPORTED_VIDEO_EXTENSIONS

def is_video_name(name: str) -> bool:
    return Path(name).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS

def guess_mime_name(name: str) -> str:
    mt, _ = mimetypes.guess_type(name)
    if mt:
        return mt
    if is_video_name(name):
        return "video/mp4"
    return "image/jpeg"

def gh_download_file_bytes(file_path: str) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    """
    Download file bytes from GitHub Contents API:
    - prefer content (base64)
    - fallback download_url
    - fallback git_url
    Returns: (bytes, sha, name)
    """
    data = gh_get_json(file_path)
    if not data or data.get("type") != "file":
        return None, None, None

    name = data.get("name")
    sha = data.get("sha")

    b64_content = data.get("content")
    if isinstance(b64_content, str) and b64_content.strip():
        try:
            raw = base64.b64decode(b64_content, validate=False)
            if raw:
                return raw, sha, name
        except Exception:
            pass

    dl = data.get("download_url")
    if dl:
        r = requests.get(dl, headers=gh_headers(), timeout=120)
        if r.status_code == 200 and r.content:
            return r.content, sha, name

    git_url = data.get("git_url")
    if git_url:
        rb = requests.get(git_url, headers=gh_headers(), timeout=120)
        if rb.status_code == 200:
            blob = rb.json()
            enc = (blob.get("encoding") or "").lower()
            cont = blob.get("content") or ""
            if enc == "base64" and cont:
                raw = base64.b64decode(cont, validate=False)
                if raw:
                    return raw, sha, name

    return None, sha, name

def gh_put_file(path: str, content_bytes: bytes, message: str) -> Tuple[bool, str]:
    url = gh_contents_url(path)
    old = requests.get(url, headers=gh_headers(), params={"ref": BRANCH}, timeout=60)
    sha = old.json().get("sha") if old.status_code == 200 else None

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=gh_headers(), json=payload, timeout=120)
    return (r.status_code in (200, 201)), r.text

def gh_delete_file(path: str, message: str, sha: Optional[str]) -> Tuple[bool, str]:
    if not sha:
        data = gh_get_json(path)
        if not data or data.get("type") != "file":
            return False, f"Not found: {path}"
        sha = data.get("sha")

    url = gh_contents_url(path)
    r = requests.delete(
        url,
        headers=gh_headers(),
        json={"message": message, "sha": sha, "branch": BRANCH},
        timeout=120,
    )
    return (r.status_code in (200, 204)), r.text

def publish_photo(tokens: dict, filename: str, content: bytes, caption: str) -> tuple[bool, str]:
    page_id = str(tokens["facebook_page_id"])
    access_token = str(tokens["facebook_access_token"])

    url = f"{GRAPH_API_BASE}/{page_id}/photos"
    mime = guess_mime_name(filename)

    try:
        files = {"source": (filename, content, mime)}
        data = {"caption": caption, "access_token": access_token}
        r = requests.post(url, data=data, files=files, timeout=300)

        if r.status_code in (200, 201):
            return True, r.text
        return False, f"HTTP {r.status_code}: {r.text[:2000]}"
    except Exception as exc:
        return False, f"Exception: {exc}"

def publish_video(tokens: dict, filename: str, content: bytes, caption: str) -> tuple[bool, str]:
    page_id = str(tokens["facebook_page_id"])
    access_token = str(tokens["facebook_access_token"])

    url = f"{GRAPH_API_BASE}/{page_id}/videos"
    mime = guess_mime_name(filename)

    try:
        files = {"source": (filename, content, mime)}
        data = {"description": caption, "access_token": access_token}
        r = requests.post(url, data=data, files=files, timeout=600)

        if r.status_code in (200, 201):
            return True, r.text
        return False, f"HTTP {r.status_code}: {r.text[:2000]}"
    except Exception as exc:
        return False, f"Exception: {exc}"

def scan_and_publish_once(tokens: dict):
    if not GITHUB_TOKEN:
        die("GITHUB_TOKEN is missing (required to read/write GitHub outbox + processed).", 2)

    items = gh_list_dir(OUTBOX_DIR)

    media = []
    for it in items:
        if it.get("type") != "file":
            continue
        name = it.get("name") or ""
        if is_supported_name(name):
            media.append(it)

    media.sort(key=lambda x: (x.get("name") or "").lower())

    if not media:
        logger.info("No media found in GitHub outbox: %s/", OUTBOX_DIR)
        return

    for it in media:
        name = it.get("name")
        path = it.get("path")
        sha = it.get("sha")

        if not name or not path:
            continue

        logger.info("Found in GitHub outbox: %s", name)

        content, dl_sha, _ = gh_download_file_bytes(path)
        if not content:
            logger.warning("Skipping (cannot download): %s (sha=%s dl_sha=%s)", path, sha, dl_sha)
            continue

        caption = FB_CAPTION

        if is_video_name(name):
            logger.info("Detected VIDEO. Publishing to Facebook...")
            ok, msg = publish_video(tokens, name, content, caption)
        else:
            logger.info("Detected IMAGE. Publishing to Facebook...")
            ok, msg = publish_photo(tokens, name, content, caption)

        if ok:
            logger.info("Published successfully: %s", name)

            dst_path = f"{PROCESSED_DIR}/{name}"
            ok_put, put_resp = gh_put_file(dst_path, content, f"fb-publisher: processed {name}")
            if not ok_put:
                logger.error("Failed to write processed: %s | %s", dst_path, put_resp[:300])
                continue

            ok_del, del_resp = gh_delete_file(path, f"fb-publisher: remove {name} from outbox", sha=sha or dl_sha)
            if not ok_del:
                logger.error("Processed uploaded but delete failed: %s | %s", path, del_resp[:300])
                continue

            logger.info("Moved on GitHub: %s -> %s", path, dst_path)
        else:
            logger.error("Publish failed for %s | %s", name, msg)


def main():
    logger.info(
        "Watching GitHub outbox: %s/%s (branch=%s) dir=%s/",
        REPO_OWNER,
        REPO_NAME,
        BRANCH,
        OUTBOX_DIR,
    )
    logger.info("Processed GitHub folder: %s/", PROCESSED_DIR)
    logger.info("Polling every %s seconds", POLL_INTERVAL_SECONDS)
    logger.info("Tokens: %s", SOCIAL_TOKENS_PATH)

    try:
        tokens = load_tokens()
    except Exception as e:
        logger.error("Cannot load tokens: %s", e)
        sys.exit(2)

    while True:
        try:
            scan_and_publish_once(tokens)
        except Exception as exc:
            logger.exception("Unexpected error: %s", exc)

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()