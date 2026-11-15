"""Durable record of the projection inputs a missing-input repair must not change.

The original intake context lives only inside the staged audio, which is the
artifact a repair replaces. Admission therefore records the fields projection
uses to choose a conversation, exactly as frozen into that audio, plus each
unit's frozen language decision, beside the immutable intake record. A repair
restages with these recorded values; it never re-derives either from the
retried request, whose clock bounds the router re-normalizes against the
current server time (Luna r2).
"""

import json

LINEAGE_KEYS = (
    'recording_session_id',
    'audio_start_seconds',
    'audio_end_seconds',
    'geolocation',
    'capture_evidence_claims',
)
LANGUAGE_KEYS = ('stt_language', 'stt_language_evidence', 'stt_language_confidence', 'stt_language_probe_seconds')


def lineage_record(context: dict | None) -> str:
    """Canonical JSON: Firestore rejects nested arrays that capture claims may hold."""
    payload = {key: (context or {}).get(key) for key in LINEAGE_KEYS}
    return json.dumps(payload, allow_nan=False, sort_keys=True, separators=(',', ':'))


def recorded_lineage(record: str) -> dict:
    payload = json.loads(record)
    if not isinstance(payload, dict) or set(payload) != set(LINEAGE_KEYS):
        raise ValueError('recorded lineage has the wrong shape')
    return payload


def language_proof(language: str, decision) -> dict:
    """The frozen language fields of one staged unit, as admission records them for a later repair."""
    return {
        'stt_language': language,
        'stt_language_evidence': decision.evidence,
        'stt_language_confidence': decision.confidence,
        'stt_language_probe_seconds': decision.probe_seconds,
    }
