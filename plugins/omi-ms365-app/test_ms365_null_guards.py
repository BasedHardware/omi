"""Regression tests for #14247: null guards / type validation in ms365 services.

These exercise the pure normalisation helpers and the recipient extraction that
previously crashed on Microsoft Graph null collections / non-dict items.
"""
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Stub only the auth/config leaves so importing the REAL graph_client (and the
# services that import it) doesn't drag in msal / pydantic_settings. This keeps
# graph_client._parse_retry_after real while avoiding external deps.
sys.modules.setdefault("services", types.ModuleType("services")).__path__ = [str(Path(__file__).parent / "services")]

_auth = types.ModuleType("services.auth")
async def _get_access_token(user_id):  # noqa: ANN001
    return "fake-token"
_auth.get_access_token = _get_access_token
sys.modules["services.auth"] = _auth

_config = types.ModuleType("config")
_config.GRAPH_SCOPES = []
_config.get_settings = lambda: None
sys.modules["config"] = _config

from services import mail, teams, sharepoint, calendar, graph_client  # noqa: E402


# ---- limit bounding -------------------------------------------------------
def test_bound_limit_clamps():
    assert mail._bound_limit(0) == 1
    assert mail._bound_limit(-5) == 1
    assert mail._bound_limit(10_000) == mail._MAX_LIMIT
    assert mail._bound_limit("nope") == 10          # default
    assert mail._bound_limit(None) == 10
    assert mail._bound_limit(25) == 25
    assert teams._bound_limit(None) == 15
    assert sharepoint._bound_limit(None) == 15


# ---- collection normalisation --------------------------------------------
def test_iter_dicts_handles_null_and_junk():
    assert mail._iter_dicts(None) == []             # {"value": null}
    assert mail._iter_dicts("notalist") == []
    assert mail._iter_dicts([1, "x", None, {"a": 1}]) == [{"a": 1}]  # drops non-dicts


# ---- mail recipients ------------------------------------------------------
def test_extract_recipients_null_collection():
    assert mail._extract_recipients(None) == []     # toRecipients: null
    assert mail._extract_recipients("x") == []


def test_extract_recipients_missing_or_bad_emailaddress():
    recips = [
        {"emailAddress": {"address": "a@b.com"}},   # good
        {"noEmail": 1},                              # missing key
        {"emailAddress": "notadict"},                # bad type
        "notadict",                                  # bad item
        None,
    ]
    assert mail._extract_recipients(recips) == [{"address": "a@b.com"}]


def test_slim_message_non_dict_and_bad_from():
    assert mail._slim_message(None) == {}
    assert mail._slim_message("x") == {}
    out = mail._slim_message({"id": "1", "from": None})
    assert out["from"] == {} and out["id"] == "1"
    out2 = mail._slim_message({"from": {"emailAddress": {"address": "z@z.com"}}})
    assert out2["from"] == {"address": "z@z.com"}


# ---- sharepoint item ------------------------------------------------------
def test_slim_item_non_dict_and_bad_file():
    assert sharepoint._slim_item(None) == {}
    assert sharepoint._slim_item("x") == {}
    it = sharepoint._slim_item({"id": "1", "file": None, "folder": {}})
    assert it["mime"] is None and it["folder"] is True


# ---- async read() with mocked GraphClient --------------------------------
class _FakeGraph:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return self._payload

    async def post(self, *a, **k):
        return self._payload


def test_read_survives_null_recipients(monkeypatch):
    payload = {"id": "m1", "subject": "hi", "toRecipients": None, "ccRecipients": None, "body": None}
    monkeypatch.setattr(mail, "GraphClient", lambda *_: _FakeGraph(payload))
    out = asyncio.run(mail.read("u", "m1"))
    assert out["to"] == [] and out["cc"] == [] and out["subject"] == "hi"


def test_list_recent_survives_null_value(monkeypatch):
    monkeypatch.setattr(mail, "GraphClient", lambda *_: _FakeGraph({"value": None}))
    assert asyncio.run(mail.list_recent("u")) == []


def test_teams_survives_null_value(monkeypatch):
    monkeypatch.setattr(teams, "GraphClient", lambda *_: _FakeGraph({"value": None}))
    assert asyncio.run(teams.list_recent_chats("u")) == []
    monkeypatch.setattr(teams, "GraphClient", lambda *_: _FakeGraph({"value": [1, None, {"id": "t"}]}))
    assert asyncio.run(teams.list_my_teams("u")) == [{"id": "t", "name": None, "description": None}]


# ---- calendar guards ------------------------------------------------------
def test_slim_event_non_dict_and_nulls():
    assert calendar._slim_event(None) == {}
    assert calendar._slim_event("x") == {}
    ev = calendar._slim_event({"id": "e1", "start": None, "organizer": None, "onlineMeeting": None})
    assert ev["start"] is None and ev["organizer"] is None and ev["join_url"] is None and ev["id"] == "e1"
    ev2 = calendar._slim_event({"organizer": {"emailAddress": "notadict"}})
    assert ev2["organizer"] is None


def test_find_free_slots_survives_junk(monkeypatch):
    payload = {"meetingTimeSuggestions": [None, "x", {"meetingTimeSlot": None, "confidence": 90},
                                          {"meetingTimeSlot": {"start": {"dateTime": "T1"}, "end": {"dateTime": "T2"}}}]}
    monkeypatch.setattr(calendar, "GraphClient", lambda *_: _FakeGraph(payload))
    out = asyncio.run(calendar.find_free_slots("u", 30, ["a@b.com"]))
    assert out[-1] == {"start": "T1", "end": "T2", "confidence": None}
    assert out[-2]["start"] is None  # meetingTimeSlot None handled


def test_find_free_slots_null_suggestions(monkeypatch):
    monkeypatch.setattr(calendar, "GraphClient", lambda *_: _FakeGraph({"meetingTimeSuggestions": None}))
    assert asyncio.run(calendar.find_free_slots("u", 30, ["a@b.com"])) == []


# ---- graph_client Retry-After parsing ------------------------------------
def test_parse_retry_after_seconds_and_junk():
    assert graph_client._parse_retry_after("120") == 120
    assert graph_client._parse_retry_after(None) == 2
    assert graph_client._parse_retry_after("") == 2
    assert graph_client._parse_retry_after("-3") == 0
    assert graph_client._parse_retry_after("garbage") == 2


def test_parse_retry_after_http_date():
    # An HTTP-date in the past clamps to 0; the previous int() would ValueError.
    assert graph_client._parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
