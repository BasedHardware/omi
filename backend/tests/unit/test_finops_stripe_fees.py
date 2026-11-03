"""Hermetic Stripe fee-contract tests. Synthetic API shapes only: no account
reads, identifiers, network or credentials. The book (stripe_plan_mrr.json) and
the fee artifact (stripe_fee_daily.json) are separate so a fee-leg skip can
never lose the subscription snapshot.
"""

import datetime as dt
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
def stripe(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    return load("pull_stripe")


def txn(created_epoch, fee, amount, type_="charge", currency="usd", fee_details="default"):
    return {
        "id": "txn_%d_%d" % (created_epoch, fee),
        "object": "balance_transaction",
        "created": created_epoch,
        "amount": amount,
        "fee": fee,
        # When present, fee_details is the authoritative breakdown and must sum
        # to `fee` (the producer cross-checks; see test below). By default the
        # fixture mirrors the API's own consistency.
        "fee_details": (
            (
                [
                    {
                        "amount": fee,
                        "application": None,
                        "currency": currency,
                        "description": "Stripe processing fees",
                        "type": "stripe_fee",
                    }
                ]
                if fee
                else []
            )
            if fee_details == "default"
            else fee_details
        ),
        "net": amount - fee,
        "currency": currency,
        "type": type_,
    }


def epoch(day):
    return int(dt.datetime.fromisoformat(day + "T12:00:00+00:00").timestamp())


def test_fees_sum_per_utc_day_refund_documented_shape_and_foreign_counted(stripe):
    # Refund representation follows the documented contract
    # (docs.stripe.com/api/balance_transactions/object): `fee` is "Represented
    # as a positive integer when assessed" and the funds direction lives in
    # `amount` ("A positive value represents funds charged to another party,
    # and a negative value represents funds sent to another party"). The API's
    # own documented example of a funds-out transaction carries fee 0 with
    # empty fee_details, so a refund is booked at its represented fee — 0 —
    # and never assumed to carry a negative fee (Luna r2 P2).
    page = {
        "object": "list",
        "has_more": False,
        "data": [
            txn(epoch("2026-10-01"), 441, 19900),  # charge fee $4.41
            txn(epoch("2026-10-01"), 320, 12000, type_="payment"),
            # documented funds-out shape: negative amount, fee 0, no breakdown
            # (the doc's example transaction: amount -400, fee 0, fee_details [])
            txn(epoch("2026-10-01"), 0, -9500, type_="refund", fee_details=[]),
            txn(epoch("2026-10-02"), 105, 5000, type_="payout"),
            txn(epoch("2026-10-02"), 99, 4800, currency="eur"),  # counted, never summed
        ],
    }
    rows = stripe.aggregate_fees(lambda path, **params: page, ["2026-10-01", "2026-10-02"])
    by_day = {row["date"]: row for row in rows}
    assert by_day["2026-10-01"]["fee_usd"] == 7.61  # 4.41 + 3.20 + the refund's represented fee 0
    assert by_day["2026-10-01"]["volume_usd"] == 319.0  # charge + payment gross; refunds are not volume
    assert by_day["2026-10-01"]["transaction_count"] == 3
    assert by_day["2026-10-02"]["fee_usd"] == 1.05  # EUR row excluded from sums
    assert by_day["2026-10-02"]["volume_usd"] == 0
    assert by_day["2026-10-02"]["foreign_transaction_count"] == 1
    assert "txn_" not in json.dumps(rows)  # no identifiers persist


def test_refund_fee_taken_with_its_sign_only_when_represented(stripe):
    # No refund-specific sign is invented: a non-zero fee on a refund row is
    # counted only because Stripe explicitly represents it, and it keeps the
    # sign the API gives — a returned fee arrives as whatever Stripe sends,
    # and a fee assessed on the refund arrives positive ("positive when
    # assessed", docs.stripe.com/api/balance_transactions/object).
    returned = txn(epoch("2026-10-01"), -205, -9500, type_="refund")
    assessed = txn(epoch("2026-10-02"), 150, -4000, type_="refund")
    rows = stripe.aggregate_fees(
        lambda path, **params: {"object": "list", "has_more": False, "data": [returned, assessed]},
        ["2026-10-01", "2026-10-02"],
    )
    by_day = {row["date"]: row for row in rows}
    assert by_day["2026-10-01"]["fee_usd"] == -2.05  # explicitly represented return: sign kept
    assert by_day["2026-10-02"]["fee_usd"] == 1.50  # fee assessed on a refund: positive kept
    assert by_day["2026-10-01"]["volume_usd"] == 0 and by_day["2026-10-02"]["volume_usd"] == 0


def test_fee_details_breakdown_disagreement_is_a_shape_error(stripe):
    # fee_details is the authority when present: a row whose breakdown does not
    # sum to `fee` is rejected, never summed on a guess.
    mismatch = txn(
        epoch("2026-10-01"),
        441,
        19900,
        fee_details=[
            {
                "amount": 300,
                "application": None,
                "currency": "usd",
                "description": "Stripe processing fees",
                "type": "stripe_fee",
            }
        ],
    )
    with pytest.raises(stripe.FeeUnavailable, match="fee_details"):
        stripe.aggregate_fees(
            lambda path, **params: {"object": "list", "has_more": False, "data": [mismatch]},
            ["2026-10-01"],
        )


def test_fees_paginate_with_created_window_and_exclusive_end(stripe):
    pages = [
        {
            "object": "list",
            "has_more": True,
            "data": [txn(epoch("2026-10-01"), 100, 4000), txn(epoch("2026-10-02"), 50, 2000)],
        },
        {"object": "list", "has_more": False, "data": [txn(epoch("2026-10-02"), 25, 1000)]},
    ]
    calls = []

    def get(path, **params):
        assert path == "/balance_transactions"
        calls.append(params)
        return pages.pop(0)

    rows = stripe.aggregate_fees(get, ["2026-10-01", "2026-10-02"])
    assert calls[0]["created[gte]"] == int(dt.datetime.fromisoformat("2026-10-01T00:00:00+00:00").timestamp())
    assert calls[0]["created[lt]"] == int(dt.datetime.fromisoformat("2026-10-03T00:00:00+00:00").timestamp())
    assert calls[1]["starting_after"] == "txn_%d_%d" % (epoch("2026-10-02"), 50)
    assert {row["date"]: row["fee_usd"] for row in rows} == {"2026-10-01": 1.0, "2026-10-02": 0.75}


def test_fee_scope_denial_skips_with_reason_and_never_guesses(stripe, tmp_path, capsys):
    def get(path, **params):
        raise urllib.error.HTTPError("PRIVATE_URL", 403, "PRIVATE_BODY", {}, None)

    stripe.pull_fees(get, tmp_path, "2026-10-17")
    artifact = json.loads((tmp_path / "stripe_fee_daily.json").read_text())
    assert artifact == {"status": "skipped", "reason": "permission_unavailable"}
    err = capsys.readouterr().err
    assert "balance transactions" in err and "PRIVATE" not in err
    # A prior ready artifact cannot be reused after a skipped refresh.
    (tmp_path / "stripe_fee_daily.json").write_text('{"status":"ready","rows":["old"]}')
    stripe.pull_fees(get, tmp_path, "2026-10-17")
    assert json.loads((tmp_path / "stripe_fee_daily.json").read_text())["status"] == "skipped"


def test_fee_transport_failure_skips_without_failing_the_pull(stripe, tmp_path, capsys):
    def get(path, **params):
        raise urllib.error.HTTPError("PRIVATE_URL", 500, "PRIVATE_BODY", {}, None)

    stripe.pull_fees(get, tmp_path, "2026-10-17")
    artifact = json.loads((tmp_path / "stripe_fee_daily.json").read_text())
    assert artifact == {"status": "skipped", "reason": "error"}
    assert "PRIVATE" not in capsys.readouterr().err


def test_fee_ready_artifact_covers_every_window_day_including_zero(stripe, tmp_path):
    def get(path, **params):
        return {"object": "list", "has_more": False, "data": [txn(epoch("2026-10-17"), 88, 4000)]}

    stripe.pull_fees(get, tmp_path, "2026-10-17")
    artifact = json.loads((tmp_path / "stripe_fee_daily.json").read_text())
    assert artifact["status"] == "ready"
    assert artifact["start"] == (dt.date(2026, 10, 17) - dt.timedelta(days=89)).isoformat()
    assert len(artifact["rows"]) == 90
    assert artifact["rows"][-1] == {
        "date": "2026-10-17",
        "fee_usd": 0.88,
        "volume_usd": 40.0,
        "transaction_count": 1,
        "foreign_transaction_count": 0,
    }
    assert all(row["fee_usd"] == 0 for row in artifact["rows"][:-1])  # fetched-but-zero days stay explicit


def test_fee_shape_failure_is_sanitized(stripe):
    with pytest.raises(stripe.FeeUnavailable) as error:
        stripe.aggregate_fees(
            lambda path, **params: {"object": "list", "data": [{"created": "PRIVATE"}]}, ["2026-10-01"]
        )
    assert "PRIVATE" not in str(error.value)


def test_loader_dark_when_skipped_and_strict_when_ready(stripe, tmp_path):
    loader = load("load_bigquery")
    ensured, replaced = [], []

    def replace(name, rows, dates):
        replaced.append((name, rows, dates))
        return len(rows)

    (tmp_path / "stripe_fee_daily.json").write_text('{"status":"skipped","reason":"permission_unavailable"}')
    assert loader.load_stripe_fees(tmp_path, "run-1", "t", ensured.append, replace) == {}
    assert ensured == [] and replaced == []

    rows = [
        {
            "date": "2026-10-01",
            "fee_usd": -1.25,
            "volume_usd": 0,
            "transaction_count": 1,
            "foreign_transaction_count": 0,
        },
        {
            "date": "2026-10-02",
            "fee_usd": 4.4,
            "volume_usd": 190.0,
            "transaction_count": 2,
            "foreign_transaction_count": 0,
        },
    ]
    (tmp_path / "stripe_fee_daily.json").write_text(
        json.dumps({"status": "ready", "start": "2026-10-01", "end": "2026-10-02", "rows": rows})
    )
    result = loader.load_stripe_fees(tmp_path, "run-2", "t", ensured.append, replace)
    assert ensured == ["stripe_fee_daily"]
    assert replaced[0][0] == "stripe_fee_daily"
    assert replaced[0][1][0]["fee_usd"] == -1.25  # a day net of an explicitly represented fee return stays negative
    assert replaced[0][1][0]["run_id"] == "run-2"
    assert replaced[0][2] == ["2026-10-01", "2026-10-02"]

    (tmp_path / "stripe_fee_daily.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "start": "2026-10-01",
                "end": "2026-10-02",
                "rows": rows
                + [
                    {
                        "date": "2099-01-01",
                        "fee_usd": 1,
                        "volume_usd": 1,
                        "transaction_count": 1,
                        "foreign_transaction_count": 0,
                    }
                ],
            }
        )
    )
    with pytest.raises(SystemExit, match="invalid Stripe fee aggregate"):
        loader.load_stripe_fees(tmp_path, "run-3", "t", ensured.append, replace)
