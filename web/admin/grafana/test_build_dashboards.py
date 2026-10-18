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
    def test_plan_economics_is_account_scoped_and_discloses_coverage(self) -> None:
        titles = {
            "Plan economics — data coverage", "Cost and margin by plan — 30-day run rate",
            "Per-user economics by plan", "Cost by plan — 30-day run rate",
        }
        for uid in BOARDS:
            panels = [p for p in load(uid)["panels"] if p["title"] in titles]
            self.assertEqual(len(panels), 4 if uid == "omi-tv" else 0)
            for panel in panels:
                self.assertTrue(panel["targets"][0]["url"].endswith("/api/omi/stats/plan-economics"))
                self.assertEqual(panel["fieldConfig"]["defaults"]["noValue"], "N/A")
        panels = {p["title"]: p for p in load("omi-tv")["panels"] if p["title"] in titles}
        self.assertEqual(panels["Plan economics — data coverage"]["targets"][0]["root_selector"], "status")
        unit_fields = {c["selector"] for c in panels["Per-user economics by plan"]["targets"][0]["columns"]}
        self.assertTrue({"subscribers", "activeUsersPerDay", "costPerSubscriber", "costPerActiveDay", "unitBasis"} <= unit_fields)

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
        # Battery panels are mobile-only; the shared mirror is everything else.
        mobile_panels = [
            panel for panel in mobile["panels"]
            if build_dashboards.base_title(panel) not in build_dashboards.MOBILE_BATTERY_TITLES
        ]
        self.assertEqual(len(mobile_panels), len(macos["panels"]))
        placeholder_norms = {self.normalize(t) for t in build_dashboards.DESKTOP_ONLY_TITLES}
        for m_panel, mob_panel in zip(macos["panels"], mobile_panels):
            m_norm = self.normalize(m_panel["title"])
            self.assertEqual(m_norm, self.normalize(mob_panel["title"]))
            self.assertEqual(m_panel["gridPos"], mob_panel["gridPos"],
                             f"layout diverges at {m_panel['title']}")
            if m_norm in placeholder_norms:
                self.assertEqual(mob_panel["type"], "text", m_panel["title"])
            else:
                self.assertEqual(mob_panel["type"], m_panel["type"], m_panel["title"])

    def test_mobile_board_adds_battery_health_panels(self) -> None:
        mobile = load("omi-tv-mobile")
        by_title = {build_dashboards.base_title(panel): panel for panel in mobile["panels"]}
        pendant = by_title[build_dashboards.PENDANT_DRAIN_TITLE]
        phone = by_title[build_dashboards.PHONE_DRAIN_TITLE]
        self.assertEqual(pendant["type"], "barchart")
        self.assertEqual(phone["type"], "barchart")
        self.assertEqual(pendant["datasource"]["uid"], "omi-admin-api")
        self.assertEqual(phone["datasource"]["uid"], "omi-admin-api")
        self.assertEqual(pendant["targets"][0]["root_selector"], "pendant_health")
        self.assertEqual(phone["targets"][0]["root_selector"], "phone_health.series")
        self.assertIn(
            "/api/omi/stats/device-health?days=7",
            pendant["targets"][0]["url"],
        )
        self.assertIn(
            "/api/omi/stats/device-health?days=14",
            phone["targets"][0]["url"],
        )
        self.assertNotIn("days=14", pendant["targets"][0]["url"])
        self.assertEqual(
            [column["selector"] for column in pendant["targets"][0]["columns"]],
            ["firmware_label", "p50_drain_valid", "p90_drain_valid", "users"],
        )
        self.assertEqual(
            [column["selector"] for column in phone["targets"][0]["columns"]],
            ["label", "p50_drain_per_hour", "p90_drain_per_hour", "users"],
        )
        for panel in (pendant, phone):
            defaults = panel["fieldConfig"]["defaults"]
            self.assertNotIn("max", defaults)
            self.assertEqual(defaults["custom"]["barWidth"], 0.62)
            self.assertEqual(panel["options"]["orientation"], "horizontal")
            self.assertEqual(panel["options"]["tooltip"]["mode"], "multi")
            hidden = [
                override for override in panel["fieldConfig"]["overrides"]
                if override["matcher"]["options"] == "users"
            ]
            self.assertEqual(
                hidden[0]["properties"][1]["value"],
                {"tooltip": False, "viz": True, "legend": True},
            )
            p90 = [
                override for override in panel["fieldConfig"]["overrides"]
                if override["matcher"]["options"] == "p90 drain %/h"
            ]
            self.assertTrue(p90)
        for uid in ("omi-tv", "omi-tv-macos"):
            titles = {build_dashboards.base_title(panel) for panel in load(uid)["panels"]}
            self.assertTrue(build_dashboards.MOBILE_BATTERY_TITLES.isdisjoint(titles), uid)

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
    def test_apply_publishes_only_legacy_boards(self) -> None:
        import apply_omi_tv_dashboard as apply_mod

        found = {
            json.loads(path.read_text(encoding="utf-8"))["uid"]
            for path in (HERE / "dashboards").glob("*.json")
        }
        self.assertEqual(found, set(BOARDS) | {"omi-tv-v2"})
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
    def test_all_board_has_the_three_series_release_chart(self) -> None:
        panel = next(p for p in load("omi-tv")["panels"]
                     if build_dashboards.base_title(p) == build_dashboards.RELEASES_CHART_TITLE)
        target = panel["targets"][0]
        self.assertIn("/api/omi/stats/releases", target["url"])
        self.assertIn("_tzdates=date", target["url"])
        names = [c["text"] for c in target["columns"]]
        self.assertEqual(names, ["time", "macOS releases", "iOS releases", "Android releases"])
        self.assertEqual([c["selector"] for c in target["columns"]],
                         ["date", "macos", "ios", "android"])
        self.assertIn("TestFlight/Play builds included", panel["description"])
        colors = {o["matcher"]["options"]: o["properties"][0]["value"]["fixedColor"]
                  for o in panel["fieldConfig"]["overrides"]}
        self.assertEqual(set(colors), {"macOS releases", "iOS releases", "Android releases"})
        self.assertEqual(len(set(colors.values())), 3)
        self.assertNotIn(colors["Android releases"].lower(), {"#a855f7", "#9333ea"})

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


