"""Omi TV v3: Direction A's five story columns in the old board's chart vocabulary.

Each column reads Growth → Activation → Retention → Revenue → Health. A compact
stat panel (headline numbers) sits above native charts whose form matches the
question: stacked weekly bars for composition, lines for rates, cohort curves,
histograms, a capture-source bar and an all-in cost stack against revenue. Under
each stat a one-row strip shows the API's prior-period change: percentage points
for rates, relative % for counts and money.
Data comes from `/api/omi/stats/wall/series/<name>`, which reuses the v2 snapshot
definitions; every chart's latest point is the stat above it. Infinity is the
only external plugin. The wall carries no diagnostics table: one "data through"
line sits under the Health column (David, 2026-10-16).

Grafana orders a frame's fields by name, so every multi-series panel pins its
field order (`organize`): legends, stacks and stat strips read in the authored
order, never alphabetically.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Variable-margin goal, shared with lib/wall-cost.ts (VARIABLE_MARGIN_TARGET).
MARGIN_GOAL_PCT = json.loads((HERE.parent / "lib/omi-tv-goals.json").read_text())["variableMarginTargetPct"]
GOAL_COST = f"{MARGIN_GOAL_PCT:g}% target cost"
DS = {"type": "yesoreyeram-infinity-datasource", "uid": "omi-admin-api"}
BASE = "http://127.0.0.1:8899/api/omi/stats/wall/series"
# Uptime is served by the Grafana pod's stats sidecar from fixed PromQL
# (backend/charts/monitoring/grafana/stats_proxy.py), not by the admin API.
UPTIME_URL = "http://127.0.0.1:8899/api/omi/stats/uptime"
JOURNEYS = {"Live capture": "#d55181", "Conversation saved": "#008300", "Chat answer": "#c4bdf4",
            "Push-to-talk": "#a8a69e"}  # slots 6, 7, lilac, neutral: never a platform hue
COLUMNS = ["Growth", "Activation", "Retention", "Revenue", "Health"]

# Reference categorical palette, dark-surface steps (dataviz palette.md). Platform
# hues (slots 1–4) are reserved for platform splits on every chart; other series
# use slots 5–8 or neutrals.
PLATFORM = {"Mobile": "#d95926", "macOS": "#3987e5", "Other": "#199e70", "MCP-only": "#c98500"}
TOTAL = "#e8e6df"
NEUTRAL = "#a8a69e"  # a single-series bar that is not a platform
MUTED = "#6b6a63"
VIOLET, MAGENTA, GREEN, RED, LILAC = "#9085e9", "#d55181", "#008300", "#e66767", "#c4bdf4"
REVENUE = VIOLET  # revenue is violet on every chart; cost is the blue-greys
# Status steps (dataviz palette.md, fixed): ≥3:1 on the dark surface; the strip's
# ▲/▼ glyph carries direction, so color is never the only signal.
STATUS_GOOD, STATUS_BAD = "#0ca30c", "#d03b3b"
# Slots 7, 5, 6, 8 (validated adjacent, dark), then neutrals for the small tail.
# Ratified display names: `unlimited` = Neo (legacy), `unlimited_v2` = Unlimited,
# `operator` = Pro.
PLAN_NAMES = {"unlimited": "Neo", "unlimited_v2": "Unlimited", "operator": "Pro", "plus": "Plus",
              "architect": "Architect"}
PLANS = {"Neo": VIOLET, "Unlimited": MAGENTA, "Pro": GREEN, "Plus": RED, "Architect": NEUTRAL,
         "Other": MUTED}
FREE = "Free $/day"
# Manual cost constants' read date (`STT_AS_OF` / `SAAS_AS_OF` in lib/wall-cost.ts;
# a board test keeps them equal). The API flags them stale after 35 days.
ESTIMATES_AS_OF = "2026-10-16"
COST = {"GCP": "#5c6b80", "Vertex LLM": "#8494ab", "OpenAI": "#aab6c6", "Anthropic": "#cdd5df"}
# Estimated lines are drawn apart from measured/invoiced ones: sand, low opacity.
ESTIMATE_OPACITY = 55  # invoiced bars use 88
ESTIMATE = {"STT est.": "#d8b46a", "SaaS est.": "#eedcb3", "Modulate modelled": "#e3c98a"}  # sand, not the MCP-only yellow
MEASURED = {"STT measured": "#aab6c6", "STT cash (Mercury)": "#bfc9d6", "SaaS measured (Mercury)": "#8494ab"}
GOOD_MARK, BAD_MARK = "​", "⁠"  # tone markers set by the series API
# Cohort curve: one neutral ramp, oldest dimmest → newest brightest and thickest
# (no platform hue: the curve is not a platform split). Index = cohort age.
# The API tags each cohort's field name with `age` invisible CURVE_MARKs (the
# joined frame no longer knows its source frame), so overrides find it by name.
CURVE_MARK = "\u200b"
CURVE_RAMP = ["#e8e6df", "#d4d2cc", "#c0bfb8", "#adaba5", "#999892", "#85847f", "#72706c",
              "#5e5d58", "#4a4945"]

# Column x/width. Health has two stats and two charts, so it is the narrow one.
GEOMETRY = {"Growth": (0, 5), "Activation": (5, 5), "Retention": (10, 5), "Revenue": (15, 5), "Health": (20, 4)}
STAT_H = 3
STRIP_H = 1
WALL_H = 27
# One value size and label size on every stat; sized so the widest value
# ("10,287", "$72.4K") fits a three-value column at 1440 px.
STAT_VALUE_SIZE, STAT_LABEL_SIZE = 26, 13


def target(series, frame, columns, ref="A"):
    url = UPTIME_URL if series == "uptime" else f"{BASE}/{series}"
    return {"refId": ref, "datasource": DS, "type": "json", "source": "url", "format": "table",
            "parser": "backend", "url": url, "url_options": {"method": "GET"},
            "root_selector": f"frames.{frame}",
            "columns": [{"selector": s, "text": t, "type": ty} for s, t, ty in columns]}


def organize(names):
    """Pin field order (Grafana sorts a frame's fields by name)."""
    return {"id": "organize", "options": {"indexByName": {n: i for i, n in enumerate(names)},
                                          "excludeByName": {}, "renameByName": {}}}


def color(name, hex_):
    # displayName pins the legend label: multi-frame panels otherwise prefix the refId.
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "displayName", "value": name},
                           {"id": "color", "value": {"mode": "fixed", "fixedColor": hex_}}]}


