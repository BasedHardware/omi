#!/usr/bin/env python3
"""Cloud Run Job entrypoint for the daily Omi unit-cost producer.

Contract (matches the laptop cron shim, minus laptop-only paths):

  * date    = today (UTC) - 2, the GCP billing-export settlement frontier (D-2).
             A daily run also reloads up to GAP_FILL_CAP missing settled days in the
             trailing LOOKBACK_DAYS window, so one failed day does not stay a hole.
  * FINOPS_DATE = YYYY-MM-DD loads that settled date only (one-off backfill).
  * overlap = one producer run per date, globally. A GCS lease object
              (``gs://<FINOPS_LOCK_BUCKET>/locks/unit-cost/<date>.lock``) is created
              with a generation precondition; a second concurrent run loses the race
              and skips that date. A failed run releases its lease so a Cloud Run
              retry can acquire it.
  * auth    = ADC of the job's runtime service account (FINOPS_AUTH=cloudrun).
  * failure = non-zero exit so Cloud Run Job reports the execution as failed.
              Child pull stderr is copied onto this process's stderr (Cloud Logging).

Required runtime configuration:
  FINOPS_LOCK_BUCKET      GCS bucket for the daily overlap lease (name only, no secret).
  FINOPS_SECRETS_DIR      dir where Secret Manager volumes are mounted (default
                          /run/secrets/finops), containing the provider/prometheus/stripe
                          keys by file name (see cloudrun.SECRET_FILES).
Optional:
  FINOPS_WRITER_SA        expected runtime SA email (default finops-writer@based-hardware).
  FINOPS_RUN_ROOT         scratch dir for run artefacts (default /tmp/finops-runs).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cloudrun  # noqa: E402

SETTLEMENT_LAG_DAYS = 2
LOCK_TTL_HOURS = 6  # a crashed run's lease expires; content is just provenance metadata
LOOKBACK_DAYS = 14
GAP_FILL_CAP = 3
SERIES_START = dt.date(2026, 9, 1)


def lease_blob(date: str):
    from google.cloud import storage

    bucket_name = os.environ.get("FINOPS_LOCK_BUCKET", "").strip()
    if not bucket_name:
        raise SystemExit("FINOPS_LOCK_BUCKET is required for overlap protection")
    client = storage.Client(project=cloudrun.PROJECT)
    return client.bucket(bucket_name).blob("locks/unit-cost/%s.lock" % date)


def acquire_lease(date: str) -> bool:
    """Create-if-absent race on a GCS object; True = this run owns the date."""
    blob = lease_blob(date)
    payload = json.dumps(
        {
            "date": date,
            "run_id": uuid.uuid4().hex[:12],
            "acquired_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "holder": cloudrun.runtime_identity(),
            "ttl_hours": LOCK_TTL_HOURS,
        },
        indent=1,
    )
    try:
        blob.upload_from_string(payload, if_generation_match=0)
        return True
    except Exception as e:  # noqa: BLE001
        # 412 = precondition failed: someone else owns the lease
        if "412" in str(e) or "Precondition" in type(e).__name__:
            return False
        raise


def takeover_if_stale(date: str) -> bool:
    """If the existing lease is older than LOCK_TTL_HOURS, replace it (crashed run)."""
    blob = lease_blob(date)
    try:
        blob.reload()
    except Exception:  # noqa: BLE001
        return acquire_lease(date)
    age_h = (dt.datetime.now(dt.timezone.utc) - blob.updated).total_seconds() / 3600.0
    if age_h < LOCK_TTL_HOURS:
        return False
    payload = json.dumps(
        {
            "date": date,
            "run_id": uuid.uuid4().hex[:12],
            "acquired_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "holder": cloudrun.runtime_identity(),
            "takeover_of_stale_lease": True,
            "ttl_hours": LOCK_TTL_HOURS,
        },
        indent=1,
    )
    try:
        blob.upload_from_string(payload, if_generation_match=blob.generation)
        return True
    except Exception:  # noqa: BLE001
        return False


def release_lease(date: str) -> None:
    """Drop a lease after failure so a retry is not told the date is already owned."""
    try:
        lease_blob(date).delete()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("lease release failed for %s: %s\n" % (date, type(e).__name__))


def settlement_frontier(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=SETTLEMENT_LAG_DAYS)


def parse_explicit_date(raw: str, today: dt.date) -> str:
    """FINOPS_DATE must be a settled day inside the finops series. Never a future day."""
    try:
        day = dt.date.fromisoformat(raw.strip())
    except ValueError as e:
        raise SystemExit("FINOPS_DATE must be YYYY-MM-DD") from e
    frontier = settlement_frontier(today)
    if day > frontier:
        raise SystemExit("FINOPS_DATE %s is not settled (frontier %s)" % (day.isoformat(), frontier.isoformat()))
    if day < SERIES_START:
        raise SystemExit("FINOPS_DATE %s is before the finops series start" % day.isoformat())
    return day.isoformat()


def gap_fill_dates(
    today: dt.date,
    present: set[str],
    lookback: int = LOOKBACK_DAYS,
    cap: int = GAP_FILL_CAP,
) -> tuple[list[str], list[str]]:
    """Missing settled days before the frontier, oldest first, capped.

    The frontier itself is the primary daily load, not a gap. Returns
    (to_fill, skipped_over_cap).
    """
    frontier = settlement_frontier(today)
    start = max(SERIES_START, today - dt.timedelta(days=lookback))
    missing: list[str] = []
    day = start
    while day < frontier:
        iso = day.isoformat()
        if iso not in present:
            missing.append(iso)
        day += dt.timedelta(days=1)
    return missing[:cap], missing[cap:]


def load_present_days(start: str, end: str) -> set[str] | None:
    """Days that already have a fully_loaded total. None means discovery failed."""
    try:
        from google.cloud import bigquery  # type: ignore[attr-defined]
    except ImportError:
        sys.stderr.write("gap-fill discovery unavailable (no bigquery client); loading frontier only\n")
        return None
    try:
        client = bigquery.Client(project=cloudrun.PROJECT)
        sql = """
          SELECT DISTINCT FORMAT_DATE('%F', date) AS day
          FROM `based-hardware.omi_finops.unit_cost_daily`
          WHERE date BETWEEN @start AND @end
            AND segment_type = 'total'
            AND component = 'fully_loaded'
        """
        job = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("start", "DATE", dt.date.fromisoformat(start)),
                    bigquery.ScalarQueryParameter("end", "DATE", dt.date.fromisoformat(end)),
                ]
            ),
        )
        return {row.day for row in job.result()}
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("gap-fill discovery failed (%s); loading frontier only\n" % type(e).__name__)
        return None


def dates_for_run(today: dt.date, present: set[str] | None, explicit: str) -> list[str]:
    if explicit:
        return [parse_explicit_date(explicit, today)]
    frontier = settlement_frontier(today).isoformat()
    if present is None:
        return [frontier]
    extras, skipped = gap_fill_dates(today, present)
    if skipped:
        sys.stderr.write("gap-fill cap skipped: %s\n" % ",".join(skipped))
    return extras + [frontier]


def main() -> int:
    today = dt.datetime.now(dt.timezone.utc).date()
    identity = cloudrun.assert_runtime_identity()
    explicit = os.environ.get("FINOPS_DATE", "").strip()
    present = None
    if not explicit:
        frontier = settlement_frontier(today)
        present = load_present_days(
            max(SERIES_START, today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat(),
            frontier.isoformat(),
        )
    dates = dates_for_run(today, present, explicit)
    sys.stderr.write("finops cloudrun producer: dates=%s runtime_sa=%s\n" % (",".join(dates), identity))

    os.environ.setdefault("FINOPS_RUN_ROOT", "/tmp/finops-runs")
    os.environ["FINOPS_AUTH"] = "cloudrun"

    failed = [date for date in dates if run_one(date) != 0]
    if failed:
        sys.stderr.write("FINOPS FAILED dates: %s\n" % ",".join(failed))
        return 1
    return 0


def run_one(date: str) -> int:
    if not acquire_lease(date):
        if not takeover_if_stale(date):
            sys.stderr.write("another run owns %s; skipping (overlap protection)\n" % date)
            return 0
        sys.stderr.write("took over a stale lease for %s\n" % date)
    rc = subprocess_run(date)
    if rc != 0:
        release_lease(date)
        sys.stderr.write("released lease for failed date %s so a retry can acquire it\n" % date)
    return rc


def subprocess_run(date: str) -> int:
    import subprocess

    entry = HERE / "run_unit_cost.py"
    env = dict(os.environ)
    env["FINOPS_AUTH"] = "cloudrun"
    p = subprocess.run(
        [sys.executable, str(entry), "--date", date, "--load"],
        capture_output=True,
        text=True,
        timeout=3600,
        env=env,
    )
    if p.returncode != 0:
        sys.stderr.write("FINOPS FAILED for %s (rc=%d)\n" % (date, p.returncode))
        tail = [line for line in (p.stderr or "").strip().splitlines() if line.strip()][-80:]
        sys.stderr.write("\n".join(tail) + "\n")
        if p.stdout and p.stdout.strip():
            sys.stderr.write("stdout tail:\n%s\n" % "\n".join(p.stdout.strip().splitlines()[-20:]))
        return p.returncode
    if (p.stdout or "").strip():
        sys.stdout.write(p.stdout.strip() + "\n")
    return 0


if __name__ == "__main__":
    # Preflight subcommands used by the deploy workflow's image smoke:
    #   (no args) = normal daily production run
    #   identity  = assert the runtime SA and print it (used with ADC present)
    #   --help    = usage only
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        if arg == "identity":
            sys.exit(0 if cloudrun.assert_runtime_identity() else 1)
        raise SystemExit("usage: cloudrun_entry.py [--help | identity]")
    sys.exit(main())
