"""
database/operations.py
Async database access layer using SQLAlchemy + aiosqlite.
All write operations encrypt sensitive fields before insertion.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func

from database.models import Base, User, Expense, ConversationState
from config import settings

logger = logging.getLogger(__name__)


def _hash_phone(phone_number: str) -> str:
    """SHA-256 hash of phone number — used as stable pseudonymous user key."""
    return hashlib.sha256(phone_number.encode("utf-8")).hexdigest()


class DatabaseManager:
    """
    Central async database access object.
    Instantiated once at startup and shared via app.state.db.
    Uses WAL mode for SQLite to handle concurrent reads without blocking.
    """

    def __init__(self):
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
            # WAL mode: concurrent reads + one write without locking
            await conn.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode=WAL;")
            )
            await conn.execute(
                __import__("sqlalchemy").text("PRAGMA synchronous=NORMAL;")
            )
        logger.info("Database initialized (WAL mode enabled).")

    # ── User operations ──────────────────────────────────────────────────────

    async def get_or_create_user(
        self, phone_number: str, encryption
    ) -> User:
        """
        Retrieve existing user or create a new one.
        phone_number is hashed before storage; encrypted copy also stored.
        """
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
        """
        Encrypt sensitive fields and persist a new expense record.

        Args:
            phone_number: Raw phone number (will be hashed).
            amount:       Exact amount (encrypted before storage).
            category:     Expense category (encrypted).
            description:  Free-text note (encrypted).
            currency_code: ISO 4217 code (stored plaintext).
            encryption:   EncryptionManager instance.

        Returns:
            The persisted Expense ORM object.
        """
        phone_hash = _hash_phone(phone_number)
        # Round amount to nearest 10 for non-sensitive threshold checking
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
            logger.info(
                "Expense saved: id=%s user=%s...", expense.id, phone_hash[:8]
            )
        return expense

    async def get_expenses(
        self,
        phone_number: str,
        encryption,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Retrieve and decrypt all expenses for a user within a date range.

        Returns a list of dicts with decrypted fields ready for report generation.
        """
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
        """
        Fast total using amount_approx (no decryption) for alert threshold checks.
        Returns sum of approximate amounts for the given calendar day.
        """
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
        """Fast weekly total using amount_approx (no decryption)."""
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
        """
        Returns (step, pending_data) for the user's current conversation.
        pending_data is the decrypted JSON dict of the in-progress expense.
        """
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

        # Expire states older than 5 minutes
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
        """Upsert the conversation state for a user."""
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
        """Reset conversation back to step 0 (no pending expense)."""
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
