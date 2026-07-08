"""Canonical vector search telemetry module (WS-G8a).

Neutral ``vector_search_telemetry`` is the source of truth. Legacy
Canonical vector search telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, cast

VECTOR_SEARCH_COMPONENT = 'vector_search'
_ALLOWED_LABEL_KEYS = {'component', 'consumer', 'surface', 'mode', 'status', 'reason', 'event_type'}


@dataclass(frozen=True)
class VectorSearchTelemetryConfig:
    """Fake-injectable low-cardinality telemetry config for hydrated memory vector search.

    This seam deliberately builds deterministic payloads and accepts an injected
    emitter instead of importing a production metrics client. Payload labels are
    bounded to static buckets and must not include uid, memory_id, vector_id, raw
    query text, raw error text, idempotency keys, or other high-cardinality values.
    """

    enabled: bool = False
    component: str = VECTOR_SEARCH_COMPONENT
    consumer: str = 'unknown'
    surface: str = 'default_vector_search'
    mode: str = 'default'


def emit_memory_vector_search_telemetry(
    *,
    search_summary: Mapping[str, Any],
    emitter: Callable[[Dict[str, Any]], Any],
    config: VectorSearchTelemetryConfig,
) -> Dict[str, Any]:
    """Emit low-cardinality metrics/events for one hydrated memory vector search.

    Emitter failures are returned in a deterministic summary and never raised, so
    telemetry outages do not mask a successfully fail-closed/filtered search result.
    """
    if not config.enabled:
        return _telemetry_result(enabled=False)

    result = _telemetry_result(enabled=True)
    for payload in _build_memory_vector_search_telemetry_payloads(search_summary=search_summary, config=config):
        try:
            emitter(payload)
            result['emitted_count'] += 1
        except Exception as exc:
            result['failed_count'] += 1
            result['errors'].append({'stage': 'telemetry', 'name': payload['name'], 'error': str(exc)})
    return result


def _build_memory_vector_search_telemetry_payloads(
    *, search_summary: Mapping[str, Any], config: VectorSearchTelemetryConfig
) -> List[Dict[str, Any]]:
    labels_base = {
        'component': _bounded_label(config.component),
        'consumer': _bounded_label(config.consumer),
        'surface': _bounded_label(config.surface),
        'mode': _bounded_label(config.mode),
    }
    payloads = [
        _metric(
            'vector_search_candidates_total',
            _safe_int(search_summary.get('queried_candidate_count')),
            {**labels_base, 'status': 'queried'},
        ),
        _metric(
            'vector_search_candidates_total',
            _safe_int(search_summary.get('hydrated_candidate_count')),
            {**labels_base, 'status': 'hydrated'},
        ),
        _metric(
            'vector_search_candidates_total',
            _safe_int(search_summary.get('vector_rejected_count')),
            {**labels_base, 'status': 'vector_rejected'},
        ),
        _metric(
            'vector_search_result_count',
            _safe_int(search_summary.get('returned_count')),
            {**labels_base, 'status': 'returned'},
        ),
        _metric(
            'vector_search_queries_total',
            _safe_int(search_summary.get('vector_query_count')),
            {**labels_base, 'status': 'attempted'},
        ),
        _metric(
            'vector_search_candidate_request_limit',
            _safe_int(search_summary.get('candidate_request_limit')),
            {**labels_base, 'status': 'bounded'},
        ),
        _metric(
            'vector_search_candidate_budget',
            _safe_int(search_summary.get('candidate_budget')),
            {**labels_base, 'status': 'bounded'},
        ),
        _metric(
            'vector_search_control_exhausted_total',
            int(bool(search_summary.get('vector_query_budget_exhausted'))),
            {**labels_base, 'reason': 'vector_query_budget_exhausted'},
        ),
        _metric(
            'vector_search_control_exhausted_total',
            int(bool(search_summary.get('hydration_read_budget_exhausted'))),
            {**labels_base, 'reason': 'hydration_read_budget_exhausted'},
        ),
        _metric(
            'vector_search_timeout_exhausted_total',
            int(bool(search_summary.get('timeout_exhausted'))),
            {**labels_base, 'status': 'exhausted'},
        ),
    ]

    for reason, key in (
        ('missing_authoritative_item', 'hydration_rejected_missing_count'),
        ('stale_projection', 'hydration_rejected_stale_projection_count'),
        ('stale_vector', 'hydration_rejected_stale_vector_count'),
        ('access_denied', 'hydration_rejected_access_denied_count'),
    ):
        payloads.append(
            _metric(
                'vector_search_hydration_rejects_total',
                _safe_int(search_summary.get(key)),
                {**labels_base, 'reason': reason},
            )
        )

    empty_after_hydration = int(
        _safe_int(search_summary.get('queried_candidate_count')) > 0
        and _safe_int(search_summary.get('returned_count')) == 0
    )
    payloads.append(
        _metric(
            'vector_search_empty_after_hydration_total',
            empty_after_hydration,
            {**labels_base, 'status': 'empty_after_hydration'},
        )
    )
    if empty_after_hydration:
        payloads.append(
            _event(
                'vector_search_empty_after_hydration',
                {**labels_base, 'event_type': 'threshold_signal'},
                {
                    'queried_candidate_count': _safe_int(search_summary.get('queried_candidate_count')),
                    'hydrated_candidate_count': _safe_int(search_summary.get('hydrated_candidate_count')),
                    'returned_count': 0,
                },
            )
        )

    budget_exhausted = int(bool(search_summary.get('candidate_budget_exhausted')))
    payloads.append(
        _metric(
            'vector_search_budget_exhausted_total',
            budget_exhausted,
            {**labels_base, 'status': 'exhausted'},
        )
    )
    if budget_exhausted:
        payloads.append(
            _event(
                'vector_search_budget_exhausted',
                {**labels_base, 'event_type': 'threshold_signal'},
                {
                    'candidate_budget': _safe_int(search_summary.get('candidate_budget')),
                    'candidate_request_limit': _safe_int(search_summary.get('candidate_request_limit')),
                    'returned_count': _safe_int(search_summary.get('returned_count')),
                },
            )
        )

    for reason in ('vector_query_budget_exhausted', 'hydration_read_budget_exhausted'):
        if bool(search_summary.get(reason)):
            payloads.append(
                _event(
                    'vector_search_control_exhausted',
                    {**labels_base, 'event_type': 'threshold_signal', 'reason': reason},
                    {
                        'vector_query_count': _safe_int(search_summary.get('vector_query_count')),
                        'candidate_hydration_read_count': _safe_int(
                            search_summary.get('candidate_hydration_read_count')
                        ),
                        'returned_count': _safe_int(search_summary.get('returned_count')),
                    },
                )
            )

    if bool(search_summary.get('timeout_exhausted')):
        payloads.append(
            _event(
                'vector_search_timeout_exhausted',
                {**labels_base, 'event_type': 'threshold_signal'},
                {
                    'vector_query_count': _safe_int(search_summary.get('vector_query_count')),
                    'candidate_hydration_read_count': _safe_int(search_summary.get('candidate_hydration_read_count')),
                    'returned_count': _safe_int(search_summary.get('returned_count')),
                },
            )
        )

    return [_sanitize_payload(payload) for payload in payloads]


def _metric(name: str, value: int, labels: Dict[str, str]) -> Dict[str, Any]:
    return {'kind': 'metric', 'name': name, 'value': value, 'labels': labels}


def _event(name: str, labels: Dict[str, str], fields: Dict[str, Any]) -> Dict[str, Any]:
    return {'kind': 'event', 'name': name, 'labels': labels, 'fields': dict(fields)}


def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_labels = payload.get('labels')
    labels: Mapping[str, Any]
    if isinstance(raw_labels, Mapping):
        labels = cast(Mapping[str, Any], raw_labels)
    else:
        labels = {}
    payload['labels'] = {key: _bounded_label(value) for key, value in labels.items() if key in _ALLOWED_LABEL_KEYS}
    return payload


def _bounded_label(raw: Any) -> str:
    value = str(raw or 'unknown').strip().lower().replace(' ', '_').replace('-', '_')
    return ''.join(ch for ch in value if ch.isalnum() or ch == '_')[:64] or 'unknown'


def _safe_int(raw: Any) -> int:
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def _telemetry_result(*, enabled: bool) -> Dict[str, Any]:
    return {'enabled': enabled, 'emitted_count': 0, 'failed_count': 0, 'errors': []}


__all__ = [
    "VectorSearchTelemetryConfig",
    "VECTOR_SEARCH_COMPONENT",
    "emit_memory_vector_search_telemetry",
]
