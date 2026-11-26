"""Hermetic vendor-balance contract tests: Soniox org-key balance snapshots
and the consecutive-snapshot day-rate math. No network, no account reads, no
credentials. Fixtures use the published balance response shape (strings)."""

import datetime as dt
from decimal import Decimal
import importlib.util
import io
import json
import pathlib
import re
import urllib.error

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"


def load(name):
    spec = importlib.util.spec_from_file_location("test_" + name, FINOPS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def vb(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    monkeypatch.delenv("FINOPS_SONIOX_ORG_KEY", raising=False)
    return load("pull_vendor_balance")


BALANCE = {
    "used_balance_usd": "10427.62",
    "available_balance_usd": "1572.38",
    "invoice_billing_enabled": False,
}


# ---------------------------------------------------------------- string parsing


def test_parse_balance_accepts_string_amounts(vb):
    parsed = vb.parse_balance(BALANCE)
    assert parsed == {
        "used_usd": "10427.62",
        "available_usd": "1572.38",
        "invoice_billing_enabled": False,
    }


def test_parse_balance_accepts_numeric_amounts_leniently(vb):
    parsed = vb.parse_balance({**BALANCE, "used_balance_usd": 12.5, "available_balance_usd": 0})
    assert parsed["used_usd"] == "12.5"
    assert parsed["available_usd"] == "0"


NUMERIC_RE = r"^\d{1,29}(\.\d{1,9})?$"  # what a BigQuery NUMERIC load accepts from JSON text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("10427.6212345678901234", "10427.621234568"),  # more than nine fractional digits rounds
        ("0.0000000005", "0.000000001"),  # half rounds up, the table's documented policy
        ("0.0000000004", "0.000000000"),
        ("1E-12", "0.000000000"),  # exponent notation never reaches the table
        ("1E+3", "1000"),
        ("12.5", "12.5"),  # short values keep their digits
        ("0", "0"),
        ("99999999999999999999999999999.9999999994", "99999999999999999999999999999.999999999"),
    ],
)
def test_parse_balance_renders_numeric_safe_strings(vb, raw, expected):
    parsed = vb.parse_balance({**BALANCE, "used_balance_usd": raw, "available_balance_usd": raw})
    assert parsed["used_usd"] == expected and parsed["available_usd"] == expected
    assert re.match(NUMERIC_RE, parsed["used_usd"])


@pytest.mark.parametrize(
    "raw",
    [
        "100000000000000000000000000000",
        "1E+40",
        "99999999999999999999999999999.9999999996",  # rounds up to 10**29, which NUMERIC cannot hold
    ],
)
def test_parse_balance_rejects_values_outside_the_numeric_range(vb, raw):
    with pytest.raises(vb.BalanceError) as err:
        vb.parse_balance({**BALANCE, "used_balance_usd": raw})
    assert err.value.reason == "invalid_response"


@pytest.mark.parametrize(
    "payload",
    [
        {"used_balance_usd": "-1", "available_balance_usd": "1", "invoice_billing_enabled": False},
        {"used_balance_usd": "nan", "available_balance_usd": "1", "invoice_billing_enabled": False},
        {"used_balance_usd": "abc", "available_balance_usd": "1", "invoice_billing_enabled": False},
        {"used_balance_usd": True, "available_balance_usd": "1", "invoice_billing_enabled": False},
        {"used_balance_usd": "1"},  # missing keys / missing flag
        {"available_balance_usd": "1", "invoice_billing_enabled": True},
        {"used_balance_usd": "1", "available_balance_usd": "1", "invoice_billing_enabled": "no"},
        ["not", "an", "object"],
    ],
)
def test_parse_balance_rejects_invalid_shapes(vb, payload):
    with pytest.raises(vb.BalanceError):
        vb.parse_balance(payload)


# ---------------------------------------------------------------- pull + fallback


def test_pull_skips_without_key_and_never_fails_the_job(vb, tmp_path, capsys):
    vb.pull(tmp_path)
    artifact = json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())
    assert artifact == {"status": "skipped", "reason": "key_unavailable"}
    err = capsys.readouterr().err
    assert "WARNING" in err and "key_unavailable" in err


