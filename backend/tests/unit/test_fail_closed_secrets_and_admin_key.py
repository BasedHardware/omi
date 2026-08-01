"""Regressions for controls that became permissive when a secret was unset or a read failed.

- ``utils.encryption.decrypt`` used to return its input on any exception, so an AES-GCM
  authentication-tag failure was indistinguishable from a successful read.
- The ``secret_key != os.getenv('ADMIN_KEY')`` compare used to authenticate an empty header
  whenever ADMIN_KEY materialised as the empty string.
"""

import base64
import os

import pytest

from utils import encryption
from utils.admin_auth import has_admin_authorization, require_admin_authorization


class TestDecryptRaisesOnTampering:
    def test_round_trip_still_works(self):
        assert encryption.decrypt(encryption.encrypt('hello', 'uid1'), 'uid1') == 'hello'

    def test_tampered_ciphertext_raises_instead_of_returning_input(self):
        blob = bytearray(base64.b64decode(encryption.encrypt('hello', 'uid1')))
        blob[-1] ^= 0xFF  # break the authentication tag
        tampered = base64.b64encode(bytes(blob)).decode('utf-8')

        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt(tampered, 'uid1')

    def test_wrong_user_key_raises(self):
        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt(encryption.encrypt('hello', 'uid1'), 'uid2')

    def test_empty_input_is_still_passed_through(self):
        assert encryption.decrypt('', 'uid1') == ''

    def test_decryption_error_is_a_value_error(self):
        """Existing decode boundaries that catch ValueError keep treating this as unreadable."""
        assert issubclass(encryption.DecryptionError, ValueError)


class TestAdminKeyFailsClosed:
    def test_empty_admin_key_rejects_empty_header(self, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', '')
        assert has_admin_authorization('') is False
        assert has_admin_authorization(None) is False

    def test_unset_admin_key_rejects_everything(self, monkeypatch):
        monkeypatch.delenv('ADMIN_KEY', raising=False)
        assert has_admin_authorization('') is False
        assert has_admin_authorization('anything') is False

    def test_configured_admin_key_matches_exactly(self, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', 'real-secret')
        assert has_admin_authorization('real-secret') is True
        assert has_admin_authorization('wrong') is False
        assert has_admin_authorization('') is False

    def test_non_ascii_header_value_is_rejected_not_raised(self, monkeypatch):
        """Starlette decodes headers as latin-1, so a non-ASCII key must compare, not TypeError."""
        monkeypatch.setenv('ADMIN_KEY', 'real-secret')
        assert has_admin_authorization('ké') is False

    def test_require_raises_403_when_admin_key_is_empty(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setenv('ADMIN_KEY', '')
        with pytest.raises(HTTPException) as exc:
            require_admin_authorization('')
        assert exc.value.status_code == 403

    def test_require_passes_on_match(self, monkeypatch):
        monkeypatch.setenv('ADMIN_KEY', 'real-secret')
        require_admin_authorization('real-secret')


def test_encryption_secret_is_required_at_import():
    """The module-level guard is what agent-proxy now mirrors; keep it asserted."""
    assert os.getenv('ENCRYPTION_SECRET')
    assert len(encryption.ENCRYPTION_SECRET) >= 32
