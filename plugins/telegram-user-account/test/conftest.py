"""Shared pytest fixtures for the telegram-user-account plugin tests.

Important: this plugin never writes long-lived platform credentials
(session string, api_id, api_hash, phone auth token) to disk. The
test fixtures must NOT bypass that invariant by using real
credentials. Stub all external surfaces:

- `telethon_client` is replaced with an in-process shim that records
  every call. Tests assert the RECORDED calls.
- `persona_client.chat` is replaced with a stub that returns canned
  replies. Tests assert the request body shape (sender context,
  previous_messages).
- The MCP / Telethon subprocess (when one is added) is replaced with a
  fake-subprocess in tests/unit that reads from a script-and-output
  pair rather than spawning a real Telethon client.

Auth: bearer gate handled by the shared plugins/_shared/auth module —
same config as the WhatsApp / Telegram bot plugins (AI_CLONE_PLUGIN_TOKEN
or OMI_DEV_MODE=1).

The discovery-file writer is patched per-test so the file lands in a
tmp_path rather than ~/.config/omi/, and so the test can read back
exactly what was written.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

# Make the plugin's own directory importable so test modules can do
# `import redact` (bare-name), `import simple_storage`, etc. — same
# pattern as plugins/omi-telegram-app/test/conftest.py. The plugin
# directory has a hyphen in its name (`telegram-user-account`) which
# is a non-Python identifier, so we don't use `import plugins....`
# — we put the plugin's directory on sys.path directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_DIR = os.path.abspath(os.path.join(_HERE, ".."))  # plugins/telegram-user-account/
_PLUGINS_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))  # plugins/
_SHARED = os.path.join(_PLUGINS_ROOT, "_shared")
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))  # repo root
for _p in (_PLUGIN_DIR, _SHARED, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# Default to dev mode so tests don't have to thread a bearer header
# through every TestClient.post(...). Same pattern as the Telegram
# bot plugin's conftest.
os.environ.setdefault("OMI_DEV_MODE", "1")
os.environ.setdefault("AI_CLONE_PLUGIN_TOKEN", "test-token")
# Pin the storage dir to a per-test tmp_path (the fixture below
# applies it BEFORE the plugin module loads).
os.environ.setdefault("TELEGRAM_USER_STORAGE_DIR", "/tmp/telegram-user-account-test")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.fixture(autouse=True)
def _isolated_storage_dir(tmp_path, monkeypatch):
    """Pin TELEGRAM_USER_STORAGE_DIR to a per-test tmp directory.

    The plugin reads the env var at module import time, so we have to
    set it BEFORE the import. conftest.py is imported once per
    pytest session, but the per-test fixture fires before each test
    function. Tests that need to re-import the plugin (e.g., to
    re-resolve STORAGE_DIR) pop the modules from sys.modules first.
    """
    monkeypatch.setenv("TELEGRAM_USER_STORAGE_DIR", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# Plugin module loader — mirrors plugins/omi-whatsapp-app/test/conftest.py
# so we can isolate sys.modules per test without breaking sibling tests.
# ---------------------------------------------------------------------------


def _load_telegram_user_account_module():
    """Load plugins/telegram-user-account/<name>.py via importlib and return it.

    Loaded module is cached. Stubs for sys.modules survive across
    tests so a second call is a dict lookup.
    """
    from tests._telegram_user_account_loader import load_module  # noqa: F401

    return load_module


# Stub heavy deps before any import that would touch firebase / google /
# langchain. Same pattern as tests/unit/test_persona_prompt_rewrite.py.
class _AutoMockModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


_HEAVY_STUB_NAMES = [
    "anthropic",
    "langchain",
    "langchain_core",
    "langchain_core.messages",
    "langchain_openai",
    "langchain_anthropic",
    "langchain_community",
    "openai",
    "tiktoken",
    "firebase_admin",
    "firebase_admin.messaging",
    "google",
    "google.cloud",
    "google.cloud.firestore",
    "redis",
    "pymemcache",
    "qdrant_client",
    "stripe",
    "deepgram",
    "deepgram.clients",
    "deepgram.clients.live",
    "deepgram.clients.live.v1",
    "pydub",
    "av",
    "tqdm",
    "twitter",
]
for _name in _HEAVY_STUB_NAMES:
    sys.modules.setdefault(_name, _AutoMockModule(_name))


@pytest.fixture(autouse=True)
def _clear_storage_state():
    """Reset simple_storage's module-level state at the start of every
    test so entries from one test don't leak into the next.

    Resets:
    - users (Telegram user id → config)
    - chats (chat id → ring buffer)
    - account (account metadata from Telethon's get_me())

    Pattern is consistent with the cubic P3 review 4614271733 fix
    applied to the WhatsApp plugin's conftest. The user-account plugin
    adds `chats` and `account` to the clear list because the WhatsApp
    plugin doesn't have those (it uses a single users dict keyed by
    phone number, not separate chats + account dicts).
    """
    import simple_storage

    if hasattr(simple_storage, "users"):
        simple_storage.users.clear()
    if hasattr(simple_storage, "chats"):
        simple_storage.chats.clear()
    if hasattr(simple_storage, "account"):
        simple_storage.account.clear()
    yield
