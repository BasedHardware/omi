#!/usr/bin/env python3
"""VAD-gated audio hours actually forwarded to the cloud STT vendors, per usage day.

`omi_vad_gate_audio_seconds_total{outcome="sent"}` is the only measured quantity of vendor
STT volume we have: there is no Modulate/Soniox invoice feed. Multiplying it by a rate gives
the `stt_vendor_*` MODELLED component -- it is never presented as measured.

Read through the Grafana datasource proxy on monitor.omi.me (kubectl port-forward is denied
to the read-only identity). Token from ~/.hermes/skills/devops/omi-prometheus/references/.env;
never printed. Output shape matches what assemble_unit_cost.py expects:
  daily.d_vad_gate_audio_seconds.result.data.result[].values -> [ts, seconds]
with the bucket at time T carrying increase(...[1d]) over (T-1d, T], i.e. usage day T-1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

ENV = pathlib.Path.home() / ".hermes/skills/devops/omi-prometheus/references/.env"

DAILY = {
    "d_vad_gate_audio_seconds": 'sum by (outcome, mode) (increase(omi_vad_gate_audio_seconds_total[1d]))',
    "d_live_stt_accepted": "sum by (provider) (increase(omi_live_stt_accepted_total[1d]))",
    "d_parakeet_audio_duration_sum": "sum (increase(parakeet_audio_duration_seconds_sum[1d]))",
}


def load_env() -> tuple[str, str]:
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)
    ep = os.environ.get("OMI_PROMETHEUS_ENDPOINT", "https://monitor.omi.me").rstrip("/")
    return ep + "/api/datasources/proxy/uid/prometheus/api/v1", os.environ["OMI_PROMETHEUS_TOKEN"]


def call(base: str, tok: str, api: str, params) -> dict:
    cmd = ["curl", "-fsS", "-H", "Authorization: Bearer " + tok, "--get", f"{base}/{api}"]
    for k, v in params:
        cmd += ["--data-urlencode", f"{k}={v}"]
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=300)
    if p.returncode:
        return {"status": "error", "error": p.stderr[:300]}
    try:
        return json.loads(p.stdout)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="first usage day, inclusive")
    ap.add_argument("--end", required=True, help="last usage day, inclusive")
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()
    base, tok = load_env()
    # evaluation points are one day AFTER each usage day: increase(...[1d]) at T covers day T-1
    t0 = dt.datetime.fromisoformat(a.start).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
    t1 = dt.datetime.fromisoformat(a.end).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
    out = {
        "window": {"start": a.start, "end": a.end},
        "method": "query_range step=86400 with increase(...[1d]); bucket at T is usage day T-1",
        "endpoint": "Grafana datasource proxy uid=prometheus on monitor.omi.me",
        "daily": {},
    }
    for name, q in DAILY.items():
        r = call(
            base,
            tok,
            "query_range",
            [("query", q), ("start", str(int(t0.timestamp()))), ("end", str(int(t1.timestamp()))), ("step", "86400")],
        )
        out["daily"][name] = {"query": q, "result": r}
        n = len(r.get("data", {}).get("result", [])) if r.get("status") == "success" else 0
        sys.stderr.write("%s: %s series=%d\n" % (name, r.get("status"), n))
    raw = pathlib.Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "prom_stt_7d.json").write_text(json.dumps(out, indent=1))
    sent = {}
    for s in out["daily"]["d_vad_gate_audio_seconds"].get("result", {}).get("data", {}).get("result", []):
        if s["metric"].get("outcome") == "sent":
            for ts, v in s["values"]:
                day = (dt.datetime.fromtimestamp(int(ts), dt.timezone.utc) - dt.timedelta(days=1)).date().isoformat()
                sent[day] = sent.get(day, 0.0) + float(v) / 3600
    for d in sorted(sent):
        sys.stderr.write("  %s vad sent %.0f h\n" % (d, sent[d]))
    if not sent:
        sys.stderr.write("WARNING: no VAD 'sent' series; stt_vendor_* will be zero for this window\n")


if __name__ == "__main__":
    main()