def test_pull_skips_on_permission_and_on_error(vb, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FINOPS_SONIOX_ORG_KEY", "org-key-value")

    def denied(key):
        raise PermissionError("no")

    monkeypatch.setattr(vb, "fetch_balance", denied)
    vb.pull(tmp_path)
    assert json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())["reason"] == "permission_unavailable"
    assert "permission_unavailable" in capsys.readouterr().err

    def broken(key):
        raise vb.BalanceError("http_error", "balance HTTP 500", http_status=500)

    monkeypatch.setattr(vb, "fetch_balance", broken)
    vb.pull(tmp_path)
    artifact = json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())
    assert artifact == {"status": "skipped", "reason": "http_error", "http_status": 500}
    err = capsys.readouterr().err
    assert "http_error" in err and "http_status=500" in err


@pytest.mark.parametrize(
    "reason",
    [
        "key_unavailable",
        "permission_unavailable",
        "redirect_refused",
        "http_error",
        "transport_error",
        "invalid_response",
    ],
)
def test_every_skip_reason_is_bounded_and_logged(vb, tmp_path, monkeypatch, capsys, reason):
    assert reason in vb.SKIP_REASONS
    monkeypatch.setenv("FINOPS_SONIOX_ORG_KEY", "org-key-value")

    def broken(key):
        raise vb.BalanceError(reason, "synthetic detail")

    monkeypatch.setattr(vb, "fetch_balance", broken)
    vb.pull(tmp_path)
    artifact = json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())
    assert artifact == {"status": "skipped", "reason": reason}
    assert reason in capsys.readouterr().err


def test_balance_error_refuses_an_unbounded_reason(vb):
    with pytest.raises(ValueError, match="unbounded"):
        vb.BalanceError("Bearer sk-live-SENTINEL", "detail")
    with pytest.raises(ValueError, match="unbounded"):
        vb.write_skip(pathlib.Path("unused.json"), "raw vendor response")


def test_pull_writes_parsed_numbers_only_and_stays_idempotent(vb, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FINOPS_SONIOX_ORG_KEY", "org-key-value")
    monkeypatch.setattr(vb, "fetch_balance", lambda key: vb.parse_balance(BALANCE))
    now = dt.datetime(2026, 10, 22, 14, 30, tzinfo=dt.timezone.utc)
    vb.pull(tmp_path, now=now)
    artifact = json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())
    assert artifact == {
        "status": "ready",
        "vendor": "soniox",
        "ts": "2026-10-22T14:30:00Z",
        "used_usd": "10427.62",
        "available_usd": "1572.38",
        "invoice_billing_enabled": False,
    }
    err = capsys.readouterr().err
    assert "10427.62" in err and "1572.38" in err
    # the key never appears in any log line
    assert "org-key-value" not in err


def test_pull_never_logs_the_key_even_on_transport_paths(vb, tmp_path, monkeypatch, capsys):
    secret = "soniox-org-secret-DO-NOT-PRINT"
    monkeypatch.setenv("FINOPS_SONIOX_ORG_KEY", secret)

    def boom(key):
        raise vb.BalanceError("transport_error", "balance transport/JSON failure")

    monkeypatch.setattr(vb, "fetch_balance", boom)
    vb.pull(tmp_path)
    out = capsys.readouterr()
    assert secret not in out.err and secret not in out.out
    assert (tmp_path / "vendor_balance_snapshot.json").read_text().find(secret) == -1


def test_pull_never_logs_a_raw_response_or_request_url(vb, tmp_path, monkeypatch, capsys):
    """An HTTPError carries the URL and body; only its integer status may escape."""
    import auth_http

    secret = "soniox-org-secret-DO-NOT-PRINT"
    body = b'{"error":"raw vendor body SENTINEL-BODY","key":"' + secret.encode() + b'"}'
    monkeypatch.setenv("FINOPS_SONIOX_ORG_KEY", secret)

    class ErrorOpener:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError(
                vb.BALANCE_URL + "?token=" + secret,
                404,
                "x",
                {"Authorization": "Bearer " + secret},
                io.BytesIO(body),
            )

    monkeypatch.setattr(auth_http, "build_opener", lambda *a, **k: ErrorOpener())
    vb.pull(tmp_path)
    out = capsys.readouterr()
    artifact = (tmp_path / "vendor_balance_snapshot.json").read_text()
    for leaked in (secret, "SENTINEL-BODY", "token=", "Authorization"):
        assert leaked not in out.err and leaked not in out.out and leaked not in artifact
    assert json.loads(artifact) == {"status": "skipped", "reason": "http_error", "http_status": 404}
    assert "http_error" in out.err and "http_status=404" in out.err


