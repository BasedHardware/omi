#!/usr/bin/env python3
"""Minimal `bq` CLI substitute for the Cloud Run finops job.

The laptop path shells out to the real `bq` CLI. Cloud Run Jobs have no bundled
gcloud/bq, so this stub translates exactly the invocations backend/scripts/finops
uses into google-cloud-bigquery API calls under ADC (the job's runtime SA).
Anything unrecognised exits non-zero with a clear message instead of guessing.
"""

from __future__ import annotations

import json
import os
import sys


def die(msg: str, code: int = 2) -> None:
    sys.stderr.write("bq-stub: %s\n" % msg)
    sys.exit(code)


def parse_args(argv: list[str]) -> dict:
    flags = {"positional": []}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if "=" in a:
                k, v = a[2:].split("=", 1)
                flags[k] = v
            else:
                flags[a[2:]] = True
        else:
            flags["positional"].append(a)
        i += 1
    return flags


def table_ref(parts: list[str]) -> str:
    """Accept project.dataset.table / project:dataset.table / dataset.table."""
    joined = ".".join(parts)
    return joined.replace(":", ".", 1)


def client():
    from google.cloud import bigquery

    return bigquery.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None)


def cmd_query(flags: dict) -> None:
    # validate input before touching optional deps so misuse fails with a clear message
    sql = sys.stdin.read()
    if not sql.strip():
        die("query requires SQL on stdin")
    from google.cloud import bigquery

    c = client()
    job_config = bigquery.QueryJobConfig()
    if flags.get("dry_run"):
        job_config.dry_run = True
    if flags.get("maximum_bytes_billed"):
        job_config.maximum_bytes_billed = int(flags["maximum_bytes_billed"])
    job = c.query(sql, job_config=job_config, job_id_prefix="finops_stub_")
    if flags.get("dry_run"):
        print(json.dumps({"dryRun": True, "totalBytesProcessed": job.total_bytes_processed}))
        return
    job.result()
    fmt = flags.get("format", "json")
    if fmt in ("none",):
        return
    rows = [dict(r) for r in job.result(timeout=1800)]
    if fmt == "csv":
        w = csv_writer(rows)
        sys.stdout.write(w)
    else:
        sys.stdout.write(json.dumps(rows, default=str))


def csv_writer(rows: list[dict]) -> str:
    import csv
    import io

    if not rows:
        return ""
    buf = io.StringIO()
    cols = list(rows[0].keys())
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def cmd_load(flags: dict) -> None:
    from google.cloud import bigquery

    pos = flags["positional"]
    if len(pos) < 3:
        die("load requires <table_ref> <path> <schema>")
    ref, path, schema = pos[0], pos[1], pos[2]
    c = client()
    cols = []
    for spec in schema.split(","):
        name, typ = spec.split(":", 1)
        typ = {"FLOAT": "FLOAT64", "BOOLEAN": "BOOL"}.get(typ, typ)
        cols.append(bigquery.SchemaField(name, typ))
    cfg = bigquery.LoadJobConfig()
    cfg.schema = cols
    cfg.source_format = bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
    cfg.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE
    with open(path, "rb") as fh:
        job = c.load_table_from_file(fh, ref.replace(":", ".", 1), job_config=cfg, job_id_prefix="finops_stub_")
    job.result()
    sys.stderr.write("loaded %s\n" % ref)


def cmd_show(flags: dict) -> None:
    from google.cloud import bigquery

    pos = flags["positional"]
    if not pos:
        die("show requires a resource")
    ref = pos[0].replace(":", ".", 1)
    c = client()
    try:
        if flags.get("dataset"):
            ds = c.get_dataset(ref)
            print(json.dumps({"location": ds.location, "datasetReference": ds.reference.to_api_repr()}))
            return
        if "-j" in flags or flags.get("job"):
            job = c.get_job(ref)
            print(json.dumps(job.to_api_repr(), default=str))
            return
        t = c.get_table(ref)
        print(json.dumps(t.to_api_repr(), default=str))
    except Exception as e:  # noqa: BLE001
        die("show %s failed: %s" % (ref, e), 1)


def cmd_mk(flags: dict) -> None:
    from google.cloud import bigquery

    pos = flags["positional"]
    if flags.get("dataset"):
        ref = pos[-1].replace(":", ".", 1)
        c = client()
        ds = bigquery.Dataset(ref)
        ds.location = flags.get("location", "US")
        c.create_dataset(ds, exists_ok=True)
        sys.stderr.write("dataset %s ready\n" % ref)
        return
    if flags.get("table"):
        if len(pos) < 2:
            die("mk --table requires <ref> <schema>")
        ref, schema = pos[0].replace(":", ".", 1), pos[1]
        c = client()
        cols = []
        for spec in schema.split(","):
            name, typ = spec.split(":", 1)
            typ = {"FLOAT": "FLOAT64", "BOOLEAN": "BOOL"}.get(typ, typ)
            cols.append(bigquery.SchemaField(name, typ))
        t = bigquery.Table(ref, cols)
        t.time_partitioning = bigquery.TimePartitioning(field="date")
        c.create_table(t, exists_ok=True)
        sys.stderr.write("table %s ready\n" % ref)
        return
    die("mk requires --dataset or --table")


def cmd_rm(flags: dict) -> None:
    from google.cloud import bigquery

    pos = flags["positional"]
    if flags.get("t") and pos:
        ref = pos[-1].replace(":", ".", 1)
        try:
            client().delete_table(ref, not_found_ok=True)
            sys.stderr.write("deleted %s\n" % ref)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("rm %s ignored: %s\n" % (ref, e))
        return
    die("unsupported rm form")


def main() -> None:
    argv = sys.argv[1:]
    # peel --project_id=P wherever it appears
    proj = None
    rest = []
    for a in argv:
        if a.startswith("--project_id="):
            proj = a.split("=", 1)[1]
        else:
            rest.append(a)
    if proj:
        os.environ["GOOGLE_CLOUD_PROJECT"] = proj
    if not rest:
        die("no command given")
    cmd, flags = rest[0], parse_args(rest[1:])
    handlers = {
        "query": cmd_query,
        "load": cmd_load,
        "show": cmd_show,
        "mk": cmd_mk,
        "rm": cmd_rm,
    }
    h = handlers.get(cmd)
    if not h:
        die("bq-stub does not implement %r; the cloud path must not shell to real bq" % cmd)
    h(flags)


if __name__ == "__main__":
    main()
