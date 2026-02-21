"""
execution/telegram_send_digest.py

Formats and sends per-group digest messages to a Telegram chat.
Handles message chunking for Telegram's 4096-char limit and
retries with exponential backoff on transient failures.
"""

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from config.settings import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
MAX_MESSAGE_LENGTH = 4096
MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds

# ── Phone-number safety net ───────────────────────────────────────────


def _scrub_phone_numbers(text: str) -> str:
    """
    Remove phone numbers from text before sending to Telegram.
    This is a last-resort safety net — upstream code should already
    filter phone-heavy content, but this ensures zero leakage.
    """
    if not text:
        return text
    # Pattern: +CC followed by digits/spaces/dashes (international phone format)
    scrubbed = re.sub(r"\+?\d[\d\s\-\(\)]{7,}\d", "[redacted]", text)
    # If scrubbing removed >40% of the content, the text was mostly phone numbers
    if len(scrubbed.replace("[redacted]", "").strip()) < len(text) * 0.4:
        return "[phone numbers redacted]"
    return scrubbed


# ── Public API ────────────────────────────────────────────────────────


def send_digest(
    telegram_chat_id: str,
    digests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Send digest messages to a Telegram chat.

    Parameters
    ----------
    telegram_chat_id : str
        Target Telegram chat.
    digests : list[dict]
        Per-group digest objects from summarize_groups.summarize().

    Returns
    -------
    list[dict]
        [{group_id, message_ids: [...], status: "sent"|"failed"}]
    """
    results: list[dict[str, Any]] = []

    # Header message
    header = _format_header(digests)
    _send_message(telegram_chat_id, header)

    for digest in digests:
        formatted = _format_digest(digest)
        chunks = _chunk_text(formatted, MAX_MESSAGE_LENGTH)
        msg_ids: list[int] = []
        status = "sent"

        for chunk in chunks:
            msg_id = _send_message(telegram_chat_id, chunk)
            if msg_id:
                msg_ids.append(msg_id)
            else:
                status = "failed"

        results.append({
            "group_id": digest["group_id"],
            "message_ids": msg_ids,
            "status": status,
        })

    return results


# ── Formatting ────────────────────────────────────────────────────────


def _format_header(digests: list[dict[str, Any]]) -> str:
    """Create the header message with clean timestamp."""
    groups_count = len(digests)
    total_msgs = sum(d["stats"]["relevant_msgs"] for d in digests)

    # Clean timestamp: date | HH:MM (local time, UTC+3)
    now = datetime.now(timezone(timedelta(hours=3)))
    ts = now.strftime("%Y-%m-%d | %H:%M")

    return (
        "📋 *Al-Furat University Digest*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {ts}\n"
        f"👥 Groups: {groups_count}\n"
        f"💬 Messages: {total_msgs}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )


def _format_digest(digest: dict[str, Any]) -> str:
    """Format a single group digest — English headings, Arabic body."""
    lines: list[str] = []

    lines.append(f"📌 *{_scrub_phone_numbers(digest['group_name'])}*")
    lines.append(
        f"📊 Messages: {digest['stats']['relevant_msgs']}  •  "
        f"Senders: {digest['stats']['senders']}"
    )
    lines.append("")

    # Summary
    if digest.get("summary_bullets"):
        lines.append("📝 *Summary:*")
        for bullet in digest["summary_bullets"]:
            lines.append(f"  🔹 {_scrub_phone_numbers(bullet)}")
        lines.append("")

    # Announcements
    if digest.get("announcements"):
        lines.append("📢 *Announcements:*")
        for ann in digest["announcements"]:
            date_part = f" 🗓 {ann['date']}" if ann.get("date") else ""
            lines.append(
                f"  🔔 {_scrub_phone_numbers(ann['title'])}{date_part}\n"
                f"      ↳ {_scrub_phone_numbers(ann.get('details', ''))}"
            )
        lines.append("")

    # Action items
    if digest.get("action_items"):
        lines.append("⚡ *Action Items:*")
        for item in digest["action_items"]:
            lines.append(f"  ✅ {_scrub_phone_numbers(item)}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


# ── Sending ───────────────────────────────────────────────────────────


def _chunk_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks that fit within Telegram's limit."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at the last newline before limit
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def _send_message(chat_id: str, text: str) -> int | None:
    """
    Send a single Telegram message with retries and exponential backoff.

    Returns the message_id on success, None on failure.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(f"{TELEGRAM_API}/sendMessage", json=payload)

            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", BACKOFF_BASE)
                logger.warning("Rate limited, retrying in %ds", retry_after)
                time.sleep(retry_after)
                continue

            resp.raise_for_status()
            return resp.json().get("result", {}).get("message_id")

        except Exception as exc:
            wait = BACKOFF_BASE ** attempt
            logger.error(
                "Send failed (attempt %d/%d): %s — retrying in %ds",
                attempt, MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)

    logger.error("All retries exhausted for chat %s", chat_id)
    return None
