#!/usr/bin/env python3
"""OpenAI and Anthropic organization cost, per usage day, straight off the provider APIs.

These are the INVOICE side of the LLM reconciliation: the gateway ledger explains most of
the OpenAI bill per user, and the difference (`llm_direct_residual`) is spread by each
user's OpenAI share. Anthropic has no ledger rows in this era (direct path), so the whole
Anthropic invoice is residual.

Bucket-to-day mapping, which is easy to get wrong:
  * OpenAI buckets are labelled by END time; usage day = end_time_iso - 1 day.
  * Anthropic buckets are labelled by START time; usage day = starting_at[:10].
Credentials live inside the two admin scripts; nothing is printed here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

OPENAI = pathlib.Path.home() / ".hermes/skills/openai-platform-admin/scripts/openai_admin.py"
ANTHROPIC = (
    pathlib.Path.home() / ".hermes/skills/openai-platform-admin/anthropic-platform/scripts/anthropic_platform.py"
)


def run_json(cmd: list[str]) -> dict:
    p = subprocess.run([sys.executable] + cmd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise SystemExit("provider pull failed: %s\n%s" % (cmd[0], p.stderr[-1500:]))
    return json.loads(p.stdout)


def openai_costs(start: str, end_excl: str) -> dict:
    t0 = int(dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp())
    t1 = int(dt.datetime.fromisoformat(end_excl).replace(tzinfo=dt.timezone.utc).timestamp())
    days = max(1, (t1 - t0) // 86400)
    merged = None
    while True:
        page = run_json(
            [
                str(OPENAI),
                "costs",
                "--start-time",
                str(t0),
                "--end-time",
                str(t1),
                "--bucket-width",
                "1d",
                "--limit",
                str(min(180, days)),
                "--group-by",
                "line_item,project_id",
            ]
        )
        if merged is None:
            merged = page
        else:
            merged["data"].extend(page["data"])
        if not page.get("has_more") or not page.get("next_page"):
            break
        # the admin script has no cursor flag; advance the window past the last bucket instead
        last_end = max(b["end_time"] for b in page["data"])
        if last_end >= t1:
            break
        t0 = last_end
    merged["has_more"] = False
    merged["next_page"] = None
    return merged


def anthropic_costs(start: str, end_excl: str) -> dict:
    return run_json(
        [str(ANTHROPIC), "cost", "--start", start + "T00:00:00Z", "--end", end_excl + "T00:00:00Z", "--limit", "31"]
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="last usage day, inclusive")
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()
    raw = pathlib.Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    end_excl = (dt.date.fromisoformat(a.end) + dt.timedelta(days=1)).isoformat()

    oai = openai_costs(a.start, end_excl)
    (raw / "openai_cost_daily.json").write_text(json.dumps(oai, indent=1))
    tot = {}
    for b in oai["data"]:
        d = (dt.date.fromisoformat(b["end_time_iso"][:10]) - dt.timedelta(days=1)).isoformat()
        tot[d] = tot.get(d, 0.0) + sum(float(x["amount"]["value"]) for x in b["results"])
    for d in sorted(tot):
        sys.stderr.write("  openai %s $%.2f\n" % (d, tot[d]))

    ant = anthropic_costs(a.start, end_excl)
    (raw / "anthropic_cost_daily.json").write_text(json.dumps(ant, indent=1))
    tot = {}
    for b in ant["data"]:
        d = b["starting_at"][:10]
        tot[d] = tot.get(d, 0.0) + sum(float(x["amount_usd"]) for x in b["results"])
    for d in sorted(tot):
        sys.stderr.write("  anthropic %s $%.2f\n" % (d, tot[d]))


if __name__ == "__main__":
    main()
