# 💸 WhatsApp Expense Tracker

A production-ready WhatsApp chatbot for logging expenses, storing them encrypted, and generating Excel analytics reports — deployable for free on Render or Railway.

---

## Architecture Overview

```
User (WhatsApp)
    │
    ▼ HTTPS POST
┌─────────────────────────────────────────────────────┐
│  FastAPI  (main.py)                                  │
│  POST /webhook/whatsapp  ←── Twilio sends here       │
│  GET  /health                                        │
│  POST /api/report/excel                              │
└────────────┬────────────────────────────────────────┘
             │
    ┌────────▼────────┐
    │  MessageHandler  │  ← chatbot/handlers.py
    │  (2-step state)  │
    └──┬──────────┬───┘
       │          │
  ┌────▼──┐  ┌────▼──────────────┐
  │Parser │  │ DatabaseManager   │
  │       │  │ (SQLite + WAL)    │
  └───────┘  └──────┬────────────┘
                    │ Fernet AES-128
             ┌──────▼────────────┐
             │  EncryptionManager │
             └───────────────────┘
                    │
             ┌──────▼────────────┐
             │  ExcelGenerator   │
             │  (openpyxl)       │
             └───────────────────┘
```

---

## Project Structure

```
expense_tracker/
├── main.py                  # FastAPI app, webhook route
├── config.py                # Pydantic settings from env vars
├── requirements.txt
├── .env.example             # Copy → .env with real credentials
├── render.yaml              # Render free-tier deploy config
├── Procfile                 # Railway/Heroku deploy
│
├── chatbot/
│   ├── parser.py            # Natural-language expense parsing
│   ├── responses.py         # TwiML message templates
│   └── handlers.py          # 2-step conversation orchestrator
│
├── database/
│   ├── models.py            # SQLAlchemy ORM (User, Expense, ConversationState)
│   └── operations.py        # Async CRUD + conversation state management
│
├── encryption/
│   └── fernet_manager.py    # Fernet AES-128 encrypt/decrypt
│
├── reports/
│   └── excel_generator.py   # 4-sheet Excel workbooks with charts
│
├── integrations/
│   └── twilio_client.py     # Outbound WhatsApp messages
│
└── tests/
    ├── conftest.py
    ├── test_parser.py
    └── test_encryption.py
```

---

## Quick Start (Local)