def test_fetch_balance_classifies_permission_and_http_errors(vb, monkeypatch):
    import auth_http

    class ErrorOpener:
        def __init__(self, code):
            self.code = code

        def open(self, req, timeout=None):
            raise urllib.error.HTTPError(vb.BALANCE_URL, self.code, "x", {}, None)

    monkeypatch.setattr(auth_http, "build_opener", lambda *a, **k: ErrorOpener(403))
    with pytest.raises(PermissionError):
        vb.fetch_balance("k")

    monkeypatch.setattr(auth_http, "build_opener", lambda *a, **k: ErrorOpener(500))
    with pytest.raises(vb.BalanceError) as caught:
        vb.fetch_balance("k")
    assert caught.value.reason == "http_error" and caught.value.http_status == 500


# ---------------------------------------------------------------- daily job surfacing


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    return load("run_unit_cost")


def test_daily_job_surfaces_the_bounded_skip_reason(runner, tmp_path, capsys):
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps({"status": "skipped", "reason": "http_error", "http_status": 404})
    )
    runner.log_vendor_balance_skip(tmp_path, set())
    err = capsys.readouterr().err
    assert "WARNING: Soniox balance snapshot skipped: http_error http_status=404" in err


def test_daily_job_never_echoes_artifact_free_text(runner, tmp_path, capsys):
    sentinel = "Bearer sk-live-SENTINEL /v1/organization/balance?token=abc"
    (tmp_path / "vendor_balance_snapshot.json").write_text(json.dumps({"status": "skipped", "reason": sentinel}))
    runner.log_vendor_balance_skip(tmp_path, set())
    err = capsys.readouterr().err
    assert "reason_unrecognized" in err
    assert sentinel not in err and "SENTINEL" not in err and "token=" not in err


@pytest.mark.parametrize(
    "reason",
    [
        ["http_error", "Bearer sk-live-SENTINEL"],
        {"code": "http_error", "url": "/v1/organization/balance?token=abc"},
        ["SENTINEL-BODY"],
        {"SENTINEL-BODY": "raw vendor response"},
    ],
)
def test_daily_job_bounds_unhashable_artifact_reasons(runner, tmp_path, capsys, reason):
    """A JSON array/object reason is unhashable; membership must not raise TypeError."""
    (tmp_path / "vendor_balance_snapshot.json").write_text(json.dumps({"status": "skipped", "reason": reason}))
    runner.log_vendor_balance_skip(tmp_path, set())
    err = capsys.readouterr().err
    assert "reason_unrecognized" in err
    for leaked in ("SENTINEL", "token=", "Bearer", "http_error"):
        assert leaked not in err


def test_daily_job_reports_an_unreadable_artifact(runner, tmp_path, capsys):
    (tmp_path / "vendor_balance_snapshot.json").write_text("{not json")
    runner.log_vendor_balance_skip(tmp_path, set())
    assert "artifact_unreadable" in capsys.readouterr().err


def test_daily_job_reports_a_missing_artifact_only_when_balance_ran(runner, tmp_path, capsys):
    runner.log_vendor_balance_skip(tmp_path, set())
    assert "artifact_missing" in capsys.readouterr().err
    runner.log_vendor_balance_skip(tmp_path, {"balance"})
    assert capsys.readouterr().err == ""


def test_daily_job_stays_quiet_on_a_ready_artifact(runner, tmp_path, capsys):
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "vendor": "soniox",
                "ts": "2026-10-22T14:30:00Z",
                "used_usd": "100",
                "available_usd": "50",
                "invoice_billing_enabled": False,
            }
        )
    )
    runner.log_vendor_balance_skip(tmp_path, set())
    assert capsys.readouterr().err == ""


def test_daily_job_ignores_a_non_integer_http_status(runner, tmp_path, capsys):
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps({"status": "skipped", "reason": "http_error", "http_status": "404 SENTINEL"})
    )
    runner.log_vendor_balance_skip(tmp_path, set())
    err = capsys.readouterr().err
    assert "http_error" in err and "SENTINEL" not in err and "http_status" not in err


# ---------------------------------------------------------------- delta math


def snap(day, used, hour=14, minute=30):
    return {"ts": "%sT%02d:%02d:00Z" % (day, hour, minute), "used_usd": used}


