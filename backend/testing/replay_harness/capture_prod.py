"""Read-only production replay seeds. No decryption, service imports or secret loading.

Operator: source gcp-agent-env.sh ro-prod (or prod-operator for artifact get),
then run from backend. The transport remains read-only with either identity:
  .venv/bin/python -m testing.replay_harness.capture_prod --check-access
  .venv/bin/python -m testing.replay_harness.capture_prod --tier S --output <new-dir>
  .venv/bin/python -m testing.replay_harness.capture_prod --tier C --uid-file <0600> \
    --consent-file <0600-sha256-lines> --conversations-file <0600-id-lines> --output <new-dir>

Output's parent must exist. Keep corpus and salt on this Mac, outside Git;
the program lead owns deletion at program end (plan §5, ruling a5c4f6).
"""

import argparse
from collections import Counter
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import quote, urlsplit

from .capture_schema import blob_fact, enum_fact, json_bytes, manifest_stub
from .guard import (
    CaptureRefused,
    consenting_uid,
    conversations,
    document_id,
    private_directory,
    private_write,
    without_uid,
)

FIRESTORE_ROOT = 'https://firestore.googleapis.com/v1/projects/based-hardware/databases/(default)/documents'
STORAGE_ROOT = 'https://storage.googleapis.com/storage/v1'
PREFIX = 'batch_pipeline_prod_'
ADMISSION_FIELDS = (
    'owner_id',
    'conversation_id',
    'state',
    'attempt',
    'available_at',
    'duration_seconds',
    'worker_vad_receipt.captured_samples',
    'worker_vad_receipt.speech_samples',
)
READ_PERMISSIONS = ('storage.objects.get', 'storage.objects.list')
MAX_ROWS = 2000


class ReadOnlyViolation(PermissionError):
    pass


class CaptureReadError(RuntimeError):
    pass


class StorageReadDenied(CaptureReadError):
    pass


class ReadOnlyTransport:
    """Capability wrapper: even accidental request/SDK-style writes fail locally.

    POST is needed for Firestore reads only. No generic URL or RPC passthrough;
    redirects are disabled so an allowed endpoint cannot redirect credentials.
    """

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        raise ReadOnlyViolation('capture transport only permits explicit read operations')

    def request(self, method, url, **kwargs):
        firestore_read = method == 'POST' and url in {FIRESTORE_ROOT + ':runQuery', FIRESTORE_ROOT + ':batchGet'}
        storage_read = method == 'GET' and url.startswith(STORAGE_ROOT + '/b/')
        if not (firestore_read or storage_read):
            raise ReadOnlyViolation('capture transport refused a non-read operation')
        if set(kwargs) - {'params', 'json'}:
            raise ReadOnlyViolation('capture transport refused request overrides')
        response = self._session.request(method, url, timeout=120, allow_redirects=False, **kwargs)
        if response.status_code == 404:
            return None
        if storage_read and response.status_code == 403:
            raise StorageReadDenied('storage read denied')
        if response.status_code != 200:
            raise CaptureReadError('production read failed')
        return response


def decode_fields(fields):
    """JSON-native Firestore values; preserve opaque bytes as base64, never decrypt."""

    def decode(value):
        for kind in ('stringValue', 'timestampValue', 'referenceValue', 'booleanValue', 'doubleValue'):
            if kind in value:
                return value[kind]
        if 'bytesValue' in value:
            return {'_firestore_bytes_base64': value['bytesValue']}
        if 'integerValue' in value:
            return int(value['integerValue'])
        if 'mapValue' in value:
            return decode_fields(value['mapValue'].get('fields', {}))
        if 'arrayValue' in value:
            return [decode(item) for item in value['arrayValue'].get('values', [])]
        if 'geoPointValue' in value:
            return value['geoPointValue']
        return None

    return {key: decode(value) for key, value in fields.items()}


def eq(field, value):
    return {'fieldFilter': {'field': {'fieldPath': field}, 'op': 'EQUAL', 'value': {'stringValue': value}}}


