"""
chatbot/responses.py
TwiML response builders and message templates.
All user-facing strings are defined here for easy localization.
"""

from typing import Optional


def twiml(message: str) -> str:
    """Wrap a message string in TwiML Response XML."""
    # Escape XML special characters
    safe = (
        message
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{safe}</Message>
</Response>"""


# ─── Welcome / Help ───────────────────────────────────────────────────────────
def welcome_message() -> str:
    return twiml(
        "👋 Welcome to *Expense Tracker*!\n\n"
        "Log expenses by typing like:\n"
        "  • Coffee 5 USD\n"
        "  • Groceries 50 INR\n"
        "  • Uber ride 12.50 CAD\n\n"
        "Commands:\n"
        "  📊 *report* — weekly Excel report\n"
        "  📅 *daily* — today's total\n"
        "  📆 *weekly* — this week's total\n"
        "  ❓ *help* — show this message\n\n"
        "Start logging! 💸"
    )


# ─── Confirmation prompt (Step 1) ─────────────────────────────────────────────
def confirmation_prompt(
    amount: float,
    currency: str,
    category: str,
    description: str,
) -> str:
    return twiml(
        f"Got it! Logging this expense:\n\n"
        f"  💰 *{amount:.2f} {currency}*\n"
        f"  🏷 Category: *{category}*\n"
        f"  📝 Note: {description}\n\n"
        f"Reply *yes* to confirm or *no* to cancel."
    )


# ─── Success ──────────────────────────────────────────────────────────────────
def expense_saved(
    amount: float,
    currency: str,
    category: str,
    daily_total: float,
) -> str:
    return twiml(
        f"✅ Saved! *{amount:.2f} {currency}* → {category}\n"
        f"Today's total: *{daily_total:.2f} {currency}*\n\n"
        f"Keep logging or type *report* for your weekly Excel."
    )


# ─── Spending alert ───────────────────────────────────────────────────────────
def spending_alert(
    daily_total: float,
    threshold: float,
    currency: str,
) -> str:
    return twiml(
        f"⚠️ *Spending Alert!*\n"
        f"Today's total *{daily_total:.2f} {currency}* has exceeded "
        f"your daily limit of {threshold:.0f} {currency}.\n\n"
        f"Review your expenses with *report*."
    )


# ─── Cancellation ────────────────────────────────────────────────────────────
def cancelled() -> str:
    return twiml("❌ Cancelled. Send a new expense anytime!")


# ─── Totals / summaries ───────────────────────────────────────────────────────
def daily_summary(total: float, currency: str = "USD") -> str:
    return twiml(
        f"📅 *Today's Spending*\n"
        f"Total: *{total:.2f} {currency}*\n\n"
        f"Type *report* for a full weekly breakdown."
    )


def weekly_summary(total: float, currency: str = "USD") -> str:
    return twiml(
        f"📆 *This Week's Spending*\n"
        f"Total: *{total:.2f} {currency}*\n\n"
        f"Type *report* to get your Excel breakdown."
    )


# ─── Report notification ──────────────────────────────────────────────────────
def report_ready(file_path: str) -> str:
    return twiml(
        f"📊 Your weekly Excel report is ready!\n"
        f"Download at: {file_path}\n\n"
        f"It includes category breakdown, daily trends, and charts."
    )


def report_generating() -> str:
    return twiml(
        "⏳ Generating your Excel report... "
        "You'll receive a download link in a moment!"
    )


# ─── Errors / edge cases ──────────────────────────────────────────────────────
def parse_error() -> str:
    return twiml(
        "🤔 I couldn't find an expense in that message.\n\n"
        "Try formats like:\n"
        "  • Coffee 5 USD\n"
        "  • Groceries 50\n"
        "  • Uber 12.50 CAD\n\n"
        "Or type *help* for all commands."
    )


def generic_error() -> str:
    return twiml(
        "😅 Something went wrong on our end. Please try again in a moment!"
    )
