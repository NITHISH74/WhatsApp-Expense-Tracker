"""
tests/test_encryption.py
Unit tests for Fernet encryption/decryption.
"""

import pytest
from cryptography.fernet import Fernet
from encryption.fernet_manager import EncryptionManager


@pytest.fixture
def enc():
    key = Fernet.generate_key().decode()
    return EncryptionManager(key=key)


class TestEncryptionManager:
    def test_roundtrip_string(self, enc):
        plaintext = "Hello, World!"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_roundtrip_float(self, enc):
        value = 123.45
        assert enc.decrypt_float(enc.encrypt_float(value)) == pytest.approx(value)

    def test_different_ciphertexts(self, enc):
        """Fernet uses random IVs — same plaintext → different ciphertexts."""
        c1 = enc.encrypt("same text")
        c2 = enc.encrypt("same text")
        assert c1 != c2

    def test_wrong_key_raises(self):
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()
        enc1 = EncryptionManager(key=key1)
        enc2 = EncryptionManager(key=key2)
        ciphertext = enc1.encrypt("secret")
        with pytest.raises(ValueError):
            enc2.decrypt(ciphertext)

    def test_empty_key_raises(self):
        with pytest.raises(Exception):
            EncryptionManager(key="")

    def test_unicode_roundtrip(self, enc):
        plaintext = "₹500 कॉफ़ी ☕"
        assert enc.decrypt(enc.encrypt(plaintext)) == plaintext

    def test_generate_new_key(self):
        key = EncryptionManager.generate_new_key()
        assert len(key) == 44  # Base64-encoded Fernet key length
        # Should be usable
        enc = EncryptionManager(key=key)
        assert enc.decrypt(enc.encrypt("test")) == "test"