class ReadOnlyFirestore:
    def __init__(self, transport):
        self._transport = transport

    def __getattr__(self, name):
        raise ReadOnlyViolation('capture Firestore client has no write operations')

    def query(self, collection, *, filters=(), fields=None, order=None, limit=MAX_ROWS, require_complete=True):
        document_id(collection)
        query = {'from': [{'collectionId': collection}], 'limit': limit + int(require_complete)}
        if filters:
            query['where'] = (
                filters[0] if len(filters) == 1 else {'compositeFilter': {'op': 'AND', 'filters': list(filters)}}
            )
        if fields is not None:
            if not fields:
                raise ValueError('empty projection is not a structure-only read')
            query['select'] = {'fields': [{'fieldPath': field} for field in fields]}
        if order:
            query['orderBy'] = [{'field': {'fieldPath': order}, 'direction': 'ASCENDING'}]
        response = self._transport.request('POST', FIRESTORE_ROOT + ':runQuery', json={'structuredQuery': query})
        rows = [row['document'] for row in response.json() if 'document' in row]
        if require_complete and len(rows) > limit:
            raise CaptureRefused('capture row limit exceeded; narrow the selection')
        return {row['name'].rsplit('/', 1)[-1]: decode_fields(row.get('fields', {})) for row in rows}

    def read(self, paths):
        found = {}
        for start in range(0, len(paths), 100):
            batch = paths[start : start + 100]
            if any(not path or any(not document_id(part) for part in path.split('/')) for path in batch):
                raise CaptureRefused('invalid document path')
            response = self._transport.request(
                'POST',
                FIRESTORE_ROOT + ':batchGet',
                json={'documents': [FIRESTORE_ROOT.split('/v1/', 1)[1] + '/' + path for path in batch]},
            )
            for row in response.json():
                if 'found' in row:
                    doc = row['found']
                    found[doc['name'].split('/documents/', 1)[1]] = decode_fields(doc.get('fields', {}))
        return found


class ReadOnlyStorage:
    def __init__(self, transport):
        self._transport = transport

    def __getattr__(self, name):
        raise ReadOnlyViolation('capture storage client has no write operations')

    def permissions(self, bucket):
        response = self._transport.request(
            'GET',
            STORAGE_ROOT + '/b/' + quote(bucket, safe='') + '/iam/testPermissions',
            params=[('permissions', permission) for permission in READ_PERMISSIONS],
        )
        return set(response.json().get('permissions', [])) if response is not None else set()

    def inventory(self, bucket, prefix):
        rows, token = [], None
        while True:
            params = {'prefix': prefix, 'maxResults': 1000, 'fields': 'items(name,generation,size),nextPageToken'}
            if token:
                params['pageToken'] = token
            response = self._transport.request(
                'GET', STORAGE_ROOT + '/b/' + quote(bucket, safe='') + '/o', params=params
            )
            if response is None:
                raise CaptureReadError('inventory bucket unavailable')
            page = response.json()
            for item in page.get('items', []):
                if not item['name'].startswith(prefix):
                    raise CaptureRefused('object escaped selected conversation')
                rows.append(
                    {
                        'bucket': bucket,
                        'name': item['name'],
                        'generation': item['generation'],
                        'size': int(item['size']),
                    }
                )
            if len(rows) > 10000:
                raise CaptureRefused('chunk inventory limit exceeded')
            token = page.get('nextPageToken')
            if not token:
                return rows

    def ciphertext(self, bucket, name, generation=None):
        url = STORAGE_ROOT + '/b/' + quote(bucket, safe='') + '/o/' + quote(name, safe='')
        if generation is None:
            metadata = self._transport.request('GET', url, params={'fields': 'generation'})
            if metadata is None:
                return None
            generation = str(metadata.json()['generation'])
        if not re.fullmatch(r'[1-9][0-9]{0,19}', generation):
            raise CaptureRefused('invalid artifact generation')
        response = self._transport.request('GET', url, params={'alt': 'media', 'generation': generation})
        if response is None:
            return None
        body = response.content
        if not body.startswith(b'OMIBP1'):
            raise CaptureRefused('artifact is not a batch ciphertext envelope')
        return body, generation


