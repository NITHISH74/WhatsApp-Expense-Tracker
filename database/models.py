"""
database/models.py
SQLAlchemy ORM models for the expense tracker.

Schema design notes:
  - All sensitive fields (amount, description, category) are stored encrypted.
  - Metadata (user_id, timestamp, currency_code) stored plaintext for querying/sorting.
  - user_id is the phone number hash — supports multi-user from day one.
  - row_uuid is a UUID for idempotent deduplication.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Index,
    Float,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    """
    Stores per-user settings and encryption context.
    phone_number is stored hashed (SHA-256) to avoid PII in the DB.
    """

    __tablename__ = "users"

    phone_hash = Column(String(64), primary_key=True, index=True)
    # Encrypted phone number for display purposes
    phone_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Encrypted JSON blob for user preferences
    preferences_encrypted = Column(Text, nullable=True)
    # Daily/weekly spending threshold (plaintext float for fast threshold checks)
    daily_alert_threshold = Column(Float, default=100.0)
    weekly_alert_threshold = Column(Float, default=500.0)

    def __repr__(self) -> str:
        return f"<User hash={self.phone_hash[:8]}...>"


class Expense(Base):
    """
    Core expense record. Sensitive fields are Fernet-encrypted blobs.

    Plaintext metadata stored for querying:
      - user_phone_hash  → links to User.phone_hash
      - currency_code    → 3-letter ISO (e.g., USD, INR, CAD)
      - created_at       → timestamp for range queries
      - amount_approx    → approximate amount (rounded to nearest 10) for
                           threshold alerting without full decryption

    Encrypted blobs (cannot be queried directly):
      - amount_enc       → exact float amount
      - category_enc     → expense category string
      - description_enc  → free-text description
    """

    __tablename__ = "expenses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_phone_hash = Column(String(64), nullable=False, index=True)

    # Plaintext metadata
    currency_code = Column(String(3), nullable=False, default="USD")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    amount_approx = Column(Float, nullable=False)  # rounded, for alert thresholds

    # Encrypted sensitive fields
    amount_enc = Column(Text, nullable=False)
    category_enc = Column(Text, nullable=False)
    description_enc = Column(Text, nullable=True)

    # Compound indexes for fast date-range + user queries
    __table_args__ = (
        Index("ix_expenses_user_date", "user_phone_hash", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Expense id={self.id} user={self.user_phone_hash[:8]}... at={self.created_at}>"


class ConversationState(Base):
    """
    Tracks in-progress 2-step conversations.
    Cleared once conversation completes or times out (TTL: 5 minutes).

    Steps:
      0 = fresh (no pending confirmation)
      1 = awaiting user confirmation of parsed expense
    """

    __tablename__ = "conversation_states"

    phone_hash = Column(String(64), primary_key=True)
    step = Column(String(10), default="0", nullable=False)
    # Encrypted JSON blob holding pending expense data
    pending_data_enc = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<ConversationState hash={self.phone_hash[:8]}... step={self.step}>"