class CanonicalProfitabilityKeyTests(unittest.TestCase):
    """Boards must read the profitability key the precompute cron writes.

    The cache key embeds desktop_cost/mobile_cost and the cron precomputes
    only the default (0.2/0.2) params, so a URL carrying its own cost params
    reads a legacy doc no writer maintains. That doc was served frozen for
    ~4 weeks (Aug 25) while a fresh one sat under the default key — this
    static tripwire keeps every board surface on the canonical key.
    """

    def test_profit_path_carries_no_cost_params(self) -> None:
        parsed = urllib.parse.urlparse(build_dashboards.PROFIT_PATH)
        params = urllib.parse.parse_qs(parsed.query)
        self.assertNotIn("desktop_cost", params)
        self.assertNotIn("mobile_cost", params)

    def test_no_board_profitability_url_carries_cost_params(self) -> None:
        for uid in BOARDS:
            for where, url in all_urls(load(uid)):
                haystack = urllib.parse.unquote(url)
                if "profitability" not in haystack:
                    continue
                self.assertNotIn("desktop_cost", haystack, f"{uid} {where}")
                self.assertNotIn("mobile_cost", haystack, f"{uid} {where}")


def is_strip(panel):
    return panel["type"] == "stat" and panel["targets"][0]["root_selector"].startswith("frames.strip_")


def is_text_line(panel):
    """Untitled one-row stats: the delta strips and the data-through line."""
    return panel["type"] == "stat" and panel.get("transparent") and not panel["title"]


class WallV2Contract(unittest.TestCase):
    def test_checked_in_wall_matches_builder(self):
        from build_wall_dashboard import build_wall_board
        self.assertEqual(load("omi-tv-v2"), build_wall_board())

    def test_noop_legacy_build_preserves_authored_bytes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            path.write_text('{"panels": []}\n')
            before = path.read_bytes()
            build_dashboards.write_if_changed(path, {"panels": []})
            self.assertEqual(path.read_bytes(), before)

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
        self.assertEqual(len(stats), 5)
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
        for line in ["gcp", "vertexLlm", "openai", "anthropic", "sttMeasuredUsd", "sttEstimateUsd",
                     "saasMeasuredUsd", "saasEstimateUsd", "revenuePerDay"]:
            self.assertIn(line, fields)
        styled = {o["matcher"]["options"]: {p["id"]: p["value"] for p in o["properties"]}
                  for o in cost["fieldConfig"]["overrides"]}
        for name in ESTIMATE:
            self.assertEqual(styled[name]["custom.fillOpacity"], ESTIMATE_OPACITY)
            self.assertNotIn("custom.stacking", styled[name])  # still in the stack
        self.assertEqual(set(ESTIMATE), {"STT est.", "SaaS est."})
        self.assertEqual(set(MEASURED), {"STT measured", "SaaS measured (Mercury)"})
        for name in MEASURED:
            self.assertIn(name, styled)
            self.assertNotIn("custom.fillOpacity", styled[name])
        self.assertTrue(cost["options"]["legend"]["showLegend"])  # identity is never color alone
        self.assertIn("Soniox console", cost["description"])
        self.assertIn("measured SaaS (Mercury)", cost["description"])
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
        self.assertEqual(custom["insertNulls"], 2 * 86_400_000)
        self.assertFalse(custom["spanNulls"])  # a gap is drawn as a gap
        self.assertEqual(panel["timeFrom"], "35d")  # the FinOps book's daily history
        self.assertIn("one point per day", panel["description"])

    def test_margin_by_plan_sits_beside_unit_economics(self):
        from build_wall_dashboard import FREE, PLAN_NAMES
        board = load("omi-tv-v2")
        panel = next(p for p in board["panels"] if p["title"] == "Margin by plan")
        unit = next(p for p in board["panels"] if p["title"] == "Unit economics")
        self.assertEqual(panel["gridPos"]["y"], unit["gridPos"]["y"])
        self.assertEqual(panel["gridPos"]["h"], unit["gridPos"]["h"])
        self.assertEqual(panel["gridPos"]["x"] + panel["gridPos"]["w"], unit["gridPos"]["x"])
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

    def test_legacy_apply_rejects_private_uid_without_changing_layout_policy(self):
        import apply_omi_tv_dashboard as apply_module
        with self.assertRaises(SystemExit):
            apply_module.load_dashboard(HERE / "dashboards/omi-tv-v2.json")
        incoming=[{"id":1,"gridPos":{"x":0}}]
        apply_module.preserve_live_layout(incoming,[{"id":1,"gridPos":{"x":5}}])
        self.assertEqual(incoming[0]["gridPos"],{"x":5})


if __name__ == "__main__":
    unittest.main()
