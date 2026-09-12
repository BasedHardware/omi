"""Pretty list tables must keep IDs that subsequent get commands accept."""

from __future__ import annotations

from omi_cli.main import app
from omi_cli.output import shorten

FULL_ID = "12345678-1234-4234-8234-123456789abc"
TRUNCATED_ID = shorten(FULL_ID, 14)


def test_shorten_width_matches_the_reported_ellipsis() -> None:
    assert TRUNCATED_ID == "12345678-1234…"
    assert TRUNCATED_ID != FULL_ID


def test_memory_pretty_list_keeps_full_id_for_get(authed_profile, respx_mock, cli_runner) -> None:
    item = {
        "id": FULL_ID,
        "content": "hello",
        "category": "core",
        "visibility": "private",
        "tags": [],
    }
    respx_mock.get("/v1/dev/user/memories").respond(json=[item])

    listed = cli_runner.invoke(app, ["--no-color", "memory", "list"])
    assert listed.exit_code == 0
    assert FULL_ID in listed.stdout
    assert TRUNCATED_ID not in listed.stdout

    missing = cli_runner.invoke(app, ["memory", "get", TRUNCATED_ID])
    assert missing.exit_code == 5

    found = cli_runner.invoke(app, ["--json", "memory", "get", FULL_ID])
    assert found.exit_code == 0


def test_goal_pretty_list_keeps_full_id_for_get(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/goals").respond(
        json=[{"id": FULL_ID, "title": "ship cli", "goal_type": "scale", "is_active": True}]
    )
    respx_mock.get(f"/v1/dev/user/goals/{FULL_ID}").respond(
        json={"id": FULL_ID, "title": "ship cli", "goal_type": "scale", "is_active": True}
    )

    listed = cli_runner.invoke(app, ["--no-color", "goal", "list"])
    assert listed.exit_code == 0
    assert FULL_ID in listed.stdout
    assert TRUNCATED_ID not in listed.stdout

    found = cli_runner.invoke(app, ["--json", "goal", "get", FULL_ID])
    assert found.exit_code == 0


def test_conversation_pretty_list_keeps_full_id(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/conversations").respond(
        json=[{"id": FULL_ID, "structured": {"title": "hello", "category": "personal"}}]
    )

    listed = cli_runner.invoke(app, ["--no-color", "conversation", "list"])
    assert listed.exit_code == 0
    assert FULL_ID in listed.stdout
    assert TRUNCATED_ID not in listed.stdout


def test_action_item_pretty_list_keeps_full_id_for_get(authed_profile, respx_mock, cli_runner) -> None:
    item = {"id": FULL_ID, "description": "ship it", "completed": False}
    respx_mock.get("/v1/dev/user/action-items").respond(json=[item])

    listed = cli_runner.invoke(app, ["--no-color", "action-item", "list"])
    assert listed.exit_code == 0
    assert FULL_ID in listed.stdout
    assert TRUNCATED_ID not in listed.stdout

    missing = cli_runner.invoke(app, ["action-item", "get", TRUNCATED_ID])
    assert missing.exit_code == 5

    found = cli_runner.invoke(app, ["--json", "action-item", "get", FULL_ID])
    assert found.exit_code == 0
