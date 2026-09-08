import json
import sys
import pytest
from omi_cli.main import app, main

CASES = [(["goal", "create", "test", "--target", "1"], flag) for flag in ["--target", "--current", "--min", "--max"]]
CASES += [(["goal", "update", "g1"], flag) for flag in ["--target", "--current", "--min", "--max"]]
CASES += [(["goal", "progress", "g1"], None)]


@pytest.mark.parametrize("prefix,flag", CASES)
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "1e999"])
def test_nonfinite_goal_numbers_fail_before_http(authed_profile, respx_mock, monkeypatch, capsys, prefix, flag, value):
    args = [f"{flag}={value}"] if flag else ["--", value]
    monkeypatch.setattr(sys, "argv", ["omi", "--json", *prefix, *args])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "finite" in json.loads(output.err)["detail"]
    assert not respx_mock.calls


@pytest.mark.parametrize("value", ["0", "-3.5", "1e6"])
def test_finite_progress_is_preserved(authed_profile, respx_mock, cli_runner, value):
    route = respx_mock.patch("/v1/dev/user/goals/g1/progress").respond(json={"id": "g1"})
    result = cli_runner.invoke(app, ["--json", "goal", "progress", "g1", "--", value])
    assert result.exit_code == 0, result.output
    assert float(route.calls.last.request.url.params["current_value"]) == float(value)
