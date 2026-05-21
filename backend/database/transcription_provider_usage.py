from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from utils.metrics import (
    identity_confidence_bucket,
    observe_transcription_provider_audio_seconds,
    observe_transcription_provider_fallback,
    observe_transcription_provider_identity_confidence,
    observe_transcription_provider_request,
    observe_transcription_provider_retry,
    observe_transcription_provider_speaker_clusters,
)

RUNS_COLLECTION = 'transcription_provider_runs'
DAILY_USAGE_COLLECTION = 'transcription_provider_usage_daily'
RUN_TTL_DAYS = 180

FORBIDDEN_LEDGER_KEYS = {
    'audio_bytes',
    'audio',
    'raw_audio_bytes',
    'text',
    'transcript',
    'transcript_text',
    'words',
    'word_records',
    'chunks',
    'utterances',
}


def utc_day_bucket(value: Optional[datetime] = None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime('%Y-%m-%d')


def _safe_doc_id_part(value: str) -> str:
    return str(value or 'unknown').replace('/', '_')


def daily_rollup_doc_id(day: str, provider: str, model: str, workload: str) -> str:
    return ':'.join(
        [
            _safe_doc_id_part(day),
            _safe_doc_id_part(provider),
            _safe_doc_id_part(model),
            _safe_doc_id_part(workload),
        ]
    )


def _run_ref(run_id: str):
    return db.collection(RUNS_COLLECTION).document(run_id)


def _rollup_ref(day: str, provider: str, model: str, workload: str):
    return db.collection(DAILY_USAGE_COLLECTION).document(daily_rollup_doc_id(day, provider, model, workload))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ttl_expires_at(now: datetime) -> datetime:
    return now + timedelta(days=RUN_TTL_DAYS)


def _reject_forbidden_payload_keys(payload: dict[str, Any]) -> None:
    forbidden = _find_forbidden_payload_keys(payload)
    if forbidden:
        raise ValueError(f'transcription provider ledger payload contains forbidden keys: {sorted(forbidden)}')


def _find_forbidden_payload_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_LEDGER_KEYS & set(value)
        for nested in value.values():
            forbidden.update(_find_forbidden_payload_keys(nested))
        return forbidden
    if isinstance(value, list):
        forbidden = set()
        for nested in value:
            forbidden.update(_find_forbidden_payload_keys(nested))
        return forbidden
    return set()


def create_provider_run(
    uid: str,
    provider: str,
    model: str,
    workload: str,
    run_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    provider_job_ref: Optional[str] = None,
    artifact_refs: Optional[dict[str, str]] = None,
    started_at: Optional[datetime] = None,
) -> str:
    run_id = run_id or str(uuid4())
    now = _utc_now()
    started_at = started_at or now
    payload = {
        'run_id': run_id,
        'uid': uid,
        'conversation_id': conversation_id,
        'provider': provider,
        'model': model,
        'workload': workload,
        'status': 'started',
        'provider_job_ref': provider_job_ref,
        'artifact_refs': artifact_refs or {},
        'timing': {
            'started_at': started_at,
            'completed_at': None,
            'latency_ms': None,
        },
        'raw_audio_seconds': 0.0,
        'speech_active_seconds': 0.0,
        'billable_seconds': 0.0,
        'estimated_cost_usd': 0.0,
        'retry_count': 0,
        'fallback_count': 0,
        'transcript_segment_count': 0,
        'transcript_word_count': 0,
        'speaker_cluster_count': 0,
        'identified_speaker_cluster_count': 0,
        'provider_speaker_count': 0,
        'mapped_speaker_count': 0,
        'mapped_person_count': 0,
        'unmapped_speaker_count': 0,
        'embedding_extraction_failure_count': 0,
        'identity_metric_update': {
            'status': 'pending',
            'skipped_reason': None,
            'updated_at': None,
        },
        'identity_confidence_summary': {},
        'error_class': None,
        'created_at': now,
        'updated_at': now,
        'expires_at': _ttl_expires_at(now),
    }
    _reject_forbidden_payload_keys(payload)
    _run_ref(run_id).set(payload, merge=False)
    return run_id


def finalize_provider_run(
    run_id: str,
    provider: str,
    model: str,
    workload: str,
    status: str,
    started_at: datetime,
    completed_at: Optional[datetime] = None,
    raw_audio_seconds: float = 0.0,
    speech_active_seconds: float = 0.0,
    billable_seconds: float = 0.0,
    estimated_cost_usd: float = 0.0,
    retry_count: int = 0,
    fallback_count: int = 0,
    transcript_segment_count: int = 0,
    transcript_word_count: int = 0,
    speaker_cluster_count: int = 0,
    identified_speaker_cluster_count: int = 0,
    provider_speaker_count: int = 0,
    mapped_speaker_count: int = 0,
    mapped_person_count: int = 0,
    unmapped_speaker_count: int = 0,
    embedding_extraction_failure_count: int = 0,
    identity_confidence_summary: Optional[dict[str, Any]] = None,
    error_class: Optional[str] = None,
    artifact_refs: Optional[dict[str, str]] = None,
    fallback_provider: Optional[str] = None,
    fallback_reason: str = 'provider_failure',
) -> None:
    completed_at = completed_at or _utc_now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    latency_seconds = max((completed_at - started_at).total_seconds(), 0.0)
    summary = identity_confidence_summary or {}
    payload = {
        'status': status,
        'timing': {
            'started_at': started_at,
            'completed_at': completed_at,
            'latency_ms': int(latency_seconds * 1000),
        },
        'raw_audio_seconds': raw_audio_seconds,
        'speech_active_seconds': speech_active_seconds,
        'billable_seconds': billable_seconds,
        'estimated_cost_usd': estimated_cost_usd,
        'retry_count': retry_count,
        'fallback_count': fallback_count,
        'transcript_segment_count': transcript_segment_count,
        'transcript_word_count': transcript_word_count,
        'speaker_cluster_count': speaker_cluster_count,
        'identified_speaker_cluster_count': identified_speaker_cluster_count,
        'provider_speaker_count': provider_speaker_count,
        'mapped_speaker_count': mapped_speaker_count,
        'mapped_person_count': mapped_person_count,
        'unmapped_speaker_count': unmapped_speaker_count,
        'embedding_extraction_failure_count': embedding_extraction_failure_count,
        'identity_confidence_summary': summary,
        'error_class': error_class,
        'artifact_refs': artifact_refs or {},
        'fallback': _fallback_details(
            fallback_count=fallback_count,
            from_provider=fallback_provider,
            to_provider=provider,
            reason=fallback_reason,
        ),
        'updated_at': completed_at,
    }
    _reject_forbidden_payload_keys(payload)
    _run_ref(run_id).set(payload, merge=True)
    increment_daily_rollup(
        day=utc_day_bucket(completed_at),
        provider=provider,
        model=model,
        workload=workload,
        status=status,
        raw_audio_seconds=raw_audio_seconds,
        speech_active_seconds=speech_active_seconds,
        billable_seconds=billable_seconds,
        estimated_cost_usd=estimated_cost_usd,
        retry_count=retry_count,
        fallback_count=fallback_count,
        transcript_segment_count=transcript_segment_count,
        transcript_word_count=transcript_word_count,
        speaker_cluster_count=speaker_cluster_count,
        identified_speaker_cluster_count=identified_speaker_cluster_count,
        provider_speaker_count=provider_speaker_count,
        mapped_speaker_count=mapped_speaker_count,
        mapped_person_count=mapped_person_count,
        unmapped_speaker_count=unmapped_speaker_count,
        embedding_extraction_failure_count=embedding_extraction_failure_count,
        identity_confidence_summary=summary,
    )
    emit_provider_run_metrics(
        provider=provider,
        model=model,
        workload=workload,
        status=status,
        latency_seconds=latency_seconds,
        raw_audio_seconds=raw_audio_seconds,
        speech_active_seconds=speech_active_seconds,
        billable_seconds=billable_seconds,
        retry_count=retry_count,
        fallback_count=fallback_count,
        fallback_provider=fallback_provider,
        fallback_reason=fallback_reason,
        speaker_cluster_count=speaker_cluster_count,
        identified_speaker_cluster_count=identified_speaker_cluster_count,
        identity_confidence_summary=summary,
    )


def _fallback_details(
    fallback_count: int,
    from_provider: Optional[str],
    to_provider: str,
    reason: str,
) -> Optional[dict[str, Any]]:
    if fallback_count <= 0:
        return None
    return {
        'from_provider': from_provider or 'unknown',
        'to_provider': to_provider,
        'reason': reason,
    }


def increment_daily_rollup(
    day: str,
    provider: str,
    model: str,
    workload: str,
    status: str,
    raw_audio_seconds: float = 0.0,
    speech_active_seconds: float = 0.0,
    billable_seconds: float = 0.0,
    estimated_cost_usd: float = 0.0,
    retry_count: int = 0,
    fallback_count: int = 0,
    transcript_segment_count: int = 0,
    transcript_word_count: int = 0,
    speaker_cluster_count: int = 0,
    identified_speaker_cluster_count: int = 0,
    provider_speaker_count: int = 0,
    mapped_speaker_count: int = 0,
    mapped_person_count: int = 0,
    unmapped_speaker_count: int = 0,
    embedding_extraction_failure_count: int = 0,
    identity_confidence_summary: Optional[dict[str, Any]] = None,
) -> None:
    update = {
        'day': day,
        'provider': provider,
        'model': model,
        'workload': workload,
        'run_count': firestore.Increment(1),
        f'status_counts.{status}': firestore.Increment(1),
        'raw_audio_seconds': firestore.Increment(raw_audio_seconds),
        'speech_active_seconds': firestore.Increment(speech_active_seconds),
        'billable_seconds': firestore.Increment(billable_seconds),
        'estimated_cost_usd': firestore.Increment(estimated_cost_usd),
        'retry_count': firestore.Increment(retry_count),
        'fallback_count': firestore.Increment(fallback_count),
        'transcript_segment_count': firestore.Increment(transcript_segment_count),
        'transcript_word_count': firestore.Increment(transcript_word_count),
        'speaker_cluster_count': firestore.Increment(speaker_cluster_count),
        'identified_speaker_cluster_count': firestore.Increment(identified_speaker_cluster_count),
        'provider_speaker_count': firestore.Increment(provider_speaker_count),
        'mapped_speaker_count': firestore.Increment(mapped_speaker_count),
        'mapped_person_count': firestore.Increment(mapped_person_count),
        'unmapped_speaker_count': firestore.Increment(unmapped_speaker_count),
        'embedding_extraction_failure_count': firestore.Increment(embedding_extraction_failure_count),
        'last_updated': _utc_now(),
    }
    for bucket, count in (identity_confidence_summary or {}).items():
        if isinstance(count, (int, float)) and count > 0:
            update[f'identity_confidence_counts.{bucket}'] = firestore.Increment(count)
    _rollup_ref(day, provider, model, workload).set(update, merge=True)


def rebuild_daily_rollup_from_runs(day: str, provider: str, model: str, workload: str) -> dict[str, Any]:
    query = (
        db.collection(RUNS_COLLECTION)
        .where(filter=FieldFilter('provider', '==', provider))
        .where(filter=FieldFilter('model', '==', model))
        .where(filter=FieldFilter('workload', '==', workload))
    )
    rollup = _empty_rollup(day, provider, model, workload)
    for doc in query.stream():
        data = doc.to_dict() or {}
        completed_at = (data.get('timing') or {}).get('completed_at')
        if not completed_at or utc_day_bucket(completed_at) != day:
            continue
        _add_run_to_rollup(rollup, data)
    _rollup_ref(day, provider, model, workload).set(rollup, merge=False)
    return rollup


def purge_provider_runs_for_user(uid: str, batch_size: int = 400) -> int:
    deleted = 0
    query = db.collection(RUNS_COLLECTION).where(filter=FieldFilter('uid', '==', uid))
    batch = db.batch()
    pending = 0
    for doc in query.stream():
        batch.delete(doc.reference)
        deleted += 1
        pending += 1
        if pending >= batch_size:
            batch.commit()
            batch = db.batch()
            pending = 0
    if pending:
        batch.commit()
    return deleted


def update_provider_run_identity_metrics(
    run_id: str,
    provider: str,
    model: str,
    workload: str,
    identified_speaker_cluster_count: int,
    identity_confidence_summary: Optional[dict[str, Any]] = None,
    provider_speaker_count: int = 0,
    mapped_speaker_count: int = 0,
    mapped_person_count: int = 0,
    unmapped_speaker_count: int = 0,
    embedding_extraction_failure_count: int = 0,
    identity_metric_update_status: str = 'succeeded',
    identity_metric_update_skipped_reason: Optional[str] = None,
) -> None:
    ref = _run_ref(run_id)
    snapshot = ref.get()
    if not snapshot.exists:
        return
    data = snapshot.to_dict() or {}
    previous_identified = data.get('identified_speaker_cluster_count', 0) or 0
    previous_provider_speakers = data.get('provider_speaker_count', data.get('speaker_cluster_count', 0)) or 0
    previous_mapped_speakers = data.get('mapped_speaker_count', previous_identified) or 0
    previous_mapped_people = data.get('mapped_person_count', 0) or 0
    previous_unmapped_speakers = data.get('unmapped_speaker_count', 0) or 0
    previous_embedding_failures = data.get('embedding_extraction_failure_count', 0) or 0
    previous_summary = data.get('identity_confidence_summary') or {}
    summary = identity_confidence_summary or {}
    completed_at = (data.get('timing') or {}).get('completed_at') or _utc_now()

    ref.set(
        {
            'identified_speaker_cluster_count': identified_speaker_cluster_count,
            'provider_speaker_count': provider_speaker_count,
            'mapped_speaker_count': mapped_speaker_count,
            'mapped_person_count': mapped_person_count,
            'unmapped_speaker_count': unmapped_speaker_count,
            'embedding_extraction_failure_count': embedding_extraction_failure_count,
            'identity_metric_update': {
                'status': identity_metric_update_status,
                'skipped_reason': identity_metric_update_skipped_reason,
                'updated_at': _utc_now(),
            },
            'identity_confidence_summary': summary,
            'updated_at': _utc_now(),
        },
        merge=True,
    )

    rollup_update = {
        'identified_speaker_cluster_count': firestore.Increment(identified_speaker_cluster_count - previous_identified),
        'provider_speaker_count': firestore.Increment(provider_speaker_count - previous_provider_speakers),
        'mapped_speaker_count': firestore.Increment(mapped_speaker_count - previous_mapped_speakers),
        'mapped_person_count': firestore.Increment(mapped_person_count - previous_mapped_people),
        'unmapped_speaker_count': firestore.Increment(unmapped_speaker_count - previous_unmapped_speakers),
        'embedding_extraction_failure_count': firestore.Increment(
            embedding_extraction_failure_count - previous_embedding_failures
        ),
        'last_updated': _utc_now(),
    }
    for bucket in set(previous_summary) | set(summary):
        delta = (summary.get(bucket, 0) or 0) - (previous_summary.get(bucket, 0) or 0)
        if delta:
            rollup_update[f'identity_confidence_counts.{bucket}'] = firestore.Increment(delta)
    _rollup_ref(utc_day_bucket(completed_at), provider, model, workload).set(rollup_update, merge=True)


def emit_provider_run_metrics(
    provider: str,
    model: str,
    workload: str,
    status: str,
    latency_seconds: float,
    raw_audio_seconds: float,
    speech_active_seconds: float,
    billable_seconds: float,
    retry_count: int,
    fallback_count: int,
    speaker_cluster_count: int,
    identified_speaker_cluster_count: int,
    identity_confidence_summary: Optional[dict[str, Any]] = None,
    fallback_provider: Optional[str] = None,
    fallback_reason: str = 'provider_failure',
) -> None:
    observe_transcription_provider_request(provider, model, workload, status, latency_seconds)
    observe_transcription_provider_audio_seconds(
        provider,
        model,
        workload,
        raw_audio_seconds=raw_audio_seconds,
        speech_active_seconds=speech_active_seconds,
        billable_seconds=billable_seconds,
    )
    observe_transcription_provider_retry(provider, model, workload, 'provider_retry', retry_count)
    if fallback_count > 0:
        observe_transcription_provider_fallback(
            fallback_provider or 'unknown',
            provider,
            workload,
            fallback_reason,
            fallback_count,
        )
    observe_transcription_provider_speaker_clusters(
        provider,
        model,
        workload,
        speaker_cluster_count=speaker_cluster_count,
        identified_speaker_cluster_count=identified_speaker_cluster_count,
    )
    for bucket, count in (identity_confidence_summary or {}).items():
        observe_transcription_provider_identity_confidence(provider, model, workload, bucket, count)


def summarize_identity_confidences(confidences: List[Optional[float]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for confidence in confidences:
        bucket = identity_confidence_bucket(confidence)
        summary[bucket] = summary.get(bucket, 0) + 1
    return summary


def _empty_rollup(day: str, provider: str, model: str, workload: str) -> dict[str, Any]:
    return {
        'day': day,
        'provider': provider,
        'model': model,
        'workload': workload,
        'run_count': 0,
        'status_counts': {},
        'raw_audio_seconds': 0.0,
        'speech_active_seconds': 0.0,
        'billable_seconds': 0.0,
        'estimated_cost_usd': 0.0,
        'retry_count': 0,
        'fallback_count': 0,
        'transcript_segment_count': 0,
        'transcript_word_count': 0,
        'speaker_cluster_count': 0,
        'identified_speaker_cluster_count': 0,
        'provider_speaker_count': 0,
        'mapped_speaker_count': 0,
        'mapped_person_count': 0,
        'unmapped_speaker_count': 0,
        'embedding_extraction_failure_count': 0,
        'identity_confidence_counts': {},
        'last_updated': _utc_now(),
    }


def _add_run_to_rollup(rollup: dict[str, Any], data: dict[str, Any]) -> None:
    rollup['run_count'] += 1
    status = data.get('status') or 'unknown'
    rollup['status_counts'][status] = rollup['status_counts'].get(status, 0) + 1
    for field in (
        'raw_audio_seconds',
        'speech_active_seconds',
        'billable_seconds',
        'estimated_cost_usd',
        'retry_count',
        'fallback_count',
        'transcript_segment_count',
        'transcript_word_count',
        'speaker_cluster_count',
        'identified_speaker_cluster_count',
        'provider_speaker_count',
        'mapped_speaker_count',
        'mapped_person_count',
        'unmapped_speaker_count',
        'embedding_extraction_failure_count',
    ):
        rollup[field] += data.get(field, 0) or 0
    for bucket, count in (data.get('identity_confidence_summary') or {}).items():
        rollup['identity_confidence_counts'][bucket] = rollup['identity_confidence_counts'].get(bucket, 0) + count
