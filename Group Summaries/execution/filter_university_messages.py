"""
execution/filter_university_messages.py

Filters fetched WhatsApp messages per group, keeping only those relevant
to Al-Furat University based on keyword matching, thread context, and
deduplication rules defined in the directive.
"""

import hashlib
import logging
import re
import unicodedata
from typing import Any

from config.settings import UNIVERSITY_KEYWORDS

logger = logging.getLogger(__name__)

# ── Public API ────────────────────────────────────────────────────────


def filter_messages(
    groups_messages: list[dict[str, Any]],
    keywords_config: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Filter each group's messages for university relevance.

    Parameters
    ----------
    groups_messages : list[dict]
        Output of whatsapp_fetch_messages.fetch_messages().
    keywords_config : dict | None
        Override keyword config; defaults to settings.UNIVERSITY_KEYWORDS.

    Returns
    -------
    list[dict]
        Per-group result:
        {
          "group_id", "group_name",
          "messages": [filtered],
          "total_raw": int,
          "relevant_count": int,
          "unique_senders": int,
          "dominant_language": "ar" | "tr" | "en" | "mixed"
        }
    """
    kw = keywords_config or UNIVERSITY_KEYWORDS
    flat_keywords = _flatten_keywords(kw)
    keyword_pattern = _build_keyword_regex(flat_keywords)

    results: list[dict[str, Any]] = []

    for group in groups_messages:
        raw = group["messages"]
        relevant_ids: set[str] = set()
        seen_hashes: set[str] = set()
        filtered: list[dict[str, Any]] = []

        # Pass 1 — direct keyword matching
        for msg in raw:
            text = msg.get("text", "")
            normalised_text = _normalise_text(text)
            if keyword_pattern.search(normalised_text):
                relevant_ids.add(msg["msg_id"])

        # Pass 2 — thread-context rule (replies to relevant messages)
        changed = True
        while changed:
            changed = False
            for msg in raw:
                if msg["msg_id"] in relevant_ids:
                    continue
                if msg.get("reply_to") and msg["reply_to"] in relevant_ids:
                    relevant_ids.add(msg["msg_id"])
                    changed = True

        # Pass 3 — collect, deduplicate
        for msg in raw:
            if msg["msg_id"] not in relevant_ids:
                continue
            content_hash = _content_hash(msg.get("text", ""))
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            filtered.append(msg)

        # Language detection
        dominant_lang = _detect_dominant_language(filtered)

        unique_senders = len({m.get("sender", "") for m in filtered})

        results.append({
            "group_id": group["group_id"],
            "group_name": group["group_name"],
            "messages": filtered,
            "total_raw": len(raw),
            "relevant_count": len(filtered),
            "unique_senders": unique_senders,
            "dominant_language": dominant_lang,
        })

        logger.info(
            "Group %s: %d/%d relevant, lang=%s",
            group["group_name"], len(filtered), len(raw), dominant_lang,
        )

    return results


# ── Internals ─────────────────────────────────────────────────────────


def _flatten_keywords(kw: dict[str, list[str]]) -> list[str]:
    """Flatten multi-language keyword dict to a single list."""
    flat: list[str] = []
    for keywords in kw.values():
        flat.extend(keywords)
    return flat


def _build_keyword_regex(keywords: list[str]) -> re.Pattern:
    """Build a single compiled regex matching any keyword (case-insensitive)."""
    escaped = [re.escape(kw) for kw in keywords]
    pattern = "|".join(escaped)
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


def _normalise_text(text: str) -> str:
    """Unicode-normalise and strip for consistent matching."""
    text = unicodedata.normalize("NFKC", text)
    # Remove tatweel (Arabic kashida) for broader matching
    text = text.replace("\u0640", "")
    return text


def _content_hash(text: str) -> str:
    """
    Produce a normalised hash for deduplication of forwarded messages.
    Strips whitespace and normalises punctuation before hashing.
    """
    cleaned = re.sub(r"\s+", " ", text.strip())
    cleaned = unicodedata.normalize("NFKC", cleaned)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]


def _detect_dominant_language(messages: list[dict[str, Any]]) -> str:
    """
    Determine dominant language by Unicode code-point ratio.

    Returns "ar", "tr", "en", or "mixed".
    """
    if not messages:
        return "en"

    arabic_chars = 0
    latin_chars = 0

    for msg in messages:
        text = msg.get("text", "")
        for ch in text:
            if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F":
                arabic_chars += 1
            elif ch.isalpha():
                latin_chars += 1

    total = arabic_chars + latin_chars
    if total == 0:
        return "en"

    arabic_ratio = arabic_chars / total

    if arabic_ratio > 0.6:
        return "ar"
    elif arabic_ratio < 0.2:
        # Could be Turkish or English — simple heuristic: check for Turkish chars
        all_text = " ".join(m.get("text", "") for m in messages)
        turkish_chars = set("çğıöşüÇĞİÖŞÜ")
        if any(ch in turkish_chars for ch in all_text):
            return "tr"
        return "en"
    else:
        return "mixed"
