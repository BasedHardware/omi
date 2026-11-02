"""Hermetic invoice-contract tests. Fixtures use published API example shapes,
with no account reads, identifiers, network or credentials.
"""

import csv
import datetime as dt
from decimal import Decimal
import http.client
import importlib.util
import io
import json
import pathlib
import urllib.error
import urllib.request
import urllib.response

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"
FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "finops"


def load(name):
    spec = importlib.util.spec_from_file_location("test_" + name, FINOPS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def stt(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    for provider in ("SONIOX", "DEEPGRAM"):
        monkeypatch.delenv(provider + "_API_KEY", raising=False)
    return load("pull_stt_costs")


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_soniox_utc_days_decimal_costs_and_no_double_count(stt, monkeypatch):
    calls = []

    def get(url, key, params):
        calls.append(params)
        return fixture("soniox_summary.json")

    monkeypatch.setattr(stt, "get_json", get)
    costs = stt.soniox_costs("2026-04-01", "2026-04-03", "test")
    assert costs == {"2026-04-01": "0.0409000000", "2026-04-02": "0.0204500000"}
    assert calls == [{"start_time": "2026-04-01T00:00:00Z", "end_time": "2026-04-03T00:00:00Z"}]


def test_soniox_multiple_stt_models_and_zero_days(stt, monkeypatch):
    payload = fixture("soniox_summary.json")
    payload["models"].append({"model": "stt-rt-v5", "days": ["2026-04-01"], "cost_usd": ["1.2"]})
    monkeypatch.setattr(stt, "get_json", lambda *args: payload)
    assert stt.soniox_costs("2026-04-01", "2026-04-03", "test")["2026-04-01"] == "1.2409000000"
    payload["models"] = []
    assert set(stt.soniox_costs("2026-04-01", "2026-04-03", "test").values()) == {"0"}


@pytest.mark.parametrize("bad", ["length", "duplicate", "outside", "coverage", "nan"])
def test_soniox_rejects_incomplete_or_misaligned_summary(stt, monkeypatch, bad):
    payload = fixture("soniox_summary.json")
    model = payload["models"][0]
    if bad == "length":
        model["cost_usd"].pop()
    elif bad == "duplicate":
        model["days"][1] = model["days"][0]
    elif bad == "outside":
        model["days"][0] = "2026-03-31"
    elif bad == "coverage":
        payload["total"]["days"].pop()
    else:
        model["cost_usd"][0] = "NaN"
    monkeypatch.setattr(stt, "get_json", lambda *args: payload)
    with pytest.raises(stt.InvoiceError):
        stt.soniox_costs("2026-04-01", "2026-04-03", "test")


def test_summary_chunks_at_366_days_without_overlap(stt, monkeypatch):
    calls = []

    def get(url, key, params):
        days = stt.dates(params["start_time"][:10], params["end_time"][:10])
        calls.append(days)
        return {"total": {"days": days}, "models": []}

    monkeypatch.setattr(stt, "get_json", get)
    start = dt.date(2025, 1, 1)
    end = (start + dt.timedelta(days=367)).isoformat()
    costs = stt.soniox_costs(start.isoformat(), end, "test")
    assert [len(c) for c in calls] == [366, 1]
    assert len(costs) == 367
    assert calls[0][-1] != calls[1][0]


def _deepgram_payload():
    payload = fixture("deepgram_billing.json")
    payload["results"].append(
        {"dollars": 99, "grouping": {"start": "2026-04-02", "end": "2026-04-02", "line_item": "streaming::nova-3"}}
    )
    return payload


def test_deepgram_known_stt_is_measured_and_ignores_the_next_day(stt, monkeypatch):
    def get(url, key, params, scheme):
        assert params == {"start": "2026-04-01", "end": "2026-04-02", "deployment": "hosted", "grouping": "line_item"}
        assert scheme == "Token"
        payload = _deepgram_payload()
        for row in payload["results"]:
            if row["grouping"]["line_item"] == "sync::aura-2":
                row["dollars"] = 0
        return payload

    monkeypatch.setattr(stt, "get_json", get)
    assert stt.deepgram_costs("2026-04-01", "2026-04-02", "test", "company") == {
        "2026-04-01": {"usd": "0.35", "unclassified_usd": "0", "status": "measured"}
    }


def test_deepgram_unrecognized_positive_dollars_are_not_measured(stt, monkeypatch):
    monkeypatch.setattr(stt, "get_json", lambda *args, **kwargs: _deepgram_payload())
    day = stt.deepgram_costs("2026-04-01", "2026-04-02", "test", "company")["2026-04-01"]
    assert day["status"] == "incomplete"
    assert day["usd"] == "0.35"
    assert Decimal(day["unclassified_usd"]) == Decimal("0.5")
    assert "99" not in day["usd"] and "99" not in day["unclassified_usd"]


def test_unclassified_deepgram_is_recorded_and_not_published(stt, monkeypatch, tmp_path):
    monkeypatch.setenv("SONIOX_API_KEY", "soniox-test-key")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "deepgram-test-key")
    monkeypatch.setenv("FINOPS_DEEPGRAM_PROJECT_ID", "company")
    monkeypatch.setattr(stt, "soniox_costs", lambda *args: {"2026-04-01": "0.0409000000"})
    monkeypatch.setattr(stt, "get_json", lambda *args, **kwargs: _deepgram_payload())
    stt.pull(tmp_path, "2026-04-01", "2026-04-02")
    document = json.loads((tmp_path / "stt_vendor_cost_daily.json").read_text())
    assert "deepgram" not in document["providers"]
    assert document["providers"]["soniox"]["2026-04-01"] == "0.0409000000"
    assert document["incomplete"]["deepgram"]["2026-04-01"]["status"] == "incomplete"
    assert Decimal(document["incomplete"]["deepgram"]["2026-04-01"]["unclassified_usd"]) == Decimal("0.5")
    recon = load("gcp_cost_reconciliation")
    longs, recons = recon.company_stt_rows(tmp_path, ["2026-04-01"], None)
    assert [row["component"] for row in longs] == ["stt_soniox_measured"]
    assert all(row["method"] == "measured" for row in longs)
    assert "stt_deepgram_measured" not in {row["pool"] for row in recons}
    assert recons[0]["delta_pct"] is None


def test_measured_stt_does_not_claim_a_reconciliation_delta(tmp_path):
    recon = load("gcp_cost_reconciliation")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "stt_vendor_cost_daily.json").write_text(
        json.dumps({"providers": {"deepgram": {"2026-04-01": "0.35"}}, "skipped": []})
    )
    longs, recons = recon.company_stt_rows(raw, ["2026-04-01"], None)
    assert longs[0]["method"] == "measured"
    assert recons[0]["pool"] == "stt_deepgram_measured"
    assert recons[0]["pool_usd"] == recons[0]["allocated_usd"] == 0.35
    assert recons[0]["delta_pct"] is None


