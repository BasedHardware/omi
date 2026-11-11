"""Regression tests for Rich markup-like fragments in resource IDs."""

from __future__ import annotations

from omi_cli.main import app

MARKUP_ID = "item[/bold]x"

def test_memory_update_escapes_markup_id(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.patch(f"/v1/dev/user/memories/{MARKUP_ID}").respond(
        json={"id": MARKUP_ID, "content": "updated", "category": "core", "visibility": "private", "tags": []}
    )

    result = cli_runner.invoke(app, ["memory", "update", MARKUP_ID, "--content", "test"])

    assert result.exit_code == 0, result.stderr
    assert "MarkupError" not in result.stderr
    assert MARKUP_ID in result.stderr

def test_action_item_delete_escapes_markup_id(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.delete(f"/v1/dev/user/action-items/{MARKUP_ID}").respond(
        json={"success": True}
    )

    result = cli_runner.invoke(app, ["action-item", "delete", MARKUP_ID, "--yes"])

    assert result.exit_code == 0, result.stderr
    assert "MarkupError" not in result.stderr
    assert MARKUP_ID in result.stderr
