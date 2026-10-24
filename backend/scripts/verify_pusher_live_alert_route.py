#!/usr/bin/env python3
"""Fail closed unless the finalization alert is live, queryable, and routed.

The default invocation is the Pusher release gate: the gated UID set, scrape
targets, finalization metrics, and Telegram receiver. Optional ``--mode fleet``
classifies every committed Grafana rule against live provisioning without
changing that gate. Fleet drift is report-only unless ``--fail-on`` is raised.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "backend/charts/monitoring/alerts/resilience.json"
ALERT_SOURCES = ROOT / "backend/charts/monitoring/alerts"
GATE_FILE = ROOT / "backend/charts/monitoring/live-alert-gate.json"
RULE_UIDS = (
    "omi-capture-finalization-memory-fence",
    "omi-journey-capture-success-critical",
    "omi-journey-capture-settle-gap",
    "omi-capture-oldest-nonterminal",
    "omi-capture-dead-letter-surge",
    "omi-journey-scrape-missing",
    "omi-journey-capture-fail",
)
LIVE_STT_IMPORT_UIDS = (
    "omi-stt-account-state",
    "omi-stt-window-overflow",
    "omi-stt-window-saturated",
    "omi-stt-window-post-errors",
    "omi-stt-leg-error-rate",
    "omi-live-transcription-success-low",
    "omi-soniox-rate-limited",
    "omi-stt-single-leg-risk",
    "omi-soniox-budget-exhausted",
    "omi-modulate-failing-soniox",
    "omi-stt-window-no-text",
    "omi-stt-window-first-text",
    "omi-stt-batch-queue-depth",
    "omi-stt-batch-queue-latency",
    "omi-stt-sync-prerecorded-errors",
    "omi-stt-terminal-after-text",
    "omi-stt-mid-session-terminal",
    "omi-stt-paid-capacity",
    "omi-stt-combined-pressure",
    "omi-stt-window-post-latency",
    "omi-stt-replay-continuity",
    "omi-stt-evidence-loss",
    "omi-stt-evidence-loss-critical",
    "omi-stt-leg-lifecycle-gap",
    "omi-stt-leg-settlement-omission",
    "omi-stt-snapshot-unready",
    "omi-stt-stage-disagreement",
    "omi-stt-enabled-state-unknown",
    "omi-stt-capacity-full-exhausted",
    "omi-stt-local-delivery-exhausted",
    "omi-stt-provider-terminal-failure-ratio",
    "omi-stt-chain-exhausted-ratio",
    "omi-stt-no-full-stage-target",
    "omi-stt-pressure-sampler-stuck",
)
DATASOURCE_CANARY_UIDS = ("omi-datasource-prometheus", "omi-datasource-cloud-monitoring")
REDIS_CACHE_IMPORT_UIDS = ("omi-redis-cache-conn-warn", "omi-redis-cache-conn-page")
TELEGRAM_RECEIVER = "Omi - Services Alerting (Telegram)"
REQUIRED_METRICS = {
    "omi_capture_finalization_failures_total",
    "omi_journey_accepted_total",
    "omi_journey_terminal_total",
}
REQUIRED_JOBS = {"pusher-metrics", "backend-listen-metrics"}
# Per-target `up` series. Pusher and backend-listen additionalScrapeConfigs both
# relabel namespace and pod. min(up) is applied in process to the series that
# remain after confirmed deletions are removed. Do not replace this with max(up).
SERVING_UP_QUERY = 'up{job=~"pusher-metrics|backend-listen-metrics"}'
# Before publishing, the gate checks the *currently serving* fleet. One missed
# scrape on any of the many backend-listen pods made a single instant read fail
# the release (backend-listen-metrics=0 on 2026-10-16/17 with every pod serving).
# A target therefore counts as up when any scrape succeeded in the last window;
# a target down for the whole window still fails. Post-rollout keeps instant up.
PREPUBLISH_UP_WINDOW = "2m"
PREPUBLISH_UP_QUERY = f"max_over_time({SERVING_UP_QUERY}[{PREPUBLISH_UP_WINDOW}])"
PREPUBLISH_DEFAULT_ATTEMPTS = 6
# kube-state-metrics v2.16 emits this gauge only when metadata.deletionTimestamp
# is set. Labels are namespace, pod, and uid — the same namespace/pod keys as the
# scrape targets. Both Deployments use terminationGracePeriodSeconds 120 plus a
# 15s preStop, which outlasts the post-rollout retry budget, so a draining old
# pod must not fail the serving set. Phase Running is not a deletion signal.
POD_DELETION_TIMESTAMP_QUERY = "kube_pod_deletion_timestamp"
# Distinguishes "nothing is deleting" from "kube-state-metrics is not scraped".
# An empty deletion result is authoritative only when this count is positive.
KSM_POD_INFO_COUNT_QUERY = "count(kube_pod_info)"
ALLOWED_HOSTS = {"monitor.omiapi.com", "monitor.omi.me"}
DEFINITION_KEYS = ("uid", "title", "condition", "data", "noDataState", "execErrState", "for", "labels")
# Grafana stores these on a query node when the committed rule omits them.
# They are assigned storage defaults, not authored alert behavior. A committed
# value is compared exactly, including when it equals one of these defaults.
GRAFANA_ASSIGNED_QUERY_DEFAULTS = {"queryType": ""}
GRAFANA_ASSIGNED_MODEL_DEFAULTS = {"intervalMs": 1000, "maxDataPoints": 43200}
SINGLE_RULE_SIZE_LIMIT = 1_000_000
FLEET_LIST_SIZE_LIMIT = 4_000_000
ALERT_RULE_LIST_PATH = "/api/v1/provisioning/alert-rules"


class AlertRouteError(ValueError):
    pass


@dataclass(frozen=True)
class FleetCoverage:
    committed_but_absent: tuple[str, ...]
    live_but_uncommitted: tuple[str, ...]
    present_but_paused: tuple[str, ...]
    present_but_divergent: tuple[str, ...]
    live_and_matching: tuple[str, ...]
    live_count: int


def _token(path: Path) -> str:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise AlertRouteError("Grafana token file must not be accessible by group or others")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise AlertRouteError("Grafana token file is empty")
    return value


def _request_json(base_url: str, path: str, token: str, *, size_limit: int = SINGLE_RULE_SIZE_LIMIT) -> Any:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(size_limit + 1)
    except urllib.error.HTTPError as exc:
        # Name the status. Collapsing every failure into "HTTPError" cost ~37h of red
        # deploys in #12668 because CI could not tell an unprovisioned rule (404) from a
        # revoked token (401) — two failures with completely different owners and fixes.
        # Status and reason phrase only: the response body can carry Grafana detail we do
        # not want in a public log.
        raise AlertRouteError(f"Grafana API request failed for {path}: HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        # Subclass of OSError, superclass of HTTPError, so it has to sit between the two.
        raise AlertRouteError(f"Grafana API request failed for {path}: URLError {exc.reason}") from exc
    except OSError as exc:
        raise AlertRouteError(f"Grafana API request failed for {path}: {type(exc).__name__}") from exc
    if len(body) > size_limit:
        raise AlertRouteError(f"Grafana API response exceeded the size limit for {path}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AlertRouteError(f"Grafana API returned invalid JSON for {path}") from exc


def _write_rule(base_url: str, uid: str, rule: dict[str, Any], token: str, *, exists: bool) -> None:
    method = "PUT" if exists else "POST"
    path = f"{ALERT_RULE_LIST_PATH}/{urllib.parse.quote(uid, safe='')}" if exists else ALERT_RULE_LIST_PATH
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(rule, separators=(",", ":")).encode("utf-8"),
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read(SINGLE_RULE_SIZE_LIMIT + 1)
    except urllib.error.HTTPError as exc:
        raise AlertRouteError(f"Grafana API request failed for {path}: HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise AlertRouteError(f"Grafana API request failed for {path}: URLError {exc.reason}") from exc
    except OSError as exc:
        raise AlertRouteError(f"Grafana API request failed for {path}: {type(exc).__name__}") from exc


def load_live_stt_import_rules(*, production: bool = True) -> dict[str, dict[str, Any]]:
    loaded: object = json.loads((ALERT_SOURCES / "live-stt.json").read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise AlertRouteError("committed live-STT alert file is not a list")
    by_uid: dict[str, dict[str, Any]] = {}
    for item in loaded:
        if not isinstance(item, dict):
            raise AlertRouteError("committed live-STT alert file contains a non-object rule")
        uid = item.get("uid")
        if not isinstance(uid, str) or not uid or uid in by_uid:
            raise AlertRouteError("committed live-STT alert file contains a missing or duplicate uid")
        by_uid[uid] = item
    if set(by_uid) != set(LIVE_STT_IMPORT_UIDS):
        raise AlertRouteError("committed live-STT rules do not match the import allowlist")
    rules = {uid: by_uid[uid] for uid in LIVE_STT_IMPORT_UIDS}
    committed = load_all_committed_rules()
    canary_uids = DATASOURCE_CANARY_UIDS if production else ()
    for uid in (*canary_uids, *REDIS_CACHE_IMPORT_UIDS):
        if uid not in committed:
            raise AlertRouteError(f"committed import alert {uid} is missing")
        rules[uid] = committed[uid]
    # Gate-file UIDs, including the resilience finalization set, share this
    # import. Canaries stay first so their read-back still precedes KeepLast.
    for uid in load_gated_uids(committed):
        if uid not in rules:
            rules[uid] = committed[uid]
    if not production:
        rules = _development_rules(rules)
    for uid in canary_uids:
        canary = rules[uid]
        if (
            canary.get("execErrState") != "Alerting"
            or canary.get("noDataState") != "Alerting"
            or canary.get("isPaused") is not False
        ):
            raise AlertRouteError(f"datasource canary {uid} must be active and page on errors and no data")
    for uid, rule in rules.items():
        labels = rule.get("labels")
        if not isinstance(labels, dict) or labels.get("alert_identity") != uid:
            raise AlertRouteError(f"live-STT alert {uid} has an invalid alert_identity label")
        if _receiver(rule) != TELEGRAM_RECEIVER:
            raise AlertRouteError(f"live-STT alert {uid} does not route to the verified Telegram receiver")
    return rules


def _has_telegram_receiver(contact_points: Any, receiver: str) -> bool:
    return isinstance(contact_points, list) and any(
        isinstance(point, dict)
        and point.get("name") == receiver
        and str(point.get("type", "")).lower() == "telegram"
        and point.get("disableResolveMessage") is not True
        for point in contact_points
    )


def _run_live_stt_import(grafana_url: str, token: str) -> list[str]:
    rules = load_live_stt_import_rules(production=grafana_url == "https://monitor.omi.me")
    canary_uids = tuple(uid for uid in DATASOURCE_CANARY_UIDS if uid in rules)
    live = index_live_rules(
        _request_json(grafana_url, ALERT_RULE_LIST_PATH, token, size_limit=FLEET_LIST_SIZE_LIMIT),
        path=ALERT_RULE_LIST_PATH,
    )
    contacts = _request_json(grafana_url, "/api/v1/provisioning/contact-points", token)
    if not _has_telegram_receiver(contacts, TELEGRAM_RECEIVER):
        return ["verified Telegram alert receiver is missing or resolve notifications are disabled"]
    # Establish and read back the replacement pages before KeepLast reaches any
    # business rule. The GMP canary belongs to its separately deployed datasource.
    for uid in canary_uids:
        _write_rule(grafana_url, uid, rules[uid], token, exists=uid in live)
        print(f"UPSERTED datasource canary {uid}")
    failures = []
    for uid in canary_uids:
        canary = _request_json(grafana_url, f"{ALERT_RULE_LIST_PATH}/{uid}", token)
        if not isinstance(canary, dict):
            failures.append(f"datasource canary {uid} read-back is not an object")
        else:
            failures.extend(rule_definition_errors(uid, canary, rules[uid]))
    if failures:
        return failures
    for uid, rule in rules.items():
        if uid in DATASOURCE_CANARY_UIDS:
            continue
        _write_rule(grafana_url, uid, rule, token, exists=uid in live)
        print(f"UPSERTED live-STT alert {uid}")
    return []


def _development_rules(rules: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    # No verified development sentinel exists. Development keeps error pages
    # instead of KeepLast, on a detached copy so canonical rules never change.
    rules = copy.deepcopy(rules)
    for rule in rules.values():
        if rule.get("execErrState") == "KeepLast":
            rule["execErrState"] = "Error"
    return rules


def _committed_rules() -> dict[str, dict[str, Any]]:
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    by_uid = {rule.get("uid"): rule for rule in rules if isinstance(rule, dict) and isinstance(rule.get("uid"), str)}
    missing = [uid for uid in RULE_UIDS if uid not in by_uid]
    if missing:
        raise AlertRouteError(f"committed finalization alert set is incomplete: {','.join(missing)}")
    return {uid: by_uid[uid] for uid in RULE_UIDS}


def load_all_committed_rules() -> dict[str, dict[str, Any]]:
    by_uid: dict[str, dict[str, Any]] = {}
    for path in sorted(ALERT_SOURCES.glob("*.json")):
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise AlertRouteError(f"committed alert file {path.name} is not a list")
        for item in loaded:
            if not isinstance(item, dict):
                raise AlertRouteError(f"committed alert file {path.name} contains a non-object rule")
            uid = item.get("uid")
            if not isinstance(uid, str) or not uid:
                raise AlertRouteError(f"committed alert file {path.name} contains a rule without a uid")
            if uid in by_uid:
                raise AlertRouteError(f"duplicate committed alert uid {uid}")
            by_uid[uid] = item
    if not by_uid:
        raise AlertRouteError("committed alert exports contain no rules")
    return by_uid


def load_gated_uids(committed: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    loaded: object = json.loads(GATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AlertRouteError("live-alert-gate.json must be an object")
    raw = loaded.get("uids")
    if not isinstance(raw, list) or not raw:
        raise AlertRouteError("live-alert-gate.json uids must be a non-empty list")
    uids: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item:
            raise AlertRouteError("live-alert-gate.json uids must be non-empty strings")
        if item in seen:
            raise AlertRouteError(f"live-alert-gate.json duplicate uid {item}")
        if item not in committed:
            raise AlertRouteError(f"live-alert-gate.json uid {item} is not a committed alert")
        seen.add(item)
        uids.append(item)
    return tuple(uids)


def index_live_rules(payload: object, *, path: str) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        raise AlertRouteError(f"Grafana API returned a non-list payload for {path}")
    by_uid: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise AlertRouteError(f"Grafana API returned a non-object rule for {path}")
        uid = item.get("uid")
        if not isinstance(uid, str) or not uid:
            raise AlertRouteError(f"Grafana API returned a rule without a uid for {path}")
        if uid in by_uid:
            raise AlertRouteError(f"Grafana API returned duplicate uid {uid} for {path}")
        by_uid[uid] = item
    return by_uid


def _receiver(rule: dict[str, Any]) -> Any:
    settings = rule.get("notification_settings", {})
    if not isinstance(settings, dict):
        return None
    return settings.get("receiver")


def _strip_grafana_assigned_query_defaults(live_node: dict[str, Any], expected_node: dict[str, Any]) -> dict[str, Any]:
    """Drop exact Grafana storage defaults that the committed node does not set."""
    node = dict(live_node)
    for key, default in GRAFANA_ASSIGNED_QUERY_DEFAULTS.items():
        if key not in expected_node and node.get(key) == default:
            del node[key]
    expected_model = expected_node.get("model")
    live_model = node.get("model")
    if isinstance(live_model, dict) and isinstance(expected_model, dict):
        model = dict(live_model)
        for key, default in GRAFANA_ASSIGNED_MODEL_DEFAULTS.items():
            if key not in expected_model and model.get(key) == default:
                del model[key]
        node["model"] = model
    return node


def _data_matches_committed(live: Any, expected: Any) -> bool:
    if live == expected:
        return True
    if not isinstance(live, list) or not isinstance(expected, list) or len(live) != len(expected):
        return False
    for live_node, expected_node in zip(live, expected):
        if live_node == expected_node:
            continue
        if not isinstance(live_node, dict) or not isinstance(expected_node, dict):
            return False
        if _strip_grafana_assigned_query_defaults(live_node, expected_node) != expected_node:
            return False
    return True


def mismatched_definition_keys(live: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in DEFINITION_KEYS:
        if key == "data":
            if not _data_matches_committed(live.get(key), expected.get(key)):
                keys.append(key)
            continue
        if live.get(key) != expected.get(key):
            keys.append(key)
    receiver = _receiver(expected)
    if not isinstance(receiver, str) or _receiver(live) != receiver:
        keys.append("receiver")
    return keys


def rule_definition_errors(uid: str, live: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    keys = mismatched_definition_keys(live, expected)
    errors = [f"live alert rule {uid} {key} does not match the committed rule" for key in keys if key != "receiver"]
    if live.get("isPaused") is not False:
        errors.append(f"live alert rule {uid} must be unpaused")
    if "receiver" in keys:
        errors.append(f"live alert rule {uid} receiver does not match the committed route")
    return errors


def classify_fleet_coverage(
    committed: dict[str, dict[str, Any]], live_by_uid: dict[str, dict[str, Any]]
) -> FleetCoverage:
    committed_but_absent: list[str] = []
    present_but_paused: list[str] = []
    present_but_divergent: list[str] = []
    live_and_matching: list[str] = []
    for uid in sorted(committed):
        live = live_by_uid.get(uid)
        if not isinstance(live, dict):
            committed_but_absent.append(uid)
            continue
        keys = mismatched_definition_keys(live, committed[uid])
        paused = live.get("isPaused") is not False
        if paused:
            present_but_paused.append(uid)
        if keys:
            present_but_divergent.append(f"{uid} ({','.join(keys)})")
        if not paused and not keys:
            live_and_matching.append(uid)
    live_but_uncommitted = tuple(sorted(uid for uid in live_by_uid if uid not in committed))
    return FleetCoverage(
        committed_but_absent=tuple(committed_but_absent),
        live_but_uncommitted=live_but_uncommitted,
        present_but_paused=tuple(present_but_paused),
        present_but_divergent=tuple(present_but_divergent),
        live_and_matching=tuple(live_and_matching),
        live_count=len(live_by_uid),
    )


def format_fleet_report(coverage: FleetCoverage, *, committed_count: int, gated_uids: tuple[str, ...]) -> list[str]:
    gated_matching = tuple(uid for uid in gated_uids if uid in coverage.live_and_matching)
    ungated_unproven = committed_count - len(gated_uids)
    lines = [
        (
            f"FLEET committed={committed_count} live={coverage.live_count} gated={len(gated_uids)} "
            f"matching={len(coverage.live_and_matching)} gated_matching={len(gated_matching)}"
        ),
        (
            f"COMMITTED_BUT_ABSENT ({len(coverage.committed_but_absent)}): "
            f"{', '.join(coverage.committed_but_absent) or '-'}"
        ),
        (
            f"LIVE_BUT_UNCOMMITTED ({len(coverage.live_but_uncommitted)}): "
            f"{', '.join(coverage.live_but_uncommitted) or '-'}"
        ),
        (
            f"PRESENT_BUT_PAUSED ({len(coverage.present_but_paused)}): "
            f"{', '.join(coverage.present_but_paused) or '-'}"
        ),
        (
            f"PRESENT_BUT_DIVERGENT ({len(coverage.present_but_divergent)}): "
            f"{', '.join(coverage.present_but_divergent) or '-'}"
        ),
        f"LIVE_AND_MATCHING ({len(coverage.live_and_matching)})",
        (
            "UNPROVEN: live status of ungated committed rules is classified above; "
            f"{ungated_unproven} committed UIDs are outside the fail-closed gate "
            "until live-alert-gate.json is widened after a token-backed proof."
        ),
    ]
    return lines


def _divergent_uid(entry: str) -> str:
    return entry.split(" (", 1)[0]


def fleet_gate_failures(coverage: FleetCoverage, gated_uids: tuple[str, ...], fail_on: str) -> list[str]:
    if fail_on == "none":
        return []
    absent = set(coverage.committed_but_absent)
    paused = set(coverage.present_but_paused)
    divergent = {_divergent_uid(entry): entry for entry in coverage.present_but_divergent}
    uncommitted = set(coverage.live_but_uncommitted)
    uids = gated_uids if fail_on == "gated" else tuple(sorted(absent | paused | set(divergent) | uncommitted))
    failures: list[str] = []
    for uid in uids:
        if uid in uncommitted:
            failures.append(f"live alert rule {uid} is not in the committed exports")
            continue
        if uid in absent:
            failures.append(f"live alert rule {uid} is absent from Grafana")
        if uid in paused:
            failures.append(f"live alert rule {uid} must be unpaused")
        if uid in divergent:
            failures.append(f"live alert rule {divergent[uid]} does not match the committed rule")
    return failures


@dataclass(frozen=True)
class ServingUp:
    by_job: dict[str, str]
    deletion_timestamps_confirmed: bool
    excluded_targets: int


def _query_samples(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    result = data.get("result")
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def _sample_number(item: dict[str, Any]) -> float | None:
    value = item.get("value")
    if not isinstance(value, list) or len(value) != 2:
        return None
    raw = value[1]
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        number = float(raw)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _metric_label(item: dict[str, Any], key: str) -> str | None:
    metric = item.get("metric")
    if not isinstance(metric, dict):
        return None
    value = metric.get(key)
    if not isinstance(value, str) or not value:
        return None
    return value


def confirmed_deleting_pods(
    deletion_query: dict[str, Any] | None,
    ksm_presence_query: dict[str, Any] | None,
) -> tuple[set[tuple[str, str]], bool]:
    """Return namespace/pod pairs with a confirmed deletion timestamp.

    The boolean is false when those pairs cannot be trusted. An empty deletion
    result means "nothing is deleting" only when kube_pod_info is being scraped.
    Without that, kube-state-metrics may be absent, and no down target is excused.
    Samples of kube_pod_deletion_timestamp are themselves confirmation.
    """
    deletion_ok = isinstance(deletion_query, dict) and deletion_query.get("status") == "success"
    pairs: set[tuple[str, str]] = set()
    if deletion_ok:
        for item in _query_samples(deletion_query):
            namespace = _metric_label(item, "namespace")
            pod = _metric_label(item, "pod")
            stamp = _sample_number(item)
            if namespace is None or pod is None or stamp is None or stamp <= 0:
                continue
            pairs.add((namespace, pod))
    if pairs:
        return pairs, True
    ksm_present = False
    for item in _query_samples(ksm_presence_query):
        sample = _sample_number(item)
        if sample is not None and sample > 0:
            ksm_present = True
            break
    if deletion_ok and ksm_present:
        return set(), True
    return set(), False


def serving_up_by_job(
    up_query: dict[str, Any] | None,
    deletion_query: dict[str, Any] | None = None,
    ksm_presence_query: dict[str, Any] | None = None,
) -> ServingUp:
    """min(up) by job over targets whose pod has no confirmed deletion timestamp.

    A job with no remaining series is absent. That keeps a rollout from passing
    when every scraped target for it is terminating. Targets that lack namespace
    and pod labels cannot be matched and stay in the min.
    """
    deleting, confirmed = confirmed_deleting_pods(deletion_query, ksm_presence_query)
    samples: dict[str, list[float]] = {job: [] for job in REQUIRED_JOBS}
    excluded = 0
    for item in _query_samples(up_query):
        job = _metric_label(item, "job")
        if job not in samples:
            continue
        namespace = _metric_label(item, "namespace")
        pod = _metric_label(item, "pod")
        if confirmed and namespace is not None and pod is not None and (namespace, pod) in deleting:
            excluded += 1
            continue
        number = _sample_number(item)
        samples[job].append(0.0 if number is None else number)
    by_job: dict[str, str] = {}
    for job, values in samples.items():
        if not values:
            by_job[job] = "absent"
        elif min(values) >= 1.0:
            by_job[job] = "1"
        else:
            by_job[job] = "0"
    return ServingUp(by_job=by_job, deletion_timestamps_confirmed=confirmed, excluded_targets=excluded)


def validate_live_route(
    live_rules: dict[str, dict[str, Any]],
    datasource: dict[str, Any],
    up_query: dict[str, Any],
    metric_query: dict[str, Any],
    contact_points: Any,
    *,
    phase: str,
    deletion_query: dict[str, Any] | None = None,
    ksm_presence_query: dict[str, Any] | None = None,
    production: bool = True,
) -> list[str]:
    expected_rules = _committed_rules()
    if not production:
        expected_rules = _development_rules(expected_rules)
    errors: list[str] = []
    receivers: set[str] = set()
    for uid, expected in expected_rules.items():
        rule = live_rules.get(uid, {})
        rule_errors = rule_definition_errors(uid, rule, expected)
        errors.extend(rule_errors)
        if not any("receiver does not match" in error for error in rule_errors):
            receiver = _receiver(expected)
            if isinstance(receiver, str):
                receivers.add(receiver)
    if str(datasource.get("status", "")).upper() != "OK":
        errors.append("live Prometheus datasource health is not OK")
    serving = serving_up_by_job(up_query, deletion_query, ksm_presence_query)
    # Every required target already up does not need a deletion timestamp.
    # kube-state-metrics darkness fails this gate only when a down target would
    # otherwise be excused; that down target stays in min(up) and is reported.
    if any(serving.by_job.get(job) != "1" for job in REQUIRED_JOBS):
        observed = ", ".join(f"{job}={serving.by_job.get(job, 'absent')}" for job in sorted(REQUIRED_JOBS))
        detail = ""
        if not serving.deletion_timestamps_confirmed and any(serving.by_job.get(job) == "0" for job in REQUIRED_JOBS):
            detail = (
                "; kube-state-metrics deletion timestamps were not confirmed, "
                "so down targets were not treated as terminating"
            )
        errors.append(
            "current Pusher and backend-listen Prometheus scrape targets are not both healthy"
            f" (observed min(up) by job: {observed}{detail})"
        )
    results = metric_query.get("data", {}).get("result", []) if metric_query.get("status") == "success" else []
    observed_metrics = {
        (item.get("metric", {}).get("__name__"), item.get("metric", {}).get("job"))
        for item in results
        if isinstance(item, dict) and isinstance(item.get("metric"), dict)
    }
    required_metric_jobs = {(metric, job) for metric in REQUIRED_METRICS for job in REQUIRED_JOBS}
    if phase == "postrollout" and observed_metrics != required_metric_jobs:
        errors.append("live Prometheus finalization telemetry sources are missing or incomplete")
    points = contact_points if isinstance(contact_points, list) else []
    for receiver in receivers:
        if not any(
            isinstance(point, dict)
            and point.get("name") == receiver
            and str(point.get("type", "")).lower() == "telegram"
            and point.get("disableResolveMessage") is not True
            for point in points
        ):
            errors.append("committed Telegram receiver is missing or resolve notifications are disabled")
    return errors


def _approved_grafana_url(raw: str) -> bool:
    parsed = urllib.parse.urlparse(raw)
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_HOSTS
        and parsed.path in ("", "/")
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _prometheus_instant_query(base_url: str, token: str, query: str) -> dict[str, Any]:
    path = "/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode({"query": query})
    payload = _request_json(base_url, path, token)
    if not isinstance(payload, dict):
        raise AlertRouteError(f"Grafana API returned a non-object Prometheus payload for {query}")
    return payload


def _prometheus_instant_query_or_error(base_url: str, token: str, query: str) -> dict[str, Any]:
    try:
        return _prometheus_instant_query(base_url, token, query)
    except AlertRouteError:
        return {"status": "error"}


def _run_pusher_gate(grafana_url: str, token: str, phase: str, attempts: int) -> list[str]:
    metric_query_path = "/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode(
        {
            "query": 'count({__name__=~"omi_capture_finalization_failures_total|omi_journey_accepted_total|omi_journey_terminal_total",job=~"pusher-metrics|backend-listen-metrics"}) by (__name__,job)'
        }
    )
    up_query = PREPUBLISH_UP_QUERY if phase == "prepublish" else SERVING_UP_QUERY
    failures: list[str] = []
    for attempt in range(attempts):
        try:
            failures = validate_live_route(
                {
                    uid: _request_json(grafana_url, f"/api/v1/provisioning/alert-rules/{uid}", token)
                    for uid in RULE_UIDS
                },
                _request_json(grafana_url, "/api/datasources/uid/prometheus/health", token),
                _prometheus_instant_query(grafana_url, token, up_query),
                _request_json(grafana_url, metric_query_path, token),
                _request_json(grafana_url, "/api/v1/provisioning/contact-points", token),
                phase=phase,
                deletion_query=_prometheus_instant_query_or_error(grafana_url, token, POD_DELETION_TIMESTAMP_QUERY),
                ksm_presence_query=_prometheus_instant_query_or_error(grafana_url, token, KSM_POD_INFO_COUNT_QUERY),
                production=grafana_url == "https://monitor.omi.me",
            )
        except AlertRouteError as exc:
            # A transient Grafana/Prometheus request failure is retried like a miss.
            failures = [str(exc)]
        if not failures or attempt + 1 == attempts:
            break
        time.sleep(5)
    return failures


def _run_fleet_coverage(
    grafana_url: str, token: str, attempts: int, fail_on: str, *, alert_set: str = "all"
) -> tuple[list[str], list[str]]:
    committed = load_all_committed_rules()
    gated_uids = load_gated_uids(committed)
    if alert_set == "live-stt":
        committed = load_live_stt_import_rules(production=grafana_url == "https://monitor.omi.me")
        canary_uids = tuple(uid for uid in DATASOURCE_CANARY_UIDS if uid in committed)
        gated_uids = tuple(dict.fromkeys((*canary_uids, *(uid for uid in gated_uids if uid in committed))))
    coverage: FleetCoverage | None = None
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            payload = _request_json(grafana_url, ALERT_RULE_LIST_PATH, token, size_limit=FLEET_LIST_SIZE_LIMIT)
            live_by_uid = index_live_rules(payload, path=ALERT_RULE_LIST_PATH)
            if alert_set == "live-stt":
                live_by_uid = {uid: rule for uid, rule in live_by_uid.items() if uid in committed}
            coverage = classify_fleet_coverage(committed, live_by_uid)
            last_error = None
            break
        except AlertRouteError as exc:
            last_error = str(exc)
            if attempt + 1 == attempts:
                break
            time.sleep(5)
    if coverage is None:
        return [last_error or "fleet coverage request failed"], []
    report = format_fleet_report(coverage, committed_count=len(committed), gated_uids=gated_uids)
    return fleet_gate_failures(coverage, gated_uids, fail_on), report


def resolve_attempts(requested: int | None, *, mode: str, phase: str | None) -> int:
    if requested is not None:
        return requested
    return PREPUBLISH_DEFAULT_ATTEMPTS if mode == "pusher" and phase == "prepublish" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--phase", choices=("prepublish", "postrollout"))
    parser.add_argument("--mode", choices=("pusher", "fleet", "import"), default="pusher")
    parser.add_argument("--alert-set", choices=("all", "live-stt"), default="all")
    parser.add_argument("--fail-on", choices=("none", "gated", "all"))
    parser.add_argument(
        "--attempts",
        type=int,
        default=None,
        help=f"default {PREPUBLISH_DEFAULT_ATTEMPTS} for --phase prepublish, otherwise 1",
    )
    args = parser.parse_args()
    if not _approved_grafana_url(args.grafana_url):
        print("FAIL: Grafana URL must be an approved HTTPS monitoring origin")
        return 1
    if args.mode == "pusher" and args.phase is None:
        print("FAIL: pusher mode requires --phase")
        return 1
    if args.mode == "pusher" and args.fail_on is not None:
        print("FAIL: --fail-on is only valid with --mode fleet")
        return 1
    if args.mode != "fleet" and args.alert_set != "all":
        print("FAIL: --alert-set is only valid with --mode fleet")
        return 1
    if args.mode == "import" and args.fail_on is not None:
        print("FAIL: --fail-on is only valid with --mode fleet")
        return 1
    fail_on = "none" if args.mode == "fleet" and args.fail_on is None else args.fail_on
    report_lines: list[str] = []
    try:
        token = _token(args.token_file)
        attempts = resolve_attempts(args.attempts, mode=args.mode, phase=args.phase)
        if attempts < 1 or attempts > 12:
            raise AlertRouteError("attempts must be between 1 and 12")
        if args.mode == "pusher":
            phase = args.phase
            if phase is None:
                raise AlertRouteError("pusher mode requires --phase")
            failures = _run_pusher_gate(args.grafana_url, token, phase, attempts)
        elif args.mode == "import":
            failures = _run_live_stt_import(args.grafana_url, token)
        else:
            if fail_on is None:
                raise AlertRouteError("fleet mode requires --fail-on none, gated, or all")
            failures, report_lines = _run_fleet_coverage(
                args.grafana_url, token, attempts, fail_on, alert_set=args.alert_set
            )
    except (AlertRouteError, OSError, json.JSONDecodeError) as exc:
        failures = [str(exc)]
    for line in report_lines:
        print(line)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    if args.mode == "pusher":
        print(
            "OK: live finalization outcome rules, telemetry sources, datasource, and Telegram routes match the contract."
        )
    elif args.mode == "import":
        print("OK: allowlisted live-STT alert rules were upserted and Telegram routing was verified.")
    else:
        print("OK: fleet Grafana coverage report completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
