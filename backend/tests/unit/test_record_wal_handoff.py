"""Synthetic all-file custody, crash replay, privacy and rollback contracts."""

import base64
import asyncio
import math
from copy import deepcopy
import hashlib
import json
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import google_crc32c
from cryptography.exceptions import InvalidTag
from google.api_core.exceptions import PreconditionFailed, ServiceUnavailable
from google.cloud.exceptions import NotFound
import pytest

from config import batch_pipeline_record_wal_handoff as config
from database import record_wal_handoff as database
from database import record_wal_capacity as capacity
from utils.batch_pipeline import intake
from utils.other import audio_opus
from database.batch_pipeline_privacy import privacy_owner_key, BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreStore
from models.sync_job_status import SyncJobStartResponse, SyncJobStatusResponse
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import live_upload, record_wal_handoff as handoff, record_wal_metrics as metrics
from utils.batch_pipeline.artifact_reads import ArtifactReadLimit
from utils.batch_pipeline.intake import durable_status
from utils.other import storage
from utils.other.local_storage import LocalStorageClient
from utils.sync import record_token_lease
from utils.sync.poll_limit import with_poll_hint

UID, CID, NS = 'synthetic-wal-owner', 'synthetic-record', 'batch_pipeline_dev'
ROW_PATH = ('users', UID, 'conversations', CID)
ROW = {
    'record_lane_owner': 'batch_live_v1',
    'source': 'omi',
    'client_device_id': 'synthetic-device',
    'private_cloud_sync_enabled': True,
    'record_upload_revision': 7,
    'status': 'completed',
    'record_audio_closed': True,
}


class Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.metadata = bucket, name, {}
        self.generation, self.size, self.crc32c = None, None, None

    def upload_from_string(self, raw, **kwargs):
        assert kwargs['if_generation_match'] == 0 and kwargs['retry'] is None
        self.bucket.attempts += 1
        if self.name in self.bucket.rows:
            raise PreconditionFailed('synthetic create collision')
        if self.bucket.fail_at == self.bucket.attempts:
            raise OSError('synthetic write failure')
        self.bucket.rows[self.name] = {'raw': raw, 'metadata': deepcopy(self.metadata), 'generation': 1}
        self.reload()
        if self.bucket.after_upload:
            self.bucket.after_upload()

    def reload(self, **kwargs):
        row = self.bucket.rows.get(self.name)
        if row is None:
            raise NotFound('synthetic missing object')
        self.metadata = deepcopy(row['metadata'])
        self.generation = row.get('generation')
        self.size = len(row['raw']) + self.bucket.size_delta
        self.crc32c = base64.b64encode(google_crc32c.value(row['raw']).to_bytes(4, 'big')).decode()
        if self.bucket.bad_checksum:
            self.crc32c = 'AAAAAA=='

    def download_as_bytes(self, **kwargs):
        assert kwargs['if_generation_match'] == self.generation
        return self.bucket.rows[self.name]['raw']

    def delete(self, **kwargs):
        assert kwargs['if_generation_match'] == self.bucket.rows[self.name]['generation']
        self.bucket.rows.pop(self.name)


class Bucket:
    name = 'synthetic-wal-bucket'

    def __init__(self):
        self.rows, self.attempts = {}, 0
        self.fail_at, self.after_upload = None, None
        self.size_delta, self.bad_checksum = 0, False

    def blob(self, name):
        return Blob(self, name)