def prop(name, *props):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": k, "value": v} for k, v in props]}


def hidden(name):
    """In the tooltip only (counts behind a rate, an unplotted total)."""
    return prop(name, ("custom.hideFrom", {"legend": True, "tooltip": False, "viz": True}))


def short_label(override, label):
    """Shorter legend label for a series' own override, so a legend beside the plot stays narrow."""
    for prop_ in override["properties"]:
        if prop_["id"] == "displayName":
            prop_["value"] = label
    return override


# Legend labels for the cost stack, short enough for a legend beside a 4-column plot.
STACK_LABELS = {"GCP": "GCP", "Vertex LLM": "Vertex", "OpenAI": "OpenAI", "Anthropic": "Anthropic",
                "STT measured": "STT meas.", "STT cash (Mercury)": "STT cash", "SaaS measured (Mercury)": "SaaS meas.",
                "STT est.": "STT est.", "SaaS est.": "SaaS est.", "Modulate modelled": "Modulate"}


def legend_right(panel):
    """The legend beside the plot, not a list under it: a short panel has no room for the list."""
    panel["options"]["legend"]["placement"] = "right"


def mrr_extra(panel):
    """Legend beside the plot, and a break across missing book days: the Stripe book
    has no snapshot from 2026-10-07 to 2026-11-07, and a smooth ramp across that
    month reads as measured growth."""
    legend_right(panel)
    disconnect_after(1.5)(panel)


def dashed(name, hex_):
    return {"matcher": {"id": "byName", "options": name}, "properties": [
        {"id": "displayName", "value": name},
        {"id": "color", "value": {"mode": "fixed", "fixedColor": hex_}},
        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [6, 4]}},
        {"id": "custom.drawStyle", "value": "line"}, {"id": "custom.fillOpacity", "value": 0},
        {"id": "custom.stacking", "value": {"mode": "none", "group": "A"}},
        {"id": "custom.lineWidth", "value": 2}]}


def line(name, hex_, width=2):
    """A line drawn over a stacked-bar panel (revenue over cost)."""
    o = dashed(name, hex_)
    o["properties"] = [p for p in o["properties"] if p["id"] != "custom.lineStyle"]
    o["properties"][-1]["value"] = width
    return o


def maturing(name, hex_):
    """Shaded span of cohorts still inside their maturity window (series frame
    `maturing`: 1 from the newest closed cohort to now). Its own unit gives it a
    hidden 0–1 scale, so it fills the plot height behind the lines; the legend
    names it, the tooltip skips it."""
    return {"matcher": {"id": "byName", "options": name}, "properties": [
        {"id": "displayName", "value": name}, {"id": "unit", "value": "none"},
        {"id": "min", "value": 0}, {"id": "max", "value": 1},
        {"id": "color", "value": {"mode": "fixed", "fixedColor": hex_}},
        {"id": "custom.drawStyle", "value": "line"}, {"id": "custom.lineWidth", "value": 0},
        {"id": "custom.fillOpacity", "value": 14}, {"id": "custom.lineInterpolation", "value": "stepAfter"},
        {"id": "custom.axisPlacement", "value": "hidden"},
        {"id": "custom.hideFrom", "value": {"legend": False, "tooltip": True, "viz": False}}]}


def chart(title, description, targets, *, unit, axis="", draw="line", stack=False, overrides=(),
          legend=True, time_from=None, decimals=None, soft_min=0, extra=None, kind="timeseries"):
    """Native chart. `axis` is empty unless the unit alone is ambiguous: the title
    already names the measure, and a y label costs plot width."""
    custom = {"drawStyle": draw, "lineWidth": 2 if draw == "line" else 1,
              "fillOpacity": 88 if draw == "bars" else (40 if stack else 0),
              "gradientMode": "none", "showPoints": "never", "pointSize": 5, "spanNulls": True,
              "barAlignment": 0, "axisPlacement": "left", "axisLabel": axis,
              "axisSoftMin": soft_min, "axisBorderShow": False, "axisCenteredZero": False,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"},
              "lineInterpolation": "smooth" if draw == "line" else "linear",
              "thresholdsStyle": {"mode": "off"}}
    defaults = {"unit": unit, "color": {"mode": "fixed", "fixedColor": TOTAL}, "custom": custom,
                "noValue": "Loading…"}
    if decimals is not None:
        defaults["decimals"] = decimals
    names = list(dict.fromkeys(c["text"] for t in targets for c in t["columns"]))
    panel = {"type": kind, "title": title, "description": description, "datasource": DS,
             "targets": targets, "fieldConfig": {"defaults": defaults, "overrides": list(overrides)},
             "options": {"legend": {"showLegend": legend, "displayMode": "list", "placement": "bottom"},
                         "tooltip": {"mode": "multi", "sort": "none"}}}
    if len(names) > 2:
        panel["transformations"] = [organize(names)]
    if time_from:
        panel.update(timeFrom=time_from, hideTimeOverride=True)
    if extra:
        extra(panel)
    return panel


