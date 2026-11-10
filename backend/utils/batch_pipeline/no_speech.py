"""Strict-VAD classification and digest-approved no-speech terminal planning.

Planning is read-only: it decodes retained raw-live audio in memory, runs the
repository's strict local VAD, and never writes. Apply re-proves the exact row
revision and measurement before one fenced lifecycle close. No audio object or
conversation row is deleted; the operator undo restores the saved fields.

Every disposition is a closed label. Reports contain aggregate counts and
audio seconds only; identities, object paths and decoded audio never leave the
process.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
import time

from google.api_core.exceptions import PreconditionFailed
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from config.refactor_modes import no_speech_terminal_enabled
from config.no_speech_terminal import EXITS, OPERATION
from database import no_speech_terminal as terminal_db
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils import encryption
from utils.batch_pipeline.live import record_identity
from utils.batch_pipeline.record_orphan_repair import (
    candidate_refusal,
    privacy_read,
    row_state,
)
from utils.batch_pipeline.record_seal_nojob import conversation_path
from utils.batch_pipeline.record_seal_repair import plan_digest
from utils.batch_pipeline.source_audio import read_reference
from utils.batch_pipeline.no_speech_coverage import CoverageIncomplete, capture_bounds, covered_pcm, source_start
from utils.conversations import lifecycle
from utils.batch_pipeline.no_speech_undo import undo_no_speech as undo_no_speech
from utils.other.storage import list_audio_chunks, private_cloud_sync_bucket
from utils.stt.local_vad import offline_pcm_speech_segments

SPEECH_LIMIT_SECONDS = 10.0
MAX_RAW_OBJECTS = 4096
MAX_AUDIO_SECONDS = 7200

ACTIONABLE = frozenset({'no_speech'})


def discover(client, *, limit=128, after=None, now=None):
    """Newest-first bounded page of stale batch-live in-progress captures.

    ``after`` is the private cursor ``{'created_at': iso, 'path': path}``. A
    page shorter than ``limit`` ends the pass and resets the cursor so the next
    invocation revisits rows that appeared behind it.
    """
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('discovery limit must be 1..128')
    now = now or datetime.now(timezone.utc)
    query = (
        client.collection_group('conversations')
        .where(filter=FieldFilter('record_lane_owner', '==', 'batch_live_v1'))
        .where(filter=FieldFilter('status', '==', 'in_progress'))
        .where(filter=FieldFilter('created_at', '<', now))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .order_by('__name__', direction=firestore.Query.DESCENDING)
        .select(('created_at',))
        .limit(limit)
    )
    if after is not None:
        created = after.get('created_at')
        path = after.get('path')
        if not isinstance(created, str) or not isinstance(path, str):
            raise ValueError('invalid private cursor')
        conversation_path(path)
        query = query.start_after({'created_at': datetime.fromisoformat(created), '__name__': client.document(path)})
    paths, cursor = [], None
    for snapshot in query.stream():
        data = snapshot.to_dict() or {}
        created = data.get('created_at')
        if not isinstance(created, datetime):
            continue
        paths.append(snapshot.reference.path)
        cursor = {'created_at': created.isoformat(), 'path': snapshot.reference.path}
    return paths, (cursor if len(paths) == limit else None)


def _snapshot(store, uid, cid):
    snapshot = store.client.collection('users').document(uid).collection('conversations').document(cid).get()
    return (snapshot.to_dict() or {}) if snapshot.exists else {}, terminal_db.revision(snapshot)


def _job_exists(store, uid, cid):
    _, job_id = record_identity(uid, cid)
    return store.client.collection(f'{store.namespace}_jobs').document(job_id).get().exists


def _raw_refs(storage_client, uid, cid):
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    refs = []
    for index, blob in enumerate(
        bucket.list_blobs(prefix=f'raw-live/{uid}/{cid}/', page_size=200, timeout=30, retry=None)
    ):
        if index >= MAX_RAW_OBJECTS:
            raise ValueError('raw object budget exceeded')
        metadata = blob.metadata or {}
        refs.append(
            {
                'path': blob.name,
                'bucket': private_cloud_sync_bucket,
                'generation': str(blob.generation),
                'metadata': metadata,
                'size': blob.size,
                'metageneration': blob.metageneration,
                'sample_rate': int(metadata.get('record_sample_rate', 16000)),
            }
        )
    refs.sort(key=lambda ref: ref['path'])
    return refs


def _measure(storage_client, uid, cid, refs, row):
    key = encryption.derive_key(uid)
    capture_bounds(row, MAX_AUDIO_SECONDS)
    sources, decoded_bytes = [], 0
    for ref in refs:
        if (
            type(ref.get('size')) is not int
            or ref['size'] <= 0
            or type(ref.get('metageneration')) is not int
            or ref['metageneration'] <= 0
        ):
            raise CoverageIncomplete('coverage_incomplete')
        chunk = read_reference(
            storage_client, ref, uid, cid, {private_cloud_sync_bucket}, key, source_metadata=True, listed_source=ref
        )
        if not chunk or len(chunk) % 2:
            raise ValueError('invalid retained PCM')
        decoded_bytes += len(chunk)
        if decoded_bytes > MAX_AUDIO_SECONDS * 32000:
            raise ValueError('retained audio budget exceeded')
        sources.append((source_start(ref, chunk), chunk))
    pcm = covered_pcm(row, sources, MAX_AUDIO_SECONDS)
    spans = offline_pcm_speech_segments(bytes(pcm))
    speech = math.fsum(span['duration'] for span in spans)
    if not math.isfinite(speech) or speech < 0:
        raise ValueError('invalid speech measurement')
    return speech, len(pcm) / 32000


def _legacy_chunks(storage_client, uid, cid):
    return list_audio_chunks(
        uid,
        cid,
        max_count=MAX_RAW_OBJECTS,
        require_archive=True,
        include_raw=True,
        client=storage_client,
        source_metadata=True,
    )


def _classify(*, speech_seconds, raw_objects, legacy_objects):
    if raw_objects:
        return 'no_speech' if speech_seconds < SPEECH_LIMIT_SECONDS else 'has_speech'
    if legacy_objects:
        return 'retained_audio_unmeasured'
    return 'coverage_incomplete'


def _measure_row(storage_client, uid, cid, row):
    """Return (disposition, speech_seconds, audio_seconds, raw_objects, legacy_objects)."""
    refs = _raw_refs(storage_client, uid, cid)
    if refs:
        try:
            speech, audio = _measure(storage_client, uid, cid, refs, row)
        except BatchPrivacyBlocked:
            raise
        except (CoverageIncomplete, PreconditionFailed):
            return 'coverage_incomplete', None, None, len(refs), 0
        except Exception:
            return 'decode_failed', None, None, len(refs), 0
        return (
            _classify(speech_seconds=speech, raw_objects=len(refs), legacy_objects=0),
            speech,
            audio,
            len(refs),
            0,
        )
    legacy = _legacy_chunks(storage_client, uid, cid)
    return (
        'coverage_incomplete' if not legacy else 'retained_audio_unmeasured',
        None,
        None,
        0,
        len(legacy),
    )


def plan_no_speech(store, paths, storage_client, *, run_id=None, now=None, pace=0.0):
    if run_id == '' or len(paths) > 128 or len(set(paths)) != len(paths):
        raise ValueError('bounded unique discovery page required')
    now = now or datetime.now(timezone.utc)
    entries = []
    for path in paths:
        entry = {'path': path, 'disposition': 'read_error'}
        try:
            uid, cid = conversation_path(path)
            generation = store.run(lambda tx: privacy_read(tx, uid, (cid,)))
            row, revision = _snapshot(store, uid, cid)
            reason = candidate_refusal(row, now)
            if reason:
                entry['disposition'] = reason
            elif row.get(terminal_db.MARKER):
                entry['disposition'] = 'already_marked'
            elif _job_exists(store, uid, cid):
                entry['disposition'] = 'already_registered'
            else:
                disposition, speech, audio, raw_objects, legacy_objects = _measure_row(storage_client, uid, cid, row)
                entry.update(
                    disposition=disposition,
                    raw_objects=raw_objects,
                    legacy_objects=legacy_objects,
                )
                if speech is not None:
                    entry['speech_seconds'] = speech
                    entry['audio_seconds'] = audio
                if disposition in ACTIONABLE:
                    entry.update(
                        row_sha256=row_state(row),
                        privacy_generation=generation,
                        revision=revision,
                    )
            # Validate each row's disposition inside its own failure boundary.
            # Future/odd refusal labels cannot abort another row's plan.
            if entry['disposition'] not in EXITS:
                raise ValueError('unknown disposition')
        except BatchPrivacyBlocked:
            entry['disposition'] = 'privacy_blocked'
        except (ValueError, TypeError, KeyError):
            entry['disposition'] = 'proof_refused'
        except Exception:
            entry['disposition'] = 'read_error'
        entry['exit'] = EXITS.get(entry['disposition'], 'operator_review')
        entries.append(entry)
        if pace:
            time.sleep(pace)
    body = {'operation': OPERATION, 'namespace': store.namespace, 'entries': entries}
    # Bind run identity to the page proof so dry-run and apply reconstruct the
    # same approval; a random CLI run id would invalidate every reviewed digest.
    body['run_id'] = run_id if run_id is not None else plan_digest(body)
    return {**body, 'plan_sha256': plan_digest(body)}


class NoSpeechRefused(ValueError):
    pass


def _reprove(store, storage_client, entry, now):
    uid, cid = conversation_path(entry['path'])
    store.run(lambda tx: privacy_read(tx, uid, (cid,), expected_generation=entry['privacy_generation']))
    row, revision = _snapshot(store, uid, cid)
    if revision != entry['revision'] or row_state(row) != entry['row_sha256']:
        raise NoSpeechRefused('state_changed')
    if candidate_refusal(row, now) or row.get(terminal_db.MARKER) or _job_exists(store, uid, cid):
        raise NoSpeechRefused('state_changed')
    disposition, speech, audio, _, _ = _measure_row(storage_client, uid, cid, row)
    if disposition == 'coverage_incomplete':
        raise NoSpeechRefused('coverage_incomplete')
    if disposition != entry['disposition']:
        raise NoSpeechRefused('state_changed')
    if disposition == 'no_speech' and (speech is None or abs(speech - entry['speech_seconds']) > 1e-6):
        raise NoSpeechRefused('state_changed')
    return uid, cid, speech, audio


def apply_no_speech(store, plan, approved_digest, storage_client, *, ledger, pace=0.0):
    body = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    if approved_digest != plan['plan_sha256'] or plan_digest(body) != approved_digest:
        raise ValueError('fresh dry-run plan approval required')
    if plan['operation'] != OPERATION or plan['namespace'] != store.namespace or len(plan['entries']) > 128:
        raise ValueError('plan target changed')
    outcomes = Counter()
    for entry in plan['entries']:
        action = entry['disposition']
        if action not in ACTIONABLE:
            outcomes[action] += 1
            continue
        if not no_speech_terminal_enabled():
            outcomes['disabled'] += 1
            continue
        try:
            uid, cid, speech, audio = _reprove(store, storage_client, entry, datetime.now(timezone.utc))
            token = ledger.prepare(entry, uid, cid, plan['run_id'])
            revision = lifecycle.close_no_speech_capture(
                uid,
                cid,
                expected_revision=entry['revision'],
                expected_privacy_generation=entry['privacy_generation'],
                run_id=plan['run_id'],
                speech_seconds=speech or 0.0,
                audio_seconds=audio or 0.0,
                firestore_client=store.client,
            )
            ledger.committed(token, revision)
            outcome = 'committed_revision_unknown' if revision == terminal_db.COMMITTED_REVISION_UNKNOWN else 'closed'
            outcomes[outcome] += 1
        except BatchPrivacyBlocked:
            outcomes['privacy_blocked'] += 1
        except NoSpeechRefused as error:
            outcomes[str(error)] += 1
        except terminal_db.NoSpeechConflict as error:
            outcomes[str(error)] += 1
        except Exception:
            outcomes['write_error'] += 1
        if pace:
            time.sleep(pace)
    return dict(sorted(outcomes.items()))


def summary(plan):
    counts = Counter(entry['disposition'] for entry in plan['entries'])
    return {
        'operation': OPERATION,
        'plan_sha256': plan['plan_sha256'],
        'count': len(plan['entries']),
        'dispositions': dict(sorted(counts.items())),
        'exits': {key: EXITS[key] for key in sorted(counts)},
        'actionable': sum(n for key, n in counts.items() if key in ACTIONABLE),
        'skipped': sum(n for key, n in counts.items() if key not in ACTIONABLE),
        'measured_speech_seconds': sum(entry.get('speech_seconds', 0.0) for entry in plan['entries']),
        'measured_audio_seconds': sum(entry.get('audio_seconds', 0.0) for entry in plan['entries']),
        'raw_objects': sum(entry.get('raw_objects', 0) for entry in plan['entries']),
        'legacy_objects': sum(entry.get('legacy_objects', 0) for entry in plan['entries']),
    }
