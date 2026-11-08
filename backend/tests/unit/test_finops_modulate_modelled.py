"""Hermetic Modulate modelled-line tests: measured Prometheus volume × the
committed, dated rate-card price. No network, no credentials, no account
reads. The Modulate ORG key must never be read by this line (no API exists)."""

from decimal import Decimal
import datetime as dt
import importlib.util
import json
import pathlib

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "finops"


def load(name):
    spec = importlib.util.spec_from_file_location("test_" + name, FINOPS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mm(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    monkeypatch.delenv("FINOPS_MODULATE_ORG_KEY", raising=False)
    module = load("pull_modulate_modelled")
    # point the committed card at a fixture copy so a future v2 edit cannot
    # silently re-price this test's expectations
    card = json.loads((FINOPS.parents[1] / "config" / "rate_card_v2.json").read_text())
    fixture_card = tmp_path / "rate_card_v2.json"
    fixture_card.write_text(json.dumps(card))
    monkeypatch.setattr(module, "RATE_CARD", fixture_card)
    fixture_prices = tmp_path / "modulate_prices.json"
    fixture_prices.write_text(module.REST_PRICES.read_text())
    monkeypatch.setattr(module, "REST_PRICES", fixture_prices)
    return module


def success(rows=()):
    return {"status": "success", "data": {"result": list(rows)}}


def prom_artifact(tmp_path, result, gke=(), gmp=()):
    artifact = {
        "daily": {
            "d_live_stt_audio_seconds": {"datasource": "prometheus", "result": result},
            "d_modulate_rest_audio_seconds": {"datasource": "prometheus", "result": success(gke)},
            "d_gmp_modulate_rest_audio_seconds": {"datasource": "gmp-cloud-run", "result": success(gmp)},
        }
    }
    (tmp_path / "prom_stt_7d.json").write_text(json.dumps(artifact))
    return artifact


def series(endpoint="stt", outcome="ok", seconds="3600", day="2026-10-20", **labels):
    timestamp = int((dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)).timestamp())
    return {"metric": {"endpoint": endpoint, "outcome": outcome, **labels}, "values": [[timestamp, seconds]]}


def run_main(mm, tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(
        sys, "argv", ["modelled", "--start", "2026-10-20", "--end", "2026-10-22", "--raw", str(tmp_path)]
    )
    mm.main()
    return json.loads((tmp_path / mm.ARTIFACT).read_text())


def test_committed_price_is_the_dated_rate_card_entry(mm):
    price = mm.price_from_card(json.loads(mm.RATE_CARD.read_text()))
    # rate card v2, committed 2026-10-18 @ f6a358902db: $0.06/hour
    # (platform.modulate.ai Multilingual Transcription streaming; 100 credits = $1)
    assert price["price_usd_per_hour"] == "0.060000000"
    assert price["price_as_of"] == "2026-10-18"
    assert "modulate" in price["price_source"].lower()


@pytest.mark.parametrize(
    "card",
    [
        {},
        {"transcription": {}},
        {"transcription": {"modulate": {}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": 0, "status": "card", "source": "s"}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": "60000", "status": "card", "source": "s"}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": 60000, "status": "provisional", "source": "s"}}},
        {"transcription": {"modulate": {"micro_usd_per_hour": 60000, "status": "card"}}},
    ],
)
def test_price_rejects_anything_not_a_committed_card(mm, card):
    with pytest.raises(mm.ModelledError):
        mm.price_from_card(card)


def test_seconds_take_only_modulate_provider_and_map_bucket_to_prior_day(mm, tmp_path):
    raw = json.loads((FIXTURES / "prom_live_stt_audio_seconds.json").read_text())
    prom = {"daily": {"d_live_stt_audio_seconds": {"result": raw}}}
    seconds = mm.modulate_seconds(prom, "2026-10-20", "2026-10-21")
    assert seconds == {"2026-10-20": Decimal("36000"), "2026-10-21": Decimal("7200")}


def test_modelled_rows_are_seconds_times_committed_price(mm):
    rows = mm.modelled_rows(
        {"2026-10-20": Decimal("36000")}, mm.price_from_card(json.loads(mm.RATE_CARD.read_text())), {}, mm.rest_prices()
    )
    assert rows == [
        {
            "date": "2026-10-20",
            "audio_seconds": "36000.000000000",
            "usd": "0.600000000",
            "live_seconds": "36000.000000000",
            "rest_stt_seconds": "0.000000000",
            "lid_seconds": "0.000000000",
        }
    ]


def test_main_writes_ready_artifact_marked_modelled(mm, tmp_path, capsys, monkeypatch):
    prom_artifact(tmp_path, json.loads((FIXTURES / "prom_live_stt_audio_seconds.json").read_text()))
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["pull_modulate_modelled.py", "--start", "2026-10-20", "--end", "2026-10-21", "--raw", str(tmp_path)],
    )
    mm.main()
    artifact = json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text())
    assert artifact["status"] == "ready"
    assert artifact["method"] == "modelled"
    assert artifact["price_usd_per_hour"] == "0.060000000"
    assert artifact["price_as_of"] == "2026-10-18"
    assert {r["date"]: r["usd"] for r in artifact["rows"]} == {
        "2026-10-20": "0.600000000",
        "2026-10-21": "0.120000000",
    }
    err = capsys.readouterr().err
    assert "0.720000000" in err  # parsed aggregates only


def test_main_skips_when_series_missing_and_never_guesses(mm, tmp_path, monkeypatch):
    prom_artifact(tmp_path, {"status": "success", "data": {"result": []}})
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        ["pull_modulate_modelled.py", "--start", "2026-10-20", "--end", "2026-10-21", "--raw", str(tmp_path)],
    )
    mm.main()
    assert json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text()) == {
        "status": "skipped",
        "reason": "prometheus_series_missing",
    }


