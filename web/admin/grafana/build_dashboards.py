#!/usr/bin/env python3
"""Derive the platform dashboards from the checked-in omi-tv board.

Reads dashboards/omi-tv.json (the "All platforms" board, source of truth),
then:
  1. In place: pins timezone to America/New_York, routes daily/weekly/monthly
     date columns through the proxy's `_tzdates` rewrite (so each bucket
     renders on its labeled calendar day instead of shifting 8 pm earlier),
     pins `platform=all` on the PostHog-backed routes, and adds the
     All / macOS / Mobile switcher links.
  2. Writes dashboards/omi-tv-macos.json and dashboards/omi-tv-mobile.json —
     the SAME board scoped per platform (`platform=macos` / `platform=mobile`
     on viral-metrics, dau-trends, retention and k-factor; per-platform series
     of /api/omi/stats/profitability for signups/revenue/cost/conversion).
     The mobile board mirrors the macOS board panel-for-panel except the
     desktop-only product surfaces (floating bar, desktop notifications,
     desktop crash rate, macOS version pies), which have no mobile analog.

Mobile IS instrumented in PostHog (iOS since 2025-03, Android since 2026-05)
but does not emit `Sign In Completed`, so its signup/activation cohorts anchor
on first-seen-any-event (handled inside viral-metrics).

Idempotent: run after editing omi-tv.json, commit all three outputs.
apply_omi_tv_dashboard.py publishes every dashboards/*.json to Grafana.
"""

from __future__ import annotations

import copy
import json
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
DASH_DIR = HERE / "dashboards"
BASE_PATH = DASH_DIR / "omi-tv.json"

PROFIT_PATH = "/api/omi/stats/profitability?days=30&desktop_cost=1.2&mobile_cost=0.3"
VIRAL_PATH = "/api/omi/stats/viral-metrics?days=60"
PROXY = "http://127.0.0.1:8899"
RFC3339 = "2006-01-02T15:04:05Z07:00"
DAY_FORMATS = {"2006-01-02", "2006-01"}

# Routes that accept ?platform=all|macos|mobile.
PLATFORM_ROUTES = ("viral-metrics", "dau-trends", "retention/posthog", "k-factor/posthog")

# Surfaces with NO mobile data at all — kept on the mobile board as explicit
# "not available on mobile" placeholders so both platform boards stay
# panel-for-panel identical without mislabeling desktop data as mobile.
# (Floating bar is a macOS-only feature; mobile sends no crash telemetry.)
DESKTOP_ONLY_TITLES = {
    "Floating bar queries per user", "Floating bar queries",
    "Floating bar notification CTR", "Crash-free rate (today)",
    "Crash-free rate", "Omi Desktop rating — daily",
}

# Account-level metrics: computed over every Firestore user (or every device a
# user owns) with no platform dimension — they live on the All board only.
# "Notifications enabled" counts all user docs and defaults missing fields to
# enabled, so scoping it to a platform would silently lie.
ACCOUNT_LEVEL_TITLES = {
    "Daily notifications sent", "Notifications sent — last 168 hours",
    "Weekly notification reach", "Notifications enabled",
}

LINKS = [
    {"title": title, "type": "link", "url": f"/grafana/d/{uid}/", "icon": "dashboard",
     "asDropdown": False, "includeVars": False, "keepTime": False, "targetBlank": False,
     "tags": [], "tooltip": ""}
    for title, uid in [("All platforms", "omi-tv"),
                       ("macOS", "omi-tv-macos"),
                       ("Mobile", "omi-tv-mobile")]
]


def base_title(panel) -> str:
    return panel.get("title", "").split("  ·  ")[0]


def add_query_param(url: str, key: str, value: str) -> str:
    if f"{key}=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{key}={value}"


