"""Tests for ``omi folder`` commands."""

from __future__ import annotations

import json

import httpx
import pytest

from omi_cli.main import app


def test_folder_list_json(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/folders").respond(
        json=[
            {
                "id": "fld_work_1",
                "name": "Work",
                "description": "Work conversations",
                "color": "#FF5733",
                "icon": "briefcase",
                "created_at": "2026-09-01T12:00:00Z",
                "updated_at": "2026-09-01T12:00:00Z",
                "order": 0,
                "is_default": False,
                "is_system": True,
                "conversation_count": 5,
            }
        ]
    )
    result = cli_runner.invoke(app, ["--json", "folder", "list"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["id"] == "fld_work_1"
    assert payload[0]["name"] == "Work"
    assert payload[0]["conversation_count"] == 5


def test_folder_list_text(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/folders").respond(
        json=[
            {
                "id": "fld_personal",
                "name": "Personal",
                "description": None,
                "color": "#33FF57",
                "icon": "user",
                "created_at": "2026-09-01T12:00:00Z",
                "updated_at": "2026-09-01T12:00:00Z",
                "order": 1,
                "is_default": False,
                "is_system": False,
                "conversation_count": 12,
            }
        ]
    )
    result = cli_runner.invoke(app, ["folder", "list"])
    assert result.exit_code == 0, result.output
    assert "Personal" in result.output
    assert "fld_personal" in result.output


def test_folder_list_empty(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/folders").respond(json=[])
    result = cli_runner.invoke(app, ["--json", "folder", "list"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []


def test_folder_list_error(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/folders").respond(
        status_code=403,
        json={"detail": "Forbidden: requires conversations:read scope"},
    )
    result = cli_runner.invoke(app, ["folder", "list"])
    assert result.exit_code != 0
