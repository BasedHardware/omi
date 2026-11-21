"""Read a versioned corpus and preserve Firestore timestamps and bytes."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import re

DEFAULT_TEST_KEY = 'replay-harness-synthetic-encryption-key-0000'
FIXED_DATE = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
SLUG = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}')
END_REASONS = {'user_stop', 'silence', 'disconnect', 'timeout', 'server_shutdown', 'unknown'}
TRIGGERS = {'capture_end', 'client_finalize', 'server_recovery', 'user_reprocess'}


def unpack(value):
    if isinstance(value, list):
        return [unpack(item) for item in value]
    if isinstance(value, dict):
        if value.keys() == {'$timestamp'}:
            stamp = datetime.fromisoformat(value['$timestamp'])
            if stamp.utcoffset() is None:
                raise ValueError('fixture timestamp requires a timezone')
            return stamp
        if value.keys() == {'$bytes'}:
            return base64.b64decode(value['$bytes'], validate=True)
        return {name: unpack(item) for name, item in value.items()}
    return value


def pack(value):
    if isinstance(value, datetime):
        return {'$timestamp': value.isoformat()}
    if isinstance(value, bytes):
        return {'$bytes': base64.b64encode(value).decode('ascii')}
    if isinstance(value, dict):
        return {key: pack(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [pack(item) for item in value]
    return value


def _validate_case(case, seen):
    fields = {
        'name',
        'uid',
        'conversation_id',
        'recording',
        'document',
        'trigger',
        'revision',
        'notes',
        'memories',
        'apps',
        'min_words',
        'end_reason',
        'repeat',
        'own_key',
        'responses',
        'final_attempt',
        'unavailable_app',
        'erase_after',
        'delete_before_worker_read',
    }
    if not isinstance(case, dict) or set(case) - fields:
        raise ValueError('unknown replay case fields')
    name = case.get('name', '')
    if not isinstance(name, str) or not SLUG.fullmatch(name) or name in seen:
        raise ValueError('invalid or duplicate replay case name')
    seen.add(name)
    for field in ('uid', 'conversation_id'):
        if field in case and (not isinstance(case[field], str) or not IDENTIFIER.fullmatch(case[field])):
            raise ValueError('invalid replay identity')
    if case.get('end_reason', 'user_stop') not in END_REASONS:
        raise ValueError('unknown end reason')
    if case.get('trigger', 'capture_end') not in TRIGGERS:
        raise ValueError('unknown trigger')
    if type(case.get('revision', 1)) is not int or case.get('revision', 1) < 1:
        raise ValueError('invalid replay revision')
    if type(case.get('min_words', 1)) is not int or case.get('min_words', 1) < 0:
        raise ValueError('invalid minimum words')
    if case.get('document', {}) is not None and not isinstance(case.get('document', {}), dict):
        raise ValueError('document must be an object or null')
    for field in ('memories', 'apps'):
        values = case.get(field, [])
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise ValueError('expected an array of strings')
    if any(not SLUG.fullmatch(app) for app in case.get('apps', [])):
        raise ValueError('invalid synthetic app identifier')
    if len(set(case.get('apps', []))) != len(case.get('apps', [])):
        raise ValueError('duplicate synthetic app identifier')
    if 'unavailable_app' in case and case['unavailable_app'] not in case.get('apps', []):
        raise ValueError('unavailable_app must name a seeded app')
    if any(
        type(case.get(field, False)) is not bool
        for field in ('repeat', 'own_key', 'final_attempt', 'erase_after', 'delete_before_worker_read')
    ):
        raise ValueError('expected a boolean')
    if 'notes' in case and (
        not isinstance(case['notes'], dict)
        or set(case['notes']) != {'title', 'overview'}
        or any(not isinstance(item, str) for item in case['notes'].values())
    ):
        raise ValueError('invalid synthetic notes response')
    responses = case.get('responses', {})
    if not isinstance(responses, dict) or any(not SLUG.fullmatch(feature) for feature in responses):
        raise ValueError('invalid gateway response map')
    recording = case.get('recording', {})
    if not isinstance(recording, dict) or set(recording) - {'segments', 'duration_s'}:
        raise ValueError('invalid recording')
    segments = recording.get('segments', [])
    if not isinstance(segments, list) or any(not isinstance(item, dict) for item in segments):
        raise ValueError('recording segments must be objects')
    if any(not isinstance(segment.get('text'), str) for segment in segments):
        raise ValueError('recording segments require text')
    duration = recording.get('duration_s', 25)
    if type(duration) not in (int, float) or not 0 <= duration <= 86_400:
        raise ValueError('invalid synthetic recording duration')


def read_corpus(payload: bytes) -> list[dict]:
    if len(payload) > 16 * 1024 * 1024:
        raise ValueError('replay corpus exceeds 16 MiB')
    corpus = json.loads(payload.decode('utf-8'))
    if not isinstance(corpus, dict) or set(corpus) != {'version', 'cases'} or type(corpus['version']) is not int:
        raise ValueError('expected a versioned corpus')
    if corpus['version'] != 1 or not isinstance(corpus['cases'], list) or not corpus['cases']:
        raise ValueError('expected at least one version 1 case')
    seen: set[str] = set()
    for case in corpus['cases']:
        _validate_case(case, seen)
    return corpus['cases']


def seed_document(case: dict, cid: str) -> dict | None:
    supplied = case.get('document', {})
    if supplied is None:
        return None
    recording = case.get('recording', {})
    segments = [
        {'id': f'segment-{i}', 'is_user': True, 'start': i * 3, 'end': i * 3 + 2, **segment}
        for i, segment in enumerate(recording.get('segments', []))
    ]
    return {
        'id': cid,
        'status': 'in_progress',
        'created_at': FIXED_DATE,
        'started_at': FIXED_DATE,
        'finished_at': FIXED_DATE + timedelta(seconds=recording.get('duration_s', 25)),
        'source': 'omi',
        'language': 'en',
        'data_protection_level': 'standard',
        'transcript_segments': segments,
        'structured': {'title': '', 'overview': ''},
        **unpack(supplied),
    }