def bucket_config():
    """Use backend's checked-in production env defaults, plus explicit runtime overrides.

    Avoid importing utils.other.storage (imports encryption and service clients).
    """
    import yaml

    backend = Path(__file__).resolve().parents[2]
    sources = (
        backend / 'charts/backend-listen/prod_omi_backend_listen_values.yaml',
        backend / 'deploy/runtime_env/prod.overlay.yaml',
    )

    # Chart list entries and Cloud Run map entries both define needed buckets.
    def entries(value):
        if isinstance(value, dict):
            if value.get('name', '').startswith('BUCKET_') and 'value' in value:
                yield value['name'], value['value']
            for key, child in value.items():
                if key.startswith('BUCKET_') and isinstance(child, dict) and 'value' in child:
                    yield key, child['value']
                yield from entries(child)
        elif isinstance(value, list):
            for child in value:
                yield from entries(child)

    defaults = {}
    for source in sources:
        for key, value in entries(yaml.safe_load(source.read_text())):
            if isinstance(value, str) and value.strip():
                defaults.setdefault(key, set()).add(value.strip())
    config = {}
    for key in ('BUCKET_BATCH_PIPELINE', 'BUCKET_PRIVATE_CLOUD_SYNC', 'BUCKET_AUDIO_DERIVED'):
        candidates = defaults.get(key, set())
        if key not in os.environ and len(candidates) > 1:
            raise CaptureRefused('backend bucket configuration is ambiguous; set an explicit override')
        config[key] = os.environ[key].strip() if key in os.environ else next(iter(candidates), '')
    if not config['BUCKET_BATCH_PIPELINE'] or not config['BUCKET_PRIVATE_CLOUD_SYNC']:
        raise CaptureRefused('backend bucket configuration missing')
    if any(value and not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]', value) for value in config.values()):
        raise CaptureRefused('invalid backend bucket configuration')
    return config


def check_access(storage, buckets):
    facts = []
    for bucket in sorted(set(buckets.values()) - {''}):
        try:
            permissions = storage.permissions(bucket)
            facts.append(
                {
                    'bucket': bucket,
                    'status': 'checked',
                    **{permission: permission in permissions for permission in READ_PERMISSIONS},
                }
            )
        except CaptureReadError:
            facts.append(
                {'bucket': bucket, 'status': 'unavailable', **{permission: False for permission in READ_PERMISSIONS}}
            )
    return facts


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def admission_shape(key, row, digest, now):
    available = number(row.get('available_at'))
    delta = available - now if available is not None else None
    bucket = (
        'unknown'
        if delta is None
        else (
            'future'
            if delta > 0
            else (
                'due-under-1m'
                if delta > -60
                else 'due-under-1h' if delta > -3600 else 'due-under-1d' if delta > -86400 else 'due-over-1d'
            )
        )
    )
    receipt = row.get('worker_vad_receipt') or {}
    return {
        'unit': digest(key),
        'owner': digest(row.get('owner_id')),
        'conversation': digest(row.get('conversation_id')),
        'state': 'record_pending' if row.get('state') == 'record_pending' else 'other',
        'attempt': number(row.get('attempt')),
        'available_at_bucket': bucket,
        'duration_seconds': number(row.get('duration_seconds')),
        'captured_samples': number(receipt.get('captured_samples')),
        'speech_samples': number(receipt.get('speech_samples')),
    }


