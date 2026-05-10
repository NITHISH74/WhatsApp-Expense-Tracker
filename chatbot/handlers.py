"""
chatbot/handlers.py
Orchestrates the 2-step conversation flow:
  Step 0: Receive message → parse → send confirmation
  Step 1: Receive yes/no → save or cancel

Commands bypass the state machine entirely.
"""

import logging
from typing import Optional

from chatbot.parser import parse_expense, detect_command
from chatbot import responses as R
from database.operations import DatabaseManager
from encryption.fernet_manager import EncryptionManager
from reports.excel_generator import ExcelReportGenerator

logger = logging.getLogger(__name__)


class MessageHandler:
    """
    Stateless handler — all conversation state is persisted in the database.
    Each call to handle_message() is fully self-contained.
    """

    def __init__(self, db: DatabaseManager, encryption: EncryptionManager):
        self._db = db
        self._enc = encryption

    async def handle_message(self, phone_number: str, message: str) -> str:
        """
        Main entry point. Returns a TwiML XML string.

        Flow:
          1. Ensure user exists in DB.
          2. Check for commands (bypass state machine).
          3. Load current conversation state.
          4. If step == "0": parse new expense → prompt confirmation.
          5. If step == "1": handle yes/no → save or cancel.
        """
        try:
            await self._db.get_or_create_user(phone_number, self._enc)
            command = detect_command(message)

            # ── Command routing ────────────────────────────────────────────
            if command == "help":
                return R.welcome_message()

            step, pending = await self._db.get_conversation_state(
                phone_number, self._enc
            )

            if command == "cancel" or (step == "1" and command == "cancel"):
                await self._db.clear_conversation_state(phone_number)
                return R.cancelled()

            if step == "1":
                return await self._handle_confirmation(
                    phone_number, message, pending, command
                )

            # ── Commands that work outside expense flow ────────────────────
            if command == "daily":
                total = await self._db.get_daily_total_approx(phone_number)
                return R.daily_summary(total)

            if command == "weekly":
                total = await self._db.get_weekly_total_approx(phone_number)
                return R.weekly_summary(total)

            if command == "report":
                return await self._trigger_report(phone_number)

            # ── Expense parsing (step 0) ───────────────────────────────────
            return await self._handle_new_expense(phone_number, message)

        except Exception as exc:
            logger.exception("Error handling message from %s: %s", phone_number, exc)
            return R.generic_error()

    # ─── Internal handlers ────────────────────────────────────────────────────

    async def _handle_new_expense(self, phone_number: str, message: str) -> str:
        """Parse message as expense and send confirmation prompt."""
        parsed = parse_expense(message)

        if parsed is None:
            return R.parse_error()

        # Store pending expense in conversation state (step 1 = awaiting confirm)
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
        self,
        phone_number: str,
        message: str,
        pending: Optional[dict],
        command: Optional[str],
    ) -> str:
        """Handle yes/no response to expense confirmation."""
        if pending is None:
            # State corruption — reset
            await self._db.clear_conversation_state(phone_number)
            return R.parse_error()

        if command == "confirm":
            # Save the expense
            expense = await self._db.save_expense(
                phone_number=phone_number,
                amount=pending["amount"],
                category=pending["category"],
                description=pending.get("description", ""),
                currency_code=pending["currency"],
                encryption=self._enc,
            )
            await self._db.clear_conversation_state(phone_number)

            # Get updated daily total (fast, uses amount_approx)
            daily_total = await self._db.get_daily_total_approx(phone_number)

            # Check if daily threshold exceeded
            from database.operations import DatabaseManager
            user = await self._db.get_or_create_user(phone_number, self._enc)
            response = R.expense_saved(
                amount=pending["amount"],
                currency=pending["currency"],
                category=pending["category"],
                daily_total=daily_total,
            )

            # Append spending alert if threshold exceeded
            if daily_total > user.daily_alert_threshold:
                alert = R.spending_alert(
                    daily_total=daily_total,
                    threshold=user.daily_alert_threshold,
                    currency=pending["currency"],
                )
                # Combine both messages (Twilio allows one response; include both as one message)
                combined = (
                    response.replace("</Response>", "")
                    + "\n\n"
                    + alert.replace('<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n  <Message>', "")
                    .replace("</Message>\n</Response>", "")
                    + "\n</Response>"
                )
                return combined

            return response

        else:
            # Any non-confirm reply = cancel
            await self._db.clear_conversation_state(phone_number)
            return R.cancelled()

    async def _trigger_report(self, phone_number: str) -> str:
        """Generate Excel report asynchronously."""
        try:
            generator = ExcelReportGenerator(db=self._db, encryption=self._enc)
            file_path = await generator.generate(phone_number=phone_number, period="weekly")
            return R.report_ready(file_path)
        except Exception as exc:
            logger.exception("Report generation failed: %s", exc)
            return R.generic_error()
