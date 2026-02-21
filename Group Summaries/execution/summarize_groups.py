"""
execution/summarize_groups.py

Produces per-group digest objects from filtered university messages
using the OpenRouter API (OpenAI-compatible). Summaries are written
in the dominant language of each group's messages.
"""

import json
import logging
from typing import Any

import httpx

from config.settings import OPENROUTER_API_KEY, OPENROUTER_MODEL

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# ── Public API ────────────────────────────────────────────────────────


def summarize(filtered_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Generate a digest object for each group.

    Parameters
    ----------
    filtered_groups : list[dict]
        Output of filter_university_messages.filter_messages().

    Returns
    -------
    list[dict]
        Per-group digest:
        {
          "group_id", "group_name", "language",
          "time_window": {"start", "end"},
          "stats": {"relevant_msgs", "senders"},
          "summary_bullets": [...],
          "announcements": [{title, date, details}],
          "action_items": [...]
        }
    """
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set in .env")
        return [
            _error_digest(g, "OPENROUTER_API_KEY not configured")
            for g in filtered_groups
            if g["messages"]
        ]

    digests: list[dict[str, Any]] = []

    for group in filtered_groups:
        if not group["messages"]:
            continue

        digest = _summarize_single_group(group)
        digests.append(digest)

    return digests


# ── Internals ─────────────────────────────────────────────────────────

_LANGUAGE_NAMES = {"ar": "Arabic", "tr": "Turkish", "en": "English", "mixed": "Arabic"}


def _build_prompt(group: dict[str, Any]) -> str:
    """Build the summarisation prompt — English headings, Arabic body, full coverage."""
    msg_count = len(group["messages"])
    min_bullets = max(3, min(msg_count, 12))

    messages_text = "\n".join(
        f"MSG#{i+1} [{m.get('timestamp', '')}] {m.get('sender', 'Unknown')}: {m.get('text', '')}"
        for i, m in enumerate(group["messages"])
    )

    return f"""أنت مساعد تلخيص محترف متخصص بشؤون جامعة الفرات.
لخّص الرسائل التالية من مجموعة واتساب بشكل واضح ومهني.

❗ قواعد اللغة:
- اكتب محتوى الملخص باللغة العربية فقط (إذا كانت الرسائل بالتركية أو الإنجليزية، ترجمها إلى العربية)
- استخدم مفاتيح JSON بالإنجليزية كما هو موضح أدناه
- احتفظ بالأسماء الشخصية وأسماء المجموعات والمنظمات والأسماء العلم بلغتها الأصلية بدون ترجمة
  مثال: "Alev Hoca", "كلية التكنولوجيا", "Diferansiyel Denklemler" تبقى كما هي

❗❗ قواعد التغطية (إلزامي):
- يوجد أدناه {msg_count} رسالة مرقمة (MSG#1 إلى MSG#{msg_count})
- يجب أن يعكس الملخص محتوى جميع الـ {msg_count} رسائل وليس رسالة واحدة فقط
- اقرأ كل رسالة على حدة واستخرج الموضوع الرئيسي منها قبل تجميع الملخص
- لا تتجاهل أي رسالة — كل رسالة يجب أن تنعكس في الملخص
- الحد الأدنى للنقاط التلخيصية: {min_bullets} نقاط على الأقل
- صنّف المواضيع بحسب الفئة (مواد، امتحانات، حضور، إعلانات، أسئلة، إلخ)

المجموعة: {group['group_name']}
عدد الرسائل: {msg_count}

الرسائل:
{messages_text}

أجب بكائن JSON صالح فقط (بدون أقواس markdown، بدون تعليقات):
{{
  "summary_bullets": ["نقطة بالعربية 1", "نقطة بالعربية 2", ...],
  "announcements": [
    {{"title": "عنوان بالعربية", "date": "تاريخ اختياري أو null", "details": "تفاصيل بالعربية"}}
  ],
  "action_items": ["مطلوب بالعربية 1", ...]
}}

القواعد:
- {min_bullets} إلى 12 نقطة تلخيصية (كل رسالة = نقطة واحدة على الأقل)
- احتفظ بالأسماء العلم بلغتها الأصلية (لا تترجم الأسماء)
- استخرج أي إعلانات رسمية مع تواريخها
- اذكر أي مهام أو إجراءات مطلوبة من الطلاب
- إذا لم توجد إعلانات أو مهام، استخدم مصفوفات فارغة
- لا ترسل أي أرقام هواتف أو معرّفات أعضاء
"""


def _summarize_single_group(group: dict[str, Any]) -> dict[str, Any]:
    """Call OpenRouter and build the digest object for one group."""
    prompt = _build_prompt(group)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2000,
    }

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(OPENROUTER_URL, headers=headers, json=payload)

        if not resp.is_success:
            logger.error(
                "OpenRouter error %d for group %s: %s",
                resp.status_code, group["group_name"], resp.text,
            )
            # Human-readable error messages
            error_msgs = {
                401: "Invalid API key. Check OPENROUTER_API_KEY in .env",
                402: "OpenRouter credits exhausted. Add credits at openrouter.ai/credits",
                429: "Rate limit exceeded. Try again in a few minutes",
                500: "OpenRouter server error. Try again later",
            }
            msg = error_msgs.get(resp.status_code, f"API error (HTTP {resp.status_code})")
            return _error_digest(group, msg)

        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.endswith("```"):
                raw_text = raw_text[: -len("```")]
            raw_text = raw_text.strip()

        llm_result = json.loads(raw_text)

    except json.JSONDecodeError:
        logger.error("OpenRouter returned non-JSON for group %s", group["group_name"])
        llm_result = {
            "summary_bullets": ["Summary generation encountered a formatting error."],
            "announcements": [],
            "action_items": [],
        }
    except Exception as exc:
        logger.error("OpenRouter API error for group %s: %s", group["group_name"], exc)
        llm_result = {
            "summary_bullets": [f"Summary unavailable: {exc}"],
            "announcements": [],
            "action_items": [],
        }

    # Derive time window from message timestamps
    timestamps = [m.get("timestamp", "") for m in group["messages"] if m.get("timestamp")]
    time_start = min(timestamps) if timestamps else ""
    time_end = max(timestamps) if timestamps else ""

    return {
        "group_id": group["group_id"],
        "group_name": group["group_name"],
        "language": group["dominant_language"],
        "time_window": {"start": time_start, "end": time_end},
        "stats": {
            "relevant_msgs": group["relevant_count"],
            "senders": group["unique_senders"],
        },
        "summary_bullets": llm_result.get("summary_bullets", []),
        "announcements": llm_result.get("announcements", []),
        "action_items": llm_result.get("action_items", []),
    }


def _error_digest(group: dict[str, Any], error_msg: str) -> dict[str, Any]:
    """Create an error digest object when summarisation fails."""
    timestamps = [m.get("timestamp", "") for m in group["messages"] if m.get("timestamp")]
    return {
        "group_id": group["group_id"],
        "group_name": group["group_name"],
        "language": group.get("dominant_language", "en"),
        "time_window": {
            "start": min(timestamps) if timestamps else "",
            "end": max(timestamps) if timestamps else "",
        },
        "stats": {
            "relevant_msgs": group.get("relevant_count", len(group["messages"])),
            "senders": group.get("unique_senders", 0),
        },
        "summary_bullets": [f"⚠️ {error_msg}"],
        "announcements": [],
        "action_items": [],
    }
