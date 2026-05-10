"""
integrations/sheets_client.py
Writes expenses to a Google Sheet in real-time.

Setup (one-time):
  1. Go to https://console.cloud.google.com
  2. Create a project → Enable "Google Sheets API" + "Google Drive API"
  3. Create a Service Account → download JSON key file
  4. Copy the entire JSON content into GOOGLE_SERVICE_ACCOUNT_JSON env var
  5. Create a Google Sheet → share it with the service account email
  6. Copy the Sheet ID from the URL → set GOOGLE_SHEET_ID env var

Sheet URL format:
  https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class GoogleSheetsClient:
    """
    Appends expense rows to a Google Sheet using a Service Account.
    Fails silently — sheet errors never crash the bot.
    """

    def __init__(self, service_account_json: str, sheet_id: str):
        self._sheet_id = sheet_id
        self._gc = None

        if not service_account_json or not sheet_id:
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
            logger.info("Google Sheets client initialized.")
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
        """
        Append one expense row to the Google Sheet.
        Creates the header row automatically on first use.
        Returns True on success, False on failure.
        """
        if not self._gc:
            return False

        try:
            sheet = self._gc.open_by_key(self._sheet_id).sheet1

            # Auto-create header row if sheet is empty
            if sheet.row_count == 0 or not sheet.row_values(1):
                sheet.append_row(
                    ["Date", "Time", "Category", "Description", "Amount", "Currency", "Phone (last 4)"],
                    value_input_option="USER_ENTERED",
                )

            now = created_at or datetime.utcnow()
            # Only store last 4 digits of phone for privacy
            phone_display = f"...{phone_number[-4:]}" if len(phone_number) >= 4 else "****"

            row = [
                now.strftime("%Y-%m-%d"),
                now.strftime("%H:%M"),
                category,
                description,
                amount,
                currency,
                phone_display,
            ]
            sheet.append_row(row, value_input_option="USER_ENTERED")
            logger.info("Expense appended to Google Sheet.")
            return True

        except Exception as exc:
            logger.warning("Google Sheets append failed: %s", exc)
            return False

    async def get_sheet_url(self) -> str:
        """Return the public URL of the Google Sheet."""
        return f"https://docs.google.com/spreadsheets/d/{self._sheet_id}/edit"