def make_wal(tmp_path, ordinal, codec='pcm16', payload=None):
    path = tmp_path / f'audio_omi_{codec}_16000_1_fs160_{1700000000 + ordinal}.bin'
    packet = payload if payload is not None else struct.pack('<h', ordinal + 1) * 160
    path.write_bytes(struct.pack('<I', len(packet)) + packet)
    return path


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-wal-handoff-test-secret')
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'true')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
    client = StrictFirestore({('users', UID): {'private_cloud_sync_enabled': True}, ROW_PATH: ROW})
    store = FirestoreStore(NS, firestore_client=client)
    bucket = Bucket()
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda _: bucket))
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', bucket.name)
    monkeypatch.setattr(
        storage.conversation_tombstones,
        'is_deleted',
        lambda uid, cid: (('users', uid, 'deleted_conversations', cid) in client.rows),
    )
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    forbidden = Mock(side_effect=AssertionError('phase 1 decoded or dispatched audio'))
    monkeypatch.setattr(live_upload, 'decode_units', forbidden)
    monkeypatch.setattr(live_upload, 'artifacts_for', forbidden)
    paths = [make_wal(tmp_path, ordinal) for ordinal in range(2)]

    async def upload(upload_paths=None, **kwargs):
        return await live_upload.registered_record_response(
            uid=UID,
            conversation_id=CID,
            content_id='synthetic-upload',
            paths=paths if upload_paths is None else upload_paths,
            source='omi',
            client_device_id='synthetic-device',
            loaded_conversation=deepcopy(client.rows.get(ROW_PATH, ROW)),
            policy=SimpleNamespace(live_admission_enabled=False, live_record_enabled=True),
            **kwargs,
        )

    def rows(table):
        entries = {path[-1]: row for path, row in client.rows.items() if path[0] == f'{NS}_intakes'}
        if table == 'wal_handoffs':
            return {key: row for key, row in entries.items() if row.get('kind') == database.BUNDLE_KIND}
        file_rows = {key: row for key, row in entries.items() if row.get('kind') == database.FILE_KIND}
        if table == 'wal_files':
            return file_rows
        if table in {'wal_obligations', 'wal_outbox'}:
            field = 'obligation' if table == 'wal_obligations' else 'outbox'
            return {key: row[field] for key, row in file_rows.items()}
        return {path[-1]: row for path, row in client.rows.items() if path[0] == f'{NS}_{table}'}

    return SimpleNamespace(client=client, store=store, bucket=bucket, paths=paths, upload=upload, rows=rows)


@pytest.mark.parametrize(
    'failure_at, failure',
    [
        ('inventory', ArtifactReadLimit('archive count limit')),
        ('inventory', KeyError('missing manifest')),
        ('inventory', InvalidTag()),
        ('parse', struct.error('truncated WAL')),
        ('revalidate', ServiceUnavailable('final snapshot read failed')),
        ('commit', ServiceUnavailable('uncertain CAS')),
        ('timeout_before_commit', None),
        ('timeout_after_commit', None),
    ],
)
async def test_duplicate_settlement_only_falls_back_before_commit(world, monkeypatch, failure_at, failure):
    from config.record_audio import record_identity
    from utils.batch_pipeline import record_wal_duplicate as duplicate

    job = 'bp_' + record_identity(UID, CID)[0]
    world.client.rows[(f'{NS}_intakes', job)] = {'segment_ids': ['segment']}
    world.client.rows[(f'{NS}_jobs', 'segment')] = {'state': 'committed'}
    monkeypatch.setattr(duplicate, 'select', lambda *_: ('settle', None))

    def staged(paths, budget, *, descriptors):
        if failure_at == 'parse':
            raise failure
        descriptors['wal'] = {}
        return [('wal', 1, [])]

    monkeypatch.setattr(duplicate.sample, 'read_staged_packets', staged)
    prepared = SimpleNamespace(prior=None, scope=SimpleNamespace(source={}))
    late_dispatch = []

    def reconcile_snapshot(*args, commit=False, before_commit=None, **kwargs):
        if not commit:
            return prepared
        if failure_at == 'commit':
            before_commit()
        else:
            late_dispatch.append(before_commit)
        raise failure

    reconcile = Mock(side_effect=reconcile_snapshot)
    monkeypatch.setattr(duplicate.ledger, 'reconcile', reconcile)
    inventory = Mock(side_effect=failure if failure_at == 'inventory' else None)
    monkeypatch.setattr(duplicate, '_inventory', inventory)
    monkeypatch.setattr(duplicate, '_placements', lambda *_: (['proved'], False))
    monkeypatch.setattr(duplicate, '_recheck', lambda *_: None)
    legacy = AsyncMock(return_value=live_upload.JSONResponse(status_code=202, content={'job_id': job}))
    monkeypatch.setattr(live_upload, '_answer_registered_upload', legacy)

    if failure is None:
        timeout = asyncio.timeout(None)
        monkeypatch.setattr(duplicate.asyncio, 'timeout', lambda _: timeout)

        async def offload(executor, body, *args, **kwargs):
            if kwargs.get('commit'):
                if failure_at == 'timeout_after_commit':
                    kwargs['before_commit']()
                else:
                    late_dispatch.append(kwargs['before_commit'])
                timeout.reschedule(asyncio.get_running_loop().time())
                await asyncio.Future()
            return body(*args, **kwargs)

        monkeypatch.setattr(duplicate, 'run_blocking', offload)

    response = await world.upload(upload_paths=world.paths[:1], capture_claims={'wal': {}})
    if failure_at in ('commit', 'timeout_after_commit'):
        assert response.status_code == 503
        legacy.assert_not_awaited()
        if failure_at == 'commit':
            assert reconcile.call_count == 2 and reconcile.call_args.kwargs['commit'] is True
    else:
        assert response.status_code == 202
        legacy.assert_awaited_once()
        assert (
            reconcile.call_count
            == {'parse': 0, 'inventory': 1, 'revalidate': 2, 'timeout_before_commit': 1}[failure_at]
        )
        if late_dispatch:
            with pytest.raises(ArtifactReadLimit, match='cancelled before dispatch'):
                late_dispatch[0]()


