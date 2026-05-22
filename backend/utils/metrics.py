from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS = Gauge(
    'backend_listen_active_ws_connections',
    'Number of currently active WebSocket connections in backend-listen',
)

PUSHER_ACTIVE_WS_CONNECTIONS = Gauge(
    'pusher_active_ws_connections',
    'Number of currently active WebSocket connections in pusher',
)

PUSHER_CIRCUIT_BREAKER_STATE = Gauge(
    'pusher_circuit_breaker_state',
    'Pusher circuit breaker state (0=closed, 1=open, 2=half_open)',
)

PUSHER_CIRCUIT_BREAKER_REJECTIONS = Counter(
    'pusher_circuit_breaker_rejections_total',
    'Total pusher connection attempts rejected by circuit breaker',
)

PUSHER_SESSION_DEGRADED = Gauge(
    'pusher_sessions_degraded',
    'Number of sessions currently in degraded mode (pusher unavailable)',
)

TRANSCRIPTION_PROVIDER_REQUESTS = Counter(
    'transcription_provider_requests_total',
    'Total transcription provider requests by provider, model, workload, and status',
    ['provider', 'model', 'workload', 'status'],
)

TRANSCRIPTION_PROVIDER_LATENCY_SECONDS = Histogram(
    'transcription_provider_latency_seconds',
    'Transcription provider request latency by provider, model, workload, and status',
    ['provider', 'model', 'workload', 'status'],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, float('inf')),
)

TRANSCRIPTION_PROVIDER_RETRIES = Counter(
    'transcription_provider_retries_total',
    'Total transcription provider retry attempts by provider, model, workload, and reason',
    ['provider', 'model', 'workload', 'reason'],
)

TRANSCRIPTION_PROVIDER_FALLBACKS = Counter(
    'transcription_provider_fallbacks_total',
    'Total transcription provider fallbacks by from provider, to provider, and workload',
    ['from_provider', 'to_provider', 'workload', 'reason'],
)

TRANSCRIPTION_PROVIDER_AUDIO_SECONDS = Counter(
    'transcription_provider_audio_seconds_total',
    'Total transcription provider audio seconds by provider, model, workload, and kind',
    ['provider', 'model', 'workload', 'kind'],
)

TRANSCRIPTION_PROVIDER_BILLABLE_SECONDS = Counter(
    'transcription_provider_billable_seconds_total',
    'Total transcription provider billable seconds by provider, model, and workload',
    ['provider', 'model', 'workload'],
)

TRANSCRIPTION_PROVIDER_SPEAKER_CLUSTERS = Counter(
    'transcription_provider_speaker_clusters_total',
    'Total transcription provider speaker clusters by provider, model, workload, and kind',
    ['provider', 'model', 'workload', 'kind'],
)

TRANSCRIPTION_PROVIDER_IDENTITY_CONFIDENCE = Counter(
    'transcription_provider_identity_confidence_total',
    'Total speaker identity assignments by provider, model, workload, and confidence bucket',
    ['provider', 'model', 'workload', 'bucket'],
)

TRANSCRIPTION_PROVIDER_ALLOWED_LABELS = {
    'provider',
    'model',
    'workload',
    'status',
    'reason',
    'from_provider',
    'to_provider',
    'kind',
    'bucket',
}

TRANSCRIPTION_PROVIDER_FORBIDDEN_LABELS = {
    'uid',
    'user_id',
    'conversation_id',
    'provider_job_id',
    'transcript',
    'transcript_text',
    'text',
    'run_id',
}


def _provider_metric_labels(**labels: str) -> dict:
    unexpected = set(labels) - TRANSCRIPTION_PROVIDER_ALLOWED_LABELS
    forbidden = set(labels) & TRANSCRIPTION_PROVIDER_FORBIDDEN_LABELS
    if unexpected or forbidden:
        raise ValueError(f'Unsafe transcription provider metric labels: {sorted(unexpected | forbidden)}')
    return {key: str(value or 'unknown') for key, value in labels.items()}


def observe_transcription_provider_request(
    provider: str,
    model: str,
    workload: str,
    status: str,
    latency_seconds: float,
) -> None:
    labels = _provider_metric_labels(provider=provider, model=model, workload=workload, status=status)
    TRANSCRIPTION_PROVIDER_REQUESTS.labels(**labels).inc()
    if latency_seconds >= 0:
        TRANSCRIPTION_PROVIDER_LATENCY_SECONDS.labels(**labels).observe(latency_seconds)


def observe_transcription_provider_retry(provider: str, model: str, workload: str, reason: str, count: int = 1) -> None:
    if count <= 0:
        return
    labels = _provider_metric_labels(provider=provider, model=model, workload=workload, reason=reason)
    TRANSCRIPTION_PROVIDER_RETRIES.labels(**labels).inc(count)


def observe_transcription_provider_fallback(
    from_provider: str,
    to_provider: str,
    workload: str,
    reason: str,
    count: int = 1,
) -> None:
    if count <= 0:
        return
    labels = _provider_metric_labels(
        from_provider=from_provider,
        to_provider=to_provider,
        workload=workload,
        reason=reason,
    )
    TRANSCRIPTION_PROVIDER_FALLBACKS.labels(**labels).inc(count)


def observe_transcription_provider_audio_seconds(
    provider: str,
    model: str,
    workload: str,
    raw_audio_seconds: float = 0.0,
    speech_active_seconds: float = 0.0,
    billable_seconds: float = 0.0,
) -> None:
    for kind, seconds in (
        ('raw', raw_audio_seconds),
        ('speech_active', speech_active_seconds),
        ('billable', billable_seconds),
    ):
        if seconds <= 0:
            continue
        labels = _provider_metric_labels(provider=provider, model=model, workload=workload, kind=kind)
        TRANSCRIPTION_PROVIDER_AUDIO_SECONDS.labels(**labels).inc(seconds)
    if billable_seconds > 0:
        labels = _provider_metric_labels(provider=provider, model=model, workload=workload)
        TRANSCRIPTION_PROVIDER_BILLABLE_SECONDS.labels(**labels).inc(billable_seconds)


def observe_transcription_provider_speaker_clusters(
    provider: str,
    model: str,
    workload: str,
    speaker_cluster_count: int = 0,
    identified_speaker_cluster_count: int = 0,
) -> None:
    for kind, count in (
        ('provider', speaker_cluster_count),
        ('identified', identified_speaker_cluster_count),
    ):
        if count <= 0:
            continue
        labels = _provider_metric_labels(provider=provider, model=model, workload=workload, kind=kind)
        TRANSCRIPTION_PROVIDER_SPEAKER_CLUSTERS.labels(**labels).inc(count)


def identity_confidence_bucket(confidence: Optional[float]) -> str:
    if confidence is None:
        return 'unknown'
    if confidence >= 0.90:
        return 'very_high'
    if confidence >= 0.75:
        return 'high'
    if confidence >= 0.50:
        return 'medium'
    return 'low'


def observe_transcription_provider_identity_confidence(
    provider: str,
    model: str,
    workload: str,
    bucket: str,
    count: int = 1,
) -> None:
    if count <= 0:
        return
    labels = _provider_metric_labels(provider=provider, model=model, workload=workload, bucket=bucket)
    TRANSCRIPTION_PROVIDER_IDENTITY_CONFIDENCE.labels(**labels).inc(count)


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
