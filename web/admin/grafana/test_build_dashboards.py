#!/usr/bin/env python3
"""Behavioral coverage for build_dashboards.py — the platform boards and the
NYC-time/latest-day display contract.

The regression this guards: daily buckets arrive as bare date strings
("2026-08-18"); parsed as UTC midnight they render at 8 pm the previous day
in America/New_York, so the latest day silently disappears from every daily
chart. The builder must (a) pin every board to America/New_York and (b) route
every daily/weekly/monthly timestamp column through the proxy's `_tzdates`
rewrite with an RFC3339 parse format.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_dashboards  # noqa: E402

BOARDS = ["omi-tv", "omi-tv-macos", "omi-tv-mobile"]
RFC3339 = "2006-01-02T15:04:05Z07:00"
BARE_DAY_FORMATS = {"2006-01-02", "2006-01"}


def load(uid: str) -> dict:
    return json.loads((HERE / "dashboards" / f"{uid}.json").read_text(encoding="utf-8"))


def timestamp_columns(dash):
    for panel in dash.get("panels", []):
        for target in panel.get("targets", []):
            for col in target.get("columns", []):
                if col.get("type") == "timestamp":
                    yield panel, target, col


class NycTimeContractTests(unittest.TestCase):
    def test_every_board_is_pinned_to_new_york(self) -> None:
        for uid in BOARDS:
            self.assertEqual(load(uid)["timezone"], "America/New_York", uid)

    def test_no_bare_date_columns_survive(self) -> None:
        """Bare date formats parse as UTC midnight and shift the latest day
        off the chart in NYC time — every day-grain column must go through
        _tzdates and parse as RFC3339."""
        for uid in BOARDS:
            for panel, target, col in timestamp_columns(load(uid)):
                fmt = col.get("timestampFormat")
                self.assertNotIn(fmt, BARE_DAY_FORMATS,
                                 f"{uid} / {panel['title']}: bare day format {fmt}")
                if fmt == RFC3339:
                    query = urllib.parse.urlparse(target["url"]).query
                    tz_fields = urllib.parse.parse_qs(query).get("_tzdates", [""])[0]
                    self.assertIn(col["selector"], tz_fields.split(","),
                                  f"{uid} / {panel['title']}: {col['selector']} "
                                  "not routed through _tzdates")

    def test_hourly_columns_stay_utc_parsed(self) -> None:
        """Hourly buckets are genuine UTC instants; they must NOT be rewritten
        (the dashboard timezone converts them to NYC wall-clock at render)."""
        hourly = [
            (panel, target, col)
            for panel, target, col in timestamp_columns(load("omi-tv"))
            if col.get("timestampFormat") == "2006-01-02T15"
        ]
        self.assertTrue(hourly, "expected an hourly panel on the base board")
        for _panel, target, _col in hourly:
            self.assertNotIn("_tzdates", target["url"])


class PlatformBoardTests(unittest.TestCase):
    def test_switcher_links_on_every_board(self) -> None:
        for uid in BOARDS:
            urls = [link["url"] for link in load(uid)["links"]]
            self.assertEqual(
                urls,
                ["/grafana/d/omi-tv/", "/grafana/d/omi-tv-macos/", "/grafana/d/omi-tv-mobile/"],
                uid,
            )

    def test_macos_board_has_no_mobile_series(self) -> None:
        dash = load("omi-tv-macos")
        for panel in dash["panels"]:
            for target in panel.get("targets", []):
                for col in target.get("columns", []):
                    self.assertNotIn("mobile", col.get("selector", "").lower(),
                                     f"macOS board leaks mobile series in {panel['title']}")
        titles = " ".join(p["title"] for p in dash["panels"])
        self.assertIn("macOS users", titles)
        self.assertNotIn("by platform", titles)

    def test_mobile_board_is_honest(self) -> None:
        """Mobile engagement isn't instrumented — the board must only carry
        profitability-derived series plus the instrumentation note."""
        dash = load("omi-tv-mobile")
        titles = [p["title"] for p in dash["panels"]]
        joined = " ".join(titles)
        for absent in ["Retention", "Floating bar", "WAU", "notification", "Crash"]:
            self.assertNotIn(absent, joined, f"mobile board should not claim {absent}")
        note = next(p for p in dash["panels"] if p["type"] == "text")
        self.assertIn("not instrumented", note["options"]["content"])
        for panel in dash["panels"]:
            for target in panel.get("targets", []):
                for col in target.get("columns", []):
                    self.assertNotIn("desktop", col.get("selector", "").lower(),
                                     f"mobile board leaks desktop series in {panel['title']}")

    def test_platform_delta_variables_follow_their_board(self) -> None:
        for uid, field in [("omi-tv-macos", "desktop"), ("omi-tv-mobile", "mobile")]:
            for var in load(uid)["templating"]["list"]:
                url = var["query"]["infinityQuery"]["url"]
                params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                if "profitability" in params.get("path", [""])[0]:
                    self.assertEqual(params["fields"], [field], f"{uid}: {var['name']}")


class ApplyScopeTests(unittest.TestCase):
    def test_apply_publishes_exactly_the_three_boards(self) -> None:
        import apply_omi_tv_dashboard as apply_mod

        found = {
            json.loads(path.read_text(encoding="utf-8"))["uid"]
            for path in (HERE / "dashboards").glob("*.json")
        }
        self.assertEqual(found, set(BOARDS))
        self.assertEqual(apply_mod.ALLOWED_UIDS, set(BOARDS))

    def test_apply_rejects_foreign_uids(self) -> None:
        import tempfile

        import apply_omi_tv_dashboard as apply_mod

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"uid": "rogue-board", "panels": []}, handle)
        with self.assertRaises(SystemExit):
            apply_mod.load_dashboard(Path(handle.name))


class BuilderIdempotencyTests(unittest.TestCase):
    def test_rebuild_is_idempotent(self) -> None:
        """Running the builder against its own output changes nothing —
        guards against _tzdates double-append and title suffix drift."""
        base = load("omi-tv")
        rebuilt = copy.deepcopy(base)
        build_dashboards.apply_tzdates(rebuilt)
        build_dashboards.finish(rebuilt, "omi-tv", "Omi TV")
        self.assertEqual(base, rebuilt)
        self.assertEqual(build_dashboards.build_macos(rebuilt), load("omi-tv-macos"))
        self.assertEqual(build_dashboards.build_mobile(rebuilt), load("omi-tv-mobile"))


if __name__ == "__main__":
    unittest.main()
