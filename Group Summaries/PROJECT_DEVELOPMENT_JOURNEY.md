# Comprehensive Development Journey: WhatsApp University Digest Bot 🤖📚

This page documents all the stages and updates the project has gone through from its inception to the current version, providing a detailed breakdown of the tools used and the challenges faced while building the system.

---

## 🏗️ Phase 1: Planning and Core Infrastructure Setup (Architecture & Setup)
- **Goal**: Establish the foundation of the project and divide tasks to ensure clean and scalable code.
- **Detailed Steps**:
  - Built a 3-layer architecture: `Directive` (SOPs), `Orchestration` (Digest lifecycle management), and `Execution` (Isolated execution scripts).
  - Defined core requirements and set up a Python Virtual Environment.
  - Set up a `.env` file to securely store API Keys and secrets.
- **Tools and Technologies Used**: 
  - Modern Language: **Python 3.11+**
  - Environment Variable Management: **`python-dotenv`**

---

## 🌐 Phase 2: Shifting to Browser Automation (Selenium WhatsApp Migration)
- **Goal**: Fully extract messages independently using WhatsApp Web due to the limitations of linking mobile numbers via the official `WhatsApp Cloud API`.
- **Detailed Steps**:
  - Completely abandoned the official WhatsApp API in favor of a **Web Scraping** approach.
  - Developed the `whatsapp_fetch_messages.py` module to run a Headless Browser that reads messages from the WhatsApp Web interface.
  - Handled parsing DOM elements to extract message text, timestamps, and sender names (bypassing the initial issue of only capturing phone numbers).
  - Implemented session persistence to avoid scanning the QR code on every single run.
- **Tools and Technologies Used**:
  - Automation Tool: **`Selenium WebDriver`** (driving Google Chrome).
  - DOM data structuring and HTML querying techniques.

---

## 🧠 Phase 3: AI Summarization Engine (Migrating to OpenRouter)
- **Goal**: Filter and extract news related to **Al-Furat University**, then formulate a professional summary in the language appropriate for each group.
- **Detailed Steps**:
  - Designed a filtering module to remove irrelevant messages and random replies using pattern matching and text parsing techniques.
  - Initially started with the `Gemini API`, then **later migrated to the `OpenRouter` platform** to access more compatible and efficient Large Language Models (LLMs) at a lower operational cost.
  - Applied Prompt Engineering to ensure summaries are formatted in Markdown, generated separately for each group, and automatically detect the required language (Arabic, Turkish, English).
- **Tools and Technologies Used**:
  - Summarization & Rewriting: **`OpenRouter API`**.
  - HTTP Requests: **`requests`** library to communicate with AI servers.

---

## 📱 Phase 4: Control Panel and Telegram Bot Integration
- **Goal**: Provide a simple and user-friendly interface (UI) to interact with the bot and receive the generated digests.
- **Detailed Steps**:
  - Created the bot via `@BotFather` and extracted the access Token.
  - Resolved environment variable logic related to loading the `TELEGRAM_BOT_TOKEN`.
  - Solved Telegram's message length limitations: Built a custom chunking mechanism to split long digest messages that exceed Telegram's 4096-character limit.
- **Tools and Technologies Used**:
  - Core Bot Framework: **`python-telegram-bot`**.
  - Async/Await architecture to ensure the bot remains responsive during long digest generation tasks.

---

## 🎛️ Phase 5: Interactive Group Selector (Telegram Group Selector)
- **Goal**: Give the user full control to select specific groups for summarization instead of generating digests for all groups at once.
- **Detailed Steps**:
  - Modified the bot chat interface to add interactive Inline Keyboards displaying the list of available groups.
  - Added toggleable Checkboxes (✅/❌) to allow users to easily select and deselect groups.
  - Linked the "Generate Digest" confirmation button to the execution Pipeline, ensuring unselected groups are ignored during the extraction and summarization process.
- **Tools and Technologies Used**:
  - Telegram UI Elements: **`telegram.InlineKeyboardMarkup`** and **`telegram.InlineKeyboardButton`**.
  - **Callback Queries** to capture user clicks and interactions without requiring text commands.

---