def test_main_skips_without_prom_artifact_or_card(mm, tmp_path, monkeypatch):
    import sys

    def run_main():
        monkeypatch.setattr(
            sys,
            "argv",
            ["pull_modulate_modelled.py", "--start", "2026-10-20", "--end", "2026-10-21", "--raw", str(tmp_path)],
        )
        mm.main()

    run_main()
    assert (
        json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text())["reason"]
        == "prometheus_artifact_unavailable"
    )

    (tmp_path / "stt_modulate_modelled_daily.json").unlink()
    monkeypatch.setattr(mm, "RATE_CARD", tmp_path / "absent.json")
    run_main()
    assert json.loads((tmp_path / "stt_modulate_modelled_daily.json").read_text())["reason"] == "rate_card_unavailable"


def test_modulate_line_never_reads_the_org_key():
    """The ORG key binding exists for a future API; this line must not use it."""
    source = (FINOPS / "pull_modulate_modelled.py").read_text()
    assert "FINOPS_MODULATE_ORG_KEY" not in source
    assert "modulate_org" not in source
    assert "modulate-developer-apis" not in source


def test_committed_rest_prices_are_dated_public_prices(mm):
    prices = mm.rest_prices()
    assert prices == {
        "rest_price_usd_per_hour": "0.030000000",
        "lid_price_usd_per_hour": "0.010000000",
        "rest_price_source": "platform.modulate.ai public pricing",
        "lid_price_source": "platform.modulate.ai public pricing",
        "rest_price_as_of": "2026-11-08",
        "lid_price_as_of": "2026-11-08",
    }


def test_rest_only_day_is_priced_without_live(mm, tmp_path, monkeypatch):
    prom_artifact(tmp_path, success(), gmp=[series(seconds="7200")])
    artifact = run_main(mm, tmp_path, monkeypatch)
    assert artifact["status"] == "ready"
    assert artifact["rows"] == [
        {
            "date": "2026-10-20",
            "audio_seconds": "7200.000000000",
            "usd": "0.060000000",
            "live_seconds": "0.000000000",
            "rest_stt_seconds": "7200.000000000",
            "lid_seconds": "0.000000000",
        }
    ]


