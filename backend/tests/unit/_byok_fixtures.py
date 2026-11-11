"""Shared BYOK security-test isolation (issue #6880).

Not a test module: pytest does not collect this file. Test modules import
`_byok_isolation` so the autouse fixture is registered in each file.
"""

import os
import re
import warnings
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('DEEPGRAM_API_KEY', 'dg-test-fake-for-unit-tests')
os.environ.setdefault('GOOGLE_API_KEY', 'goog-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

warnings.filterwarnings('ignore', message='.*stream_options.*')

_SHA256_HEX_RE = re.compile(r'^[a-f0-9]{64}$')

_BACKEND = Path(__file__).resolve().parents[2]


def _make_db_fakes() -> dict:
    fakes: dict = {
        "database._client": AutoMockModule("database._client"),
        "database.redis_db": AutoMockModule("database.redis_db"),
        "database.conversations": AutoMockModule("database.conversations"),
        "database.memories": AutoMockModule("database.memories"),
        "database.chat": AutoMockModule("database.chat"),
        "database.users": AutoMockModule("database.users"),
        "database.user_usage": AutoMockModule("database.user_usage"),
        "database.llm_usage": AutoMockModule("database.llm_usage"),
        "database.announcements": AutoMockModule("database.announcements"),
        "database.notifications": AutoMockModule("database.notifications"),
        "database.daily_summaries": AutoMockModule("database.daily_summaries"),
        "database.app_review_config": AutoMockModule("database.app_review_config"),
        "database.webhook_health": AutoMockModule("database.webhook_health"),
        "database.action_items": AutoMockModule("database.action_items"),
        "utils.other.storage": AutoMockModule("utils.other.storage"),
    }

    apps = ModuleType("utils.apps")
    apps.get_available_app_by_id = MagicMock(return_value=None)
    fakes["utils.apps"] = apps

    stripe_utils = ModuleType("utils.stripe")
    stripe_utils.cancel_subscription = MagicMock(return_value=True)
    fakes["utils.stripe"] = stripe_utils

    twilio_service = ModuleType("utils.twilio_service")
    twilio_service.delete_user_caller_ids = MagicMock()
    twilio_service.delete_user_caller_ids_strict = MagicMock()
    fakes["utils.twilio_service"] = twilio_service

    external_integrations = ModuleType("utils.llm.external_integrations")
    external_integrations.generate_comprehensive_daily_summary = MagicMock()
    fakes["utils.llm.external_integrations"] = external_integrations

    streaming = ModuleType("utils.stt.streaming")
    streaming.deepgram_nova3_multi_languages = ['en']
    fakes["utils.stt.streaming"] = streaming

    return fakes


@pytest.fixture(scope="module", autouse=True)
def _byok_isolation():
    with stub_modules(_make_db_fakes()):
        # Warm the OpenAI client construction path once (SDK import/init) so the
        # per-test fast-unit CPU-time guard doesn't charge cold-start cost to the
        # first cache-routing test. Uses a distinct key so no assertion is affected.
        from utils.llm.clients import _cached_openai_chat

        # Force a fresh load against the stubs: another test module may already have
        # imported the real utils.subscription (and bound the real database._client),
        # so a plain `import` would reuse the cached module and bypass the fakes.
        load_module_fresh('utils.subscription', str(_BACKEND / 'utils' / 'subscription.py'))

        _cached_openai_chat('gpt-4.1-mini', 'sk-warmup-timing-guard-not-asserted', {})
        yield
