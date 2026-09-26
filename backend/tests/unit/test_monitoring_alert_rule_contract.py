"""Static contracts for Grafana alert rules."""

import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
MONITORING = REPO / "backend/charts/monitoring"
ALERT_SOURCES = MONITORING / "alerts"
PROD_STACK_VALUES = MONITORING / "kube-prometheus-stack/prod_omi_monitoring_values.yaml"
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
PARAKEET_STREAM_CAPACITY_RUNBOOK = "backend/docs/runbooks/parakeet-stream-capacity.md"
PARAKEET_CAPACITY_DASHBOARD = MONITORING / "dashboards/gke/parakeet-asr-monitoring.json"
LIVE_TRANSCRIPTION_FAILURE_RULE = "omi-journey-live-transcription-fail"
LIVE_TRANSCRIPTION_FAILURE_EXPR = 'sum(increase(omi_live_stt_accepted_total[30m]))'
PARAKEET_READY_POD_NO_SUCCESS_RULE = "omi-parakeet-ready-pod-no-success"
PARAKEET_READY_POD_NO_SUCCESS_EXPR = (
    '((sum by (pod) (increase(parakeet_requests_total{container="parakeet",namespace="prod-omi-backend",'
    'status="error"}[5m])) >= 10) unless on (pod) (sum by (pod) '
    '(increase(parakeet_requests_total{container="parakeet",namespace="prod-omi-backend",'
    'status="success"}[5m])) > 0)) and on (pod) (max by (pod) '
    '(kube_pod_status_ready{namespace="prod-omi-backend",condition="true",'
    'pod=~"prod-omi-parakeet-.*"}) == 1)'
)
PARAKEET_FATAL_CUDA_RULE = "omi-parakeet-fatal-cuda"
PARAKEET_FATAL_CUDA_EXPR = (
    'sum by (pod) (increase(parakeet_gpu_fatal_errors_total{container="parakeet",' 'namespace="prod-omi-backend"}[5m]))'
)


# Grafana rejects a rule whose UID exceeds 40 characters with
# "UID is longer than 40 symbols", at create time. A repo export is a mirror, so
# an over-long UID costs nothing until someone tries to provision it -- and then
# the rule that was written, reviewed, and merged simply cannot be made live.
# Two rules were already past the limit before this was pinned.
GRAFANA_MAX_UID_LENGTH = 40


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