def write_case(output, case_id, tier, corpus, evidence, blobs=()):
    case = output / case_id
    private_directory(case, create=True)
    private_directory(case / 'blobs', create=True)
    private_directory(case / 'cassettes', create=True)
    # Paths and byte counts belong to the corpus, keeping the manifest wire
    # fields compatible with WP1. Expectations intentionally remain empty.
    corpus = {**corpus, 'seed_blobs': [blob_fact(name, body) for name, body in blobs]}
    facts = []
    for name, body in [('corpus.json', json_bytes(corpus)), *blobs]:
        private_write(case / name, body)
        facts.append(blob_fact(name, body))
    private_write(case / 'manifest.json', json_bytes(manifest_stub(case_id, tier, evidence, facts)))


def capture_structure(db, output, digest, *, limit=MAX_ROWS, now=None):
    now = time.time() if now is None else now
    rows = db.query(
        PREFIX + 'jobs',
        filters=[eq('state', 'record_pending')],
        fields=ADMISSION_FIELDS,
        order='available_at',
        limit=limit,
        require_complete=False,
    )
    units = [admission_shape(key, row, digest, now) for key, row in rows.items()]
    evidence = {
        'rows': len(units),
        'owners': len({row['owner'] for row in units} - {None}),
        'conversations': len({row['conversation'] for row in units} - {None}),
        'due_rows': sum(row['available_at_bucket'].startswith('due-') for row in units),
    }
    corpus = {
        'schema': 1,
        'source': 'firestore-admission-structure-only',
        'admission_window': units,
        'counts': evidence,
        'available_at_buckets': dict(Counter(row['available_at_bucket'] for row in units)),
        'window_limit': limit,
        'window_full': len(units) == limit,
        'field_allowlist': {'jobs': ADMISSION_FIELDS},
    }
    write_case(output, 'admission-window', 'S', corpus, evidence)
    return {'cases': 1, 'rows': len(units)}


def owner_row(row, uid, *, owner_field='owner_id'):
    if row.get(owner_field) != uid:
        raise CaptureRefused('related document owner mismatch')