def stat(title, description, items):
    """One stat panel per column: the headline value per metric, one line each.

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
                        "justifyMode": "center", "orientation": "vertical",
                        "wideLayout": False,  # label always above value, on every stat
                        "showPercentChange": False,
                        "text": {"titleSize": STAT_LABEL_SIZE, "valueSize": STAT_VALUE_SIZE}}}


def delta_strip(column, keys, description):
    """Prior-period change per headline metric, in the stat's field order.

    Text comes from the series API (`headline.strip_<column>`); its invisible tone
    marker colors it: green good, red bad (cost up is bad), muted when flat.
    """
    tone = lambda mark, hex_: {"type": "regex", "options": {"pattern": f".*{mark}.*", "result": {"color": hex_}}}
    return {"type": "stat", "title": "", "description": description, "datasource": DS, "transparent": True,
            "targets": [target("headline", f"strip_{column.lower()}", [(k, k, "string") for k in keys])],
            "transformations": [organize(keys)],
            "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": MUTED}, "noValue": "—",
                                         "mappings": [tone(GOOD_MARK, STATUS_GOOD), tone(BAD_MARK, STATUS_BAD)]},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/", "values": False},
                        "textMode": "value", "colorMode": "value", "graphMode": "none",
                        "justifyMode": "center", "orientation": "vertical", "wideLayout": True,
                        "showPercentChange": False, "text": {"valueSize": 14}}}


def data_through():
    """The wall's single freshness line (headline `through` frame)."""
    return {"type": "stat", "title": "", "transparent": True, "datasource": DS,
            "description": "Day before the oldest source read behind the wall's charts (UTC), how many series are still filling, and how many headline stats are a retained earlier value because their source failed; the wall shows stale-but-real data rather than waiting. A chart's own last point can be older (cost settles D−2; Margin by plan has its own line). Sources without a defensible read path (crash-free, answer ratings, payer churn, activated → paid, gross margin) stay off the wall; the full classified reasons are in /api/omi/stats/wall/series/headline.",
            "targets": [target("headline", "through", [("text", "Data through", "string")])],
            "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": MUTED}, "noValue": "Data through —"},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/", "values": False},
                        "textMode": "value", "colorMode": "value", "graphMode": "none",
                        "justifyMode": "center", "orientation": "vertical", "wideLayout": True,
                        "showPercentChange": False, "text": {"valueSize": 12}}}


# Platform order everywhere: largest first, so stacks build up from the biggest.
PLATFORM_COLUMNS = [("mobile", "Mobile", "number"), ("macos", "macOS", "number"),
                    ("other", "Other", "number")]
PLATFORM_OVERRIDES = [color(n, h) for n, h in PLATFORM.items()]
DATE = ("date", "date", "timestamp")
# The uptime sidecar emits the UTC day as epoch milliseconds (a number); a plain "timestamp"
# column parses it to null and the panel reads "Data outside time range".
UPTIME_DATE = ("date", "date", "timestamp_epoch")


MATURING = ("The shaded band on the right is cohorts still inside their first week: a cohort is drawn 8 days "
            "after its last first-seen day, and a new one is added every day, so the line always ends 8 days back. ")


def rate_lines(title, description, frame, series="activation", time_from="95d", total="All"):
    # "Other" platform cohorts are a handful of users: their rate is noise, so it
    # stays in the tooltip only (a null there draws nothing).
    return chart(title, description + " " + MATURING,
                 [target(series, frame, [DATE, ("total", total, "number"), *PLATFORM_COLUMNS,
                                         ("n", "Cohort users", "number")]),
                  target(series, "maturing", [DATE, ("maturing", "Maturing", "number")], "B")],
                 unit="percent", decimals=0, time_from=time_from,
                 overrides=[*PLATFORM_OVERRIDES, prop(total, ("displayName", total), ("custom.lineWidth", 3)),
                            hidden("Other"), hidden("Cohort users"),
                            prop("Cohort users", ("unit", "short")), maturing("Maturing", MUTED)])


USERS = ("Users are deduplicated persons with qualified use (v2 definitions): a capture, conversation, "
         "chat or ≥2 successful MCP calls on a UTC day, not just an app open. ")
QUALIFIED_MAU = ("MAU here is qualified MAU (~10K). The \"Omi Cost vs Revenue\" artifact divides by any-event "
                 "PostHog MAU (~22K, $3.41 in October), so its per-user cost is about half of this one. ")
ALL_IN = ("All-in cost counts every line: GCP net of committed-use credits (one-time incidents excluded), "
          "Vertex/Gemini LLM, OpenAI and Anthropic invoices, STT and SaaS. STT uses the dated $5.3K/month "
          f"Soniox-console estimate as of {ESTIMATES_AS_OF} until a measured FinOps line exists (the FinOps "
          f"stt_vendor_low model overstated it ~2×). SaaS uses the dated fixed $4.8K/month estimate as of "
          f"{ESTIMATES_AS_OF} until a complete fresh Mercury row exists, then it is measured SaaS (Mercury). "
          "Measured lines are labeled by source; "
          "an estimate older than 35 days is marked stale under Margin by plan. ")