def set_url_param(url: str, key: str, value: str) -> str:
    """Set/replace a query param, preserving the rest of the URL."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qsl(parsed.query)
    params = [(k, v) for k, v in params if k != key] + [(key, value)]
    return parsed._replace(query=urllib.parse.urlencode(params)).geturl()


def set_platform(url: str, scope: str) -> str:
    """Pin ?platform=<scope> on platform-aware routes, including routes
    wrapped inside a /compare?path=… URL."""
    if "/compare?" in url:
        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        inner = params.get("path", "")
        if any(route in inner for route in PLATFORM_ROUTES):
            params["path"] = set_url_param(inner, "platform", scope)
            return f"{PROXY}{parsed.path}?" + urllib.parse.urlencode(params)
        return url
    if any(route in url for route in PLATFORM_ROUTES):
        return set_url_param(url, "platform", scope)
    return url


def apply_platform(dash, scope: str) -> None:
    for panel in dash.get("panels", []):
        for target in panel.get("targets", []):
            if "url" in target:
                target["url"] = set_platform(target["url"], scope)
    for var in dash.get("templating", {}).get("list", []):
        q = var.get("query", {}).get("infinityQuery", {})
        if "url" in q:
            q["url"] = set_platform(q["url"], scope)


def apply_tzdates(dash) -> None:
    for panel in dash.get("panels", []):
        for target in panel.get("targets", []):
            fields = []
            for col in target.get("columns", []):
                if col.get("type") == "timestamp" and col.get("timestampFormat") in DAY_FORMATS:
                    fields.append(col["selector"])
                    col["timestampFormat"] = RFC3339
            if fields:
                target["url"] = add_query_param(target["url"], "_tzdates", ",".join(fields))


def set_compare(query_holder: dict, url_key: str, **overrides) -> None:
    """Rewrite a /compare URL's params in place (query_holder[url_key])."""
    parsed = urllib.parse.urlparse(query_holder[url_key])
    params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    params.update({k: str(v) for k, v in overrides.items()})
    query_holder[url_key] = f"{PROXY}{parsed.path}?" + urllib.parse.urlencode(params)


def panel_by_title(dash, title):
    for panel in dash.get("panels", []):
        if base_title(panel) == title:
            return panel
    raise KeyError(f"panel not found: {title}")


def set_stat_query(panel, path: str, root: str, selector: str, text: str) -> None:
    target = panel["targets"][0]
    target["url"] = f"{PROXY}{path}"
    target["root_selector"] = root
    target["columns"] = [{"selector": selector, "text": text, "type": "number"}]


def platform_series(panel, path: str, root: str, field: str, series_name: str) -> None:
    """Point a time-series panel at one platform field of a profitability root."""
    target = panel["targets"][0]
    target["url"] = add_query_param(f"{PROXY}{path}", "_tzdates", "date")
    target["root_selector"] = root
    target["columns"] = [
        {"selector": "date", "text": "time", "type": "timestamp", "timestampFormat": RFC3339},
        {"selector": field, "text": series_name, "type": "number"},
    ]
    panel["timeFrom"] = "30d"


def keep_series(panel, keep: set[str]) -> None:
    target = panel["targets"][0]
    target["columns"] = [
        c for c in target.get("columns", [])
        if c.get("type") == "timestamp" or c.get("text") in keep
    ]


def prune_vars_and_titles(dash) -> None:
    titles = " ".join(p.get("title", "") for p in dash.get("panels", []))
    kept = []
    for var in dash.get("templating", {}).get("list", []):
        if "${" + var["name"] + "}" in titles:
            kept.append(var)
    dash["templating"]["list"] = kept
    names = {v["name"] for v in kept}
    for panel in dash.get("panels", []):
        title = panel.get("title", "")
        if "${" in title:
            head, _, var = title.partition("  ·  ")
            if var.strip().strip("${}") not in names:
                panel["title"] = head


def retarget_var(dash, name: str, **overrides) -> None:
    for var in dash.get("templating", {}).get("list", []):
        if var["name"] == name:
            set_compare(var["query"]["infinityQuery"], "url", **overrides)
            return


