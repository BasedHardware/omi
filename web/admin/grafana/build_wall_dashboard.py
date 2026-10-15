"""Direction A: one native Canvas card per metric; Infinity is the sole external plugin.

Each tile is a single native Canvas icon containing a sanitized, data-only SVG.
This keeps every part inside one card without another panel plugin or enabling
unsanitized HTML on Grafana 13.1.3.
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
# One native Canvas panel is one complete visual card. SVG is data-only and
# passes through Canvas's built-in SanitizedSVG icon renderer. No HTML setting,
# external resource, custom JavaScript, or additional panel plugin is required.
HERO_IDS = {"growth.wau", "activation.rate", "retention.if_activated", "revenue.arpmau", "health.crash_free"}
SMALL_IDS = {"revenue.plan_prepay_usd_week", "revenue.payer_churn", "cost.gross_margin_pct"}


def geometry(mid):
    if mid in SMALL_IDS:
        return 3, 102
    if mid == "revenue.arpmau":
        return 5, 174
    if mid in HERO_IDS:
        return 6, 210
    return 4, 144


def build_wall_board():
    panels = []
    x = 0
    for col, (heading, ids) in enumerate(COLUMNS):
        width = 5 if col < 4 else 4
        panels.append({"id":len(panels)+1,"type":"text","title":"","transparent":True,
                       "gridPos":{"x":x,"y":0,"w":width,"h":2},
                       "options":{"mode":"markdown","content":f"## {heading}"}})
        y = 2
        for mid in ids:
            height, design_height = geometry(mid)
            key = mid.replace('.', '_')
            panels.append({
                "id":len(panels)+1,"type":"canvas","title":"","transparent":True,
                "datasource":DS,"gridPos":{"x":x,"y":y,"w":width,"h":height},
                "description":f"{mid}. Complete UTC periods. Count splits use primary qualified platform; first-seen cohorts use entry platform. Percentage-point cohort deltas. Capture share is saved-own-capture evidence, not device connection or recording intent. Proxy definitions and full coverage details are in diagnostics.",
                "targets":[{"refId":"A","datasource":DS,"type":"json","source":"url","format":"table","parser":"backend","url":URL,
                            "url_options":{"method":"GET"},"root_selector":f"tiles.{key}",
                            "columns":[{"selector":"cardSvg","text":"Card","type":"string"}]}],
                "fieldConfig":{"defaults":{},"overrides":[]},
                "options":{"inlineEditing":False,"panZoom":False,"zoomToContent":True,"showAdvancedTypes":False,"tooltip":{"mode":"none"},
                           "root":{"name":"Metric card","type":"frame","elements":[
                               {"name":mid,"type":"icon","placement":{"left":0,"top":0,"right":0,"bottom":0},
                                "constraint":{"horizontal":"leftright","vertical":"topbottom"},
                                "background":{"color":{"fixed":"transparent"}},
                                "config":{"path":{"mode":"field","field":"Card"},"fill":{"fixed":"transparent"}}}
                           ]}}
            })
            y += height
        x += width
    # Grafana compacts empty grid rows on load. A transparent spacer preserves
    # the gap so diagnostics begin below both verified wall viewports.
    wall_end = max(2 + sum(geometry(mid)[0] for mid in ids) for _, ids in COLUMNS)
    panels.append({"id":len(panels)+1,"type":"text","title":"","transparent":True,
                   "gridPos":{"x":0,"y":wall_end,"w":24,"h":4},
                   "options":{"mode":"markdown","content":""}})
    panels.append({"id":len(panels)+1,"type":"table","title":"Diagnostics · definitions and coverage","datasource":DS,
                   "gridPos":{"x":0,"y":wall_end+4,"w":24,"h":12},
                   "targets":[{"refId":"A","datasource":DS,"type":"json","source":"url","format":"table","parser":"backend","url":URL,"url_options":{"method":"GET"},"root_selector":"metrics",
                               "columns":[{"selector":f,"text":f,"type":"number" if f in {"numerator", "denominator"} else "string"} for f in ['id','status','reason','numerator','denominator','windowStart','windowEnd','dataThrough','sourceRefreshedAt','definitionVersion']]}],
                   "options":{"showHeader":True}})
    return {"uid":"omi-tv-v2","title":"Omi TV v2 · Direction A","schemaVersion":39,"version":1,"timezone":"utc","refresh":"30s","editable":True,
            "tags":["omi-tv","v2"],"time":{"from":"now-180d","to":"now/d"},"templating":{"list":[]},"annotations":{"list":[]},"panels":panels,
            "description":"Five story columns. Native Canvas cards include label, scope, value, delta, platform split, complete-period trend and human coverage copy. Diagnostics below the wall. Legacy boards are unchanged.","links":[]}


def write_wall_board():
    (HERE / 'dashboards/omi-tv-v2.json').write_text(json.dumps(build_wall_board(),indent=2)+'\n')


if __name__ == '__main__':
    write_wall_board()
