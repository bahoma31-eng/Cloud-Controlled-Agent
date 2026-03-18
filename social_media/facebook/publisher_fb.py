
import os
import time
import shutil
import logging
from pathlib import Path
import requests

# =========================
# Configuration
# =========================
PAGE_ID = "104244552728514"
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()

WATCH_DIR = Path("media-pipeline/output")
PROCESSED_DIR = Path("media-pipeline/processed")

POLL_INTERVAL_SECONDS = 20
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

GRAPH_API_VERSION = "v20.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("facebook-auto-poster")


def ensure_directories():
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def is_supported_image(file_path: Path) -> bool:
    return file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def wait_until_file_is_stable(file_path: Path, checks: int = 3, delay: float = 1.0) -> bool:
    """
    Prevents uploading partially written files.
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


def post_image_to_facebook(image_path: Path) -> tuple[bool, str]:
    """
    Publishes an image to the Facebook Page feed.
    Returns: (success, result_message)
    """
    url = f"{GRAPH_API_BASE}/{PAGE_ID}/photos"

    with image_path.open("rb") as image_file:
        files = {
            "source": (image_path.name, image_file, "application/octet-stream")
        }
        data = {
            "access_token": PAGE_ACCESS_TOKEN,
            "published": "true"
        }

        response = requests.post(url, files=files, data=data, timeout=120)

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if response.status_code == 200 and "id" in payload:
        return True, payload["id"]

    return False, f"HTTP {response.status_code}: {payload}"


def move_to_processed(image_path: Path):
    destination = PROCESSED_DIR / image_path.name

    if destination.exists():
        stem = image_path.stem
        suffix = image_path.suffix
        timestamp = int(time.time())
        destination = PROCESSED_DIR / f"{stem}_{timestamp}{suffix}"

    shutil.move(str(image_path), str(destination))
    return destination


def scan_and_publish_once():
    images = sorted(
        [p for p in WATCH_DIR.iterdir() if is_supported_image(p)],
        key=lambda p: p.stat().st_mtime
    )

    if not images:
        logger.info("No images found in %s", WATCH_DIR)
        return

    for image_path in images:
        logger.info("Found image: %s", image_path.name)

        if not wait_until_file_is_stable(image_path):
            logger.warning("Skipping unstable file: %s", image_path.name)
            continue

        logger.info("Publishing image to Facebook page...")
        success, result = post_image_to_facebook(image_path)

        if success:
            logger.info("Published successfully. Facebook post/photo id: %s", result)
            moved_path = move_to_processed(image_path)
            logger.info("Moved to processed: %s", moved_path)
        else:
            logger.error("Failed to publish %s | %s", image_path.name, result)


def main():
    if not PAGE_ACCESS_TOKEN:
        raise RuntimeError(
            "Missing FB_PAGE_ACCESS_TOKEN environment variable."
        )

    ensure_directories()
    logger.info("Watching folder: %s", WATCH_DIR)
    logger.info("Processed folder: %s", PROCESSED_DIR)
    logger.info("Polling every %s seconds", POLL_INTERVAL_SECONDS)

    while True:
        try:
            scan_and_publish_once()
        except Exception as exc:
            logger.exception("Unexpected error: %s", exc)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
