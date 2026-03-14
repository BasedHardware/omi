"""
Unit tests for E2EE encryption flows.
Tests server-side encryption, migration paths, and key validation.
"""
import base64
import hashlib
import os
import re
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set required env vars before importing modules
os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret-key-for-e2ee-unit-tests-32bytes!')


class TestServerSideEncryption(unittest.TestCase):
    """Test server-side encryption used for 'enhanced' and 'e2ee' at-rest encryption."""

    def setUp(self):
        from utils.encryption import encrypt, decrypt
        self.encrypt = encrypt
        self.decrypt = decrypt
        self.uid = 'test-user-e2ee-123'

    def test_roundtrip(self):
        """Encrypt then decrypt returns original plaintext."""
        plaintext = 'This is a secret memory about my day'
        encrypted = self.encrypt(plaintext, self.uid)
        decrypted = self.decrypt(encrypted, self.uid)
        self.assertEqual(decrypted, plaintext)

    def test_encrypted_differs_from_plaintext(self):
        """Encrypted output is not the same as plaintext."""
        plaintext = 'Secret content'
        encrypted = self.encrypt(plaintext, self.uid)
        self.assertNotEqual(encrypted, plaintext)

    def test_empty_string_passthrough(self):
        """Empty strings pass through without error."""
        self.assertEqual(self.encrypt('', self.uid), '')
        self.assertEqual(self.decrypt('', self.uid), '')

    def test_wrong_uid_fails(self):
        """Decryption with wrong UID returns original (graceful failure)."""
        plaintext = 'secret'
        encrypted = self.encrypt(plaintext, self.uid)
        result = self.decrypt(encrypted, 'wrong-user-id')
        # Server decrypt returns original ciphertext on failure (graceful)
        self.assertEqual(result, encrypted)
        self.assertNotEqual(result, plaintext)

    def test_random_nonce(self):
        """Two encryptions of same data produce different ciphertext (random nonce)."""
        plaintext = 'Same content encrypted twice'
        enc1 = self.encrypt(plaintext, self.uid)
        enc2 = self.encrypt(plaintext, self.uid)
        self.assertNotEqual(enc1, enc2)

    def test_output_is_base64(self):
        """Encrypted output is valid base64."""
        encrypted = self.encrypt('test data', self.uid)
        try:
            decoded = base64.b64decode(encrypted)
            self.assertGreater(len(decoded), 28)  # nonce(12) + tag(16) + data
        except Exception:
            self.fail('Encrypted output is not valid base64')

    def test_none_passthrough(self):
        """None values pass through."""
        self.assertIsNone(self.encrypt(None, self.uid))
        self.assertIsNone(self.decrypt(None, self.uid))


