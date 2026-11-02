"""Durable proof of the projection inputs a missing-input repair must not change.

The original intake context lives only inside the staged audio, which is the
artifact a repair replaces. Admission therefore records a digest of the fields
projection uses to choose a conversation, plus each unit's frozen language
decision, beside the immutable intake record. A repair matches them exactly or
holds; it never re-derives either from the retried request.
"""

import hashlib
import json

LINEAGE_KEYS = (
    'recording_session_id',
    'audio_start_seconds',
    'audio_end_seconds',
    'geolocation',
    'capture_evidence_claims',
)
LANGUAGE_KEYS = ('stt_language', 'stt_language_evidence', 'stt_language_confidence', 'stt_language_probe_seconds')


def lineage_digest(context: dict | None) -> str:
    payload = {key: (context or {}).get(key) for key in LINEAGE_KEYS}
    body = json.dumps(payload, allow_nan=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(body.encode()).hexdigest()
