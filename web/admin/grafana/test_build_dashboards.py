#!/usr/bin/env python3
"""Behavioral coverage for build_dashboards.py — the platform boards and the
NYC-time/latest-day display contract.

Regressions guarded here:
  - Daily buckets arrive as bare date strings; parsed as UTC midnight they
    render 8 pm the previous NYC day and the latest day disappears. Every
    day-grain column must go through `_tzdates` + RFC3339.
  - The platform boards must actually be platform-scoped: every PostHog-backed
    query (including ones nested in /compare URLs) pins platform=macos /
    platform=mobile / platform=all per board. Unscoped viral-metrics silently
    reports macOS numbers as all-platform (the "same DAU on every board" bug).
  - The mobile board mirrors the macOS board panel-for-panel except the
    desktop-only product surfaces.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unittest
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_dashboards  # noqa: E402

BOARDS = ["omi-tv", "omi-tv-macos", "omi-tv-mobile"]
BOARD_SCOPE = {"omi-tv": "all", "omi-tv-macos": "macos", "omi-tv-mobile": "mobile"}
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


def all_urls(dash):
    for panel in dash.get("panels", []):
        for target in panel.get("targets", []):
            if "url" in target:
                yield panel.get("title", "?"), target["url"]
    for var in dash.get("templating", {}).get("list", []):
        q = var.get("query", {}).get("infinityQuery", {})
        if "url" in q:
            yield f"var:{var['name']}", q["url"]


def platform_of(url: str) -> str | None:
    """The effective platform param of a URL (unwrapping /compare paths)."""
    parsed = urllib.parse.urlparse(url)
    params = dict(urllib.parse.parse_qsl(parsed.query))
    if "/compare" in parsed.path and "path" in params:
        inner = urllib.parse.urlparse(params["path"])
        params = dict(urllib.parse.parse_qsl(inner.query))
        url = params.get("path", "") or inner.path
        return params.get("platform")
    return params.get("platform")


def touches_platform_route(url: str) -> bool:
    haystack = urllib.parse.unquote(url)
    return any(route in haystack for route in build_dashboards.PLATFORM_ROUTES)


class NycTimeContractTests(unittest.TestCase):
    def test_every_board_is_pinned_to_new_york(self) -> None:
        for uid in BOARDS:
            self.assertEqual(load(uid)["timezone"], "America/New_York", uid)

    def test_auto_refresh_is_hourly(self) -> None:
        """Layout edits live in Grafana's DB; aggressive auto-refresh churns
        panels and the boards must not refresh more than once an hour."""
        for uid in BOARDS:
            self.assertEqual(load(uid)["refresh"], "1h", uid)

    def test_no_bare_date_columns_survive(self) -> None:
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
        hourly = [
            (panel, target, col)
            for panel, target, col in timestamp_columns(load("omi-tv"))
            if col.get("timestampFormat") == "2006-01-02T15"
        ]
        self.assertTrue(hourly, "expected an hourly panel on the base board")
        for _panel, target, _col in hourly:
            self.assertNotIn("_tzdates", target["url"])


class PlatformScopeTests(unittest.TestCase):
    def test_every_posthog_query_pins_its_board_platform(self) -> None:
        """The 'same DAU on every board' bug: an unscoped viral-metrics /
        dau-trends / retention / k-factor URL reports macOS-only numbers
        wherever it appears."""
        for uid, scope in BOARD_SCOPE.items():
            exceptions = {"var:d_act"} if uid == "omi-tv" else set()
            for where, url in all_urls(load(uid)):
                if not touches_platform_route(url):
                    continue
                expected = "macos" if where in exceptions else scope
                self.assertEqual(platform_of(url), expected,
                                 f"{uid} / {where}: expected platform={expected} in {url}")

    def test_switcher_links_on_every_board(self) -> None:
        for uid in BOARDS:
            urls = [link["url"] for link in load(uid)["links"]]
            self.assertEqual(
                urls,
                ["/grafana/d/omi-tv/", "/grafana/d/omi-tv-macos/", "/grafana/d/omi-tv-mobile/"],
                uid,
            )


class MirrorTests(unittest.TestCase):
    @staticmethod
    def normalized_titles(dash) -> set[str]:
        return {
            re.sub(r"desktop|mobile|macOS|Mobile", "×", build_dashboards.base_title(p))
            for p in dash["panels"]
        }

    @staticmethod
    def normalize(title: str) -> str:
        title = title.split("  ·  ")[0]
        title = re.sub(r"macOS: beta vs production", "×: split", title)
        title = re.sub(r"Mobile: iOS vs Android", "×: split", title)
        title = re.sub(r"macOS: by version", "×: by version", title)
        title = re.sub(r"Mobile: by app version", "×: by version", title)
        return re.sub(r"desktop|mobile|macOS|Mobile", "×", title)

    def test_mobile_mirrors_macos_panel_for_panel(self) -> None:
        """Position-by-position: same normalized title, same gridPos, and the
        same panel type — except the five no-mobile-data placeholders, which
        must be text panels in the same slots."""
        macos, mobile = load("omi-tv-macos"), load("omi-tv-mobile")
        self.assertEqual(len(mobile["panels"]), len(macos["panels"]))
        placeholder_norms = {self.normalize(t) for t in build_dashboards.DESKTOP_ONLY_TITLES}
        for m_panel, mob_panel in zip(macos["panels"], mobile["panels"]):
            m_norm = self.normalize(m_panel["title"])
            self.assertEqual(m_norm, self.normalize(mob_panel["title"]))
            self.assertEqual(m_panel["gridPos"], mob_panel["gridPos"],
                             f"layout diverges at {m_panel['title']}")
            if m_norm in placeholder_norms:
                self.assertEqual(mob_panel["type"], "text", m_panel["title"])
            else:
                self.assertEqual(mob_panel["type"], m_panel["type"], m_panel["title"])

    def test_desktop_only_surfaces_are_explicit_placeholders_on_mobile(self) -> None:
        mobile = load("omi-tv-mobile")
        for title in build_dashboards.DESKTOP_ONLY_TITLES:
            panel = build_dashboards.panel_by_title(mobile, title)
            self.assertEqual(panel["type"], "text", title)
            self.assertIn("Desktop-only", panel["options"]["content"], title)
            self.assertIn("/grafana/d/omi-tv-macos/", panel["options"]["content"], title)

    def test_mobile_equivalents_query_the_mobile_scope(self) -> None:
        mobile = load("omi-tv-mobile")
        for title in ["Mobile: iOS vs Android (today)", "Mobile: by app version (today)",
                      "Mobile active today"]:
            panel = build_dashboards.panel_by_title(mobile, title)
            self.assertIn("macos-versions?platform=mobile", panel["targets"][0]["url"], title)

    def test_platform_growth_charts_share_the_ticker_population(self) -> None:
        """The cumulative chart must end at the all-time ticker value: both
        read viral-metrics (userGrowth / allTimeUsers), same person-dedup."""
        for uid in ["omi-tv-macos", "omi-tv-mobile"]:
            dash = load(uid)
            for title in ["Daily new users", "Cumulative users"]:
                panel = next(p for p in dash["panels"]
                             if build_dashboards.base_title(p).startswith(title.split(" (")[0])
                             and p["type"] == "timeseries")
                target = panel["targets"][0]
                self.assertIn("viral-metrics", target["url"], f"{uid}/{title}")
                self.assertEqual(target["root_selector"], "userGrowth", f"{uid}/{title}")

    def test_boards_do_not_leak_the_other_platforms_series(self) -> None:
        for uid, foreign in [("omi-tv-macos", "mobile"), ("omi-tv-mobile", "desktop")]:
            for panel in load(uid)["panels"]:
                for target in panel.get("targets", []):
                    for col in target.get("columns", []):
                        self.assertNotIn(foreign, col.get("selector", "").lower(),
                                         f"{uid} leaks {foreign} series in {panel['title']}")

    def test_platform_tickers_use_alltime_users(self) -> None:
        for uid, label in [("omi-tv-macos", "macOS"), ("omi-tv-mobile", "Mobile")]:
            ticker = build_dashboards.panel_by_title(load(uid), f"{label} users (all-time)")
            target = ticker["targets"][0]
            self.assertIn("viral-metrics", target["url"])
            self.assertEqual(target["columns"][0]["selector"], "allTimeUsers")


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


class AccountLevelLeakTests(unittest.TestCase):
    def test_account_level_metrics_stay_off_platform_boards(self) -> None:
        """Account-level metrics (all-Firestore-user populations, per-account
        pushes) have no platform dimension; showing them on a platform board
        silently mislabels cross-platform data. Regression: the desktop
        notifications_enabled gauge leaked onto the macOS board."""
        account_level = build_dashboards.ACCOUNT_LEVEL_TITLES
        self.assertIn("Notifications enabled", account_level)
        for uid in ["omi-tv-macos", "omi-tv-mobile"]:
            titles = {build_dashboards.base_title(p) for p in load(uid)["panels"]}
            leaked = titles & account_level
            self.assertFalse(leaked, f"{uid} leaks account-level panels: {leaked}")
        all_titles = {build_dashboards.base_title(p) for p in load("omi-tv")["panels"]}
        self.assertTrue(account_level <= all_titles,
                        "All board must keep the account-level panels")


class ReleasePanelTests(unittest.TestCase):
    def test_all_board_has_the_two_line_release_chart(self) -> None:
        panel = next(p for p in load("omi-tv")["panels"]
                     if build_dashboards.base_title(p) == build_dashboards.RELEASES_CHART_TITLE)
        target = panel["targets"][0]
        self.assertIn("/api/omi/stats/releases", target["url"])
        self.assertIn("_tzdates=date", target["url"])
        names = [c["text"] for c in target["columns"]]
        self.assertEqual(names, ["time", "macOS releases", "iOS releases"])

    def test_platform_boards_show_their_latest_release_stat(self) -> None:
        for uid, root, absent in [("omi-tv-macos", "latest.macos", "latest.ios"),
                                  ("omi-tv-mobile", "latest.ios", "latest.macos")]:
            dash = load(uid)
            titles = [build_dashboards.base_title(p) for p in dash["panels"]]
            self.assertNotIn(build_dashboards.RELEASES_CHART_TITLE, titles, uid)
            stat = next(p for p in dash["panels"]
                        if build_dashboards.base_title(p).startswith("Latest"))
            self.assertEqual(stat["targets"][0]["root_selector"], root, uid)
            self.assertNotEqual(stat["targets"][0]["root_selector"], absent, uid)


class KFactorTests(unittest.TestCase):
    """The K-factor surface: stat tile + daily graph + daily/weekly trackers,
    platform-scoped per board, reading the rebuilt viral-signals payload."""

    def test_kfactor_tile_reads_summary_and_names_its_board_scope(self) -> None:
        for uid, label in [("omi-tv", "all platforms"), ("omi-tv-macos", "macOS"),
                           ("omi-tv-mobile", "Mobile")]:
            panel = next(p for p in load(uid)["panels"]
                         if build_dashboards.base_title(p).startswith("K-factor")
                         and p.get("type") == "stat")
            self.assertIn(f"last 30d ({label})", panel["description"], uid)
            target = panel["targets"][0]
            self.assertEqual(target["root_selector"], "summary", uid)
            self.assertEqual([c["selector"] for c in target["columns"]], ["kFactor"], uid)

    def test_mobile_kfactor_tile_admits_shares_only(self) -> None:
        panel = next(p for p in load("omi-tv-mobile")["panels"]
                     if build_dashboards.base_title(p).startswith("K-factor")
                     and p.get("type") == "stat")
        self.assertIn("desktop-only", panel["description"])

    def test_every_board_has_the_viral_tracker_panels(self) -> None:
        for uid, scope in [("omi-tv", "all"), ("omi-tv-macos", "macos"),
                           ("omi-tv-mobile", "mobile")]:
            dash = load(uid)
            for title, root in [("K-factor — daily", "daily"),
                                ("Viral loop — daily", "daily"),
                                ("Viral loop — weekly", "weekly")]:
                panel = next(p for p in dash["panels"]
                             if build_dashboards.base_title(p) == title)
                target = panel["targets"][0]
                self.assertEqual(target["root_selector"], root, f"{uid} {title}")
                params = urllib.parse.parse_qs(
                    urllib.parse.urlparse(target["url"]).query)
                self.assertEqual(params["platform"], [scope], f"{uid} {title}")
                # The date/week column is routed through the proxy's NYC
                # rewrite, never parsed as a bare UTC-midnight day.
                ts_cols = [c for c in target["columns"] if c["type"] == "timestamp"]
                self.assertEqual(len(ts_cols), 1, f"{uid} {title}")
                self.assertEqual(ts_cols[0]["timestampFormat"],
                                 build_dashboards.RFC3339, f"{uid} {title}")
                self.assertEqual(params["_tzdates"], [ts_cols[0]["selector"]],
                                 f"{uid} {title}")

    def test_viral_trackers_chart_all_three_signals(self) -> None:
        for uid in ["omi-tv", "omi-tv-macos", "omi-tv-mobile"]:
            for title in ["Viral loop — daily", "Viral loop — weekly"]:
                panel = next(p for p in load(uid)["panels"]
                             if build_dashboards.base_title(p) == title)
                selectors = [c["selector"] for c in panel["targets"][0]["columns"]
                             if c.get("type") != "timestamp"]
                self.assertEqual(selectors, ["friend", "referral", "shares"],
                                 f"{uid} {title}")


class ExactRevenueTests(unittest.TestCase):
    def test_platform_revenue_never_includes_unknown_attribution(self) -> None:
        """profitability's plain desktop/mobile revenue fields smear
        unknown-platform subscription MRR proportionally; platform boards must
        chart only the exact-attribution fields."""
        for uid, field in [("omi-tv-macos", "desktopExact"), ("omi-tv-mobile", "mobileExact")]:
            dash = load(uid)
            panel = next(p for p in dash["panels"]
                         if build_dashboards.base_title(p).startswith("Revenue / day"))
            selectors = [c["selector"] for c in panel["targets"][0]["columns"]
                         if c.get("type") != "timestamp"]
            self.assertEqual(selectors, [field], uid)
            var = next(v for v in dash["templating"]["list"] if v["name"] == "d_prev")
            url = var["query"]["infinityQuery"]["url"]
            params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            self.assertEqual(params["fields"], [field], uid)


class BuilderIdempotencyTests(unittest.TestCase):
    def test_rebuild_is_idempotent(self) -> None:
        base = load("omi-tv")
        rebuilt = copy.deepcopy(base)
        build_dashboards.apply_tzdates(rebuilt)
        build_dashboards.apply_platform(rebuilt, "all")
        build_dashboards.retarget_var(
            rebuilt, "d_act",
            path=build_dashboards.set_url_param(build_dashboards.VIRAL_PATH, "platform", "macos"),
        )
        build_dashboards.finish(rebuilt, "omi-tv", "Omi TV")
        self.assertEqual(base, rebuilt)
        self.assertEqual(build_dashboards.build_platform_board(rebuilt, "macos"),
                         load("omi-tv-macos"))
        self.assertEqual(build_dashboards.build_platform_board(rebuilt, "mobile"),
                         load("omi-tv-mobile"))


class RetentionCurveAxisTests(unittest.TestCase):
    """Day numbers on the 30d curve must not inherit unit=percent
    (Grafana then labels 0/11/22 as 0%/11%/22%)."""

    def test_day_axis_is_not_percent(self) -> None:
        for uid in BOARDS:
            panel = next(
                p for p in load(uid)["panels"]
                if build_dashboards.base_title(p).startswith("Retention curve")
            )
            self.assertIsNone(
                panel["fieldConfig"]["defaults"].get("unit"), uid
            )
            overrides = {
                o["matcher"]["options"]: o
                for o in panel["fieldConfig"]["overrides"]
            }
            self.assertEqual(
                overrides["Day"]["properties"],
                [{"id": "unit", "value": "none"}],
                uid,
            )
            self.assertEqual(
                overrides["Retention"]["properties"],
                [{"id": "unit", "value": "percent"}],
                uid,
            )


class ApplyPreservesLayoutTests(unittest.TestCase):
    """An apply must never revert layout the user arranged in the Grafana UI
    (#12212 era: three same-day applies stamped checked-in gridPos over
    Nik's manual resizes). Live geometry wins for panels that already exist."""

    def test_live_gridpos_wins_for_existing_panels(self) -> None:
        import apply_omi_tv_dashboard as apply_mod
        incoming = [
            {"id": 7, "gridPos": {"h": 6, "w": 4, "x": 20, "y": 0}},
            {"id": 992, "gridPos": {"h": 7, "w": 24, "x": 0, "y": 990}},
        ]
        live = [
            {"id": 7, "gridPos": {"h": 9, "w": 12, "x": 0, "y": 3}},  # user resized
        ]
        apply_mod.preserve_live_layout(incoming, live)
        self.assertEqual(incoming[0]["gridPos"], {"h": 9, "w": 12, "x": 0, "y": 3})
        # A panel new to this apply keeps its authored position.
        self.assertEqual(incoming[1]["gridPos"], {"h": 7, "w": 24, "x": 0, "y": 990})

    def test_first_apply_of_a_new_board_keeps_authored_layout(self) -> None:
        import apply_omi_tv_dashboard as apply_mod
        incoming = [{"id": 1, "gridPos": {"h": 6, "w": 4, "x": 0, "y": 0}}]
        apply_mod.preserve_live_layout(incoming, [])
        self.assertEqual(incoming[0]["gridPos"], {"h": 6, "w": 4, "x": 0, "y": 0})


if __name__ == "__main__":
    unittest.main()