async def test_legacy_coverage_cannot_replace_a_concurrently_settled_alias(world, monkeypatch):
    from config.record_audio import record_identity
    from config.record_wal_duplicate import RECEIPT_FIELD
    from utils.batch_pipeline import record_lease_append

    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'false')
    monkeypatch.setattr(live_upload, 'coverage_wait_memo_enabled', lambda: False)
    monkeypatch.setattr(record_lease_append, 'retain_upload', AsyncMock())
    monkeypatch.setattr(live_upload, 'artifacts_for', lambda _: object())
    legacy = Mock(side_effect=AssertionError('legacy status must not redrive a settled alias'))
    monkeypatch.setattr(live_upload, 'durable_status', legacy)
    canonical = record_identity(UID, CID)[0]
    job = 'bp_' + canonical
    world.client.rows[(f'{NS}_intakes', job)] = {'segment_ids': ['segment']}
    world.client.rows[(f'{NS}_jobs', 'segment')] = {'state': 'committed'}
    original = {'dispatch_protocol': 'batch_v1', 'job_id': job, 'status': 'completed'}
    world.store.run(lambda tx: tx.put('content', f'{UID}/{canonical}', original))
    alias_key = f'{UID}/synthetic-upload'
    winner = {**original, 'record_content_id': canonical, RECEIPT_FIELD: {'scope': 'synthetic'}}

    def covered(*args):
        world.store.run(lambda tx: tx.put('content', alias_key, winner))
        return True

    monkeypatch.setattr(live_upload, '_covered', covered)
    response = await world.upload()
    assert response.status_code == 503
    assert world.store.run(lambda tx: tx.get('content', alias_key)) == winner
    legacy.assert_not_called()


async def test_all_files_accepted_before_decode_and_completed_native_job_never_completes_upload(world):
    response = await world.upload()
    assert response.status_code == 202
    start = json.loads(response.body)
    SyncJobStartResponse(**start)
    assert start['job_id'].startswith(database.JOB_PREFIX)
    assert start['status'] == 'processing' and start['total_files'] == 2
    for _ in range(3):
        status = durable_status(world.store, UID, start['job_id'])
        SyncJobStatusResponse(**status)
        assert status['status'] == 'processing' and status.get('result') is None
        assert status['reason_code'] == database.PENDING_REASON
        assert with_poll_hint(status)['poll_after_ms'] == 300000
        assert with_poll_hint(status, surface_open=True)['poll_after_ms'] == 300000
    assert len(world.bucket.rows) == len(world.rows('wal_files')) == len(world.rows('wal_obligations')) == 2
    assert len(world.rows('wal_outbox')) == 2
    assert world.client.rows[ROW_PATH]['record_upload_revision'] == 8
    assert next(iter(world.rows('wal_handoffs').values()))['base_upload_revision'] == 7
    assert all(
        'expires_at' not in row
        for table in ('wal_handoffs', 'wal_files', 'wal_obligations', 'wal_outbox')
        for row in world.rows(table).values()
    )
    assert all(path.exists() for path in world.paths)
    assert all(row['state'] == 'pending' for row in world.rows('wal_obligations').values())
    # Exact create-only originals, no paid job, queue or provider reservation.
    assert not world.rows('jobs') and not world.rows('queues')


