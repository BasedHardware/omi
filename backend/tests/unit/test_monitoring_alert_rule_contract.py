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
        assert rule["labels"]["severity"] == "critical"
        # chat_response is emitted from Cloud Run, which Prometheus does not
        # scrape. Including it before an ingestion path exists would page
        # permanently and train operators to mute the rule.
        assert "chat_response" not in expression, export_name


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
        assert rule["data"][2]["model"]["conditions"][0]["evaluator"]["params"] == [5], export_name
        assert rule["data"][2]["model"]["conditions"][0]["evaluator"]["type"] == "lt"
        assert 'lane_id="omi:auto:chat-agent"' in rule["data"][0]["model"]["expr"]


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
# that makes the counter reachable.
LIVENESS_EXEMPT_JOURNEYS = {
    "chat_response": (
        "Emitted by backend/routers/chat.py from the Cloud Run backend service. Prometheus "
        "scrapes GKE pods only, so this counter reads zero and including it in the liveness "
        "rule would page permanently. Remove this exemption in the change that gives Cloud "
        "Run services a metrics ingestion path, and add the journey to the liveness rule."
    ),
}


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
