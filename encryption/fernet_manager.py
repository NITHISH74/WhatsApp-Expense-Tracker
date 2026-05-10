"""
encryption/fernet_manager.py
Handles AES-128 Fernet encryption/decryption for all sensitive fields.
Keys are loaded exclusively from environment variables.
"""

import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from config import settings

logger = logging.getLogger(__name__)


class EncryptionManager:
    """
    Manages Fernet symmetric encryption.
    Use one instance (singleton via FastAPI app.state) for the app lifetime.
    """

    def __init__(self, key: Optional[str] = None):
        # Explicit empty string → raise immediately (don't fall back to env)
        if key is not None and key == "":
            raise ValueError("Encryption key must not be empty.")
        raw_key = key or settings.fernet_key
        if not raw_key:
            raise ValueError(
                "FERNET_KEY environment variable is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        self._fernet = Fernet(raw_key.encode() if isinstance(raw_key, str) else raw_key)
        logger.info("EncryptionManager initialized.")

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string.
        Returns a URL-safe base64-encoded ciphertext string.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Encrypted, URL-safe base64 string.
        """
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
        ciphertext_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
        return ciphertext_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a Fernet-encrypted ciphertext string.

        Args:
            ciphertext: The encrypted string (as returned by encrypt()).

        Returns:
            Original plaintext string.

        Raises:
            ValueError: If decryption fails (tampered or wrong key).
        """
        try:
            plaintext_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return plaintext_bytes.decode("utf-8")
        except InvalidToken as exc:
            logger.error("Decryption failed — invalid token or wrong key.")
            raise ValueError("Decryption failed: invalid or corrupted data.") from exc

    def encrypt_float(self, value: float) -> str:
        """Convenience: encrypt a float as string."""
        return self.encrypt(str(value))

    def decrypt_float(self, ciphertext: str) -> float:
        """Convenience: decrypt a ciphertext back to float."""
        return float(self.decrypt(ciphertext))

    @staticmethod
    def generate_new_key() -> str:
        """
        Generate a brand-new Fernet key.
        Use this once during initial setup and store in FERNET_KEY env var.
        """
        return Fernet.generate_key().decode("utf-8")
