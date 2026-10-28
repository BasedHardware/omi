"""Static contract: Cloud Monitoring PromQL targets must carry a sibling query object.

Grafana 13's cloud-monitoring backend runs `migrateRequest` before dispatch. A target
with no `metricQuery`, `timeSeriesQuery`, `timeSeriesList` or `sloQuery` key is
treated as a legacy metric query and its JSON is rewritten without `promQLQuery`;
the restored `queryType: promQL` then dereferences nil parameters and the whole
/api/ds/query batch returns 500 (pkg/tsdb/cloud-monitoring/promql_query.go). Queries
built in the Grafana editor always include `timeSeriesList`, so only hand-written
provisioned JSON hits this. Every PromQL target here keeps a `timeSeriesList` stub.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOTS = [
    REPO / "backend/charts/monitoring/dashboards",
    REPO / "backend/charts/monitoring/alerts",
    REPO / "web/admin/grafana/dashboards",
]
SIBLINGS = ("metricQuery", "timeSeriesQuery", "timeSeriesList", "sloQuery")


def promql_targets(node, path=""):
    if isinstance(node, dict):
        if node.get("queryType") == "promQL" and "promQLQuery" in node:
            yield path, node
        for key, value in node.items():
            yield from promql_targets(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from promql_targets(value, f"{path}/{index}")


def test_cloud_monitoring_promql_targets_have_sibling_query_object():
    files = [p for root in ROOTS if root.exists() for p in sorted(root.rglob("*.json"))]
    assert files
    missing = [
        f"{file.relative_to(REPO)}:{path}"
        for file in files
        for path, target in promql_targets(json.loads(file.read_text()))
        if not any(key in target for key in SIBLINGS)
    ]
    assert not missing, "add a timeSeriesList stub beside promQLQuery:\n" + "\n".join(missing)
