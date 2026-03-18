#!/usr/bin/env python3
import os
import sys
import json
import time
import shutil
import logging
import mimetypes
from pathlib import Path

import requests
from dotenv import load_dotenv

# =========================
# Load .env file
# =========================
load_dotenv()

# =========================
# Configuration (can be overridden by env vars)
# =========================
WATCH_DIR = Path(os.getenv("FB_WATCH_DIR", "media-pipeline/output"))
PROCESSED_DIR = Path(os.getenv("FB_PROCESSED_DIR", "media-pipeline/processed"))

POLL_INTERVAL_SECONDS = int(os.getenv("FB_POLL_INTERVAL_SECONDS", "5"))
STABILITY_CHECKS = int(os.getenv("FB_STABILITY_CHECKS", "3"))
STABILITY_DELAY_SEC = float(os.getenv("FB_STABILITY_DELAY_SEC", "1.0"))

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

# GitHub Token (read from .env)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("fb-watcher-publisher")


def ensure_directories():
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_tokens() -> dict:
    p = Path(SOCIAL_TOKENS_PATH)
    if not p.exists():
        raise FileNotFoundError(f"social_tokens.json not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Expected (from your screenshot):
    # {
    #   "facebook_access_token": "...",
    #   "facebook_page_id": "...."
    # }
    if "facebook_access_token" not in data or "facebook_page_id" not in data:
        raise ValueError("social_tokens.json must contain facebook_access_token and facebook_page_id")

    return data


def is_supported(file_path: Path) -> bool:
    if not file_path.is_file():
        return False
    ext = file_path.suffix.lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS or ext in SUPPORTED_VIDEO_EXTENSIONS


def is_video(file_path: Path) -> bool:
    return file_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def wait_until_file_is_stable(file_path: Path, checks: int = STABILITY_CHECKS, delay: float = STABILITY_DELAY_SEC) -> bool:
    """
    Prevents handling partially written files.
    """
    try:
        previous_size = -1
        for _ in range(checks):
            current_size = file_path.stat().st_size
            if current_size == previous_size and current_size > 0:
                return True
            previous_size = current_size
            time.sleep(delay)
        return file_path.stat().st_size > 0
    except FileNotFoundError:
        return False


def move_to_processed(file_path: Path) -> Path:
    destination = PROCESSED_DIR / file_path.name
    if destination.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        timestamp = int(time.time())
        destination = PROCESSED_DIR / f"{stem}_{timestamp}{suffix}"

    shutil.move(str(file_path), str(destination))
    return destination


def guess_mime(file_path: Path) -> str:
    mt, _ = mimetypes.guess_type(str(file_path))
    if mt:
        return mt
    # fallback
    if is_video(file_path):
        return "video/mp4"
    return "image/jpeg"


def publish_photo(tokens: dict, file_path: Path, caption: str) -> tuple[bool, str]:
    page_id = str(tokens["facebook_page_id"])
    access_token = str(tokens["facebook_access_token"])

    url = f"{GRAPH_API_BASE}/{page_id}/photos"
    mime = guess_mime(file_path)

    # Graph API expects multipart form-data:
    # - source: file
    # - caption: text
    # - access_token: token
    try:
        with file_path.open("rb") as f:
            files = {"source": (file_path.name, f, mime)}
            data = {"caption": caption, "access_token": access_token}
            r = requests.post(url, data=data, files=files, timeout=300)

        if r.status_code in (200, 201):
            return True, r.text
        return False, f"HTTP {r.status_code}: {r.text[:2000]}"
    except Exception as exc:
        return False, f"Exception: {exc}"


def publish_video(tokens: dict, file_path: Path, caption: str) -> tuple[bool, str]:
    page_id = str(tokens["facebook_page_id"])
    access_token = str(tokens["facebook_access_token"])

    url = f"{GRAPH_API_BASE}/{page_id}/videos"
    mime = guess_mime(file_path)

    # For /videos, use:
    # - source: file
    # - description: text
    # - access_token
    try:
        with file_path.open("rb") as f:
            files = {"source": (file_path.name, f, mime)}
            data = {"description": caption, "access_token": access_token}
            r = requests.post(url, data=data, files=files, timeout=600)

        if r.status_code in (200, 201):
            return True, r.text
        return False, f"HTTP {r.status_code}: {r.text[:2000]}"
    except Exception as exc:
        return False, f"Exception: {exc}"


def scan_and_publish_once(tokens: dict):
    items = sorted(
        [p for p in WATCH_DIR.iterdir() if is_supported(p)],
        key=lambda p: p.stat().st_mtime
    )

    if not items:
        logger.info("No media found in %s", WATCH_DIR)
        return

    for p in items:
        logger.info("Found: %s", p.name)

        if not wait_until_file_is_stable(p):
            logger.warning("Skipping unstable file: %s", p.name)
            continue

        caption = FB_CAPTION

        if is_video(p):
            logger.info("Detected VIDEO. Publishing to Facebook...")
            ok, msg = publish_video(tokens, p, caption)
        else:
            logger.info("Detected IMAGE. Publishing to Facebook...")
            ok, msg = publish_photo(tokens, p, caption)

        if ok:
            logger.info("Published successfully.")
            moved = move_to_processed(p)
            logger.info("Moved to processed: %s", moved)
        else:
            logger.error("Publish failed for %s | %s", p.name, msg)


def main():
    ensure_directories()
    
    logger.info("GitHub Token loaded: %s", "✓ Yes" if GITHUB_TOKEN else "✗ No")
    logger.info("Watching: %s", WATCH_DIR)
    logger.info("Processed: %s", PROCESSED_DIR)
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
