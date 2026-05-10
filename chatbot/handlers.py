"""
chatbot/handlers.py
2-step conversation flow with Google Sheets sync on every save.
"""

import logging
from typing import Optional

from chatbot.parser import parse_expense, detect_command
from chatbot import responses as R
from database.operations import DatabaseManager
from encryption.fernet_manager import EncryptionManager

logger = logging.getLogger(__name__)


class MessageHandler:

    def __init__(self, db: DatabaseManager, encryption: EncryptionManager, sheets=None):
        self._db = db
        self._enc = encryption
        self._sheets = sheets  # GoogleSheetsClient or None

    async def handle_message(self, phone_number: str, message: str) -> str:
        try:
            await self._db.get_or_create_user(phone_number, self._enc)
            command = detect_command(message)

            if command == "help":
                return R.welcome_message()

            step, pending = await self._db.get_conversation_state(phone_number, self._enc)

            if command == "cancel":
                await self._db.clear_conversation_state(phone_number)
                return R.cancelled()

            if step == "1":
                return await self._handle_confirmation(phone_number, message, pending, command)

            if command == "daily":
                total = await self._db.get_daily_total_approx(phone_number)
                return R.daily_summary(total)

            if command == "weekly":
                total = await self._db.get_weekly_total_approx(phone_number)
                return R.weekly_summary(total)

            if command == "report":
                return await self._handle_report(phone_number)

            return await self._handle_new_expense(phone_number, message)

        except Exception as exc:
            logger.exception("Error handling message from %s: %s", phone_number, exc)
            return R.generic_error()

    async def _handle_new_expense(self, phone_number: str, message: str) -> str:
        parsed = parse_expense(message)
        if parsed is None:
            return R.parse_error()

        pending_data = {
            "amount": parsed.amount,
            "currency": parsed.currency,
            "category": parsed.category,
            "description": parsed.description,
        }
        await self._db.set_conversation_state(
            phone_number, step="1", pending_data=pending_data, encryption=self._enc
        )
        return R.confirmation_prompt(
            amount=parsed.amount,
            currency=parsed.currency,
            category=parsed.category,
            description=parsed.description,
        )

    async def _handle_confirmation(
        self, phone_number: str, message: str, pending: Optional[dict], command: Optional[str]
    ) -> str:
        if pending is None:
            await self._db.clear_conversation_state(phone_number)
            return R.parse_error()

        if command == "confirm":
            # Save to SQLite
            await self._db.save_expense(
                phone_number=phone_number,
                amount=pending["amount"],
                category=pending["category"],
                description=pending.get("description", ""),
                currency_code=pending["currency"],
                encryption=self._enc,
            )
            await self._db.clear_conversation_state(phone_number)

            # Sync to Google Sheets (silent fail — never crashes the bot)
            sheet_synced = False
            if self._sheets and self._sheets.is_configured():
                sheet_synced = await self._sheets.append_expense(
                    amount=pending["amount"],
                    currency=pending["currency"],
                    category=pending["category"],
                    description=pending.get("description", ""),
                    phone_number=phone_number,
                )

            daily_total = await self._db.get_daily_total_approx(phone_number)
            user = await self._db.get_or_create_user(phone_number, self._enc)

            return R.expense_saved(
                amount=pending["amount"],
                currency=pending["currency"],
                category=pending["category"],
                daily_total=daily_total,
                sheet_synced=sheet_synced,
                sheet_url=await self._sheets.get_sheet_url() if sheet_synced else None,
            )
        else:
            await self._db.clear_conversation_state(phone_number)
            return R.cancelled()

    async def _handle_report(self, phone_number: str) -> str:
        """Return Google Sheet link if configured, otherwise explain how to access."""
        if self._sheets and self._sheets.is_configured():
            url = await self._sheets.get_sheet_url()
            return R.report_sheet_link(url)
        else:
            return R.report_no_sheet()
