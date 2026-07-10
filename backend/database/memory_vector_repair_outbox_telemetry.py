"""Canonical vector repair outbox worker telemetry (WS-G7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, cast

VECTOR_REPAIR_OUTBOX_WORKER_COMPONENT = "vector_repair_outbox_worker"
_ALLOWED_LABEL_KEYS = {"worker_component", "status", "action", "reason", "event_type"}


@dataclass(frozen=True)
class VectorRepairOutboxTelemetryConfig:
    """Low-cardinality telemetry config for the memory vector repair outbox worker.

    This seam intentionally accepts an injected emitter so unit tests, Cloud Run
    log adapters, Prometheus/OpenTelemetry bridges, or alert-rule renderers can
    consume the same deterministic payloads without importing a production metrics
    client here. Labels are bounded and must not contain uid/vector/memory/record
    identifiers.
    """

    enabled: bool = False
    worker_component: str = VECTOR_REPAIR_OUTBOX_WORKER_COMPONENT


def emit_vector_repair_outbox_worker_telemetry(
    *,
    tick_summary: Mapping[str, Any],
    emitter: Callable[[Dict[str, Any]], Any],
    config: VectorRepairOutboxTelemetryConfig,
    backlog: Optional[Mapping[str, Any]] = None,
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Emit low-cardinality metrics/events for one worker tick.

    Emission failures are returned in a deterministic summary and are never raised
    to callers. This preserves the worker cleanup/ack result even when the central
    metrics/log sink is unavailable.
    """
    if not config.enabled:
        return _telemetry_result(enabled=False)

    result = _telemetry_result(enabled=True)
    for payload in _build_vector_repair_outbox_worker_telemetry_payloads(
        tick_summary=tick_summary,
        config=config,
        backlog=backlog or {},
        duration_ms=duration_ms,
    ):
        try:
            emitter(payload)
            result["emitted_count"] += 1
        except Exception as exc:
            result["failed_count"] += 1
            result["errors"].append({"stage": "telemetry", "name": payload["name"], "error": str(exc)})
    return result


def _build_vector_repair_outbox_worker_telemetry_payloads(
    *,
    tick_summary: Mapping[str, Any],
    config: VectorRepairOutboxTelemetryConfig,
    backlog: Mapping[str, Any],
    duration_ms: Optional[int],
) -> List[Dict[str, Any]]:
    labels_base = {"worker_component": _bounded_label(config.worker_component)}
    payloads: List[Dict[str, Any]] = []

    for status, key in (
        ("leased", "leased_count"),
        ("processed", "processed_count"),
        ("skipped", "skipped_count"),
        ("failed", "failed_count"),
    ):
        payloads.append(
            _metric(
                "vector_repair_outbox_worker_records_total",
                _safe_int(tick_summary.get(key)),
                {**labels_base, "status": status},
            )
        )

    action_counts: Dict[str, int] = {"delete": 0, "repair": 0}
    raw_actions = tick_summary.get("actions")
    if isinstance(raw_actions, list):
        actions_list: List[object] = cast(List[object], raw_actions)
        for raw_action in actions_list:
            if not isinstance(raw_action, dict):
                continue
            action_dict: Dict[str, Any] = cast(Dict[str, Any], raw_action)
            action_name = _bounded_action(action_dict.get("action"))
            if action_name in action_counts:
                action_counts[action_name] += 1
    for action_name, count in action_counts.items():
        payloads.append(
            _metric(
                "vector_repair_outbox_worker_action_total",
                count,
                {**labels_base, "action": action_name},
            )
        )

    failed_count = _safe_int(tick_summary.get("failed_count"))
    if failed_count:
        payloads.append(
            _metric(
                "vector_repair_outbox_worker_retry_total",
                failed_count,
                {**labels_base, "reason": _reason_bucket_from_summary(tick_summary)},
            )
        )

    dead_letter_count = _safe_int(backlog.get("dead_letter_count")) + _safe_int(tick_summary.get("dead_letter_count"))
    payloads.append(
        _metric(
            "vector_repair_outbox_worker_dead_letter_total",
            dead_letter_count,
            {**labels_base, "reason": _reason_bucket_from_summary(tick_summary)},
        )
    )
    if dead_letter_count:
        payloads.append(
            _event(
                "vector_repair_outbox_worker_dead_letter",
                {**labels_base, "reason": _reason_bucket_from_summary(tick_summary), "event_type": "threshold_signal"},
                {"dead_letter_count": dead_letter_count},
            )
        )

    ack_failed_count = _safe_int(tick_summary.get("ack_failed_count"))
    payloads.append(
        _metric(
            "vector_repair_outbox_worker_ack_failure_total",
            ack_failed_count,
            {**labels_base, "reason": "ack_failure"},
        )
    )
    if ack_failed_count:
        payloads.append(
            _event(
                "vector_repair_outbox_worker_ack_failure",
                {**labels_base, "reason": "ack_failure", "event_type": "threshold_signal"},
                {"ack_failed_count": ack_failed_count},
            )
        )

    for status, key in (("pending", "pending_count"), ("dead_letter", "dead_letter_count")):
        payloads.append(
            _metric(
                "vector_repair_outbox_worker_backlog_count",
                _safe_int(backlog.get(key)),
                {**labels_base, "status": status},
            )
        )
    if "oldest_pending_age_seconds" in backlog:
        payloads.append(
            _metric(
                "vector_repair_outbox_worker_oldest_pending_age_seconds",
                _safe_int(backlog.get("oldest_pending_age_seconds")),
                {**labels_base, "status": "pending"},
            )
        )
    if duration_ms is not None:
        payloads.append(
            _metric(
                "vector_repair_outbox_worker_duration_ms",
                _safe_int(duration_ms),
                {**labels_base, "status": "tick"},
            )
        )

    return [_sanitize_payload(payload) for payload in payloads]