async def test_file_two_failure_has_no_acceptance_then_fresh_nonce_retry_reuses_first_generation(world):
    world.bucket.fail_at = 2
    assert (await world.upload()).status_code == 503
    assert len(world.bucket.rows) == 1
    first = deepcopy(world.bucket.rows)
    assert not world.rows('wal_files') and not world.rows('wal_obligations') and not world.rows('wal_outbox')
    assert all(row['state'] == 'preparing' for row in world.rows('wal_handoffs').values())
    world.bucket.fail_at = None
    response = await world.upload()
    assert response.status_code == 202
    assert all(world.bucket.rows[path] == row for path, row in first.items())
    assert world.client.rows[ROW_PATH]['record_upload_revision'] == 8


async def test_lost_response_after_receipt_replays_same_handle_without_any_storage_or_second_revision(
    world, monkeypatch
):
    original = database.commit
    committed = []

    def lose_reply(*args):
        receipt = original(*args)
        committed.append(receipt)
        raise OSError('synthetic response lost after atomic commit')

    monkeypatch.setattr(database, 'commit', lose_reply)
    assert (await world.upload()).status_code == 503
    assert len(committed) == 1 and len(world.rows('wal_outbox')) == 2
    attempts = world.bucket.attempts
    monkeypatch.setattr(database, 'commit', original)
    response = await world.upload()
    assert response.status_code == 202
    assert json.loads(response.body)['job_id'] == committed[0]['job_id']
    assert world.bucket.attempts == attempts
    assert world.client.rows[ROW_PATH]['record_upload_revision'] == 8


async def test_rebundling_reuses_file_obligation_and_wake(world):
    one = await world.upload([world.paths[0]])
    assert one.status_code == 202
    first_work = deepcopy(world.rows('wal_obligations'))
    assert (await world.upload(list(reversed(world.paths)))).status_code == 202
    assert len(world.rows('wal_obligations')) == len(world.rows('wal_outbox')) == 2
    assert all(world.rows('wal_obligations')[key] == row for key, row in first_work.items())
    assert world.bucket.attempts == 2
    # Request ordering cannot change the stable bundle handle.
    again = await world.upload()
    assert json.loads(again.body)['job_id'] != json.loads(one.body)['job_id']
    assert world.bucket.attempts == 2


@pytest.mark.parametrize('malformation', ['truncated_header', 'truncated_frame', 'empty', 'bad_pcm', 'bad_name'])
async def test_malformed_final_file_never_stores_or_accepts_partial_bundle(world, malformation):
    path = world.paths[1]
    if malformation == 'bad_name':
        other = path.with_name('unknown.bin')
        path.rename(other)
        world.paths[1] = other
    else:
        path.write_bytes(
            {
                'truncated_header': b'\x01',
                'truncated_frame': struct.pack('<I', 20) + b'x',
                'empty': b'',
                'bad_pcm': struct.pack('<I', 1) + b'x',
            }[malformation]
        )
    assert (await world.upload()).status_code == 503
    assert not world.bucket.rows and not world.rows('wal_handoffs')


