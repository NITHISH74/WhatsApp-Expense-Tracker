"""
integrations/sheets_client.py
Writes expenses to a Google Sheet in real-time.
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_sheet_id(sheet_id_or_url: str) -> str:
    """
    Accept either a raw Sheet ID or the full Google Sheets URL.
    Extracts just the ID either way.

    Full URL format:
      https://docs.google.com/spreadsheets/d/SHEET_ID/edit#gid=0
    """
    if not sheet_id_or_url:
        return ""
    # If it looks like a URL, extract the ID part
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_id_or_url)
    if match:
        return match.group(1)
    # Otherwise assume it's already a raw ID
    return sheet_id_or_url.strip()


class GoogleSheetsClient:
    """
    Appends expense rows to a Google Sheet using a Service Account.
    Fails silently — sheet errors never crash the bot.
    """

    def __init__(self, service_account_json: str, sheet_id: str):
        # Auto-extract ID from URL if full URL was pasted
        self._sheet_id = _extract_sheet_id(sheet_id)
        self._gc = None

        if not service_account_json or not self._sheet_id:
            logger.warning("Google Sheets not configured — skipping sheet writes.")
            return

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds_dict = json.loads(service_account_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            self._gc = gspread.authorize(creds)
            logger.info("Google Sheets client initialized. Sheet ID: %s", self._sheet_id)
        except Exception as exc:
            logger.warning("Google Sheets init failed: %s", exc)
            self._gc = None

    def is_configured(self) -> bool:
        return self._gc is not None

    async def append_expense(
        self,
        amount: float,
        currency: str,
        category: str,
        description: str,
        phone_number: str,
        created_at: Optional[datetime] = None,
    ) -> bool:
        """Append one expense row to the Google Sheet."""
        if not self._gc:
            return False

        try:
            sheet = self._gc.open_by_key(self._sheet_id).sheet1

            # Auto-create header if sheet is empty
            existing = sheet.get_all_values()
            if not existing:
                sheet.append_row(
                    ["Date", "Time", "Category", "Description", "Amount", "Currency"],
                    value_input_option="USER_ENTERED",
                )

            now = created_at or datetime.utcnow()
            row = [
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M"),
                category,
                description,
                amount,
                currency,
            ]
            sheet.append_row(row, value_input_option="USER_ENTERED")
            logger.info("Expense appended to Google Sheet.")
            return True

        except Exception as exc:
            logger.warning("Google Sheets append failed: %s", exc)
            return False

    async def get_sheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self._sheet_id}/edit"
