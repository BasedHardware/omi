#!/usr/bin/env python3
"""One entrypoint for the daily Omi unit-cost job: pull -> assemble -> validate -> load.

  run_unit_cost.py --date 2026-09-07 [--backfill-from 2026-09-01] [--load]

What it does, in order:
  1. picks a run directory and records a manifest (window, identities, settlement)
  2. pulls the raw inputs for the window (GCP billing export, gateway ledger, users snapshot,
     hourly_usage transcription seconds, Prometheus VAD hours, OpenAI/Anthropic invoices,
     Stripe subscription book, PostHog DAU)
  3. assembles the allocation (backend/scripts/finops/assemble_unit_cost.py)
  4. validates: every variable pool must reconcile within --recon-tolerance-pct, the window
     must be settled, and no raw uid may appear in any output
  5. optionally loads BigQuery `based-hardware.omi_finops`, idempotently per date

Identities: every READ runs as read-only-bot-account@based-hardware; only the BigQuery load
runs as finops-writer@based-hardware, and it refuses to run under any other account.

Settlement: the GCP billing export lands a usage day over the following ~48 h, so a date is
only treated as settled at D-2. `--date` defaults to today-2. Unsettled dates can still be
computed with --allow-unsettled; the rows carry inputs_settled=false.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
RUN_ROOT = pathlib.Path(
    os.environ.get("FINOPS_RUN_ROOT", os.environ.get("SCRATCH_ROOT", "/Volumes/scratch") + "/finops-runs")
)
SETTLEMENT_LAG_DAYS = 2


def sh(argv: list[str], log: pathlib.Path, label: str, required: bool = True) -> bool:
    t0 = time.time()
    sys.stderr.write("[%s] %s\n" % (label, " ".join(str(x) for x in argv)))
    with open(log, "a") as fh:
        fh.write("\n===== %s: %s\n" % (label, " ".join(str(x) for x in argv)))
        fh.flush()
        p = subprocess.run([sys.executable] + argv, stdout=fh, stderr=subprocess.STDOUT)
    ok = p.returncode == 0
    sys.stderr.write("[%s] %s in %.0fs\n" % (label, "ok" if ok else "FAILED rc=%d" % p.returncode, time.time() - t0))
    if not ok and required:
        raise SystemExit("required pull %s failed; see %s" % (label, log))
    return ok


def daterange(a: str, b: str) -> list[str]:
    d0, d1 = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def check_no_raw_uids(paths: list[pathlib.Path]) -> None:
    """Outputs may only carry sha256[:16] hashes.

    Two checks. Structural: every value in a `uid_hash` column must be exactly 16 lowercase
    hex characters (or the `anonymous` sentinel the gateway writes when an attempt carries no
    uid). Generic: no long token that looks like a Firebase uid (>=20 characters, >=3 letters
    and >=1 digit) may appear anywhere. A long run of digits is a float and a single-letter
    exponent is scientific notation, so neither is flagged.
    """
    hashish = re.compile(r"^([0-9a-f]{16}|anonymous)$")
    uidish = re.compile(
        r"\b(?=[0-9A-Za-z_-]{20,}\b)(?=(?:[^A-Za-z\s,]*[A-Za-z]){3})(?=[^\s,]*[0-9])[0-9A-Za-z_-]{20,}\b"
    )
    bad = []
    for p in paths:
        if not p.exists():
            continue
        if p.suffix == ".csv":
            with open(p, newline="") as fh:
                for i, row in enumerate(csv.DictReader(fh)):
                    if i > 200000:
                        break
                    v = row.get("uid_hash")
                    if v is not None and not hashish.match(v):
                        bad.append("%s:%d uid_hash=%r" % (p.name, i + 2, v[:12]))
                        break
        with open(p, errors="ignore") as fh:
            for i, line in enumerate(fh):
                if i > 20000:
                    break
                m = uidish.search(line)
                if m:
                    bad.append("%s:%d %s..." % (p.name, i + 1, m.group()[:10]))
                    break
    if bad:
        raise SystemExit("possible raw identifiers in outputs: %s" % "; ".join(bad))


def validate(derived: pathlib.Path, raw: pathlib.Path, tol_pct: float, dates: list[str]) -> list[dict]:
    recon = list(csv.DictReader(open(derived / "unit_cost_reconciliation.csv")))
    variable = {
        "shared_gcp",
        "audio_pipeline_gcp",
        "vertex_paygo",
        "desktop_pools",
        "vertex_pt_fixed",
        "llm_openai",
        "llm_anthropic",
        "stt_vendor_low",
        "gcp_total_export",
        "one_time",
    }
    failures = []
    for r in recon:
        if r["pool"] not in variable:
            continue
        if abs(float(r["delta_pct"])) > tol_pct:
            failures.append(r)
    if failures:
        for r in failures:
            sys.stderr.write(
                "RECON FAIL %s %s pool=%.2f allocated=%.2f delta=%.4f%%\n"
                % (r["date"], r["pool"], float(r["pool_usd"]), float(r["allocated_usd"]), float(r["delta_pct"]))
            )
        raise SystemExit("reconciliation outside %.2f%% on %d rows" % (tol_pct, len(failures)))
    got = sorted({r["date"] for r in csv.DictReader(open(derived / "unit_cost_long.csv"))})
    missing = [d for d in dates if d not in got]
    if missing:
        raise SystemExit("no allocated rows for %s" % ", ".join(missing))
    check_no_raw_uids(
        [
            derived / "unit_cost_long.csv",
            derived / "user_day_allocated.csv",
            raw / "ledger_user_daily.csv",
            raw / "users_active_30d.csv",
            raw / "stt_usage_daily.csv",
        ]
    )
    return recon


def settlement_frontier(raw: pathlib.Path) -> str | None:
    p = raw / "gcp_recon.json"
    if not p.exists():
        return None
    ends = [r.get("max_usage_end_time") for r in json.load(open(p)) if r.get("max_usage_end_time")]
    return max(ends) if ends else None


def main() -> None:
    today = dt.date.today()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--date",
        default=(today - dt.timedelta(days=SETTLEMENT_LAG_DAYS)).isoformat(),
        help="last usage day, inclusive. Default: today-%d (the settlement frontier)." % SETTLEMENT_LAG_DAYS,
    )
    ap.add_argument("--backfill-from", default=None, help="first usage day, inclusive. Default: --date.")
    ap.add_argument("--load", action="store_true", help="load BigQuery omi_finops (finops-writer SA)")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument(
        "--cohort-window-start",
        default=None,
        help="pin the date from which a users-snapshot last_active_at_* counts as 'on that platform'. "
        "Omit for the default trailing window, which is the same definition for every usage day "
        "whether it is computed alone or inside a backfill.",
    )
    ap.add_argument("--cohort-lookback-days", type=int, default=7)
    ap.add_argument("--reuse-raw", action="store_true", help="skip the pulls and use the run dir as-is")
    ap.add_argument(
        "--skip", default="", help="comma-separated pulls to skip: gcp,ledger,users,stt,prom,providers,stripe,posthog"
    )
    ap.add_argument("--recon-tolerance-pct", type=float, default=0.5)
    ap.add_argument("--allow-unsettled", action="store_true")
    a = ap.parse_args()

    start = a.backfill_from or a.date
    end = a.date
    if start > end:
        raise SystemExit("--backfill-from %s is after --date %s" % (start, end))
    frontier = (today - dt.timedelta(days=SETTLEMENT_LAG_DAYS)).isoformat()
    if end > frontier and not a.allow_unsettled:
        raise SystemExit(
            "%s is not settled yet (frontier %s at D-%d); pass --allow-unsettled to compute anyway"
            % (end, frontier, SETTLEMENT_LAG_DAYS)
        )
    dates = daterange(start, end)
    run_id = "%s_%s_%s" % (start, end, uuid.uuid4().hex[:8])
    run = pathlib.Path(a.run_dir) if a.run_dir else RUN_ROOT / ("%s_%s" % (start, end))
    raw, derived = run / "raw", run / "derived"
    raw.mkdir(parents=True, exist_ok=True)
    log = run / "pull.log"
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    t0 = time.time()

    if not a.reuse_raw:
        if "gcp" not in skip:
            sh([str(HERE / "pull_gcp.py"), "--start", start, "--end", end, "--raw", str(raw)], log, "gcp")
        if "ledger" not in skip:
            for f in ("ledger_agg_daily.csv", "ledger_user_daily.csv", "ledger_daily_totals.csv"):
                (raw / f).unlink(missing_ok=True)  # pull_ledger appends; never double-count a rerun
            sh([str(HERE / "pull_ledger.py"), "--out", str(raw), "--dates"] + dates, log, "ledger")
        if "users" not in skip:
            sh([str(HERE / "pull_users.py"), "--raw", str(raw)], log, "users")
        if "stt" not in skip:
            sh([str(HERE / "pull_hourly_usage.py"), "--start", start, "--end", end, "--raw", str(raw)], log, "stt")
        if "prom" not in skip:
            sh([str(HERE / "pull_prometheus.py"), "--start", start, "--end", end, "--raw", str(raw)], log, "prom")
        if "providers" not in skip:
            sh([str(HERE / "pull_providers.py"), "--start", start, "--end", end, "--raw", str(raw)], log, "providers")
        if "stripe" not in skip:
            sh([str(HERE / "pull_stripe.py"), "--raw", str(raw)], log, "stripe", required=False)
        if "posthog" not in skip:
            # denominator colour only; the allocation does not depend on it
            nxt = (dt.date.fromisoformat(end) + dt.timedelta(days=1)).isoformat()
            sh(
                [str(HERE / "posthog_dau.py"), start, nxt, str(raw / "posthog_dau_daily.csv")],
                log,
                "posthog",
                required=False,
            )

    cws = a.cohort_window_start
    with open(run / "assembly_output.md", "w") as fh:
        p = subprocess.run(
            [sys.executable, str(HERE / "assemble_unit_cost.py"), str(raw), str(derived), start, end]
            + ([cws] if cws else [])
            + [
                "--settled-through",
                frontier,
                "--cohort-lookback-days",
                str(a.cohort_lookback_days),
            ],
            stdout=fh,
            stderr=subprocess.PIPE,
            text=True,
        )
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-3000:])
        raise SystemExit("assembly failed")

    recon = validate(derived, raw, a.recon_tolerance_pct, dates)
    manifest = {
        "run_id": run_id,
        "window": [start, end],
        "dates": dates,
        "cohort_window_start": cws or "trailing %dd per usage day" % a.cohort_lookback_days,
        "settled_through": frontier,
        "settlement_frontier_export": settlement_frontier(raw),
        "computed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "run_dir": str(run),
        "recon_tolerance_pct": a.recon_tolerance_pct,
        "users_snapshot": (
            json.load(open(raw / "_users_snapshot.json")) if (raw / "_users_snapshot.json").exists() else None
        ),
        "gcp_bytes_billed": (
            json.load(open(raw / "_gcp_pull_stats.json")).get("bytes_billed_total")
            if (raw / "_gcp_pull_stats.json").exists()
            else None
        ),
        "wall_seconds": round(time.time() - t0, 1),
    }
    (run / "run_manifest.json").write_text(json.dumps(manifest, indent=1))

    loaded = None
    if a.load:
        p = subprocess.run(
            [
                sys.executable,
                str(HERE / "load_bigquery.py"),
                "--derived",
                str(derived),
                "--raw",
                str(raw),
                "--run-id",
                run_id,
                "--settled-through",
                frontier,
            ],
            capture_output=True,
            text=True,
        )
        sys.stderr.write(p.stderr)
        if p.returncode != 0:
            raise SystemExit("BigQuery load failed")
        loaded = json.loads(p.stdout)
        manifest["bigquery"] = loaded
        (run / "run_manifest.json").write_text(json.dumps(manifest, indent=1))

    # ---- short stdout summary (this is what the cron job delivers)
    summary = json.load(open(derived / "day_summary.json"))["days"]
    print("Omi unit cost %s..%s  (run %s)" % (start, end, run_id))
    worst = max(
        (abs(float(r["delta_pct"])) for r in recon if r["pool"] not in ("llm_openai_ledger_coverage",)), default=0.0
    )
    print(
        "reconciliation: worst |delta| %.4f%% (tolerance %.2f%%)  |  %s"
        % (worst, a.recon_tolerance_pct, "LOADED" if loaded else "not loaded")
    )
    plan_rows = [
        r
        for r in csv.DictReader(open(derived / "unit_cost_long.csv"))
        if r["segment_type"] == "plan" and r["component"] == "gross_total"
    ]
    by_plan = {}
    for r in plan_rows:
        g = by_plan.setdefault(r["segment"], [0.0, 0])
        g[0] += float(r["usd"])
        g[1] += int(r["users"])
    for d in dates:
        s = summary.get(d)
        if not s:
            continue
        print(
            "  %s users %-5d gcp $%-8.0f openai $%-7.0f gross/user-day $%.3f%s"
            % (
                d,
                s["cost_active_users"],
                s["gcp_net_excl_one_time"],
                s["openai_invoice"],
                sum(float(r["usd"]) for r in plan_rows if r["date"] == d)
                / max(1, sum(int(r["users"]) for r in plan_rows if r["date"] == d)),
                "  one-time $%.0f" % s["gcp_one_time"] if s["gcp_one_time"] else "",
            )
        )
    print(
        "  gross $/user-day by plan: "
        + ", ".join("%s %.2f" % (k, v[0] / v[1]) for k, v in sorted(by_plan.items(), key=lambda kv: -kv[1][0])[:8])
    )
    print("  run dir: %s" % run)


if __name__ == "__main__":
    main()