@pytest.mark.parametrize('field', ['sha256', 'size'])
async def test_changed_upload_between_inspection_and_storage_is_refused(world, monkeypatch, field):
    original = handoff.inspect_files

    def forged(paths):
        entries = original(paths)
        entries[1][field] = '0' * 64 if field == 'sha256' else entries[1][field] + 1
        return entries

    monkeypatch.setattr(handoff, 'inspect_files', forged)
    assert (await world.upload()).status_code == 503
    assert not world.rows('wal_obligations')


@pytest.mark.parametrize('corruption', ['bytes', 'metadata', 'generation', 'size', 'checksum'])
async def test_create_collision_requires_full_object_identity_not_existence(world, corruption):
    world.bucket.fail_at = 2
    assert (await world.upload()).status_code == 503
    row = next(iter(world.bucket.rows.values()))
    if corruption == 'bytes':
        row['raw'] = b'synthetic changed ciphertext'
    elif corruption == 'metadata':
        row['metadata']['wal_name'] = 'different.bin'
    elif corruption == 'generation':
        row['generation'] = None
    elif corruption == 'size':
        world.bucket.size_delta = 1
    else:
        world.bucket.bad_checksum = True
    world.bucket.fail_at = None
    assert (await world.upload()).status_code == 503
    assert not world.rows('wal_files') and not world.rows('wal_obligations')


@pytest.mark.parametrize('race', ['owner', 'device', 'deleted', 'optout', 'account_deleted', 'generation'])
@pytest.mark.parametrize('during_write', [False, True])
async def test_privacy_and_owner_races_never_accept_or_dispatch(world, race, during_write):
    def change():
        row = world.client.rows[ROW_PATH]
        if race == 'owner':
            row['record_lane_owner'] = 'batch_sync_v1'
        elif race == 'device':
            row['client_device_id'] = 'different-synthetic-device'
        elif race == 'deleted':
            world.client.rows['users', UID, 'deleted_conversations', CID] = {'deleted': True}
        elif race == 'optout':
            world.client.rows['users', UID]['private_cloud_sync_enabled'] = False
        elif race == 'account_deleted':
            world.client.rows['account_deletions', UID] = {'wipe_status': 'in_progress'}
        else:
            world.client.rows['batch_pipeline_privacy', privacy_owner_key(UID)] = {
                'generation': 2,
                'purging': not during_write,
            }

    if during_write:
        world.bucket.after_upload = change
    else:
        change()
    response = await world.upload()
    if not during_write and race == 'owner':
        assert response is live_upload.RecordUploadRoute.BATCH
    else:
        assert response.status_code in {409, 503}
    assert not world.rows('wal_obligations') and not world.rows('wal_files') and not world.rows('wal_outbox')
    assert not any(row['state'] == 'accepted' for row in world.rows('wal_handoffs').values())
    if during_write and race in {'deleted', 'optout', 'account_deleted', 'generation'}:
        assert not world.bucket.rows


async def test_admission_off_restores_strict_503_but_receipts_replay_and_poll(world, monkeypatch):
    assert config.handoff_enabled()
    response = await world.upload()
    assert response.status_code == 202
    job_id = json.loads(response.body)['job_id']
    attempts = world.bucket.attempts
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'false')
    assert not config.handoff_enabled()
    assert (await world.upload()).status_code == 202
    assert world.bucket.attempts == attempts
    assert durable_status(world.store, UID, job_id)['status'] == 'processing'
    # A different exact upload remains on the original strict path.
    world.paths[1].write_bytes(world.paths[1].read_bytes() + struct.pack('<I', 2) + b'xx')
    assert (await world.upload()).status_code == 503
    assert world.bucket.attempts == attempts