### 1. Prerequisites
- Python 3.9+
- [ngrok](https://ngrok.com/download) (for local Twilio webhook)
- A [Twilio account](https://www.twilio.com/try-twilio) (free trial)

### 2. Clone and install

```bash
git clone <your-repo-url>
cd expense_tracker
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Generate encryption key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy the output — this is your FERNET_KEY
```

> ⚠️ **Save this key safely.** If you lose it, all stored expense data becomes unrecoverable.

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your real values:
#   TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, FERNET_KEY
```

### 5. Run the server

```bash
uvicorn main:app --reload --port 8000
```

### 6. Expose with ngrok

```bash
ngrok http 8000
# Copy the https://xxxx.ngrok.io URL
```

### 7. Configure Twilio WhatsApp Sandbox

1. Go to [Twilio Console → Messaging → Try it out → Send a WhatsApp message](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
2. Follow the sandbox join instructions (send a join code from your phone)
3. In **Sandbox Settings**, set:
   - **When a message comes in**: `https://xxxx.ngrok.io/webhook/whatsapp`
   - Method: `POST`
4. Save.

### 8. Test it!

Send WhatsApp messages to the Twilio sandbox number:
```
Coffee 5 USD
→ Bot confirms → Reply "yes"
→ Expense saved!

report
→ Generates weekly Excel file
```

---

## Supported Message Formats

| Message | Amount | Currency | Category |
|---------|--------|----------|----------|
| `Coffee 5 USD` | 5.00 | USD | Food & Dining |
| `Groceries 50` | 50.00 | USD | Groceries |
| `Uber ride 12.50 CAD` | 12.50 | CAD | Transport |
| `₹500 electricity bill` | 500.00 | INR | Utilities |
| `$25 lunch` | 25.00 | USD | Food & Dining |
| `Doctor visit 80 EUR` | 80.00 | EUR | Health |
| `Netflix 15 USD` | 15.00 | USD | Entertainment |

## Commands

| Command | Action |
|---------|--------|
| `help` / `hi` / `hello` | Show help menu |
| `daily` / `today` | Today's spending total |
| `weekly` / `this week` | 7-day spending total |
| `report` / `export` | Generate Excel report |
| `yes` / `confirm` | Confirm pending expense |
| `no` / `cancel` | Cancel pending expense |

---

## WhatsApp Conversation Flow

```
User: "Coffee 5 USD"
         │
         ▼
    [Parse expense]
    amount=5.0, currency=USD,
    category=Food & Dining, confidence=high
         │
         ▼
Bot: "Got it! Logging:
      💰 5.00 USD
      🏷 Food & Dining
      📝 Coffee
      Reply yes to confirm..."
         │
    ┌────┴─────┐
   yes         no/cancel
    │               │
    ▼               ▼
[Save to DB]   [Clear state]
[Encrypt]           │
    │          Bot: "❌ Cancelled"
    ▼
Bot: "✅ Saved! 5.00 USD → Food & Dining
      Today's total: 12.50 USD"
    │
    ▼ (if daily total > threshold)
Bot: "⚠️ Spending Alert! You've exceeded
      your daily limit of 100 USD."
```

---

## Database Schema

### `users` table

| Column | Type | Encrypted | Description |
|--------|------|-----------|-------------|
| `phone_hash` | TEXT PK | ❌ | SHA-256 of phone number |
| `phone_encrypted` | TEXT | ✅ | Encrypted phone number |
| `created_at` | DATETIME | ❌ | Account creation time |
| `preferences_encrypted` | TEXT | ✅ | JSON user preferences |
| `daily_alert_threshold` | FLOAT | ❌ | Daily spend limit (USD) |
| `weekly_alert_threshold` | FLOAT | ❌ | Weekly spend limit |

### `expenses` table

| Column | Type | Encrypted | Description |
|--------|------|-----------|-------------|
| `id` | TEXT PK | ❌ | UUID v4 |
| `user_phone_hash` | TEXT | ❌ | FK → users.phone_hash |
| `currency_code` | TEXT | ❌ | ISO 4217 (USD, INR…) |
| `created_at` | DATETIME | ❌ | Timestamp (indexed) |
| `amount_approx` | FLOAT | ❌ | Rounded to nearest 10 (for alerts) |
| `amount_enc` | TEXT | ✅ | Exact amount (Fernet) |
| `category_enc` | TEXT | ✅ | Category string (Fernet) |
| `description_enc` | TEXT | ✅ | Free-text note (Fernet) |

**Indexes**: `ix_expenses_user_date` on `(user_phone_hash, created_at)` for fast date-range queries.

### `conversation_states` table

| Column | Type | Encrypted | Description |
|--------|------|-----------|-------------|
| `phone_hash` | TEXT PK | ❌ | FK → users.phone_hash |
| `step` | TEXT | ❌ | "0" = idle, "1" = awaiting confirm |
| `pending_data_enc` | TEXT | ✅ | Encrypted JSON of pending expense |
| `updated_at` | DATETIME | ❌ | Auto-expires after 5 minutes |

---

## Excel Report Sheets

**Sheet 1 — Expense Log**: All expenses in date order with full decrypted details.

**Sheet 2 — By Category**: Category totals, percentage of spend, transaction count + embedded pie chart.

**Sheet 3 — Daily Trend**: Per-day spending totals + bar chart.

**Sheet 4 — Summary**: Key stats (total, average, top category, largest expense).

---

## Deployment (Render Free Tier)

1. Push code to GitHub.
2. Go to [render.com](https://render.com) → **New Web Service** → connect repo.
3. Render auto-detects `render.yaml`. Review settings.
4. Add environment variables in the Render dashboard (never in `render.yaml`):
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `FERNET_KEY`
5. Under **Disks**, Render creates `/data` (1GB free) for SQLite persistence.
6. Update `DATABASE_URL` to: `sqlite+aiosqlite:////data/expenses.db`
7. Deploy. Copy the `https://your-app.onrender.com` URL.
8. Update Twilio sandbox webhook to: `https://your-app.onrender.com/webhook/whatsapp`

> **SQLite persistence on Render**: Free tier VMs restart, wiping non-disk storage. The `render.yaml` mounts a persistent 1GB disk at `/data`. Point `DATABASE_URL` and `DB_FILE_PATH` there.

---

## Security

- All PII encrypted with Fernet AES-128 before any DB write.
- Phone numbers stored only as SHA-256 hashes (pseudonymous).
- `amount_approx` (rounded to nearest 10) stored plaintext only for alert threshold checks — exact amounts always encrypted.
- Encryption key stored only in environment variables.
- Conversation states auto-expire after 5 minutes.
- Input sanitized and capped at 500 characters.

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Future Scalability

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-user | ✅ Ready | `user_phone_hash` as PK in all tables |
| AI categorization | 🔧 Hook ready | Replace `_infer_category()` with LLM API call |
| OCR receipt scanning | 🔧 Module slot | Add `integrations/ocr_client.py` |
| Siri Shortcuts | 🔧 Endpoints ready | `/api/expense` POST accepts same format |
| Android SMS parser | 🔧 Architecture | Add background job consumer |
| Scheduled summaries | 🔧 Ready | `TwilioWhatsAppClient.send_weekly_summaries()` |

---

## Troubleshooting

**"FERNET_KEY not set"**: Add the key to your `.env` file. Generate with the command in step 3.

**Twilio not receiving messages**: Check ngrok is running and the webhook URL in Twilio console matches.

**"Database locked"**: SQLite WAL mode is enabled by default. Ensure only one write process at a time in production (single Render instance).

**Excel report empty**: No expenses found for the period. Log at least one expense first.
