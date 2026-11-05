"""Capture-side manifest v1 (plan §6); stage expectations belong to the operator.

    {schema_version, id, tier, scrub, seed_blob_sha256[], created,
     prod_evidence{}, stages{}}

`corpus.json` is always a seed blob. Tier C `blobs/*.enc` contain unmodified
production ciphertext. The owner token in corpus.json must be replaced in memory
from the private UID file at replay time, before deriving keys or checking AAD.
The corpus owner_sha256 pins that UID independently of the salted owner token.
"""

from datetime import datetime, timezone
import hashlib
import json
import re

VERSION = 1
EVIDENCE_ENUMS = {
    'capture_status': {'complete', 'partial', 'refused'},
    'conversation_status': {'in_progress', 'processing', 'completed', 'failed', 'deleted', 'other', 'missing'},
    'finalization_status': {'queued', 'leased', 'completed', 'dead_letter', 'blocked_byok', 'other', 'missing'},
    'speaker_status': {
        'resolved',
        'failed_incomplete_coverage',
        'failed_batch_audio',
        'skipped_budget',
        'failed_unassigned_words',
        'other',
        'missing',
    },
}
BUCKET_KEYS = frozenset({'BUCKET_BATCH_PIPELINE', 'BUCKET_PRIVATE_CLOUD_SYNC', 'BUCKET_AUDIO_DERIVED'})
EVIDENCE_COUNTS = frozenset(
    {
        'rows',
        'owners',
        'conversations',
        'due_rows',
        'jobs',
        'results',
        'artifacts',
        'chunks',
        'ciphertext_blobs',
        'missing_blobs',
        'finalization_jobs',
        'outbox_rows',
        'has_title',
        'has_structured',
        'audio_closed',
    }
)


def enum_fact(key, value):
    return value if isinstance(value, str) and value in EVIDENCE_ENUMS[key] else 'missing' if value is None else 'other'


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode()


def blob_fact(path: str, body: bytes):
    return {'path': path, 'sha256': hashlib.sha256(body).hexdigest(), 'size': len(body)}


def manifest_stub(case_id, tier, evidence, blobs):
    if not re.fullmatch(r'[a-z0-9-]{1,100}', case_id) or tier not in {'S', 'C'}:
        raise ValueError('invalid capture manifest identity')
    for key, value in evidence.items():
        if key == 'missing_input':
            if (
                not isinstance(value, list)
                or any(not isinstance(bucket, str) or bucket not in BUCKET_KEYS for bucket in value)
                or len(set(value)) != len(value)
            ):
                raise ValueError('missing inputs require unique configured bucket keys')
        elif key in EVIDENCE_COUNTS:
            if type(value) is not int or value < 0:
                raise ValueError('invalid capture count')
        elif key not in EVIDENCE_ENUMS or value not in EVIDENCE_ENUMS[key]:
            raise ValueError('unapproved production evidence')
    return {
        'schema_version': VERSION,
        'id': case_id,
        'tier': tier,
        'scrub': 'structure-only' if tier == 'S' else 'owner-tokenized-ciphertext',
        'seed_blob_sha256': list(dict.fromkeys(blob['sha256'] for blob in blobs)),
        'created': datetime.now(timezone.utc).isoformat(),
        'prod_evidence': evidence,
        'stages': {},
    }
