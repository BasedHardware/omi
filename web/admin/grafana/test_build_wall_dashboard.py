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
    def test_funnel_row_is_its_own_board_that_fills_the_screen(self):
        from build_wall_dashboard import WALL_H
        board = load("omi-tv-funnel")
        self.assertEqual(board["uid"], "omi-tv-funnel")
        row = board["panels"]
        self.assertEqual({p["gridPos"]["y"] for p in row}, {0})
        self.assertEqual({p["gridPos"]["h"] for p in row}, {WALL_H})  # fills 1920×1080, no scroll
        self.assertEqual(sum(p["gridPos"]["w"] for p in row), 24)
        self.assertEqual({p["targets"][0]["root_selector"] for p in row},
                         {"frames.funnel", "frames.funnelWeekly", "frames.funnelPlatforms"})

    def test_wall_board_has_no_funnel_row(self):
        board = load("omi-tv-v2")
        self.assertFalse(any(p["targets"][0]["root_selector"].startswith("frames.funnel")
                             for p in board["panels"] if p.get("targets")))

    def test_checked_in_boards_match_builder(self):
        from build_wall_dashboard import build_funnel_board, build_wall_board
        self.assertEqual(load("omi-tv-v2"), build_wall_board())
        self.assertEqual(load("omi-tv-funnel"), build_funnel_board())

    def test_wall_columns_plugins_and_utc(self):
        from build_wall_dashboard import BASE, COLUMNS, GEOMETRY, UPTIME_URL
        board = load("omi-tv-v2")
        self.assertEqual(board["uid"], "omi-tv-v2")  # provisioning + embed links
        self.assertEqual(board["timezone"], "utc")
        self.assertEqual(COLUMNS, ["Growth", "Activation", "Retention", "Revenue", "Health"])
        self.assertTrue(all(p["type"] in {"stat", "timeseries", "barchart", "trend", "table"} for p in board["panels"]))
        names = {"headline", "growth", "activation", "retention", "revenue", "health"}
        for panel in board["panels"]:
            self.assertLessEqual(panel["gridPos"]["x"] + panel["gridPos"]["w"], 24)
            for target in panel["targets"]:
                if target["url"] == UPTIME_URL:  # the sidecar's fixed-PromQL route
                    self.assertEqual(target["root_selector"].split(".")[0], "frames")
                    continue
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
            column = sorted((p for p in board["panels"] if p["gridPos"]["x"] == x and p["gridPos"]["y"] < WALL_H),
                            key=lambda p: p["gridPos"]["y"])
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
                    "mrr", "arpmau", "hardware", "netCost"]:
            self.assertIn(f"frames.{key}", headline)

    def test_each_stat_has_an_api_delta_strip_in_field_order(self):
        import re
        from build_wall_dashboard import BAD_MARK, COLUMNS, GEOMETRY, GOOD_MARK, STAT_H, WALL_H
        board = load("omi-tv-v2")
        source = (HERE.parent / "lib/wall-series.ts").read_text()
        block = re.search(r"DELTA_STRIPS[^=]*= \{(.*?)\};", source, re.S).group(1)
        api = {k: re.findall(r'"(\w+)"', v) for k, v in re.findall(r"(\w+): \[([^\]]*)\]", block)}
        self.assertIn('GOOD_MARK = "\\u200b"', source)
        self.assertIn('BAD_MARK = "\\u2060"', source)
        for name in COLUMNS:
            x, _ = GEOMETRY[name]
            column = sorted((p for p in board["panels"] if p["gridPos"]["x"] == x and p["gridPos"]["y"] < WALL_H),
                            key=lambda p: p["gridPos"]["y"])
            head, strip = column[0], column[1]
            self.assertTrue(is_strip(strip))
            self.assertFalse(head["options"]["showPercentChange"])  # native change is relative only
            self.assertEqual(strip["gridPos"]["y"], STAT_H)
            keys = [t["root_selector"].split(".")[-1] for t in head["targets"] if "/wall/series/" in t["url"]]
            self.assertEqual(keys, api[name.lower()][:len(keys)])
            self.assertEqual([c["selector"] for c in strip["targets"][0]["columns"]], keys)
            if len(keys) < len(head["targets"]):  # Uptime brings its own change
                self.assertEqual(strip["targets"][1]["root_selector"], "frames.strip")
                self.assertEqual(strip["targets"][1]["columns"][0]["selector"], "uptime")
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
        # Under the plot, never beside it: Health is a narrow column, and a right
        # legend squeezed the 35-day stack and revenue line into a sliver.
        self.assertEqual(cost["options"]["legend"]["placement"], "bottom")
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

    def test_uptime_by_journey_replaces_unit_economics(self):
        from build_wall_dashboard import PLATFORM, UPTIME_URL
        board = load("omi-tv-v2")
        titles = {p["title"] for p in board["panels"]}
        self.assertNotIn("Unit economics", titles)  # redundant with Cost vs revenue (David 2026-11-06)
        panel = next(p for p in board["panels"] if p["title"] == "Uptime by journey")
        self.assertEqual(panel["gridPos"]["x"], 20)
        target = panel["targets"][0]
        self.assertEqual((target["url"], target["root_selector"]), (UPTIME_URL, "frames.daily"))
        fields = [c["selector"] for c in target["columns"]]
        self.assertEqual(fields, ["date", "all", "capture", "saved", "chat", "ptt"])
        # the sidecar emits the UTC day as epoch milliseconds; a plain "timestamp" column parses
        # that to null and the panel reads "Data outside time range"
        date_col = next(c for c in target["columns"] if c["selector"] == "date")
        self.assertEqual(date_col["type"], "timestamp_epoch")
        custom = panel["fieldConfig"]["defaults"]["custom"]
        self.assertFalse(custom["spanNulls"])  # a day without attempts is a gap, not 0%
        hues = {p["value"]["fixedColor"] for o in panel["fieldConfig"]["overrides"] for p in o["properties"]
                if p["id"] == "color"}
        self.assertFalse(hues & set(PLATFORM.values()))  # platform hues stay platforms
        health = next(p for p in board["panels"] if p["title"] == "Health")
        uptime = next(t for t in health["targets"] if t["url"] == UPTIME_URL)
        self.assertEqual(uptime["root_selector"], "frames.headline")

    def test_margin_by_plan_keeps_its_frame_and_closes_the_column(self):
        from build_wall_dashboard import FREE, PLAN_NAMES
        board = load("omi-tv-v2")
        panel = next(p for p in board["panels"] if p["title"] == "Margin by plan")
        # The Revenue column's tall closing chart.
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
        # An empty frame names its cause; "Loading…" would read as a stuck query.
        self.assertEqual(panel["fieldConfig"]["defaults"]["noValue"],
                         "No day in the last 35 has both plan cost and revenue")
        self.assertEqual(panel["timeFrom"], "35d")  # MARGIN_DAYS in lib/wall-series.ts
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
        # It closes the Revenue column; its data-through text stays in the API
        # (frames.marginStatus), not as a tiny line on the wall (David 2026-11-06).
        from build_wall_dashboard import WALL_H
        self.assertEqual(panel["gridPos"]["y"] + panel["gridPos"]["h"], WALL_H)
        roots = {t.get("root_selector") for p in board["panels"] for t in p.get("targets", [])}
        self.assertNotIn("frames.marginStatus", roots)

    def test_all_in_tiles_name_their_scope(self):
        board = load("omi-tv-v2")
        # Relabelled so the names say what they include (David 2026-11-02): the
        # stat names stay short (no wrap at 1440), the description carries scope.
        health = next(p for p in board["panels"] if p["title"] == "Health")
        blob = json.dumps(health, ensure_ascii=False)
        self.assertIn("All-in/day", blob)
        self.assertIn("Uptime", blob)
        self.assertIn("attempt-weighted", blob)
        self.assertNotIn('"Cost / day"', blob)
        self.assertNotIn('"Cost / user"', blob)

    def test_variable_margin_tile_big_number_sparkline_and_target(self):
        from build_wall_dashboard import STATUS_GOOD
        board = load("omi-tv-v2")
        tile = next(p for p in board["panels"] if p["title"] == "Variable margin (live est.)")
        # The big number is the latest margin % (today's live estimate), with
        # the 60-day daily series as the stat's own sparkline; the goal is the
        # threshold (green at/above).
        self.assertEqual(tile["type"], "stat")
        self.assertEqual(tile["targets"][0]["url"].rsplit("/", 1)[1], "health")
        self.assertEqual(tile["targets"][0]["root_selector"], "frames.variableMargin")
        self.assertEqual(tile["options"]["graphMode"], "area")
        # The reducer is `last`, never `lastNotNull`: a day without an MRR book
        # snapshot nulls that day's margin, and the headline must show the
        # explicit no-value marker, not an older non-null margin (Luna r3 P2).
        self.assertEqual(tile["options"]["reduceOptions"]["calcs"], ["last"])
        self.assertNotIn("lastNotNull", tile["options"]["reduceOptions"]["calcs"])
        # No live estimate (or no MRR book) shows no value, never a settled number as live.
        self.assertEqual(tile["fieldConfig"]["defaults"]["noValue"], "no live est.")
        self.assertEqual(tile["fieldConfig"]["defaults"]["unit"], "percent")
        steps = tile["fieldConfig"]["defaults"]["thresholds"]["steps"]
        self.assertEqual([s["value"] for s in steps], [None, 50])
        self.assertEqual(steps[1]["color"], STATUS_GOOD)
        # The definition is on the wall, not in a separate doc.
        for phrase in ("MRR − real monthly cost", "Vertex reserved", "OpenAI, Soniox, Modulate (Mercury cash), OpenRouter and Pinecone",
                       "Goal 50%", "60 days", "non-USD paying subscriptions", "no MRR book"):
            self.assertIn(phrase, tile["description"])
        # Cost vs revenue on Health covers the run-rate view; the duplicate
        # chart and the tiny status lines are gone (David 2026-11-06).
        titles = {p["title"] for p in board["panels"]}
        self.assertNotIn("Cost run rate vs MRR", titles)
        roots = {t.get("root_selector") for p in board["panels"] for t in p.get("targets", [])}
        self.assertNotIn("frames.variableMarginStatus", roots)
        shopify = next(p for p in board["panels"] if p["title"] == "Shopify sales per week")
        self.assertGreaterEqual(shopify["gridPos"]["h"], 5)  # tall enough to read the bars

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
