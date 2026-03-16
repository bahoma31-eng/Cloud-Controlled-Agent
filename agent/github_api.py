"""
agent/github_api.py
~~~~~~~~~~~~~~~~~~~
Unified GitHub content API client.

All GitHub REST interactions go through the `GitHubClient` class.
This eliminates the duplicated helper functions that existed in V12
and provides consistent error handling, rate-limit awareness, and logging.
"""

import re
import time
import json
import base64
import logging
from typing import Optional, Tuple, List, Dict

import requests

from agent.config import (
    REPO_OWNER,
    REPO_NAME,
    GITHUB_TOKEN,
    AGENT_UA,
    GITHUB_API_BASE,
    OUTBOX_DIR,
    VERBOSE,
)

logger = logging.getLogger("cloud-agent.github")


class GitHubClient:
    """Stateless wrapper around the GitHub Contents API."""

    def __init__(
        self,
        owner: str = REPO_OWNER,
        repo: str = REPO_NAME,
        token: str = GITHUB_TOKEN,
    ) -> None:
        self._owner = owner
        self._repo = repo
        self._token = token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": AGENT_UA,
        }

    def _content_url(self, path: str) -> str:
        return f"{GITHUB_API_BASE}/repos/{self._owner}/{self._repo}/contents/{path}"

    @staticmethod
    def _pretty(r: requests.Response) -> str:
        try:
            return json.dumps(r.json(), ensure_ascii=False, indent=2)
        except Exception:
            return r.text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_file(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (content, sha) or (None, None) on failure."""
        logger.debug(f"GET  {path}")
        try:
            r = requests.get(self._content_url(path), headers=self._headers(), timeout=20)
            if r.status_code == 200:
                data = r.json()
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                return content, data.get("sha")
        except Exception as e:
            logger.error(f"GET {path} failed: {e}", exc_info=True)
        return None, None

    def put_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
        *,
        _retry: int = 0,
    ) -> bool:
        """Create or update a file. Returns True on success."""
        logger.debug(f"PUT  {path}  msg='{message}'")
        try:
            url = self._content_url(path)
            r_old = requests.get(url, headers=self._headers(), timeout=20)
            sha = r_old.json().get("sha") if r_old.status_code == 200 else None

            payload: Dict = {
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha

            r = requests.put(url, headers=self._headers(), json=payload, timeout=30)

            # Rate-limit / conflict retries (max 2 extra attempts)
            if r.status_code == 429 and _retry < 2:
                logger.warning("Rate-limited by GitHub — waiting 30 s")
                time.sleep(30)
                return self.put_file(path, content, message, branch, _retry=_retry + 1)
            if r.status_code == 409 and _retry < 2:
                logger.warning("Conflict (409) — retrying in 2 s")
                time.sleep(2)
                return self.put_file(path, content, message, branch, _retry=_retry + 1)

            if VERBOSE:
                print(f"  [GitHub PUT] {r.status_code} {r.reason}")
                print(f"  {self._pretty(r)}")

            return r.status_code in (200, 201)

        except Exception as e:
            logger.error(f"PUT {path} failed: {e}", exc_info=True)
            return False

    def delete_file(
        self, path: str, message: str, branch: str = "main"
    ) -> bool:
        """Delete a file. Returns True on success."""
        logger.debug(f"DEL  {path}")
        try:
            url = self._content_url(path)
            r_old = requests.get(url, headers=self._headers(), timeout=20)
            if r_old.status_code != 200:
                return False
            sha = r_old.json().get("sha")
            payload = {"message": message, "sha": sha, "branch": branch}
            r = requests.delete(url, headers=self._headers(), json=payload, timeout=20)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"DEL {path} failed: {e}", exc_info=True)
            return False

    def list_directory(self, path: str = "") -> List[Dict]:
        """List files/dirs at *path*. Returns list of {name, path, type}."""
        logger.debug(f"LIST {path or '(root)'}")
        try:
            r = requests.get(self._content_url(path), headers=self._headers(), timeout=20)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return [
                        {"name": item["name"], "path": item["path"], "type": item["type"]}
                        for item in data
                    ]
        except Exception as e:
            logger.error(f"LIST {path} failed: {e}", exc_info=True)
        return []

    # ------------------------------------------------------------------
    # Outbox helpers
    # ------------------------------------------------------------------
    def list_outbox_files(self) -> List[Dict]:
        """Return outbox .txt files sorted by embedded timestamp."""
        try:
            r = requests.get(
                self._content_url(OUTBOX_DIR), headers=self._headers(), timeout=20
            )
            if r.status_code == 200:
                files = [
                    f
                    for f in r.json()
                    if f.get("type") == "file" and f.get("name", "").endswith(".txt")
                ]
                _ts = re.compile(r"log(\d+)")
                files.sort(key=lambda x: int(m.group(1)) if (m := _ts.search(x.get("name", ""))) else 0)
                return files
        except Exception:
            pass
        return []

    def read_latest_report(self) -> Optional[Tuple[str, str]]:
        """Return (filename, content) of the most recent outbox report."""
        files = self.list_outbox_files()
        if not files:
            return None
        latest = files[-1]
        content, _ = self.get_file(latest["path"])
        if content is not None:
            return (latest["name"], content)
        return None


# ------------------------------------------------------------------
# Injected library code for Worker subprocesses
# ------------------------------------------------------------------
def build_remote_libs() -> str:
    """Return the helper code injected into Worker Python scripts.

    Uses the SAME GitHubClient logic but in standalone form so that
    subprocesses don't need the *agent* package installed.
    """
    return f"""
import requests, base64, json, os, time
from datetime import datetime

REPO_OWNER = "{REPO_OWNER}"
REPO_NAME = "{REPO_NAME}"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "{GITHUB_TOKEN}")

def _gh_headers():
    return {{
        "Authorization": f"token GITHUB_TOKEN",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Agent-Worker-Subprocess"
    }}

def _gh_url(path):
    return f"https://api.github.com/repos/REPO_OWNER/REPO_NAME/contents/path"

def get_file_content(path):
    url = _gh_url(path)
    r = requests.get(url, headers=_gh_headers(), timeout=20)
    if r.status_code == 200:
        data = r.json()
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace"), data.get("sha")
    return None, None

def put_file_content(path, content, message, branch="main"):
    url = _gh_url(path)
    r_old = requests.get(url, headers=_gh_headers(), timeout=20)
    sha = r_old.json().get("sha") if r_old.status_code == 200 else None
    payload = 
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    
    if sha: payload["sha"] = sha
    r = requests.put(url, headers=_gh_headers(), json=payload, timeout=20)
    return r.status_code in (200, 201)

def delete_file_content(path, message, branch="main"):
    url = _gh_url(path)
    r_old = requests.get(url, headers=_gh_headers(), timeout=20)
    if r_old.status_code != 200: return False
    sha = r_old.json().get("sha")
    payload = "message": message, "sha": sha, "branch": branch
    r = requests.delete(url, headers=_gh_headers(), json=payload, timeout=20)
    return r.status_code == 200

def list_github_directory(path=""):
    url = _gh_url(path)
    r = requests.get(url, headers=_gh_headers(), timeout=20)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list):
            return ["name": i["name"], "path": i["path"], "type": i["type"] for i in data]
    return []
"""
