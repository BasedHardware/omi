import json
import sys

import pytest

from omi_cli.main import app, main


@pytest.mark.parametrize(
    ("options", "body"),
    [
        (["--clear-due-at"], {"due_at": None}),
        (["--due-at", "2026-09-10T12:00:00"], {"due_at": "2026-09-10T12:00:00"}),
        (["--description", "call"], {"description": "call"}),
        (["--clear-due-at", "--open"], {"due_at": None, "completed": False}),
    ],
)
def test_due_date_update_states(authed_profile, respx_mock, cli_runner, options, body) -> None:
    route = respx_mock.patch("/v1/dev/user/action-items/a1").respond(json={"id": "a1", **body})
    result = cli_runner.invoke(app, ["--json", "action-item", "update", "a1", *options])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == body


def test_conflicting_due_date_flags(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["omi", "--json", "action-item", "update", "a1", "--due-at", "2026-09-10", "--clear-due-at"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "--clear-due-at" in json.loads(output.err)["detail"]
    assert not respx_mock.calls