## 🌍 Phase 6: Public Bot Access (Public Accessibility)
- **Goal**: Allow any user (student or professor) to use and interact with the bot without being restricted by a hardcoded User ID.
- **Detailed Steps**:
  - Removed the strict `ALLOWED_USER_IDS` conditions from the source code.
  - Re-engineered the state/data management per user to ensure it can serve multiple concurrent users without session conflicts.
- **Tools and Technologies Used**:
  - Access control via Command and Callback Handlers in `python-telegram-bot`.

---

## 📂 Final Project Structure:

\`\`\`text
WhatsappSumm/
├── bot.py                              # Main entry point for the publicly accessible Telegram bot
├── config/
│   └── settings.py                     # Centralized configurations and group mappings
├── orchestration/
│   └── digest_pipeline.py             # Pipeline connecting extraction with summarization
├── execution/
│   ├── whatsapp_fetch_messages.py     # Interactive message extraction using Selenium
│   ├── filter_university_messages.py  # Smart content filtering for university news
│   ├── summarize_groups.py            # AI Summarization via OpenRouter
│   └── telegram_send_digest.py        # System for chunking and sending long messages
├── .env                                # Environment variables (Tokens & Credentials)
└── requirements.txt                    # Python dependencies
\`\`\`

## 🛑 Key Challenges & Problems Faced

Throughout the development lifecycle, we encountered several technical hurdles that required significant architectural pivots:

1. **WhatsApp Cloud API Limitations**:
   - *Problem*: The official API prohibits easy linking of personal mobile numbers or scraping arbitrary groups without heavy business verification and template restrictions.
   - *Solution*: Abandoned the API and built a custom **Selenium-based scraper** to interact directly with WhatsApp Web, ensuring full access to all groups without business constraints.

2. **DOM Element Parsing in WhatsApp Web**:
   - *Problem*: The React-based DOM heavily obfuscates data. Initially, the scraper was only able to capture phone numbers rather than the actual sender identities or message content.
   - *Solution*: Refined the scraping logic to use robust selectors and delays, ensuring accurate extraction of message text, sender names, and timestamps.

3. **Telegram Message Length Constraints**:
   - *Problem*: Telegram throws an error when attempting to send a full consolidated digest that exceeds its strict 4096-character limit.
   - *Solution*: Developed a custom **chunking mechanism** that cleanly splits long Markdown messages at safe boundaries (like paragraphs or newlines) before sending them sequentially.

4. **Environment Variable / Token Errors**:
   - *Problem*: The application occasionally crashed with `RuntimeError: TELEGRAM_BOT_TOKEN missing in .env` during the initial deployment and testing phases.
   - *Solution*: Standardized the configuration loader, enforced validation checks on startup, and securely managed `.env` credentials using `python-dotenv`.

5. **AI Model Constraints and Flexibility**:
   - *Problem*: The initial implementation using the Gemini API presented challenges with formatting consistency across different languages and limited model flexibility.
   - *Solution*: **Migrated to the OpenRouter platform**, allowing the system to effortlessly switch to more capable or cost-effective Large Language Models (LLMs) for multilingual generation.

6. **Hardcoded User Restrictions**:
   - *Problem*: The bot was initially restricted to only respond to specific User IDs (`ALLOWED_USER_IDS`), preventing public access for the wider student body.
   - *Solution*: Removed the hardcoded restrictions and re-engineered the session management to handle concurrent requests from any public Telegram user safely.

7. **Cluttered User Experience with Bulk Summaries**:
   - *Problem*: Initially, requesting a digest summarized *all* configured groups simultaneously, leading to information overload and wasted processing time.
   - *Solution*: Built an **interactive Telegram UI** using Inline Keyboards and Checkboxes, empowering users to specifically select which groups they want to process.

---

## 🎯 Quick Journey Summary
We started with the idea of direct extraction via the official WhatsApp API and summarizing with Gemini. However, upon facing the technical limitations of the WhatsApp API, we pivoted to **Selenium** to ensure complete flexibility and data capture. Instead of forcing users to receive everything at once, we built a **fully interactive UI within Telegram** to select specific groups via inline buttons. We then replaced the summarization engine with **OpenRouter** for stronger performance and model choice. Finally, we **made the bot publicly available** so that the maximum number of Al-Furat University students could benefit from it.
