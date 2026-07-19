"""Static contracts for Grafana alert rules."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / "backend/charts/monitoring"
ALERT_SOURCES = MONITORING / "alerts"
ERROR_COUNT_RULES = {
    "cew4j7ruiik1sd",  # Backend 4XX
    "cew4jcnpa68sga",  # Backend 5XX
    "cew97rzyegdtsa",  # Backend-sync 4XX
    "cew97uqu791q8a",  # Backend-sync 5XX
    "eew96lge97gg0e",  # Backend-integration 4XX
    "eew96o25qztvkf",  # Backend-integration 5XX
}
REQUIRED_HUMAN_ANNOTATIONS = {
    "summary",
    "user_impact",
    "scope",
    "verification",
    "safe_next_action",
}
REQUIRED_IDENTITY_LABELS = {"alert_identity", "component", "impact"}
IMPACT_TIERS = {"infrastructure", "product", "user-experience"}
UNSAFE_ANNOTATION_MARKERS = ("{{", "}}", "$values", "traceback", "stack trace")
PARAKEET_STREAM_CAPACITY_RULES = {
    "omi-parakeet-stream-capacity-warning": ("warning", 15),
    "omi-parakeet-stream-capacity-critical": ("critical", 20),
}
PARAKEET_STREAMS_PER_READY_REPLICA = (
    'sum(parakeet_active_streams{container="parakeet", namespace="prod-omi-backend"}) '
    '/ clamp_min(sum(kube_deployment_status_replicas_ready{deployment="prod-omi-parakeet", '
    'namespace="prod-omi-backend"}), 1)'
)


def _rules(path: Path) -> dict[str, dict]:
    rules = json.loads(path.read_text(encoding="utf-8"))
    by_uid = {rule["uid"]: rule for rule in rules}
    assert len(by_uid) == len(rules), f"duplicate Grafana alert UID in {path}"
    return by_uid


def _split_rules() -> dict[str, dict]:
    rules = {}
    for path in sorted(ALERT_SOURCES.glob("*.json")):
        for uid, rule in _rules(path).items():
            assert uid not in rules, f"duplicate Grafana alert UID across split exports: {uid}"
            rules[uid] = rule
    return rules


def _all_rule_exports() -> dict[str, dict[str, dict]]:
    return {
        "combined": _rules(MONITORING / "alert-rules.json"),
        "split": _split_rules(),
    }


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
    split = _split_rules()

    assert ERROR_COUNT_RULES <= split.keys()
    for uid in ERROR_COUNT_RULES:
        assert combined[uid]["noDataState"] == split[uid]["noDataState"] == "OK"


def test_combined_alert_export_matches_every_split_source_rule():
    """The combined Grafana import is an exact UID-indexed copy of split sources."""
    combined, split = _all_rule_exports().values()

    assert combined.keys() == split.keys()
    for uid in combined:
        assert combined[uid] == split[uid], uid


def test_grafana_alert_rules_have_safe_human_impact_metadata():
    """Every operator notification explains human impact without raw error output."""
    for export_name, rules in _all_rule_exports().items():
        for uid, rule in rules.items():
            annotations = rule["annotations"]
            labels = rule["labels"]

            assert REQUIRED_HUMAN_ANNOTATIONS <= annotations.keys(), f"{export_name}:{uid}"
            assert REQUIRED_IDENTITY_LABELS <= labels.keys(), f"{export_name}:{uid}"
            assert labels["alert_identity"] == uid, f"{export_name}:{uid}"
            assert labels["impact"] in IMPACT_TIERS, f"{export_name}:{uid}"

            for key in REQUIRED_HUMAN_ANNOTATIONS:
                value = annotations[key]
                assert isinstance(value, str) and value.strip(), f"{export_name}:{uid}:{key}"
                value_lower = value.lower()
                assert not any(
                    marker in value_lower for marker in UNSAFE_ANNOTATION_MARKERS
                ), f"{export_name}:{uid}:{key} exposes raw alert output"

            assert isinstance(labels["component"], str) and labels["component"].strip(), f"{export_name}:{uid}"


def test_parakeet_stream_capacity_alerts_preserve_per_ready_replica_headroom():
    """Capacity alerts use the active-stream gauge, normalized by ready replicas."""
    rules = _rules(ALERT_SOURCES / "parakeet.json")

    assert PARAKEET_STREAM_CAPACITY_RULES.keys() <= rules.keys()
    for uid, (severity, threshold) in PARAKEET_STREAM_CAPACITY_RULES.items():
        rule = rules[uid]
        assert rule["labels"]["severity"] == severity
        assert rule["noDataState"] == "OK"
        assert rule["data"][0]["model"]["expr"] == PARAKEET_STREAMS_PER_READY_REPLICA
        assert rule["data"][2]["model"]["conditions"][0]["evaluator"]["params"] == [threshold]


def test_pusher_degradation_uses_listener_emitter_metrics():
    """The reconnect degradation gauge is emitted by backend-listen, not Pusher."""
    rule = _rules(ALERT_SOURCES / "pusher.json")["bfobs1pusherdeg01"]
    expr = rule["data"][0]["model"]["expr"]

    assert 'pusher_sessions_degraded{job="backend-listen-metrics"}' in expr
    assert 'backend_listen_active_ws_connections{job="backend-listen-metrics"}' in expr
    assert 'job="pusher-metrics"' not in expr

    pusher_5xx = _rules(ALERT_SOURCES / "pusher.json")["aew926uoh6o00c"]
    assert pusher_5xx["noDataState"] == "OK"
    assert "or vector(0)" in pusher_5xx["data"][0]["model"]["expr"]


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
