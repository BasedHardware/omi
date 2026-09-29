import os
from unittest.mock import patch

from services.conversation_selfheal import (
    selfheal_mode,
    selfheal_dry_run,
    selfheal_uid_allowlist,
)

def test_selfheal_mode_default():
    with patch.dict(os.environ, clear=True):
        assert selfheal_mode() == 'off'

def test_selfheal_mode_configured():
    with patch.dict(os.environ, {'SELFHEAL_MODE': 'heal'}):
        assert selfheal_mode() == 'heal'

def test_selfheal_mode_invalid():
    with patch.dict(os.environ, {'SELFHEAL_MODE': 'invalid'}):
        assert selfheal_mode() == 'off'

def test_selfheal_dry_run_default():
    with patch.dict(os.environ, clear=True):
        assert selfheal_dry_run() is False

def test_selfheal_dry_run_true():
    with patch.dict(os.environ, {'SELFHEAL_DRY_RUN': '1'}):
        assert selfheal_dry_run() is True
    with patch.dict(os.environ, {'SELFHEAL_DRY_RUN': 'true'}):
        assert selfheal_dry_run() is True

def test_selfheal_uid_allowlist_unset():
    with patch.dict(os.environ, clear=True):
        assert selfheal_uid_allowlist() is None

def test_selfheal_uid_allowlist_configured():
    with patch.dict(os.environ, {'SELFHEAL_UID_ALLOWLIST': 'uid1, uid2 , uid3'}):
        assert set(selfheal_uid_allowlist()) == {'uid1', 'uid2', 'uid3'}
