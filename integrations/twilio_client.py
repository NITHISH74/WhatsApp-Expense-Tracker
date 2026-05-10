"""
integrations/twilio_client.py
Outbound WhatsApp messaging via Twilio.
Used for proactive notifications (spending alerts, scheduled summaries).
Inbound messages are handled via the /webhook/whatsapp endpoint (TwiML).
"""

import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class TwilioWhatsAppClient:
    """
    Wraps Twilio REST client for sending outbound WhatsApp messages.
    Credentials are loaded exclusively from environment variables.
    """

    def __init__(self):
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.warning(
                "Twilio credentials not configured. "
                "Outbound messages will be logged but not sent."
            )
            self._client = None
        else:
            try:
                from twilio.rest import Client
                self._client = Client(
                    settings.twilio_account_sid,
                    settings.twilio_auth_token,
                )
                logger.info("Twilio client initialized.")
            except ImportError:
                logger.error("twilio package not installed. Run: pip install twilio")
                self._client = None

    async def send_message(
        self,
        to_number: str,
        body: str,
        from_number: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send an outbound WhatsApp message.

        Args:
            to_number:   Recipient phone number (e.g., "whatsapp:+1234567890").
            body:        Message text.
            from_number: Sender WhatsApp number (defaults to configured sandbox).

        Returns:
            Twilio message SID on success, None on failure.
        """
        sender = from_number or settings.twilio_whatsapp_number
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        if self._client is None:
            logger.info("[DRY RUN] Would send to %s: %s", to_number, body[:80])
            return None

        try:
            msg = self._client.messages.create(
                from_=sender,
                to=to_number,
                body=body,
            )
            logger.info("Message sent: SID=%s to=%s", msg.sid, to_number)
            return msg.sid
        except Exception as exc:
            logger.exception("Failed to send WhatsApp message: %s", exc)
            return None

    async def send_weekly_summaries(self, users: list[dict], db, encryption) -> None:
        """
        Scheduled job: send weekly spending summaries to all active users.
        Call this from a cron job or APScheduler task.

        Args:
            users:      List of user dicts with 'phone_number' keys.
            db:         DatabaseManager instance.
            encryption: EncryptionManager instance.
        """
        from reports.excel_generator import ExcelReportGenerator

        generator = ExcelReportGenerator(db=db, encryption=encryption)
        for user in users:
            phone = user.get("phone_number")
            if not phone:
                continue
            try:
                total = await db.get_weekly_total_approx(phone)
                report_path = await generator.generate(phone, period="weekly")
                body = (
                    f"📊 Weekly Expense Summary\n"
                    f"Total: {total:.2f}\n"
                    f"Report: {report_path}\n\n"
                    f"Reply 'daily' or 'weekly' for quick totals."
                )
                await self.send_message(to_number=phone, body=body)
            except Exception as exc:
                logger.exception("Failed weekly summary for %s: %s", phone[:8], exc)
