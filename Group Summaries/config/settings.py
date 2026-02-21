"""
config/settings.py — Centralised configuration loader.

Reads environment variables from `.env` (via python-dotenv) and exposes
all settings used across the three layers.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from project root ───────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ── Telegram ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_CHAT_IDS: list[str] = [
    cid.strip()
    for cid in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
]

# ── WhatsApp — Selenium (WhatsApp Web) ────────────────────────────────
WHATSAPP_SOURCE: str = os.getenv("WHATSAPP_SOURCE", "selenium")

# Browser profile directory (persists QR login between runs)
SELENIUM_PROFILE_DIR: str = os.getenv(
    "SELENIUM_PROFILE_DIR",
    str(_PROJECT_ROOT / "selenium-profile"),
)

# Seconds to wait for WhatsApp Web to load / QR scan
SELENIUM_INITIAL_WAIT: int = int(os.getenv("SELENIUM_INITIAL_WAIT", "15"))

# Seconds to wait after opening a group chat
SELENIUM_CHAT_WAIT: int = int(os.getenv("SELENIUM_CHAT_WAIT", "4"))

# How many messages to read from the bottom of each chat
LAST_N_MESSAGES: int = int(os.getenv("LAST_N_MESSAGES", "50"))

# ── WhatsApp Group Names (JSON array) ─────────────────────────────────
# Exact names as they appear in WhatsApp
WHATSAPP_GROUP_NAMES: list[str] = json.loads(
    os.getenv("WHATSAPP_GROUP_NAMES", "[]")
)

# ── WhatsApp Group Mapping (optional, for state tracking) ─────────────
# JSON string → dict  { group_id: friendly_name }
WHATSAPP_GROUP_MAP: dict[str, str] = json.loads(
    os.getenv("WHATSAPP_GROUP_MAP", "{}")
)

# ── Filter Keywords (flat list for quick Selenium scraping filter) ────
FILTER_KEYWORDS: list[str] = json.loads(
    os.getenv("FILTER_KEYWORDS", "[]")
)

# ── OpenRouter (LLM) ─────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

# ── Digest behaviour ─────────────────────────────────────────────────
DIGEST_STATE_STORE: Path = _PROJECT_ROOT / os.getenv(
    "DIGEST_STATE_STORE", ".tmp/state.json"
)
SEND_EMPTY_GROUPS: bool = os.getenv("SEND_EMPTY_GROUPS", "false").lower() == "true"
MAX_MESSAGES_PER_GROUP: int = int(os.getenv("MAX_MESSAGES_PER_GROUP", "500"))
DEFAULT_TIME_WINDOW: str = os.getenv("DEFAULT_TIME_WINDOW", "24h")

# ── University Keywords (multi-language) ──────────────────────────────────
UNIVERSITY_KEYWORDS: dict[str, list[str]] = {
    "ar": [
        "جامعة الفرات", "الفرات", "كلية", "امتحان", "محاضرة",
        "تسجيل", "دوام", "نتائج", "قسم", "مقرر", "جلسة",
        "دكتور", "أستاذ", "مخبر", "حرم جامعي",
        "مادة", "درس", "علامة", "درجة", "واجب", "بحث",
        "حضور", "غياب", "قاعة", "مختبر", "مشروع",
        "تخرج", "فصل", "سنة", "برنامج", "جدول",
        "طالب", "طالبة", "طلاب", "معيد", "تدريب",
    ],
    "en": [
        "Al-Furat University", "Furat University", "faculty",
        "exam", "lecture", "registration", "results",
        "lesson", "subject", "course", "class", "grade",
        "homework", "assignment", "project", "lab",
        "professor", "teacher", "attendance", "schedule",
        "semester", "midterm", "final", "campus",
    ],
    "tr": [
        "Fırat Üniversitesi", "fakülte", "sınav", "ders",
        "kayıt", "sonuçlar", "hoca", "lab", "vize", "final",
        "ödev", "derslik", "yoklama", "not", "bölüm", "müfredat",
        "devamsızlık", "staj", "başlıyor", "başlıyo", "saat",
        "proje", "öğretim", "sınıf", "akademik", "dönem",
        "geli", "gelmiş", "geliyor", "program", "öğrenci",
        "katilım", "imza", "tatil", "doktor", "asistan",
        "mezuniyet", "kampus", "kampüs", "mühendislik", "yazılım",
    ],
}
