# ⚠️ DEPRECATED — This standalone script is superseded by the integrated
# execution layer at execution/whatsapp_fetch_messages.py.
# Kept for reference only. Use `python bot.py` to run the full pipeline.

import os
import re
import time
import json
import requests
from typing import Dict, List
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# =========================================================
# Config
# =========================================================

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_CHAT_IDS = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")

# ✅ ضع أسماء مجموعاتك هنا بالضبط كما تظهر في واتساب
GROUP_NAMES = [
    "تجمع الطلاب العرب في جامعة الفرات",
    "Yazılım طلاب الفرات",
    "FÜ-Genel Tek&Müh YAZILIM",
    "Yazılım 2. Öğretim 2. Sınıf",
    "المجموعة العامة",
    "كلية التكنولوجيا",
]


# ✅ كلمات الفلترة (عدّلها كما تريد)
KEYWORDS = [
    "doktor",
    "ders",
    "tatil",
    "katılım",
    "devamsızlık",
    "imza",
    # مرادفات شائعة (اختيارية لكنها مفيدة جدًا)
    "hoca",
    "yoklama",
]


# كم رسالة نقرأ من آخر المحادثة
LAST_N_MESSAGES = 50

# كم ننتظر بعد فتح المجموعة حتى تكتمل الرسائل
OPEN_CHAT_WAIT_SEC = 4

# كم ننتظر عند فتح واتساب ويب (QR أو تحميل)
INITIAL_LOGIN_WAIT_SEC = 15


# =========================================================
# Helpers: Telegram
# =========================================================



