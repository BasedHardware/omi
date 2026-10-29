"""Read projected Firestore fields only; never download encrypted artifacts.

Run directly with the backend venv after sourcing gcp-agent-env.sh ro-prod.
All persisted identifiers are HMACs with a fresh, private per-corpus salt.
"""

import argparse
from collections import Counter
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets

import google.auth
from google.auth.transport.requests import AuthorizedSession

RESULT_FIELDS = (
    'owner_key',
    'segment_id',
    'previous_segment_id',
    'log_sequence',
    'committed_at',
    'projection_state',
    'projection.state',
    'projection.conversation_id',
    'result.outcome',
    'audio_seconds',
    'speech_seconds',
)
JOB_FIELDS = (
    'owner_id',
    'duration_seconds',
    'unit_kind',
    'conversation_id',
    'fresh_capture',
    'state',
    'attempt',
    'recovery_state',
    'recovery_attempt',
    'retry_at',
    'worker_vad_receipt.captured_samples',
    'worker_vad_receipt.speech_samples',
    'projection_binding.target_conversation_id',
    'projection_binding.record_origin',
    'projection_binding.native_record',
    'projection_binding.content_id',
    'projection_binding.segment_ids',
    'audio_seconds',
    'speech_seconds',
)
TARGET_FIELDS = (
    'discarded',
    'deleted',
    'status',
    'sync_merged_into',
    'record_lane_owner',
    'uses_custom_stt',
    'data_protection_level',
)
STATES = frozenset(
    (
        'pending',
        'persisted',
        'ready',
        'complete',
        'completed',
        'committed',
        'projected',
        'quarantine_held',
        'quarantined',
        'held',
        'prepared',
        'running',
        'failed_held',
        'erased',
        'result_ready',
        'success',
        'silence',
        'no_recoverable_speech',
        'in_progress',
        'processing',
        'retry',
        'leased',
        'failed',
        'superseded',
    )
)


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def state(value):
    return value if isinstance(value, str) and value in STATES else 'other' if value is not None else None


def decode_dict(fields):
    """Decode REST values without SDK protobuf objects or reference clients."""

    def decode(value):
        for kind in ('stringValue', 'booleanValue', 'doubleValue'):
            if kind in value:
                return value[kind]
        if 'integerValue' in value:
            return int(value['integerValue'])
        if 'mapValue' in value:
            return decode_dict(value['mapValue'].get('fields', {}))
        if 'arrayValue' in value:
            return [decode(item) for item in value['arrayValue'].get('values', [])]
        return None

    return {key: decode(value) for key, value in fields.items()}


class ReadOnlyFirestore:
    """REST avoids keeping a gRPC stream open during related-document reads."""

    root = 'https://firestore.googleapis.com/v1/projects/based-hardware/databases/(default)/documents'

    def __init__(self):
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/datastore'])
        self.session = AuthorizedSession(credentials)

    def post(self, operation, body):
        response = self.session.post(self.root + ':' + operation, json=body, timeout=120)
        response.raise_for_status()
        return response.json()

    def latest(self, fields, limit):
        rows = self.post(
            'runQuery',
            {
                'structuredQuery': {
                    'from': [{'collectionId': 'batch_pipeline_prod_results'}],
                    'select': {'fields': [{'fieldPath': field} for field in fields]},
                    'orderBy': [{'field': {'fieldPath': 'committed_at'}, 'direction': 'DESCENDING'}],
                    'limit': limit,
                }
            },
        )
        return [
            (row['document']['name'].rsplit('/', 1)[-1], decode_dict(row['document'].get('fields', {})))
            for row in rows
            if 'document' in row
        ]

    def read(self, paths, fields):
        found = {}
        paths = list(dict.fromkeys(paths))
        for offset in range(0, len(paths), 100):
            rows = self.post(
                'batchGet',
                {
                    'documents': [
                        self.root.removeprefix('https://firestore.googleapis.com/v1/') + '/' + path
                        for path in paths[offset : offset + 100]
                    ],
                    'mask': {'fieldPaths': list(fields)},
                },
            )
            for row in rows:
                if 'found' in row:
                    doc = row['found']
                    found[doc['name'].split('/documents/', 1)[1]] = {
                        **decode_dict(doc.get('fields', {})),
                        '_exists': True,
                    }
        return found


def target_shape(target, digest, *, child=True):
    return {
        'exists': target.get('_exists', bool(target)),
        'discarded': target.get('discarded') is True,
        'deleted': target.get('deleted') is True,
        'status': state(target.get('status')),
        'redirect': digest(target.get('sync_merged_into')),
        'route_owner': (
            target.get('record_lane_owner')
            if target.get('record_lane_owner') in {'batch_live_v1', 'batch_sync_v1'}
            else 'other'
        ),
        'custom_stt': target.get('uses_custom_stt') is True,
        'protection': (
            target.get('data_protection_level', 'enhanced')
            if target.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
            else 'other'
        ),
        'redirect_state': (
            target_shape(target['_redirect_state'], digest, child=False)
            if child and '_redirect_state' in target
            else None
        ),
    }