UPTIME = ("Uptime: of every settled attempt in a core journey over the last 7 days, the share that went the "
          "way it should (attempt-weighted, so busy journeys weigh more). Journeys: live capture (an audio "
          "session not cut by a queue wait or application error), conversation saved (finalization job "
          "success), chat answer (server chat_response) and cloud push-to-talk. Cancelled, degraded and "
          "unknown outcomes are not settled. Same counters as Omi Core Features, read from in-cluster "
          "Prometheus by the board's own sidecar. Change below: percentage points vs the prior 7 days. ")


def columns():
    growth = [
        stat("Growth · active users", USERS + "Weekly, daily and monthly users over the trailing 7 / 1 / 30 complete UTC days (MCP-only included). Change below: relative % vs the prior 7 / 1 / 30 days.",
             [("headline", "wau", "Weekly", "locale", 0), ("headline", "dau", "Daily", "locale", 0),
              ("headline", "mau", "Monthly", "locale", 0)]),
        (7, chart("Weekly users by platform",
                  USERS + "Trailing 7-day periods ending each date (UTC), stacked by each user's primary platform. Starts at the first period after mobile telemetry began (week of 2026-05-04); earlier periods undercount mobile and are not drawn. MCP-only = users whose only qualified use was ≥2 successful MCP calls on a day (blank before that marker existed). The latest bar is the weekly-users stat.",
                  [target("growth", "weekly", [DATE, *PLATFORM_COLUMNS, ("mcp", "MCP-only", "number")])],
                  unit="short", draw="bars", stack=True, overrides=PLATFORM_OVERRIDES,
                  time_from="182d")),
        (6, chart("New, returning, lost",
                  "Each week's active users = returning (also active the prior 7 days) + back after a break + new (first seen this week). Lost = last week's users not active this week, drawn below zero.",
                  [target("growth", "weekly", [DATE, ("retained", "Returning", "number"),
                                               ("resurrected", "Back after a break", "number"),
                                               ("new", "New", "number"), ("churned", "Lost", "number")])],
                  unit="short", draw="bars", stack=True, soft_min=None, time_from="182d",
                  overrides=[color("Returning", MUTED), color("Back after a break", LILAC), color("New", VIOLET),
                             color("Lost", RED)])),
        (5, chart("Quick ratio",
                  "Users gained ÷ users lost each week: (new + back after a break) ÷ lost. Above the dashed 1.0 line the active base is growing.",
                  [target("growth", "weekly", [DATE, ("quickRatio", "Quick ratio", "number")])],
                  unit="none", decimals=1, legend=False, time_from="182d",
                  extra=threshold_line(1, MUTED))),
        (5, chart("Stickiness (DAU/WAU)",
                  "Average daily users ÷ weekly users: qualified user-days in the 7-day period ÷ (7 × weekly users). 100% = every weekly user is active every day.",
                  [target("growth", "weekly", [DATE, ("stickiness", "Stickiness", "number")])],
                  unit="percent", decimals=0, legend=False, time_from="182d")),
    ]
    activation = [
        stat("Activation · week one", "Activated: new users (first seen in the weekly cohort, 180-day lookback so returning users are not counted as new) with ≥2 qualified days in days 1–7. Saved capture: share of the same cohort with a saved own-device or mic capture in week one, the main activation driver. Change below in percentage points vs the prior weekly cohort.",
             [("headline", "activation", "Activated", "percent", 1),
              ("headline", "capture", "Saved capture", "percent", 1)]),
        (8, rate_lines("Activation by platform",
                       "Week-one activation for weekly new-user cohorts, dated by the cohort's last day, split by the platform users first arrived on. Rates use the full cohort, including users who never qualified. The latest All point is the Activated stat. \"Other\" platform cohorts are a handful of users, so their rate is in the tooltip only.",
                       "activation")),
        (7, rate_lines("Week-one capture",
                       "Share of each new-user cohort with a saved, non-discarded own-device or mic conversation in days 1–7, by first platform. The latest All point is the Saved capture stat.",
                       "capture")),
        (8, chart("Activation by capture",
                  "Latest matured new-user cohort (the Activated stat's cohort), split by what users captured with in week one, largest group first: phone mic, an Omi pendant, \"Other Omi\" (another or unknown Omi model), \"2+ devices\", Limitless, Apple Watch, another device, Mac only, phone + Mac, or nothing saved. Bars are each group's week-one activation; the group's user count is in the label. Groups sum to the cohort.",
                  [target("activation", "sources", [("source", "Capture source", "string"),
                                                    ("activation", "Activated", "number")])],
                  unit="percent", decimals=0, legend=False, kind="barchart",
                  overrides=[prop("Activated", ("custom.axisPlacement", "hidden"))],  # bars carry their %
                  extra=barchart_options(horizontal=True, color_hex=NEUTRAL, max_value=115, value_size=16))),
    ]
    retention = [
        stat("Retention", "If activated: activated new users who qualify again in days 8–37 (the cohort needs 37 days to mature, so this is the cohort that started ~5 weeks ago). Established: users active in both of the prior two weeks who are active this week. Change below in percentage points vs the prior cohort / week.",
             [("headline", "retained", "If activated", "percent", 1),
              ("headline", "established", "Established", "percent", 1)]),
        (8, chart("Weekly cohort retention",
                  "W0–W8: share of each weekly new-user cohort (180-day history check, as the activation stat) with a qualified day in week k after first seen. Only fully observed weeks are drawn, so the newest cohort is a single W0 point. Older cohorts are dimmer; the newest is brightest and thickest. Legend oldest → newest.",
                  [target("retention", f"cohort_{age}", [], chr(65 + i)) for i, age in enumerate(range(8, -1, -1))],
                  unit="percent", decimals=0, kind="trend", soft_min=0, extra=curve_options)),
        (7, chart("Retention by week",
                  "Established retention by week (solid) and retained-if-activated (dashed) by the cohort's last first-seen day. Retained-if-activated needs 37 days to mature, so its line always ends 38 days back; the violet band is the cohorts still maturing (a new one closes every day). Established ends at the last complete Mon–Sun week. Latest points are the stats.",
                  [target("retention", "established", [DATE, ("total", "Established", "number")], "A"),
                   target("retention", "retained", [DATE, ("total", "If activated", "number")], "B"),
                   target("retention", "retainedMaturing", [DATE, ("maturing", "If activated: maturing", "number")], "C")],
                  unit="percent", decimals=0, time_from="125d",
                  overrides=[color("Established", TOTAL), dashed("If activated", VIOLET),
                             maturing("If activated: maturing", VIOLET)])),
        (8, chart("Power users · days active",
                  "Share of weekly users by number of active days in the latest 7 days (white), against the same period 4 weeks earlier (grey). A rise on the right means habitual use.",
                  [target("retention", "power", [("days", "Days active", "string"),
                                                 ("4 weeks earlier", "4 weeks earlier", "number"),
                                                 ("This week", "This week", "number")])],
                  unit="percent", decimals=0, kind="barchart",
                  overrides=[color("This week", TOTAL), color("4 weeks earlier", MUTED)],
                  extra=barchart_options())),
    ]
    revenue = [
        stat("Revenue", "MRR: live Stripe Omi-plan book (change = same-source FinOps 7-day change). Per user = MRR ÷ monthly users (qualified MAU; change vs prior week). Hardware: Shopify net device sales, last complete Mon–Sun week vs the prior week. Relative % change.",
             [("headline", "mrr", "MRR", "currencyUSD", 1), ("headline", "arpmau", "Per user", "currencyUSD", 2),
              ("headline", "hardware", "Hardware", "currencyUSD", 0)]),
        (6, chart("MRR by plan",
                   "Neo = legacy Unlimited (plan id unlimited), Unlimited = unlimited_v2, Pro = operator. Daily FinOps snapshots of the Stripe plan book (deduplicated by snapshot date; known gaps: an unmapped enterprise price and two JPY subscriptions). A day with no snapshot is a gap, never a line drawn across it (no book exists from 2026-10-07 to 2026-11-07). The final point is the live Stripe book, the MRR stat. Shopify plan prepay is cash and never included.",
                   [target("revenue", "mrr", [DATE, *[(k, n, "number") for k, n in PLAN_NAMES.items()],
                                              ("other", "Other", "number")])],
                   unit="currencyUSD", stack=True, time_from="40d",
                   overrides=[color(n, h) for n, h in PLANS.items()], extra=mrr_extra)),
        (5, chart("Shopify sales per week",
                   "Mon–Sun weeks. Net device sales (refunds restate their sale week, no tax/shipping) and Omi Unlimited plan prepay cash (reported separately, never MRR). Device units in the tooltip. The latest Hardware bar is the Hardware stat.",
                   [target("revenue", "hardware", [("date", "Week ending", "timestamp"),
                                                   ("hardwareUsd", "Hardware", "number"),
                                                   ("prepayUsd", "Plan prepay (cash)", "number"),
                                                   ("units", "Devices", "number")])],
                   unit="currencyUSD", kind="barchart",
                   overrides=[color("Hardware", REVENUE), color("Plan prepay (cash)", MUTED),
                              hidden("Devices"), prop("Devices", ("unit", "short"))],
                   extra=barchart_options(time_x=True))),
        (4, variable_margin_stat()),
        (8, margin_by_plan()),
    ]
    health = [
        stat("Health", ALL_IN + "All-in/day: the settled day D−2, every line of the all-in stack above (it excludes the margin-only lines OpenRouter and Pinecone); relative % change, up is bad. "
                       + UPTIME,
             [("headline", "netCost", "All-in/day", "currencyUSD", 2),
              ("uptime", "headline", "Uptime", "percent", 1)]),
        (12, chart("Cost vs revenue",
                   ALL_IN + "Settled through D−2. Measured/invoiced lines are solid blue-greys: STT measured is the Soniox prepaid-balance delta plus measured Deepgram usage only; STT cash is Mercury vendor cash; measured SaaS (Mercury) is the daily SaaS aggregate. Modulate modelled (measured volume × committed price), STT est. (Soniox console) and SaaS est. (fixed) are sand-colored because they are not measured. The stack top is the Cost / day stat. One-time GCP spikes (a service-day above 2× and $500 over its 14-day median, e.g. the 2026-09-07 Coldline migration) are excluded and shown in the tooltip. Revenue (violet line) = FinOps MRR ÷ 30.4.",
                   [target("health", "cost", [DATE, ("gcp", "GCP", "number"),
                                              ("vertexLlm", "Vertex LLM", "number"),
                                              ("openai", "OpenAI", "number"), ("anthropic", "Anthropic", "number"),
                                              ("sttMeasuredUsd", "STT measured", "number"),
                                              ("sttCashUsd", "STT cash (Mercury)", "number"),
                                              ("sttModulateModelledUsd", "Modulate modelled", "number"),
                                              ("sttEstimateUsd", "STT est.", "number"),
                                              ("saasMeasuredUsd", "SaaS measured (Mercury)", "number"),
                                              ("saasEstimateUsd", "SaaS est.", "number"),
                                              ("revenuePerDay", "Revenue", "number"),
                                              ("oneTimeExcluded", "One-time excluded", "number"),
                                              ("total", "All-in total", "number")])],
                   # Legend under the plot, not beside it: Health is a 4-column
                   # panel, and a right-hand legend left the 35 days ~100px wide.
                   unit="currencyUSD", draw="bars", stack=True, time_from="35d",
                   overrides=[*[short_label(color(n, h), STACK_LABELS[n]) for n, h in COST.items()],
                              *[short_label(color(n, h), STACK_LABELS[n]) for n, h in MEASURED.items()],
                              *[short_label(estimate(n, h), STACK_LABELS[n]) for n, h in ESTIMATE.items()],
                              line("Revenue", REVENUE, 3),
                              hidden("One-time excluded"), hidden("All-in total")])),
        (10, chart("Uptime by journey",
                   UPTIME + "One point per UTC day (that day's settled attempts); the white line is all journeys "
                   "together. A journey with no settled attempts that day draws nothing, not 0%. Attempts and "
                   "failures for the last 7 days are in the Health stat's source frame `journeys`.",
                   [target("uptime", "daily", [UPTIME_DATE, ("all", "All journeys", "number"),
                                               ("capture", "Live capture", "number"),
                                               ("saved", "Conversation saved", "number"),
                                               ("chat", "Chat answer", "number"),
                                               ("ptt", "Push-to-talk", "number")])],
                   unit="percent", decimals=1, time_from="35d", soft_min=None,
                   overrides=[prop("All journeys", ("displayName", "All journeys"), ("custom.lineWidth", 3)),
                              *[color(n, h) for n, h in JOURNEYS.items()]],
                   extra=disconnect_after(1.5))),
        (1, data_through()),
    ]
    return dict(zip(COLUMNS, [growth, activation, retention, revenue, health]))