def test_overlapping_incomplete_provider_is_not_measured(tmp_path):
    recon = load("gcp_cost_reconciliation")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "stt_vendor_cost_daily.json").write_text(
        json.dumps(
            {
                "providers": {"deepgram": {"2026-04-01": "0.35"}},
                "incomplete": {"deepgram": {"2026-04-01": {"status": "incomplete", "unclassified_usd": "0.5"}}},
            }
        )
    )
    with pytest.raises(ValueError, match="incomplete"):
        recon.company_stt_rows(raw, ["2026-04-01"], None)


def test_unreadable_secret_skips_that_vendor_only(stt, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    monkeypatch.setenv("FINOPS_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("FINOPS_DEEPGRAM_PROJECT_ID", "company")
    soniox = tmp_path / "SONIOX_API_KEY"
    soniox.mkdir()
    (soniox / "SONIOX_API_KEY").write_bytes(b"\xff\xfesoniox-secret-bytes")
    deepgram = tmp_path / "DEEPGRAM_API_KEY"
    deepgram.mkdir()
    (deepgram / "DEEPGRAM_API_KEY").write_text("deepgram-test-key")
    monkeypatch.setattr(stt, "soniox_costs", lambda *args: pytest.fail("unreadable secret must not pull"))
    monkeypatch.setattr(
        stt,
        "deepgram_costs",
        lambda *args: {"2026-04-01": {"usd": "0.35", "unclassified_usd": "0", "status": "measured"}},
    )
    stt.pull(tmp_path, "2026-04-01", "2026-04-02")
    document = json.loads((tmp_path / "stt_vendor_cost_daily.json").read_text())
    assert document["skipped"] == ["soniox"]
    assert "soniox" not in document["providers"]
    assert document["providers"]["deepgram"] == {"2026-04-01": "0.35"}
    err = capsys.readouterr().err
    assert "WARNING: soniox measured STT skipped: secret/config unavailable" in err
    assert "soniox-secret" not in err
    assert "deepgram-test-key" not in err


def test_cross_host_redirect_does_not_send_the_credential(stt, monkeypatch):
    secret = "stt-live-key-do-not-leak"
    seen = []

    class Capture(urllib.request.BaseHandler):
        handler_order = 100

        def https_open(self, req):
            seen.append((req.full_url, req.get_header("Authorization")))
            headers = http.client.HTTPMessage()
            headers["Location"] = "https://evil.example/collect?echo=" + secret
            response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
            response.msg = "Found"
            return response

        http_open = https_open

    def build(ssl_context=None):
        return urllib.request.build_opener(stt.auth_http.NoRedirect(), Capture())

    monkeypatch.setattr(stt.auth_http, "build_opener", build)
    monkeypatch.setattr(stt.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("urlopen follows redirects"))
    with pytest.raises(stt.InvoiceError, match="redirect refused") as error:
        stt.get_json(
            "https://api.deepgram.com/v1/projects/company/billing/breakdown",
            secret,
            {"start": "2026-04-01"},
            scheme="Token",
        )
    assert secret not in str(error.value)
    assert len(seen) == 1
    assert seen[0][0].startswith("https://api.deepgram.com/")
    assert seen[0][1] == "Token " + secret
    assert "evil.example" not in seen[0][0]


def test_missing_mount_warns_skips_and_replaces_stale_raw(stt, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    monkeypatch.setenv("FINOPS_SECRETS_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(stt, "get_json", lambda *a, **kw: pytest.fail("network must not be called"))
    raw_file = tmp_path / "stt_vendor_cost_daily.json"
    raw_file.write_text('{"providers":{"soniox":{"2026-04-01":"999"}}}')
    stt.pull(tmp_path, "2026-04-01", "2026-04-02")
    assert json.loads(raw_file.read_text()) == {"providers": {}, "skipped": ["soniox", "deepgram"]}
    assert "WARNING: soniox" in capsys.readouterr().err


def test_nested_mount_is_supported(stt, monkeypatch, tmp_path):
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    monkeypatch.setenv("FINOPS_SECRETS_DIR", str(tmp_path))
    nested = tmp_path / "SONIOX_API_KEY"
    nested.mkdir()
    (nested / "SONIOX_API_KEY").write_text("test-only")
    assert stt.optional_key("soniox") == "test-only"


def test_permission_skip_is_independent_of_other_vendor(stt, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SONIOX_API_KEY", "never-log-this")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "never-log-this-either")
    monkeypatch.setenv("FINOPS_DEEPGRAM_PROJECT_ID", "company")
    monkeypatch.setattr(stt, "soniox_costs", lambda *a: (_ for _ in ()).throw(PermissionError("private")))
    monkeypatch.setattr(
        stt,
        "deepgram_costs",
        lambda *a: {"2026-04-01": {"usd": "0.35", "unclassified_usd": "0", "status": "measured"}},
    )
    stt.pull(tmp_path, "2026-04-01", "2026-04-02")
    result = json.loads((tmp_path / "stt_vendor_cost_daily.json").read_text())
    assert result["skipped"] == ["soniox"]
    assert result["providers"] == {"deepgram": {"2026-04-01": "0.35"}}
    assert "never-log" not in capsys.readouterr().err


def test_http_error_does_not_expose_body_or_key(stt, monkeypatch):
    def deny(*args, **kwargs):
        raise urllib.error.HTTPError("private-key", 403, "private-body", {}, None)

    monkeypatch.setattr(stt.auth_http, "open_authenticated", deny)
    with pytest.raises(PermissionError) as error:
        stt.get_json("https://example.invalid", "private-key", {})
    assert "private" not in str(error.value)


def write_csv(path, rows, fields=None):
    with path.open("w") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_company_total_reaches_existing_bq_loader_and_date_replacement(stt, monkeypatch, tmp_path):
    recon = load("gcp_cost_reconciliation")
    raw = tmp_path / "raw"
    raw.mkdir()
    derived = tmp_path / "derived"
    derived.mkdir()
    invoice = raw / "stt_vendor_cost_daily.json"
    invoice.write_text(json.dumps({"providers": {"soniox": {"2026-04-01": "143.00", "2026-04-02": "0"}}}))
    longs, recons = recon.company_stt_rows(raw, ["2026-04-01", "2026-04-02"], "2026-04-01")
    assert {r["segment_type"] for r in longs} == {"total"}
    assert {r["segment"] for r in longs} == {"all"}
    assert all(r["usd_per_user_day"] is None for r in longs)
    write_csv(derived / "unit_cost_long.csv", longs)
    write_csv(derived / "unit_cost_reconciliation.csv", recons)
    write_csv(derived / "user_day_allocated.csv", [], ["date"])
    loader = load("load_bigquery")
    tables, days = loader.build_rows(derived, raw, "run-2", "2026-04-03T00:00:00Z", "2026-04-01", "2026-04-03")
    measured = tables["unit_cost_daily"]
    assert [r["usd"] for r in measured] == [143, 0]
    assert [r["inputs_settled"] for r in measured] == [True, False]
    assert tables["unit_cost_reconciliation"][0]["pool"] == "stt_soniox_measured"
    assert tables["unit_cost_reconciliation"][0]["delta_pct"] is None
    calls = []
    monkeypatch.setattr(loader, "bq", lambda args, stdin=None: calls.append((args, stdin)))
    monkeypatch.setattr(loader.subprocess, "run", lambda *a, **kw: None)
    assert loader.load_replace("unit_cost_daily", measured, days) == 2
    sql = next(stdin for _, stdin in calls if stdin)
    assert "BEGIN TRANSACTION" in sql and "DELETE FROM" in sql and "INSERT INTO" in sql
    assert "2026-04-01" in sql and "2026-04-02" in sql
    assert "stt_soniox_measured" not in sql  # replaces the whole date, no append/double counting
    invoice.write_text('{"providers":{}}')
    assert recon.company_stt_rows(raw, days, None) == ([], [])


def test_provider_entrypoint_succeeds_with_missing_stt_secrets(stt, monkeypatch, tmp_path):
    import sys

    providers = load("pull_providers")
    monkeypatch.setattr(providers, "openai_costs", lambda *a: {"data": []})
    monkeypatch.setattr(providers, "anthropic_costs", lambda *a: {"data": []})
    monkeypatch.setattr(
        sys, "argv", ["pull_providers", "--start", "2026-04-01", "--end", "2026-04-01", "--raw", str(tmp_path)]
    )
    providers.main()
    assert (tmp_path / "openai_cost_daily.json").exists()
    assert (tmp_path / "anthropic_cost_daily.json").exists()
    assert json.loads((tmp_path / "stt_vendor_cost_daily.json").read_text())["providers"] == {}


def test_offline_assembly_cli_emits_measured_company_line(stt, tmp_path):
    import subprocess
    import sys

    raw, derived = tmp_path / "raw", tmp_path / "derived"
    raw.mkdir()
    for name, value in {
        "gcp_components_daily.json": [{"usage_day": "2026-04-01", "component": "firestore_reads", "net": 1}],
        "gcp_day_resource_top.json": [],
        "gcp_day_service_sku.json": [],
        "gcp_recon.json": [{"usage_day": "2026-04-01", "net": 1}],
        "openai_cost_daily.json": {"data": []},
        "anthropic_cost_daily.json": {"data": []},
        "stt_vendor_cost_daily.json": {"providers": {"soniox": {"2026-04-01": "143.00"}}},
    }.items():
        (raw / name).write_text(json.dumps(value))
    write_csv(
        raw / "users_active_30d.csv",
        [
            {
                "uid_hash": "0123456789abcdef",
                "plan": "basic",
                "last_active_at_desktop": "2026-04-01",
                "last_active_at_mobile": "",
                "last_active_at_web": "",
            }
        ],
    )
    write_csv(raw / "ledger_user_daily.csv", [], ["date", "uid_hash"])
    write_csv(
        raw / "stt_usage_daily.csv",
        [{"date": "2026-04-01", "uid_hash": "0123456789abcdef", "transcription_seconds": 10}],
    )
    result = subprocess.run(
        [sys.executable, str(FINOPS / "assemble_unit_cost.py"), str(raw), str(derived), "2026-04-01", "2026-04-01"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rows = list(csv.DictReader((derived / "unit_cost_long.csv").open()))
    measured = [r for r in rows if r["component"] == "stt_soniox_measured"]
    assert len(measured) == 1 and float(measured[0]["usd"]) == 143
    assert measured[0]["segment_type"] == "total"
    assert "stt_soniox_measured" not in (derived / "user_day_allocated.csv").read_text()
    recon_rows = list(csv.DictReader((derived / "unit_cost_reconciliation.csv").open()))
    measured_recon = [r for r in recon_rows if r["pool"] == "stt_soniox_measured"]
    assert len(measured_recon) == 1 and measured_recon[0]["delta_pct"] == ""
