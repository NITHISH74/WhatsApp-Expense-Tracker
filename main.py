"""
WhatsApp Expense Tracker - Main Application Entry Point
FastAPI async server with Twilio webhook integration
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from database.operations import DatabaseManager
from chatbot.handlers import MessageHandler
from encryption.fernet_manager import EncryptionManager
from integrations.sheets_client import GoogleSheetsClient
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Expense Tracker...")
    db = DatabaseManager()
    await db.initialize()

    encryption = EncryptionManager()
    sheets = GoogleSheetsClient(
        service_account_json=settings.google_service_account_json,
        sheet_id=settings.google_sheet_id,
    )

    app.state.db = db
    app.state.encryption = encryption
    app.state.sheets = sheets
    app.state.handler = MessageHandler(db=db, encryption=encryption, sheets=sheets)

    if sheets.is_configured():
        logger.info("Google Sheets integration active.")
    else:
        logger.info("Google Sheets not configured — expenses saved to SQLite only.")

    logger.info("All systems ready.")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="WhatsApp Expense Tracker",
    description="Log expenses via WhatsApp, store encrypted, sync to Google Sheets.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/webhook/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
):
    if not Body or not From:
        raise HTTPException(status_code=400, detail="Missing Body or From fields")

    message_body = Body.strip()[:500]
    sender_phone = From.strip()

    logger.info("Message from %s: %s", sender_phone, message_body[:80])

    try:
        twiml_response = await request.app.state.handler.handle_message(
            phone_number=sender_phone,
            message=message_body,
        )
        return PlainTextResponse(content=twiml_response, media_type="application/xml")
    except Exception as exc:
        logger.exception("Unhandled error in webhook: %s", exc)
        return PlainTextResponse(
            content=_error_twiml("Something went wrong. Please try again in a moment."),
            media_type="application/xml",
        )


def _error_twiml(message: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{message}</Message>
</Response>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