async def test_receipt_owns_202_without_rearming_optional_token_lease(world, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setattr(record_token_lease.record_custody_append, 'get_firestore_client', lambda: world.client)
    forbidden = Mock(side_effect=AssertionError('phase 1 woke native partial recovery'))
    monkeypatch.setattr(record_token_lease.record_custody_append, 'prepare_recovery', forbidden)

    @record_token_lease.custody_upload
    async def upload():
        await record_token_lease.begin_upload(UID, CID, 'synthetic-request')
        return await world.upload()

    assert (await upload()).status_code == 202
    assert world.client.rows[ROW_PATH]['record_upload_revision'] == 8
    assert not world.client.rows[ROW_PATH].get('record_upload_sessions')
    forbidden.assert_not_called()


@pytest.mark.parametrize('toc,samples', [(b'\xf0', 160), (b'\xf8', 320)])
def test_synthetic_opus_header_is_inspected_without_decoding(tmp_path, toc, samples):
    path = make_wal(tmp_path, 0, codec='opus', payload=toc + b'\xff\xfe')
    renamed = path.with_name(path.name.replace('fs160', f'fs{samples}'))
    path.rename(renamed)
    entries = handoff.inspect_files([renamed])
    assert entries[0]['sample_count'] == samples and entries[0]['codec'] == 'opus'


def test_opus_frame_header_must_match_declared_frame_geometry(tmp_path):
    path = make_wal(tmp_path, 0, codec='opus', payload=b'\xf8\xff\xfe')
    with pytest.raises(ValueError):
        handoff.inspect_files([path])


def test_filename_binding_changes_identity_even_with_identical_bytes(tmp_path):
    first, second = make_wal(tmp_path, 0), make_wal(tmp_path, 1)
    second.write_bytes(first.read_bytes())
    assert database.bundle_id(UID, CID, handoff.inspect_files([first])) != database.bundle_id(
        UID, CID, handoff.inspect_files([second])
    )


async def test_privacy_change_after_last_object_before_receipt_erases_unaccepted_originals(world, monkeypatch):
    original = database.commit

    def race(*args):
        world.client.rows['batch_pipeline_privacy', privacy_owner_key(UID)] = {'generation': 9}
        return original(*args)

    monkeypatch.setattr(database, 'commit', race)
    assert (await world.upload()).status_code == 503
    assert not world.bucket.rows and not world.rows('wal_files') and not world.rows('wal_outbox')


async def test_cancellation_after_objects_never_accepts_and_retry_recovers(world, monkeypatch):
    original = handoff.run_blocking

    async def cancel(executor, function, *args, **kwargs):
        if function is database.commit:
            raise asyncio.CancelledError()
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(handoff, 'run_blocking', cancel)
    with pytest.raises(asyncio.CancelledError):
        await world.upload()
    assert len(world.bucket.rows) == 2 and not world.rows('wal_obligations')
    assert all(path.exists() for path in world.paths)
    monkeypatch.setattr(handoff, 'run_blocking', original)
    assert (await world.upload()).status_code == 202
    assert len(world.rows('wal_obligations')) == 2


async def test_expired_fence_during_storage_cannot_accept(world, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(database.time, 'time', lambda: now[0])
    world.bucket.after_upload = lambda: now.__setitem__(0, now[0] + database.FENCE_SECONDS + 1)
    assert (await world.upload()).status_code == 503
    assert not world.rows('wal_outbox') and not world.rows('wal_obligations')
    assert all(path.exists() for path in world.paths)


async def test_capacity_overflow_keeps_whole_bundle_on_phone(world):
    assert (await world.upload(world.paths * 11)).status_code == 503
    assert not world.bucket.rows and not world.rows('wal_handoffs')


async def test_accepted_receipt_does_not_bypass_later_erasure_or_optout(world):
    response = await world.upload()
    job_id = json.loads(response.body)['job_id']
    world.client.rows['users', UID]['private_cloud_sync_enabled'] = False
    with pytest.raises(BatchPrivacyBlocked):
        durable_status(world.store, UID, job_id)
    assert (await world.upload()).status_code == 409


async def test_admission_and_accepted_marker_bypass_conversation_memo(world, monkeypatch):
    monkeypatch.setattr(live_upload, 'cached_record_wait', lambda *_: 'record_jobs_missing')
    assert await live_upload.memoized_record_wait(UID, CID) is None
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'false')
    monkeypatch.setattr(database, 'get_data_plane_firestore_client', lambda: world.client)
    assert (await live_upload.memoized_record_wait(UID, CID)).status_code == 503
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'true')
    assert (await world.upload()).status_code == 202
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'false')
    assert await live_upload.memoized_record_wait(UID, CID) is None


