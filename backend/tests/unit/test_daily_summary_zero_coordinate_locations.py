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
"""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytz  # noqa: F401  (real dependency used by the module under test)

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENCRYPTION_SECRET", "omi_test_secret")


def _real_pkg(name, *relpath):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    mod.__path__ = [os.path.join(_BACKEND, *relpath)]
    return mod


def _stub_leaf(name, **attrs):
    mod = MagicMock(name=name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


# Parent packages kept on their real disk paths so the real module under test resolves,
# while __init__.py is skipped (they are already present in sys.modules).
_real_pkg("utils", "utils")
_real_pkg("utils.llm", "utils", "llm")
_real_pkg("utils.llms", "utils", "llms")
_real_pkg("utils.conversations", "utils", "conversations")
_real_pkg("models", "models")
_real_pkg("database", "database")

# Leaf modules external_integrations imports -> stubbed so their heavy internals never run.
_stub_leaf("database.action_items")
_stub_leaf("database.users")
_stub_leaf("models.conversation")
_stub_leaf("models.daily_summary_payload")
_stub_leaf("models.structured")
_stub_leaf("models.structured_extraction")
_stub_leaf("models.other")
_stub_leaf("utils.conversations.render")
_stub_leaf("utils.llm.clients")
_stub_leaf("utils.llm.usage_tracker")
_stub_leaf("utils.llms.memory")
_stub_leaf("utils.log_sanitizer")
sys.modules["langchain_core"] = MagicMock(name="langchain_core")
_stub_leaf("langchain_core.prompts", ChatPromptTemplate=MagicMock())

import utils.llm.external_integrations as ext  # noqa: E402


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


def _configure():
    ext.users_db.get_user_profile = MagicMock(return_value={"time_zone": "UTC", "language": "en"})
    ext.users_db.get_people_by_ids = MagicMock(return_value=[])
    ext.action_items_db.get_action_items = MagicMock(return_value=[])
    ext.get_prompt_memories = MagicMock(return_value=("TestUser", ""))
    ext.conversations_to_string = MagicMock(return_value="history")
    # Non-JSON LLM output -> JSONDecodeError -> _basic_daily_summary(..., locations)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "not json at all"
    ext.get_llm = MagicMock(return_value=mock_llm)


def test_zero_coordinate_location_is_not_dropped():
    _configure()
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


def test_conversation_without_geolocation_is_excluded():
    _configure()
    convos = [_Convo("c-none", None, started_at=datetime(2026, 6, 29, tzinfo=timezone.utc))]

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-06-29")

    assert result["locations"] == []
