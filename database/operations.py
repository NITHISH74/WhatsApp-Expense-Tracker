"""
database/operations.py
Async database access layer using SQLAlchemy + aiosqlite.
All write operations encrypt sensitive fields before insertion.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func, text

from database.models import Base, User, Expense, ConversationState
from config import settings

logger = logging.getLogger(__name__)


def _hash_phone(phone_number: str) -> str:
    """SHA-256 hash of phone number — used as stable pseudonymous user key."""
    return hashlib.sha256(phone_number.encode("utf-8")).hexdigest()


def _ensure_db_directory(database_url: str) -> None:
    """
    Parse the SQLite file path from the connection URL and
    create its parent directory if it does not yet exist.

    SQLite URL formats handled:
      sqlite+aiosqlite:///./expenses.db      → relative  ./expenses.db
      sqlite+aiosqlite:////data/expenses.db  → absolute  /data/expenses.db
    """
    raw = re.sub(r"^sqlite\+aiosqlite://", "", database_url)
    # 4-slash URL  → raw starts with //  → absolute path (e.g. /data/x.db)
    # 3-slash URL  → raw starts with /   → relative path (e.g. ./x.db)
    if raw.startswith("//"):
        file_path = raw[1:]   # //data/x.db → /data/x.db
    elif raw.startswith("/"):
        file_path = raw[1:]   # /./x.db → ./x.db
    else:
        file_path = raw

    parent = Path(file_path).parent
    # Only create if it's not the current directory
    if str(parent) not in (".", ""):
        parent.mkdir(parents=True, exist_ok=True)
        logger.info("Database directory ready: %s", parent)


class DatabaseManager:
    """
    Central async database access object.
    Instantiated once at startup and shared via app.state.db.
    Uses WAL mode for SQLite to handle concurrent reads without blocking.
    """

    def __init__(self):
        # Always create the DB directory before SQLite tries to open the file
        _ensure_db_directory(settings.database_url)

        self._engine = create_async_engine(
            settings.database_url,
            echo=(settings.app_env == "development"),
            connect_args={
                "check_same_thread": False,
                "timeout": 10,
            },
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    async def initialize(self) -> None:
        """Create all tables and enable WAL mode for concurrency."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
        logger.info("Database initialized (WAL mode enabled).")

    # ── User operations ──────────────────────────────────────────────────────

    async def get_or_create_user(self, phone_number: str, encryption) -> User:
        phone_hash = _hash_phone(phone_number)
        async with self._session_factory() as session:
            result = await session.execute(
                select(User).where(User.phone_hash == phone_hash)
            )
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    phone_hash=phone_hash,
                    phone_encrypted=encryption.encrypt(phone_number),
                    daily_alert_threshold=settings.default_daily_alert_threshold,
                    weekly_alert_threshold=settings.default_weekly_alert_threshold,
                )
                session.add(user)
                await session.commit()
                logger.info("New user created: %s", phone_hash[:8])
            return user

    # ── Expense operations ────────────────────────────────────────────────────

    async def save_expense(
        self,
        phone_number: str,
        amount: float,
        category: str,
        description: str,
        currency_code: str,
        encryption,
    ) -> Expense:
        phone_hash = _hash_phone(phone_number)
        amount_approx = round(amount / 10) * 10

        expense = Expense(
            user_phone_hash=phone_hash,
            currency_code=currency_code.upper()[:3],
            amount_approx=amount_approx,
            amount_enc=encryption.encrypt_float(amount),
            category_enc=encryption.encrypt(category),
            description_enc=encryption.encrypt(description) if description else None,
        )
        async with self._session_factory() as session:
            session.add(expense)
            await session.commit()
            logger.info("Expense saved: id=%s user=%s...", expense.id, phone_hash[:8])
        return expense

    async def get_expenses(
        self,
        phone_number: str,
        encryption,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[dict]:
        phone_hash = _hash_phone(phone_number)
        async with self._session_factory() as session:
            query = select(Expense).where(Expense.user_phone_hash == phone_hash)
            if since:
                query = query.where(Expense.created_at >= since)
            if until:
                query = query.where(Expense.created_at <= until)
            query = query.order_by(Expense.created_at.desc())
            result = await session.execute(query)
            rows = result.scalars().all()

        decrypted = []
        for row in rows:
            try:
                decrypted.append({
                    "id": row.id,
                    "amount": encryption.decrypt_float(row.amount_enc),
                    "category": encryption.decrypt(row.category_enc),
                    "description": encryption.decrypt(row.description_enc) if row.description_enc else "",
                    "currency_code": row.currency_code,
                    "created_at": row.created_at,
                })
            except ValueError:
                logger.warning("Could not decrypt row %s — skipping.", row.id)
        return decrypted

    async def get_daily_total_approx(
        self, phone_number: str, date: Optional[datetime] = None
    ) -> float:
        phone_hash = _hash_phone(phone_number)
        day = (date or datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = day + timedelta(days=1)
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.sum(Expense.amount_approx)).where(
                    Expense.user_phone_hash == phone_hash,
                    Expense.created_at >= day,
                    Expense.created_at < next_day,
                )
            )
            total = result.scalar_one_or_none()
        return total or 0.0

    async def get_weekly_total_approx(self, phone_number: str) -> float:
        phone_hash = _hash_phone(phone_number)
        week_ago = datetime.utcnow() - timedelta(days=7)
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.sum(Expense.amount_approx)).where(
                    Expense.user_phone_hash == phone_hash,
                    Expense.created_at >= week_ago,
                )
            )
            total = result.scalar_one_or_none()
        return total or 0.0

    # ── Conversation state ────────────────────────────────────────────────────

    async def get_conversation_state(
        self, phone_number: str, encryption
    ) -> tuple[str, Optional[dict]]:
        phone_hash = _hash_phone(phone_number)
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationState).where(
                    ConversationState.phone_hash == phone_hash
                )
            )
            state = result.scalar_one_or_none()

        if state is None:
            return "0", None

        age = datetime.utcnow() - (state.updated_at or datetime.utcnow())
        if age.total_seconds() > 300:
            await self.clear_conversation_state(phone_number)
            return "0", None

        pending = None
        if state.pending_data_enc:
            try:
                pending = json.loads(encryption.decrypt(state.pending_data_enc))
            except (ValueError, json.JSONDecodeError):
                pending = None

        return state.step, pending

    async def set_conversation_state(
        self,
        phone_number: str,
        step: str,
        pending_data: Optional[dict],
        encryption,
    ) -> None:
        phone_hash = _hash_phone(phone_number)
        encrypted_data = None
        if pending_data:
            encrypted_data = encryption.encrypt(json.dumps(pending_data))

        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationState).where(
                    ConversationState.phone_hash == phone_hash
                )
            )
            state = result.scalar_one_or_none()
            if state is None:
                state = ConversationState(phone_hash=phone_hash)
                session.add(state)
            state.step = step
            state.pending_data_enc = encrypted_data
            state.updated_at = datetime.utcnow()
            await session.commit()

    async def clear_conversation_state(self, phone_number: str) -> None:
        phone_hash = _hash_phone(phone_number)
        async with self._session_factory() as session:
            result = await session.execute(
                select(ConversationState).where(
                    ConversationState.phone_hash == phone_hash
                )
            )
            state = result.scalar_one_or_none()
            if state:
                state.step = "0"
                state.pending_data_enc = None
                state.updated_at = datetime.utcnow()
                await session.commit()