def reflow(dash) -> None:
    """Repack panels left-to-right, top-to-bottom, keeping each panel's size."""
    x = y = row_h = 0
    for panel in dash.get("panels", []):
        w, h = panel["gridPos"]["w"], panel["gridPos"]["h"]
        if x + w > 24:
            x, y, row_h = 0, y + row_h, 0
        panel["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
        x += w
        row_h = max(row_h, h)


def drop_panels(dash, titles: set[str]) -> None:
    dash["panels"] = [p for p in dash["panels"] if base_title(p) not in titles]


def placeholder_panels(dash, titles: set[str]) -> None:
    """Replace panels in place with same-size 'not available' text panels."""
    for i, panel in enumerate(dash["panels"]):
        if base_title(panel) not in titles:
            continue
        dash["panels"][i] = {
            "id": panel["id"],
            "type": "text",
            "title": base_title(panel),
            "gridPos": panel["gridPos"],
            "transparent": True,
            "options": {
                "mode": "markdown",
                "content": "**Desktop-only surface — no mobile equivalent.**\n\n"
                           "This feature exists only in the macOS app; see the "
                           "[macOS board](/grafana/d/omi-tv-macos/).",
            },
            "targets": [],
        }


def user_growth_series(panel, scope: str, field: str, series_name: str) -> None:
    """Point a chart at viral-metrics userGrowth — the same person-deduped
    population as the all-time ticker, so counts agree across the board."""
    viral = set_url_param(VIRAL_PATH, "platform", scope)
    target = panel["targets"][0]
    target["url"] = add_query_param(f"{PROXY}{viral}", "_tzdates", "date")
    target["root_selector"] = "userGrowth"
    target["columns"] = [
        {"selector": "date", "text": "time", "type": "timestamp", "timestampFormat": RFC3339},
        {"selector": field, "text": series_name, "type": "number"},
    ]
    panel["timeFrom"] = "30d"



RELEASES_PATH = "/api/omi/stats/releases?days=30"
RELEASES_CHART_TITLE = "Releases / day — macOS vs iOS"


def releases_chart_panel(panel_id: int) -> dict:
    """All-board timeline: one chart, two series — release cadence per
    platform. A multi-day flat zero on either line is the alarm."""
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": RELEASES_CHART_TITLE,
        "description": "macOS: GitHub releases tagged -macos (candidates included). "
                       "iOS: first day a version clears 200 daily App Store users "
                       "(TestFlight noise excluded); latest verified against the "
                       "App Store lookup API.",
        "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "omi-admin-api"},
        "gridPos": {"x": 0, "y": 999, "w": 24, "h": 6},
        "timeFrom": "30d",
        "fieldConfig": {
            "defaults": {
                "unit": "short",
                "min": 0,
                "color": {"mode": "palette-classic"},
                "custom": {
                    "drawStyle": "bars", "lineWidth": 1, "fillOpacity": 70,
                    "showPoints": "always", "pointSize": 5, "barAlignment": 0,
                    "stacking": {"mode": "none", "group": "A"},
                    "axisPlacement": "auto", "gradientMode": "none",
                    "spanNulls": False,
                },
            },
            "overrides": [
                {"matcher": {"id": "byName", "options": "macOS releases"},
                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "#3b82f6"}}]},
                {"matcher": {"id": "byName", "options": "iOS releases"},
                 "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "#22c55e"}}]},
            ],
        },
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "none"},
        },
        "targets": [{
            "refId": "A",
            "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "omi-admin-api"},
            "type": "json", "source": "url", "parser": "backend", "format": "timeseries",
            "url": f"{PROXY}{RELEASES_PATH}",
            "url_options": {"method": "GET", "data": ""},
            "root_selector": "daily",
            "columns": [
                {"selector": "date", "text": "time", "type": "timestamp",
                 "timestampFormat": "2006-01-02"},
                {"selector": "macos", "text": "macOS releases", "type": "number"},
                {"selector": "ios", "text": "iOS releases", "type": "number"},
            ],
        }],
    }


