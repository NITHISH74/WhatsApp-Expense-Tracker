"""
chatbot/responses.py
TwiML response builders and message templates.
"""

from typing import Optional


def twiml(message: str) -> str:
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{safe}</Message>
</Response>"""


def welcome_message() -> str:
    return twiml(
        "👋 Welcome to *Expense Tracker*!\n\n"
        "Log expenses like:\n"
        "  • Coffee 5 USD\n"
        "  • Groceries 50 INR\n"
        "  • Uber 12.50 CAD\n\n"
        "Commands:\n"
        "  📊 *report* — view your Google Sheet\n"
        "  📅 *daily* — today's total\n"
        "  📆 *weekly* — this week's total\n"
        "  ❓ *help* — show this message"
    )


def confirmation_prompt(amount: float, currency: str, category: str, description: str) -> str:
    return twiml(
        f"Got it! Logging this expense:\n\n"
        f"  💰 *{amount:.2f} {currency}*\n"
        f"  🏷 Category: *{category}*\n"
        f"  📝 Note: {description}\n\n"
        f"Reply *yes* to confirm or *no* to cancel."
    )


def expense_saved(
    amount: float,
    currency: str,
    category: str,
    daily_total: float,
    sheet_synced: bool = False,
    sheet_url: Optional[str] = None,
) -> str:
    sheet_line = ""
    if sheet_synced and sheet_url:
        sheet_line = f"\n📊 Added to your Google Sheet:\n{sheet_url}"
    elif not sheet_synced:
        sheet_line = "\n💾 Saved locally (Google Sheets not connected)"

    return twiml(
        f"✅ Saved! *{amount:.2f} {currency}* → {category}\n"
        f"Today's total: *{daily_total:.2f} {currency}*"
        f"{sheet_line}"
    )


def report_sheet_link(url: str) -> str:
    return twiml(
        f"📊 *Your Expense Sheet*\n\n"
        f"Open your live Google Sheet here:\n"
        f"{url}\n\n"
        f"All your expenses are there with category breakdown and totals. "
        f"You can filter, sort, and add charts directly in Google Sheets!"
    )


def report_no_sheet() -> str:
    return twiml(
        "📊 *Google Sheets not connected yet.*\n\n"
        "To see your expenses in a live spreadsheet, ask me to help you "
        "set up Google Sheets integration.\n\n"
        "Your expenses are safely stored — nothing is lost!"
    )


def daily_summary(total: float, currency: str = "INR") -> str:
    return twiml(
        f"📅 *Today's Spending*\n"
        f"Total: *{total:.2f} {currency}*\n\n"
        f"Type *report* to open your Google Sheet."
    )


def weekly_summary(total: float, currency: str = "INR") -> str:
    return twiml(
        f"📆 *This Week's Spending*\n"
        f"Total: *{total:.2f} {currency}*\n\n"
        f"Type *report* to open your Google Sheet."
    )


def cancelled() -> str:
    return twiml("❌ Cancelled. Send a new expense anytime!")


def parse_error() -> str:
    return twiml(
        "🤔 I couldn't find an expense in that message.\n\n"
        "Try formats like:\n"
        "  • Coffee 5 USD\n"
        "  • Groceries 50 INR\n"
        "  • Uber 12.50 CAD\n\n"
        "Or type *help* for all commands."
    )


def generic_error() -> str:
    return twiml("😅 Something went wrong on our end. Please try again in a moment!")