MARGIN_EMPTY = "No day in the last 35 has both plan cost and revenue"


def margin_by_plan():
    """Allocated-estimate margin by plan (David 2026-10-17): paid plans as margin %
    lines (left axis); Free, which has no revenue, as negative $/day bars (right
    axis). Both axes centre zero, so Free hangs below the line the plans sit on.
    Per-plan revenue, cost and margin $/day ride in the tooltip."""
    pct = [(f"{k}Pct", n, "number") for k, n in PLAN_NAMES.items()]
    money = [(f"{k}{part}", f"{n} {part.lower()}/day", "number")
             for k, n in PLAN_NAMES.items() for part in ("Revenue", "Cost", "Margin")]
    money += [("basicCost", "Free cost/day", "number"), ("unattributedCost", "Unattributed cost/day", "number"),
              ("shared", "Shared pool/day", "number"), ("allInTotal", "All-in total/day", "number")]
    free = {"matcher": {"id": "byName", "options": FREE}, "properties": [
        {"id": "displayName", "value": FREE}, {"id": "unit", "value": "currencyUSD"},
        {"id": "color", "value": {"mode": "fixed", "fixedColor": MUTED}},
        {"id": "custom.drawStyle", "value": "bars"}, {"id": "custom.fillOpacity", "value": 70},
        {"id": "custom.barWidthFactor", "value": 0.7},
        {"id": "custom.lineWidth", "value": 1}, {"id": "custom.axisPlacement", "value": "right"},
        {"id": "custom.axisCenteredZero", "value": True}]}

    def centre(panel):
        panel["fieldConfig"]["defaults"]["custom"]["axisCenteredZero"] = True
        # An empty frame is a real answer here (no day in the window has both a
        # settled plan cost and a revenue book), not a load still in flight.
        panel["fieldConfig"]["defaults"]["noValue"] = MARGIN_EMPTY
        disconnect_after(1.5)(panel)  # any missing day is a gap (e.g. no 09-29 book)

    return chart("Margin by plan",
                 "Allocated estimate, not gross margin. Revenue = that day's FinOps MRR ÷ 30.4. Cost = FinOps "
                 "fully-loaded plan cost + the shared pool (TV all-in − FinOps: BigQuery, STT, SaaS) split by each "
                 "plan's cost-active user-days. Lines: margin % (left); Free: −$/day bars (right); $/day and the "
                 "unattributed row in the tooltip. FinOps plan cost settles ~3 days back, so this chart ends earlier "
                 "than the wall (its data-through day is the marginStatus frame of /api/omi/stats/wall/series/health); a day without both cost and revenue is a gap. Caveats: STT is not "
                 "invoiced per plan (vendor cost is pooled; GCP audio is allocated by speech seconds), and plan "
                 "membership comes from a point-in-time snapshot.",
                 [target("health", "marginByPlan", [DATE, *pct, ("basicMargin", FREE, "number"), *money])],
                 unit="percent", decimals=0, time_from="35d", soft_min=None,
                 overrides=[*[color(n, PLANS[n]) for n in PLAN_NAMES.values()], free,
                            *[tooltip_only(n) for _, n, _ in money]],
                 extra=centre)