class TestClientSideE2EE(unittest.TestCase):
    """Test that client-side encrypted data cannot be decrypted by the server."""

    def setUp(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self.AESGCM = AESGCM
        from utils.encryption import decrypt as server_decrypt
        self.server_decrypt = server_decrypt
        self.uid = 'test-user-e2ee-client'

    def _client_encrypt(self, plaintext: str, key: bytes) -> str:
        """Simulate client-side AES-256-GCM encryption (mirrors Flutter E2eeService)."""
        aesgcm = self.AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def _client_decrypt(self, encrypted: str, key: bytes) -> str:
        """Simulate client-side decryption."""
        payload = base64.b64decode(encrypted)
        aesgcm = self.AESGCM(key)
        return aesgcm.decrypt(payload[:12], payload[12:], None).decode()

    def test_client_roundtrip(self):
        """Client can encrypt and decrypt its own data."""
        key = os.urandom(32)
        plaintext = 'Client-encrypted secret memory'
        encrypted = self._client_encrypt(plaintext, key)
        decrypted = self._client_decrypt(encrypted, key)
        self.assertEqual(decrypted, plaintext)

    def test_server_cannot_decrypt_client_data(self):
        """Server-side decrypt fails on client-encrypted data."""
        key = os.urandom(32)
        encrypted = self._client_encrypt('secret', key)
        # Server should not be able to decrypt
        result = self.server_decrypt(encrypted, self.uid)
        # server_decrypt returns original on failure
        self.assertEqual(result, encrypted)

    def test_key_hash_format(self):
        """SHA-256 hash of key is valid 64-char hex."""
        key = os.urandom(32)
        key_hash = hashlib.sha256(key).hexdigest()
        self.assertEqual(len(key_hash), 64)
        self.assertTrue(re.fullmatch(r'[0-9a-f]{64}', key_hash))


class TestMigrationPath(unittest.TestCase):
    """Test data migration between protection levels."""

    def setUp(self):
        from utils.encryption import encrypt, decrypt
        self.encrypt = encrypt
        self.decrypt = decrypt
        self.uid = 'test-migration-user'

    def test_standard_to_enhanced(self):
        """Plain data can be encrypted for enhanced level."""
        plaintext = 'Unencrypted memory'
        encrypted = self.encrypt(plaintext, self.uid)
        decrypted = self.decrypt(encrypted, self.uid)
        self.assertEqual(decrypted, plaintext)

    def test_enhanced_to_e2ee(self):
        """Enhanced data can be re-encrypted for e2ee level (server-side at-rest)."""
        plaintext = 'Memory being migrated'
        # Encrypt at enhanced level
        enhanced = self.encrypt(plaintext, self.uid)
        # Decrypt then re-encrypt (migration)
        decrypted = self.decrypt(enhanced, self.uid)
        e2ee = self.encrypt(decrypted, self.uid)
        # Verify round-trip
        final = self.decrypt(e2ee, self.uid)
        self.assertEqual(final, plaintext)

    def test_migration_preserves_data(self):
        """Migration doesn't lose or corrupt data."""
        test_data = [
            'Simple text',
            'Text with émojis 🔐🔑',
            'Multi\nline\ncontent',
            'A' * 10000,  # Large content
            '',  # Empty
        ]
        for data in test_data:
            if not data:
                continue
            encrypted = self.encrypt(data, self.uid)
            decrypted = self.decrypt(encrypted, self.uid)
            self.assertEqual(decrypted, data, f'Failed for: {data[:50]}...')


class TestKeyHashValidation(unittest.TestCase):
    """Test Pydantic key_hash validation regex."""

    def test_valid_hash(self):
        """Valid SHA-256 hex hash passes."""
        valid = 'a14721051814d3fe9b0c4a2e8d76f84c2e8f3a1b4c5d6e7f8a9b0c1d2e3f4a5b'
        self.assertTrue(re.fullmatch(r'[0-9a-f]{64}', valid))

    def test_uppercase_rejected(self):
        """Uppercase hex is rejected."""
        upper = 'A14721051814D3FE9B0C4A2E8D76F84C2E8F3A1B4C5D6E7F8A9B0C1D2E3F4A5B'
        self.assertIsNone(re.fullmatch(r'[0-9a-f]{64}', upper))

    def test_short_rejected(self):
        """Too-short hash is rejected."""
        self.assertIsNone(re.fullmatch(r'[0-9a-f]{64}', 'tooshort'))

    def test_non_hex_rejected(self):
        """Non-hex characters rejected."""
        self.assertIsNone(re.fullmatch(r'[0-9a-f]{64}', 'x' * 64))


class TestWebCryptoCompatibility(unittest.TestCase):
    """Verify encryption format is compatible with Web Crypto API AES-256-GCM."""

    def test_format_structure(self):
        """Encrypted data has correct structure: base64(nonce[12] + ciphertext + tag[16])."""
        from utils.encryption import encrypt
        encrypted = encrypt('test content', 'test-user')
        payload = base64.b64decode(encrypted)
        # Minimum: 12 (nonce) + 1 (data) + 16 (tag) = 29
        self.assertGreaterEqual(len(payload), 29)
        # First 12 bytes are nonce
        nonce = payload[:12]
        self.assertEqual(len(nonce), 12)


@unittest.skipUnless(
    os.environ.get('RUN_INTEGRATION_TESTS') or __import__('importlib').util.find_spec('fastapi'),
    'fastapi not installed — skipping verify_e2ee_access tests'
)
class TestVerifyE2eeAccess(unittest.TestCase):
    """Test the centralized verify_e2ee_access helper."""

    def setUp(self):
        self.uid = 'test-verify-user'

    @patch('utils.e2ee_access.users_db')
    def test_non_e2ee_user_passes(self, mock_users):
        """Non-E2EE users are not blocked."""
        mock_users.get_data_protection_level.return_value = 'enhanced'
        from utils.e2ee_access import verify_e2ee_access
        verify_e2ee_access(self.uid, None, None)

    @patch('utils.e2ee_access.users_db')
    def test_e2ee_without_hash_raises(self, mock_users):
        """E2EE user without key hash gets 403."""
        mock_users.get_data_protection_level.return_value = 'e2ee'
        from utils.e2ee_access import verify_e2ee_access
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            verify_e2ee_access(self.uid, None, None)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch('utils.e2ee_access.users_db')
    def test_e2ee_with_valid_header_hash(self, mock_users):
        """Valid key hash via header passes."""
        mock_users.get_data_protection_level.return_value = 'e2ee'
        mock_users.get_e2ee_key_hash.return_value = 'a' * 64
        from utils.e2ee_access import verify_e2ee_access
        verify_e2ee_access(self.uid, 'a' * 64, None)

    @patch('utils.e2ee_access.users_db')
    def test_e2ee_with_valid_query_hash(self, mock_users):
        """Valid key hash via query parameter passes."""
        mock_users.get_data_protection_level.return_value = 'e2ee'
        mock_users.get_e2ee_key_hash.return_value = 'b' * 64
        from utils.e2ee_access import verify_e2ee_access
        verify_e2ee_access(self.uid, None, 'b' * 64)

    @patch('utils.e2ee_access.users_db')
    def test_e2ee_with_wrong_hash_raises(self, mock_users):
        """Wrong key hash gets 403."""
        mock_users.get_data_protection_level.return_value = 'e2ee'
        mock_users.get_e2ee_key_hash.return_value = 'a' * 64
        from utils.e2ee_access import verify_e2ee_access
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            verify_e2ee_access(self.uid, 'b' * 64, None)
        self.assertEqual(ctx.exception.status_code, 403)

    @patch('utils.e2ee_access.users_db')
    def test_e2ee_empty_string_hash_rejected(self, mock_users):
        """Empty string key hash is treated as missing."""
        mock_users.get_data_protection_level.return_value = 'e2ee'
        from utils.e2ee_access import verify_e2ee_access
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            verify_e2ee_access(self.uid, '', None)


if __name__ == '__main__':
    unittest.main()
