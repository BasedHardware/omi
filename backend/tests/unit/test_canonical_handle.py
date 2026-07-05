"""Handle normalization tests — imports database.users directly (no heavy stubs)
so canonical_handle is the real function, not an isolation mock."""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import importlib  # noqa: E402


def _real_users_db():
    # Other unit tests install a global sys.modules stub for `database.users`
    # (memory_import_isolation.install_canonical_write_runtime_stubs). Force a real
    # reimport so canonical_handle here is the actual function, not a MagicMock,
    # regardless of test collection order.
    sys.modules.pop("database.users", None)
    return importlib.import_module("database.users")


users_db = _real_users_db()


def test_canonical_handle_passes_telegram_ids_through():
    # tg:<id> and @username must survive intact (never digit-stripped like a phone),
    # so a stable Telegram user id keys People correctly.
    assert users_db.canonical_handle('tg:123456789') == 'tg:123456789'
    assert users_db.canonical_handle('TG:123456789') == 'tg:123456789'
    assert users_db.canonical_handle('@Alice') == '@alice'


def test_canonical_handle_still_normalizes_phone_and_email():
    assert users_db.canonical_handle('+1 (555) 123-4567') == '5551234567'
    assert users_db.canonical_handle('  Foo@Bar.com ') == 'foo@bar.com'
