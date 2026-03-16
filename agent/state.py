"""
agent/state.py
~~~~~~~~~~~~~~
Persistent state management.

State is a small JSON document stored at ``inbox/state.json`` on GitHub.
This module owns loading, saving, and resetting that document.
"""

import json
import logging
from typing import Dict

from agent.config import STATE_PATH
from agent.github_api import GitHubClient

logger = logging.getLogger("cloud-agent.state")

# Default empty state
_EMPTY: Dict = {
    "last_task_id_sent": None,
    "last_report_name_seen": None,
}


class StateManager:
    """Read / write the agent’s persistent state on GitHub."""

    def __init__(self, gh: GitHubClient) -> None:
        self._gh = gh

    def load(self) -> Dict:
        """Load state from GitHub; return empty state on any failure."""
        raw, _ = self._gh.get_file(STATE_PATH)
        if not raw:
            return dict(_EMPTY)
        try:
            return json.loads(raw)
        except Exception:
            logger.warning("Corrupt state.json — returning empty state.")
            return dict(_EMPTY)

    def save(self, state: Dict) -> None:
        """Persist *state* to GitHub."""
        self._gh.put_file(
            STATE_PATH,
            json.dumps(state, ensure_ascii=False, indent=2),
            "Agent: update state",
        )

    def reset(self) -> Dict:
        """Reset state to empty and persist. Returns the new empty state."""
        state = dict(_EMPTY)
        self.save(state)
        return state
