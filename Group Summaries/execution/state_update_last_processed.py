"""
execution/state_update_last_processed.py

Manages persistent state for the last-processed timestamp per group.
Uses atomic writes to avoid corruption on crash.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from config.settings import DIGEST_STATE_STORE

logger = logging.getLogger(__name__)


def _ensure_state_file() -> Path:
    """Ensure the state file and its parent directories exist."""
    path = Path(DIGEST_STATE_STORE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}", encoding="utf-8")
    return path


def _load_state() -> dict[str, Any]:
    """Read the state file."""
    path = _ensure_state_file()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read state file, starting fresh: %s", exc)
        return {}


def _save_state(state: dict[str, Any]) -> None:
    """Atomically write the state file (write-to-temp then rename)."""
    path = _ensure_state_file()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix="state_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        # Atomic rename (on Windows this may raise if target exists,
        # so we remove first)
        if path.exists():
            path.unlink()
        os.rename(tmp_path, str(path))
    except Exception:
        # Clean up temp file on error
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ── Public API ────────────────────────────────────────────────────────


def get_last_processed(group_id: str) -> str | None:
    """
    Get the last-processed timestamp for a group.

    Returns
    -------
    str | None
        ISO-8601 timestamp, or None if the group hasn't been processed.
    """
    state = _load_state()
    return state.get(group_id, {}).get("last_processed")


def update_state(group_id: str, last_timestamp: str) -> None:
    """
    Update the last-processed timestamp for a group.

    Parameters
    ----------
    group_id : str
        WhatsApp group ID.
    last_timestamp : str
        ISO-8601 timestamp of the most recent processed message.
    """
    state = _load_state()
    state[group_id] = {"last_processed": last_timestamp}
    _save_state(state)
    logger.info("State updated for group %s: %s", group_id, last_timestamp)
