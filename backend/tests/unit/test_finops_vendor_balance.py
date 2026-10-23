"""Hermetic vendor-balance contract tests: Soniox org-key balance snapshots
and the consecutive-snapshot day-rate math. No network, no account reads, no
credentials. Fixtures use the published balance response shape (strings)."""

import datetime as dt
from decimal import Decimal
import importlib.util
import json
import pathlib
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
    assert "WARNING" in capsys.readouterr().err


def test_pull_skips_on_permission_and_on_error(vb, tmp_path, monkeypatch):
    monkeypatch.setenv("FINOPS_SONIOX_ORG_KEY", "org-key-value")

    def denied(key):
        raise PermissionError("no")

    monkeypatch.setattr(vb, "fetch_balance", denied)
    vb.pull(tmp_path)
    assert json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())["reason"] == "permission_unavailable"

    def broken(key):
        raise vb.BalanceError("balance HTTP 500")

    monkeypatch.setattr(vb, "fetch_balance", broken)
    vb.pull(tmp_path)
    assert json.loads((tmp_path / "vendor_balance_snapshot.json").read_text())["reason"] == "error"


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
        raise vb.BalanceError("balance transport/JSON failure")

    monkeypatch.setattr(vb, "fetch_balance", boom)
    vb.pull(tmp_path)
    out = capsys.readouterr()
    assert secret not in out.err and secret not in out.out
    assert (tmp_path / "vendor_balance_snapshot.json").read_text().find(secret) == -1


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
    with pytest.raises(vb.BalanceError):
        vb.fetch_balance("k")


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
