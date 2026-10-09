"""Tests for goal context update options (--desired-outcome, --why-it-matters, --success-criterion)."""

from __future__ import annotations

import json
import sys

import pytest

from omi_cli.main import app, main


def test_goal_update_context_fields(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/goals/g123").respond(
        json={
            "id": "g123",
            "title": "Goal 1",
            "desired_outcome": "Reach 10k MRR",
            "why_it_matters": "Financial independence",
            "success_criteria": ["Ship MVP", "Get 100 paying users"],
        }
    )

    result = cli_runner.invoke(
        app,
        [
            "--json",
            "goal",
            "update",
            "g123",
            "--desired-outcome",
            "Reach 10k MRR",
            "--why-it-matters",
            "Financial independence",
            "--success-criterion",
            "Ship MVP",
            "--success-criterion",
            "Get 100 paying users",
        ],
    )

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body["desired_outcome"] == "Reach 10k MRR"
    assert body["why_it_matters"] == "Financial independence"
    assert body["success_criteria"] == ["Ship MVP", "Get 100 paying users"]


def test_goal_update_clear_context_fields(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/goals/g123").respond(
        json={"id": "g123", "title": "Goal 1", "why_it_matters": None, "success_criteria": []}
    )

    result = cli_runner.invoke(
        app,
        [
            "--json",
            "goal",
            "update",
            "g123",
            "--clear-why-it-matters",
            "--clear-success-criteria",
        ],
    )

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body["why_it_matters"] is None
    assert body["success_criteria"] == []


def test_goal_update_conflicting_why_it_matters(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["omi", "--json", "goal", "update", "g123", "--why-it-matters", "Important", "--clear-why-it-matters"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    error = json.loads(output.err)
    assert "--why-it-matters" in error["detail"]
    assert "--clear-why-it-matters" in error["detail"]
    assert not respx_mock.calls


def test_goal_update_conflicting_success_criteria(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["omi", "--json", "goal", "update", "g123", "--success-criterion", "Done", "--clear-success-criteria"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    error = json.loads(output.err)
    assert "--success-criterion" in error["detail"]
    assert "--clear-success-criteria" in error["detail"]
    assert not respx_mock.calls


def test_goal_update_no_fields_error(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "goal", "update", "g123"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    error = json.loads(output.err)
    assert "No fields to update" in error["error"]
    assert not respx_mock.calls
