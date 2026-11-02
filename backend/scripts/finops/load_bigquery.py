#!/usr/bin/env python3
"""Load an assembled run into `based-hardware.omi_finops`.

Writes run as finops-writer@based-hardware (verified by name first); every read in the
pipeline runs as the read-only bot. Loads are IDEMPOTENT per date: rows for the dates in
this run are deleted and re-inserted inside one BigQuery transaction, so re-running a date
replaces it rather than doubling it.

Tables (all partitioned by `date`, no partition expiry):
  unit_cost_daily          long format: date x segment_type x segment x component x method
  unit_cost_reconciliation what each pool cost vs what landed on user-days
  plan_revenue_daily       Stripe snapshot, carrying snapshot_date so it stays honest
  unit_cost_user_day       per (date, uid_hash) allocation. HASHED uids only, never raw.
  mercury_*                vendor-spend aggregates (load_mercury; dark when Mercury is off)
  stripe_fee_daily         measured Stripe processing fees (dark while the fee scope is missing)
  vendor_balance_snapshot  Soniox prepaid-balance snapshots (dark while the org key is off)
  vendor_balance_spend_daily  daily spend derived from consecutive snapshots
  stt_modulate_modelled_daily modelled Modulate STT cost (Prometheus seconds x committed price)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from assemble_unit_cost import COMPS  # noqa: E402
import load_mercury  # noqa: E402

AUTH_MODE = os.environ.get("FINOPS_AUTH", "local")  # 'local' (laptop cron) | 'cloudrun'
if AUTH_MODE == "cloudrun":
    import cloudrun  # noqa: E402

    PROJECT = cloudrun.PROJECT
    assert_writer_identity = cloudrun.assert_runtime_identity
else:
    from gcpauth import PROJECT, assert_writer_identity  # noqa: E402

DATASET = "omi_finops"
LOCATION = "US"  # same location as gcp_billing_export, so the two can be joined

SCHEMAS = {
    "unit_cost_daily": [
        ("date", "DATE"),
        ("segment_type", "STRING"),
        ("segment", "STRING"),
        ("component", "STRING"),
        ("method", "STRING"),
        ("usd", "FLOAT64"),
        ("users", "INT64"),
        ("usd_per_user_day", "FLOAT64"),
        ("run_id", "STRING"),
        ("computed_at", "TIMESTAMP"),
        ("inputs_settled", "BOOL"),
    ],
    "unit_cost_reconciliation": [
        ("date", "DATE"),
        ("pool", "STRING"),
        ("pool_usd", "FLOAT64"),
        ("allocated_usd", "FLOAT64"),
        ("delta_pct", "FLOAT64"),
        ("invoice_source", "STRING"),
        ("note", "STRING"),
        ("run_id", "STRING"),
        ("computed_at", "TIMESTAMP"),
        ("inputs_settled", "BOOL"),
    ],
    "plan_revenue_daily": [
        ("date", "DATE"),
        ("plan", "STRING"),
        ("paying_subs", "INT64"),
        ("trialing_subs", "INT64"),
        ("mrr_usd", "FLOAT64"),
        ("arpu_usd", "FLOAT64"),
        ("snapshot_date", "DATE"),
        ("run_id", "STRING"),
        ("computed_at", "TIMESTAMP"),
        # Added 2026-10-22 (nullable; `ensure_table` reconciles the live table before the load).
        # Book-wide distinct counts repeated on every plan row of a snapshot.
        ("paying_customers", "INT64"),
        ("non_usd_paying_subs", "INT64"),
    ],
    "unit_cost_user_day": [
        ("date", "DATE"),
        ("uid_hash", "STRING"),
        ("cohort", "STRING"),
        ("plan", "STRING"),
        ("attempts", "INT64"),
        ("unpriced_attempts", "INT64"),
        ("tx_sec", "FLOAT64"),
    ]
    + [(c, "FLOAT64") for c in COMPS]
    + [
        ("run_id", "STRING"),
        ("computed_at", "TIMESTAMP"),
        ("inputs_settled", "BOOL"),
    ],
}
CLUSTER = {
    "unit_cost_daily": ["segment_type", "segment", "component"],
    "unit_cost_reconciliation": ["pool"],
    "plan_revenue_daily": ["plan"],
    "unit_cost_user_day": ["cohort", "plan"],
}

SCHEMAS.update(load_mercury.SCHEMAS)
CLUSTER.update(load_mercury.CLUSTER)

# Measured Stripe processing fees (net of refunds), refreshed with the daily run
# from balance transactions. Dark while the restricted key lacks the scope: a
# skipped artifact means no table reads, writes or creation, exactly like Mercury.
SCHEMAS["stripe_fee_daily"] = [
    ("date", "DATE"),
    ("fee_usd", "NUMERIC"),
    ("volume_usd", "NUMERIC"),
    ("transaction_count", "INT64"),
    ("foreign_transaction_count", "INT64"),
    ("run_id", "STRING"),
    ("computed_at", "TIMESTAMP"),
]
CLUSTER["stripe_fee_daily"] = ["run_id"]
STRIPE_FEE_KEYS = {"date", "fee_usd", "volume_usd", "transaction_count", "foreign_transaction_count"}

# Soniox prepaid-balance snapshots (the org key has no usage/invoice API) and
# the per-UTC-day spend derived from consecutive snapshots. Dark while the org
# key is unmounted: a skipped artifact creates and writes nothing.
SCHEMAS["vendor_balance_snapshot"] = [
    ("date", "DATE"),
    ("ts", "TIMESTAMP"),
    ("vendor", "STRING"),
    ("used_usd", "NUMERIC"),
    ("available_usd", "NUMERIC"),
    ("invoice_billing_enabled", "BOOL"),
    ("run_id", "STRING"),
    ("computed_at", "TIMESTAMP"),
]
CLUSTER["vendor_balance_snapshot"] = ["vendor"]
SNAPSHOT_KEYS = {"status", "vendor", "ts", "used_usd", "available_usd", "invoice_billing_enabled"}
SCHEMAS["vendor_balance_spend_daily"] = [
    ("date", "DATE"),
    ("vendor", "STRING"),
    ("usd", "NUMERIC"),
    ("flag", "STRING"),
    ("interval_start", "TIMESTAMP"),
    ("interval_end", "TIMESTAMP"),
    ("run_id", "STRING"),
    ("computed_at", "TIMESTAMP"),
]
CLUSTER["vendor_balance_spend_daily"] = ["vendor", "flag"]

# Modelled Modulate STT cost: measured Prometheus audio seconds x the committed
# rate-card price. Dark while either input is missing; never a guessed number.
SCHEMAS["stt_modulate_modelled_daily"] = [
    ("date", "DATE"),
    ("audio_seconds", "FLOAT64"),
    ("usd", "NUMERIC"),
    ("price_usd_per_hour", "NUMERIC"),
    ("price_as_of", "DATE"),
    ("method", "STRING"),
    ("run_id", "STRING"),
    ("computed_at", "TIMESTAMP"),
]
CLUSTER["stt_modulate_modelled_daily"] = ["run_id"]
MODULATE_ROW_KEYS = {"date", "audio_seconds", "usd"}


def load_stripe_fees(raw: pathlib.Path, run_id: str, computed_at: str, ensure_table, load_replace) -> dict:
    path = raw / "stripe_fee_daily.json"
    if not path.exists():
        return {}
    snapshot = json.loads(path.read_text())
    if snapshot.get("status") == "skipped":
        return {}  # unavailable is not zero: no rows, no table creation, no guess
    if set(snapshot) != {"status", "start", "end", "rows"} or snapshot["status"] != "ready":
        raise SystemExit("invalid Stripe fee artifact")
    window = set(load_mercury.days(snapshot["start"], snapshot["end"]))
    for row in snapshot["rows"]:
        if set(row) != STRIPE_FEE_KEYS or row["date"] not in window:
            raise SystemExit("invalid Stripe fee aggregate")
        counts = (row["transaction_count"], row["foreign_transaction_count"])
        if any(type(c) is not int or c < 0 for c in counts):
            raise SystemExit("invalid Stripe fee counts")
        if row["volume_usd"] is None or float(row["volume_usd"]) < 0:
            raise SystemExit("invalid Stripe fee volume")
        # fee_usd may be negative: refunds return fees on their own day.
    dates = sorted(window)
    ensure_table("stripe_fee_daily")
    rows = [dict(row, run_id=run_id, computed_at=computed_at) for row in snapshot["rows"]]
    return {"stripe_fee_daily": load_replace("stripe_fee_daily", rows, dates)}


def load_vendor_balance(raw: pathlib.Path, run_id: str, computed_at: str, ensure_table, load_replace, bq) -> dict:
    """Insert today's Soniox balance snapshot, then republish the derived daily
    spend over the trailing snapshot window (recomputed whole, so the spread and
    reset rules can change without backfilling). Dark while the artifact is
    skipped: no table reads, writes or creation."""
    import pull_vendor_balance

    path = raw / "vendor_balance_snapshot.json"
    if not path.exists():
        return {}
    snapshot = json.loads(path.read_text())
    if snapshot.get("status") == "skipped":
        return {}
    if set(snapshot) != SNAPSHOT_KEYS or snapshot["status"] != "ready":
        raise SystemExit("invalid vendor balance artifact")
    if snapshot["vendor"] != pull_vendor_balance.VENDOR:
        raise SystemExit("unknown vendor balance vendor")
    if not str(snapshot["ts"]).endswith("Z"):
        raise SystemExit("vendor balance ts must be UTC ISO with Z")
    pull_vendor_balance.usd(snapshot["used_usd"])
    pull_vendor_balance.usd(snapshot["available_usd"])
    if type(snapshot["invoice_billing_enabled"]) is not bool:
        raise SystemExit("invalid vendor balance invoice flag")
    vendor = snapshot["vendor"]
    day = snapshot["ts"][:10]
    ensure_table("vendor_balance_snapshot")
    loaded = {
        "vendor_balance_snapshot": load_replace(
            "vendor_balance_snapshot",
            [dict(snapshot, date=day, run_id=run_id, computed_at=computed_at)],
            [day],
            extra_delete=" AND vendor = '%s'" % vendor,
        )
    }
    # Read the trailing snapshots back (including this run's) and rederive spend.
    sql = (
        "SELECT FORMAT_TIMESTAMP('%%Y-%%m-%%dT%%H:%%M:%%SZ', ts) AS ts, used_usd "
        "FROM `%s.%s.vendor_balance_snapshot` "
        "WHERE vendor = '%s' AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL 40 DAY) "
        "ORDER BY ts"
    ) % (PROJECT, DATASET, vendor)
    rows = json.loads(bq(["query", "--use_legacy_sql=false", "--format=json"], stdin=sql))
    deltas = pull_vendor_balance.daily_deltas(rows)
    if not deltas:
        return loaded  # first snapshot: baseline only, no spend rows yet
    for row in deltas:
        if not {"date", "vendor", "usd", "flag", "interval_start", "interval_end"} <= set(row):
            raise SystemExit("invalid vendor balance delta row")
    dates = sorted({row["date"] for row in deltas})
    ensure_table("vendor_balance_spend_daily")
    loaded["vendor_balance_spend_daily"] = load_replace(
        "vendor_balance_spend_daily",
        [dict(row, run_id=run_id, computed_at=computed_at) for row in deltas],
        dates,
        extra_delete=" AND vendor = '%s'" % vendor,
    )
    return loaded


def load_modulate_modelled(raw: pathlib.Path, run_id: str, computed_at: str, ensure_table, load_replace) -> dict:
    path = raw / "stt_modulate_modelled_daily.json"
    if not path.exists():
        return {}
    artifact = json.loads(path.read_text())
    if artifact.get("status") == "skipped":
        return {}
    required = {"status", "method", "price_usd_per_hour", "price_source", "price_as_of", "rows"}
    if set(artifact) != required or artifact["status"] != "ready" or artifact["method"] != "modelled":
        raise SystemExit("invalid Modulate modelled artifact")
    dt.date.fromisoformat(artifact["price_as_of"])
    if float(artifact["price_usd_per_hour"]) <= 0:
        raise SystemExit("invalid Modulate modelled price")
    for row in artifact["rows"]:
        if set(row) != MODULATE_ROW_KEYS:
            raise SystemExit("invalid Modulate modelled row")
        if float(row["audio_seconds"]) < 0 or float(row["usd"]) < 0:
            raise SystemExit("invalid Modulate modelled amounts")
    dates = sorted({row["date"] for row in artifact["rows"]})
    ensure_table("stt_modulate_modelled_daily")
    rows = [
        dict(
            row,
            price_usd_per_hour=artifact["price_usd_per_hour"],
            price_as_of=artifact["price_as_of"],
            method="modelled",
            run_id=run_id,
            computed_at=computed_at,
        )
        for row in artifact["rows"]
    ]
    return {"stt_modulate_modelled_daily": load_replace("stt_modulate_modelled_daily", rows, dates)}


def _bq_cmd() -> list[str]:
    """The `bq` command prefix: real CLI locally, the ADC stub on Cloud Run."""
    if AUTH_MODE == "cloudrun":
        return [sys.executable, str(HERE / "bq_stub.py")]
    return ["bq"]


def bq(args: list[str], stdin: str | None = None, timeout: int = 1800) -> str:
    p = subprocess.run(
        _bq_cmd() + ["--project_id=" + PROJECT] + args, input=stdin, capture_output=True, text=True, timeout=timeout
    )
    if p.returncode != 0:
        raise SystemExit("bq %s failed:\n%s\n%s" % (" ".join(args[:3]), p.stdout[-1500:], p.stderr[-2000:]))
    return p.stdout


def ensure_dataset() -> None:
    p = subprocess.run(
        _bq_cmd() + ["--project_id=" + PROJECT, "show", "--format=json", "--dataset", "%s:%s" % (PROJECT, DATASET)],
        capture_output=True,
        text=True,
    )
    if p.returncode == 0:
        loc = json.loads(p.stdout).get("location")
        if loc != LOCATION:
            raise SystemExit("dataset %s exists in %s, expected %s" % (DATASET, loc, LOCATION))
        sys.stderr.write("dataset %s.%s exists (%s)\n" % (PROJECT, DATASET, loc))
        return
    bq(
        [
            "mk",
            "--dataset",
            "--location=" + LOCATION,
            "--description=Omi finops: daily true user unit cost, reconciliation and plan revenue. "
            "Written by backend/scripts/finops/run_unit_cost.py. Hashed uids only.",
            "%s:%s" % (PROJECT, DATASET),
        ]
    )
    sys.stderr.write("created dataset %s.%s in %s\n" % (PROJECT, DATASET, LOCATION))


def ensure_table(name: str) -> None:
    """Create the table when absent; when present, reconcile its columns to SCHEMAS[name] first."""
    ref = "%s:%s.%s" % (PROJECT, DATASET, name)
    p = subprocess.run(
        _bq_cmd() + ["--project_id=" + PROJECT, "show", "--format=json", ref], capture_output=True, text=True
    )
    if p.returncode == 0:
        sys.stderr.write("table %s exists\n" % name)
        ensure_columns(name)
        return
    schema = ",".join("%s:%s" % (c, t.replace("FLOAT64", "FLOAT").replace("BOOL", "BOOLEAN")) for c, t in SCHEMAS[name])
    bq(
        [
            "mk",
            "--table",
            "--time_partitioning_field=date",
            "--time_partitioning_type=DAY",
            "--clustering_fields=" + ",".join(CLUSTER[name]),
            ref,
            schema,
        ]
    )
    sys.stderr.write("created table %s\n" % name)


# The live table is reconciled to SCHEMAS[name] before every load: a column the
# code added is appended in place (nullable, metadata-only DDL), so the daily
# job keeps working on an older table and old artifacts (missing values load as
# NULL). Columns are never dropped or retyped — a type disagreement is a hard
# stop because it needs a migration, not a guess. A table that does not exist
# is still created whole by `ensure_table`.
_TYPE_ALIASES = {
    "INTEGER": "INT",
    "INT64": "INT",
    "FLOAT": "FLOAT",
    "FLOAT64": "FLOAT",
    "BOOLEAN": "BOOL",
    "BOOL": "BOOL",
}


def _canonical_type(t: str) -> str:
    return _TYPE_ALIASES.get(t.strip().upper(), t.strip().upper())


def ensure_columns(name: str, show=None, run=None) -> list[str]:
    """Add SCHEMAS[name] columns missing from the live table (nullable); returns what was added."""
    ref = "%s:%s.%s" % (PROJECT, DATASET, name)
    show = show or (
        lambda: subprocess.run(
            _bq_cmd() + ["--project_id=" + PROJECT, "show", "--format=json", ref], capture_output=True, text=True
        )
    )
    p = show()
    if p.returncode != 0:
        raise SystemExit("bq show %s failed:\n%s" % (name, p.stderr[-2000:]))
    live = {f["name"]: f.get("type", "") for f in json.loads(p.stdout).get("schema", {}).get("fields", [])}
    wanted = dict(SCHEMAS[name])
    clashes = sorted(
        "%s is %s in the table but %s in code" % (c, live[c] or "?", t)
        for c, t in wanted.items()
        if c in live and _canonical_type(live[c]) != _canonical_type(t)
    )
    if clashes:
        raise SystemExit(
            "table %s disagrees with the loader schema (a migration is required; the loader only adds columns): %s"
            % (name, "; ".join(clashes))
        )
    missing = [c for c in wanted if c not in live]
    if not missing:
        return []
    sql = "ALTER TABLE `%s.%s.%s`\n%s;" % (
        PROJECT,
        DATASET,
        name,
        ",\n".join("ADD COLUMN IF NOT EXISTS %s %s" % (c, wanted[c]) for c in missing),
    )
    (run or (lambda s: bq(["query", "--use_legacy_sql=false", "--format=none"], stdin=s)))(sql)
    sys.stderr.write("table %s: added columns %s\n" % (name, ", ".join(missing)))
    return missing


def load_replace(name: str, rows: list[dict], dates: list[str], extra_delete: str = "") -> int:
    """Delete the run's dates then insert, in one transaction. Idempotent per date.

    ``extra_delete`` narrows the DELETE (e.g. `` AND vendor = 'soniox'``) when a
    table holds more than one writer's rows for the same date.
    """
    if not rows:
        sys.stderr.write("  %s: nothing to load\n" % name)
        return 0
    cols = [c for c, _ in SCHEMAS[name]]
    stage = "_stage_%s_%d" % (name, int(dt.datetime.now().timestamp()))
    stage_ref = "%s:%s.%s" % (PROJECT, DATASET, stage)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        for r in rows:
            fh.write(json.dumps({c: r.get(c) for c in cols}) + "\n")
        path = fh.name
    schema = ",".join("%s:%s" % (c, t.replace("FLOAT64", "FLOAT").replace("BOOL", "BOOLEAN")) for c, t in SCHEMAS[name])
    try:
        bq(["load", "--source_format=NEWLINE_DELIMITED_JSON", "--replace", stage_ref, path, schema])
        in_list = ", ".join("DATE('%s')" % d for d in dates)
        sql = (
            "BEGIN TRANSACTION;\n"
            "DELETE FROM `{p}.{ds}.{t}` WHERE date IN ({dates}){extra};\n"
            "INSERT INTO `{p}.{ds}.{t}` ({cols}) SELECT {cols} FROM `{p}.{ds}.{stage}`;\n"
            "COMMIT TRANSACTION;"
        ).format(p=PROJECT, ds=DATASET, t=name, dates=in_list, extra=extra_delete, cols=", ".join(cols), stage=stage)
        bq(["query", "--use_legacy_sql=false", "--format=none"], stdin=sql)
    finally:
        subprocess.run(
            _bq_cmd() + ["--project_id=" + PROJECT, "rm", "-f", "-t", stage_ref], capture_output=True, text=True
        )
        pathlib.Path(path).unlink(missing_ok=True)
    sys.stderr.write("  %s: replaced %d dates, inserted %d rows\n" % (name, len(dates), len(rows)))
    return len(rows)


def build_rows(
    derived: pathlib.Path,
    raw: pathlib.Path,
    run_id: str,
    computed_at: str,
    settled_through: str | None,
    snapshot_date: str,
):
    longs = list(csv.DictReader(open(derived / "unit_cost_long.csv")))
    recon = list(csv.DictReader(open(derived / "unit_cost_reconciliation.csv")))
    userday = list(csv.DictReader(open(derived / "user_day_allocated.csv")))
    dates = sorted({r["date"] for r in longs})

    def settled(d):
        return settled_through is None or d <= settled_through

    def f(x):
        return None if x in ("", None) else float(x)

    out = {}
    out["unit_cost_daily"] = [
        {
            "date": r["date"],
            "segment_type": r["segment_type"],
            "segment": r["segment"],
            "component": r["component"],
            "method": r["method"],
            "usd": f(r["usd"]),
            "users": int(r["users"]),
            "usd_per_user_day": f(r["usd_per_user_day"]),
            "run_id": run_id,
            "computed_at": computed_at,
            "inputs_settled": settled(r["date"]),
        }
        for r in longs
    ]
    out["unit_cost_reconciliation"] = [
        {
            "date": r["date"],
            "pool": r["pool"],
            "pool_usd": f(r["pool_usd"]),
            "allocated_usd": f(r["allocated_usd"]),
            "delta_pct": f(r["delta_pct"]),
            "invoice_source": r["invoice_source"],
            "note": r["note"],
            "run_id": run_id,
            "computed_at": computed_at,
            "inputs_settled": r["inputs_settled"] == "True",
        }
        for r in recon
    ]
    out["unit_cost_user_day"] = [
        dict(
            {
                "date": r["date"],
                "uid_hash": r["uid_hash"],
                "cohort": r["cohort"],
                "plan": r["plan"],
                "attempts": int(r["attempts"]),
                "unpriced_attempts": int(r["unpriced_attempts"]),
                "tx_sec": f(r["tx_sec"]),
                "run_id": run_id,
                "computed_at": computed_at,
                "inputs_settled": settled(r["date"]),
            },
            **{c: f(r[c]) for c in COMPS},
        )
        for r in userday
    ]

    plan_rows = []
    sp = raw / "stripe_plan_mrr.json"
    if sp.exists():
        book = json.load(open(sp))["by_plan"]
        for d in dates:
            for x in book:
                if x["plan"].startswith("unmapped:"):
                    continue
                plan_rows.append(
                    {
                        "date": d,
                        "plan": x["plan"],
                        "paying_subs": x["paying_subs"],
                        "trialing_subs": x["trialing_subs"],
                        "mrr_usd": x["mrr_usd"],
                        "arpu_usd": x["arpu_usd"],
                        # NULL on artifacts written before the columns existed.
                        "paying_customers": x.get("paying_customers"),
                        "non_usd_paying_subs": x.get("non_usd_paying_subs"),
                        "snapshot_date": snapshot_date,
                        "run_id": run_id,
                        "computed_at": computed_at,
                    }
                )
    out["plan_revenue_daily"] = plan_rows
    return out, dates


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--derived", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--settled-through", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    acct = assert_writer_identity()
    computed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    tables, dates = build_rows(
        pathlib.Path(a.derived), pathlib.Path(a.raw), a.run_id, computed_at, a.settled_through, snapshot_date
    )
    sys.stderr.write("writer identity: %s | dates: %s\n" % (acct, ", ".join(dates)))
    for t, rows in tables.items():
        sys.stderr.write("  %-26s %d rows\n" % (t, len(rows)))
    if a.dry_run:
        sys.stderr.write("dry run: nothing written\n")
        return
    ensure_dataset()
    loaded = {}
    for name in ("unit_cost_daily", "unit_cost_reconciliation", "plan_revenue_daily", "unit_cost_user_day"):
        ensure_table(name)
        loaded[name] = load_replace(name, tables[name], dates)
    loaded.update(load_mercury.load(pathlib.Path(a.raw), a.run_id, computed_at, ensure_table, load_replace, bq))
    loaded.update(load_stripe_fees(pathlib.Path(a.raw), a.run_id, computed_at, ensure_table, load_replace))
    loaded.update(load_vendor_balance(pathlib.Path(a.raw), a.run_id, computed_at, ensure_table, load_replace, bq))
    loaded.update(load_modulate_modelled(pathlib.Path(a.raw), a.run_id, computed_at, ensure_table, load_replace))
    print(
        json.dumps(
            {"run_id": a.run_id, "dates": dates, "rows_loaded": loaded, "dataset": "%s.%s" % (PROJECT, DATASET)},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