def test_deltas_consecutive_daily_snapshots(vb):
    rows = vb.daily_deltas([snap("2026-10-20", "100"), snap("2026-10-21", "130"), snap("2026-10-22", "180")])
    assert [(r["date"], r["usd"], r["flag"]) for r in rows] == [
        ("2026-10-21", "30.000000000", ""),
        ("2026-10-22", "50.000000000", ""),
    ]


def test_deltas_single_snapshot_establishes_baseline_only(vb):
    assert vb.daily_deltas([snap("2026-10-22", "10427.62")]) == []


def test_deltas_missing_day_spreads_and_flags(vb):
    rows = vb.daily_deltas([snap("2026-10-19", "100"), snap("2026-10-22", "160")])
    assert [(r["date"], r["usd"], r["flag"]) for r in rows] == [
        ("2026-10-20", "20.000000000", vb.GAP_FLAG),
        ("2026-10-21", "20.000000000", vb.GAP_FLAG),
        ("2026-10-22", "20.000000000", vb.GAP_FLAG),
    ]


def test_deltas_lower_value_is_new_baseline_and_flagged(vb):
    rows = vb.daily_deltas([snap("2026-10-20", "500"), snap("2026-10-21", "120"), snap("2026-10-22", "150")])
    assert rows[0] == {
        "date": "2026-10-21",
        "vendor": "soniox",
        "usd": None,
        "flag": vb.RESET_FLAG,
        "interval_start": "2026-10-20T14:30:00Z",
        "interval_end": "2026-10-21T14:30:00Z",
    }
    # the reset value becomes the baseline: the next interval measures from it
    assert rows[1]["date"] == "2026-10-22"
    assert Decimal(rows[1]["usd"]) == Decimal("30")


def test_deltas_same_day_snapshots_both_attribute_to_that_day(vb):
    rows = vb.daily_deltas([snap("2026-10-22", "100", 10, 0), snap("2026-10-22", "110", 18, 0)])
    assert [(r["date"], r["usd"]) for r in rows] == [("2026-10-22", "10.000000000")]


def test_deltas_unsorted_input_is_ordered_by_ts(vb):
    rows = vb.daily_deltas([snap("2026-10-22", "180"), snap("2026-10-21", "130"), snap("2026-10-20", "100")])
    assert [r["date"] for r in rows] == ["2026-10-21", "2026-10-22"]


def test_deltas_decimal_string_inputs(vb):
    rows = vb.daily_deltas([snap("2026-10-20", "10427.62"), snap("2026-10-21", "10571.88")])
    assert Decimal(rows[0]["usd"]) == Decimal("144.26")


# ---------------------------------------------------------------- loader dark path


def test_deltas_never_emit_exponent_notation_or_overflow_the_context(vb):
    # a zero delta quantizes to 0E-9 without the renderer; the readback strings are NUMERIC text
    zero = vb.daily_deltas([snap("2026-10-20", "100.000000000"), snap("2026-10-21", "100.000000000")])
    assert re.match(NUMERIC_RE, zero[0]["usd"]) and "E" not in zero[0]["usd"]
    # a 29-integer-digit value divides and rounds under the default 28-digit context otherwise
    big = vb.daily_deltas([snap("2026-10-20", "0"), snap("2026-10-22", "99999999999999999999999999999.999999999")])
    assert len(big) == 2 and all(re.match(NUMERIC_RE, row["usd"]) for row in big)
    # the subtraction itself must not round at the default 28 digits: a one-day delta
    # of 99999999999999999999999999999.999999999 stays in range
    one_day = vb.daily_deltas([snap("2026-10-20", "0"), snap("2026-10-21", "99999999999999999999999999999.999999999")])
    assert one_day[0]["usd"] == "99999999999999999999999999999.999999999"
    # a repeating share rounds to nine places
    third = vb.daily_deltas([snap("2026-10-20", "0"), snap("2026-10-23", "1")])
    assert [row["usd"] for row in third] == ["0.333333333"] * 3


def test_loader_skips_an_out_of_range_artifact_instead_of_failing_the_job(vb, tmp_path, capsys):
    lb = load("load_bigquery")
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "vendor": "soniox",
                "ts": "2026-10-23T14:30:00Z",
                "used_usd": "100000000000000000000000000000",
                "available_usd": "1",
                "invoice_billing_enabled": False,
            }
        )
    )
    created = []
    assert lb.load_vendor_balance(tmp_path, "r1", "t", created.append, lambda *a, **k: 0, lambda *a, **k: "[]") == {}
    assert created == []
    assert "skipped: invalid_response" in capsys.readouterr().err


