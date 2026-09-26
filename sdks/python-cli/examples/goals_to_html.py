"""Export a CLI goal-list response to a standalone, offline HTML dashboard."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEMO_GOALS = [
    {"id": "demo-books", "title": "Read 10 books", "status": "background", "is_active": True,
     "metric": {"type": "scale", "current": 3, "target": 10, "unit": "books"}},
    {"id": "demo-walk", "title": "Walk every day", "status": "focused", "is_active": True,
     "metric": {"type": "boolean", "current": 1, "target": 1}},
    {"id": "demo-people", "title": "Reconnect with friends", "status": "achieved", "is_active": False,
     "desired_outcome": "Make time for the people who matter."},
    {"id": "demo-savings", "title": "Save for a trip", "status": "paused", "is_active": True,
     "metric": {"type": "numeric", "current": 250, "target": 1000, "unit": "USD"}},
]
STATUSES = {"background", "focused", "paused", "achieved", "abandoned"}
METRIC_TYPES = {"boolean", "scale", "numeric"}
LIVE_LIMIT = 100  # omi goal list --limit accepts 1..100 and has no offset/cursor.


class ExportError(Exception):
    """Expected input, retrieval, or output failure."""


def parse_goals(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        raise ExportError("Goal response must be a JSON array.")
    goals = []
    for index, item in enumerate(payload, 1):
        if not isinstance(item, dict):
            raise ExportError(f"Goal {index} must be an object.")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise ExportError(f"Goal {index} needs a nonempty title.")
        if item.get("status") is not None and (not isinstance(item["status"], str) or item["status"] not in STATUSES):
            raise ExportError(f"Goal {index} has an unsupported status.")
        if "is_active" in item and not isinstance(item["is_active"], bool):
            raise ExportError(f"Goal {index} has an invalid is_active value.")
        if item.get("metric") is not None:
            metric = item["metric"]
            if not isinstance(metric, dict) or not isinstance(metric.get("type"), str) or metric["type"] not in METRIC_TYPES:
                raise ExportError(f"Goal {index} has an invalid metric.")
        goals.append(item)
    return goals


def load_json(raw: str) -> list[dict]:
    try:
        return parse_goals(json.loads(raw.lstrip("\ufeff")))
    except (ValueError, TypeError) as exc:
        raise ExportError("Input is not valid JSON.") from exc


def cli_executable(explicit: str | None) -> str:
    if explicit:
        return explicit
    scripts = Path(sys.executable).parent
    for name in ("omi.exe", "omi"):
        candidate = scripts / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("omi") or "omi"


def retrieve_goals(executable: str, profile: str | None) -> list[dict]:
    command = [executable, "--json"]
    if profile:
        command.extend(["--profile", profile])
    command.extend(["goal", "list", "--include-inactive", "--limit", str(LIVE_LIMIT)])
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=45, check=False)
    except FileNotFoundError as exc:
        raise ExportError("Omi CLI executable not found; install omi-cli or use --omi-executable.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExportError("Omi CLI timed out after 45 seconds.") from exc
    except OSError as exc:
        raise ExportError(f"Could not launch Omi CLI: {exc.strerror or type(exc).__name__}.") from exc
    if result.returncode:
        # CLI diagnostics can include account details; do not copy them to the export or console.
        raise ExportError(f"Omi CLI failed (exit {result.returncode}); check the CLI directly for details.")
    return load_json(result.stdout)


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def formatted(value: float) -> str:
    return f"{value:,.6f}".rstrip("0").rstrip(".") if value % 1 else f"{value:,.0f}"


def progress(goal: dict) -> tuple[str, float | None]:
    metric = goal.get("metric")
    if metric is None:
        return "Qualitative goal — no numeric progress", None
    current, target = number(metric.get("current")), number(metric.get("target"))
    if current is None or target is None:
        return "Progress unavailable: missing or invalid value", None
    unit = metric.get("unit") if isinstance(metric.get("unit"), str) else ""
    values = f"{formatted(current)} / {formatted(target)}" + (f" {unit}" if unit else "")
    if metric["type"] == "boolean":
        if target not in (0, 1) or current not in (0, 1):
            return values + " · Boolean values must be 0 or 1", None
        if target == 0:
            return values + " · Zero target has no percentage", None
        return values, current * 100
    if target <= 0:
        return values + " · Target must be positive for percentage", None
    percentage = current / target * 100
    if not math.isfinite(percentage):
        return values + " · Percentage exceeds supported range", None
    return values, percentage


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def optional_text(goal: dict, key: str, label: str) -> str:
    value = goal.get(key)
    if not isinstance(value, str) or not value.strip() or (key == "desired_outcome" and value == goal["title"]):
        return ""
    return f'<p class="detail"><strong>{label}:</strong> <span dir="auto">{esc(value)}</span></p>'


def success_criteria(goal: dict) -> str:
    criteria = goal.get("success_criteria")
    if not isinstance(criteria, list):
        return ""
    items = "".join(f'<li dir="auto">{esc(item)}</li>' for item in criteria if isinstance(item, str) and item.strip())
    return f'<div class="detail"><strong>Success criteria:</strong><ul>{items}</ul></div>' if items else ""


def card(goal: dict) -> str:
    status = goal.get("status") or "unknown"
    active = goal.get("is_active")
    if active is None:
        active = status not in {"achieved", "abandoned"} if status != "unknown" else False
    metric = goal.get("metric")
    metric_type = metric["type"] if metric else "qualitative"
    label, percent = progress(goal)
    meter = ""
    if percent is not None:
        width = max(0, min(100, percent))
        meter = (f'<div class="meter" role="progressbar" aria-label="Progress" aria-valuemin="0" '
                 f'aria-valuemax="100" aria-valuenow="{width:.1f}"><span style="width:{width:.1f}%"></span></div>'
                 f'<p class="percent">{formatted(percent)}% progress</p>')
    state = "Active" if active else "Inactive"
    criteria = goal.get("success_criteria")
    search_parts = [goal["title"]]
    search_parts.extend(goal[key] for key in ("desired_outcome", "why_it_matters") if isinstance(goal.get(key), str))
    if isinstance(criteria, list):
        search_parts.extend(item for item in criteria if isinstance(item, str))
    search = " ".join(search_parts)
    deadline = optional_text(goal, "horizon_at", "Deadline")
    source = optional_text(goal, "source", "Source")
    details = (optional_text(goal, "desired_outcome", "Outcome")
               + optional_text(goal, "why_it_matters", "Why it matters")
               + success_criteria(goal) + deadline + source)
    return (f'<article class="goal" data-search="{esc(search)}" data-status="{esc(status)}" '
            f'data-state="{state.lower()}" data-type="{metric_type}">'
            f'<details class="goal-disclosure"><summary><span class="goal-title" dir="auto">{esc(goal["title"])}</span>'
            f'<span class="badges"><span class="badge">{esc(status.title())}</span><span class="badge">{state}</span></span>'
            f'</summary><div class="goal-details">{details}<p class="metric" dir="auto">{esc(label)}</p>{meter}</div>'
            f'</details></article>')


CSS = """
:root{color-scheme:light;--ink:#172530;--muted:#52636e;--line:#d9e3e5;--accent:#176d68;--paper:#f5f8f7}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1120px;margin:auto;padding:clamp(20px,4vw,48px)}header{display:flex;justify-content:space-between;gap:24px;align-items:start}
h1{font-size:clamp(2rem,4vw,3.25rem);line-height:1.1;margin:.3em 0}h2{font-size:1.3rem}h3{margin:0;font-size:1.2rem}
.eyebrow{color:var(--accent);font-weight:800;letter-spacing:.09em;text-transform:uppercase}.muted,.detail{color:var(--muted)}
.snapshot{display:inline-block;background:#dcefea;color:#10524f;padding:7px 12px;border-radius:99px;font-weight:700;white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:26px 0}.kpi,.goal,.controls{background:white;border:1px solid var(--line);border-radius:16px}
.kpi{padding:20px}.kpi strong{display:block;font-size:2rem;line-height:1.15}.kpi span{color:var(--muted)}
.controls{padding:20px;margin-bottom:22px}.fields{display:flex;gap:12px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:5px;flex:1 1 165px}
label{font-weight:700;font-size:.88rem}input,select,button{font:inherit;border-radius:9px;min-height:43px;padding:9px 12px}input,select{width:100%;border:1px solid #9aafb4;background:white;color:var(--ink)}
button{cursor:pointer;border:1px solid var(--accent);background:var(--accent);color:white;font-weight:700}button.secondary{background:white;color:var(--accent)}
:focus-visible{outline:3px solid #e5a22f;outline-offset:3px}.results{color:var(--muted);font-weight:700;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.goal{padding:22px;break-inside:avoid}.goal-disclosure summary{cursor:pointer;padding:2px 4px;border-radius:7px}.goal-title{font-size:1.2rem;font-weight:700;overflow-wrap:anywhere}.badges{display:inline-flex;gap:6px;flex-wrap:wrap;margin-inline-start:12px;vertical-align:middle}.goal-details{padding-top:12px}.goal-details ul{margin:6px 0 0;padding-inline-start:24px}
.badge{font-size:.75rem;font-weight:800;color:#115d58;background:#e4f2ef;border-radius:99px;padding:4px 9px;white-space:nowrap}.detail{margin:.7em 0}.metric{font-weight:700;margin:18px 0 8px;overflow-wrap:anywhere}.meter{height:10px;background:#e4ebec;border-radius:99px;overflow:hidden}.meter span{display:block;height:100%;background:var(--accent)}.percent{margin:5px 0 0;color:var(--muted);font-size:.88rem}
.empty{padding:36px;text-align:center;background:white;border:1px dashed var(--line);border-radius:16px}[hidden]{display:none!important}footer{margin-top:28px;color:var(--muted);font-size:.87rem}
@media(max-width:720px){header{display:block}.kpis{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.badges{margin:8px 0 0 12px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
@media print{body{background:white}.wrap{max-width:none;padding:0}.controls,.print-button,noscript{display:none!important}.kpi,.goal{box-shadow:none;break-inside:avoid}.grid{display:block}.goal{margin:0 0 12px}.goal-details,.goal-disclosure:not([open])>.goal-details{display:block!important}.goal-disclosure summary{cursor:default}footer{margin-top:14px}@page{margin:16mm}}
"""
JS = """
const cards=Array.from(document.querySelectorAll('.goal'));
const search=document.getElementById('search');
const status=document.getElementById('status');
const state=document.getElementById('state');
const type=document.getElementById('type');
const count=document.getElementById('results');
const empty=document.getElementById('no-matches');
function filterGoals(){
  const query=search.value.trim().toLocaleLowerCase();let shown=0;
  for(const card of cards){
    const visible=card.dataset.search.toLocaleLowerCase().includes(query)&&(!status.value||card.dataset.status===status.value)
      &&(!state.value||card.dataset.state===state.value)&&(!type.value||card.dataset.type===type.value);
    card.hidden=!visible;if(visible)shown++;
  }
  count.textContent=`Showing ${shown} of ${cards.length} goals`;
  empty.hidden=shown!==0||cards.length===0;
}
for(const control of [search,status,state,type])control.addEventListener('input',filterGoals);
document.getElementById('reset').addEventListener('click',()=>{search.value='';status.value='';state.value='';type.value='';filterGoals();search.focus()});
document.getElementById('print').addEventListener('click',()=>window.print());
let openBeforePrint=null;
window.addEventListener('beforeprint',()=>{
  const disclosures=Array.from(document.querySelectorAll('.goal-disclosure'));
  openBeforePrint=disclosures.filter(details=>details.open);
  for(const details of disclosures)details.open=true;
});
window.addEventListener('afterprint',()=>{
  if(openBeforePrint===null)return;
  for(const details of document.querySelectorAll('.goal-disclosure'))details.open=openBeforePrint.includes(details);
  openBeforePrint=null;
});
"""


def render(goals: list[dict], source: str, exported_at: datetime | None = None) -> str:
    goals = parse_goals(goals)
    total = len(goals)
    active = sum(g.get("is_active", g.get("status") not in {"achieved", "abandoned"}) is True for g in goals)
    completed = sum(g.get("status") == "achieved" for g in goals)
    rate = completed / total * 100 if total else 0
    timestamp = (exported_at or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    kpis = "".join(f'<div class="kpi"><strong>{value}</strong><span>{label}</span></div>' for value, label in
                   ((total, "Exported goals"), (active, "Active goals"), (completed, "Completed goals"),
                    (f"{rate:.0f}%", "Completion rate")))
    notes = (f"Live CLI snapshot: up to {LIVE_LIMIT} most recent goals; this may omit older goals."
             if source == "live" else "Snapshot of the supplied goals; completeness depends on the source data.")
    cards = "".join(card(goal) for goal in goals)
    empty = '<p class="empty">No exported goals. Add goals to the source and export again.</p>' if not goals else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Omi Goals Dashboard</title><style>{CSS}</style></head><body><main class="wrap">
<header><div><div class="eyebrow">Personal goals</div><h1>Omi Goals Dashboard</h1><p class="muted">Exported {esc(timestamp)}</p></div><span class="snapshot">Offline snapshot</span></header>
<section class="kpis" aria-label="Goal summary">{kpis}</section>
<section class="controls" aria-label="Goal filters"><h2>Explore goals</h2><div class="fields">
<div class="field"><label for="search">Search goals</label><input id="search" type="search" placeholder="Search title or description"></div>
<div class="field"><label for="status">Status</label><select id="status"><option value="">All statuses</option>{''.join(f'<option value="{s}">{s.title()}</option>' for s in sorted(STATUSES))}</select></div>
<div class="field"><label for="state">Active state</label><select id="state"><option value="">All states</option><option value="active">Active</option><option value="inactive">Inactive</option></select></div>
<div class="field"><label for="type">Metric type</label><select id="type"><option value="">All types</option><option value="qualitative">Qualitative</option><option value="boolean">Boolean</option><option value="scale">Scale</option><option value="numeric">Numeric</option></select></div>
<button id="reset" class="secondary" type="button">Clear filters</button><button id="print" class="print-button" type="button">Print / Save PDF</button></div></section>
<p id="results" class="results" role="status" aria-live="polite">Showing {total} of {total} goals</p>
<noscript><p>JavaScript is off. All exported goals remain visible; search and filters need JavaScript. Use your browser’s Print command to save a PDF.</p></noscript>
<section class="grid" aria-label="Exported goals">{cards}</section>{empty}<p id="no-matches" class="empty" hidden>No goals match these filters.</p>
<footer>{esc(notes)} This file contains personal goal data. Keep it private.</footer></main><script>{JS}</script></body></html>'''


def write_html(path: Path, content: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    except OSError as exc:
        raise ExportError(f"Could not write output file: {exc.strerror or type(exc).__name__}.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="Use synthetic goals without account access")
    source.add_argument("--input", metavar="FILE", help="Read JSON from FILE, or - for stdin")
    parser.add_argument("--output", required=True, type=Path, help="Destination HTML file")
    parser.add_argument("--omi-executable", help="Explicit Omi CLI executable path")
    parser.add_argument("--profile", help="Omi profile for live retrieval")
    args = parser.parse_args(argv)
    try:
        if args.demo:
            goals, label = parse_goals(DEMO_GOALS), "demo"
        elif args.input:
            try:
                raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise ExportError(f"Could not read input: {type(exc).__name__}.") from exc
            goals, label = load_json(raw), "file"
        else:
            goals, label = retrieve_goals(cli_executable(args.omi_executable), args.profile), "live"
        write_html(args.output, render(goals, label))
    except ExportError as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(goals)} goals to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