def tooltip_only(name):
    """A $/day tooltip row on a mixed-unit panel. Grafana 13 drops fields hidden
    from the viz out of the tooltip, so this one is drawn invisibly (no line, no
    fill) on its own hidden, fixed scale that never moves the visible axes."""
    return prop(name, ("displayName", name), ("unit", "currencyUSD"), ("decimals", 2),
                ("min", -1e6), ("max", 1e6), ("custom.axisPlacement", "hidden"),
                ("custom.lineWidth", 0), ("custom.fillOpacity", 0), ("custom.pointSize", 1),
                ("custom.hideFrom", {"legend": True, "tooltip": False, "viz": False}))


VARIABLE_MARGIN = ("Variable margin (approved 2026-10-24, definition 2026-10-23): (MRR − real monthly cost) ÷ MRR. "
                   "Real monthly cost = the trailing-7-day run rate (× 30.44) of GCP net of credits with only the "
                   "prepaid Vertex reserved capacity excluded (a one-time GCP incident stays in), plus OpenAI, "
                   "Soniox, Modulate (Mercury cash), OpenRouter and Pinecone (configured, dated estimates) and Stripe "
                   "fees. The development project's GCP is excluded. It excludes "
                   "marketing, hardware, SaaS tooling and non-GCP infra (the all-in stack on Health counts those). "
                   "MRR = the FinOps plan book, USD-only: non-USD paying subscriptions are excluded from the figure "
                   "and counted in the variableMarginStatus frame of /api/omi/stats/wall/series/health. The headline is the live estimate (est.) for "
                   "today: the margin meter's newest hourly row (omi_finops.margin_meter_hourly) while it is under 3 hours old, "
                   "else the metered Cloud Monitoring estimate lagged 5 minutes when there is one, else no value. "
                   "The meter's figure is its own 24-hour basis, so the last point can step away from the "
                   "trailing-7d sparkline; the variableMarginStatus frame names the meter hour, or how long it has been stale. "
                   "Settled through D−2 beneath it; "
                   "the sparkline is the daily trailing-7d series over 60 days. "
                   f"Goal {MARGIN_GOAL_PCT:g}%: green at or above, red below. When the latest day has no MRR book snapshot the "
                   "headline shows no value (no MRR book) unless a fresh margin-meter row supplies it (the meter uses its own revenue basis), never the previous day's margin. The variableMarginStatus frame "
                   "names each line's source; a missing or stale vendor line is disclosed there, never silently dropped.")