def test_live_rest_lid_sum_and_errors_are_only_logged(mm, tmp_path, monkeypatch, capsys):
    live = series(seconds="36000", provider="modulate")
    prom_artifact(
        tmp_path,
        success([live]),
        gke=[series(), series(endpoint="lid")],
        gmp=[
            series(seconds="7200", namespace="sync"),
            series(seconds="3600", namespace="backfill"),
            series(endpoint="lid", seconds="7200"),
            series(outcome="error", seconds="1800"),
            series(endpoint="lid", outcome="error", seconds="900"),
            series(provider="soniox"),
        ],
    )
    artifact = run_main(mm, tmp_path, monkeypatch)
    row = artifact["rows"][0]
    assert row["live_seconds"] == "36000.000000000"
    assert row["rest_stt_seconds"] == "14400.000000000"
    assert row["lid_seconds"] == "10800.000000000"
    assert row["audio_seconds"] == "61200.000000000"
    assert row["usd"] == "0.750000000"  # 10h live + 4h STT + 3h LID
    log = capsys.readouterr().err
    assert "stt error seconds=1800 (unpriced upper bound)" in log
    assert "lid error seconds=900 (unpriced upper bound)" in log


@pytest.mark.parametrize(
    "name,status",
    [
        ("d_gmp_modulate_rest_audio_seconds", "error"),
        ("d_gmp_modulate_rest_audio_seconds", None),
        ("d_modulate_rest_audio_seconds", "error"),
        ("d_live_stt_audio_seconds", "error"),
        ("diagnostic", "error"),
    ],
)
def test_any_failed_query_skips_window_and_replaces_stale_rows(mm, tmp_path, monkeypatch, name, status):
    artifact = prom_artifact(tmp_path, success([series(provider="modulate")]))
    artifact["daily"][name] = {"result": {"status": status}}
    (tmp_path / "prom_stt_7d.json").write_text(json.dumps(artifact))
    (tmp_path / mm.ARTIFACT).write_text(json.dumps({"status": "ready", "rows": [{"usd": "999"}]}))
    assert run_main(mm, tmp_path, monkeypatch) == {"status": "skipped", "reason": "gmp_query_failed"}


def test_missing_gmp_query_cannot_publish_old_live_only_artifact(mm, tmp_path, monkeypatch):
    artifact = prom_artifact(tmp_path, success([series(provider="modulate")]))
    del artifact["daily"]["d_gmp_modulate_rest_audio_seconds"]
    (tmp_path / "prom_stt_7d.json").write_text(json.dumps(artifact))
    assert run_main(mm, tmp_path, monkeypatch) == {"status": "skipped", "reason": "gmp_query_failed"}


def test_no_series_days_omitted_but_observed_zero_is_retained(mm, tmp_path, monkeypatch):
    prom_artifact(tmp_path, success([series(provider="modulate")]), gmp=[series(seconds="0", day="2026-10-22")])
    rows = run_main(mm, tmp_path, monkeypatch)["rows"]
    assert [row["date"] for row in rows] == ["2026-10-20", "2026-10-22"]
    assert rows[1]["usd"] == "0.000000000"


def test_cloud_run_series_in_gke_ignored_and_selectors_are_disjoint(mm, tmp_path, monkeypatch):
    prom_artifact(tmp_path, success(), gke=[series(cluster="__run__", seconds="999999")], gmp=[series()])
    assert run_main(mm, tmp_path, monkeypatch)["rows"][0]["usd"] == "0.030000000"
    prom = load("pull_prometheus")
    assert prom.DAILY["d_modulate_rest_audio_seconds"] == (
        'sum by (endpoint, outcome) (increase(omi_prerecorded_vendor_audio_seconds_total{provider="modulate",cluster!="__run__"}[1d]))'
    )
    assert prom.GMP_DAILY["d_gmp_modulate_rest_audio_seconds"] == (
        'sum by (namespace, endpoint, outcome) (increase(omi_prerecorded_vendor_audio_seconds_total{project_id="based-hardware",cluster="__run__",job="omi-cloud-run-application-metrics",provider="modulate"}[1d]))'
    )