def test_pending_metrics_publish_durable_count_age_and_unknown_on_failure(monkeypatch):
    monkeypatch.setattr(metrics, 'pending_sample', lambda *_: (4, 100.0))
    monkeypatch.setattr(metrics, 'capacity_sample', lambda *_: {'bytes': 400, 'files': 4})
    metrics.refresh(SimpleNamespace(client=None, namespace=NS), 200.0)
    assert metrics.pending._value.get() == 4
    assert metrics.pending_bytes._value.get() == 400
    assert metrics.age._value.get() == 100
    assert metrics.sampled_at._value.get() == 200
    monkeypatch.setattr(metrics, 'pending_sample', Mock(side_effect=OSError('synthetic unavailable')))
    metrics.refresh(SimpleNamespace(client=None, namespace=NS), 300.0)
    assert math.isnan(metrics.pending._value.get()) and math.isnan(metrics.age._value.get())
    assert math.isnan(metrics.pending_bytes._value.get())
    assert metrics.sampled_at._value.get() == 200


async def test_local_storage_adapter_retains_verified_originals_across_restart(world, monkeypatch, tmp_path):
    root = tmp_path / 'storage'
    monkeypatch.setattr(storage, '_get_storage_client', lambda: LocalStorageClient(root))
    response = await world.upload()
    assert response.status_code == 202
    receipt = next(iter(world.rows('wal_files').values()))['receipt']
    restarted = LocalStorageClient(root).bucket(storage.private_cloud_sync_bucket)
    blob = restarted.blob(receipt['uri'].split('/', 3)[3].split('#', 1)[0], generation=int(receipt['generation']))
    blob.reload()
    assert blob.size == receipt['stored_size'] and blob.crc32c == receipt['crc32c']
    assert blob.download_as_bytes(if_generation_match=int(receipt['generation']))
    assert (await world.upload()).status_code == 202


def test_unset_admission_is_off_for_reader_first_deployment(monkeypatch):
    monkeypatch.delenv('RECORD_WAL_HANDOFF_ENABLED', raising=False)
    assert config.handoff_enabled() is False


async def test_plain_status_lookup_is_receipt_capable_even_with_admission_unset(world, monkeypatch):
    accepted = json.loads((await world.upload()).body)
    monkeypatch.delenv('RECORD_WAL_HANDOFF_ENABLED', raising=False)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *_: world.store)
    monkeypatch.setattr(
        intake, 'shadow_from_env', Mock(side_effect=AssertionError('WAL status used ordinary jobstore'))
    )
    assert intake.get_durable_job_status(accepted['job_id'], UID)['status'] == 'processing'
    assert (await world.upload()).status_code == 202
    assert world.bucket.attempts == 2


@pytest.mark.parametrize('scope', ['owner', 'global'])
@pytest.mark.parametrize('dimension,limit', [('FILES', '1'), ('BYTES', '355')])
async def test_pending_capacity_refuses_before_any_object_write(world, monkeypatch, scope, dimension, limit):
    monkeypatch.setenv(f'RECORD_WAL_PENDING_{scope.upper()}_{dimension}', limit)
    counter = metrics.capacity_refusals.labels(scope)
    before = counter._value.get()
    response = await world.upload()
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body['code'] == 'record_capture_pending'
    assert counter._value.get() == before + 1
    assert not world.bucket.rows and not world.rows('wal_handoffs')
    assert capacity.sample(world.client) == {'bytes': 0, 'files': 0}
    assert all(path.exists() for path in world.paths)


async def test_crash_reservations_are_charged_once_and_block_distinct_uploads(world, monkeypatch, tmp_path):
    monkeypatch.setenv('RECORD_WAL_PENDING_OWNER_FILES', '2')
    world.bucket.fail_at = 2
    assert (await world.upload()).status_code == 503
    charge = capacity.sample(world.client)
    assert charge == {'bytes': sum(path.stat().st_size + 32 for path in world.paths), 'files': 2}
    assert (await world.upload([make_wal(tmp_path, 2)])).status_code == 503
    assert len(world.bucket.rows) == 1
    world.bucket.fail_at = None
    assert (await world.upload()).status_code == 202
    assert capacity.sample(world.client) == charge
    monkeypatch.setenv('RECORD_WAL_PENDING_OWNER_FILES', '0')
    assert (await world.upload()).status_code == 202
    assert capacity.sample(world.client) == charge


