"""Static contract for Grafana rules where an empty error-count series is healthy."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / "backend/charts/monitoring"
ERROR_COUNT_RULES = {
    "cew4j7ruiik1sd",  # Backend 4XX
    "cew4jcnpa68sga",  # Backend 5XX
    "cew97rzyegdtsa",  # Backend-sync 4XX
    "cew97uqu791q8a",  # Backend-sync 5XX
    "eew96lge97gg0e",  # Backend-integration 4XX
    "eew96o25qztvkf",  # Backend-integration 5XX
}


def _rules(path: Path) -> dict[str, dict]:
    return {rule["uid"]: rule for rule in json.loads(path.read_text(encoding="utf-8"))}


def test_stackdriver_error_count_rules_treat_no_data_as_zero_errors():
    """Grafana's Stackdriver empty result is healthy for these error counters."""
    rules = _rules(MONITORING / "alert-rules.json")

    assert ERROR_COUNT_RULES <= rules.keys()
    for uid in ERROR_COUNT_RULES:
        rule = rules[uid]
        assert rule["noDataState"] == "OK", rule["title"]
        query = rule["data"][0]["model"]
        assert query["datasource"]["type"] == "stackdriver"
        assert any("backend_request_count" in value for value in query["timeSeriesList"]["filters"])


def test_split_alert_exports_preserve_error_count_no_data_contract():
    """The deployable combined export and group exports must not drift."""
    combined = _rules(MONITORING / "alert-rules.json")
    split = {}
    for name in ("backend.json", "backend-sync.json", "backend-integration.json"):
        split.update(_rules(MONITORING / "alerts" / name))

    assert ERROR_COUNT_RULES <= split.keys()
    for uid in ERROR_COUNT_RULES:
        assert combined[uid]["noDataState"] == split[uid]["noDataState"] == "OK"


def test_llm_gateway_alerts_cover_client_black_holes_and_ready_endpoints():
    split = _rules(MONITORING / "alerts" / "resilience.json")
    combined = _rules(MONITORING / "alert-rules.json")
    expected = {"omi-llm-gateway-client-reachability", "omi-llm-gateway-no-ready-endpoints"}

    assert expected <= split.keys()
    assert expected <= combined.keys()
    reachability_expr = split["omi-llm-gateway-client-reachability"]["data"][0]["model"]["expr"]
    assert "llm_gateway_chat_extraction_requests_total" in reachability_expr
    assert "llm_gateway_circuit_open" in reachability_expr
    assert 'outcome="success"' in reachability_expr
    assert "llm_gateway_client_first_byte_seconds_bucket" in reachability_expr
    endpoint_rule = split["omi-llm-gateway-no-ready-endpoints"]
    assert endpoint_rule["noDataState"] == "Alerting"
    assert "kube_endpoint_address_available" in endpoint_rule["data"][0]["model"]["expr"]
