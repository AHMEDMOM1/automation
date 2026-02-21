"""
bot.py — Telegram Bot Entry Point

Registers the /furat_digest command with an interactive checkbox UI
for selecting which WhatsApp groups to summarize.
"""

import logging
import re
import uuid
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import (
    TELEGRAM_BOT_TOKEN,
    WHATSAPP_GROUP_NAMES,
)
from orchestration.digest_pipeline import run_digest

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-35s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot")
logging.getLogger("httpx").setLevel(logging.WARNING)  # suppress polling noise

# ── In-memory session state (chat_id → set of selected group names) ──

_selections: dict[str, set[str]] = {}
_pending_args: dict[str, dict] = {}  # chat_id → parsed time args

# ── Command parsing ───────────────────────────────────────────────────

_CUSTOM_RANGE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*->\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})"
)


def _parse_args(args: list[str]) -> dict:
    """Parse /furat_digest arguments into a partial command payload."""
    raw = " ".join(args).strip()

    if not raw:
        return {"time_window": "24h"}

    m = _CUSTOM_RANGE_RE.search(raw)
    if m:
        return {
            "time_window": "custom",
            "start_time": m.group(1).replace(" ", "T") + ":00",
            "end_time": m.group(2).replace(" ", "T") + ":00",
        }

    if raw == "since_last":
        return {"time_window": "since_last"}

    if raw.endswith("h") and raw[:-1].isdigit():
        return {"time_window": raw}

    return {"time_window": "24h"}


# ── Inline keyboard helpers ──────────────────────────────────────────


def _build_keyboard(chat_id: str) -> InlineKeyboardMarkup:
    """Build the checkbox keyboard for group selection."""
    selected = _selections.get(chat_id, set())
    buttons = []

    for idx, group_name in enumerate(WHATSAPP_GROUP_NAMES):
        check = "+" if group_name in selected else "-"
        buttons.append([
            InlineKeyboardButton(
                f"[{check}] {group_name}",
                callback_data=f"g{idx}",
            )
        ])

    # Select All / Deselect All row
    buttons.append([
        InlineKeyboardButton("Select All", callback_data="sa"),
        InlineKeyboardButton("Deselect All", callback_data="da"),
    ])

    # Confirm / Cancel row
    buttons.append([
        InlineKeyboardButton("Confirm", callback_data="ok"),
        InlineKeyboardButton("Cancel", callback_data="no"),
    ])

    return InlineKeyboardMarkup(buttons)


# ── Handlers ──────────────────────────────────────────────────────────


async def furat_digest_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /furat_digest — show group selection UI."""
    chat_id = str(update.effective_chat.id)

    # Parse time args and store for later
    parsed = _parse_args(context.args or [])
    _pending_args[chat_id] = parsed

    # Initialize with all groups selected by default
    _selections[chat_id] = set(WHATSAPP_GROUP_NAMES)

    try:
        keyboard = _build_keyboard(chat_id)
        await update.message.reply_text(
            "Select groups to summarize:\n\n"
            "Tap a group to toggle.\n"
            "Press Confirm when ready.",
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.error("Failed to send keyboard: %s", exc)
        await update.message.reply_text(f"Error building selection UI: {exc}")


async def callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    chat_id = str(query.message.chat_id)
    data = query.data

    # ── Toggle a single group ─────────────────────────────────────
    if data.startswith("g") and data[1:].isdigit():
        idx = int(data[1:])
        if 0 <= idx < len(WHATSAPP_GROUP_NAMES):
            group_name = WHATSAPP_GROUP_NAMES[idx]
            selected = _selections.setdefault(chat_id, set())

            if group_name in selected:
                selected.discard(group_name)
            else:
                selected.add(group_name)

        keyboard = _build_keyboard(chat_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    # ── Select All ────────────────────────────────────────────────
    if data == "sa":
        _selections[chat_id] = set(WHATSAPP_GROUP_NAMES)
        keyboard = _build_keyboard(chat_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    # ── Deselect All ──────────────────────────────────────────────
    if data == "da":
        _selections[chat_id] = set()
        keyboard = _build_keyboard(chat_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    # ── Cancel ────────────────────────────────────────────────────
    if data == "no":
        _selections.pop(chat_id, None)
        _pending_args.pop(chat_id, None)
        await query.edit_message_text("Digest cancelled.")
        return

    # ── Confirm ───────────────────────────────────────────────────
    if data == "ok":
        selected = _selections.pop(chat_id, set())
        parsed = _pending_args.pop(chat_id, {"time_window": "24h"})

        if not selected:
            await query.edit_message_text(
                "No groups selected. Use /furat_digest to try again."
            )
            return

        selected_list = [g for g in WHATSAPP_GROUP_NAMES if g in selected]
        group_names = "\n".join(f"  - {g}" for g in selected_list)
        await query.edit_message_text(
            f"Generating digest for {len(selected_list)} group(s)...\n{group_names}"
        )

        command_payload = {
            "request_id": str(uuid.uuid4()),
            "telegram_chat_id": chat_id,
            "command": "/furat_digest",
            "groups_scope": "list",
            "groups_list": selected_list,
            **parsed,
        }

        logger.info(
            "Digest request %s — %d groups: %s",
            command_payload["request_id"],
            len(selected_list),
            selected_list,
        )

        result = run_digest(command_payload)

        if result["status"] == "success":
            logger.info("Digest %s completed", command_payload["request_id"])
        else:
            logger.error("Digest %s failed: %s", command_payload["request_id"], result["details"])

        return


async def start_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "👋 مرحبًا بك في بوت التلخيص الخاص بجامعة الفرات!\n\n"
        "يمكنك الآن اختيار المجموعات التي تريد استخراج ملخصاتها مباشرة:"
    )
    # Automatically show the digest selection UI when the user presses start
    await furat_digest_handler(update, context)


async def _ignore_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Reply to non-command messages with a help message."""
    await update.message.reply_text(
        "⚠️ الأمر غير معروف.\n\n"
        "الأوامر المتاحة:\n"
        "  /start — رسالة الترحيب\n"
        "  /furat_digest — اختيار المجموعات وإنشاء الملخص\n"
        "  /furat_digest 48h — ملخص آخر 48 ساعة\n"
        "  /furat_digest since_last — منذ آخر ملخص"
    )


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    """Start the Telegram bot (long-polling mode)."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and configure it.")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("furat_digest", furat_digest_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Catch-all: reply with help for non-command messages
    app.add_handler(MessageHandler(filters.ALL, _ignore_handler))

    logger.info("🤖 Bot started — listening for /furat_digest commands…")
    app.run_polling()


if __name__ == "__main__":
    main()
