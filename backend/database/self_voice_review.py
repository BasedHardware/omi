from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db, document_id_from_seed

CANDIDATES_COLLECTION = 'self_voice_review_candidates'
NEGATIVE_MARKERS_COLLECTION = 'self_voice_review_negative_markers'
CONFIRMED_SAMPLES_COLLECTION = 'self_voice_review_confirmed_samples'
DEFAULT_CANDIDATE_TTL_DAYS = 30
FORBIDDEN_CANDIDATE_KEYS = {'text', 'transcript', 'transcript_text', 'words', 'utterances', 'audio_bytes', 'raw_audio'}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def candidate_id_from_source(conversation_id: str, provider_cluster_id: str, segment_ids: list[str]) -> str:
    seed = ':'.join(['self_voice_review', conversation_id, provider_cluster_id, ','.join(sorted(segment_ids))])
    return document_id_from_seed(seed)


def marker_id_from_source(conversation_id: str, provider_cluster_id: str) -> str:
    return document_id_from_seed(':'.join(['self_voice_negative_marker', conversation_id, provider_cluster_id]))


def _user_ref(uid: str):
    return db.collection('users').document(uid)


def _candidate_ref(uid: str, candidate_id: str):
    return _user_ref(uid).collection(CANDIDATES_COLLECTION).document(candidate_id)


def _negative_marker_ref(uid: str, marker_id: str):
    return _user_ref(uid).collection(NEGATIVE_MARKERS_COLLECTION).document(marker_id)


def _confirmed_sample_ref(uid: str, sample_id: str):
    return _user_ref(uid).collection(CONFIRMED_SAMPLES_COLLECTION).document(sample_id)


def get_candidate(uid: str, candidate_id: str) -> Optional[dict[str, Any]]:
    snapshot = _candidate_ref(uid, candidate_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    data.setdefault('candidate_id', snapshot.id)
    return data


def has_negative_marker(uid: str, marker_id: str) -> bool:
    return _negative_marker_ref(uid, marker_id).get().exists


def recently_shown_source_exists(
    uid: str,
    conversation_id: str,
    provider_cluster_id: str,
    now: Optional[datetime] = None,
) -> bool:
    now = now or utc_now()
    query = (
        _user_ref(uid)
        .collection(CANDIDATES_COLLECTION)
        .where(filter=FieldFilter('source.conversation_id', '==', conversation_id))
        .where(filter=FieldFilter('source.provider_cluster_id', '==', provider_cluster_id))
        .where(filter=FieldFilter('cooldown_until', '>', now))
        .limit(1)
    )
    return bool(list(query.stream()))


def upsert_candidate(uid: str, candidate: dict[str, Any]) -> bool:
    candidate_id = candidate['candidate_id']
    ref = _candidate_ref(uid, candidate_id)
    if ref.get().exists:
        return False

    now = candidate.get('created_at') or utc_now()
    payload = {
        **candidate,
        'uid': uid,
        'review_status': candidate.get('review_status', 'pending'),
        'created_at': now,
        'updated_at': now,
        'expires_at': candidate.get('expires_at') or now + timedelta(days=DEFAULT_CANDIDATE_TTL_DAYS),
    }
    _reject_forbidden_candidate_keys(payload)
    ref.set(payload, merge=False)
    return True


def list_pending_candidates(uid: str, limit: int = 20, confidence_bucket: Optional[str] = None) -> list[dict[str, Any]]:
    query = _user_ref(uid).collection(CANDIDATES_COLLECTION).where(filter=FieldFilter('review_status', '==', 'pending'))
    if confidence_bucket:
        query = query.where(filter=FieldFilter('confidence_bucket', '==', confidence_bucket))
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)

    candidates = []
    for snapshot in query.stream():
        data = snapshot.to_dict() or {}
        data.setdefault('candidate_id', snapshot.id)
        candidates.append(data)
    return candidates


def mark_candidate_confirmed(
    uid: str,
    candidate_id: str,
    embedding_version: str,
    reviewed_at: Optional[datetime] = None,
) -> None:
    reviewed_at = reviewed_at or utc_now()
    _candidate_ref(uid, candidate_id).update(
        {
            'review_status': 'confirmed',
            'reviewed_at': reviewed_at,
            'negative_review_marker': None,
            'updated_at': reviewed_at,
            'confirmed_sample': {
                'candidate_id': candidate_id,
                'embedding_version': embedding_version,
                'confirmed_at': reviewed_at,
                'revisable': True,
            },
        }
    )
    _confirmed_sample_ref(uid, candidate_id).set(
        {
            'candidate_id': candidate_id,
            'source': 'self_voice_review',
            'embedding_version': embedding_version,
            'confirmed_at': reviewed_at,
            'deleted_at': None,
        },
        merge=True,
    )


def mark_candidate_rejected(
    uid: str,
    candidate: dict[str, Any],
    reviewed_at: Optional[datetime] = None,
) -> str:
    reviewed_at = reviewed_at or utc_now()
    source = candidate.get('source') or {}
    marker_id = marker_id_from_source(source.get('conversation_id', ''), source.get('provider_cluster_id', ''))
    marker = {
        'marker_id': marker_id,
        'candidate_id': candidate['candidate_id'],
        'conversation_id': source.get('conversation_id'),
        'provider_cluster_id': source.get('provider_cluster_id'),
        'segment_ids': source.get('segment_ids', []),
        'negative_review': True,
        'reviewed_at': reviewed_at,
    }
    _negative_marker_ref(uid, marker_id).set(marker, merge=True)
    _candidate_ref(uid, candidate['candidate_id']).update(
        {
            'review_status': 'rejected',
            'reviewed_at': reviewed_at,
            'negative_review_marker': marker,
            'updated_at': reviewed_at,
        }
    )
    return marker_id


def mark_candidate_skipped(
    uid: str,
    candidate_id: str,
    cooldown_until: datetime,
    reviewed_at: Optional[datetime] = None,
) -> None:
    reviewed_at = reviewed_at or utc_now()
    _candidate_ref(uid, candidate_id).update(
        {
            'review_status': 'pending',
            'last_review_action': 'skipped',
            'reviewed_at': reviewed_at,
            'cooldown_until': cooldown_until,
            'updated_at': reviewed_at,
        }
    )


def delete_confirmed_sample(uid: str, candidate_id: str, deleted_at: Optional[datetime] = None) -> bool:
    deleted_at = deleted_at or utc_now()
    candidate = get_candidate(uid, candidate_id)
    if not candidate or candidate.get('review_status') != 'confirmed':
        return False
    _candidate_ref(uid, candidate_id).update(
        {
            'review_status': 'deleted',
            'reviewed_at': deleted_at,
            'updated_at': deleted_at,
            'confirmed_sample.deleted_at': deleted_at,
        }
    )
    _confirmed_sample_ref(uid, candidate_id).set({'deleted_at': deleted_at}, merge=True)
    return True


def _reject_forbidden_candidate_keys(payload: dict[str, Any]) -> None:
    forbidden = _find_forbidden_candidate_keys(payload)
    if forbidden:
        raise ValueError(f'self voice review candidate contains forbidden keys: {sorted(forbidden)}')


def _find_forbidden_candidate_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CANDIDATE_KEYS & set(value)
        for nested in value.values():
            forbidden.update(_find_forbidden_candidate_keys(nested))
        return forbidden
    if isinstance(value, list):
        forbidden = set()
        for nested in value:
            forbidden.update(_find_forbidden_candidate_keys(nested))
        return forbidden
    return set()
