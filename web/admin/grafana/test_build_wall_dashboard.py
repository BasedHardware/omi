#!/usr/bin/env python3
"""Behavioral contract for the Business Omi TV board artifact."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(uid: str) -> dict:
    return json.loads((HERE / "dashboards" / f"{uid}.json").read_text(encoding="utf-8"))


def is_strip(panel):
    return panel["type"] == "stat" and panel["targets"][0]["root_selector"].startswith("frames.strip_")


def is_text_line(panel):
    """Untitled one-row stats: the delta strips and the data-through line."""
    return panel["type"] == "stat" and panel.get("transparent") and not panel["title"]


class WallV2Contract(unittest.TestCase):
    def test_checked_in_wall_matches_builder(self):
        from build_wall_dashboard import build_wall_board
        self.assertEqual(load("omi-tv-v2"), build_wall_board())

    def test_wall_columns_plugins_and_utc(self):
        from build_wall_dashboard import BASE, COLUMNS, GEOMETRY
        board = load("omi-tv-v2")
        self.assertEqual(board["uid"], "omi-tv-v2")  # provisioning + embed links
        self.assertEqual(board["timezone"], "utc")
        self.assertEqual(COLUMNS, ["Growth", "Activation", "Retention", "Revenue", "Health"])
        self.assertTrue(all(p["type"] in {"stat", "timeseries", "barchart", "trend", "table"} for p in board["panels"]))
        names = {"headline", "growth", "activation", "retention", "revenue", "health"}
        for panel in board["panels"]:
            self.assertLessEqual(panel["gridPos"]["x"] + panel["gridPos"]["w"], 24)
            for target in panel["targets"]:
                self.assertTrue(target["url"].startswith(BASE + "/"))
                self.assertIn(target["url"].rsplit("/", 1)[1], names)
                self.assertEqual(target["datasource"]["uid"], "omi-admin-api")
                self.assertEqual(target["url_options"]["method"], "GET")
                self.assertTrue(target["root_selector"].startswith("frames."))
        self.assertEqual(sum(w for _, w in GEOMETRY.values()), 24)

    def test_story_columns_stat_above_charts_on_one_screen(self):
        from build_wall_dashboard import COLUMNS, GEOMETRY, WALL_H
        board = load("omi-tv-v2")
        for name in COLUMNS:
            x, w = GEOMETRY[name]
            column = sorted((p for p in board["panels"] if p["gridPos"]["x"] == x), key=lambda p: p["gridPos"]["y"])
            self.assertEqual(column[0]["type"], "stat")
            self.assertTrue(column[0]["title"].startswith(name), column[0]["title"])
            self.assertEqual(column[0]["gridPos"]["y"], 0)
            y = 0
            for panel in column:
                self.assertEqual(panel["gridPos"]["y"], y)
                self.assertEqual(panel["gridPos"]["w"], w)
                y += panel["gridPos"]["h"]
            self.assertEqual(y, WALL_H)  # fills the 1920×1080 kiosk exactly, no scroll
        self.assertTrue(board["timepicker"]["hidden"])

    def test_charts_are_labelled_in_plain_english(self):
        board = load("omi-tv-v2")
        for panel in board["panels"]:
            self.assertTrue(panel["description"])
            if is_text_line(panel):
                continue
            self.assertTrue(panel["title"])
            self.assertLessEqual(len(panel["title"]), 32, panel["title"])  # no truncation at 1440
            for word in ("qualified", "interim", "people", "cohort P"):
                self.assertNotIn(word, panel["title"].lower() if word != "cohort P" else panel["title"])
            if panel["type"] in {"timeseries", "barchart", "trend"}:
                defaults = panel["fieldConfig"]["defaults"]
                self.assertTrue(defaults.get("unit"), panel["title"])
                self.assertIn("axisLabel", defaults["custom"], panel["title"])
        stats = {p["title"]: p for p in board["panels"] if p["type"] == "stat" and not is_text_line(p)}
        # Five column stats + the Variable margin tile (David, 2026-10-24).
        self.assertEqual(len(stats), 6)
        names = [o["properties"][0]["value"] for p in stats.values() for o in p["fieldConfig"]["overrides"]]
        self.assertIn("Stickiness (DAU/WAU)", {p["title"] for p in board["panels"]})
        self.assertTrue(all("people" not in n.lower() for n in names), names)
        headline = [t["root_selector"] for p in stats.values() for t in p["targets"]]
        for key in ["wau", "dau", "mau", "activation", "capture", "retained", "established",
                    "mrr", "arpmau", "hardware", "netCost", "costPerMau"]:
            self.assertIn(f"frames.{key}", headline)

    def test_each_stat_has_an_api_delta_strip_in_field_order(self):
        import re
        from build_wall_dashboard import BAD_MARK, COLUMNS, GEOMETRY, GOOD_MARK, STAT_H
        board = load("omi-tv-v2")
        source = (HERE.parent / "lib/wall-series.ts").read_text()
        block = re.search(r"DELTA_STRIPS[^=]*= \{(.*?)\};", source, re.S).group(1)
        api = {k: re.findall(r'"(\w+)"', v) for k, v in re.findall(r"(\w+): \[([^\]]*)\]", block)}
        self.assertIn('GOOD_MARK = "\\u200b"', source)
        self.assertIn('BAD_MARK = "\\u2060"', source)
        for name in COLUMNS:
            x, _ = GEOMETRY[name]
            column = sorted((p for p in board["panels"] if p["gridPos"]["x"] == x), key=lambda p: p["gridPos"]["y"])
            head, strip = column[0], column[1]
            self.assertTrue(is_strip(strip))
            self.assertFalse(head["options"]["showPercentChange"])  # native change is relative only
            self.assertEqual(strip["gridPos"]["y"], STAT_H)
            keys = [t["root_selector"].split(".")[-1] for t in head["targets"]]
            self.assertEqual(keys, api[name.lower()])
            self.assertEqual([c["selector"] for c in strip["targets"][0]["columns"]], keys)
            colors = {m["options"]["pattern"]: m["options"]["result"]["color"]
                      for m in strip["fieldConfig"]["defaults"]["mappings"]}
            self.assertEqual(set(colors), {f".*{GOOD_MARK}.*", f".*{BAD_MARK}.*"})

    def test_cost_stack_counts_every_line_and_marks_estimates(self):
        from build_wall_dashboard import ESTIMATE, ESTIMATE_OPACITY, MEASURED
        board = load("omi-tv-v2")
        cost = next(p for p in board["panels"] if p["title"] == "Cost vs revenue")
        fields = [c["selector"] for c in cost["targets"][0]["columns"]]
        for line in ["gcp", "vertexLlm", "openai", "anthropic", "sttMeasuredUsd", "sttCashUsd",
                     "sttModulateModelledUsd", "sttEstimateUsd",
                     "saasMeasuredUsd", "saasEstimateUsd", "revenuePerDay"]:
            self.assertIn(line, fields)
        styled = {o["matcher"]["options"]: {p["id"]: p["value"] for p in o["properties"]}
                  for o in cost["fieldConfig"]["overrides"]}
        for name in ESTIMATE:
            self.assertEqual(styled[name]["custom.fillOpacity"], ESTIMATE_OPACITY)
            self.assertNotIn("custom.stacking", styled[name])  # still in the stack
        # The measured stack carries ONLY measured dollars per provider; modelled
        # Modulate and the dated constants stay sand-colored estimate series.
        self.assertEqual(set(ESTIMATE), {"STT est.", "SaaS est.", "Modulate modelled"})
        self.assertEqual(set(MEASURED), {"STT measured", "STT cash (Mercury)", "SaaS measured (Mercury)"})
        for name in MEASURED:
            self.assertIn(name, styled)
            self.assertNotIn("custom.fillOpacity", styled[name])
        self.assertTrue(cost["options"]["legend"]["showLegend"])  # identity is never color alone
        self.assertIn("Soniox console", cost["description"])
        self.assertIn("measured SaaS (Mercury)", cost["description"])
        self.assertIn("Modulate modelled", cost["description"])
        self.assertNotIn("FinOps modelled", cost["description"])

    def test_status_colors_curve_placeholder_and_data_through(self):
        from build_wall_dashboard import STATUS_BAD, STATUS_GOOD
        board = load("omi-tv-v2")
        strips = [p for p in board["panels"] if is_strip(p)]
        colors = {m["options"]["result"]["color"] for p in strips for m in p["fieldConfig"]["defaults"]["mappings"]}
        self.assertEqual(colors, {STATUS_GOOD, STATUS_BAD})  # dataviz status steps
        curve = next(p for p in board["panels"] if p["title"].startswith("Weekly cohort retention"))
        self.assertEqual(curve["fieldConfig"]["defaults"]["noValue"], "Cohorts still filling")
        # No diagnostics table on the TV (David 2026-10-16): one data-through line.
        self.assertFalse([p for p in board["panels"] if p["type"] == "table"])
        through = [p for p in board["panels"] if p["targets"][0]["root_selector"] == "frames.through"]
        self.assertEqual(len(through), 1)
        self.assertEqual(through[0]["gridPos"]["h"], 1)
        health = next(p for p in board["panels"] if p["title"] == "Health")
        names = [o["properties"][0]["value"] for o in health["fieldConfig"]["overrides"]]
        self.assertTrue(all(len(n) <= 12 for n in names), names)  # no wrap at 1440

    def test_field_order_is_pinned_not_alphabetical(self):
        board = load("omi-tv-v2")
        for panel in board["panels"]:
            names = list(dict.fromkeys(c["text"] for t in panel["targets"] for c in t["columns"]))
            if panel["type"] == "trend" or len(names) <= 2 or (panel["type"] == "stat" and not is_strip(panel)):
                continue
            order = next(t["options"]["indexByName"] for t in panel.get("transformations", [])
                         if t["id"] == "organize")
            self.assertEqual(sorted(order, key=order.get), names, panel["title"] or panel["targets"][0]["root_selector"])

    def test_cohort_curve_lists_by_date_on_one_ramp(self):
        import re
        from build_wall_dashboard import CURVE_MARK, CURVE_RAMP
        board = load("omi-tv-v2")
        source = (HERE.parent / "lib/wall-series.ts").read_text()
        self.assertIn('CURVE_MARK = "\\u200b"', source)
        self.assertEqual(CURVE_MARK, "\u200b")
        curve = next(p for p in board["panels"] if p["title"] == "Weekly cohort retention")
        self.assertEqual([t["root_selector"] for t in curve["targets"]],
                         [f"frames.cohort_{age}" for age in range(8, -1, -1)])  # oldest first
        self.assertEqual(curve["transformations"][0]["id"], "joinByField")
        ramp = [o for o in curve["fieldConfig"]["overrides"] if o["matcher"]["id"] == "byRegexp"]
        for age, override in enumerate(ramp):
            pattern = override["matcher"]["options"]
            props = {p["id"]: p["value"] for p in override["properties"]}
            self.assertEqual(props["color"]["fixedColor"], CURVE_RAMP[age])
            for other in range(9):
                name = "Sep 26" + CURVE_MARK * other + " B"
                self.assertEqual(bool(re.search(pattern, name)), other == age, (age, other))
        self.assertEqual([o["properties"][2]["value"] for o in ramp][0], 3)  # newest is thickest

    def test_cohort_lines_end_at_an_explained_maturing_band(self):
        board = load("omi-tv-v2")
        bands = {"Activation by platform": ("activation", "frames.maturing", "Maturing"),
                 "Week-one capture": ("activation", "frames.maturing", "Maturing"),
                 "Retention by week": ("retention", "frames.retainedMaturing", "If activated: maturing")}
        for title, (series, frame, name) in bands.items():
            panel = next(p for p in board["panels"] if p["title"] == title)
            band = next(t for t in panel["targets"] if t["root_selector"] == frame)
            self.assertTrue(band["url"].endswith("/" + series))
            props = next({p["id"]: p["value"] for p in o["properties"]}
                         for o in panel["fieldConfig"]["overrides"] if o["matcher"]["options"] == name)
            # Its own 0–1 scale (not the percent axis), hidden, filled, legend only.
            self.assertEqual((props["unit"], props["min"], props["max"]), ("none", 0, 1))
            self.assertEqual(props["custom.axisPlacement"], "hidden")
            self.assertEqual(props["custom.lineWidth"], 0)
            self.assertEqual(props["custom.hideFrom"], {"legend": False, "tooltip": True, "viz": False})
            self.assertIn("band", panel["description"])
            self.assertNotIn("Oct 24", panel["description"])  # cohorts roll daily: no release date

    def test_unit_economics_is_daily_and_breaks_on_missing_days(self):
        board = load("omi-tv-v2")
        panel = next(p for p in board["panels"] if p["title"] == "Unit economics")
        custom = panel["fieldConfig"]["defaults"]["custom"]
        self.assertLess(custom["insertNulls"], 2 * 86_400_000)  # a one-day hole is a gap
        self.assertFalse(custom["spanNulls"])  # a gap is drawn as a gap
        self.assertEqual(panel["timeFrom"], "35d")  # the FinOps book's daily history
        self.assertIn("one point per day", panel["description"])

    def test_margin_by_plan_keeps_its_frame_and_status_line(self):
        from build_wall_dashboard import FREE, PLAN_NAMES
        board = load("omi-tv-v2")
        panel = next(p for p in board["panels"] if p["title"] == "Margin by plan")
        # Still the Revenue column's tall closing chart, directly above its
        # status line (the Variable margin tile now fills the space beside
        # Unit economics instead — same frame family, 2026-10-24).
        self.assertEqual(panel["gridPos"]["x"], 15)
        self.assertGreaterEqual(panel["gridPos"]["h"], 6)
        target = panel["targets"][0]
        self.assertTrue(target["url"].endswith("/health"))
        self.assertEqual(target["root_selector"], "frames.marginByPlan")
        fields = [c["selector"] for c in target["columns"]]
        for key in PLAN_NAMES:  # paid plans as margin %, $/day in the tooltip
            for suffix in ("Pct", "Revenue", "Cost", "Margin"):
                self.assertIn(key + suffix, fields)
        self.assertIn("basicMargin", fields)
        self.assertIn("unattributedCost", fields)  # its own row, never folded in
        self.assertEqual(set(PLAN_NAMES), {"unlimited", "unlimited_v2", "operator", "plus", "architect"})
        styled = {o["matcher"]["options"]: {p["id"]: p["value"] for p in o["properties"]}
                  for o in panel["fieldConfig"]["overrides"]}
        # Free: negative $/day bars on their own centred axis.
        free = styled[FREE]
        self.assertEqual((free["unit"], free["custom.drawStyle"], free["custom.axisPlacement"]),
                         ("currencyUSD", "bars", "right"))
        self.assertTrue(free["custom.axisCenteredZero"])
        custom = panel["fieldConfig"]["defaults"]["custom"]
        self.assertEqual(panel["fieldConfig"]["defaults"]["unit"], "percent")
        self.assertTrue(custom["axisCenteredZero"])
        self.assertFalse(custom["spanNulls"])
        self.assertLess(custom["insertNulls"], 2 * 86_400_000)  # a one-day hole is a gap
        # Tooltip rows: drawn invisibly on their own hidden scale (Grafana 13 drops
        # viz-hidden fields from the tooltip).
        money = styled["Neo revenue/day"]
        self.assertEqual(money["custom.hideFrom"], {"legend": True, "tooltip": False, "viz": False})
        self.assertEqual((money["custom.lineWidth"], money["custom.fillOpacity"], money["custom.axisPlacement"]),
                         (0, 0, "hidden"))
        self.assertNotIn("min", free)  # Free keeps its own centred, data-fitted axis
        for phrase in ("Allocated estimate", "cost-active user-days", "speech seconds", "point-in-time snapshot",
                       "~3 days back"):
            self.assertIn(phrase, panel["description"])
        status = next(p for p in board["panels"] if p["targets"][0]["root_selector"] == "frames.marginStatus")
        self.assertEqual(status["gridPos"], {**panel["gridPos"], "y": panel["gridPos"]["y"] + panel["gridPos"]["h"],
                                             "h": 1})

    def test_variable_margin_tile_big_number_sparkline_and_target(self):
        from build_wall_dashboard import STATUS_GOOD
        board = load("omi-tv-v2")
        tile = next(p for p in board["panels"] if p["title"] == "Variable margin")
        # The big number is the latest margin %, with the 60-day daily series
        # as the stat's own sparkline; 50% is the threshold (green at/above).
        self.assertEqual(tile["type"], "stat")
        self.assertEqual(tile["targets"][0]["url"].rsplit("/", 1)[1], "health")
        self.assertEqual(tile["targets"][0]["root_selector"], "frames.variableMargin")
        self.assertEqual(tile["options"]["graphMode"], "area")
        # The reducer is `last`, never `lastNotNull`: a day without an MRR book
        # snapshot nulls that day's margin, and the headline must show the
        # explicit no-value marker, not an older non-null margin (Luna r3 P2).
        self.assertEqual(tile["options"]["reduceOptions"]["calcs"], ["last"])
        self.assertNotIn("lastNotNull", tile["options"]["reduceOptions"]["calcs"])
        self.assertEqual(tile["fieldConfig"]["defaults"]["noValue"], "no MRR book")
        self.assertEqual(tile["fieldConfig"]["defaults"]["unit"], "percent")
        steps = tile["fieldConfig"]["defaults"]["thresholds"]["steps"]
        self.assertEqual([s["value"] for s in steps], [None, 50])
        self.assertEqual(steps[1]["color"], STATUS_GOOD)
        # The definition is on the wall, not in a separate doc.
        for phrase in ("MRR − real monthly cost", "Vertex reserved", "OpenAI, Soniox, Modulate and Stripe fees",
                       "Goal 50%", "60 days", "non-USD paying subscriptions", "no MRR book"):
            self.assertIn(phrase, tile["description"])
        # The secondary chart: cost run rate vs MRR with the 50% target marked.
        chart_panel = next(p for p in board["panels"] if p["title"] == "Cost run rate vs MRR")
        fields = [c["selector"] for c in chart_panel["targets"][0]["columns"]]
        for field in ("costPerMonth", "mrr", "goalCost", "vertexReservedPerMonth"):
            self.assertIn(field, fields)
        styled = {o["matcher"]["options"]: {p["id"]: p["value"] for p in o["properties"]}
                  for o in chart_panel["fieldConfig"]["overrides"]}
        target_line = styled["50% target cost"]
        self.assertEqual(target_line["color"]["fixedColor"], STATUS_GOOD)
        self.assertEqual(target_line["custom.lineStyle"]["dash"], [6, 4])  # a goal, not a series
        # Missing/stale vendor lines are named on the tile's own status line,
        # which also carries the MRR source and its non-USD exclusion count.
        status = next(p for p in board["panels"]
                      if p["targets"][0]["root_selector"] == "frames.variableMarginStatus")
        self.assertEqual(status["gridPos"]["h"], 1)
        self.assertIn("named", status["description"])
        self.assertIn("non-USD", status["description"])
        self.assertIn("7-day window", status["description"])

    def test_cost_estimates_are_dated_like_the_api(self):
        import re
        from build_wall_dashboard import ESTIMATES_AS_OF
        source = (HERE.parent / "lib/wall-cost.ts").read_text()
        self.assertEqual(re.search(r'STT_AS_OF = "([\d-]+)"', source).group(1), ESTIMATES_AS_OF)
        self.assertEqual(re.search(r'SAAS_AS_OF = "([\d-]+)"', source).group(1), ESTIMATES_AS_OF)
        board = load("omi-tv-v2")
        for title in ("Health", "Cost vs revenue"):
            panel = next(p for p in board["panels"] if p["title"] == title)
            self.assertIn(f"estimate as of {ESTIMATES_AS_OF}", panel["description"])

    def test_platform_hues_mean_platforms(self):
        from build_wall_dashboard import PLATFORM
        board = load("omi-tv-v2")
        hues = {h.lower(): n for n, h in PLATFORM.items()}
        for panel in board["panels"]:
            defaults = panel["fieldConfig"]["defaults"]
            self.assertNotIn(defaults.get("color", {}).get("fixedColor", "").lower(), hues, panel["title"])
            for o in panel["fieldConfig"]["overrides"]:
                for p in o["properties"]:
                    if p["id"] == "color" and p["value"].get("fixedColor", "").lower() in hues:
                        self.assertEqual(o["matcher"]["options"], hues[p["value"]["fixedColor"].lower()],
                                         panel["title"])


if __name__ == "__main__":
    unittest.main()
