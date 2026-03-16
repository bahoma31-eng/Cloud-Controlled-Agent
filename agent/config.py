"""
agent/config.py
~~~~~~~~~~~~~~~
Centralized configuration loaded from environment variables.
All other modules import settings from here — no scattered os.getenv() calls.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
REPO_OWNER: str = os.getenv("REPO_OWNER", "bahoma31-eng")
REPO_NAME: str = os.getenv("REPO_NAME", "Cloud-Controlled-Agent")

# ---------------------------------------------------------------------------
# Tokens (validated at import time)
# ---------------------------------------------------------------------------
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
AI_GITHUB_TOKEN: str = os.getenv("AI_GITHUB_TOKEN", GITHUB_TOKEN)

# ---------------------------------------------------------------------------
# AI Provider
# ---------------------------------------------------------------------------
AI_PROVIDER: str = os.getenv("AI_PROVIDER", "GROQ").upper()
MODEL_ID: str = os.getenv("MODEL_ID", "llama-3.3-70b-versatile")
GITHUB_MODEL: str = os.getenv("GITHUB_MODEL", "gpt-4o")

# ---------------------------------------------------------------------------
# Agent Behavior
# ---------------------------------------------------------------------------
POLL_SECONDS: int = int(os.getenv("POLL_SECONDS", "20"))
COMMAND_TIMEOUT: int = int(os.getenv("COMMAND_TIMEOUT", "240"))
MAX_RETRIES_PER_STEP: int = int(os.getenv("MAX_RETRIES_PER_STEP", "3"))
VERBOSE: bool = os.getenv("VERBOSE", "0") in ("1", "true", "True")

# ---------------------------------------------------------------------------
# Paths (relative to repo root on GitHub)
# ---------------------------------------------------------------------------
TASK_MOTHER_PATH: str = "inbox/task_mothor.txt"
PLAN_PATH: str = "inbox/plan.md"
TASKS_PATH: str = "inbox/tasks.txt"
STATE_PATH: str = "inbox/state.json"
OUTBOX_DIR: str = "outbox"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AGENT_UA: str = "Cloud-Controlled-Agent-V13-Modular"
GITHUB_API_BASE: str = "https://api.github.com"
GITHUB_MODELS_URL: str = "https://models.inference.ai.azure.com/chat/completions"

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "app_errors.log"),
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("cloud-agent")

# ---------------------------------------------------------------------------
# Startup Validation
# ---------------------------------------------------------------------------
def validate() -> None:
    """Raise RuntimeError if required secrets are missing."""
    missing = []
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if not GROQ_API_KEY and AI_PROVIDER == "GROQ":
        missing.append("GROQ_API_KEY")
    if missing:
        for m in missing:
            logger.critical(f"Missing required environment variable: {m}")
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Please set them in your .env file."
        )
    logger.info("==================  بدء جلسة عمل جديدة  ==================")
    logger.info(f"Provider={AI_PROVIDER}  Repo={REPO_OWNER}/{REPO_NAME}  Verbose={VERBOSE}")
