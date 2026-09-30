#!/usr/bin/env python3
"""Pull the GCP billing export for a usage-day window, classified into cost components.

Reads `based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256`
under the read-only bot. Three artefacts, all in the run's raw/ dir:

  gcp_components_daily.json   day x component x platform_structural, gross/credits/net
  gcp_day_resource_top.json   top-3000 (day, service, sku, resource) rows, with labels
  gcp_day_service_sku.json    day x project x service x sku (used for the dev-project split)
  gcp_recon.json              window totals straight off the export, for reconciliation

Rules that are load-bearing and easy to get wrong:
  * the table is partitioned on _PARTITIONTIME; filter it AND usage_start_time or the scan
    is unbounded. _PARTITIONTIME is set two days wide of the usage window because a usage
    day keeps landing in later partitions until it settles (D-2).
  * net = cost + credits. Never report gross.
  * `..._01B896_918303_539138` is the PREDECESSOR billing account table. Never sum it in.
  * Firestore bills under service.description='App Engine'; it is matched by SKU only.
  * every query runs with --maximum_bytes_billed so a classifier mistake cannot bill a scan.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gcpauth import READONLY_ENV, assert_readonly_identity, PROJECT  # noqa: E402

TABLE = "based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256"
MAX_BYTES = 2147483648  # 2 GiB ceiling per query


def one_time_case(events_path: pathlib.Path) -> str:
    """Render the dated one-off rules as leading CASE branches."""
    if not events_path.exists():
        return "  -- (no one-time rules registered)"
    reg = json.load(open(events_path))
    out = []
    for e in reg.get("events", []):
        conds = ["DATE(usage_start_time) BETWEEN '%s' AND '%s'" % (e["date_from"], e["date_to"])]
        if e.get("sku_like"):
            conds.append("sku.description LIKE '%s'" % e["sku_like"])
        if e.get("resource_like"):
            conds.append("IFNULL(resource.global_name, resource.name) LIKE '%s'" % e["resource_like"])
        if e.get("service"):
            conds.append("service.description = '%s'" % e["service"])
        out.append("  WHEN %s\n       THEN '%s'" % ("\n       AND ".join(conds), e["component"]))
    return "\n".join(out) if out else "  -- (no one-time rules registered)"


def classifier(events_path: pathlib.Path) -> str:
    sql = (HERE / "gcp_component_classifier.sql").read_text()
    # the file documents both the component CASE and the platform CASE; take the first only
    case_sql = sql[sql.index("CASE") : sql.index("END AS component,") + len("END AS component,")]
    case_sql = case_sql.replace("{{ONE_TIME_RULES}}", one_time_case(events_path))
    return case_sql[: -len(" AS component,")]  # bare CASE ... END


def bq(sql: str, out: pathlib.Path, label: str, max_rows: int = 100000) -> dict:
    job_id = "finops_%s_%d" % (label, int(dt.datetime.now().timestamp()))
    cmd = (
        'source "%s" >/dev/null 2>&1; '
        "bq query --project_id=%s --job_id=%s --maximum_bytes_billed=%d "
        "--use_legacy_sql=false --format=json --max_rows=%d" % (READONLY_ENV, PROJECT, job_id, MAX_BYTES, max_rows)
    )
    p = subprocess.run(["bash", "-lc", cmd], input=sql, capture_output=True, text=True, timeout=1800)
    if p.returncode != 0:
        raise SystemExit("bq query %s failed:\n%s" % (label, p.stderr[-2000:]))
    out.write_text(p.stdout)
    stats = subprocess.run(
        [
            "bash",
            "-lc",
            'source "%s" >/dev/null 2>&1; bq --project_id=%s --format=json show -j %s'
            % (READONLY_ENV, PROJECT, job_id),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    billed = None
    try:
        billed = int(json.loads(stats.stdout)["statistics"]["query"]["totalBytesBilled"])
    except Exception:
        pass
    n = len(json.loads(p.stdout or "[]"))
    sys.stderr.write("  %-22s rows=%-6d billed=%s bytes  -> %s\n" % (label, n, billed, out.name))
    return {"job_id": job_id, "rows": n, "bytes_billed": billed}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="first usage day, inclusive (YYYY-MM-DD)")
    ap.add_argument("--end", required=True, help="last usage day, inclusive (YYYY-MM-DD)")
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()

    assert_readonly_identity()
    raw = pathlib.Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    end_excl = (dt.date.fromisoformat(a.end) + dt.timedelta(days=1)).isoformat()
    # a usage day keeps arriving in later partitions; open the partition filter two days each way
    p_lo = (dt.date.fromisoformat(a.start) - dt.timedelta(days=2)).isoformat()
    p_hi = (dt.date.fromisoformat(a.end) + dt.timedelta(days=3)).isoformat()
    where = (
        "WHERE _PARTITIONTIME >= TIMESTAMP('%s') AND _PARTITIONTIME < TIMESTAMP('%s')\n"
        "  AND usage_start_time >= TIMESTAMP('%s') AND usage_start_time < TIMESTAMP('%s')"
        % (p_lo, p_hi, a.start, end_excl)
    )
    case_sql = classifier(HERE / "one_time_events.json")
    net = "cost + IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0)"

    stats = {}
    stats["components"] = bq(
        f"""
