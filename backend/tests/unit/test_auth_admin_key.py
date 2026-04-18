"""Verify ADMIN_KEY impersonation and LOCAL_DEVELOPMENT bypass are gated
to dev environments only. Production must never accept the bypass.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest
from firebase_admin.auth import InvalidIdTokenError

from utils.other import endpoints


def _env(**kwargs):
    """Context manager: set env vars for the duration of the test."""
    clean = {k: kwargs.get(k, None) for k in kwargs}
    return mock.patch.dict(os.environ, {k: v for k, v in clean.items() if v is not None}, clear=False)


def test_admin_key_impersonation_rejected_in_prod():
    """Previously: `Authorization: Bearer <ADMIN_KEY><target>` → act as target.
    After fix: prod rejects this outright, falls through to Firebase verify.
    """
    with mock.patch.dict(
        os.environ,
        {'ADMIN_KEY': 'leaked-admin-key', 'LOCAL_DEVELOPMENT': 'true', 'ENV': 'production'},
        clear=False,
    ):
        with mock.patch.object(endpoints.auth, 'verify_id_token', side_effect=InvalidIdTokenError('bad')):
            with pytest.raises(InvalidIdTokenError):
                endpoints.verify_token('leaked-admin-keyvictim_uid')


def test_admin_key_impersonation_rejected_without_local_development_flag():
    """ADMIN_KEY alone is not enough — LOCAL_DEVELOPMENT must also be true."""
    with mock.patch.dict(
        os.environ,
        {'ADMIN_KEY': 'k'},
        clear=False,
    ):
        # Ensure LOCAL_DEVELOPMENT is unset
        os.environ.pop('LOCAL_DEVELOPMENT', None)
        with mock.patch.object(endpoints.auth, 'verify_id_token', side_effect=InvalidIdTokenError('bad')):
            with pytest.raises(InvalidIdTokenError):
                endpoints.verify_token('kvictim')


def test_admin_key_impersonation_allowed_in_dev():
    """In a dev env (LOCAL_DEVELOPMENT=true, ENV=dev) impersonation still works
    for integration tests. Gate is two-key: both must be set.
    """
    with mock.patch.dict(
        os.environ,
        {'ADMIN_KEY': 'k', 'LOCAL_DEVELOPMENT': 'true', 'ENV': 'dev'},
        clear=False,
    ):
        assert endpoints.verify_token('kvictim') == 'victim'


def test_local_development_fallback_rejected_in_prod():
    """If the Firebase token is bad AND ENV=production, we must not return '123'."""
    with mock.patch.dict(
        os.environ,
        {'LOCAL_DEVELOPMENT': 'true', 'ENV': 'production'},
        clear=False,
    ):
        with mock.patch.object(endpoints.auth, 'verify_id_token', side_effect=InvalidIdTokenError('bad')):
            with pytest.raises(InvalidIdTokenError):
                endpoints.verify_token('any-token')


def test_local_development_fallback_allowed_in_dev():
    with mock.patch.dict(
        os.environ,
        {'LOCAL_DEVELOPMENT': 'true', 'ENV': 'dev'},
        clear=False,
    ):
        with mock.patch.object(endpoints.auth, 'verify_id_token', side_effect=InvalidIdTokenError('bad')):
            assert endpoints.verify_token('any-token') == '123'