COUNTER_FN_ON_GAUGE_DEBT = {
    # Pre-existing rules that apply rate() to a stackdriver_ GAUGE. The exporter
    # publishes Cloud Monitoring DELTA metrics as gauges whose value is the count
    # for one alignment window, so rate() over them is not a per-second rate.
    #
    # Measured 2026-08-25 on the backend-listen LB: rate(...[5m]) read 1.82 where
    # the correct avg_over_time(avg(...))/60 read 0.63 req/sec -- wrong by ~3x, and
    # the error scales with the series' volatility rather than being a fixed factor.
    #
    # These are NOT being rewritten here. Their thresholds were calibrated
    # empirically against the wrong values, so a mechanical rewrite would silently
    # re-tune 14 rules, 6 of which page. That needs its own change with a human
    # deciding each threshold. This set is a RATCHET: it may shrink, never grow.
    "cew923rcn3ncwb",
    "aew926uoh6o00c",  # critical, pages
    "dew91uem0dnggb",
    "dew9ala448r9cc",
    "few9anlyv16v4a",  # critical, pages
    "bew9aeqgx2w3kf",
    "eew9ai0vlsyrke",
    "dfpgfzd3t1m9sf",  # critical, pages
    "efpossz9hmsqod",  # critical, pages
    "efpgg049laqyof",
    "efpgg1kfjglj4d",
    "bevzeigrns5xca",
    "cevzen5b94z5sb",  # critical, pages
    "tz_backend_listen_lb_zero",  # critical, pages
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


def test_alert_uids_are_short_enough_for_grafana_to_accept():
    """Every exported rule must be creatable; Grafana caps UIDs at 40 characters."""
    for export_name, rules in _all_rule_exports().items():
        over = {uid: len(uid) for uid in rules if len(uid) > GRAFANA_MAX_UID_LENGTH}
        assert not over, f"{export_name}: Grafana will reject these UIDs at create time: {over}"


def test_managed_gke_disables_unavailable_control_plane_scrapes_and_alerts():
    """Managed GKE must not page on control-plane targets it cannot expose.

    kube-prometheus-stack gates each control-plane PrometheusRule group on the
    component ``enabled`` flag, so ``enabled: false`` alone suppresses the
    ``*Down`` alerts. Do not also set ``defaultRules.disabled`` — that would
    keep the alert off after a future self-managed control-plane re-enable.
    """
    values = yaml.safe_load(PROD_STACK_VALUES.read_text(encoding="utf-8"))

    for component in ("kubeProxy", "kubeScheduler", "kubeControllerManager"):
        assert values[component]["enabled"] is False

    disabled = (values.get("defaultRules") or {}).get("disabled") or {}
    for alert in ("KubeProxyDown", "KubeSchedulerDown", "KubeControllerManagerDown"):
        assert alert not in disabled


def test_combined_alert_export_matches_every_split_source_rule():
    """The combined Grafana import is an exact UID-indexed copy of split sources."""
    combined, split = _all_rule_exports().values()

    assert combined.keys() == split.keys()
    for uid in combined:
        assert combined[uid] == split[uid], uid


def test_durable_queue_oldest_ready_alert_pages_on_age_or_absent_gauge():
    for rules in _all_rule_exports().values():
        rule = rules['omi-queue-oldest-ready']
        assert len(rule['uid']) < 40
        expr = rule['data'][0]['model']['expr']
        assert 'omi_queue_oldest_ready_age_seconds' in expr
        assert 'absent(omi_queue_oldest_ready_age_seconds)' in expr
        assert '21600' in expr
        assert rule['noDataState'] == 'Alerting'
        assert rule['labels']['alert_identity'] == 'omi-queue-oldest-ready'


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


def test_parakeet_stream_capacity_alerts_link_the_matching_dashboard_and_runbook():
    """The alert, dashboard, and operator response use the same per-replica signal."""
    rules = _rules(ALERT_SOURCES / "parakeet.json")
    dashboard = json.loads(PARAKEET_CAPACITY_DASHBOARD.read_text(encoding="utf-8"))
    panel = next(panel for panel in dashboard["panels"] if panel["id"] == 3)
    runbook = (REPO / PARAKEET_STREAM_CAPACITY_RUNBOOK).read_text(encoding="utf-8")

    assert panel["title"] == "Streaming capacity per ready replica"
    assert panel["targets"][0]["expr"] == PARAKEET_STREAMS_PER_READY_REPLICA
    assert panel["fieldConfig"]["defaults"]["thresholds"]["steps"] == [
        {"color": "green", "value": 0},
        {"color": "yellow", "value": 15},
        {"color": "red", "value": 20},
    ]

    for uid, (severity, threshold) in PARAKEET_STREAM_CAPACITY_RULES.items():
        rule = rules[uid]
        assert rule["labels"]["severity"] == severity
        assert rule["annotations"]["__dashboardUid__"] == dashboard["uid"]
        assert rule["annotations"]["__panelId__"] == str(panel["id"])
        assert rule["annotations"]["runbook"] == PARAKEET_STREAM_CAPACITY_RUNBOOK
        assert f"{threshold} active streams per ready replica" in runbook

    assert PARAKEET_STREAMS_PER_READY_REPLICA in runbook


def test_parakeet_alerts_detect_fatal_cuda_and_ready_pod_black_holes():
    for rules in _all_rule_exports().values():
        no_success = rules[PARAKEET_READY_POD_NO_SUCCESS_RULE]
        assert no_success["data"][0]["model"]["expr"] == PARAKEET_READY_POD_NO_SUCCESS_EXPR
        assert no_success["noDataState"] == "OK"
        assert no_success["for"] == "2m"
        assert no_success["labels"]["severity"] == "critical"
        assert no_success["labels"]["impact"] == "user-experience"

        fatal_cuda = rules[PARAKEET_FATAL_CUDA_RULE]
        assert fatal_cuda["data"][0]["model"]["expr"] == PARAKEET_FATAL_CUDA_EXPR
        assert fatal_cuda["noDataState"] == "OK"
        assert fatal_cuda["for"] == "0s"
        assert fatal_cuda["labels"]["severity"] == "critical"
        assert fatal_cuda["labels"]["impact"] == "infrastructure"


def test_parakeet_dashboard_uses_application_request_status_labels():
    dashboard = json.loads(PARAKEET_CAPACITY_DASHBOARD.read_text(encoding="utf-8"))

    for panel_id in (1, 7):
        panel = next(panel for panel in dashboard["panels"] if panel["id"] == panel_id)
        expression = panel["targets"][0]["expr"]
        assert 'status="error"' in expression
        assert 'status=~"[45].."' not in expression


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


def test_llm_gateway_fallback_ticket_counts_only_successful_actual_failover():
    for rules in _all_rule_exports().values():
        expression = rules["bfobs1llmgfb01"]["data"][0]["model"]["expr"]
        assert 'llm_gateway_requests_total' in expression
        assert 'route_serving_class="actual_fallback"' in expression
        assert 'fallback_used="true"' in expression
        assert 'fallback_reason!="none"' in expression
        assert 'outcome="success"' in expression
        assert 'used_lkg' not in expression
        assert 'llm_gateway_chat_extraction_requests_total' not in expression


def test_live_transcription_alert_is_traffic_gated_and_ignores_idle_no_data():
    """The real-traffic alert must not page before any live sessions exist."""
    for rules in _all_rule_exports().values():
        rule = rules[LIVE_TRANSCRIPTION_FAILURE_RULE]
        assert rule["noDataState"] == "OK"
        assert rule["data"][0]["model"]["expr"] == LIVE_TRANSCRIPTION_FAILURE_EXPR
        assert 'omi_live_stt_terminal_total{outcome="failure"}' in rule["data"][1]["model"]["expr"]
        assert 'omi_live_stt_accepted_total' in rule["data"][1]["model"]["expr"]
        assert rule["data"][2]["model"]["expression"] == "$A >= 20 && $B > 0.10"
        assert rule["annotations"]["__dashboardUid__"] == "omi-resilience-fallbacks"
        assert rule["annotations"]["__panelId__"] == "10"


SILENT_FAILURE_RUNBOOK = "backend/docs/runbooks/silent-failure-detection.md"
PRE_ROUTE_REJECTION_RULE = "omi-llm-gateway-invalid-requests"
PRE_ROUTE_REJECTION_EXPR = (
    'sum(increase(llm_gateway_request_rejections_total{error_class="invalid_request"}[30m])) or vector(0)'
)
LANE_ZERO_SUCCESS_RULE = "omi-llm-gateway-lane-zero-success"
LANE_ZERO_SUCCESS_EXPR = (
    'sum by (lane_id) (increase(llm_gateway_requests_total{outcome="success"}[6h])) '
    'or sum by (lane_id) (increase(llm_gateway_requests_total[6h])) * 0'
)
SIGNAL_DEAD_RULE = "omi-journey-signal-dead"
CHAT_TRAFFIC_ZERO_RULE = "tz_chat_agent_requests_zero"
SILENT_FAILURE_RULES = {
    PRE_ROUTE_REJECTION_RULE,
    "omi-llm-gateway-lane-failure-ratio",
    LANE_ZERO_SUCCESS_RULE,
    SIGNAL_DEAD_RULE,
    CHAT_TRAFFIC_ZERO_RULE,
}


def test_pre_route_rejection_alert_watches_the_counter_lanes_cannot_see():
    """Validation rejections never reach llm_gateway_requests_total.

    During the 2026-08-19 desktop chat outage the chat lane's request counter
    read 100% success for 19 hours, because every failing request was rejected
    before a route was selected. The rejection counter is the only witness.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules[PRE_ROUTE_REJECTION_RULE]
        assert rule["data"][0]["model"]["expr"] == PRE_ROUTE_REJECTION_EXPR, export_name
        assert "llm_gateway_requests_total" not in rule["data"][0]["model"]["expr"]
        assert rule["data"][2]["model"]["conditions"][0]["evaluator"]["params"] == [2]
        assert rule["noDataState"] == "OK"
        assert rule["labels"]["severity"] == "critical"


def test_lane_zero_success_alert_zero_fills_lanes_that_never_succeeded():
    """A lane with no success series must still be visible.

    Without the ``or ... * 0`` term a lane that has never once succeeded
    produces no ratio series at all, so total failure would be silent.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules[LANE_ZERO_SUCCESS_RULE]
        assert rule["data"][1]["model"]["expr"] == LANE_ZERO_SUCCESS_EXPR, export_name
        assert rule["data"][2]["model"]["expression"] == "$A >= 20 && $B < 1"
        assert rule["noDataState"] == "OK"


def test_journey_signal_dead_alert_treats_missing_evidence_as_the_failure():
    """Journey alerts go quiet when their counter dies; this one does not."""
    for export_name, rules in _all_rule_exports().items():
        rule = rules[SIGNAL_DEAD_RULE]
        expression = rule["data"][0]["model"]["expr"]

        assert "omi_journey_accepted_total" in expression, export_name
        assert "llm_gateway_requests_total" in expression, export_name
        assert rule["noDataState"] == "Alerting", export_name
        assert rule["labels"]["severity"] == "critical", export_name
        # chat_response arrives through the Cloud Run metrics bridge, verified
        # live at ~28MB / 52,662 omi_ series per prod scrape (#12146). Its
        # liveness arm is gated on the chat-agent lane so quiet hours do not
        # page: that lane measured min 9, p01 15, p05 23 requests/hour over
        # 7 production days, so > 20/1h only demands liveness at above-p05
        # chat demand.
        assert 'journey="chat_response"' in expression, export_name
        assert 'lane_id="omi:auto:chat-agent"' in expression, export_name


def test_silent_failure_alerts_link_the_shared_runbook():
    runbook = (REPO / SILENT_FAILURE_RUNBOOK).read_text(encoding="utf-8")

    for export_name, rules in _all_rule_exports().items():
        assert SILENT_FAILURE_RULES <= rules.keys(), export_name
        for uid in SILENT_FAILURE_RULES:
            assert rules[uid]["annotations"]["runbook"] == SILENT_FAILURE_RUNBOOK, f"{export_name}:{uid}"

    for expression in (PRE_ROUTE_REJECTION_EXPR, LANE_ZERO_SUCCESS_EXPR):
        assert expression in runbook


def test_chat_traffic_zero_threshold_sits_below_the_measured_weekly_floor():
    """9 requests was the quietest hour observed in the week before this rule.

    Sampled at 15-minute resolution over 7 days of production: min 9, p01 15,
    p05 23, median 55, and zero evaluations below 5.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules[CHAT_TRAFFIC_ZERO_RULE]
        assert rule["data"][2]["model"]["conditions"][0]["evaluator"]["type"] == "lt", export_name
        assert 'lane_id="omi:auto:chat-agent"' in rule["data"][0]["model"]["expr"]


# 2026-08-30 capture-finalization outage: success stayed at 0% for hours
# (failure ~360/h, stale ~290/h, accepted ~750/h, oldest job ~5.9 days, dead
# letters ~2.5k/day) while every listen/pusher critical stayed Normal because
# they only watch LB traffic, ready pods, WS counts, and 5xx rates. Warning
# journey rules existed (#11991) but nothing page-class watched the user
# outcome. These rules page on that exact fingerprint.
PAGE_CLASS_JOURNEY_RULES = {
    "omi-journey-capture-success-critical": ("speech-processing", "NoData", "$A >= 20 && $B < 0.90"),
    "omi-journey-pusher-success-critical": ("live-transcription", "NoData", "$A >= 20 && $B < 0.90"),
    "omi-journey-chat-success-critical": ("ai-chat", "NoData", "$A >= 20 && $B < 0.90"),
    "omi-journey-capture-settle-gap": ("speech-processing", "NoData", "$A >= 100 && $B > 50"),
    "omi-capture-oldest-nonterminal": ("speech-processing", "Alerting", None),
    "omi-capture-dead-letter-surge": ("speech-processing", "Alerting", None),
}


def test_memory_admission_failure_pages_on_the_first_bounded_runtime_error():
    """A systemic memory fence/config error has no safe nonzero rate."""
    uid = "omi-capture-finalization-memory-fence"
    for export_name, rules in _all_rule_exports().items():
        rule = rules[uid]
        query = rule["data"][0]["model"]["expr"]
        assert 'omi_capture_finalization_failures_total{reason=~"memory_fence|memory_config"}' in query, export_name
        assert "[5m]" in query and "or vector(0)" in query, export_name
        assert rule["for"] == "0s", export_name
        assert rule["labels"]["severity"] == "critical", export_name
        assert rule["labels"]["impact"] == "user-experience", export_name
        assert rule["noDataState"] == "Alerting", export_name
        assert rule["notification_settings"]["receiver"] == "Omi - Services Alerting (Telegram)", export_name


def test_page_class_journey_rules_cover_the_capture_outage_fingerprint():
    """Every Core Features journey tile has a page-class rule behind it."""
    for export_name, rules in _all_rule_exports().items():
        for uid, (component, no_data, gate) in PAGE_CLASS_JOURNEY_RULES.items():
            rule = rules[uid]  # missing from an export fails the lookup
            assert rule["labels"]["severity"] == "critical", f"{export_name}:{uid}"
            assert rule["labels"]["instatus_component"] == component, f"{export_name}:{uid}"
            assert rule["labels"]["impact"] == "user-experience", f"{export_name}:{uid}"
            assert rule["noDataState"] == no_data, f"{export_name}:{uid}"
            assert rule["for"] in {"10m", "15m"}, f"{export_name}:{uid}"
            assert rule["notification_settings"]["receiver"] == "Omi - Services Alerting (Telegram)"
            math_nodes = [d["model"]["expression"] for d in rule["data"] if d["model"].get("type") == "math"]
            if gate is not None:
                assert math_nodes == [gate], f"{export_name}:{uid}"
            else:
                assert not math_nodes, f"{export_name}:{uid}"


def test_page_class_success_rules_pair_numerator_and_denominator_from_one_emitter():
    """A success ratio is only meaningful when both sides come from the same counter."""
    for export_name, rules in _all_rule_exports().items():
        for uid, journey in (
            ("omi-journey-capture-success-critical", "capture_finalization"),
            ("omi-journey-pusher-success-critical", "pusher_session"),
            ("omi-journey-chat-success-critical", "chat_response"),
        ):
            exprs = [d["model"]["expr"] for d in rules[uid]["data"] if d["model"].get("expr")]
            assert all(
                f'omi_journey_terminal_total{{journey="{journey}"' in e for e in exprs[1:]
            ), f"{export_name}:{uid}"
            assert f'omi_journey_accepted_total{{journey="{journey}"}}' in exprs[0], f"{export_name}:{uid}"


def test_finalization_queue_rules_read_the_replicated_series_correctly():
    """The age gauge aggregates with max; the dead-letter counter with increase."""
    for export_name, rules in _all_rule_exports().items():
        age_expr = rules["omi-capture-oldest-nonterminal"]["data"][0]["model"]["expr"]
        assert age_expr == "max(listen_finalization_oldest_nonterminal_age_seconds)", export_name
        dead_expr = rules["omi-capture-dead-letter-surge"]["data"][0]["model"]["expr"]
        assert dead_expr == "sum(increase(listen_finalization_dead_letter_total[1h]))", export_name


RESILIENCE_DASHBOARD = MONITORING / "dashboards/omi-services/resilience-fallbacks.json"
SILENT_FAILURE_PANELS = {
    PRE_ROUTE_REJECTION_RULE: "12",
    "omi-llm-gateway-lane-failure-ratio": "13",
    LANE_ZERO_SUCCESS_RULE: "13",
    SIGNAL_DEAD_RULE: "14",
    CHAT_TRAFFIC_ZERO_RULE: "13",
}


def test_silent_failure_alerts_link_a_panel_that_shows_their_own_signal():
    """ "Confirm it in the linked panel" is only actionable if the panel plots it."""
    dashboard = json.loads(RESILIENCE_DASHBOARD.read_text(encoding="utf-8"))
    panels = {str(panel["id"]): panel for panel in dashboard["panels"]}
    metric_for_panel = {
        "12": "llm_gateway_request_rejections_total",
        "13": "llm_gateway_requests_total",
        "14": "omi_journey_accepted_total",
    }

    for panel_id, metric in metric_for_panel.items():
        assert panel_id in panels, f"resilience dashboard is missing panel {panel_id}"
        assert any(metric in target["expr"] for target in panels[panel_id]["targets"]), panel_id

    for export_name, rules in _all_rule_exports().items():
        for uid, panel_id in SILENT_FAILURE_PANELS.items():
            annotations = rules[uid]["annotations"]
            assert annotations["__dashboardUid__"] == dashboard["uid"], f"{export_name}:{uid}"
            assert annotations["__panelId__"] == panel_id, f"{export_name}:{uid}"


JOURNEY_SELECTOR = re.compile(r'journey="([a-z_]+)"')
JOURNEY_METRIC_PREFIXES = ("omi_journey_", "omi_client_journey_")
# A journey may be exempt from liveness coverage only while its counter provably
# cannot arrive. Each entry needs a reason and must be deleted in the same change
# that makes the counter reachable. chat_response was the last exemption: its
# counter now arrives through the verified Cloud Run metrics bridge (#11998,
# #12146 measured a live ~28MB / 52,662-series prod scrape), and the liveness
# rule covers it with a chat-agent-lane traffic gate.
LIVENESS_EXEMPT_JOURNEYS: dict[str, str] = {}


def _journeys_alerted_on(rules: dict[str, dict]) -> dict[str, set[str]]:
    alerted: dict[str, set[str]] = {}
    for uid, rule in rules.items():
        if uid == SIGNAL_DEAD_RULE:
            continue
        for query in rule["data"]:
            expression = query["model"].get("expr") or ""
            if not any(prefix in expression for prefix in JOURNEY_METRIC_PREFIXES):
                continue
            for journey in JOURNEY_SELECTOR.findall(expression):
                alerted.setdefault(journey, set()).add(uid)
    return alerted


def test_every_alerted_journey_is_covered_by_the_liveness_rule():
    """An alert whose input counter is dead does not fail loudly — it goes quiet.

    omi-journey-chat-fail sat armed and unfirable for its entire existence
    because omi_journey_accepted_total{journey="chat_response"} is emitted from
    an unscraped Cloud Run process. A desktop chat outage then ran for roughly
    19 hours with no page. Adding a journey alert without liveness coverage
    recreates that exact hole, so it fails here instead.
    """
    for export_name, rules in _all_rule_exports().items():
        liveness = rules[SIGNAL_DEAD_RULE]["data"][0]["model"]["expr"]
        covered = set(JOURNEY_SELECTOR.findall(liveness))
        covered |= (
            set(re.findall(r'journey=~"([a-z_|]+)"', liveness)[0].split("|"))
            if re.findall(r'journey=~"([a-z_|]+)"', liveness)
            else set()
        )

        for journey, uids in _journeys_alerted_on(rules).items():
            if journey in LIVENESS_EXEMPT_JOURNEYS:
                assert LIVENESS_EXEMPT_JOURNEYS[journey].strip(), journey
                assert (
                    journey not in covered
                ), f"{export_name}: {journey} is both exempt and covered — delete the exemption"
                continue
            assert journey in covered, (
                f"{export_name}: {journey} is alerted on by {sorted(uids)} but is not covered by "
                f"{SIGNAL_DEAD_RULE}. Either add it to the liveness rule or record why its counter "
                f"cannot arrive in LIVENESS_EXEMPT_JOURNEYS."
            )


def test_liveness_exemptions_are_documented_in_the_runbook():
    runbook = (REPO / SILENT_FAILURE_RUNBOOK).read_text(encoding="utf-8")

    for journey in LIVENESS_EXEMPT_JOURNEYS:
        assert journey in runbook, f"{journey} is exempt from liveness coverage but the runbook does not say why"


def test_no_alert_applies_a_counter_function_to_a_stackdriver_gauge():
    """rate()/increase()/irate() over a stackdriver_ series is always a bug.

    stackdriver_exporter publishes Cloud Monitoring DELTA metrics as GAUGES whose
    value is the count for one alignment window. A counter function over that
    returns a plausible wrong number instead of an error -- which is exactly how
    two Firestore cost alerts shipped in #12193 that could never cross their
    thresholds: rate() read 75.7 where real volume was ~936/sec. Read volume must
    be recovered with avg_over_time(avg(...))/60.

    Failure-Class: FC-alert-never-provably-fired
    """
    offenders = set()
    counter_fn_over_stackdriver = re.compile(r"\b(?:rate|irate|increase)\s*\(\s*[^)]*\bstackdriver_")
    for _export_name, rules in _all_rule_exports().items():
        for uid, rule in rules.items():
            for node in rule.get("data", []):
                expr = (node.get("model") or {}).get("expr")
                if isinstance(expr, str) and counter_fn_over_stackdriver.search(expr):
                    offenders.add(uid)
    new_offenders = offenders - COUNTER_FN_ON_GAUGE_DEBT
    assert not new_offenders, (
        "rate()/irate()/increase() applied to a stackdriver_ gauge in: "
        + ", ".join(sorted(new_offenders))
        + ". Use avg_over_time(avg(<metric>)[<window>:<step>]) / 60 for a per-second rate."
    )
    stale = COUNTER_FN_ON_GAUGE_DEBT - offenders
    assert not stale, (
        "these UIDs were fixed or removed -- delete them from COUNTER_FN_ON_GAUGE_DEBT so the "
        "ratchet keeps tightening: " + ", ".join(sorted(stale))
    )


START_FAIL_RULE = "omi-cr-start-fail"


def test_cloud_run_instance_start_fail_alert_is_zero_baseline_logging_count():
    """2026-09-01: minScale kept /health green while new Cloud Run instances failed to start."""
    for rules in _all_rule_exports().values():
        rule = rules[START_FAIL_RULE]
        assert rule["title"] == "Cloud Run - instance start failures"
        assert rule["noDataState"] == "OK"
        assert rule["execErrState"] == "OK"
        assert rule["for"] == "5m"
        assert rule["labels"]["severity"] == "critical"
        assert rule["labels"]["instatus_component"] == "api"
        assert rule["labels"]["impact"] == "product"
        query = rule["data"][0]
        assert query["datasourceUid"] == "deuxlwt1d569sb"
        text = query["model"]["queryText"]
        assert "STARTUP TCP probe failed" in text
        assert "instance could not start successfully" in text
        assert query["model"]["projectId"] == "based-hardware"
        threshold = rule["data"][2]["model"]["conditions"][0]["evaluator"]["params"]
        assert threshold == [0]


STT_CHAIN_EXHAUSTED_RATIO_EXPR = (
    'sum(increase(omi_fallback_total{job="backend-listen-metrics",component="stt_selection",'
    'outcome="exhausted"}[5m])) / clamp_min(sum(increase(omi_listen_accepted_total'
    '{job="backend-listen-metrics"}[5m])), 1)'
)
STT_CHAIN_EXHAUSTED_TRAFFIC_EXPR = 'sum(increase(omi_listen_accepted_total{job="backend-listen-metrics"}[5m]))'
STT_FALLBACK_LEG_ATTEMPTS_EXPR = (
    'sum by (to_mode) (increase(omi_fallback_total{job="backend-listen-metrics",'
    'component=~"stt_selection|stt_live_session"}[6h]))'
)
STT_FALLBACK_LEG_RECOVERED_EXPR = (
    'sum by (to_mode) (increase(omi_fallback_total{job="backend-listen-metrics",'
    'component=~"stt_selection|stt_live_session",outcome="recovered"}[6h])) or sum by (to_mode) '
    '(increase(omi_fallback_total{job="backend-listen-metrics",component=~"stt_selection|stt_live_session"}[6h])) * 0'
)
STT_PROVIDER_BUDGET_EXPR = (
    'sum by (provider) (increase(omi_stt_stream_close_total{job="backend-listen-metrics",'
    'reason="provider_budget_exhausted"}[5m])) unless on (provider) '
    '(max by (provider) (omi_stt_provider_retired{job="backend-listen-metrics"} == 1))'
)
STT_PROVIDER_RETIRED_EXPR = '(max by (provider) (omi_stt_provider_retired{job="backend-listen-metrics"} == 1))'
STT_CHAIN_EXHAUSTION_RULES = {
    "omi-stt-chain-exhausted-warn": ("warning", "$A >= 50 && $B > 0.35", "10m"),
    "omi-stt-chain-exhausted-page": ("critical", "$A >= 50 && $B > 0.60", "5m"),
}


def test_stt_chain_exhaustion_alerts_ratio_listen_accepted_on_the_listen_job():
    """initialize_stt deaths never built a LiveSTTAttempt, so the 10% live-STT
    ratio is blind to them. These rules watch omi_fallback_total exhausted over
    the socket-accept counter that does increment at /v4/listen accept.
    """
    for export_name, rules in _all_rule_exports().items():
        for uid, (severity, gate, pending) in STT_CHAIN_EXHAUSTION_RULES.items():
            rule = rules[uid]
            assert rule["labels"]["severity"] == severity, f"{export_name}:{uid}"
            assert rule["labels"]["impact"] == "user-experience", f"{export_name}:{uid}"
            assert rule["noDataState"] == "OK", f"{export_name}:{uid}"
            assert rule["for"] == pending, f"{export_name}:{uid}"
            exprs = [d["model"]["expr"] for d in rule["data"] if d["model"].get("expr")]
            assert exprs[0] == STT_CHAIN_EXHAUSTED_TRAFFIC_EXPR, f"{export_name}:{uid}"
            assert exprs[1] == STT_CHAIN_EXHAUSTED_RATIO_EXPR, f"{export_name}:{uid}"
            math_nodes = [d["model"]["expression"] for d in rule["data"] if d["model"].get("type") == "math"]
            assert math_nodes == [gate], f"{export_name}:{uid}"
            assert "increase(" in exprs[1] and "rate(" not in exprs[1], f"{export_name}:{uid}"
            assert 'job="backend-listen-metrics"' in exprs[1], f"{export_name}:{uid}"
            assert "evaluated_bad" in rule["annotations"], f"{export_name}:{uid}"
            assert "evaluated_good" in rule["annotations"], f"{export_name}:{uid}"
            assert "0.817" in rule["annotations"]["evaluated_bad"], f"{export_name}:{uid}"
            assert "0.251" in rule["annotations"]["evaluated_good"], f"{export_name}:{uid}"
            assert rule["annotations"]["__dashboardUid__"] == "omi-resilience-fallbacks"
            assert rule["annotations"]["__panelId__"] == "15"


def test_stt_fallback_leg_dead_alert_zero_fills_legs_with_no_recovered_series():
    """A to_mode that never recovered produces no recovered series; without the
    `or ... * 0` term, 100% handshake failure (Deepgram since 2026-09-14) is silent.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules["omi-stt-fallback-leg-dead"]
        assert rule["labels"]["severity"] == "warning", export_name
        assert rule["noDataState"] == "OK", export_name
        assert rule["for"] == "30m", export_name
        exprs = [d["model"]["expr"] for d in rule["data"] if d["model"].get("expr")]
        assert exprs[0] == STT_FALLBACK_LEG_ATTEMPTS_EXPR, export_name
        assert exprs[1] == STT_FALLBACK_LEG_RECOVERED_EXPR, export_name
        math_nodes = [d["model"]["expression"] for d in rule["data"] if d["model"].get("type") == "math"]
        assert math_nodes == ["$A >= 50 && $B < 1"], export_name
        assert "evaluated_bad" in rule["annotations"], export_name
        assert "recovered=0" in rule["annotations"]["evaluated_bad"], export_name
        assert 'component=~"stt_selection|stt_live_session"' in exprs[0], export_name
        assert 'component="other"' not in exprs[0], export_name
        assert rule["annotations"]["__panelId__"] == "16"


def test_stt_provider_budget_alert_pages_on_typed_stream_closes():
    """Monthly/quota exhaustion is never transient. The 2026-09-19 Soniox
    organization_monthly_budget_exhausted outage closed every hop and was
    unpaged for 27.5h because recovered was recorded at connect.

    2026-09-26 revision: the alert is per provider (the aggregated form carried
    no signal — Deepgram kept it firing for days) and subtracts deployment-
    retired providers so an intentionally unfunded leg (hosted Deepgram, per
    the 2026-09 cost ruling) cannot page forever.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules["omi-stt-provider-budget"]
        assert len(rule["uid"]) < 40, export_name
        assert rule["labels"]["severity"] == "critical", export_name
        assert rule["labels"]["impact"] == "product", export_name
        assert rule["noDataState"] == "OK", export_name
        assert rule["for"] == "2m", export_name
        exprs = [d["model"]["expr"] for d in rule["data"] if d["model"].get("expr")]
        assert exprs[0] == STT_PROVIDER_BUDGET_EXPR, export_name
        assert "sum by (provider)" in exprs[0], export_name
        assert "unless on (provider)" in exprs[0], export_name
        assert "omi_stt_provider_retired" in exprs[0], export_name
        math_nodes = [d["model"]["expression"] for d in rule["data"] if d["model"].get("type") == "math"]
        assert math_nodes == ["$A > 0"], export_name
        assert "top up" in rule["annotations"]["summary"].lower(), export_name
        assert "evaluated_bad" in rule["annotations"], export_name
        assert "evaluated_good" in rule["annotations"], export_name
        assert rule["annotations"]["__panelId__"] == "18"


LIVE_TRANSCRIPTION_SUCCESS_RULE = "omi-live-transcription-success-low"
LIVE_TRANSCRIPTION_SUCCESS_TOTAL_EXPR = (
    'sum(increase(omi_live_session_transcript_outcome_total{job="backend-listen-metrics",'
    'outcome=~"transcribed|no_transcript"}[5m]))'
)


def test_live_transcription_success_alert_measures_the_user_felt_outcome():
    """The headline SLI: did this session get any transcript?

    2026-09-26 incident: ~34.8k of ~35k sessions failed for hours and nothing
    paged, because every existing rule watched provider plumbing instead of
    the session outcome. too_short sessions stay out of the denominator so
    quiet nights cannot page, and the >= 50 volume guard keeps no-data healthy.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules[LIVE_TRANSCRIPTION_SUCCESS_RULE]
        assert len(rule["uid"]) < 40, export_name
        assert rule["labels"]["severity"] == "critical", export_name
        assert rule["labels"]["impact"] == "user-experience", export_name
        assert rule["noDataState"] == "OK", export_name
        assert rule["for"] == "5m", export_name
        exprs = [d["model"]["expr"] for d in rule["data"] if d["model"].get("expr")]
        assert exprs[0] == LIVE_TRANSCRIPTION_SUCCESS_TOTAL_EXPR, export_name
        assert exprs[0] != exprs[1], export_name
        assert 'outcome="transcribed"' in exprs[1], export_name
        assert 'outcome="too_short"' not in exprs[1], export_name
        assert "clamp_min" in exprs[1], export_name
        math_nodes = [d["model"]["expression"] for d in rule["data"] if d["model"].get("type") == "math"]
        assert math_nodes == ["$A >= 50 && $B < 0.90"], export_name
        assert rule["notification_settings"]["receiver"] == "Omi - Services Alerting (Telegram)", export_name
        assert (REPO / rule["annotations"]["runbook"]).is_file(), export_name


def test_stt_leg_error_rate_reads_a_metric_every_connect_path_emits():
    """omi_stt_leg_attempts_total is configured-chain-only and was empty in prod
    while the chain was off (2026-09-26 incident: the rule could never fire).
    The rule now reads omi_stt_provider_connect_total, which both the legacy
    order and the configured chain record, and excludes retired providers.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules["omi-stt-leg-error-rate"]
        expressions = " ".join(d["model"].get("expr", "") for d in rule["data"])
        assert "omi_stt_leg_attempts_total" not in expressions, export_name
        assert "omi_stt_provider_connect_total" in expressions, export_name
        assert 'outcome="failure"' in expressions, export_name
        assert "unless on (provider)" in expressions, export_name
        assert STT_PROVIDER_RETIRED_EXPR in expressions, export_name
        assert 'job="backend-listen-metrics"' in expressions, export_name
        assert rule["noDataState"] == "OK", export_name
        assert "omi-stt-chain-terminal" not in rules, export_name


# Metrics that legitimately come from outside the backend source tree. Each
# entry must name its emitter; anything not listed here and not declared in
# backend source as a Counter/Gauge/Histogram fails the gate below.
EXTERNAL_ALERT_METRIC_PREFIXES = {
    "kube_": "kube-state-metrics",
    "namespace_workload_pod:": "kube-state-metrics relabeling rule",
    "container_": "cAdvisor",
    "stackdriver_": "prometheus-stackdriver-exporter",
    "engine_": "deepgram self-hosted deployment exporter",
}
EXTERNAL_ALERT_METRICS = {
    "up": "Prometheus builtin target health",
}

_METRIC_DECLARATION = re.compile(r"(?:Counter|Gauge|Histogram)\(\s*['\"]([a-zA-Z0-9_:]+)['\"]")
_PROMQL_KEYWORDS = frozenset(
    {
        "sum",
        "by",
        "without",
        "increase",
        "rate",
        "irate",
        "avg_over_time",
        "max_over_time",
        "min_over_time",
        "count_over_time",
        "sum_over_time",
        "last_over_time",
        "stddev_over_time",
        "quantile_over_time",
        "absent",
        "absent_over_time",
        "clamp_min",
        "clamp_max",
        "vector",
        "or",
        "and",
        "unless",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "offset",
        "bool",
        "histogram_quantile",
        "topk",
        "bottomk",
        "count",
        "max",
        "min",
        "avg",
        "sort",
        "sort_desc",
        "label_replace",
        "delta",
        "idelta",
        "deriv",
        "predict_linear",
        "resets",
        "changes",
        "abs",
        "ceil",
        "floor",
        "round",
        "sgn",
        "exp",
        "ln",
        "log2",
        "log10",
        "sqrt",
        "time",
        "timestamp",
    }
)
_PROMQL_GROUP_CLAUSE = re.compile(r"\b(?:by|on|without|group_left|group_right)\s*\([^)]*\)")
_HISTOGRAM_SUFFIXES = ("_bucket", "_sum", "_count")


def _declared_backend_metric_names() -> set[str]:
    names: set[str] = set()
    for path in (REPO / "backend").rglob("*.py"):
        text = str(path)
        if "/tests/" in text or "/testing/" in text or "/.venv/" in text:
            continue
        names |= set(_METRIC_DECLARATION.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return names


# Scanned once at import (collection) time: the walk over backend source costs
# ~0.4s CPU, which would otherwise blow the fast-unit per-call budget.
DECLARED_BACKEND_METRIC_NAMES = _declared_backend_metric_names()


def _alert_expr_metric_names(expr: str) -> set[str]:
    # Drop label values, then grouping clauses, so only selectors remain.
    stripped = _PROMQL_GROUP_CLAUSE.sub(" ", re.sub(r'"[^"]*"', '""', expr))
    names = set()
    for match in re.finditer(r"\b([a-z_][a-z0-9_]*(?::[a-z_][a-z0-9_]*)*)\b", stripped):
        token = match.group(1)
        if token in _PROMQL_KEYWORDS:
            continue
        if re.search(rf"\b{re.escape(token)}\s*(?:=~?|!=)", stripped):
            continue  # label key in a matcher
        names.add(token)
    return names


def _is_external_alert_metric(token: str) -> bool:
    return token in EXTERNAL_ALERT_METRICS or any(token.startswith(prefix) for prefix in EXTERNAL_ALERT_METRIC_PREFIXES)


def test_every_alert_expression_metric_is_emitted_in_backend_source():
    """An alert reading a metric nothing emits can never fire.

    Failure-Class: FC-alert-never-provably-fired

    omi-stt-chain-terminal and omi-stt-leg-error-rate read
    omi_stt_chain_exhausted_total / omi_stt_leg_attempts_total, which only the
    configured-order chain emits; with the chain off in prod both series were
    permanently empty and the rules were unfirable through the whole 2026-09-26
    incident. This gate fails when an alert expression references a metric
    name that is neither declared as a Counter/Gauge/Histogram anywhere in
    backend source nor explicitly allowlisted as an external emitter above.
    """
    declared = DECLARED_BACKEND_METRIC_NAMES
    assert declared, "metric declaration scan found nothing; the gate is broken"

    def _base(token: str) -> str:
        for suffix in _HISTOGRAM_SUFFIXES:
            if token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    offenders: dict[str, set[str]] = {}
    for export_name, rules in _all_rule_exports().items():
        for uid, rule in rules.items():
            for node in rule.get("data", []):
                model = node.get("model") or {}
                expr = model.get("expr")
                is_promql = (
                    node.get("datasourceUid") == "prometheus"
                    or (model.get("datasource") or {}).get("type") == "prometheus"
                )
                if not is_promql or not isinstance(expr, str) or not expr:
                    continue
                for token in _alert_expr_metric_names(expr):
                    base = _base(token)
                    if base in declared or token in declared or _is_external_alert_metric(token):
                        continue
                    offenders.setdefault(token, set()).add(f"{export_name}:{uid}")
    assert not offenders, (
        "Alert expressions reference metric names no backend source declares (and that are not "
        "allowlisted external emitters): "
        + "; ".join(f"{token} <- {sorted(uids)}" for token, uids in sorted(offenders.items()))
        + ". Emit the metric or allowlist the external emitter. Failure-Class: FC-alert-never-provably-fired"
    )


# Cloud Logging tokens counted by Grafana rules, mapped to the Cloud Run
# services that actually emit them. A query that pins resource.labels.service_name
# to a set that is not exactly those emitters either watches a service that
# never produces the numerator (permanently 0) or drops the service that does.
# Measured 2026-09-21 00:00–18:00Z on based-hardware:
#   created: 9626, all backend-sync-backfill; backend-sync created = 0
#   merged:  21482 backend-sync-backfill + 757 backend-sync
CLOUD_LOGGING_TOKEN_EMITTERS = {
    "omi_sync_intake outcome=created": frozenset({"backend-sync-backfill"}),
    "omi_sync_intake outcome=merged": frozenset({"backend-sync", "backend-sync-backfill"}),
}
_SERVICE_NAME_PIN = re.compile(r'resource\.labels\.service_name="([^"]+)"')


def test_sync_intake_fragmentation_alert_uses_cloud_logging_until_scrape_exists():
    """backend-sync is not in the Cloud Run metrics exporter allowlist, so a
    Prometheus alert on omi_sync_intake_total would be permanently empty=healthy.
    """
    for export_name, rules in _all_rule_exports().items():
        rule = rules["omi-sync-intake-fragmented"]
        assert rule["labels"]["severity"] == "warning", export_name
        assert rule["noDataState"] == "OK", export_name
        assert rule["execErrState"] == "OK", export_name
        queries = [d for d in rule["data"] if d.get("datasourceUid") == "deuxlwt1d569sb"]
        assert len(queries) == 2, export_name
        created, merged = (q["model"]["queryText"] for q in queries)
        created_services = set(_SERVICE_NAME_PIN.findall(created))
        merged_services = set(_SERVICE_NAME_PIN.findall(merged))
        assert created_services == {"backend-sync-backfill"}, export_name
        assert merged_services == {"backend-sync", "backend-sync-backfill"}, export_name
        assert 'omi_sync_intake outcome=created' in created
        assert 'omi_sync_intake outcome=merged' in merged
        assert "jsonPayload.message" in created and "textPayload" in created
        math_nodes = [d["model"]["expression"] for d in rule["data"] if d["model"].get("type") == "math"]
        assert math_nodes == ["$C >= 100 && $C / ($C + $D + 0.001) > 0.80"], export_name
        assert "9626" in rule["annotations"]["evaluated_good"], export_name
        assert "0.302" in rule["annotations"]["evaluated_good"], export_name
        assert rule["annotations"]["__panelId__"] == "17"


def test_cloud_logging_alert_filters_pin_only_services_that_emit_the_counted_token():
    """A Logging count whose service_name pin is not the token's emitters cannot fire.

    omi-sync-intake-fragmented watched backend-sync for
    ``omi_sync_intake outcome=created``. That service emitted zero created
    lines (measured 2026-09-21 00:00–18:00Z); the numerator was permanently 0.
    """
    for export_name, rules in _all_rule_exports().items():
        for uid, rule in rules.items():
            for node in rule.get("data", []):
                model = node.get("model") or {}
                datasource = model.get("datasource") or {}
                if datasource.get("type") != "googlecloud-logging-datasource":
                    continue
                query = model.get("queryText") or ""
                pinned = set(_SERVICE_NAME_PIN.findall(query))
                if not pinned:
                    continue
                for token, emitters in CLOUD_LOGGING_TOKEN_EMITTERS.items():
                    if token not in query:
                        continue
                    assert pinned == emitters, (
                        f"{export_name}:{uid} log filter for {token!r} pins "
                        f"{sorted(pinned)} but emitters are {sorted(emitters)}"
                    )


def test_stt_exhaustion_dashboard_panels_plot_the_alerted_series():
    dashboard = json.loads(RESILIENCE_DASHBOARD.read_text(encoding="utf-8"))
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    assert "omi_fallback_total" in panels[15]["targets"][0]["expr"]
    assert 'outcome="exhausted"' in panels[15]["targets"][0]["expr"]
    assert "omi_listen_accepted_total" in panels[15]["targets"][0]["expr"]
    assert 'job="backend-listen-metrics"' in panels[15]["targets"][0]["expr"]
    assert "omi_fallback_total" in panels[16]["targets"][0]["expr"]
    assert 'outcome="recovered"' in panels[16]["targets"][0]["expr"]
    assert "to_mode" in panels[16]["targets"][0]["expr"]
    assert "stt_live_session" in panels[16]["targets"][0]["expr"]
    assert "omi_sync_intake_total" in panels[17]["targets"][0]["expr"]
    assert "Scrape gap" in panels[17]["description"]
    assert "omi_stt_stream_close_total" in panels[18]["targets"][0]["expr"]
    assert "provider_budget_exhausted" in panels[18]["fieldConfig"]["defaults"]["description"]


def test_windowed_live_stt_rules_cover_admission_and_pre_audio_failures():
    """September 19 account outage: failover success must not hide exhausted accounts.

    2026-09-26: omi-stt-chain-terminal is deleted (it read the configured-chain-only
    omi_stt_chain_exhausted_total, empty in prod while the chain was off) and
    omi-stt-leg-error-rate reads the every-path connect counter instead.
    """
    expected = {
        'omi-stt-leg-error-rate': ('omi_stt_provider_connect_total', 'by (provider)'),
        'omi-stt-account-state': ('omi_stt_stream_close_total', 'reason="provider_auth_rejected"'),
        'omi-stt-window-overflow': ('omi_stt_window_admissions_total', 'outcome="overflow"'),
        'omi-stt-window-saturated': ('omi_stt_window_sessions_active', 'omi_stt_window_sessions_capacity'),
        'omi-stt-window-post-errors': ('omi_stt_window_posts_total', 'outcome="error"'),
        LIVE_TRANSCRIPTION_SUCCESS_RULE: ('omi_live_session_transcript_outcome_total', 'clamp_min'),
    }
    for rules in _all_rule_exports().values():
        for uid, metrics in expected.items():
            rule = rules[uid]
            expressions = ' '.join(d['model'].get('expr', '') for d in rule['data'])
            assert all(metric in expressions for metric in metrics), uid
            assert 'job="backend-listen-metrics"' in expressions
            assert rule['noDataState'] == 'OK'
            assert any('$A' in d['model'].get('expression', '') for d in rule['data'])
            assert (REPO / rule['annotations']['runbook']).is_file()


LISTEN_DASHBOARD = MONITORING / "dashboards/gke/backend-listen.json"


def test_backend_listen_dashboard_has_live_transcription_health_row():
    """The 2026-09-26 incident had no panel answering 'did sessions get
    transcripts, and which provider is benched'. The row the headline alert
    links to must plot the alerted series: headline %, per-provider sessions
    served and connect success, breaker-open pods, and error classes.
    """
    dashboard = json.loads(LISTEN_DASHBOARD.read_text(encoding="utf-8"))
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    row = panels[16]
    assert row["type"] == "row"
    assert row["title"] == "Live transcription health"

    exprs = {panel_id: " ".join(t["expr"] for t in panels[panel_id]["targets"]) for panel_id in range(17, 23)}
    assert "omi_live_session_transcript_outcome_total" in exprs[17]
    assert 'outcome="transcribed"' in exprs[17]
    assert "omi_live_session_transcript_outcome_total" in exprs[18]
    assert "omi_live_stt_accepted_total" in exprs[19]
    assert "omi_stt_provider_connect_total" in exprs[20]
    assert 'outcome="success"' in exprs[20]
    assert "omi_stt_provider_retired" in exprs[20]
    assert "omi_stt_provider_circuit_open" in exprs[21]
    assert "omi_stt_provider_connect_total" in exprs[22]
    assert "error_class" in exprs[22]
    for panel_id in range(17, 23):
        assert 'job="backend-listen-metrics"' in exprs[panel_id], panel_id
