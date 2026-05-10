"""
chatbot/parser.py
Parses natural-language expense messages into structured data.
Supports formats like:
  "Coffee 5 USD"
  "Groceries 50"
  "Uber ride 12.50 CAD"
  "lunch 8.75"
  "paid 200 INR for electricity"
  "electricity bill 200 inr"
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Supported currencies ────────────────────────────────────────────────────
SUPPORTED_CURRENCIES = {
    "USD", "EUR", "GBP", "CAD", "AUD", "INR", "SGD", "AED",
    "JPY", "CNY", "CHF", "MXN", "BRL", "ZAR", "NZD",
}

CURRENCY_SYMBOLS = {
    "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY",
}

# ─── Default categories (keyword → category mapping) ─────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food & Dining":    ["coffee", "lunch", "dinner", "breakfast", "restaurant", "cafe",
                          "food", "meal", "snack", "pizza", "burger", "sushi", "tea", "drink"],
    "Groceries":        ["grocery", "groceries", "supermarket", "vegetables", "fruits",
                          "walmart", "costco", "market"],
    "Transport":        ["uber", "taxi", "cab", "bus", "train", "metro", "fuel", "gas",
                          "petrol", "parking", "toll", "ride", "lyft", "ola", "auto",
                          "metro ticket", "bus ticket", "train ticket", "transit"],
    "Utilities":        ["electricity", "water", "internet", "wifi", "phone", "bill",
                          "broadband", "gas bill", "mobile"],
    "Health":           ["doctor", "medicine", "pharmacy", "hospital", "gym", "fitness",
                          "yoga", "medical"],
    "Shopping":         ["amazon", "flipkart", "clothes", "clothing", "shoes", "shopping",
                          "online", "delivery"],
    "Entertainment":    ["movie", "netflix", "spotify", "game", "concert", "ticket",
                          "subscription", "streaming"],
    "Travel":           ["hotel", "flight", "airbnb", "visa", "travel", "holiday", "trip"],
    "Education":        ["course", "book", "udemy", "tuition", "school", "college", "fee"],
    "Miscellaneous":    [],  # fallback
}


@dataclass
class ParsedExpense:
    amount: float
    currency: str
    category: str
    description: str
    raw_message: str
    confidence: float  # 0.0–1.0; low confidence → ask user to confirm


# ─── Amount extraction ────────────────────────────────────────────────────────
_AMOUNT_RE = re.compile(
    r"""
    (?:                             # optional currency symbol before amount
      (?P<sym_before>[£$€₹¥])
    )?
    (?P<amount>
      \d{1,10}                     # integer part
      (?:[.,]\d{1,2})?             # optional decimal
    )
    \s*
    (?:                             # optional currency code after amount
      (?P<code_after>[A-Z]{3})
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)

_CURRENCY_CODE_RE = re.compile(
    r"\b(" + "|".join(SUPPORTED_CURRENCIES) + r")\b",
    re.IGNORECASE,
)


def _extract_amount_and_currency(text: str) -> tuple[Optional[float], str]:
    """Extract the first valid monetary amount and currency from text."""
    # Look for explicit currency code anywhere in message
    currency = "USD"
    code_match = _CURRENCY_CODE_RE.search(text)
    if code_match:
        currency = code_match.group(1).upper()

    # Check for symbol prefix
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in text:
            currency = code
            break

    # Find amount
    for match in _AMOUNT_RE.finditer(text):
        raw = match.group("amount").replace(",", ".")
        try:
            amount = float(raw)
            if amount > 0:
                # Handle symbol before
                if match.group("sym_before"):
                    currency = CURRENCY_SYMBOLS.get(match.group("sym_before"), currency)
                return amount, currency
        except ValueError:
            continue

    return None, currency


def _infer_category(text: str) -> tuple[str, float]:
    """
    Match message text against category keyword list.
    Returns (category, confidence) where confidence reflects match strength.
    """
    lower_text = text.lower()
    best_category = "Miscellaneous"
    best_score = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower_text:
                score = len(kw)  # longer keyword = more specific = higher score
                if score > best_score:
                    best_score = score
                    best_category = category

    confidence = min(1.0, best_score / 8) if best_score > 0 else 0.3
    return best_category, confidence


def _clean_description(text: str, amount: float, currency: str, category: str) -> str:
    """
    Strip the amount and currency from the raw message to get a clean description.
    Fall back to the original message if cleaning produces garbage.
    """
    cleaned = text
    # Remove currency code
    cleaned = _CURRENCY_CODE_RE.sub("", cleaned)
    # Remove numeric amount (rough)
    cleaned = re.sub(r"\b\d+(?:[.,]\d{1,2})?\b", "", cleaned)
    # Remove known filler words
    for filler in ["paid for", "paid", "spent on", "spent", "for", "on", "my"]:
        cleaned = re.sub(rf"\b{re.escape(filler)}\b", "", cleaned, flags=re.IGNORECASE)
    # Remove currency symbols
    for sym in CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(sym, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned if len(cleaned) > 1 else text.strip()


# ─── Commands ─────────────────────────────────────────────────────────────────
COMMAND_PATTERNS = {
    "report":   re.compile(r"\b(report|summary|excel|export)\b", re.IGNORECASE),
    "weekly":   re.compile(r"\b(weekly|week|this week)\b", re.IGNORECASE),
    "daily":    re.compile(r"\b(daily|today|today's)\b", re.IGNORECASE),
    "help":     re.compile(r"\b(help|start|hi|hello|hey|commands)\b", re.IGNORECASE),
    "cancel":   re.compile(r"\b(cancel|stop|no|nope|quit)\b", re.IGNORECASE),
    "confirm":  re.compile(r"\b(yes|yeah|yep|confirm|ok|okay|sure|correct|y)\b", re.IGNORECASE),
}


def detect_command(text: str) -> Optional[str]:
    """
    Check if the message is a command rather than an expense.
    Returns command name or None.
    Priority: cancel > confirm > help > report > weekly > daily
    """
    for cmd in ["cancel", "confirm", "help", "report", "weekly", "daily"]:
        if COMMAND_PATTERNS[cmd].search(text):
            return cmd
    return None


# ─── Main parse function ──────────────────────────────────────────────────────
def parse_expense(message: str) -> Optional[ParsedExpense]:
    """
    Parse a natural-language message into a ParsedExpense.

    Returns None if no valid amount is found (not an expense message).

    Examples:
        "Coffee 5 USD"         → ParsedExpense(5.0, "USD", "Food & Dining", "Coffee")
        "Uber ride 12.50 CAD"  → ParsedExpense(12.50, "CAD", "Transport", "Uber ride")
        "hello"                → None
    """
    message = message.strip()
    amount, currency = _extract_amount_and_currency(message)

    if amount is None:
        return None

    category, confidence = _infer_category(message)
    description = _clean_description(message, amount, currency, category)

    logger.debug(
        "Parsed: amount=%.2f currency=%s category=%s confidence=%.2f desc=%r",
        amount, currency, category, confidence, description,
    )
    return ParsedExpense(
        amount=amount,
        currency=currency,
        category=category,
        description=description,
        raw_message=message,
        confidence=confidence,
    )
