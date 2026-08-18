#!/usr/bin/env python3
"""Derive the platform dashboards from the checked-in omi-tv board.

Reads dashboards/omi-tv.json (the "All platforms" board, source of truth),
then:
  1. In place: pins timezone to America/New_York, routes daily/weekly/monthly
     date columns through the proxy's `_tzdates` rewrite (so each bucket
     renders on its labeled calendar day instead of shifting 8 pm earlier),
     and adds the All / macOS / Mobile switcher links.
  2. Writes dashboards/omi-tv-macos.json — macOS-only view: platform-native
     panels kept, cross-platform panels re-pointed at the desktop series of
     /api/omi/stats/profitability, unplittable panels dropped.
  3. Writes dashboards/omi-tv-mobile.json — the honestly-available mobile
     view (signups, revenue, cost, conversion from profitability; mobile
     DAU/retention are not instrumented and say so).

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
PROXY = "http://127.0.0.1:8899"
RFC3339 = "2006-01-02T15:04:05Z07:00"
DAY_FORMATS = {"2006-01-02", "2006-01"}

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


def compare_url(path: str, root: str, fields: str, agg: str, window: int, label: str = "") -> str:
    params = {"path": path, "root": root, "fields": fields, "agg": agg, "window": window}
    if label:
        params["label"] = label
    return f"{PROXY}/compare?" + urllib.parse.urlencode(params)


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


def finish(dash, uid: str, title: str) -> dict:
    dash["uid"] = uid
    dash["title"] = title
    dash["links"] = LINKS
    dash["timezone"] = "America/New_York"
    dash.pop("id", None)
    dash.pop("version", None)
    return dash


def build_macos(base) -> dict:
    dash = copy.deepcopy(base)
    drop_panels(dash, {
        "Users → 1M goal", "ARR", "Active subscriptions", "Trialing",
        "Trials in pipeline", "Conversations", "MRR by product", "MRR over time",
        "New subscriptions / month", "Message ratings",
        "Infra cost by service — last 30 days",
    })

    ticker = panel_by_title(dash, "Total users")
    ticker["title"] = "macOS users"
    ticker["gridPos"]["h"] = 6
    set_stat_query(ticker, PROFIT_PATH, "summary", "totalUsersDesktop", "macOS users")

    mrr = panel_by_title(dash, "MRR")
    mrr["title"] = "MRR (macOS)"
    set_stat_query(mrr, PROFIT_PATH, "summary", "mrrDesktop", "MRR")

    signups = panel_by_title(dash, "Signups — last 7 days")
    signups["title"] = "macOS signups — last 7 days"
    set_compare(signups["targets"][0], "url", path=PROFIT_PATH, root="users", fields="desktop")

    daily = panel_by_title(dash, "Daily new users")
    platform_series(daily, PROFIT_PATH, "users", "desktop", "New users")
    retarget_var(dash, "d_daily", path=PROFIT_PATH, root="users", fields="desktop")

    cumulative = panel_by_title(dash, "Cumulative users")
    cumulative["title"] = "Cumulative users (macOS)  ·  ${d_cum}"
    platform_series(cumulative, PROFIT_PATH, "cumulativeUsers", "desktop", "Total users")
    retarget_var(dash, "d_cum", path=PROFIT_PATH, root="users", fields="desktop")

    for title, new_title, series in [
        ("New users / day by platform", "New users / day (desktop)  ·  ${d_pusers}", "Desktop"),
        ("Revenue / day by platform (est.)", "Revenue / day (desktop, est.)  ·  ${d_prev}", "Desktop"),
        ("Infra cost / day by platform", "Infra cost / day (desktop)  ·  ${d_cost}", "Desktop"),
        ("Cost / user / day", "Cost / user / day (desktop)  ·  ${d_cpu}", "Desktop $/user"),
        ("Free → paid conversion", "Free → paid conversion (desktop)  ·  ${d_conv}", "Desktop"),
    ]:
        panel = panel_by_title(dash, title)
        panel["title"] = new_title
        keep_series(panel, {series})
    for var in ["d_pusers", "d_prev", "d_cost", "d_cpu", "d_conv"]:
        retarget_var(dash, var, fields="desktop")

    prune_vars_and_titles(dash)
    reflow(dash)
    return finish(dash, "omi-tv-macos", "Omi TV — macOS")


def build_mobile(base) -> dict:
    dash = copy.deepcopy(base)

    ticker = panel_by_title(dash, "Total users")
    ticker["title"] = "Mobile users"
    set_stat_query(ticker, PROFIT_PATH, "summary", "totalUsersMobile", "Mobile users")

    mrr = panel_by_title(dash, "MRR")
    mrr["title"] = "MRR (mobile)"
    set_stat_query(mrr, PROFIT_PATH, "summary", "mrrMobile", "MRR")

    signups = panel_by_title(dash, "Signups — last 7 days")
    signups["title"] = "Mobile signups — last 7 days"
    set_compare(signups["targets"][0], "url", path=PROFIT_PATH, root="users", fields="mobile")

    cumulative = panel_by_title(dash, "Cumulative users")
    cumulative["title"] = "Cumulative users (mobile)  ·  ${d_cum}"
    platform_series(cumulative, PROFIT_PATH, "cumulativeUsers", "mobile", "Total users")
    retarget_var(dash, "d_cum", path=PROFIT_PATH, root="users", fields="mobile")

    daily = panel_by_title(dash, "Daily new users")
    daily["title"] = "Daily new users  ·  ${d_daily}"
    platform_series(daily, PROFIT_PATH, "users", "mobile", "New users")
    retarget_var(dash, "d_daily", path=PROFIT_PATH, root="users", fields="mobile")

    charts = []
    for title, new_title, series in [
        ("New users / day by platform", "New users / day (mobile)  ·  ${d_pusers}", "Mobile"),
        ("Revenue / day by platform (est.)", "Revenue / day (mobile, est.)  ·  ${d_prev}", "Mobile"),
        ("Infra cost / day by platform", "Infra cost / day (mobile)  ·  ${d_cost}", "Mobile"),
        ("Cost / user / day", "Cost / user / day (mobile)  ·  ${d_cpu}", "Mobile $/user"),
        ("Free → paid conversion", "Free → paid conversion (mobile)  ·  ${d_conv}", "Mobile"),
    ]:
        panel = panel_by_title(dash, title)
        panel["title"] = new_title
        keep_series(panel, {series})
        charts.append(panel)
    for var in ["d_pusers", "d_prev", "d_cost", "d_cpu", "d_conv"]:
        retarget_var(dash, var, fields="mobile")

    note = {
        "id": 999,
        "type": "text",
        "title": "",
        "transparent": True,
        "gridPos": {"x": 0, "y": 0, "w": 24, "h": 3},
        "options": {
            "mode": "markdown",
            "content": "**Mobile engagement (DAU/WAU, retention, activation) is not instrumented yet** — "
                       "PostHog only covers desktop and mobile Mixpanel is dead. These panels come from "
                       "Firebase signups split by platform token, Stripe MRR attribution, and infra cost shares.",
        },
        "targets": [],
    }

    keep = [ticker, mrr, signups, daily, charts[1], charts[2], charts[3], charts[4],
            cumulative, note]
    for stat_panel in (ticker, mrr, signups):
        stat_panel["gridPos"].update({"w": 8, "h": 5})
    dash["panels"] = keep
    prune_vars_and_titles(dash)
    reflow(dash)
    return finish(dash, "omi-tv-mobile", "Omi TV — Mobile")


def main() -> None:
    base = json.loads(BASE_PATH.read_text(encoding="utf-8"))
    apply_tzdates(base)
    finish(base, "omi-tv", "Omi TV")

    macos = build_macos(base)
    mobile = build_mobile(base)

    BASE_PATH.write_text(json.dumps(base, indent=1) + "\n", encoding="utf-8")
    for dash, name in [(macos, "omi-tv-macos.json"), (mobile, "omi-tv-mobile.json")]:
        (DASH_DIR / name).write_text(json.dumps(dash, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(dash['panels'])} panels, "
              f"{len(dash['templating']['list'])} vars")
    print(f"updated omi-tv.json: {len(base['panels'])} panels (NYC tz + _tzdates + links)")


if __name__ == "__main__":
    main()
