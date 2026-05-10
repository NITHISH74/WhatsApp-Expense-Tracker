"""
tests/conftest.py
Shared pytest fixtures for the expense tracker test suite.
"""

import asyncio
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from database.operations import DatabaseManager
from encryption.fernet_manager import EncryptionManager


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_fernet_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def encryption(test_fernet_key) -> EncryptionManager:
    return EncryptionManager(key=test_fernet_key)


@pytest_asyncio.fixture
async def test_db(test_fernet_key, tmp_path):
    """In-memory SQLite database for testing."""
    import os
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    os.environ["FERNET_KEY"] = test_fernet_key

    db = DatabaseManager()
    # Override URL to use temp path
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    db._engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
    from sqlalchemy.ext.asyncio import async_sessionmaker
    db._session_factory = async_sessionmaker(db._engine, expire_on_commit=False, class_=AsyncSession)
    await db.initialize()
    yield db