def latest_release_stat(panel_id: int, scope: str) -> dict:
    """Platform-board tile: latest release version + date, with days-since
    colored green (fresh) → red (3+ days stale)."""
    key = "macos" if scope == "macos" else "ios"
    label = "macOS" if scope == "macos" else "Mobile"
    return {
        "id": panel_id,
        "type": "stat",
        "title": f"Latest {label} release",
        "description": ("GitHub releases tagged -macos" if scope == "macos"
                        else "App Store lookup (exact store release)"),
        "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "omi-admin-api"},
        "gridPos": {"x": 0, "y": 8, "w": 4, "h": 4},
        "fieldConfig": {
            "defaults": {
                "unit": "short",
                "thresholds": {"mode": "absolute", "steps": [
                    {"color": "#22c55e", "value": None},
                    {"color": "#f59e0b", "value": 2},
                    {"color": "#ef4444", "value": 3},
                ]},
            },
            "overrides": [{
                "matcher": {"id": "byName", "options": "days ago"},
                "properties": [{"id": "unit", "value": "d"}],
            }],
        },
        "options": {
            "reduceOptions": {"values": False, "calcs": ["lastNotNull"], "fields": "/.*/"},
            "orientation": "horizontal",
            "textMode": "value_and_name",
            "colorMode": "value",
            "graphMode": "none",
            "justifyMode": "auto",
            "text": {"valueSize": 16, "titleSize": 11},
        },
        "targets": [{
            "refId": "A",
            "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": "omi-admin-api"},
            "type": "json", "source": "url", "parser": "backend", "format": "table",
            "url": f"{PROXY}{RELEASES_PATH}",
            "url_options": {"method": "GET", "data": ""},
            "root_selector": f"latest.{key}",
            "columns": [
                {"selector": "display", "text": "release", "type": "string"},
                {"selector": "daysSince", "text": "days ago", "type": "number"},
            ],
        }],
    }


def set_kfactor_tile_description(dash, platform_label: str, scope: str = "all") -> None:
    """The K-factor tile is platform-scoped per board; keep its description
    honest about which signals and which population each board counts."""
    mobile_note = (
        " Mobile counts summary shares only — the friend-source answer and the "
        "referral program are desktop-only signals."
        if scope == "mobile"
        else ""
    )
    for panel in dash.get("panels", []):
        if base_title(panel).startswith("K-factor") and panel.get("type") == "stat":
            panel["description"] = (
                f"Viral events (friend signups + referral redemptions + summary shares) "
                f"÷ first-seen new users, last 30d ({platform_label}).{mobile_note}"
            )


def finish(dash, uid: str, title: str) -> dict:
    dash["uid"] = uid
    dash["title"] = title
    dash["links"] = LINKS
    dash["timezone"] = "America/New_York"
    dash["refresh"] = "1h"  # Nik: auto-refresh at most hourly
    dash.pop("id", None)
    dash.pop("version", None)
    return dash


