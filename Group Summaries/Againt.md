# directives/whatsapp_university_digest_on_demand.md

## Directive: WhatsApp Group Digest → Telegram (On-Demand)

You operate within the existing 3-layer architecture:
- Layer 1: Directive (this file) defines SOP + IO + edge cases.
- Layer 2: Orchestration routes between execution scripts.
- Layer 3: Execution scripts perform deterministic work (no probabilistic business logic).

(Reference: core architecture & operating principles in AGENT.md)

---

## Goal
When the user requests it from the Telegram bot, generate and send:
- A separate summary **per WhatsApp group**
- Only for messages related to **"جامعة الفرات" / "Al-Furat University"** (or configured keywords)
- For a selected time window (default: since last digest OR last 24h)
- Preserving the **language of the messages** in each group (Arabic stays Arabic, Turkish stays Turkish, etc.)

---

## Trigger (How it starts)
This workflow is initiated **only** when the Telegram bot receives a command, e.g.:
- `/furat_digest`
- `/furat_digest 24h`
- `/furat_digest since_last`
- `/furat_digest 2026-02-18 00:00 -> 2026-02-19 12:00`

No background polling is required by default.

---

## Inputs
### Telegram Command Payload (from bot webhook)
- `request_id` (string)
- `telegram_chat_id` (string)
- `command` (string)
- Optional:
  - `time_window` (enum: `since_last`, `24h`, `custom`)
  - `start_time` / `end_time` (ISO 8601)
  - `groups_scope` (enum: `all`, `mapped_only`, `list`)
  - `groups_list` (array of group ids/names)

### Configuration (config file / env)
- `WHATSAPP_SOURCE`:
  - Option A: WhatsApp Web session (local automation)
  - Option B: WhatsApp Business Cloud API (if available)
- `WHATSAPP_GROUP_MAP`:
  - mapping: `{ group_id -> friendly_name }`
- `UNIVERSITY_KEYWORDS`:
  - Arabic: ["جامعة الفرات", "الفرات", "كلية", "امتحان", "محاضرة", "تسجيل", "دوام", "نتائج", ...]
  - English: ["Al-Furat University", "Furat University", ...]
  - Turkish (optional): ["Fırat Üniversitesi", ...]
- `DIGEST_STATE_STORE`:
  - where to store last_processed timestamps per group (e.g. `.tmp/state.json` or sqlite)

---

## Outputs
### Telegram Message(s)
Send to the requesting Telegram chat:
1) A header message: digest scope + time window + groups count
2) Then **one message per WhatsApp group** that contains:
   - Group name
   - Time window
   - Summary bullets (3–8 bullets)
   - Important announcements / dates
   - Action items (if any)
   - Source stats (message count, unique senders count)

**Language preservation requirement**
- If a group’s relevant messages are mostly Arabic → summary in Arabic
- If mostly Turkish → summary in Turkish
- If mixed → summary in the dominant language + small section "Other language notes"

### Optional: Persisted Artifact
- Save a copy in `.tmp/digests/{request_id}.json` for reproducibility/debug

---

## Deterministic Filtering Rules (University Relevance)
A WhatsApp message is considered relevant if:
- Contains any `UNIVERSITY_KEYWORDS` (case-insensitive, normalized)
- OR matches configured patterns (regex):
  - exam schedules, registration instructions, class cancellations
  - faculty/department names, campus logistics
- OR is a reply/forward chain where the parent message is relevant (thread context rule)

Exclude messages that are:
- Pure greetings / off-topic chat without university signals
- Duplicated forwards already counted (dedupe by normalized hash)

---

## Execution Scripts (Layer 3)
Before creating new logic, check `execution/` for existing scripts. If none exist, create these deterministic scripts:

1) `execution/whatsapp_fetch_messages.py`
   - Input: time window, group scope
   - Output: normalized messages JSON per group:
     ```json
     {
       "group_id": "...",
       "group_name": "...",
       "messages": [
         {
           "msg_id": "...",
           "timestamp": "...",
           "sender": "...",
           "text": "...",
           "reply_to": "optional_msg_id",
           "attachments": [{"type":"image|pdf|link", "url":"...", "caption":"..."}]
         }
       ]
     }
     ```
   - Notes:
     - If using WhatsApp Web automation: must reuse an authenticated session.
     - If using API: obey rate limits and pagination.

2) `execution/filter_university_messages.py`
   - Input: raw group messages + keyword config
   - Output: per-group filtered messages + counts + dominant language

3) `execution/summarize_groups.py`
   - Input: filtered messages per group
   - Output: per-group digest object:
     ```json
     {
       "group_id": "...",
       "group_name": "...",
       "language": "ar|tr|en|mixed",
       "time_window": {"start":"...", "end":"..."},
       "stats": {"relevant_msgs": 12, "senders": 5},
       "summary_bullets": ["...", "..."],
       "announcements": [{"title":"...", "date":"optional", "details":"..."}],
       "action_items": ["..."]
     }
     ```
   - Requirement: keep summary language aligned with dominant language of messages.
   - Deterministic formatting; no business logic in orchestration.

4) `execution/telegram_send_digest.py`
   - Input: telegram_chat_id + digest objects
   - Output: sent message ids + status
   - Must chunk long digests to fit Telegram limits.

5) `execution/state_update_last_processed.py`
   - Input: group_id + last_processed_timestamp
   - Output: persisted state update (atomic write)

---

## Orchestration (Layer 2) Steps
1) Parse Telegram command into time_window + scope
2) Load group mapping + keywords + last processed timestamps
3) Call `whatsapp_fetch_messages.py`
4) Call `filter_university_messages.py`
5) Call `summarize_groups.py`
6) Call `telegram_send_digest.py`
7) Call `state_update_last_processed.py` (only after successful send)

Orchestration must handle:
- retries for transient fetch/send failures
- fallbacks (see edge cases)
- consistent outputs for identical inputs

---

## Edge Cases & Fallbacks
1) No access / session expired (WhatsApp Web)
   - Return Telegram message: "WhatsApp session needs re-authentication"
   - Do NOT silently fail.

2) No relevant messages in a group
   - Option A: skip that group entirely
   - Option B: send: "No Al-Furat related updates in this window"
   - Use config `SEND_EMPTY_GROUPS=false` by default.

3) Attachments (PDF/image) with no text
   - If caption exists: process caption
   - Otherwise: include as "Attachment shared" without attempting OCR by default

4) Very large message volume
   - Apply deterministic window slicing:
     - hard cap: N messages per group (e.g. 500)
     - prioritize latest messages inside time window
   - Include note in digest: "Capped at 500 messages"

5) Duplicate forwards
   - Dedupe by normalized hash (strip whitespace, normalize punctuation)

6) Mixed-language group
   - Determine dominant language by character ratio / heuristic
   - Produce digest in dominant language + small "Other language notes"

7) Telegram send failures / rate limits
   - Retry with exponential backoff
   - If still failing: send a short error status message

---

## Message Formatting (Telegram)
Per group message template:

[Group: {group_name}]
Window: {start} → {end}
Stats: {relevant_msgs} msgs • {senders} senders

Summary:
- bullet 1
- bullet 2
- bullet 3

Announcements:
- {title} ({date if available}) — {details}

Action items:
- item 1
- item 2

---

## Acceptance Criteria
- Trigger works only via Telegram command (on-demand)
- Digest is sent per WhatsApp group (separate messages)
- Only university-related messages included
- Summary language follows the group’s dominant language
- State is updated only after successful Telegram send
- Deterministic, repeatable outputs for identical inputs