def sanitize(job, entry, owner, target, digest):
    """Allowlist construction, never recursive copying/redaction of a document."""
    binding = job.get('projection_binding') or {}
    receipt = job.get('worker_vad_receipt') or {}
    target_id = binding.get('target_conversation_id') or job.get('conversation_id')
    return {
        'unit': digest(entry['segment_id']),
        'owner': digest(job.get('owner_id')),
        'content': digest(binding.get('content_id')),
        'conversation': digest(job.get('conversation_id')),
        'target': digest(target_id),
        'previous': digest(entry.get('previous_segment_id')),
        'watermark': digest(owner.get('projection_watermark')),
        'sequence': number(entry.get('log_sequence')),
        'duration': number(job.get('duration_seconds')),
        'unit_kind': (
            job.get('unit_kind') if job.get('unit_kind') in {'conversation', 'capture_span'} else 'conversation'
        ),
        'decoded_duration': number(job.get('audio_seconds', entry.get('audio_seconds'))),
        'captured_samples': number(receipt.get('captured_samples')),
        'speech_samples': number(receipt.get('speech_samples')),
        'speech_seconds': number(job.get('speech_seconds', entry.get('speech_seconds'))),
        # Firestore arrays cannot project element subfields. Never request or
        # inspect them: nested entries may carry transcript text or paths.
        'spans': None,
        'references': None,
        'lane': (
            'backfill'
            if job.get('fresh_capture') is False
            else 'fresh' if job.get('fresh_capture') is True else 'unknown'
        ),
        'record_origin': binding.get('record_origin') is True,
        'native_record': binding.get('native_record') is True,
        'state': state(job.get('state')),
        'projection_state': state(entry.get('projection_state')),
        'assignment_state': state((entry.get('projection') or {}).get('state')),
        'outcome': state((entry.get('result') or {}).get('outcome')),
        'attempt': number(job.get('attempt')),
        'recovery_attempt': number(job.get('recovery_attempt')),
        'retry_present': job.get('retry_at') is not None,
        'recovery_state': state(job.get('recovery_state')),
        'target_state': target_shape(target, digest) if target_id else None,
    }


def capture(output, limit):
    if os.environ.get('GCP_AGENT_TIER') != 'ro-prod' or os.environ.get('FIRESTORE_EMULATOR_HOST'):
        raise RuntimeError('capture requires explicit ro-prod identity and no emulator')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    salt = secrets.token_bytes(32)

    def digest(value):
        return hmac.new(salt, str(value).encode(), hashlib.sha256).hexdigest() if value else None

    client = ReadOnlyFirestore()
    prefix = 'batch_pipeline_prod_'
    units = []
    snapshots = client.latest(RESULT_FIELDS, limit)
    jobs = client.read([prefix + 'jobs/' + sid for sid, _ in snapshots], JOB_FIELDS)
    owners = client.read(
        [prefix + 'owners/' + entry['owner_key'] for _, entry in snapshots if entry.get('owner_key')],
        ['projection_watermark'],
    )
    target_paths = []
    for job in jobs.values():
        target_id = (job.get('projection_binding') or {}).get('target_conversation_id') or job.get('conversation_id')
        if target_id and job.get('owner_id'):
            target_paths.append(f"users/{job['owner_id']}/conversations/{target_id}")
    targets = client.read(target_paths, TARGET_FIELDS)
    redirect_paths = {
        path: path.rsplit('/', 1)[0] + '/' + row['sync_merged_into']
        for path, row in targets.items()
        if row.get('sync_merged_into')
    }
    redirects = client.read(redirect_paths.values(), TARGET_FIELDS)
    for path, redirect_path in redirect_paths.items():
        targets[path]['_redirect_state'] = redirects.get(redirect_path, {})
    for sid, entry in snapshots:
        entry['segment_id'] = sid
        job = jobs.get(prefix + 'jobs/' + sid, {})
        key = entry.get('owner_key')
        binding = job.get('projection_binding') or {}
        target_id = binding.get('target_conversation_id') or job.get('conversation_id')
        target_path = f"users/{job.get('owner_id')}/conversations/{target_id}"
        units.append(
            sanitize(job, entry, owners.get(prefix + 'owners/' + str(key), {}), targets.get(target_path, {}), digest)
        )
    # Descending query is reversed so each chain retains commit order.
    units.reverse()
    coverage = {
        field: sum(unit[field] is not None for unit in units)
        for field in ('duration', 'decoded_duration', 'spans', 'references', 'target_state')
    }
    data = {
        'schema': 1,
        'source': 'firestore-structure-only',
        'units': units,
        'coverage': coverage,
        'geometry_capture': 'not-requested-by-policy',
        'field_allowlist': {
            'results': RESULT_FIELDS,
            'jobs': JOB_FIELDS,
            'targets': TARGET_FIELDS,
            'owners': ['projection_watermark'],
        },
    }
    for name, body in (('salt', salt.hex()), ('corpus.json', json.dumps(data, sort_keys=True))):
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(body)
    print(
        json.dumps(
            {
                'units': len(units),
                'coverage': coverage,
                'projection_states': dict(Counter(u['projection_state'] for u in units)),
            },
            sort_keys=True,
        )
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=2000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 2000:
        parser.error('limit must be in [1, 2000]')
    try:
        capture(args.output, args.limit)
    except Exception as error:
        print(json.dumps({'capture': 'failed', 'exception_type': type(error).__name__}))
        raise SystemExit(1) from None
