# WhatsApp University Digest Bot

On-demand Telegram bot that fetches WhatsApp group messages, filters for **Al-Furat University** content, generates language-aware summaries via **Gemini**, and sends per-group digests back to Telegram.

## Architecture

```
Layer 1 — Directive     (Againt.md)         SOP + IO + edge cases
Layer 2 — Orchestration (orchestration/)    Pipeline routing & retries
Layer 3 — Execution     (execution/)        Deterministic scripts
```

## Quick Start

### 1. Prerequisites
- Python 3.11+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- WhatsApp Business Cloud API credentials
- Gemini API key

### 2. Install
```bash
pip install -r requirements.txt
```

### 3. Configure
```bash
cp .env.example .env
# Edit .env with your tokens, group map, and preferences
```

### 4. Run
```bash
python bot.py
```

### 5. Use
Send commands to your Telegram bot:

| Command | Description |
|---------|-------------|
| `/start` | Welcome message & help |
| `/furat_digest` | Last 24 hours |
| `/furat_digest 48h` | Last 48 hours |
| `/furat_digest since_last` | Since previous digest |
| `/furat_digest 2026-02-18 00:00 -> 2026-02-19 12:00` | Custom range |

## Project Structure

```
WhatsappSumm/
├── bot.py                              # Telegram bot entry point
├── config/
│   ├── __init__.py
│   └── settings.py                     # Centralised configuration
├── orchestration/
│   ├── __init__.py
│   └── digest_pipeline.py             # Layer 2 pipeline
├── execution/
│   ├── __init__.py
│   ├── whatsapp_fetch_messages.py     # Fetch from WhatsApp Cloud API
│   ├── filter_university_messages.py  # Keyword + thread filtering
│   ├── summarize_groups.py            # Gemini-powered summarization
│   ├── telegram_send_digest.py        # Send formatted digests
│   └── state_update_last_processed.py # Persistent state management
├── .env.example                        # Environment variable template
├── requirements.txt                    # Python dependencies
└── README.md                           # This file
```

## Key Features

- **Multi-language** — Summaries generated in Arabic, Turkish, or English matching the group's dominant language
- **Deduplication** — Forwarded duplicates filtered by normalised content hash
- **Thread-aware** — Replies to relevant messages are auto-included
- **Chunked sending** — Long digests split to respect Telegram's 4096-char limit
- **Retry logic** — Exponential backoff on Telegram rate limits
- **Atomic state** — Last-processed timestamps written atomically to avoid corruption
- **Debug artifacts** — Each digest run saved to `.tmp/digests/` for reproducibility