def capture_owner_item(db, storage, output, digest, uid, cid, buckets):
    owner_hash = hashlib.sha256(uid.encode()).hexdigest()
    token = 'owner-' + digest(uid)
    missing_input, errors = set(), []
    conversation_path = f'users/{uid}/conversations/{cid}'
    conversation = db.read([conversation_path]).get(conversation_path)
    jobs = {}
    for field in ('conversation_id', 'projection_binding.target_conversation_id'):
        jobs.update(db.query(PREFIX + 'jobs', filters=[eq('owner_id', uid), eq(field, cid)]))
    stored_segments = (conversation or {}).get('transcript_segments')
    # Current production stores compressed/encrypted transcript blobs.
    # Never decode them here; job/binding queries still discover units.
    inline_segments = stored_segments if isinstance(stored_segments, list) else []
    scopes = {
        (segment.get('provider_speaker') or {}).get('scope') or segment.get('speaker_id_scope', '')
        for segment in inline_segments
        if isinstance(segment, dict)
    }
    units = {
        document_id(scope.removeprefix('final:batch:'))
        for scope in scopes
        if isinstance(scope, str)
        and scope.startswith('final:batch:')
        and not scope.startswith('final:batch:conversation:')
    }
    units.update(jobs)
    # A missing job must not hide its still-retained artifact receipt when
    # transcript scopes are encrypted. Keep this query conversation-scoped.
    selected_artifacts = db.query(
        PREFIX + 'artifacts',
        filters=[
            eq('owner_id', uid),
            {
                'fieldFilter': {
                    'field': {'fieldPath': 'conversation_ids'},
                    'op': 'ARRAY_CONTAINS',
                    'value': {'stringValue': cid},
                }
            },
        ],
    )
    for row in selected_artifacts.values():
        owner_row(row, uid)
        units.add(document_id(row.get('segment_id')))
    if len(units) > MAX_ROWS:
        raise CaptureRefused('selected conversation unit limit exceeded')
    paths = [PREFIX + table + '/' + unit for table in ('jobs', 'results') for unit in sorted(units)]
    docs = db.read(paths)
    jobs.update({unit: docs[PREFIX + 'jobs/' + unit] for unit in units if PREFIX + 'jobs/' + unit in docs})
    for row in jobs.values():
        owner_row(row, uid)
        # The whole job is persisted; a nested binding owner must match too, or
        # a foreign uid and its references would survive the pinned-uid scrub.
        binding = row.get('projection_binding')
        if isinstance(binding, dict) and binding.get('owner_id') is not None:
            owner_row(binding, uid)
    results = {unit: docs[PREFIX + 'results/' + unit] for unit in units if PREFIX + 'results/' + unit in docs}
    for row in results.values():
        if row.get('owner_key') != owner_hash:
            raise CaptureRefused('result owner mismatch')
    artifacts = dict(selected_artifacts)
    for unit in sorted(units):
        artifacts.update(db.query(PREFIX + 'artifacts', filters=[eq('owner_id', uid), eq('segment_id', unit)]))
    finalization = db.query('conversation_finalization_jobs', filters=[eq('uid', uid), eq('conversation_id', cid)])
    for row in finalization.values():
        owner_row(row, uid, owner_field='uid')
    outbox_id = hashlib.sha256(f'{uid}\0{cid}'.encode()).hexdigest()
    outbox_path = 'sync_reprocess_outbox/' + outbox_id
    outbox = db.read([outbox_path]).get(outbox_path)
    if outbox:
        # The document id is sha256(uid, cid), so the path already binds the row
        # to this owner. Production rows can carry uid=null; only a conflicting
        # non-null uid or conversation id is a mismatch.
        if outbox.get('uid') is not None:
            owner_row(outbox, uid, owner_field='uid')
        if outbox.get('conversation_id') not in (None, cid):
            raise CaptureRefused('related document owner mismatch')
    inventory, listed = [], set()
    for bucket_key in ('BUCKET_PRIVATE_CLOUD_SYNC', 'BUCKET_AUDIO_DERIVED'):
        bucket = buckets[bucket_key]
        if not bucket or bucket in listed:
            continue
        listed.add(bucket)
        # Listing contains the full inventory seed. In particular, the derived
        # bucket needs no metadata/media GET or testIamPermissions precondition.
        try:
            inventory.extend(storage.inventory(bucket, f'chunks/{uid}/{cid}/'))
        except CaptureReadError as error:
            missing_input.add(bucket_key)
            errors.append(type(error).__name__)
    # Prefer exact generations referenced by the paid job/result. Metadata
    # registration precedes upload and commonly has an unversioned URI.
    references = [(unit, row.get('audio_uri')) for unit, row in jobs.items()]
    references += [(unit, (row.get('result') or {}).get('result_uri')) for unit, row in results.items()]
    versions = {}
    for _, uri in references:
        if isinstance(uri, str) and '#' in uri:
            base, generation = uri.rsplit('#', 1)
            versions.setdefault(base, set()).add(generation)
    # Preserve missing metadata as missing: do not fabricate artifact rows.
    # Still capture owner-bound ciphertext referenced by a job/result, so a
    # unit_unavailable case includes the bytes even if its receipt vanished.
    requests = []
    for key, row in artifacts.items():
        owner_row(row, uid)
        if row.get('segment_id') not in units:
            raise CaptureRefused('artifact escaped selected units')
        requests.append((key, row.get('uri', ''), row['segment_id']))
    known = {uri.split('#', 1)[0] for _, uri, _ in requests}
    for unit, uri in references:
        if isinstance(uri, str) and uri.startswith('gs://') and uri.split('#', 1)[0] not in known:
            requests.append((None, uri, unit))
            known.add(uri.split('#', 1)[0])
    blobs, blob_refs, missing, total_bytes = [], [], 0, 0
    saved = set()
    for key, uri, unit in requests:
        parsed = urlsplit(uri)
        name = parsed.path.lstrip('/')
        prefix = f'batch-pipeline/batch_pipeline_prod/owners/{owner_hash}/'
        object_parts = name.removeprefix(prefix).split('/')
        bucket_key = next(
            (
                key
                for key in ('BUCKET_BATCH_PIPELINE', 'BUCKET_PRIVATE_CLOUD_SYNC', 'BUCKET_AUDIO_DERIVED')
                if buckets[key] and buckets[key] == parsed.netloc
            ),
            None,
        )
        if (
            parsed.scheme != 'gs'
            or bucket_key is None
            or parsed.query
            or not name.startswith(prefix)
            or not name.endswith('.enc')
            or len(object_parts) != 3
            or object_parts[1] != unit
            or object_parts[0] not in {'audio', 'result', 'results', 'voice_evidence'}
            or any(part in {'.', '..'} for part in name.split('/'))
        ):
            raise CaptureRefused('artifact escaped owner storage')
        base = uri.split('#', 1)[0]
        generations = versions.get(base) or {parsed.fragment or None}
        for generation in sorted(generations, key=str):
            try:
                if bucket_key == 'BUCKET_AUDIO_DERIVED':
                    # This bucket is inventory-only for both admitted tiers.
                    # Never try a metadata or media GET, even with operator ADC.
                    raise StorageReadDenied('derived bucket is list-only')
                captured = storage.ciphertext(parsed.netloc, name, generation)
            except CaptureReadError as error:
                captured = None
                errors.append(type(error).__name__)
            if captured is None:
                missing += 1
                missing_input.add(bucket_key)
                if not errors:
                    errors.append('FileNotFoundError')
                blob_refs.append({'artifact_id': key, 'uri': uri, 'status': 'missing'})
                continue
            body, actual_generation = captured
            local = 'blobs/' + digest(uri.split('#', 1)[0] + ':' + actual_generation) + '.enc'
            if local not in saved:
                total_bytes += len(body)
                if total_bytes > 1024 * 1024 * 1024:
                    raise CaptureRefused('case ciphertext byte limit exceeded')
                blobs.append((local, body))
                saved.add(local)
            blob_refs.append(
                {'artifact_id': key, 'uri': base + '#' + actual_generation, 'path': local, 'status': 'captured'}
            )
    corpus = {
        'schema': 1,
        'source': 'firestore-owner-ciphertext',
        'owner_token': token,
        'owner_sha256': owner_hash,
        'referenced_units': sorted(units),
        'conversation_id': cid,
        'conversation': conversation,
        'jobs': jobs,
        'results': results,
        'artifacts': artifacts,
        'finalization_jobs': finalization,
        'enrichment_outbox': outbox,
        'chunk_inventory': inventory,
        'blob_refs': blob_refs,
    }
    evidence = {
        'capture_status': 'partial' if missing_input else 'complete',
        'missing_input': sorted(missing_input),
        'jobs': len(jobs),
        'results': len(results),
        'artifacts': len(artifacts),
        'chunks': len(inventory),
        'ciphertext_blobs': len(blobs),
        'missing_blobs': missing,
        'finalization_jobs': len(finalization),
        'outbox_rows': int(outbox is not None),
        'has_title': int(bool(((conversation or {}).get('structured') or {}).get('title'))),
        'has_structured': int(bool((conversation or {}).get('structured'))),
        'audio_closed': int((conversation or {}).get('record_audio_closed') is True),
        'conversation_status': enum_fact('conversation_status', (conversation or {}).get('status')),
        'finalization_status': enum_fact(
            'finalization_status',
            finalization.get((conversation or {}).get('finalization_job_id'), {}).get('status'),
        ),
        'speaker_status': enum_fact(
            'speaker_status', ((conversation or {}).get('speaker_resolution') or {}).get('status')
        ),
    }
    write_case(output, 'owner-' + digest(cid), 'C', without_uid(corpus, uid, token), evidence, blobs)
    return {
        'item': 'owner-' + digest(cid),
        'status': 'partial' if missing_input else 'complete',
        'exception_type': errors[0] if errors else None,
    }