def variable_margin_stat():
    """The tile's big number: the latest margin % with the 60-day sparkline
    behind it (Grafana draws the series history in the stat's background).
    The reducer is `last`, NOT `lastNotNull`: a day without an MRR book
    snapshot nulls that day's margin, and the headline must show that absence
    (the explicit no-value marker) rather than an older non-null margin."""
    panel = {"type": "stat", "title": "Variable margin (live est.)", "description": VARIABLE_MARGIN, "datasource": DS,
             "targets": [target("health", "variableMargin", [("marginPct", "Variable margin", "number")])],
             "fieldConfig": {"defaults": {"unit": "percent", "decimals": 1, "noValue": "no live est.",
                                          # Below the goal is red; at/above is green.
                                          "color": {"mode": "thresholds"},
                                          "thresholds": {"mode": "absolute", "steps": [
                                              {"color": STATUS_BAD, "value": None},
                                              {"color": STATUS_GOOD, "value": MARGIN_GOAL_PCT}]}},
                             "overrides": []},
             "options": {"reduceOptions": {"calcs": ["last"], "fields": "", "values": False},
                         "textMode": "value", "colorMode": "value", "graphMode": "area",
                         "justifyMode": "center", "orientation": "vertical", "wideLayout": False,
                         "showPercentChange": False,
                         "text": {"titleSize": STAT_LABEL_SIZE, "valueSize": STAT_VALUE_SIZE}},
             "timeFrom": "62d", "hideTimeOverride": True}
    return panel


def estimate(name, hex_):
    """Estimated cost lines (STT, SaaS): stacked like the rest, sand and lighter."""
    o = color(name, hex_)
    o["properties"] += [{"id": "custom.fillOpacity", "value": ESTIMATE_OPACITY}, {"id": "custom.lineWidth", "value": 1}]
    return o


def disconnect_after(days):
    """Break a daily line across a missing day run longer than `days`."""
    def apply(panel):
        custom = panel["fieldConfig"]["defaults"]["custom"]
        custom.update(insertNulls=int(days * 86_400_000), spanNulls=False)
    return apply


def threshold_line(value, hex_):
    def apply(panel):
        d = panel["fieldConfig"]["defaults"]
        d["thresholds"] = {"mode": "absolute", "steps": [{"color": "transparent", "value": None},
                                                         {"color": hex_, "value": value}]}
        d["custom"]["thresholdsStyle"] = {"mode": "dashed"}
    return apply


