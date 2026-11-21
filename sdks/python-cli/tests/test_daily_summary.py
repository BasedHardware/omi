"""Tests for ``omi daily-summary`` commands."""

from __future__ import annotations

import json
import sys
import pytest

from omi_cli.main import app, main


_SAMPLE_SUMMARIES = {
    "summaries": [
        {
            "id": "ds_01",
            "date": "2026-04-25",
            "day_emoji": "🚀",
            "headline": "Launched the new Omi CLI daily summaries feature",
            "overview": "Detailed overview of the launch activities and discussions.",
            "created_at": "2026-04-25T20:00:00Z",
            "stats": {
                "total_conversations": 5,
                "action_items_count": 2,
            },
        },
        {
            "id": "ds_02",
            "date": "2026-04-26",
            "day_emoji": "☕",
            "headline": "Sprint planning and review",
            "overview": "Reviewed user feedback and roadmap priorities.",
            "created_at": "2026-04-26T18:30:00Z",
        },
    ]
}


def test_daily_summary_list_table(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/daily-summaries").respond(json=_SAMPLE_SUMMARIES)
    result = cli_runner.invoke(app, ["daily-summary", "list"])
    assert result.exit_code == 0, result.output
    assert "Launched the new Omi CLI" in result.stdout
    assert "ds_01" in result.stdout


def test_daily_summary_list_json_retains_shape(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.get("/v1/dev/user/daily-summaries").respond(json=_SAMPLE_SUMMARIES)
    result = cli_runner.invoke(
        app,
        [
            "--json",
            "daily-summary",
            "list",
            "--limit",
            "10",
            "--offset",
            "5",
            "--start-date",
            "2026-04-01",
            "--end-date",
            "2026-04-26",
        ],
    )
    assert result.exit_code == 0, result.output
    request = route.calls.last.request
    assert request.url.params["limit"] == "10"
    assert request.url.params["offset"] == "5"
    assert request.url.params["start_date"] == "2026-04-01"
    assert request.url.params["end_date"] == "2026-04-26"

    payload = json.loads(result.stdout)
    assert "summaries" in payload
    assert len(payload["summaries"]) == 2
    assert payload["summaries"][0]["id"] == "ds_01"


def test_daily_summary_list_invalid_date_format(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["daily-summary", "list", "--start-date", "2026/04/25"])
    assert result.exit_code == 1
    assert "Invalid date format" in result.stderr


def test_daily_summary_list_invalid_calendar_date(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["daily-summary", "list", "--end-date", "2026-02-30"])
    assert result.exit_code == 1
    assert "Invalid calendar date" in result.stderr


def test_daily_summary_list_json_error(authed_profile, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["omi", "--json", "daily-summary", "list", "--start-date", "not-a-date"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    err = json.loads(output.err)
    assert "Invalid date format" in err["error"]
    assert "--start-date" in err["detail"]


def test_daily_summary_get(authed_profile, respx_mock, cli_runner) -> None:
    summary_data = {
        "id": "ds_01",
        "date": "2026-04-25",
        "day_emoji": "🚀",
        "headline": "Launched the new Omi CLI daily summaries feature",
        "overview": "Detailed overview of the launch activities and discussions.",
        "created_at": "2026-04-25T20:00:00Z",
        "highlights": ["Shipped CLI release", "Team demo went smoothly"],
        "action_items": [{"description": "Write release notes", "completed": True}],
        "knowledge_nuggets": ["Typer options formatting rules"],
        "stats": {
            "total_conversations": 5,
            "action_items_count": 2,
            "words_spoken": 1200,
        },
    }
    respx_mock.get("/v1/dev/user/daily-summaries/ds_01").respond(json=summary_data)
    result = cli_runner.invoke(app, ["--json", "daily-summary", "get", "ds_01"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["id"] == "ds_01"
    assert payload["day_emoji"] == "🚀"
    assert payload["highlights"] == ["Shipped CLI release", "Team demo went smoothly"]
    assert payload["action_items"] == [{"description": "Write release notes", "completed": True}]
    assert payload["knowledge_nuggets"] == ["Typer options formatting rules"]
    assert payload["stats"]["total_conversations"] == 5
    assert payload["stats"]["words_spoken"] == 1200


def test_daily_summary_get_not_found(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/daily-summaries/missing_id").respond(
        status_code=404, json={"detail": "Daily summary not found"}
    )
    result = cli_runner.invoke(app, ["daily-summary", "get", "missing_id"])
    assert result.exit_code == 5
    assert "not found" in result.stderr.lower()


def test_daily_summary_get_not_found_json(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    respx_mock.get("/v1/dev/user/daily-summaries/missing_id").respond(
        status_code=404, json={"detail": "Daily summary not found"}
    )
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "daily-summary", "get", "missing_id"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 5
    output = capsys.readouterr()
    err = json.loads(output.err)
    assert "not found" in err["error"].lower() or "not found" in err.get("detail", "").lower()