def capture_owner(db, storage, output, digest, uid, selected, buckets):
    """An item failure never skips later consented conversations."""
    items = []
    for cid in selected:
        case_id = 'owner-' + digest(cid)
        try:
            item = capture_owner_item(db, storage, output, digest, uid, cid, buckets)
        except (CaptureRefused, ReadOnlyViolation) as error:
            item = {'item': case_id, 'status': 'refused', 'exception_type': type(error).__name__}
        except Exception as error:
            item = {'item': case_id, 'status': 'partial', 'exception_type': type(error).__name__}
            # Preserve a seed stub for interrupted reads, never an unsafe row or
            # an exception message. Do not overwrite any partially written case.
            if not (output / case_id).exists():
                try:
                    stub = {
                        'schema': 1,
                        'source': 'firestore-owner-ciphertext',
                        'owner_token': 'owner-' + digest(uid),
                        'conversation_id': cid,
                    }
                    write_case(
                        output,
                        case_id,
                        'C',
                        without_uid(stub, uid, 'owner-' + digest(uid)),
                        {'capture_status': 'partial'},
                    )
                except Exception as write_error:
                    item['exception_type'] = type(write_error).__name__
                    if isinstance(write_error, (CaptureRefused, ReadOnlyViolation)):
                        item['status'] = 'refused'
        items.append(item)
    return {'cases': len(selected), 'items': items}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-access', action='store_true')
    parser.add_argument('--tier', choices=('S', 'C'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--uid-file', type=Path)
    parser.add_argument('--consent-file', type=Path)
    parser.add_argument('--conversations-file', type=Path)
    parser.add_argument('--limit', type=int, default=MAX_ROWS)
    args = parser.parse_args(argv)
    try:
        if (
            os.environ.get('GCP_AGENT_TIER') not in {'ro-prod', 'prod-operator'}
            or os.environ.get('FIRESTORE_EMULATOR_HOST')
            or os.environ.get('STORAGE_EMULATOR_HOST')
        ):
            raise CaptureRefused('capture requires explicit ro-prod or prod-operator and no emulators')
        if not 1 <= args.limit <= MAX_ROWS:
            raise CaptureRefused('capture limit must be between one and 2000')
        uid, selected = None, None
        if not args.check_access:
            if not args.output or not args.tier:
                raise CaptureRefused('capture requires tier and output')
            if args.tier == 'C':
                if not all((args.uid_file, args.consent_file, args.conversations_file)):
                    raise CaptureRefused('owner capture requires private uid, consent and conversation files')
                uid = consenting_uid(args.uid_file, args.consent_file)
                selected = conversations(args.conversations_file)
            elif any((args.uid_file, args.consent_file, args.conversations_file)):
                raise CaptureRefused('owner inputs are only valid for Tier C')
            private_directory(args.output.parent)
            private_directory(args.output, create=True)
        buckets = bucket_config() if args.check_access or args.tier == 'C' else None
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        with AuthorizedSession(credentials) as session:
            transport = ReadOnlyTransport(session)
            db, storage = ReadOnlyFirestore(transport), ReadOnlyStorage(transport)
            if args.check_access:
                print(json.dumps({'access': check_access(storage, buckets)}, sort_keys=True))
                return 0
            salt = secrets.token_bytes(32)
            private_write(args.output / 'salt', salt.hex().encode())

            def digest(value):
                return hmac.new(salt, str(value).encode(), hashlib.sha256).hexdigest() if value else None

            summary = (
                capture_structure(db, args.output, digest, limit=args.limit)
                if args.tier == 'S'
                else capture_owner(db, storage, args.output, digest, uid, selected, buckets)
            )
            complete = all(item['status'] == 'complete' for item in summary.get('items', []))
            print(
                json.dumps(
                    {'capture': 'complete' if complete else 'partial', 'tier': args.tier, **summary}, sort_keys=True
                )
            )
        return 0 if complete else 1
    except Exception as error:
        # Never serialize messages, tracebacks, paths, IDs, SDK URLs or response bodies.
        print(json.dumps({'capture': 'failed', 'exception_type': type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
