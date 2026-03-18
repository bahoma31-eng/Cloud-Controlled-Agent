import os
import time
import shutil
import logging
import subprocess
from pathlib import Path

# =========================
# Configuration
# =========================
WATCH_DIR = Path("media-pipeline/output")
PROCESSED_DIR = Path("media-pipeline/processed")

POLL_INTERVAL_SECONDS = 5
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Path to the Facebook publisher script
FACEBOOK_PUBLISHER_SCRIPT = Path("social_media/facebook/publisher_fb.py")

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("media-bridge")


def ensure_directories():
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def is_supported_image(file_path: Path) -> bool:
    return file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def wait_until_file_is_stable(file_path: Path, checks: int = 3, delay: float = 1.0) -> bool:
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


def invoke_facebook_publisher() -> tuple[bool, str]:
    """
    Calls social_media/facebook/publisher_fb.py as a separate process.
    """
    if not FACEBOOK_PUBLISHER_SCRIPT.exists():
        return False, f"Publisher script not found: {FACEBOOK_PUBLISHER_SCRIPT}"

    try:
        result = subprocess.run(
            ["python", str(FACEBOOK_PUBLISHER_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            return True, result.stdout.strip() or "Facebook publisher completed successfully"

        error_output = (result.stderr or result.stdout).strip()
        return False, f"Publisher failed with exit code {result.returncode}: {error_output}"

    except subprocess.TimeoutExpired:
        return False, "Publisher script timed out"
    except Exception as exc:
        return False, f"Failed to invoke publisher script: {exc}"


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

        logger.info("New image detected in output. Invoking Facebook publisher...")
        success, message = invoke_facebook_publisher()

        if success:
            logger.info("Publisher completed successfully: %s", message)
            moved_path = move_to_processed(image_path)
            logger.info("Moved to processed: %s", moved_path)
        else:
            logger.error("Failed to invoke publisher for %s | %s", image_path.name, message)


def main():
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