def barchart_options(horizontal=False, color_hex=None, time_x=False, max_value=None, value_size=14):
    def apply(panel):
        opts = panel["options"]
        opts.update(orientation="horizontal" if horizontal else "vertical", barWidth=0.8, groupWidth=0.75,
                    text={"valueSize": value_size},
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
    """One frame per cohort (oldest first): ramp by age, newest bright and thick."""
    d = panel["fieldConfig"]["defaults"]
    d["custom"]["showPoints"] = "always"
    d["custom"]["lineInterpolation"] = "linear"
    panel["options"]["xField"] = "week"
    # Trend takes one frame: join the cohort frames on the week, in target order.
    panel["transformations"] = [{"id": "joinByField", "options": {"byField": "week", "mode": "outer"}}]
    panel["options"]["legend"] = {"showLegend": True, "displayMode": "list", "placement": "right"}
    panel["fieldConfig"]["overrides"] = [
        prop("week", ("unit", "none"), ("custom.axisLabel", "weeks since first seen")),
        *[{"matcher": {"id": "byRegexp", "options": rf"^[A-Z][a-z]{{2}} \d+{CURVE_MARK * age}[^{CURVE_MARK}]*$"},
           "properties": [{"id": "displayName", "value": "${__field.name}"},  # no refId suffix
                          {"id": "color", "value": {"mode": "fixed", "fixedColor": CURVE_RAMP[age]}},
                          {"id": "custom.lineWidth", "value": 3 if age == 0 else (2 if age < 4 else 1)}]}
          for age in range(len(CURVE_RAMP))]]
    d["noValue"] = "Cohorts still filling"  # an empty frame, not "Cannot visualize data"


def funnel_row():
    """The funnel board: a full-width row that fills the 1920×1080 kiosk, in its own rotation."""
    proxy = ("Device = paired an Omi within 48 hours of first seen; other paired hardware counts as organic. It is a proxy: a buyer who never paired counts as "
             "organic, and pairing is itself an early success, so the gap between the two is overstated. ")
    series_colors = [color("Device", MAGENTA), color("Organic", NEUTRAL)]
    funnel = chart("Funnel · device vs organic",
                   proxy + "Latest matured weekly new-user cohort, except Kept, which uses the newest cohort old "
                   "enough to measure it. Onboarded counts only people who arrived on iOS, Android or Mac, the "
                   "clients that report it. Install is not shown because PostHog sees nobody before sign-up; first "
                   "summary is not shown because it has no event.",
                   [target("activation", "funnel", [("step", "Step", "string"), ("Device", "Device", "number"),
                                                    ("Organic", "Organic", "number")])],
                   unit="percent", decimals=0, kind="barchart", overrides=series_colors,
                   extra=barchart_options(max_value=100, value_size=13))
    weekly = chart("Activated · device vs organic",
                   proxy + "Week-one activation for each matured weekly cohort, dated by its last day.",
                   [target("activation", "funnelWeekly", [DATE, ("Device", "Device", "number"),
                                                          ("Organic", "Organic", "number")])],
                   unit="percent", decimals=0, soft_min=0, time_from="60d", overrides=series_colors)
    platforms = chart("Funnel by platform",
                      proxy + "Week-one activation in the latest matured weekly new-user cohort, by the platform users "
                      "first arrived on, with its size in the label. Small platforms move a lot week to week.",
                      [target("activation", "funnelPlatforms", [("platform", "Platform", "string"),
                                                                ("Device", "Device", "number"),
                                                                ("Organic", "Organic", "number")])],
                      unit="percent", decimals=0, kind="barchart", overrides=series_colors,
                      extra=barchart_options(horizontal=True, max_value=100, value_size=13))
    return [(11, funnel), (7, weekly), (6, platforms)]


def build_wall_board():
    panels = []
    for name, items in columns().items():
        x, w = GEOMETRY[name]
        head, *charts = items
        keys = [t["root_selector"].split(".")[-1] for t in head["targets"] if t["url"] != UPTIME_URL]
        strip = delta_strip(name, keys, f"{name}: change vs the prior period, from the series API.")
        if len(keys) < len(head["targets"]):  # Uptime's change comes with Uptime, from the sidecar
            strip["targets"].append(target("uptime", "strip", [("uptime", "uptime", "string")], "B"))
            strip["transformations"] = [organize(keys + ["uptime"])]
        panels.append({**head, "gridPos": {"x": x, "y": 0, "w": w, "h": STAT_H}})
        panels.append({**strip, "gridPos": {"x": x, "y": STAT_H, "w": w, "h": STRIP_H}})
        y = STAT_H + STRIP_H
        for h, panel in charts:
            panels.append({**panel, "gridPos": {"x": x, "y": y, "w": w, "h": h}})
            y += h
        assert y == WALL_H, (name, y)  # every column fills the TV exactly, no scroll
    return _board("omi-tv-v2", "Omi TV · v3", panels,
                  "Growth → Activation → Retention → Revenue → Health. Stats above native charts; v2 metric definitions via /api/omi/stats/wall/series. Every chart's latest point is the stat above it. The data-through day is the line under Health.")


def build_funnel_board():
    """Funnel and cohorts in their own rotation: three charts that fill the kiosk, no scroll."""
    panels, x = [], 0
    for w, panel in funnel_row():
        panels.append({**panel, "gridPos": {"x": x, "y": 0, "w": w, "h": WALL_H}})
        x += w
    assert x == 24
    return _board("omi-tv-funnel", "Omi TV · funnel", panels,
                  "Device vs organic funnel, weekly activation and platform split. Its own rotation board: it fills the 1920×1080 kiosk.")


def _board(uid, title, panels, description):
    for i, panel in enumerate(panels, 1):
        panel["id"] = i
    return {"uid": uid, "title": title, "schemaVersion": 39, "version": 1, "timezone": "utc",
            "refresh": "5m", "editable": True, "graphTooltip": 1, "tags": ["omi-tv", "v3"],
            "time": {"from": "now-182d", "to": "now"}, "timepicker": {"hidden": True}, "templating": {"list": []},
            "annotations": {"list": []}, "panels": panels, "links": [], "description": description}


def write_wall_board():
    for uid, board in (("omi-tv-v2", build_wall_board()), ("omi-tv-funnel", build_funnel_board())):
        (HERE / f"dashboards/{uid}.json").write_text(json.dumps(board, indent=2) + "\n")


if __name__ == "__main__":
    write_wall_board()