async def test_global_pending_budget_is_shared_between_owners_and_stage_namespaces(world, monkeypatch):
    monkeypatch.setenv('RECORD_WAL_PENDING_GLOBAL_FILES', '2')
    assert (await world.upload()).status_code == 202
    uid = 'synthetic-second-owner'
    world.client.rows[('users', uid)] = {'private_cloud_sync_enabled': True}
    world.client.rows[('users', uid, 'conversations', CID)] = deepcopy(ROW)
    files = handoff.inspect_files(world.paths[:1])
    with pytest.raises(capacity.CapacityExceeded) as error:
        database.begin(world.client, 'batch_pipeline_prod', uid, CID, files, 'omi', 'synthetic-device')
    assert error.value.scope == 'global'
    assert capacity.sample(world.client)['files'] == 2


@pytest.mark.parametrize('name,value', [('OWNER_BYTES', 'bad'), ('GLOBAL_FILES', '-1')])
async def test_invalid_or_closed_capacity_configuration_keeps_phone_custody(world, monkeypatch, name, value):
    monkeypatch.setenv('RECORD_WAL_PENDING_' + name, value)
    assert (await world.upload()).status_code == 503
    assert not world.bucket.rows


@pytest.mark.parametrize(
    'toc,frames,samples',
    [
        (0x00, None, 160),
        (0x18, None, 960),
        (0x60, None, 160),
        (0x68, None, 320),
        (0x80, None, 40),
        (0x88, None, 80),
        (0x90, None, 160),
        (0x98, None, 320),
        (0x99, None, 640),
        (0x9B, 6, 1920),
    ],
)
def test_opus_duration_headers_need_no_native_library(monkeypatch, toc, frames, samples):
    monkeypatch.setattr(audio_opus, 'opuslib', None)
    packet = bytes([toc]) + (bytes([frames]) if frames is not None else b'')
    assert audio_opus.opus_packet_samples(packet, 16000) == samples


@pytest.mark.parametrize('packet', [b'', b'\x9b', b'\x9b\x00', b'\x9b\x07'])
def test_invalid_opus_duration_headers_fail_closed_without_native_library(monkeypatch, packet):
    monkeypatch.setattr(audio_opus, 'opuslib', None)
    with pytest.raises(ValueError):
        audio_opus.opus_packet_samples(packet, 16000)


async def test_quota_release_is_exactly_once_and_preserves_other_files(world):
    assert (await world.upload()).status_code == 202
    files = list(world.rows('wal_files'))
    reference = world.client.collection(NS + '_intakes').document(files[0])
    # Privacy erasure's caller first removes the exact stored generation.
    receipt = world.rows('wal_files')[files[0]]['receipt']
    storage.delete_record_wal_original(UID, receipt)
    capacity.erase_file(world.client, reference, UID)
    capacity.erase_file(world.client, reference, UID)
    assert capacity.sample(world.client) == {'bytes': 356, 'files': 1}
    assert len(world.rows('wal_files')) == len(world.bucket.rows) == 1


async def test_quota_release_reproves_erase_authority_before_counters_change(world):
    assert (await world.upload()).status_code == 202
    file_id = next(iter(world.rows('wal_files')))
    reference = world.client.collection(NS + '_intakes').document(file_id)
    before = capacity.sample(world.client)
    fence = Mock(side_effect=BatchPrivacyBlocked('synthetic erase authority lost'))
    with pytest.raises(BatchPrivacyBlocked):
        capacity.erase_file(world.client, reference, UID, fence=fence)
    assert capacity.sample(world.client) == before and len(world.rows('wal_files')) == 2
