"""Static contract: a Grafana stat panel must never paint absence as healthy.

`or vector(C)` substitutes a constant for an empty query result, which is what a
metric family looks like when the process that emits it is gone. When C also
lands in the panel's healthy threshold band, a dead reporter and a healthy
system render as the same number in the same colour, and the operator reads the
one that means "fine". That is the dashboard form of `noDataState: OK`.

The rule below is deliberately narrow so it can be mechanical: it does not ban
constant fallbacks, it bans the specific combination where the substituted
constant is coloured green. A counter with no series until its first event
legitimately needs a 0 — but it must either be coloured neutrally or, better,
draw its 0 from a series that proves the reporter is alive (`or (<gauge> * 0)`),
which is not a bare constant and is therefore not matched here.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DASHBOARDS = REPO / "backend/charts/monitoring/dashboards"

# A bare constant fallback: `or vector(0)`, not `or (max(foo) * 0)`.
BARE_VECTOR_FALLBACK = re.compile(r"\bor\s+vector\s*\(\s*(-?\d+(?:\.\d+)?)\s*\)")
HEALTHY_COLORS = {
    "green",
    "dark-green",
    "semi-dark-green",
    "light-green",
    "super-light-green",
}
# Only `stat` panels: the threshold colour is the whole signal there, because a
# single number stands in for "is this healthy". A timeseries renders its shape
# regardless of thresholds, and its thresholds are not drawn at all unless
# `thresholdsStyle` opts in.
GUARDED_PANEL_TYPE = "stat"


def _iter_panels(panels):
    for panel in panels:
        if panel.get("type") == "row":
            yield from _iter_panels(panel.get("panels", []))
            continue
        yield panel
        yield from _iter_panels(panel.get("panels", []))


def threshold_color_for(steps, value):
    """The colour Grafana paints `value`, given a threshold step list.

    The base step carries `value: null`, meaning negative infinity; a step
    applies from its own value upward until the next one starts.
    """

    color = None
    for step in sorted(steps, key=lambda s: (s.get("value") is not None, s.get("value") or 0)):
        bound = step.get("value")
        if bound is None or value >= bound:
            color = step.get("color")
    return color


def bare_fallback_offenses():
    offenses = []
    for path in sorted(DASHBOARDS.rglob("*.json")):
        dashboard = json.loads(path.read_text())
        for panel in _iter_panels(dashboard.get("panels", [])):
            if panel.get("type") != GUARDED_PANEL_TYPE:
                continue
            steps = (panel.get("fieldConfig", {}).get("defaults", {}).get("thresholds") or {}).get("steps") or []
            for target in panel.get("targets", []):
                for match in BARE_VECTOR_FALLBACK.finditer(target.get("expr") or ""):
                    constant = float(match.group(1))
                    color = threshold_color_for(steps, constant)
                    if color in HEALTHY_COLORS:
                        offenses.append(
                            f"{path.relative_to(REPO)} :: {panel.get('title')!r} substitutes "
                            f"{match.group(1)} for an absent series and paints it {color!r}"
                        )
    return offenses


def test_no_stat_panel_paints_a_constant_absence_fallback_green():
    offenses = bare_fallback_offenses()
    assert offenses == [], (
        "A stat panel falls back to a constant that renders in a healthy colour, so a dead "
        "reporter is indistinguishable from a healthy system:\n  " + "\n  ".join(offenses)
    )


def test_guard_rejects_the_historical_shape_it_exists_to_catch():
    """The pre-fix 'Circuit open' panel: `or vector(0)` over a green base band."""

    steps = [{"color": "green", "value": None}, {"color": "red", "value": 1}]
    assert threshold_color_for(steps, 0) == "green"
    assert BARE_VECTOR_FALLBACK.search("max(llm_gateway_circuit_open) or vector(0)")


def test_guard_accepts_a_fallback_anchored_to_a_live_series():
    """The fix: the 0 exists only while something is still reporting."""

    anchored = (
        "round(sum(increase(llm_gateway_request_rejections_total[$__range]))) or (max(llm_gateway_config_info) * 0)"
    )
    assert BARE_VECTOR_FALLBACK.search(anchored) is None


def test_guard_accepts_a_constant_fallback_that_is_not_healthy_coloured():
    """'Journeys reporting (of 3)': absence falls to 0, which is red, not green."""

    steps = [{"color": "red", "value": None}, {"color": "orange", "value": 2}, {"color": "green", "value": 3}]
    assert threshold_color_for(steps, 0) == "red"
