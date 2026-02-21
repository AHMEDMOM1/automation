"""
execution/message_store.py

JSON-file backed message persistence layer.
Saves fetched messages to .tmp/messages/ after each successful group scrape.
Provides deduplication by content hash and retrieval by group + date range.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MESSAGES_DIR = _PROJECT_ROOT / ".tmp" / "messages"


def _slugify(name: str) -> str:
    """Convert a group name to a safe filename slug."""
    # Normalise unicode, strip non-alphanumeric (keep spaces), then replace
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "_", name.strip())
    return name[:80] or "unknown"


def _content_hash(text: str) -> str:
    """SHA-256 hash of normalised text (first 16 hex chars) for dedup."""
    cleaned = re.sub(r"\s+", " ", text.strip())
    cleaned = unicodedata.normalize("NFKC", cleaned)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]


def save_group_messages(
    group_id: str,
    group_name: str,
    messages: list[dict[str, Any]],
) -> Path:
    """
    Persist messages for a group to a JSON file.

    File: .tmp/messages/{slug}_{YYYY-MM-DD}.json

    Each call **merges** new messages with any existing ones for that
    group+date, deduplicating by content hash.

    Returns the path to the saved file.
    """
    _MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

    slug = _slugify(group_name)
    today = datetime.now().strftime("%Y-%m-%d")
    filepath = _MESSAGES_DIR / f"{slug}_{today}.json"

    # Load existing messages (if any)
    existing: list[dict[str, Any]] = []
    if filepath.exists():
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            existing = data.get("messages", [])
        except (json.JSONDecodeError, OSError):
            existing = []

    # Build set of existing content hashes for dedup
    seen_hashes: set[str] = set()
    for msg in existing:
        h = _content_hash(msg.get("text", ""))
        seen_hashes.add(h)

    # Merge new messages
    added = 0
    for msg in messages:
        h = _content_hash(msg.get("text", ""))
        if h not in seen_hashes:
            seen_hashes.add(h)
            existing.append(msg)
            added += 1

    # Atomic write
    payload = {
        "group_id": group_id,
        "group_name": group_name,
        "saved_at": datetime.now().isoformat(),
        "message_count": len(existing),
        "messages": existing,
    }

    fd, tmp_path = tempfile.mkstemp(
        dir=str(_MESSAGES_DIR), suffix=".tmp", prefix="msg_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
        if filepath.exists():
            filepath.unlink()
        os.rename(tmp_path, str(filepath))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info(
        "Persisted %d messages for '%s' (%d new) → %s",
        len(existing), group_name, added, filepath.name,
    )
    return filepath


def load_group_messages(
    group_name: str,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Load persisted messages for a group.

    Parameters
    ----------
    group_name : str
        Group name (used to find matching files by slug prefix).
    since : datetime | None
        If provided, only return messages with timestamp >= since.

    Returns
    -------
    list[dict]
        Normalised message dicts.
    """
    slug = _slugify(group_name)
    if not _MESSAGES_DIR.exists():
        return []

    all_msgs: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for filepath in sorted(_MESSAGES_DIR.glob(f"{slug}_*.json")):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            for msg in data.get("messages", []):
                h = _content_hash(msg.get("text", ""))
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                if since and msg.get("timestamp"):
                    try:
                        ts = datetime.fromisoformat(msg["timestamp"])
                        if ts < since:
                            continue
                    except ValueError:
                        pass

                all_msgs.append(msg)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s: %s", filepath, exc)

    return all_msgs
