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
from config import settings

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── App Lifespan ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    logger.info("Starting Expense Tracker...")
    db = DatabaseManager()
    await db.initialize()
    app.state.db = db
    app.state.encryption = EncryptionManager()
    app.state.handler = MessageHandler(db=db, encryption=app.state.encryption)
    logger.info("All systems ready.")
    yield
    logger.info("Shutting down Expense Tracker...")


# ─── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="WhatsApp Expense Tracker",
    description="Log expenses via WhatsApp, store encrypted, export to Excel.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint for deployment platforms."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/webhook/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    To: str = Form(default=""),
):
    """
    Twilio WhatsApp webhook endpoint.
    Receives incoming messages and returns TwiML XML responses.
    Must respond within 2 seconds; heavy work is done async.
    """
    if not Body or not From:
        raise HTTPException(status_code=400, detail="Missing Body or From fields")

    # Sanitize inputs
    message_body = Body.strip()[:500]  # Cap at 500 chars
    sender_phone = From.strip()

    logger.info("Incoming message from %s: %s", sender_phone, message_body[:80])

    try:
        twiml_response = await request.app.state.handler.handle_message(
            phone_number=sender_phone,
            message=message_body,
        )
        return PlainTextResponse(content=twiml_response, media_type="application/xml")
    except Exception as exc:
        logger.exception("Unhandled error in webhook: %s", exc)
        # Return a friendly error TwiML so the user sees something
        return PlainTextResponse(
            content=_error_twiml("Something went wrong. Please try again in a moment."),
            media_type="application/xml",
        )


@app.post("/api/report/excel")
async def generate_excel_report(
    request: Request,
    phone_number: str,
    period: str = "weekly",
):
    """
    REST endpoint to trigger Excel report generation.
    Returns the file path; extend to return file bytes for download.
    """
    from reports.excel_generator import ExcelReportGenerator

    try:
        generator = ExcelReportGenerator(
            db=request.app.state.db,
            encryption=request.app.state.encryption,
        )
        file_path = await generator.generate(
            phone_number=phone_number, period=period
        )
        return JSONResponse({"status": "success", "file": file_path})
    except Exception as exc:
        logger.exception("Report generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _error_twiml(message: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{message}</Message>
</Response>"""


# ─── Dev Entry Point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