def telegram_send_message(chat_id: str, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in .env")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Telegram max message length is 4096 chars — split if needed
    MAX_LEN = 4096
    chunks = []
    while len(text) > MAX_LEN:
        # Try to split at a newline near the limit
        split_at = text.rfind("\n", 0, MAX_LEN)
        if split_at == -1:
            split_at = MAX_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        r = requests.post(url, json=payload, timeout=30)
        if not r.ok:
            print(f"❌ Telegram error {r.status_code}: {r.text}")
        r.raise_for_status()


# =========================================================
# Helpers: OpenRouter (LLM Summarization)
# =========================================================

def llm_summarize(group_name: str, messages: List[str]) -> str:
    """
    Summarize messages via OpenRouter (OpenAI-compatible API).
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY missing in .env")

    if not messages:
        return "لا توجد رسائل متعلقة بجامعة الفرات ضمن نافذة القراءة الحالية."

    joined = "\n".join(f"- {m}" for m in messages)

    prompt = f"""
أنت مساعد تلخيص عربي محترف.
ألّف ملخصًا مفصلًا وواضحًا لرسائل مجموعة واتساب التالية المتعلقة بالدراسة.
- حافظ على اللغة الأصلية داخل الرسائل (العربية/التركية/الإنجليزية كما هي).
- صنّف الملخص إلى أقسام واضحة.
- استخرج كل المواعيد/الأسماء/المواد/الواجبات/الامتحانات/أي تغيير مهم.
- إذا كانت الرسائل غير واضحة أو دردشة عامة، اذكر ذلك صراحةً.

اسم المجموعة: {group_name}

الرسائل:
{joined}

اكتب الناتج بهذا الشكل:
عنوان: <اسم المجموعة>
1) أهم الإعلانات والتحديثات
2) المواد والدروس (Ders) + ما المطلوب
3) الحضور والغياب (Katılım/Devamsızlık) + أي تعليمات
4) العطل (Tatil) إن وجدت
5) التواقيع (İmza) / التحقق / أي إجراءات
6) نقاط إضافية
"""

    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if not r.ok:
        print(f"❌ OpenRouter error {r.status_code}: {r.text}")
    r.raise_for_status()
    data = r.json()

    # Defensive parsing (OpenAI-compatible response format)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return "⚠️ لم أستطع استخراج ملخص من OpenRouter (صيغة استجابة غير متوقعة)."


# =========================================================
# Selenium / WhatsApp Web
# =========================================================

def build_driver() -> webdriver.Chrome:
    options = Options()

    # ✅ بروفايل منفصل لتجنب crash ولقفل الجلسة (لا تحتاج QR كل مرة)
    profile_dir = os.path.abspath("selenium-profile")
    options.add_argument(f"--user-data-dir={profile_dir}")

    # ✅ خيارات تقلل مشاكل DevToolsActivePort على ويندوز
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver


def wait_for_whatsapp_ready(driver: webdriver.Chrome) -> None:
    """
    Wait until WhatsApp Web is ready enough to search.
    We'll just sleep a bit + try to locate search box with retries.
    """
    time.sleep(INITIAL_LOGIN_WAIT_SEC)

    # retry find search box
    for _ in range(15):
        try:
            _ = find_search_box(driver)
            return
        except Exception:
            time.sleep(2)

    raise RuntimeError("WhatsApp Web not ready. If QR is shown, scan it then re-run.")


def find_search_box(driver: webdriver.Chrome):
    """
    WhatsApp web search field changes sometimes.
    We'll try multiple XPaths.
    """
    candidates = [
        '//div[@contenteditable="true"][@data-tab="3"]',
        '//div[@contenteditable="true"][@role="textbox"]',
    ]
    last_exc = None
    for xp in candidates:
        try:
            el = driver.find_element(By.XPATH, xp)
            return el
        except Exception as e:
            last_exc = e
    raise last_exc


def open_chat_by_name(driver: webdriver.Chrome, chat_name: str) -> str:
    """
    Search for a chat/group by name and open it.
    Returns the opened chat title as WhatsApp shows it.
    """
    search = find_search_box(driver)
    search.click()
    # clear robustly
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(Keys.BACKSPACE)

    search.send_keys(chat_name)
    time.sleep(2)
    search.send_keys(Keys.ENTER)

    time.sleep(OPEN_CHAT_WAIT_SEC)

    # read header title
    header_title = driver.find_element(By.XPATH, '//header//span[@title]').get_attribute("title")
    return header_title


def extract_last_messages(driver: webdriver.Chrome, n: int) -> List[str]:
    """
    Extract last n message bubbles text from the opened chat.
    We'll fetch message containers and take last n.
    """
    bubbles = driver.find_elements(
        By.XPATH,
        '//div[contains(@class,"message-in") or contains(@class,"message-out")]'
    )
    tail = bubbles[-n:] if len(bubbles) > n else bubbles

    texts: List[str] = []
    for b in tail:
        t = b.text.strip()
        if t:
            texts.append(t)

    # Optional cleanup: remove obvious noise
    cleaned = []
    for t in texts:
        # remove pure time stamps like "12:34"
        if re.fullmatch(r"\d{1,2}:\d{2}", t):
            continue
        # skip messages that are mostly phone numbers / member lists
        # (e.g. "+90 505 507 63 05, +90 531 ...")
        phone_pattern = r"\+?\d[\d\s\-]{7,}"
        non_phone_text = re.sub(phone_pattern, "", t).strip(" ,\n\r\t")
        if len(non_phone_text) < 5:
            continue
        cleaned.append(t)
    return cleaned


def filter_university_messages(messages: List[str], keywords: List[str]) -> List[str]:
    out = []
    for m in messages:
        ml = m.lower()
        if any(k.lower() in ml for k in keywords):
            out.append(m)
    return out


# =========================================================
# Main pipeline
# =========================================================

def main():
    allowed_ids = TELEGRAM_ALLOWED_CHAT_IDS
    if not allowed_ids:
        print("⚠️ TELEGRAM_ALLOWED_CHAT_IDS is empty. Set it in .env to receive messages.")
        print("   Example: TELEGRAM_ALLOWED_CHAT_IDS=123456789")
        return

    driver = build_driver()
    try:
        driver.get("https://web.whatsapp.com")
        print("📱 افتح واتساب ويب... إذا ظهر QR امسحه، ثم انتظر.")
        wait_for_whatsapp_ready(driver)
        print("✅ WhatsApp Web ready.")

        digests: Dict[str, str] = {}

        for target in GROUP_NAMES:
            try:
                opened_title = open_chat_by_name(driver, target)
                print(f"\n📂 Opened: {opened_title}")

                last_msgs = extract_last_messages(driver, LAST_N_MESSAGES)
                filtered = filter_university_messages(last_msgs, KEYWORDS)

                print(f"🧹 Filtered: {len(filtered)} messages (from last {len(last_msgs)})")

                summary = llm_summarize(opened_title, filtered)
                digests[opened_title] = summary

            except Exception as e:
                digests[target] = f"⚠️ فشل استخراج/تلخيص هذه المجموعة بسبب خطأ: {e}"

        # Send results to Telegram (to all allowed chat ids)
        final_text_parts = ["📌 *Al-Furat WhatsApp Digest*"]
        for group_name, summary in digests.items():
            final_text_parts.append("\n" + "=" * 18)
            final_text_parts.append(f"📍 {group_name}\n{summary}")

        final_text = "\n".join(final_text_parts)

        # Telegram parse_mode: keep it simple to avoid markdown errors
        for chat_id in allowed_ids:
            telegram_send_message(chat_id, final_text)

        print("\n✅ Sent digest to Telegram.")

    finally:
        # keep browser open a bit if you want to see it
        time.sleep(2)
        driver.quit()


if __name__ == "__main__":
    main()