def build_platform_board(base, scope: str) -> dict:
    """One pipeline for both platform boards, so they stay mirrors of each
    other: same panels, same layout, per-platform data. `scope` is "macos"
    or "mobile"."""
    profit_field = "desktop" if scope == "macos" else "mobile"
    label = "macOS" if scope == "macos" else "Mobile"

    dash = copy.deepcopy(base)
    apply_platform(dash, scope)

    # Cross-platform business panels that have no per-platform breakdown.
    # Mentor "Omi says" pushes are account-level Firestore messages delivered
    # to every device a user has, so notification volume cannot be split by
    # platform either — those panels live on the All-platforms board only.
    drop_panels(dash, ACCOUNT_LEVEL_TITLES | {
        "1M goal", "ARR", "Active subscriptions", "Trialing",
        "Conversations", "MRR by product", "MRR over time",
        "New subscriptions / month", "Message ratings",
        "Infra cost by service — last 30 days",
    })
    if scope == "mobile":
        placeholder_panels(dash, DESKTOP_ONLY_TITLES)

    ticker = panel_by_title(dash, "Total users")
    ticker["title"] = f"{label} users (all-time)"
    ticker["gridPos"]["h"] = 6
    set_stat_query(
        ticker, set_url_param(VIRAL_PATH, "platform", scope),
        "summary", "allTimeUsers", f"{label} users",
    )

    mrr = panel_by_title(dash, "MRR")
    mrr["title"] = f"MRR ({label})"
    set_stat_query(mrr, PROFIT_PATH, "summary",
                   "mrrDesktop" if scope == "macos" else "mrrMobile", "MRR")

    # Signups / daily-new / cumulative all use viral-metrics userGrowth —
    # the same person-deduped PostHog population as the all-time ticker, so
    # the cumulative chart ends exactly at the ticker value.
    viral_scoped = set_url_param(VIRAL_PATH, "platform", scope)
    signups = panel_by_title(dash, "Signups (7d)")
    signups["title"] = f"{label} signups (7d)"
    set_compare(signups["targets"][0], "url",
                path=viral_scoped, root="userGrowth", fields="users")

    daily = panel_by_title(dash, "Daily new users")
    user_growth_series(daily, scope, "users", "New users")
    retarget_var(dash, "d_daily", path=viral_scoped, root="userGrowth", fields="users")

    cumulative = panel_by_title(dash, "Cumulative users")
    cumulative["title"] = f"Cumulative users ({label})  ·  ${{d_cum}}"
    user_growth_series(cumulative, scope, "cumulative", "Total users")
    retarget_var(dash, "d_cum", path=viral_scoped, root="userGrowth", fields="users")

    set_kfactor_tile_description(dash, label, scope)
    drop_panels(dash, {RELEASES_CHART_TITLE})
    kfactor_idx = next(i for i, p in enumerate(dash["panels"])
                       if base_title(p).startswith("K-factor") and p.get("type") == "stat")
    dash["panels"].insert(kfactor_idx + 1, latest_release_stat(990, scope))

    series_label = "Desktop" if scope == "macos" else "Mobile"
    for title, new_title, series in [
        ("New users / day by platform", f"New users / day ({profit_field})  ·  ${{d_pusers}}", series_label),
        ("Revenue / day by platform (est.)", f"Revenue / day ({profit_field}, est.)  ·  ${{d_prev}}", series_label),
        ("Infra cost / day by platform", f"Infra cost / day ({profit_field})  ·  ${{d_cost}}", series_label),
        ("Cost / user / day", f"Cost / user / day ({profit_field})  ·  ${{d_cpu}}", f"{series_label} $/user"),
        ("Free → paid conversion", f"Free → paid conversion ({profit_field})  ·  ${{d_conv}}", series_label),
    ]:
        panel = panel_by_title(dash, title)
        panel["title"] = new_title
        keep_series(panel, {series})
    for var in ["d_pusers", "d_prev", "d_cost", "d_cpu", "d_conv"]:
        retarget_var(dash, var, fields=profit_field)

    # Revenue must be exact-attribution only: the plain desktop/mobile revenue
    # series smears unknown-platform subscription MRR proportionally (fine for
    # the All board's stack, wrong on a platform board).
    exact_field = f"{profit_field}Exact"
    revenue_panel = panel_by_title(dash, f"Revenue / day ({profit_field}, est.)")
    for col in revenue_panel["targets"][0]["columns"]:
        if col.get("type") != "timestamp":
            col["selector"] = exact_field
    retarget_var(dash, "d_prev", fields=exact_field)

    if scope == "macos":
        # The stat tile is already platform-neutral ("Activation"); board
        # context makes the All board's "macOS only" marker redundant here.
        panel_by_title(dash, "Activation")["description"] = (
            "% of first-seen macOS users who asked 2+ questions (typed chat or "
            "push-to-talk) after completing onboarding, within their "
            "first 48 hours (PostHog; matured signups only). The aha moment — "
            "biggest controllable lever, first-5-minutes work."
        )
        chart = panel_by_title(dash, "Activation (signup → activated, macOS)")
        chart["title"] = "Activation (signup → activated)" + (
            "  ·  " + chart["title"].split("  ·  ")[1] if "  ·  " in chart["title"] else "")
    if scope == "mobile":
        # Real mobile equivalents of the macOS-titled panels.
        versions_mobile = "/api/omi/stats/macos-versions?platform=mobile"
        channel_pie = panel_by_title(dash, "macOS: beta vs production (today)")
        channel_pie["title"] = "Mobile: iOS vs Android (today)"
        channel_pie["targets"][0]["url"] = f"{PROXY}{versions_mobile}"
        version_pie = panel_by_title(dash, "macOS: by version (today)")
        version_pie["title"] = "Mobile: by app version (today)"
        version_pie["targets"][0]["url"] = f"{PROXY}{versions_mobile}"
        active_today = panel_by_title(dash, "macOS active today")
        active_today["title"] = "Mobile active today"
        active_today["targets"][0]["url"] = f"{PROXY}{versions_mobile}"

        # The Firestore activation route is macOS-only (conversation within 7
        # days of a macOS signup); mobile activation uses PostHog telemetry
        # (first-seen → Memory Created within 7 days) via viral-metrics.
        viral_mobile = set_url_param(VIRAL_PATH, "platform", "mobile")
        rate = panel_by_title(dash, "Activation")
        rate["description"] = (
            "PostHog telemetry: % of first-seen mobile users with a Memory Created "
            "within 7 days. Not the Firestore signup→conversation definition the "
            "All and macOS boards use."
        )
        set_stat_query(rate, viral_mobile, "summary", "activationRate", "Activation")
        # Mobile daily activation: viral-metrics' daily telemetry series (its
        # own definition, Memory Created <=7d) — honest, not the macOS 2q/48h.
        daily_chart = panel_by_title(dash, "Activation rate — daily")
        daily_chart["description"] = (
            "PostHog telemetry: daily % of first-seen mobile users with a Memory "
            "Created within 7 days (not the macOS 2-questions/48h definition)."
        )
        dtarget = daily_chart["targets"][0]
        dtarget["url"] = add_query_param(f"{PROXY}{viral_mobile}", "_tzdates", "date")
        dtarget["root_selector"] = "activationDaily"
        chart = panel_by_title(dash, "Activation (signup → activated, macOS)")
        chart["title"] = "Activation (signup → activated)  ·  ${d_act}"
        target = chart["targets"][0]
        target["url"] = add_query_param(f"{PROXY}{viral_mobile}", "_tzdates", "date")
        target["root_selector"] = "activation"
        target["columns"] = [
            {"selector": "date", "text": "time", "type": "timestamp", "timestampFormat": RFC3339},
            {"selector": "signups", "text": "Signups", "type": "number"},
            {"selector": "activated", "text": "Activated", "type": "number"},
            {"selector": "rate", "text": "Rate", "type": "number"},
        ]
        chart["description"] = ("First-seen mobile users creating a Memory within 7 days "
                                "(PostHog telemetry; mobile does not emit Sign In Completed).")

    prune_vars_and_titles(dash)
    reflow(dash)
    return finish(dash, f"omi-tv-{scope}", f"Omi TV — {label}")


def main() -> None:
    base = json.loads(BASE_PATH.read_text(encoding="utf-8"))
    if not any(base_title(p) == RELEASES_CHART_TITLE for p in base["panels"]):
        base["panels"].append(releases_chart_panel(991))
    apply_tzdates(base)
    set_kfactor_tile_description(base, "all platforms")
    apply_platform(base, "all")
    # The two Firestore-backed activation panels are macOS-scoped by
    # definition; their delta var compares macOS activation to stay coherent.
    retarget_var(base, "d_act", path=set_url_param(VIRAL_PATH, "platform", "macos"))
    finish(base, "omi-tv", "Omi TV")

    macos = build_platform_board(base, "macos")
    mobile = build_platform_board(base, "mobile")

    BASE_PATH.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
    for dash, name in [(macos, "omi-tv-macos.json"), (mobile, "omi-tv-mobile.json")]:
        (DASH_DIR / name).write_text(json.dumps(dash, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(dash['panels'])} panels, "
              f"{len(dash['templating']['list'])} vars")
    print(f"updated omi-tv.json: {len(base['panels'])} panels (NYC tz + _tzdates + platform=all + links)")


if __name__ == "__main__":
    main()
