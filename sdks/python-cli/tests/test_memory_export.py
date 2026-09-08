"""Memory export uses the real CLI and client with synthetic paginated HTTP."""

import json
import sys

import httpx
import pytest

from omi_cli.main import app, main


@pytest.mark.parametrize("count", [0, 3, 200, 201, 400])
def test_export_preserves_records_and_page_offsets(authed_profile, respx_mock, cli_runner, count) -> None:
    records = [
        {"id": f"m{i}", "content": "water [bold] café " * 20, "extra": {"tags": ["work", "skills"]}}
        for i in range(count)
    ]
    offsets = []

    def page(request):
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        offsets.append(offset)
        assert limit == 200
        assert request.url.params["categories"] == "work,skills"
        return httpx.Response(200, json=records[offset : offset + limit])

    respx_mock.get("/v1/dev/user/memories").mock(side_effect=page)
    result = cli_runner.invoke(app, ["--json", "memory", "export", "--categories", "work,skills"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == records
    assert offsets == list(range(0, count + 1, 200))


@pytest.mark.parametrize("count", [3, 4])
def test_export_ceiling_never_returns_partial_success(authed_profile, respx_mock, monkeypatch, capsys, count) -> None:
    records = [{"id": f"m{i}"} for i in range(count)]
    route = respx_mock.get("/v1/dev/user/memories").respond(json=records)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "memory", "export", "--max-items", "3"])
    if count == 3:
        main()
        assert json.loads(capsys.readouterr().out) == records
    else:
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        output = capsys.readouterr()
        assert output.out == ""
        assert "--max-items" in json.loads(output.err)["error"]
    assert route.calls.last.request.url.params["limit"] == "4"
    assert len(route.calls) == 1


def test_export_discards_earlier_pages_on_api_error(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[
            httpx.Response(200, json=[{"id": f"m{i}"} for i in range(200)]),
            httpx.Response(401, json={"detail": "expired test key"}),
        ]
    )
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "memory", "export"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"]
    assert len(route.calls) == 2


def test_export_requires_json_before_request(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["omi", "memory", "export"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "--json" in output.err
    assert not respx_mock.calls


@pytest.mark.parametrize("ceiling", ["0", "100001"])
def test_export_rejects_invalid_ceiling(authed_profile, respx_mock, cli_runner, ceiling) -> None:
    result = cli_runner.invoke(app, ["--json", "memory", "export", "--max-items", ceiling])
    assert result.exit_code != 0
    assert not respx_mock.calls


@pytest.mark.parametrize("extra_page", [[], [{"id": "over-limit"}]])
def test_export_checks_one_more_record_at_full_page_ceiling(
    authed_profile, respx_mock, monkeypatch, capsys, extra_page
) -> None:
    records = [{"id": f"m{i}"} for i in range(200)]
    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[httpx.Response(200, json=records), httpx.Response(200, json=extra_page)]
    )
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "memory", "export", "--max-items", "200"])
    if extra_page:
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert capsys.readouterr().out == ""
    else:
        main()
        assert json.loads(capsys.readouterr().out) == records
    assert [(call.request.url.params["offset"], call.request.url.params["limit"]) for call in route.calls] == [
        ("0", "200"),
        ("200", "1"),
    ]