def test_loader_dark_paths(vb, tmp_path, monkeypatch):
    lb = load("load_bigquery")
    created, replaced = [], []

    def ensure_table(name):
        created.append(name)

    def load_replace(name, rows, dates, extra_delete=""):
        replaced.append((name, len(rows)))
        return len(rows)

    # absent artifact and skipped artifact: nothing read, nothing created
    assert lb.load_vendor_balance(tmp_path, "r1", "t", ensure_table, load_replace, lambda *a, **k: "") == {}
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps({"status": "skipped", "reason": "key_unavailable"})
    )
    assert lb.load_vendor_balance(tmp_path, "r1", "t", ensure_table, load_replace, lambda *a, **k: "") == {}
    assert created == [] and replaced == []

    # ready artifact with only one stored snapshot (the new one): snapshot row
    # loads, no spend rows are derived yet
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "vendor": "soniox",
                "ts": "2026-10-22T14:30:00Z",
                "used_usd": "100",
                "available_usd": "50",
                "invoice_billing_enabled": False,
            }
        )
    )

    def bq_query(args, stdin=None):
        assert "vendor_balance_snapshot" in stdin
        return json.dumps([{"ts": "2026-10-22T14:30:00Z", "used_usd": "100"}])

    loaded = lb.load_vendor_balance(tmp_path, "r1", "t", ensure_table, load_replace, bq_query)
    assert created == ["vendor_balance_snapshot"]
    assert loaded == {"vendor_balance_snapshot": 1}


def test_loader_only_sends_numeric_safe_money_to_bigquery(vb, tmp_path):
    """Regression for the first real daily run: the vendor's decimals carried more
    than nine fractional digits and BigQuery rejected used_usd as an invalid NUMERIC.
    Even an artifact written by an older image must be re-rendered before the load."""
    lb = load("load_bigquery")
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "vendor": "soniox",
                "ts": "2026-10-23T14:30:00Z",
                "used_usd": "10571.8812345678901234",
                "available_usd": "1428.1187654321098766",
                "invoice_billing_enabled": False,
            }
        )
    )
    sent = {}

    def load_replace(name, rows, dates, extra_delete=""):
        sent[name] = rows
        return len(rows)

    def bq_query(args, stdin=None):
        return json.dumps(
            [
                {"ts": "2026-10-22T14:30:00Z", "used_usd": "10427.620000000"},
                {"ts": "2026-10-23T14:30:00Z", "used_usd": "10571.881234568"},
            ]
        )

    lb.load_vendor_balance(tmp_path, "r1", "t", lambda n: None, load_replace, bq_query)
    row = sent["vendor_balance_snapshot"][0]
    assert row["used_usd"] == "10571.881234568" and row["available_usd"] == "1428.118765432"
    assert re.match(NUMERIC_RE, row["used_usd"]) and re.match(NUMERIC_RE, row["available_usd"])
    for spend in sent["vendor_balance_spend_daily"]:
        assert spend["usd"] is None or re.match(NUMERIC_RE, spend["usd"])


def test_loader_rejects_tampered_artifacts(vb, tmp_path):
    lb = load("load_bigquery")
    (tmp_path / "vendor_balance_snapshot.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "vendor": "other-vendor",
                "ts": "2026-10-22T14:30:00Z",
                "used_usd": "1",
                "available_usd": "1",
                "invoice_billing_enabled": True,
            }
        )
    )
    with pytest.raises(SystemExit, match="unknown vendor"):
        lb.load_vendor_balance(tmp_path, "r1", "t", lambda n: None, lambda *a, **k: 0, lambda *a, **k: "[]")


# ------------------------------------------------------------- CLI entry point


def test_script_entry_writes_an_artifact_when_run_as_the_job_runs_it(tmp_path):
    """The daily job runs this file as a subprocess. With no org key it must still
    leave a `skipped` artifact (a missing artifact is indistinguishable from a
    script that never ran, and left the snapshot table uncreated)."""
    import subprocess
    import sys

    env = {k: v for k, v in __import__("os").environ.items() if k != "FINOPS_SONIOX_ORG_KEY"}
    env.pop("FINOPS_AUTH", None)
    done = subprocess.run(
        [sys.executable, str(FINOPS / "pull_vendor_balance.py"), "--raw", str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(FINOPS),
    )
    assert done.returncode == 0, done.stderr
    artifact = json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())
    assert artifact == {"status": "skipped", "reason": "key_unavailable"}
