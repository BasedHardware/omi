"""Datetime options preserve ISO offsets and fractions in outgoing API requests."""

import json

import pytest

from omi_cli.main import app

CASES = [
    (["action-item", "create", "test"], "--due-at", "POST", "/v1/dev/user/action-items", "due_at"),
    (["action-item", "update", "a1"], "--due-at", "PATCH", "/v1/dev/user/action-items/a1", "due_at"),
    (["action-item", "list"], "--start-date", "GET", "/v1/dev/user/action-items", "start_date"),
    (["action-item", "list"], "--end-date", "GET", "/v1/dev/user/action-items", "end_date"),
    (["conversation", "list"], "--start-date", "GET", "/v1/dev/user/conversations", "start_date"),
    (["conversation", "list"], "--end-date", "GET", "/v1/dev/user/conversations", "end_date"),
    (["conversation", "create", "--text", "test"], "--started-at", "POST", "/v1/dev/user/conversations", "started_at"),
    (
        ["conversation", "create", "--text", "test"],
        "--finished-at",
        "POST",
        "/v1/dev/user/conversations",
        "finished_at",
    ),
    (
        ["conversation", "from-segments"],
        "--started-at",
        "POST",
        "/v1/dev/user/conversations/from-segments",
        "started_at",
    ),
    (
        ["conversation", "from-segments"],
        "--finished-at",
        "POST",
        "/v1/dev/user/conversations/from-segments",
        "finished_at",
    ),
]


@pytest.mark.parametrize("command,option,method,path,field", CASES)
@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-09-08T12:30:00Z", "2026-09-08T12:30:00+00:00"),
        ("2026-09-08T12:30:00.123456+05:30", "2026-09-08T12:30:00.123456+05:30"),
        ("2026-09-08T12:30:00-04:00", "2026-09-08T12:30:00-04:00"),
        ("2026-09-08", "2026-09-08T00:00:00"),
        ("2026-09-08T12:30:00", "2026-09-08T12:30:00"),
        ("2026-09-08 12:30:00", "2026-09-08T12:30:00"),
    ],
)
def test_datetime_option_reaches_api(
    authed_profile, respx_mock, cli_runner, tmp_path, command, option, method, path, field, value, expected
):
    args = list(command)
    if "from-segments" in args:
        segments = tmp_path / "segments.json"
        segments.write_text('[{"text":"test","start":0,"end":1}]', encoding="utf-8")
        args.append(str(segments))
    route = respx_mock.request(method, path).respond(json=[] if method == "GET" else {"id": "test"})
    result = cli_runner.invoke(app, ["--json", *args, option, value])
    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    request = route.calls.last.request
    actual = request.url.params[field] if method == "GET" else json.loads(request.content)[field]
    assert actual == expected


def test_invalid_datetime_never_calls_api(authed_profile, respx_mock, cli_runner):
    result = cli_runner.invoke(app, ["action-item", "create", "test", "--due-at", "2026-02-30T12:00:00Z"])
    assert result.exit_code != 0
    assert "Invalid value" in result.output
    assert len(respx_mock.calls) == 0
