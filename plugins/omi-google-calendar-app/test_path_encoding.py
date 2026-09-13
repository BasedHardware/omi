"""Hermetic regression: tool-body `calendar_id`/`event_id` were interpolated
raw into Google Calendar API paths. Legitimate calendar ids contain `#`
(e.g. en.usa#holiday@group.v.calendar.google.com) which truncates the URL,
and `/`/`..` let an id rewrite the request path.

Run: python3 plugins/omi-google-calendar-app/test_path_encoding.py
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _stub(name, **attrs):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.Mock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    module.__dict__.update(attrs)
    return module


def _load_main():
    fastapi = _stub(
        "fastapi",
        FastAPI=lambda *a, **k: mock.Mock(get=_decorator, post=_decorator, mount=lambda *a, **k: None),
        HTTPException=Exception,
        Request=object,
        Query=lambda default=None, **kw: default,
    )
    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": _stub(
            "fastapi.responses", HTMLResponse=dict, RedirectResponse=object, JSONResponse=dict
        ),
        "dotenv": _stub("dotenv", load_dotenv=lambda *a, **k: None),
        "db": _stub("db"),
        "models": _stub("models", ChatToolResponse=dict),
        "requests": _stub("requests"),
    }
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("gcal_main_under_test", MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _recorded_requests():
    calls = []

    class _Resp:
        status_code = 200

        def json(self):
            return {"items": [], "id": "x"}

    def _record(method):
        def call(url, **kw):
            calls.append((method, url, kw))
            return _Resp()

        return call

    return calls, types.SimpleNamespace(
        get=_record("GET"), post=_record("POST"), put=_record("PUT"),
        patch=_record("PATCH"), delete=_record("DELETE"),
    )


def _request(body):
    class _Request:
        async def json(self):
            return body

    return _Request()


def _run_tool(module, handler_name, body):
    """Drive a real tool handler and record the URL it hands to requests."""
    calls, fake_requests = _recorded_requests()
    with mock.patch.object(module, "requests", fake_requests), mock.patch.object(
        module, "get_valid_access_token", lambda uid: "token123"
    ), mock.patch.object(module, "get_default_calendar", lambda uid: "primary"):
        asyncio.run(getattr(module, handler_name)(_request(body)))
    return calls


def test_calendar_id_with_hash_is_encoded_not_truncating():
    module = _load_main()
    calls = _run_tool(
        module, "tool_list_events",
        {"uid": "u1", "calendar_id": "en.usa#holiday@group.v.calendar.google.com", "days": 1},
    )
    assert calls, "handler made no API call"
    url = calls[0][1]
    assert "#" not in url, f"# truncated the request path: {url}"
    assert "en.usa%23holiday%40group.v.calendar.google.com" in url


def test_event_id_cannot_rewrite_path():
    module = _load_main()
    calls = _run_tool(
        module, "tool_delete_event",
        {"uid": "u1", "calendar_id": "primary", "event_id": "x/../../acl/owner"},
    )
    assert calls, "handler made no API call"
    for _, url, _ in calls:
        path = url.split("?")[0]
        assert "/../" not in path and not path.endswith("/.."), f"path rewritten: {url}"
        assert path.count("/events/") == 1


def test_create_event_encodes_calendar_id():
    module = _load_main()
    calls = _run_tool(
        module, "tool_create_event",
        {
            "uid": "u1",
            "calendar_id": "en.usa#holiday@group.v.calendar.google.com",
            "title": "standup",
            "start": "2026-09-20T10:00:00Z",
        },
    )
    post = [c for c in calls if c[0] == "POST"]
    assert post, f"handler made no POST call: {calls}"
    url = post[0][1]
    assert "#" not in url, f"# truncated the request path: {url}"
    assert "en.usa%23holiday%40group.v.calendar.google.com" in url


def test_update_event_encodes_event_id():
    module = _load_main()
    calls = _run_tool(
        module, "tool_update_event",
        {"uid": "u1", "calendar_id": "primary", "event_id": "x/../../acl/owner", "title": "t"},
    )
    assert calls, "handler made no API call"
    for _, url, _ in calls:
        path = url.split("?")[0]
        assert "/../" not in path and not path.endswith("/.."), f"path rewritten: {url}"


def test_dotdot_id_fails_closed():
    module = _load_main()
    calls = _run_tool(
        module, "tool_delete_event",
        {"uid": "u1", "calendar_id": "primary", "event_id": ".."},
    )
    assert not calls, f"dot-segment id reached the API: {calls}"


def test_plain_ids_pass_through_unchanged():
    module = _load_main()
    calls = _run_tool(
        module, "tool_get_event",
        {"uid": "u1", "calendar_id": "primary", "event_id": "evt_1"},
    )
    assert calls, "handler made no API call"
    assert calls[0][1].endswith("/calendars/primary/events/evt_1")


if __name__ == "__main__":
    tests = [
        test_calendar_id_with_hash_is_encoded_not_truncating,
        test_event_id_cannot_rewrite_path,
        test_create_event_encodes_calendar_id,
        test_update_event_encodes_event_id,
        test_dotdot_id_fails_closed,
        test_plain_ids_pass_through_unchanged,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} tests passed")