def _metric(name: str, value: int, labels: Dict[str, str]) -> Dict[str, Any]:
    return {"kind": "metric", "name": name, "value": value, "labels": labels}


def _event(name: str, labels: Dict[str, str], fields: Dict[str, Any]) -> Dict[str, Any]:
    return {"kind": "event", "name": name, "labels": labels, "fields": dict(fields)}


def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_labels = payload.get("labels")
    labels: Dict[str, Any] = cast(Dict[str, Any], raw_labels) if isinstance(raw_labels, dict) else {}
    payload["labels"] = {str(key): _bounded_label(value) for key, value in labels.items() if key in _ALLOWED_LABEL_KEYS}
    return payload


def _reason_bucket_from_summary(tick_summary: Mapping[str, Any]) -> str:
    raw_errors = tick_summary.get("errors")
    if isinstance(raw_errors, list):
        errors_list: List[object] = cast(List[object], raw_errors)
        for raw_error in errors_list:
            if not isinstance(raw_error, dict):
                continue
            error_dict: Dict[str, Any] = cast(Dict[str, Any], raw_error)
            stage = _bounded_label(error_dict.get("stage"))
            if stage in {"ack", "lease", "dependencies", "config", "tick"}:
                return f"{stage}_failure"
    if _safe_int(tick_summary.get("failed_count")):
        return "worker_failure"
    return "none"


def _bounded_action(raw: Any) -> str:
    value = str(raw or "unknown")
    if value in {"delete", "repair"}:
        return value
    return "unknown"


def _bounded_label(raw: Any) -> str:
    value = str(raw or "unknown").strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(ch for ch in value if ch.isalnum() or ch == "_")[:64] or "unknown"


def _safe_int(raw: Any) -> int:
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def _telemetry_result(*, enabled: bool) -> Dict[str, Any]:
    return {"enabled": enabled, "emitted_count": 0, "failed_count": 0, "errors": []}


__all__ = [
    "VectorRepairOutboxTelemetryConfig",
    "VECTOR_REPAIR_OUTBOX_WORKER_COMPONENT",
    "emit_vector_repair_outbox_worker_telemetry",
]
