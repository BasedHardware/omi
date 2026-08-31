"""Static contract: the Core Features dashboard must stay inside Grafana's proxy budget.

Grafana batches every visible panel's queries into one POST /api/ds/query, and the
monitor.omi.me ingress in front of it cuts the connection off at 30s. A dashboard
whose visible panels sum past that budget does not render "some panels slowly" —
the whole batch 502s and every panel, including cheap gauges that never ran,
paints as no-data with a warning triangle. The expensive shapes here are wide
range queries: histogram_quantile over high-cardinality bucket families and
rate() windows much larger than the step.

The guards below keep the dashboard from drifting back over the line:
  - auto-refresh no faster than 1m (a 30s refresh retriggers the batch before
    the previous one can finish);
  - histogram_quantile timeseries pinned to a >=2m panel interval;
  - range-window rate()/increase() on timeseries no wider than 5m ($__range on
    instant stats is fine — one evaluation, no per-step lookback);
  - a row marked collapsed must actually nest its panels, because a collapsed
    row with sibling panels still queries them on first paint.

Scope is deliberately omi-core-features.json only; other dashboards have not
been budget-audited.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DASHBOARD = REPO / "backend/charts/monitoring/dashboards/general/omi-core-features.json"

TIMESERIES = "timeseries"

# `rate(metric[5m])` and friends: the range selector inside a rate/increase call.
RATE_WINDOW = re.compile(r"\b(?:rate|increase)\s*\([^[\]]*?\[(\d+)(ms|s|m|h|d|w)\]")

UNIT_SECONDS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration_seconds(text):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d|w)\s*", text or "")
    if match is None:
        return None
    return float(match.group(1)) * UNIT_SECONDS[match.group(2)]


def _iter_panels(panels):
    for panel in panels:
        yield panel
        yield from _iter_panels(panel.get("panels", []))


def dashboard():
    return json.loads(DASHBOARD.read_text())


def timeseries_panels(doc):
    return [p for p in _iter_panels(doc.get("panels", [])) if p.get("type") == TIMESERIES]


def test_refresh_is_no_faster_than_one_minute():
    refresh = parse_duration_seconds(dashboard().get("refresh"))
    assert refresh is not None, "dashboard refresh must be a plain duration like '2m', not empty or symbolic"
    assert refresh >= 60, (
        f"refresh {dashboard().get('refresh')!r} re-issues the /api/ds/query batch before a 30s-budgeted "
        "batch can settle; keep it at 1m or slower"
    )


def test_histogram_timeseries_pin_a_slow_query_interval():
    slow = []
    for panel in timeseries_panels(dashboard()):
        if not any("histogram_quantile" in (t.get("expr") or "") for t in panel.get("targets", [])):
            continue
        interval = parse_duration_seconds(panel.get("interval"))
        assert interval is not None, (
            f"{panel.get('title')!r} plots histogram_quantile without a panel interval; the step then "
            "follows the datasource timeInterval and a 24h range explodes the query cost"
        )
        if interval < 120:
            slow.append(f"{panel.get('title')!r} interval {panel.get('interval')!r}")
    assert slow == [], "histogram_quantile timeseries must pin an interval of 2m or slower:\n  " + "\n  ".join(slow)


def test_timeseries_rate_windows_are_at_most_five_minutes():
    wide = []
    for panel in timeseries_panels(dashboard()):
        for target in panel.get("targets", []):
            expr = target.get("expr") or ""
            for match in RATE_WINDOW.finditer(expr):
                window = int(match.group(1)) * UNIT_SECONDS[match.group(2)]
                if window > 300:
                    wide.append(f"{panel.get('title')!r} uses {match.group(0).split('[')[-1]}")
    assert wide == [], (
        "timeseries rate()/increase() windows wider than 5m pay the lookback at every step and blow the "
        "30s batch budget; instant stats may keep $__range:\n  " + "\n  ".join(wide)
    )


def test_collapsed_rows_nest_their_panels():
    empty = []
    for panel in _iter_panels(dashboard().get("panels", [])):
        if panel.get("type") == "row" and panel.get("collapsed") is True:
            if not panel.get("panels"):
                empty.append(f"{panel.get('title')!r}")
    assert empty == [], (
        "a row marked collapsed but with no nested panels leaves its panels as queried siblings — the "
        "collapse hides nothing and first paint still pays for them:\n  " + "\n  ".join(empty)
    )


PTT_JOURNEY = 'journey="realtime_voice"'
PTT_SCRAPE_JOB = 'job="cloud-run-application-metrics"'


def _ptt_exprs(doc):
    found = []
    for panel in _iter_panels(doc.get("panels", [])):
        for target in panel.get("targets", []):
            expr = target.get("expr") or ""
            if PTT_JOURNEY in expr:
                found.append((panel.get("title"), panel.get("type"), expr))
    return found


def test_ptt_timeseries_are_scoped_to_cloud_run_application_metrics():
    """Zero-init cartesian children on listen/pusher/gateway must not enter PTT graphs.

    Live 24h traffic for realtime_voice is only on cloud-run-application-metrics.
    rate() on idle zero-init series spikes on scrape/reset and draws phantom
    desktop_linux / incomplete_attempt / unknown lines. The job filter is the
    load-bearing honesty fix; grouping by outcome|issue_class|client_kind stays.
    """

    missing = []
    seen_timeseries = 0
    for title, panel_type, expr in _ptt_exprs(dashboard()):
        if panel_type == TIMESERIES:
            seen_timeseries += 1
        if PTT_SCRAPE_JOB not in expr:
            missing.append(f"{title!r} ({panel_type}): {expr}")
    assert seen_timeseries >= 3, (
        "expected the PTT outcome / issue_class / client_kind timeseries; "
        f"found {seen_timeseries} realtime_voice timeseries"
    )
    assert missing == [], (
        "PTT PromQL must restrict selectors to the Cloud Run scrape job so "
        "listen/pusher/gateway zero-init children cannot appear:\n  " + "\n  ".join(missing)
    )
