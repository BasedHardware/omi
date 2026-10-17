"""Omi TV v3: Direction A's five story columns in the old board's chart vocabulary.

Each column reads Growth → Activation → Retention → Revenue → Health. A compact
stat panel (headline numbers with a prior-period change) sits above native charts
whose form matches the question: stacked weekly bars for composition, lines for
rates, cohort curves, histograms, a capture-source bar and an all-in cost stack
against revenue. Under each stat a one-row strip shows the API's prior-period
change: percentage points for rates, relative % for counts and money.
Data comes from `/api/omi/stats/wall/series/<name>`, which reuses the v2 snapshot
definitions; every chart's latest point is the stat above it. Infinity is the
only external plugin. Metrics without a working source are listed in the compact
coverage-gaps table, never drawn as empty charts.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DS = {"type": "yesoreyeram-infinity-datasource", "uid": "omi-admin-api"}
BASE = "http://127.0.0.1:8899/api/omi/stats/wall/series"
COLUMNS = ["Growth", "Activation", "Retention", "Revenue", "Health"]

# Reference categorical palette, dark-surface steps (dataviz palette.md). Platform
# hues are reserved for platform splits on every chart.
PLATFORM = {"macOS": "#3987e5", "Mobile": "#d95926", "Other": "#199e70", "MCP-only": "#c98500"}
TOTAL = "#e8e6df"
MUTED = "#6b6a63"
VIOLET, LILAC, RED, GREEN = "#9085e9", "#c4bdf4", "#e66767", "#008300"
# Status steps (dataviz palette.md, fixed): ≥3:1 on the dark surface; the strip's
# ▲/▼ glyph carries direction, so color is never the only signal.
STATUS_GOOD, STATUS_BAD = "#0ca30c", "#d03b3b"
PLANS = {"Unlimited": "#3987e5", "Unlimited v2": "#9085e9", "Operator": "#199e70",
         "Plus": "#c98500", "Architect": "#d55181", "Other": MUTED}
COST = {"GCP": "#5c6b80", "Vertex LLM": "#8494ab", "OpenAI": "#aab6c6", "Anthropic": "#cdd5df"}
# Estimated lines are drawn apart from invoiced ones: amber, low opacity.
ESTIMATE_OPACITY = 55  # invoiced bars use 88
ESTIMATE = {"STT est.": "#c98500", "SaaS est.": "#e0b45c"}
GOOD_MARK, BAD_MARK = "\u200b", "\u2060"  # tone markers set by the series API

# Column x/width; Health and Revenue carry the widest charts.
GEOMETRY = {"Growth": (0, 5), "Activation": (5, 5), "Retention": (10, 5), "Revenue": (15, 4), "Health": (19, 5)}
STAT_H = 3
STRIP_H = 1
WALL_H = 27


def target(series, frame, columns, ref="A"):
    return {"refId": ref, "datasource": DS, "type": "json", "source": "url", "format": "table",
            "parser": "backend", "url": f"{BASE}/{series}", "url_options": {"method": "GET"},
            "root_selector": f"frames.{frame}",
            "columns": [{"selector": s, "text": t, "type": ty} for s, t, ty in columns]}


def color(name, hex_):
    # displayName pins the legend label: multi-frame panels otherwise prefix the refId.
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "displayName", "value": name},
                           {"id": "color", "value": {"mode": "fixed", "fixedColor": hex_}}]}


def prop(name, *props):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": k, "value": v} for k, v in props]}


def hidden(name):
    return prop(name, ("custom.hideFrom", {"legend": True, "tooltip": False, "viz": True}))


def dashed(name, hex_):
    return {"matcher": {"id": "byName", "options": name}, "properties": [
        {"id": "displayName", "value": name},
        {"id": "color", "value": {"mode": "fixed", "fixedColor": hex_}},
        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [6, 4]}},
        {"id": "custom.drawStyle", "value": "line"}, {"id": "custom.fillOpacity", "value": 0},
        {"id": "custom.stacking", "value": {"mode": "none", "group": "A"}},
        {"id": "custom.lineWidth", "value": 2}]}


def chart(title, description, targets, *, unit, axis, draw="line", stack=False, overrides=(),
          legend=True, time_from=None, decimals=None, soft_min=0, extra=None, kind="timeseries"):
    custom = {"drawStyle": draw, "lineWidth": 2 if draw == "line" else 1,
              "fillOpacity": 88 if draw == "bars" else (40 if stack else 0),
              "gradientMode": "none", "showPoints": "never", "pointSize": 4, "spanNulls": True,
              "barAlignment": 0, "axisPlacement": "left", "axisLabel": axis,
              "axisSoftMin": soft_min, "axisBorderShow": False, "axisCenteredZero": False,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"},
              "lineInterpolation": "smooth" if draw == "line" else "linear",
              "thresholdsStyle": {"mode": "off"}}
    defaults = {"unit": unit, "color": {"mode": "fixed", "fixedColor": TOTAL}, "custom": custom,
                "noValue": "Loading…"}
    if decimals is not None:
        defaults["decimals"] = decimals
    panel = {"type": kind, "title": title, "description": description, "datasource": DS,
             "targets": targets, "fieldConfig": {"defaults": defaults, "overrides": list(overrides)},
             "options": {"legend": {"showLegend": legend, "displayMode": "list", "placement": "bottom"},
                         "tooltip": {"mode": "multi", "sort": "none"}}}
    if time_from:
        panel.update(timeFrom=time_from, hideTimeOverride=True)
    if extra:
        extra(panel)
    return panel


def stat(title, description, items):
    """One stat panel per column: the headline value per metric.

    The prior-period change sits in the strip below (`delta_strip`): Grafana's
    native percent change is relative only, and rates change in percentage points.
    """
    targets, overrides = [], []
    for i, (series, frame, name, unit, decimals) in enumerate(items):
        targets.append(target(series, frame, [("value", name, "number")], chr(65 + i)))
        overrides.append(prop(name, ("displayName", name), ("unit", unit), ("decimals", decimals)))
    return {"type": "stat", "title": title, "description": description, "datasource": DS,
            "targets": targets,
            "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": TOTAL}, "noValue": "—"},
                            "overrides": overrides},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "textMode": "value_and_name", "colorMode": "value", "graphMode": "none",
                        "justifyMode": "center", "orientation": "vertical", "wideLayout": True,
                        "showPercentChange": False,
                        "text": {"titleSize": 13, "valueSize": 30}}}


def delta_strip(column, keys, description):
    """Prior-period change per headline metric, in the stat's field order.

    Text comes from the series API (`headline.strip_<column>`); its invisible tone
    marker colors it: green good, red bad (cost up is bad), muted when flat.
    """
    tone = lambda mark, hex_: {"type": "regex", "options": {"pattern": f".*{mark}.*", "result": {"color": hex_}}}
    return {"type": "stat", "title": "", "description": description, "datasource": DS, "transparent": True,
            "targets": [target("headline", f"strip_{column.lower()}", [(k, k, "string") for k in keys])],
            "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": MUTED}, "noValue": "—",
                                         "mappings": [tone(GOOD_MARK, STATUS_GOOD), tone(BAD_MARK, STATUS_BAD)]},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/", "values": False},
                        "textMode": "value", "colorMode": "value", "graphMode": "none",
                        "justifyMode": "center", "orientation": "vertical", "wideLayout": True,
                        "showPercentChange": False, "text": {"valueSize": 14}}}


PLATFORM_COLUMNS = [("macos", "macOS", "number"), ("mobile", "Mobile", "number"),
                    ("other", "Other", "number")]
PLATFORM_OVERRIDES = [color(n, h) for n, h in PLATFORM.items()]
DATE = ("date", "date", "timestamp")


def rate_lines(title, description, frame, series="activation", time_from="95d", total="All"):
    return chart(title, description,
                 [target(series, frame, [DATE, ("total", total, "number"), *PLATFORM_COLUMNS,
                                         ("n", "Cohort users", "number")])],
                 unit="percent", axis="% of cohort", decimals=0, time_from=time_from,
                 overrides=[*PLATFORM_OVERRIDES, prop(total, ("custom.lineWidth", 3)),
                            hidden("Cohort users"),
                            prop("Cohort users", ("unit", "short"))])


USERS = ("Users are deduplicated persons with qualified use (v2 definitions): a capture, conversation, "
         "chat or ≥2 successful MCP calls on a UTC day, not just an app open. ")
QUALIFIED_MAU = ("MAU here is qualified MAU (~10K). The \"Omi Cost vs Revenue\" artifact divides by any-event "
                 "PostHog MAU (~22K, $3.41 in October), so its per-user cost is about half of this one. ")
ALL_IN = ("All-in cost counts every line: GCP net of committed-use credits (one-time incidents excluded), "
          "Vertex/Gemini LLM, OpenAI and Anthropic invoices, STT and SaaS. STT has no invoice feed yet: it is "
          "a $5.3K/month estimate from the Soniox console (October 2026, read 2026-10-16; the FinOps "
          "stt_vendor_low model overstated it ~2×). SaaS is a fixed $4.8K/month estimate. ")


def columns():
    growth = [
        stat("Growth", USERS + "Weekly, daily and monthly users over the trailing 7 / 1 / 30 complete UTC days (MCP-only included).",
             [("headline", "wau", "Weekly users", "locale", 0), ("headline", "dau", "Daily users", "locale", 0),
              ("headline", "mau", "Monthly users", "locale", 0)]),
        (7, chart("Weekly users · by platform",
                  USERS + "Trailing 7-day periods ending each date (UTC), stacked by each user's primary platform. Starts at the first period after mobile telemetry began (week of 2026-05-04); earlier periods undercount mobile and are not drawn. MCP-only = users whose only qualified use was ≥2 successful MCP calls on a day (blank before that marker existed). The latest bar is the weekly-users stat.",
                  [target("growth", "weekly", [DATE, *PLATFORM_COLUMNS, ("mcp", "MCP-only", "number")])],
                  unit="short", axis="users", draw="bars", stack=True, overrides=PLATFORM_OVERRIDES,
                  time_from="182d")),
        (6, chart("New, returning & lost users",
                  "Each week's active users = returning (also active the prior 7 days) + back after a break + new (first seen this week). Lost = last week's users not active this week, drawn below zero.",
                  [target("growth", "weekly", [DATE, ("retained", "Returning", "number"),
                                               ("resurrected", "Back after a break", "number"),
                                               ("new", "New", "number"), ("churned", "Lost", "number")])],
                  unit="short", axis="users", draw="bars", stack=True, soft_min=None, time_from="182d",
                  overrides=[color("Returning", MUTED), color("Back after a break", LILAC), color("New", VIOLET),
                             color("Lost", RED)])),
        (4, chart("Quick ratio",
                  "Users gained ÷ users lost each week: (new + back after a break) ÷ lost. Above 1.0 the active base is growing.",
                  [target("growth", "weekly", [DATE, ("quickRatio", "Quick ratio", "number")])],
                  unit="none", axis="ratio", decimals=2, legend=False, time_from="182d",
                  extra=threshold_line(1, MUTED))),
        (4, chart("Stickiness (DAU/WAU)",
                  "Average daily users ÷ weekly users: qualified user-days in the 7-day period ÷ (7 × weekly users). 100% = every weekly user is active every day.",
                  [target("growth", "weekly", [DATE, ("stickiness", "Stickiness", "number")])],
                  unit="percent", axis="% of weekly users", decimals=0, legend=False, time_from="182d")),
    ]
    activation = [
        stat("Activation", "Week-one activation: new users (first seen in the weekly cohort, 180-day lookback so returning users are not counted as new) with ≥2 qualified days in days 1–7. Saved capture: share of the same cohort with a saved own-device or mic capture in week one, the main activation driver. Change in percentage points vs the prior weekly cohort.",
             [("headline", "activation", "Week-one activation", "percent", 1),
              ("headline", "capture", "Saved capture · week one", "percent", 1)]),
        (8, rate_lines("Activation · by platform",
                       "Week-one activation for weekly new-user cohorts, dated by the cohort's last day, split by the platform users first arrived on. Rates use the full cohort, including users who never qualified. The latest point is the stat.",
                       "activation")),
        (7, rate_lines("Saved capture · week one",
                       "Share of each new-user cohort with a saved, non-discarded own-device or mic conversation in days 1–7, by first platform. The latest point is the stat.",
                       "capture")),
        (7, chart("Activation by capture source",
                  "Latest matured new-user cohort (the activation stat's cohort), split by what users captured with in week one: an Omi pendant, several devices, Limitless, Apple Watch, another device, phone mic and/or Mac, or nothing saved. Bars are each group's week-one activation; the group size is in the label. Groups sum to the cohort.",
                  [target("activation", "sources", [("source", "Capture source", "string"),
                                                    ("activation", "Week-one activation", "number")])],
                  unit="percent", axis="% activated", decimals=0, legend=False, kind="barchart",
                  extra=barchart_options(horizontal=True, color_hex=PLATFORM["macOS"], max_value=112))),
    ]
    retention = [
        stat("Retention", "Retained if activated: activated new users who qualify again in days 8–37. Established: users active in both of the prior two weeks who are active this week. Change in percentage points vs the prior cohort / week.",
             [("headline", "retained", "Retained if activated", "percent", 1),
              ("headline", "established", "Established", "percent", 1)]),
        (8, chart("Weekly cohort retention · W0–W8",
                  "Share of each weekly new-user cohort (180-day history check, as the activation stat) with a qualified day in week k after first seen. Only fully observed weeks are drawn; darker = older cohort.",
                  [target("retention", "curve", [])],
                  unit="percent", axis="% of cohort", decimals=0, kind="trend", soft_min=0,
                  extra=curve_options)),
        (7, chart("Retention · weekly",
                  "Established retention by week (solid) and retained-if-activated by the cohort's last first-seen day (dashed). Latest points are the stats.",
                  [target("retention", "established", [DATE, ("total", "Established", "number")], "A"),
                   target("retention", "retained", [DATE, ("total", "Retained if activated", "number")], "B")],
                  unit="percent", axis="%", decimals=0, time_from="125d",
                  overrides=[color("Established", TOTAL), dashed("Retained if activated", VIOLET)])),
        (7, chart("Power users · days active",
                  "Share of weekly users by number of active days in the latest 7 days, against the same period 4 weeks earlier. A rise on the right means habitual use.",
                  [target("retention", "power", [("days", "Days active", "string"),
                                                 ("This week", "This week", "number"),
                                                 ("4 weeks earlier", "4 weeks earlier", "number")])],
                  unit="percent", axis="% of weekly users", decimals=0, kind="barchart",
                  overrides=[color("This week", PLATFORM["macOS"]), color("4 weeks earlier", MUTED)],
                  extra=barchart_options())),
    ]
    revenue = [
        stat("Revenue", "MRR: live Stripe Omi-plan book (change = same-source FinOps 7-day change). Revenue per user = MRR ÷ monthly users (qualified MAU; change vs prior week). Hardware: Shopify net device sales, last complete Mon–Sun week vs the prior week. Relative % change.",
             [("headline", "mrr", "MRR", "currencyUSD", 0), ("headline", "arpmau", "Per user", "currencyUSD", 2),
              ("headline", "hardware", "Hardware", "currencyUSD", 0)]),
        (8, chart("MRR · by plan",
                  "Unlimited includes Neo. Daily FinOps snapshots of the Stripe plan book (deduplicated by snapshot date; known gaps: an unmapped enterprise price and two JPY subscriptions). The final point is the live Stripe book, the MRR stat. Shopify plan prepay is cash and never included.",
                  [target("revenue", "mrr", [DATE, ("unlimited", "Unlimited", "number"),
                                             ("unlimited_v2", "Unlimited v2", "number"),
                                             ("operator", "Operator", "number"), ("plus", "Plus", "number"),
                                             ("architect", "Architect", "number"),
                                             ("other", "Other", "number")])],
                  unit="currencyUSD", axis="USD / month", stack=True, decimals=0, time_from="45d",
                  overrides=[color(n, h) for n, h in PLANS.items()])),
        (7, chart("Revenue per user (ARPMAU)",
                  "Omi-plan MRR ÷ monthly users (qualified MAU: 30 days, MCP-inclusive) at each week end. History uses the FinOps book; the latest point is the stat. " + QUALIFIED_MAU,
                  [target("revenue", "arpmau", [DATE, ("arpmau", "ARPMAU", "number"), ("mau", "Monthly users", "number")])],
                  unit="currencyUSD", axis="USD / user / month", decimals=2, legend=False, time_from="60d",
                  overrides=[hidden("Monthly users"), prop("Monthly users", ("unit", "short"))])),
        (7, chart("Shopify sales · weekly",
                  "Net device sales (refunds restate their sale week, no tax/shipping) and Omi Unlimited plan prepay cash (reported separately, never MRR). Device units in the tooltip.",
                  [target("revenue", "hardware", [("date", "Week ending", "timestamp"),
                                                  ("hardwareUsd", "Hardware", "number"),
                                                  ("prepayUsd", "Plan prepay (cash)", "number"),
                                                  ("units", "Devices", "number")])],
                  unit="currencyUSD", axis="USD / week", decimals=0, kind="barchart",
                  overrides=[color("Hardware", PLATFORM["macOS"]), color("Plan prepay (cash)", MUTED),
                             hidden("Devices"), prop("Devices", ("unit", "short"))],
                  extra=barchart_options(time_x=True))),
    ]
    health = [
        stat("Health", ALL_IN + "Cost / day is the settled day D−2; cost per user is the 30-day all-in cost ÷ monthly users. " + QUALIFIED_MAU + "Relative % change; up is bad.",
             [("headline", "netCost", "Cost / day", "currencyUSD", 0),
              ("headline", "costPerMau", "Cost / user", "currencyUSD", 2)]),
        (8, chart("All-in cost vs revenue",
                  ALL_IN + "Settled through D−2. Invoiced lines are the solid blue-greys; STT est. (Soniox console) and SaaS est. (fixed) are the amber segments. The stack top is the cost stat. One-time GCP spikes (a service-day above 2× and $500 over its 14-day median, e.g. the 2026-09-07 Coldline migration) are excluded and shown in the tooltip. Revenue = FinOps MRR ÷ 30.4.",
                  [target("health", "cost", [DATE, ("gcp", "GCP", "number"),
                                             ("vertexLlm", "Vertex LLM", "number"),
                                             ("openai", "OpenAI", "number"), ("anthropic", "Anthropic", "number"),
                                             ("stt", "STT est.", "number"),
                                             ("saas", "SaaS est.", "number"),
                                             ("revenuePerDay", "Revenue", "number"),
                                             ("oneTimeExcluded", "One-time excluded", "number"),
                                             ("total", "All-in total", "number")])],
                  unit="currencyUSD", axis="USD / day", draw="bars", stack=True, decimals=0, time_from="35d",
                  legend=True,
                  overrides=[*[color(n, h) for n, h in COST.items()],
                             *[estimate(n, h) for n, h in ESTIMATE.items()],
                             dashed("Revenue", "#199e70"), prop("Revenue", ("custom.lineStyle", {"fill": "solid"})),
                             hidden("One-time excluded"), hidden("All-in total")])),
        (7, chart("Cost per user · 30d",
                  "All-in 30-day cost through D−2 ÷ the same window's monthly users. " + QUALIFIED_MAU + "Dashed: the cost per user at which blended margin reaches the 60% goal (0.4 × revenue per user), a sizing guide rather than the contract margin.",
                  [target("health", "costPerMau", [DATE, ("costPerMau", "Cost / user", "number"),
                                                   ("goal", "60% margin ceiling", "number")])],
                  unit="currencyUSD", axis="USD / user / 30d", decimals=2, time_from="60d",
                  overrides=[color("Cost / user", TOTAL), dashed("60% margin ceiling", GREEN)])),
        (7, coverage_table()),
    ]
    return dict(zip(COLUMNS, [growth, activation, retention, revenue, health]))


def estimate(name, hex_):
    """Estimated cost lines (STT, SaaS): stacked like the rest, amber and lighter."""
    o = color(name, hex_)
    o["properties"] += [{"id": "custom.fillOpacity", "value": ESTIMATE_OPACITY}, {"id": "custom.lineWidth", "value": 1}]
    return o


def threshold_line(value, hex_):
    def apply(panel):
        d = panel["fieldConfig"]["defaults"]
        d["thresholds"] = {"mode": "absolute", "steps": [{"color": "transparent", "value": None},
                                                         {"color": hex_, "value": value}]}
        d["custom"]["thresholdsStyle"] = {"mode": "dashed"}
    return apply


def barchart_options(horizontal=False, color_hex=None, time_x=False, max_value=None):
    def apply(panel):
        opts = panel["options"]
        opts.update(orientation="horizontal" if horizontal else "vertical", barWidth=0.8, groupWidth=0.75,
                    text={"valueSize": 14},
                    showValue="always" if horizontal else "never", stacking="none", xTickLabelRotation=0,
                    xTickLabelSpacing=0, fullHighlight=False, barRadius=0.08)
        if time_x:
            opts["xTickLabelSpacing"] = 60
        d = panel["fieldConfig"]["defaults"]
        d["custom"] = {"fillOpacity": 88, "gradientMode": "none", "lineWidth": 0,
                       "axisPlacement": "auto", "axisLabel": d["custom"]["axisLabel"],
                       "axisSoftMin": 0, "axisBorderShow": False}
        if color_hex:
            d["color"] = {"mode": "fixed", "fixedColor": color_hex}
        if max_value is not None:
            d.update(min=0, max=max_value)
    return apply


def curve_options(panel):
    d = panel["fieldConfig"]["defaults"]
    d["color"] = {"mode": "shades", "fixedColor": "#3987e5"}
    d["custom"]["showPoints"] = "always"
    panel["options"]["xField"] = "week"  # Infinity does not keep JSON key order
    panel["fieldConfig"]["overrides"] = [prop("week", ("unit", "none"), ("custom.axisLabel", "weeks since first seen"))]
    panel["options"]["legend"] = {"showLegend": True, "displayMode": "list", "placement": "right"}
    d["noValue"] = "Cohorts still filling"  # an empty frame, not "Cannot visualize data"


def coverage_table():
    return {"type": "table", "title": "Data & coverage",
            "description": "First row: the oldest series' data-through day (UTC) across every chart, and how many series are still filling; the board shows stale-but-real data rather than waiting. Below: wall metrics without a defensible source (2026-10-15 contract audit). They stay off the charts rather than showing empty panels or fake zeros. The route's full classified reason is in /api/omi/stats/wall/series/headline (gaps[].reason) and the v2 diagnostics.",
            "datasource": DS,
            "targets": [target("headline", "gaps", [("metric", "Metric", "string"), ("missing", "Missing", "string")])],
            "fieldConfig": {"defaults": {"custom": {"align": "left", "cellOptions": {"type": "auto", "wrapText": False}},
                                         "color": {"mode": "fixed", "fixedColor": MUTED}},
                            "overrides": [prop("Metric", ("custom.width", 150))]},
            "options": {"showHeader": False, "cellHeight": "sm", "footer": {"show": False}}}


def build_wall_board():
    panels = []
    for name, items in columns().items():
        x, w = GEOMETRY[name]
        head, *charts = items
        keys = [t["root_selector"].split(".")[-1] for t in head["targets"]]
        panels.append({**head, "gridPos": {"x": x, "y": 0, "w": w, "h": STAT_H}})
        panels.append({**delta_strip(name, keys, f"{name}: change vs the prior period, from the series API."),
                       "gridPos": {"x": x, "y": STAT_H, "w": w, "h": STRIP_H}})
        y = STAT_H + STRIP_H
        for i, (h, panel) in enumerate(charts):
            h += i == len(charts) - 1  # the last chart takes the spare row
            panels.append({**panel, "gridPos": {"x": x, "y": y, "w": w, "h": h}})
            y += h
    for i, panel in enumerate(panels, 1):
        panel["id"] = i
    return {"uid": "omi-tv-v2", "title": "Omi TV · v3", "schemaVersion": 39, "version": 1, "timezone": "utc",
            "refresh": "1m", "editable": True, "graphTooltip": 1, "tags": ["omi-tv", "v3"],
            "time": {"from": "now-182d", "to": "now"}, "timepicker": {"hidden": True}, "templating": {"list": []},
            "annotations": {"list": []}, "panels": panels, "links": [],
            "description": "Growth → Activation → Retention → Revenue → Health. Stats above native charts; v2 metric definitions via /api/omi/stats/wall/series. Every chart's latest point is the stat above it. Data-through day and missing sources are listed under Data & coverage."}


def write_wall_board():
    (HERE / "dashboards/omi-tv-v2.json").write_text(json.dumps(build_wall_board(), indent=2) + "\n")


if __name__ == "__main__":
    write_wall_board()