def test_missing_prices_skips_with_reason(mm, tmp_path, monkeypatch):
    prom_artifact(tmp_path, success(), gmp=[series()])
    mm.REST_PRICES.unlink()
    assert run_main(mm, tmp_path, monkeypatch) == {"status": "skipped", "reason": "rest_prices_unavailable"}


@pytest.mark.parametrize("sku", ["batch_stt", "lid"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("micro_usd_per_hour", 0),
        ("micro_usd_per_hour", -1),
        ("micro_usd_per_hour", True),
        ("micro_usd_per_hour", "30000"),
        ("source", ""),
        ("source", None),
        ("status", "provisional"),
        ("as_of", "not-a-date"),
        ("as_of", None),
    ],
)
def test_invalid_prices_skip_with_reason(mm, tmp_path, monkeypatch, sku, field, value):
    prom_artifact(tmp_path, success(), gmp=[series()])
    prices = json.loads(mm.REST_PRICES.read_text())
    prices[sku][field] = value
    mm.REST_PRICES.write_text(json.dumps(prices))
    assert run_main(mm, tmp_path, monkeypatch) == {"status": "skipped", "reason": "rest_prices_invalid"}


@pytest.mark.parametrize(
    "contents,reason",
    [
        ("{", "rest_prices_unavailable"),
        ("[]", "rest_prices_invalid"),
        ("{}", "rest_prices_invalid"),
    ],
)
def test_unreadable_or_incomplete_price_documents_skip(mm, tmp_path, monkeypatch, contents, reason):
    prom_artifact(tmp_path, success(), gmp=[series()])
    mm.REST_PRICES.write_text(contents)
    assert run_main(mm, tmp_path, monkeypatch) == {"status": "skipped", "reason": reason}


def test_prometheus_queries_both_datasources_and_records_gmp_http_error(tmp_path, monkeypatch):
    import sys
    import urllib.error

    prom = load("pull_prometheus")
    monkeypatch.setattr(prom, "load_env", lambda: ("https://monitor.example/", "secret-never-log"))
    calls = []
    real_call = prom.call

    def http_error(request, **kwargs):
        raise urllib.error.HTTPError(request.full_url, 403, "secret-never-log", {}, None)

    monkeypatch.setattr(prom.auth_http, "open_authenticated", http_error)

    def call(base, token, api, params):
        calls.append((base, api, dict(params)))
        if "/uid/gmp-cloud-run/" in base:
            return real_call(base, token, api, params)
        return success()

    monkeypatch.setattr(prom, "call", call)
    monkeypatch.setattr(sys, "argv", ["prom", "--start", "2026-10-20", "--end", "2026-10-21", "--raw", str(tmp_path)])
    prom.main()
    artifact = json.loads((tmp_path / "prom_stt_7d.json").read_text())
    assert {base for base, _, _ in calls} == {
        "https://monitor.example/api/datasources/proxy/uid/prometheus/api/v1",
        "https://monitor.example/api/datasources/proxy/uid/gmp-cloud-run/api/v1",
    }
    assert len(calls) == len(prom.DAILY) + len(prom.GMP_DAILY)
    for name, entry in artifact["daily"].items():
        assert entry["datasource"] == ("gmp-cloud-run" if name in prom.GMP_DAILY else "prometheus")
    assert artifact["daily"]["d_gmp_modulate_rest_audio_seconds"]["result"] == {
        "status": "error",
        "error": "prometheus HTTP 403",
    }
    assert "secret-never-log" not in json.dumps(artifact)
    for _, api, params in calls:
        assert api == "query_range" and params["step"] == "86400"
        assert params["start"] == str(int(dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc).timestamp()))
        assert params["end"] == str(int(dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc).timestamp()))
