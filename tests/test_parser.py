"""
tests/test_parser.py
Unit tests for the expense message parser.
Run with: pytest tests/ -v
"""

import pytest
from chatbot.parser import parse_expense, detect_command, ParsedExpense


class TestParseExpense:
    """Tests for parse_expense() function."""

    def test_basic_usd(self):
        result = parse_expense("Coffee 5 USD")
        assert result is not None
        assert result.amount == 5.0
        assert result.currency == "USD"
        assert "Food" in result.category or "Dining" in result.category

    def test_decimal_amount(self):
        result = parse_expense("Uber ride 12.50 CAD")
        assert result is not None
        assert result.amount == 12.50
        assert result.currency == "CAD"
        assert result.category == "Transport"

    def test_no_currency_defaults_usd(self):
        result = parse_expense("Groceries 50")
        assert result is not None
        assert result.amount == 50.0
        assert result.currency == "USD"
        assert result.category == "Groceries"

    def test_inr_currency(self):
        result = parse_expense("electricity bill 200 INR")
        assert result is not None
        assert result.amount == 200.0
        assert result.currency == "INR"
        assert result.category == "Utilities"

    def test_rupee_symbol(self):
        result = parse_expense("₹500 groceries")
        assert result is not None
        assert result.amount == 500.0
        assert result.currency == "INR"

    def test_dollar_symbol(self):
        result = parse_expense("$25 lunch")
        assert result is not None
        assert result.amount == 25.0
        assert result.currency == "USD"

    def test_no_amount_returns_none(self):
        result = parse_expense("hello there")
        assert result is None

    def test_zero_amount_returns_none(self):
        result = parse_expense("paid 0 USD for nothing")
        assert result is None

    def test_natural_language(self):
        result = parse_expense("paid for lunch 8.75")
        assert result is not None
        assert result.amount == 8.75

    def test_category_transport(self):
        result = parse_expense("Metro ticket 2.5 GBP")
        assert result is not None
        assert result.category == "Transport"

    def test_category_health(self):
        result = parse_expense("Doctor visit 80 USD")
        assert result is not None
        assert result.category == "Health"

    def test_description_cleaned(self):
        result = parse_expense("Netflix subscription 15 USD")
        assert result is not None
        assert "Netflix" in result.description or "subscription" in result.description.lower()


class TestDetectCommand:
    """Tests for detect_command() function."""

    def test_help(self):
        assert detect_command("help") == "help"
        assert detect_command("Hello") == "help"

    def test_confirm(self):
        assert detect_command("yes") == "confirm"
        assert detect_command("Yeah, correct") == "confirm"

    def test_cancel(self):
        assert detect_command("no") == "cancel"
        assert detect_command("Cancel this") == "cancel"

    def test_report(self):
        assert detect_command("report") == "report"
        assert detect_command("export summary") == "report"

    def test_daily(self):
        assert detect_command("daily") == "daily"
        assert detect_command("show today") == "daily"

    def test_weekly(self):
        assert detect_command("weekly") == "weekly"
        assert detect_command("this week") == "weekly"

    def test_expense_not_command(self):
        assert detect_command("Coffee 5 USD") is None
        assert detect_command("Groceries 50 INR") is None
