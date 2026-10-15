"""Direction A: core stat + time series only; Infinity is the sole external plugin.

Each tile uses independent value, delta, split, state and trend panels, so the
platform counts remain readable without shrinking the hero value. This avoids
HTML sanitization changes or an additional panel plugin on Grafana 13.1.3.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DS = {"type": "yesoreyeram-infinity-datasource", "uid": "omi-admin-api"}
URL = "http://127.0.0.1:8899/api/omi/stats/wall"
# Hero first in each column. The lower rows are supporting diagnostics.
COLUMNS = [
    ("Growth", ["growth.wau", "growth.true_new_7d", "engagement.dau", "engagement.mau"]),
    ("Activation", ["activation.rate", "activation.capture_week1_share", "engagement.saved_creators", "engagement.assistant_success", "revenue.activated_paid_30d"]),
    ("Retention", ["retention.if_activated", "retention.recovery", "retention.day1_return", "retention.established_week"]),
    ("Revenue", ["revenue.arpmau", "revenue.mrr", "revenue.hardware_usd_week", "revenue.plan_prepay_usd_week", "revenue.payer_churn", "cost.gross_margin_pct"]),
    ("Health", ["health.crash_free", "cost.net_day", "cost.per_mau_month", "health.thumbs_positive"]),
]
LABELS = {
    "growth.wau": "WAU", "growth.true_new_7d": "Interim true-new · 180d", "engagement.dau": "DAU", "engagement.mau": "MAU",
    "activation.rate": "Activation · ≥2 days", "activation.capture_week1_share": "Capture in week 1", "engagement.saved_creators": "Saved creators", "engagement.assistant_success": "Assistant success · macOS",
    "revenue.activated_paid_30d": "Activated → paid · 30d", "retention.if_activated": "Retained if activated", "retention.recovery": "Recovery", "retention.day1_return": "Day-1 return", "retention.established_week": "Established retention",
    "revenue.arpmau": "ARPMAU", "revenue.mrr": "Omi-plan MRR · live book", "revenue.hardware_usd_week": "Hardware sales · UTC week", "revenue.hardware_units_week": "Hardware units · UTC week", "revenue.plan_prepay_usd_week": "Plan prepay sold · cash", "revenue.payer_churn": "Payer churn · month", "cost.gross_margin_pct": "Gross margin · goal 60%",
    "health.crash_free": "Crash-free · macOS", "cost.net_day": "Net cost · D−2", "cost.per_mau_month": "Cost / MAU · settled 30d", "health.thumbs_positive": "Positive answers · macOS",
}
RATE_IDS = {"activation.rate", "activation.capture_week1_share", "retention.if_activated", "retention.recovery", "retention.day1_return", "retention.established_week", "revenue.activated_paid_30d", "revenue.payer_churn", "cost.gross_margin_pct", "health.crash_free", "health.thumbs_positive"}


def target(key, columns, series=False):
    return {"refId": "A", "datasource": DS, "type": "json", "source": "url", "format": "timeseries" if series else "table", "parser": "backend",
            "url": URL, "url_options": {"method": "GET"}, "root_selector": ("series." if series else "tiles.") + key,
            "columns": [{"selector": selector, "text": name, "type": kind} for selector, name, kind in columns]}


def build_wall_board():
    panels = []
    def add(panel):
        panel["id"] = len(panels) + 1
        panels.append(panel)
    x = 0
    for col, (heading, ids) in enumerate(COLUMNS):
        w = 5 if col < 4 else 4
        add({"type": "text", "title": "", "gridPos": {"x": x, "y": 0, "w": w, "h": 2}, "options": {"mode": "markdown", "content": f"## {heading}"}})
        for row, mid in enumerate(ids):
            y = 2 + row * 10
            key = mid.replace(".", "_")
            unit = "percent" if mid in RATE_IDS else "currencyUSD" if mid.startswith("cost.") or mid.startswith("revenue.") and mid != "revenue.hardware_units_week" else "short"
            scope = "Entry" if mid in RATE_IDS and mid.startswith(("activation.", "retention.")) and mid != "retention.established_week" else "All" if mid.startswith(("revenue.", "cost.")) else "Active"
            common = {"datasource": DS, "description": f"{mid} · qualified-v2-2026-10-15. UTC completed buckets only. Rates show numerator/denominator by frozen entry cohort; counts use primary qualified platform. Monetary platform attribution unavailable. See diagnostics below for reason and source timestamps."}
            def stat(title, offset, height, columns, size, defaults=None, overrides=None):
                return {**common, "type": "stat", "title": title, "gridPos": {"x": x, "y": y+offset, "w": w, "h": height},
                        "transparent": offset != 0, "targets": [target(key, columns)], "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "#9ca3af"}, "noValue":"—", "mappings": [{"type": "special", "options": {"match": "null", "result": {"text": "—", "color": "#6b7280"}}}], **(defaults or {})}, "overrides": overrides or []},
                        "options": {"reduceOptions": {"values": False, "calcs": ["lastNotNull"], "fields": "/.*/"}, "textMode": "value", "orientation": "horizontal", "justifyMode": "center", "colorMode": "value", "graphMode": "none", "text": {"valueSize": size, "titleSize": 11}}}
            # Single value, grey when partial/stale; the footer exposes its status.
            headline=stat(f"{LABELS[mid]}  [{scope}]",0,3,[("value", "Value", "number")],40,{"unit":unit,"decimals":1})
            config=target(key,[("value","Mapping value","number"),("display","Mapping text","string"),("valueColor","Mapping color","string")])
            config["refId"]="B"
            headline["targets"].append(config)
            headline["transformations"]=[{"id":"configFromData","options":{"configRefId":"B","applyTo":{"id":"byName","options":"Value"},"mappings":[{"fieldName":"Mapping value","handlerKey":"mappings.value"},{"fieldName":"Mapping text","handlerKey":"mappings.text"},{"fieldName":"Mapping color","handlerKey":"mappings.color"}]}}]
            add(headline)
            low_better = mid in {"cost.net_day", "cost.per_mau_month", "revenue.payer_churn"}
            steps = [{"color": "#60a5fa" if low_better else "#fb923c", "value": None}, {"color":"#9ca3af","value":0}, {"color":"#fb923c" if low_better else "#60a5fa","value":0.000001}]
            delta_panel=stat("",3,1,[("delta", "vs prior complete", "number")],14,{"unit":"percent","decimals":1,"color":{"mode":"thresholds"},"thresholds":{"mode":"absolute","steps":steps}})
            delta_panel["options"]["textMode"]="value_and_name"
            add(delta_panel)
            split_panel=stat("",4,2,[("splitRow","macOS / Mobile / Other","string")],12)
            split_panel["options"]["textMode"]="value"
            add(split_panel)
            add(stat("",6,1,[("footnote","Coverage","string")],11))
            add({**common,"type":"timeseries","title":"","gridPos":{"x":x,"y":y+7,"w":w,"h":2},"targets":[target(key,[("date","Date","timestamp"),("value","Complete periods","number")],True)],
                 "transparent":True,"timeFrom": "60d" if mid=="engagement.mau" else "6d" if mid.startswith("engagement.") else "42d", "hideTimeOverride":True, "timeShift":"37d" if mid in {"retention.if_activated","retention.recovery"} else "7d" if mid.startswith("activation.") else "2d" if mid=="retention.day1_return" else None, "fieldConfig":{"defaults":{"unit":unit,"color":{"mode":"fixed","fixedColor":"#60a5fa"},"custom":{"drawStyle":"line","lineWidth":2,"fillOpacity":8,"axisPlacement":"hidden","showPoints":"never","spanNulls":False}},"overrides":[]},"options":{"legend":{"showLegend":False},"tooltip":{"mode":"single"}}})
        x += w
    # Full metadata table keeps operational diagnostics below the wall.
    add({"type":"table","title":"Diagnostics · definitions, coverage and source watermarks", "datasource":DS,
         "gridPos":{"x":0,"y":64,"w":24,"h":12},"targets":[{"refId":"A","datasource":DS,"type":"json","source":"url","format":"table","parser":"backend","url":URL,"root_selector":"metrics","columns":[{"selector":f,"text":f,"type":"string"} for f in ['id','status','reason','numerator','denominator','windowStart','windowEnd','dataThrough','sourceRefreshedAt','definitionVersion']]}],"options":{"showHeader":True}})
    return {"uid":"omi-tv-v2","title":"Omi TV v2 · Direction A","schemaVersion":39,"version":1,"timezone":"utc","refresh":"15m","editable":True,"tags":["omi-tv","v2"],"time":{"from":"now-180d","to":"now/d"},"templating":{"list":[]},"annotations":{"list":[]},"panels":panels,
            "description":"Direction A. Complete UTC periods; proxy/partial/null coverage stays visible. Blue better, orange worse, grey flat. Monetary splits unavailable. Legacy boards are unchanged.","links":[]}


def write_wall_board():
    (HERE / 'dashboards/omi-tv-v2.json').write_text(json.dumps(build_wall_board(),indent=2)+'\n')


if __name__ == '__main__':
    write_wall_board()
