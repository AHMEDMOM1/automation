"""
execution/whatsapp_fetch_messages.py

Fetches WhatsApp group messages via Selenium (WhatsApp Web scraping).

Opens a Chrome window with a persisted profile (QR login saved),
searches for each target group, and extracts the last N message bubbles.

Returns normalised per-group message dicts matching the directive schema.
"""

import hashlib
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from config.settings import (
    SELENIUM_PROFILE_DIR,
    SELENIUM_INITIAL_WAIT,
    SELENIUM_CHAT_WAIT,
    LAST_N_MESSAGES,
    WHATSAPP_GROUP_NAMES,
    MAX_MESSAGES_PER_GROUP,
)

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────

class SessionExpiredError(Exception):
    """WhatsApp Web session needs QR re-authentication."""


class FetchError(Exception):
    """Generic fetch failure."""


# ── Public API ────────────────────────────────────────────────────────

def fetch_messages(
    time_window: dict[str, str],
    group_scope: str = "all",
    group_list: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch messages from WhatsApp groups via Selenium (WhatsApp Web).

    Parameters
    ----------
    time_window : dict
        {"start": ISO-8601, "end": ISO-8601}  — used for metadata only;
        Selenium scrapes the last N visible messages regardless of time.
    group_scope : str
        "all" | "list"
    group_list : list[str] | None
        Explicit group names when group_scope == "list".

    Returns
    -------
    list[dict]
        One dict per group:
        {
          "group_id": "...",
          "group_name": "...",
          "messages": [ {msg_id, timestamp, sender, text, reply_to, attachments} ]
        }
    """
    target_groups = _resolve_groups(group_scope, group_list)

    if not target_groups:
        logger.warning("No target groups configured. Check WHATSAPP_GROUP_NAMES in .env")
        return []

    driver = _build_driver()
    results: list[dict[str, Any]] = []

    try:
        driver.get("https://web.whatsapp.com")
        logger.info("📱 Opening WhatsApp Web… If QR is shown, scan it.")
        _wait_for_whatsapp_ready(driver)
        logger.info("✅ WhatsApp Web ready.")

        for group_name in target_groups:
            try:
                opened_title = _open_chat_by_name(driver, group_name)
                logger.info("📂 Opened: %s", opened_title)

                raw_messages = _extract_last_messages(driver, LAST_N_MESSAGES)
                logger.info(
                    "📨 Extracted %d messages from '%s'",
                    len(raw_messages), opened_title,
                )

                # Hard cap per directive
                if len(raw_messages) > MAX_MESSAGES_PER_GROUP:
                    logger.warning(
                        "Group %s has %d messages — capping at %d",
                        opened_title, len(raw_messages), MAX_MESSAGES_PER_GROUP,
                    )
                    raw_messages = raw_messages[-MAX_MESSAGES_PER_GROUP:]

                # Normalise into the directive schema
                normalised = _normalise_messages(raw_messages, opened_title)
                logger.info(
                    "📋 Group '%s': %d raw → %d normalised messages",
                    group_name, len(raw_messages), len(normalised),
                )

                # Persist messages for durability
                try:
                    from execution.message_store import save_group_messages
                    save_group_messages(group_name, opened_title, normalised)
                except Exception as store_exc:
                    logger.warning("Could not persist messages: %s", store_exc)

                results.append({
                    "group_id": group_name,        # use name as ID for Selenium
                    "group_name": group_name,      # always use the config name (subgroup label)
                    "messages": normalised,
                })

            except Exception as exc:
                logger.error("Failed to fetch group '%s': %s", group_name, exc)
                raise FetchError(f"Error fetching group {group_name}: {exc}") from exc

    except SessionExpiredError:
        raise
    except FetchError:
        raise
    except Exception as exc:
        logger.error("Selenium error: %s", exc)
        raise FetchError(f"Selenium error: {exc}") from exc
    finally:
        time.sleep(1)
        driver.quit()
        logger.info("Browser closed.")

    return results


# ── Selenium Internals ────────────────────────────────────────────────

def _build_driver() -> webdriver.Chrome:
    """Create a Chrome WebDriver with a persisted profile."""
    options = Options()

    # ✅ Separate profile to avoid crash & keep QR login
    profile_dir = os.path.abspath(SELENIUM_PROFILE_DIR)
    options.add_argument(f"--user-data-dir={profile_dir}")

    # ✅ Options to reduce DevToolsActivePort issues on Windows
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    return driver


def _wait_for_whatsapp_ready(driver: webdriver.Chrome) -> None:
    """
    Wait until WhatsApp Web is ready enough to search.
    Sleeps for the initial wait, then retries finding the search box.
    Raises SessionExpiredError if the search box never appears.
    """
    time.sleep(SELENIUM_INITIAL_WAIT)

    for _ in range(15):
        try:
            _find_search_box(driver)
            return
        except Exception:
            time.sleep(2)

    raise SessionExpiredError(
        "WhatsApp Web not ready. If QR is shown, scan it then re-run."
    )


def _find_search_box(driver: webdriver.Chrome):
    """
    Locate the WhatsApp Web search field.
    Tries multiple XPaths as WhatsApp's DOM changes between versions.
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


def _open_chat_by_name(driver: webdriver.Chrome, chat_name: str) -> str:
    """
    Search for a chat/group by name and open it.
    Returns the opened chat title as WhatsApp shows it.
    """
    search = _find_search_box(driver)
    search.click()

    # Clear the search box robustly
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(Keys.BACKSPACE)

    search.send_keys(chat_name)
    time.sleep(2)

    # ── Click the search result instead of pressing Enter ──────────
    # Pressing Enter can open the group-info panel (member list)
    # instead of the chat conversation.  Click the matching result.
    clicked = False
    try:
        # Strategy 1: span with matching @title inside the search results
        safe_name = _escape_xpath(chat_name)
        results = driver.find_elements(
            By.XPATH,
            f'//span[@title={safe_name}]',
        )
        # Pick the result in the search-results list (not the header)
        for res in results:
            try:
                res.click()
                clicked = True
                break
            except Exception:
                continue
    except Exception:
        pass

    if not clicked:
        try:
            # Strategy 2: partial title match
            results = driver.find_elements(
                By.XPATH,
                f'//span[contains(@title, {safe_name})]',
            )
            for res in results:
                try:
                    res.click()
                    clicked = True
                    break
                except Exception:
                    continue
        except Exception:
            pass

    if not clicked:
        # Fallback: press Enter (original behaviour)
        logger.warning("Could not click search result for '%s', falling back to Enter", chat_name)
        search.send_keys(Keys.ENTER)

    time.sleep(SELENIUM_CHAT_WAIT)

    # ── Close info/member panel if it opened accidentally ─────────
    _close_info_panel_if_open(driver)

    # Read the header title of the opened chat
    # WhatsApp has multiple span[@title] in the header:
    #   - The group name (what we want)
    #   - The participants subtitle (member list — what we DON'T want)
    # Try to find the correct one by checking each candidate.
    header_title = chat_name  # safe default
    try:
        title_candidates = driver.find_elements(
            By.XPATH, '//header//span[@title]'
        )
        for candidate in title_candidates:
            title_val = candidate.get_attribute("title") or ""
            # Skip if it looks like a member/participant list
            if _looks_like_member_list(title_val):
                continue
            # Skip generic labels
            if title_val.lower() in ("announcements", "الإعلانات", "duyurular"):
                continue
            if title_val.strip():
                header_title = title_val
                break
    except Exception:
        pass

    return header_title


def _escape_xpath(s: str) -> str:
    """Safely escape a string for use in an XPath expression."""
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'
    # Contains both quotes — use concat()
    parts = s.split("'")
    return "concat(" + ", "'\''", ".join(f"'{p}'" for p in parts) + ")"


def _looks_like_member_list(text: str) -> bool:
    """
    Return True if the text looks like a WhatsApp participant/member list
    rather than a group name.  Member lists typically contain:
      - Multiple phone numbers (+90 507 505 63 05, …)
      - Comma-separated names with phone numbers
      - The word "You" / "أنت" at the end
    """
    if not text or len(text) < 5:
        return False
    # Many commas → likely a member list
    if text.count(",") >= 3:
        return True
    # Contains phone numbers
    phone_pattern = r"\+?\d[\d\s\-]{7,}"
    if len(re.findall(phone_pattern, text)) >= 2:
        return True
    # Ends with "You" or "أنت" (WhatsApp convention for member lists)
    if text.rstrip().endswith(("You", "أنت", "Sen")):
        return True
    return False


def _close_info_panel_if_open(driver: webdriver.Chrome) -> None:
    """
    Detect if the group info / member-list panel is open and close it.
    The info panel typically contains elements with 'Members' or 'participants'
    text, or a close button on the right side.
    """
    try:
        # WhatsApp Web info panel has a close button or a specific section
        info_indicators = driver.find_elements(
            By.XPATH,
            '//div[@data-testid="chat-info-drawer"]'
            '|//span[contains(text(),"Members")]'
            '|//span[contains(text(),"participants")]'
            '|//span[contains(text(),"أعضاء")]'
            '|//span[contains(text(),"Üyeler")]'
        )
        if info_indicators:
            logger.info("Info panel detected — closing with Escape")
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
    except Exception:
        pass


def _extract_last_messages(
    driver: webdriver.Chrome, n: int
) -> List[dict[str, str]]:
    """
    Extract the last n message texts from the currently open chat.

    WhatsApp Web lazy-loads messages — only visible bubbles exist in the DOM.
    We must scroll UP to load older messages before extracting.
    """
    from selenium.webdriver.common.action_chains import ActionChains

    BUBBLE_XPATH = '//div[contains(@class,"message-in") or contains(@class,"message-out")]'
    MAX_SCROLL_ATTEMPTS = 20

    # ── Step 0: Count initial bubbles ─────────────────────────────────
    bubbles = driver.find_elements(By.XPATH, BUBBLE_XPATH)
    logger.info("🔍 Initial bubble count before scrolling: %d (need %d)", len(bubbles), n)

    if len(bubbles) >= n:
        # Already have enough bubbles, no scrolling needed
        tail = bubbles[-n:]
        return _extract_from_bubbles(tail)

    # ── Step 1: Click inside the chat area to ensure focus ────────────
    try:
        if bubbles:
            # Click the first bubble to set focus inside the chat panel
            ActionChains(driver).move_to_element(bubbles[0]).click().perform()
            time.sleep(0.5)
    except Exception as e:
        logger.warning("Could not click bubble for focus: %s", e)

    # ── Step 2: Scroll up using multiple strategies ───────────────────
    prev_count = len(bubbles)
    stall_count = 0

    for attempt in range(MAX_SCROLL_ATTEMPTS):
        # Strategy A: JavaScript scroll on all scrollable containers
        scroll_worked = False
        try:
            # Find ALL scrollable divs and scroll the one containing messages
            scroll_js = """
            var panels = document.querySelectorAll('[data-testid="conversation-panel-messages"], [role="application"], [tabindex="-1"]');
            var scrolled = false;
            for (var i = 0; i < panels.length; i++) {
                var el = panels[i];
                if (el.scrollHeight > el.clientHeight && el.scrollTop > 0) {
                    el.scrollTop = Math.max(0, el.scrollTop - 2000);
                    scrolled = true;
                    break;
                }
            }
            if (!scrolled) {
                // Fallback: find any scrollable parent of message bubbles
                var msgs = document.querySelectorAll('div[class*="message-in"], div[class*="message-out"]');
                if (msgs.length > 0) {
                    var parent = msgs[0].parentElement;
                    while (parent) {
                        if (parent.scrollHeight > parent.clientHeight) {
                            parent.scrollTop = Math.max(0, parent.scrollTop - 2000);
                            scrolled = true;
                            break;
                        }
                        parent = parent.parentElement;
                    }
                }
            }
            return scrolled;
            """
            scroll_worked = driver.execute_script(scroll_js)
        except Exception as e:
            logger.debug("JS scroll failed: %s", e)

        # Strategy B: Keyboard scroll (fallback)
        if not scroll_worked:
            try:
                ActionChains(driver).send_keys(Keys.PAGE_UP).perform()
            except Exception:
                pass

        time.sleep(1.5)  # Wait for DOM to load new messages

        # Count bubbles after this scroll
        bubbles = driver.find_elements(By.XPATH, BUBBLE_XPATH)
        current_count = len(bubbles)
        logger.info(
            "📜 Scroll %d/%d: %d bubbles (was %d)",
            attempt + 1, MAX_SCROLL_ATTEMPTS, current_count, prev_count,
        )

        if current_count >= n:
            logger.info("✅ Got enough bubbles (%d >= %d)", current_count, n)
            break

        if current_count == prev_count:
            stall_count += 1
            if stall_count >= 3:
                logger.info("⚠️ No new bubbles after 3 stalls — hit chat top")
                break
        else:
            stall_count = 0

        prev_count = current_count

    # ── Step 3: Re-fetch all bubbles and take the last n ──────────────
    bubbles = driver.find_elements(By.XPATH, BUBBLE_XPATH)
    logger.info("📊 Total bubbles after all scrolling: %d", len(bubbles))
    tail = bubbles[-n:] if len(bubbles) > n else bubbles

    return _extract_from_bubbles(tail)


def _extract_from_bubbles(bubbles) -> List[dict[str, str]]:
    """Extract messages from a list of bubble elements."""
    results: List[dict[str, str]] = []
    empty_count = 0

    for bubble in bubbles:
        msg = _extract_single_message(bubble)
        if msg:
            text = msg.get("text", "").strip()
            if text:
                results.append(msg)
            else:
                empty_count += 1
        else:
            empty_count += 1

    logger.info(
        "📨 Extracted %d messages from %d bubbles (%d empty/skipped)",
        len(results), len(bubbles), empty_count,
    )
    return results


def _extract_single_message(bubble) -> dict[str, str] | None:
    """
    Extract sender, text body, and timestamp from a single message bubble.
    Uses a waterfall of selectors for resilience against DOM changes.
    """
    text_body = ""
    sender = ""
    timestamp = ""

    # ── Strategy 1: Target span.selectable-text (most reliable) ────────
    try:
        selectable_spans = bubble.find_elements(
            By.CSS_SELECTOR, "span.selectable-text"
        )
        if selectable_spans:
            # Take the first selectable-text span that has actual content
            for span in selectable_spans:
                inner = span.text.strip()
                if inner and not re.fullmatch(r"\d{1,2}:\d{2}", inner):
                    text_body = inner
                    break
    except Exception:
        pass

    # ── Strategy 2: Target div.copyable-text ───────────────────────────
    if not text_body:
        try:
            copyable_divs = bubble.find_elements(
                By.CSS_SELECTOR, "div.copyable-text"
            )
            if copyable_divs:
                for div in copyable_divs:
                    inner = div.text.strip()
                    if inner and not re.fullmatch(r"\d{1,2}:\d{2}", inner):
                        text_body = inner
                        break
        except Exception:
            pass

    # ── Strategy 3: data-testid selectors ──────────────────────────────
    if not text_body:
        try:
            text_el = bubble.find_elements(
                By.CSS_SELECTOR, '[data-testid="msg-container"] span[dir]'
            )
            parts = []
            for el in text_el:
                t = el.text.strip()
                if t and not re.fullmatch(r"\d{1,2}:\d{2}", t):
                    parts.append(t)
            if parts:
                text_body = "\n".join(parts)
        except Exception:
            pass

    # ── Strategy 4: Fallback to full bubble text with aggressive filter ─
    if not text_body:
        raw = bubble.text.strip()
        if raw:
            text_body = _clean_bubble_text(raw)

    # Skip if no text body or if it's just noise
    if not text_body or len(text_body.strip()) < 3:
        return None

    # Skip system messages ("X added Y", "You were added", etc.)
    if _is_system_message(text_body):
        return None

    # Phone-number noise filter: skip if content looks like
    # phone numbers / contact info / member lists
    if _is_phone_number_noise(text_body):
        return None

    # ── Extract sender ─────────────────────────────────────────────────
    try:
        # Group chat sender name is in a span with specific attributes
        sender_el = bubble.find_elements(
            By.CSS_SELECTOR, "span[data-testid='msg-container'] span[dir='auto']:first-child"
        )
        if not sender_el:
            sender_el = bubble.find_elements(
                By.CSS_SELECTOR, "span.x3x7a5m, span._ahxt"  # common sender class patterns
            )
        if sender_el:
            candidate = sender_el[0].text.strip()
            # Make sure the sender isn't the full message text itself
            if candidate and candidate != text_body and len(candidate) < 80:
                sender = candidate
    except Exception:
        pass

    # ── Extract timestamp ──────────────────────────────────────────────
    try:
        time_el = bubble.find_elements(
            By.CSS_SELECTOR, 'span[data-testid="msg-meta"] span'
        )
        if not time_el:
            time_el = bubble.find_elements(
                By.CSS_SELECTOR, "span.x1c4vz4f, span._ahzv"  # common timestamp patterns
            )
        if time_el:
            for te in time_el:
                t = te.text.strip()
                if re.fullmatch(r"\d{1,2}:\d{2}", t):
                    timestamp = t
                    break
    except Exception:
        pass

    return {"sender": sender, "text": text_body, "timestamp": timestamp}


def _clean_bubble_text(raw: str) -> str:
    """
    Clean raw bubble .text fallback: remove timestamps, phone-only lines,
    and other metadata noise.
    """
    lines = raw.split("\n")
    cleaned: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip pure timestamps
        if re.fullmatch(r"\d{1,2}:\d{2}", line):
            continue
        # Skip lines that are entirely phone numbers
        phone_stripped = re.sub(r"[\+\d\s\-\(\)]+", "", line).strip(" ,.")
        if len(line) > 5 and len(phone_stripped) < 3:
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def _is_phone_number_noise(text: str) -> bool:
    """
    Return True if the text content is predominantly phone numbers /
    contact identifiers — meaning this bubble is a contact card or
    member list, not a real message.
    """
    if not text:
        return True
    phone_pattern = r"\+?\d[\d\s\-\(\)]{7,}"
    phone_matches = re.findall(phone_pattern, text)
    phone_chars = sum(len(m) for m in phone_matches)
    total_chars = len(text.strip())
    if total_chars == 0:
        return True

    # Rule 1: If more than 3 phone numbers found → definitely a member list
    if len(phone_matches) > 3:
        return True

    # Rule 2: If >40% of content is phone numbers → noise
    if (phone_chars / total_chars) > 0.4:
        return True

    # Rule 3: Comma-separated number pattern (member list signature)
    # e.g. "+90 505..., +90 531..., +90 458..."
    comma_phone_pattern = r"(\+?\d[\d\s\-]{7,},\s*){2,}"
    if re.search(comma_phone_pattern, text):
        return True

    return False


def _is_system_message(text: str) -> bool:
    """
    Return True if the text looks like a WhatsApp system message
    (e.g. "X added Y", "You were added", group metadata).
    """
    system_patterns = [
        r"added\s",
        r"removed\s",
        r"left$",
        r"changed the subject",
        r"changed the group",
        r"created group",
        r"Messages and calls are end-to-end encrypted",
        r"انضم",
        r"غادر",
        r"أضاف",
        r"أزال",
        r"تم تغيير",
        r"ekledi",
        r"ayrıldı",
        r"çıkardı",
        r"grubun konusunu",
    ]
    for pat in system_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


# ── Normalisation ─────────────────────────────────────────────────────

def _resolve_groups(
    scope: str, group_list: list[str] | None
) -> list[str]:
    """Return the list of group names to scrape."""
    if scope == "list" and group_list:
        return group_list
    # "all" → use the configured group names
    return list(WHATSAPP_GROUP_NAMES)


def _normalise_messages(
    extracted: list[dict[str, str]],
    group_name: str,
) -> list[dict[str, Any]]:
    """
    Convert extracted message dicts into the directive's normalised schema.

    Parameters
    ----------
    extracted : list[dict]
        Each dict has {sender, text, timestamp} from _extract_single_message().
    group_name : str
        Used for deterministic msg_id generation.
    """
    normalised: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for msg in extracted:
        body = msg.get("text", "").strip()
        if not body:
            continue

        sender = msg.get("sender", "")
        timestamp = now_iso

        # Parse HH:MM timestamp into rough ISO format
        ts_raw = msg.get("timestamp", "")
        if ts_raw and re.fullmatch(r"\d{1,2}:\d{2}", ts_raw):
            today = datetime.now().strftime("%Y-%m-%dT")
            timestamp = today + ts_raw + ":00"
        elif ts_raw:
            timestamp = ts_raw

        # Deterministic msg_id from content + group for dedup
        hash_input = f"{group_name}:{sender}:{body}"
        msg_id = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]

        normalised.append({
            "msg_id": msg_id,
            "timestamp": timestamp,
            "sender": sender,
            "text": body,
            "reply_to": None,
            "attachments": [],
        })

    return normalised
