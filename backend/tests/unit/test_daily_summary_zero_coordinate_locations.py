"""Regression test for daily-summary location extraction.

generate_comprehensive_daily_summary built location pins with
`if c.geolocation and c.geolocation.latitude and c.geolocation.longitude`.
latitude/longitude are required floats on the Geolocation model, so that
truthiness guard silently dropped any conversation whose coordinate was
exactly 0.0 (equator latitude, prime-meridian longitude). The fix guards on
geolocation presence only.

The module under test pulls heavy backend deps at import time, so we stub the
leaf modules it imports (keeping the parent packages on their real paths so the
module itself still resolves from disk) and force the LLM to return non-JSON so
the function returns via _basic_daily_summary, which carries `locations`.

utils.llm.external_integrations binds its heavy dependencies at import time
(``from utils.llm.clients import get_llm, parser``, ``import database.users as
users_db``, …), so the fakes must be active before the module is exec'd. This is
the sanctioned Tier-2 "fake must precede import" case: see
backend/docs/test_isolation.md and testing/import_isolation.load_module_fresh.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytz  # noqa: F401  (real dependency used by the module under test)

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _leaf(name, **attrs):
    mod = AutoMockModule(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _real_pkg(name, *relpath):
    pkg = ModuleType(name)
    pkg.__path__ = [os.path.join(str(_BACKEND), *relpath)]  # type: ignore[attr-defined]
    return pkg


@pytest.fixture(scope="module")
def ext():
    """Load utils.llm.external_integrations fresh against stubbed heavy deps.

    Parent packages are given real ``__path__``s so the module under test resolves
    from disk; leaf modules are stubbed so their heavy internals never run.
    ``stub_modules`` snapshots and restores ``sys.modules`` so nothing leaks.
    """
    fakes = {
        "utils": _real_pkg("utils", "utils"),
        "utils.llm": _real_pkg("utils", "llm"),
        "utils.llms": _real_pkg("utils", "llms"),
        "utils.conversations": _real_pkg("utils", "conversations"),
        "models": _real_pkg("models", "models"),
        "database": _real_pkg("database", "database"),
        "database.action_items": _leaf("database.action_items"),
        "database.users": _leaf("database.users"),
        "models.conversation": _leaf("models.conversation"),
        "models.daily_summary_payload": _leaf("models.daily_summary_payload"),
        "models.structured": _leaf("models.structured"),
        "models.structured_extraction": _leaf("models.structured_extraction"),
        "models.other": _leaf("models.other"),
        "utils.conversations.render": _leaf("utils.conversations.render"),
        "utils.llm.clients": _leaf("utils.llm.clients"),
        "utils.llm.usage_tracker": _leaf("utils.llm.usage_tracker"),
        "utils.llms.memory": _leaf("utils.llms.memory"),
        "utils.log_sanitizer": _leaf("utils.log_sanitizer"),
        "langchain_core": AutoMockModule("langchain_core"),
        "langchain_core.prompts": _leaf("langchain_core.prompts", ChatPromptTemplate=MagicMock()),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.llm.external_integrations",
            os.path.join(str(_BACKEND), "utils", "llm", "external_integrations.py"),
        )
        yield module


class _Geo:
    def __init__(self, latitude, longitude, address=None):
        self.latitude = latitude
        self.longitude = longitude
        self.address = address


class _Convo:
    def __init__(self, id, geolocation=None, started_at=None, discarded=False):
        self.id = id
        self.geolocation = geolocation
        self.started_at = started_at
        self.finished_at = None
        self.discarded = discarded

    def get_person_ids(self):
        return []


def _configure(ext):
    ext.users_db.get_user_profile = MagicMock(return_value={"time_zone": "UTC", "language": "en"})
    ext.users_db.get_people_by_ids = MagicMock(return_value=[])
    ext.action_items_db.get_action_items = MagicMock(return_value=[])
    ext.get_prompt_memories = MagicMock(return_value=("TestUser", ""))
    ext.conversations_to_string = MagicMock(return_value="history")
    # Non-JSON LLM output -> JSONDecodeError -> _basic_daily_summary(..., locations)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "not json at all"
    ext.get_llm = MagicMock(return_value=mock_llm)


def test_zero_coordinate_location_is_not_dropped(ext):
    _configure(ext)
    started = datetime(2026, 6, 29, 14, 0, tzinfo=timezone.utc)
    convos = [
        _Convo("c-equator", _Geo(0.0, -0.13, "Equator"), started_at=started),  # latitude 0.0
        _Convo("c-meridian", _Geo(51.5, 0.0, "Greenwich"), started_at=started),  # longitude 0.0
        _Convo("c-normal", _Geo(40.7, -74.0, "NYC"), started_at=started),
        _Convo("c-none", None, started_at=started),  # no geolocation
    ]

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-06-29")

    ids = {loc["conversation_id"] for loc in result["locations"]}
    # The two zero-axis coordinates must survive; the conversation with no geolocation is excluded.
    assert ids == {"c-equator", "c-meridian", "c-normal"}
    by_id = {loc["conversation_id"]: loc for loc in result["locations"]}
    assert by_id["c-equator"]["latitude"] == 0.0
    assert by_id["c-meridian"]["longitude"] == 0.0


def test_conversation_without_geolocation_is_excluded(ext):
    _configure(ext)
    convos = [_Convo("c-none", None, started_at=datetime(2026, 6, 29, tzinfo=timezone.utc))]

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-06-29")

    assert result["locations"] == []
