"""
orchestration/digest_pipeline.py — Layer 2

Full pipeline: parse command → fetch → filter → summarize → send → update state.
Handles retries for transient failures and saves artifacts for debug.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    DEFAULT_TIME_WINDOW,
    UNIVERSITY_KEYWORDS,
    WHATSAPP_GROUP_MAP,
)
from execution.filter_university_messages import filter_messages
from execution.state_update_last_processed import get_last_processed, update_state
from execution.summarize_groups import summarize
from execution.telegram_send_digest import send_digest
from execution.whatsapp_fetch_messages import (
    FetchError,
    SessionExpiredError,
    fetch_messages,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DIGESTS_DIR = _PROJECT_ROOT / ".tmp" / "digests"


# ── Public API ────────────────────────────────────────────────────────


def run_digest(command_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Execute the full digest pipeline.

    Parameters
    ----------
    command_payload : dict
        {
          "request_id": str,
          "telegram_chat_id": str,
          "command": str,
          "time_window": "since_last" | "24h" | "custom",
          "start_time": optional ISO-8601,
          "end_time": optional ISO-8601,
          "groups_scope": "all" | "mapped_only" | "list",
          "groups_list": optional list[str],
        }

    Returns
    -------
    dict  {"status": "success"|"error", "details": ...}
    """
    request_id = command_payload.get("request_id", str(uuid.uuid4()))
    chat_id = command_payload["telegram_chat_id"]

    try:
        # 1 — Parse time window
        time_window = _resolve_time_window(command_payload)
        logger.info("Digest %s — window: %s", request_id, time_window)

        # 2 — Resolve scope
        groups_scope = command_payload.get("groups_scope", "all")
        groups_list = command_payload.get("groups_list")

        # 3 — Fetch messages
        logger.info("Fetching WhatsApp messages…")
        raw_groups = fetch_messages(time_window, groups_scope, groups_list)

        # 4 — Filter by keywords (from the 50 fetched messages)
        logger.info("Filtering %d groups by keywords…", len(raw_groups))
        filtered = filter_messages(raw_groups, UNIVERSITY_KEYWORDS)

        # Remove groups with zero keyword-matched messages
        filtered = [g for g in filtered if g["relevant_count"] > 0]

        if not filtered:
            from execution.telegram_send_digest import _send_message

            _send_message(
                chat_id,
                "ℹ️ No relevant messages found matching keywords in the selected window.",
            )
            return {"status": "success", "details": "no_relevant_messages"}

        # 5 — Summarize filtered messages only
        logger.info("Generating summaries via OpenRouter…")
        digests = summarize(filtered)

        # 6 — Send to Telegram
        logger.info("Sending digest to Telegram…")
        send_results = send_digest(chat_id, digests)

        # 7 — Update state (only after successful sends)
        for digest in digests:
            end_ts = digest["time_window"].get("end")
            if end_ts:
                update_state(digest["group_id"], end_ts)

        # Save artifact for debug / reproducibility
        _save_artifact(request_id, {
            "request_id": request_id,
            "time_window": time_window,
            "digests": digests,
            "send_results": send_results,
        })

        return {"status": "success", "details": send_results}

    except SessionExpiredError:
        logger.error("WhatsApp session expired")
        from execution.telegram_send_digest import _send_message

        _send_message(
            chat_id,
            "⚠️ WhatsApp Web session expired. Please re-run and scan the QR code.",
        )
        return {"status": "error", "details": "session_expired"}

    except FetchError as exc:
        logger.error("Fetch error: %s", exc)
        from execution.telegram_send_digest import _send_message

        _send_message(chat_id, f"❌ Failed to fetch WhatsApp messages: {exc}")
        return {"status": "error", "details": str(exc)}

    except Exception as exc:
        logger.exception("Unexpected pipeline error")
        from execution.telegram_send_digest import _send_message

        _send_message(chat_id, f"❌ Digest pipeline error: {exc}")
        return {"status": "error", "details": str(exc)}


# ── Internals ─────────────────────────────────────────────────────────


def _resolve_time_window(payload: dict[str, Any]) -> dict[str, str]:
    """
    Convert the command payload into an explicit {start, end} time window.
    """
    mode = payload.get("time_window", DEFAULT_TIME_WINDOW)
    now = datetime.now(timezone.utc)

    if mode == "custom":
        return {
            "start": payload["start_time"],
            "end": payload["end_time"],
        }

    if mode == "since_last":
        # Use the earliest last-processed timestamp across target groups
        scope = payload.get("groups_scope", "all")
        group_ids = (
            payload.get("groups_list", [])
            if scope == "list"
            else list(WHATSAPP_GROUP_MAP.keys())
        )
        last_timestamps = [
            get_last_processed(gid) for gid in group_ids
        ]
        valid = [ts for ts in last_timestamps if ts]
        start = min(valid) if valid else (now - timedelta(hours=24)).isoformat()
        return {"start": start, "end": now.isoformat()}

    # Default: "24h" or any numeric-hour shorthand
    hours = 24
    if mode.endswith("h"):
        try:
            hours = int(mode[:-1])
        except ValueError:
            pass
    return {
        "start": (now - timedelta(hours=hours)).isoformat(),
        "end": now.isoformat(),
    }


def _save_artifact(request_id: str, data: dict[str, Any]) -> None:
    """Persist digest artifact for reproducibility / debugging."""
    _DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _DIGESTS_DIR / f"{request_id}.json"
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.info("Artifact saved: %s", path)
    except Exception as exc:
        logger.warning("Could not save artifact: %s", exc)