WITH base AS (
  SELECT DATE(usage_start_time) AS usage_day,
         {case_sql} AS component,
         usage.amount AS usage_amount,
         cost AS gross,
         IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0) AS credits
  FROM `{TABLE}`
  {where}
)
SELECT usage_day, component,
  CASE
    WHEN STARTS_WITH(component, 'one_time')                      THEN 'one_time'
    WHEN component = 'vertex_pt_reservation'                     THEN 'fixed'
    WHEN component IN ('embeddings','cloud_run_desktop_backend') THEN 'desktop'
    WHEN component IN ('asr_gpu_fleet','storage_audio')          THEN 'mobile'
    WHEN component = 'bigquery'                                  THEN 'overhead'
    ELSE 'shared'
  END AS platform_structural,
  ROUND(SUM(gross),6) AS gross, ROUND(SUM(credits),6) AS credits,
  ROUND(SUM(gross+credits),6) AS net, SUM(usage_amount) AS usage_amount
FROM base GROUP BY 1,2,3 ORDER BY usage_day, net DESC
""",
        raw / "gcp_components_daily.json",
        "components",
    )

    stats["resource_top"] = bq(
        f"""
SELECT DATE(usage_start_time) AS usage_day, project.id AS project_id,
       service.description AS service, sku.description AS sku,
       resource.global_name AS resource_global_name, resource.name AS resource_name,
       ANY_VALUE(TO_JSON_STRING(labels)) AS labels,
       ANY_VALUE(TO_JSON_STRING(system_labels)) AS system_labels,
       SUM(usage.amount) AS usage_amount, ANY_VALUE(usage.unit) AS usage_unit,
       ROUND(SUM(cost),6) AS gross,
       ROUND(SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0)),6) AS credits,
       ROUND(SUM({net}),6) AS net
FROM `{TABLE}`
{where}
GROUP BY 1,2,3,4,5,6 ORDER BY gross DESC LIMIT 3000
""",
        raw / "gcp_day_resource_top.json",
        "resource_top",
        max_rows=3000,
    )

    stats["service_sku"] = bq(
        f"""
SELECT DATE(usage_start_time) AS usage_day, project.id AS project_id,
       service.description AS service, sku.description AS sku,
       SUM(usage.amount) AS usage_amount, ANY_VALUE(usage.unit) AS usage_unit,
       ROUND(SUM(cost),6) AS gross,
       ROUND(SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0)),6) AS credits,
       ROUND(SUM({net}),6) AS net
FROM `{TABLE}`
{where}
GROUP BY 1,2,3,4 ORDER BY usage_day, net DESC
""",
        raw / "gcp_day_service_sku.json",
        "service_sku",
    )

    stats["recon"] = bq(
        f"""
SELECT DATE(usage_start_time) AS usage_day,
       ROUND(SUM(cost),6) AS gross,
       ROUND(SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c),0)),6) AS credits,
       ROUND(SUM({net}),6) AS net, COUNT(*) AS rows_n,
       MAX(usage_end_time) AS max_usage_end_time
FROM `{TABLE}`
{where}
GROUP BY 1 ORDER BY 1
""",
        raw / "gcp_recon.json",
        "recon",
    )

    (raw / "_gcp_pull_stats.json").write_text(
        json.dumps(
            {
                "window": [a.start, a.end],
                "table": TABLE,
                "queries": stats,
                "bytes_billed_total": sum(v.get("bytes_billed") or 0 for v in stats.values()),
            },
            indent=1,
        )
    )
    tot = sum(v.get("bytes_billed") or 0 for v in stats.values())
    sys.stderr.write("GCP pull done: %.2f GiB billed (~$%.4f)\n" % (tot / 2**30, tot / 2**40 * 6.25))


if __name__ == "__main__":
    main()
