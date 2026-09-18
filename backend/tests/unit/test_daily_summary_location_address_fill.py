"""Daily summary pins: empty addresses are filled at read time, never dropped.

``generate_comprehensive_daily_summary`` copied ``c.geolocation.address`` into
each location pin verbatim. Conversations created by the sync path before
write-time enrichment shipped have coordinates but no address, so their recap
timeline rows rendered as "Unknown". The pins loop now fills an empty address
through the shared ~100m-rounded geocode cache (the same entries write-time
enrichment writes, so an already-enriched day costs no extra upstream call).
A geocode miss or error leaves the address empty and keeps the pin — the app
labels it "Unknown"; regeneration retroactively fixes historical summaries.

Loaded fresh with heavy deps stubbed (same Tier-2 pattern as
``test_daily_summary_zero_coordinate_locations.py``).
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

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
    fakes = {
        "utils": _real_pkg("utils", "utils"),
        "utils.llm": _real_pkg("utils.llm", "utils", "llm"),
        "utils.llms": _real_pkg("utils.llms", "utils", "llms"),
        "utils.conversations": _real_pkg("utils.conversations", "utils", "conversations"),
        "models": _real_pkg("models", "models"),
        "database": _real_pkg("database", "database"),
        "database.action_items": _leaf("database.action_items"),
        "database.daily_summaries": _leaf("database.daily_summaries"),
        "database.memories": _leaf("database.memories"),
        "database.users": _leaf("database.users"),
        "models.conversation": _leaf("models.conversation"),
        "models.structured": _leaf("models.structured"),
        "models.structured_extraction": _leaf("models.structured_extraction"),
        "models.other": _leaf("models.other"),
        "utils.conversations.render": _leaf("utils.conversations.render"),
        "utils.conversations.location": _leaf("utils.conversations.location"),
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
    def __init__(self, id, geolocation=None, started_at=None, discarded=False, source='omi'):
        self.id = id
        self.geolocation = geolocation
        self.started_at = started_at
        self.finished_at = None
        self.discarded = discarded
        self.source = source

    def get_person_ids(self):
        return []


def _configure(ext, geocoder):
    ext.users_db.get_user_profile = MagicMock(return_value={"time_zone": "UTC", "language": "en"})
    ext.users_db.get_people_by_ids = MagicMock(return_value=[])
    ext.action_items_db.get_action_items = MagicMock(return_value=[])
    ext.memories_db.count_memories_created = MagicMock(return_value=0)
    ext.daily_summaries_db.get_desktop_daily_usage = MagicMock(
        return_value={
            "watching_seconds": 0,
            "listening_seconds": 0,
            "proactive_cards_shown": 0,
            "proactive_cards_acted": 0,
            "ptt_turns": 0,
        }
    )
    ext.get_prompt_memories = MagicMock(return_value=("TestUser", ""))
    ext.conversations_to_string = MagicMock(return_value="history")
    ext.get_google_maps_location = geocoder
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "not json at all"  # -> _basic_daily_summary carries locations
    ext.get_llm = MagicMock(return_value=mock_llm)


def test_empty_address_is_filled_from_the_geocoder(ext):
    geocoder = MagicMock(return_value=_Geo(37.7749, -122.4194, address="210 Main St, San Francisco, CA 94105"))
    _configure(ext, geocoder)
    started = datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc)
    convos = [_Convo("c-sync", _Geo(37.7749, -122.4194), started_at=started)]

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-08-30")

    pin = result["locations"][0]
    geocoder.assert_called_once_with(37.7749, -122.4194)
    assert pin["address"] == "210 Main St, San Francisco, CA 94105"
    # Exact caller coordinates are preserved, not the cache cell's.
    assert pin["latitude"] == 37.7749
    assert pin["longitude"] == -122.4194


def test_present_address_skips_the_geocoder(ext):
    geocoder = MagicMock()
    _configure(ext, geocoder)
    started = datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc)
    convos = [_Convo("c-live", _Geo(37.7749, -122.4194, address="Existing address"), started_at=started)]

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-08-30")

    geocoder.assert_not_called()
    assert result["locations"][0]["address"] == "Existing address"


def test_geocode_miss_keeps_the_pin_without_an_address(ext):
    geocoder = MagicMock(return_value=None)  # ZERO_RESULTS / provider failure
    _configure(ext, geocoder)
    started = datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc)
    convos = [_Convo("c-sync", _Geo(37.7749, -122.4194), started_at=started)]

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-08-30")

    assert len(result["locations"]) == 1  # the pin is never dropped
    assert result["locations"][0]["address"] is None  # app falls back to "Unknown"


def test_geocoder_exception_keeps_the_pin_without_an_address(ext):
    geocoder = MagicMock(side_effect=RuntimeError("maps unavailable"))
    _configure(ext, geocoder)
    started = datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc)
    convos = [_Convo("c-sync", _Geo(37.7749, -122.4194), started_at=started)]

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-08-30")

    assert len(result["locations"]) == 1
    assert result["locations"][0]["address"] is None


def test_geocode_attempts_are_capped_per_summary(ext):
    """11 empty-address pins -> 10 geocode attempts; the 11th pin keeps 'Unknown'."""
    geocoder = MagicMock(side_effect=lambda lat, lng: _Geo(lat, lng, address=f"{lat:.0f} Filled St, San Francisco"))
    _configure(ext, geocoder)
    started = datetime(2026, 8, 30, 14, 0, tzinfo=timezone.utc)
    convos = [
        _Convo(f"c-{i}", _Geo(37.0 + i / 10.0, -122.4), started_at=started) for i in range(1, 12)
    ]  # 11 pins, all address-less

    result = ext.generate_comprehensive_daily_summary("uid", convos, "2026-08-30")

    assert geocoder.call_count == ext._DAILY_SUMMARY_GEOCODE_ATTEMPT_CAP == 10
    assert len(result["locations"]) == 11  # every pin stays
    filled = [pin for pin in result["locations"] if pin["address"]]
    unfilled = [pin for pin in result["locations"] if not pin["address"]]
    assert len(filled) == 10
    assert len(unfilled) == 1  # the pin past the cap falls back to "Unknown" in the app
