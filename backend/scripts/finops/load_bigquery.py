#!/usr/bin/env python3
"""Load an assembled run into `based-hardware.omi_finops`.

Writes run as the interactive owner account (verified by name first); every read in the
pipeline runs as the read-only bot. Loads are IDEMPOTENT per date: rows for the dates in
this run are deleted and re-inserted inside one BigQuery transaction, so re-running a date
replaces it rather than doubling it.

Tables (all partitioned by `date`, no partition expiry):
  unit_cost_daily          long format: date x segment_type x segment x component x method
  unit_cost_reconciliation what each pool cost vs what landed on user-days
  plan_revenue_daily       Stripe snapshot, carrying snapshot_date so it stays honest
  unit_cost_user_day       per (date, uid_hash) allocation. HASHED uids only, never raw.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from assemble_unit_cost import COMPS  # noqa: E402
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


def bq(args: list[str], stdin: str | None = None, timeout: int = 1800) -> str:
    p = subprocess.run(
        ["bq", "--project_id=" + PROJECT] + args, input=stdin, capture_output=True, text=True, timeout=timeout
    )
    if p.returncode != 0:
        raise SystemExit("bq %s failed:\n%s\n%s" % (" ".join(args[:3]), p.stdout[-1500:], p.stderr[-2000:]))
    return p.stdout


def ensure_dataset() -> None:
    p = subprocess.run(
        ["bq", "--project_id=" + PROJECT, "show", "--format=json", "--dataset", "%s:%s" % (PROJECT, DATASET)],
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
    ref = "%s:%s.%s" % (PROJECT, DATASET, name)
    p = subprocess.run(["bq", "--project_id=" + PROJECT, "show", "--format=json", ref], capture_output=True, text=True)
    if p.returncode == 0:
        sys.stderr.write("table %s exists\n" % name)
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


def load_replace(name: str, rows: list[dict], dates: list[str]) -> int:
    """Delete the run's dates then insert, in one transaction. Idempotent per date."""
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
            "DELETE FROM `{p}.{ds}.{t}` WHERE date IN ({dates});\n"
            "INSERT INTO `{p}.{ds}.{t}` ({cols}) SELECT {cols} FROM `{p}.{ds}.{stage}`;\n"
            "COMMIT TRANSACTION;"
        ).format(p=PROJECT, ds=DATASET, t=name, dates=in_list, cols=", ".join(cols), stage=stage)
        bq(["query", "--use_legacy_sql=false", "--format=none"], stdin=sql)
    finally:
        subprocess.run(["bq", "--project_id=" + PROJECT, "rm", "-f", "-t", stage_ref], capture_output=True, text=True)
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
    print(
        json.dumps(
            {"run_id": a.run_id, "dates": dates, "rows_loaded": loaded, "dataset": "%s.%s" % (PROJECT, DATASET)},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
