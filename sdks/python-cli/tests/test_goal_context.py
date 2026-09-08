import json
import sys
import pytest
from omi_cli.main import app, main


@pytest.mark.parametrize(
    "options,body",
    [
        (
            [
                "--desired-outcome",
                "Ship",
                "--why-it-matters",
                "Customers",
                "--success-criterion",
                "Tests",
                "--success-criterion",
                "Release",
            ],
            {"desired_outcome": "Ship", "why_it_matters": "Customers", "success_criteria": ["Tests", "Release"]},
        ),
        (["--clear-why-it-matters", "--clear-success-criteria"], {"why_it_matters": None, "success_criteria": []}),
        (["--title", "Ship"], {"title": "Ship"}),
        (["--why-it-matters", ""], {"why_it_matters": ""}),
    ],
)
def test_goal_context_update(authed_profile, respx_mock, cli_runner, options, body):
    route = respx_mock.patch("/v1/dev/user/goals/g1").respond(json={"id": "g1", **body})
    result = cli_runner.invoke(app, ["--json", "goal", "update", "g1", *options])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == body


@pytest.mark.parametrize(
    "field,clear", [("--why-it-matters", "--clear-why-it-matters"), ("--success-criterion", "--clear-success-criteria")]
)
def test_goal_context_conflicts(authed_profile, respx_mock, monkeypatch, capsys, field, clear):
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "goal", "update", "g1", field, "", clear])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert clear in json.loads(output.err)["detail"]
    assert not respx_mock.calls
