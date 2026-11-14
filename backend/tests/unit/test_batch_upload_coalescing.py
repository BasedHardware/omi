"""Custody state machine with original receipts; synthetic accounts/audio only."""

from copy import deepcopy
from dataclasses import asdict
import json
import struct

import pytest

from config import batch_pipeline_coalescing as config
from database import batch_pipeline_coalescing as rows
from database.batch_pipeline_staging import reap_one
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline.upload_coalescing import _pack, _unpack, member_status, queued


def store():
    result = MemoryStore()
    result.namespace = 'batch_pipeline_test_coalescing'
    result.rows['coalesce_quota', 'global'] = {'groups': 0, 'owners': {}, 'last_scan_at': 10}
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize('pump', ['true', 'false'])
async def test_supervisor_drains_existing_holds_while_producer_off(monkeypatch, pump):
    import asyncio
    from unittest.mock import AsyncMock, Mock
    from types import SimpleNamespace

    from utils.batch_pipeline import serving, upload_coalescing

    monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PUMP_ENABLED', pump)
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'true')
    service = serving.Serving(store())
    service.reconcile_async = AsyncMock()
    service.dispatch_recovery = Mock()
    service.projector = SimpleNamespace(sweep=Mock(), has_async_followups=False, owes_drains=False)
    monkeypatch.setattr(serving, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(serving, 'serving_for_stage', lambda stage: service)
    monkeypatch.setattr(serving, 'drain_recordings', AsyncMock(return_value=0))
    seen = []

    async def drain_existing(target):
        assert target is service.store
        seen.append(target)
        runtime[0].set()
        return 0

    monkeypatch.setattr(upload_coalescing, 'drain', drain_existing)
    runtime = serving.start_serving_from_env()
    try:
        await asyncio.wait_for(runtime[1], timeout=5)
    finally:
        await serving.stop_serving(runtime)
    assert seen == [service.store]


def member(name, start=100, **changes):
    work = item('hold-' + name, owner='owner')
    return {
        'owner_id': 'owner',
        'owner_key': 'owner-hash',
        'conversation_id': 'recording',
        'privacy_generation': 0,
        'content_id': name,
        'job_id': 'bp_' + name,
        'item': asdict(work),
        'uri': 'gs://synthetic/object#1',
        'bytes': 100,
        'files': 1,
        'filenames': [name],
        'seconds': 10,
        'start': start,
        'end': start + 10,
        'original_units': 1,
        'lane': 'fresh',
        'hold_seconds': 60,
        **changes,
    }


def group(s):
    return next(v for (table, _), v in s.rows.items() if table == 'coalesce_groups')


@pytest.mark.parametrize(
    'value,expected', [(None, False), ('false', False), ('1', False), ('on', False), ('true', True), (' TRUE ', True)]
)
def test_only_explicit_true_enables_new_holds(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', value)
    assert config.enabled() is expected


@pytest.mark.parametrize(
    'deadline,reserve,expected',
    [
        (None, None, 0),
        (600, None, 0),
        (600, 100, 60),
        (440, 100, 40),
        (400, 100, 0),
        (399, 100, 0),
        (float('nan'), 1, 0),
        (600, -1, 0),
    ],
)
def test_real_stale_budget_never_guessed_or_reset(deadline, reserve, expected):
    assert config.hold_seconds(deadline=deadline, reserve=reserve, now=300) == expected
    assert config.hold_seconds(now=300, batch_pre_unit=True) == 60


def test_reordered_duplicate_uploads_seal_one_fixed_deadline():
    s = store()
    assert rows.enqueue(s, member('later', 120), 'record-key', 10) == 'bp_later'
    rows.note_scan(s, 30, producer_enabled=True)
    assert rows.enqueue(s, member('earlier', 100), 'record-key', 30) == 'bp_earlier'
    before = deepcopy(s.rows)
    assert rows.enqueue(s, member('later', 120), 'record-key', 50) == 'bp_later'
    assert s.rows == before
    assert group(s)['release_by'] == 70
    assert rows.claim(s, group(s)['id'], 69.9, producer_enabled=True) is None
    sealed = rows.claim(s, group(s)['id'], 70, producer_enabled=True)
    assert [m['content_id'] for m in sealed['members']] == ['earlier', 'later']
    assert rows.claim(s, sealed['id'], 71, producer_enabled=True) is None
    assert rows.enqueue(s, member('next', 140), 'record-key', 71) == 'wait'


def test_overlap_is_not_timestamp_dedup_and_releases_predecessor():
    s = store()
    rows.enqueue(s, member('first'), 'key', 10)
    assert rows.enqueue(s, member('different-bytes', 105), 'key', 11) == 'wait'
    assert group(s)['release_by'] == 11
    assert len(group(s)['members']) == 1
    assert ('content', 'owner/different-bytes') not in s.rows


def test_global_and_per_owner_quotas_decline_without_claiming_upload(monkeypatch):
    monkeypatch.setattr(config, 'MAX_OWNER_GROUPS', 1)
    s = store()
    rows.enqueue(s, member('first'), 'key1', 10)
    assert rows.enqueue(s, member('second'), 'key2', 11) is None
    assert ('content', 'owner/second') not in s.rows
    assert s.rows['coalesce_quota', 'global']['groups'] == 1


def test_missing_or_stalled_drainer_does_not_accept_new_custody():
    s = store()
    assert rows.enqueue(s, member('first'), 'key', 16) is None
    del s.rows['coalesce_quota', 'global']
    assert rows.enqueue(s, member('first'), 'key', 10) is None
    rows.note_scan(s, 10, producer_enabled=False)
    assert ('coalesce_quota', 'global') not in s.rows
    rows.note_scan(s, 10, producer_enabled=True)
    assert rows.enqueue(s, member('first'), 'key', 11) == 'bp_first'


def test_scan_cursor_survives_restart_and_rejects_stale_scanners():
    s = store()
    assert rows.scan_position(s) == (0, None)
    boundary = {'scan_at': 70.0, 'id': 'synthetic-boundary'}
    rows.advance_scan(s, 0, boundary)
    restarted = store()
    restarted.rows = deepcopy(s.rows)
    assert rows.scan_position(restarted) == (1, boundary)
    rows.advance_scan(restarted, 0, {'scan_at': 20.0, 'id': 'stale'})
    assert rows.scan_position(restarted) == (1, boundary)
    rows.advance_scan(restarted, 1, None)
    assert rows.scan_position(restarted) == (2, None)
    empty = MemoryStore()
    rows.advance_scan(empty, 0, None)
    assert empty.rows == {}


def test_off_restart_keeps_individual_mode_even_if_enabled_again():
    s = store()
    rows.enqueue(s, member('first'), 'key', 10)
    rows.enqueue(s, member('second', 120), 'key', 11)
    first = rows.claim(s, group(s)['id'], 12, producer_enabled=False)
    assert first['mode'] == 'individual'
    resumed = rows.claim(s, first['id'], first['lease_until'] + 1, producer_enabled=True)
    assert resumed['mode'] == 'individual'
    with pytest.raises(ValueError, match='lease lost'):
        s.run(lambda tx: rows.guard(tx, first, 13))


def test_off_after_merged_admission_never_splits_immutable_units():
    s = store()
    rows.enqueue(s, member('first'), 'key', 10)
    merged_id = 'bp_' + rows.digest([group(s)['id'], 'merged'])
    s.rows['intakes', merged_id] = {'owner_id': 'owner', 'segment_ids': ['persisted-unit']}
    claimed = rows.claim(s, group(s)['id'], 11, producer_enabled=False)
    assert claimed['mode'] == 'merged'


def test_crash_between_admission_and_fanout_replays_targets_once():
    s = store()
    rows.enqueue(s, member('first'), 'key', 10)
    rows.enqueue(s, member('second', 120), 'key', 11)
    claimed = rows.claim(s, group(s)['id'], 70, producer_enabled=True)
    s.rows['intakes', 'bp_merged'] = {'owner_id': 'owner', 'segment_ids': ['unit']}
    resumed = rows.claim(s, claimed['id'], 191, producer_enabled=True)
    from database.batch_pipeline_staging import artifact_id

    for m in resumed['members']:
        s.rows['artifacts', artifact_id(m['item']['segment_id'], m['uri'])] = {
            'uri': m['uri'],
            'segment_id': m['item']['segment_id'],
        }
    rows.finish(s, resumed, ['bp_merged', 'bp_merged'], 192)
    assert s.rows['coalesce_quota', 'global']['groups'] == 0
    assert 'scan_at' not in group(s)
    assert s.rows['intakes', 'bp_first']['coalesce_target'] == 'bp_merged'
    assert s.rows['intakes', 'bp_second']['coalesce_target'] == 'bp_merged'
    assert rows.claim(s, resumed['id'], 1000, producer_enabled=True) is None
    assert s.rows['coalesce_sources', 'hold-first']['uri'] == 'gs://synthetic/object#1'


def test_fanout_cannot_complete_from_missing_target_or_partial_set():
    s = store()
    rows.enqueue(s, member('first'), 'key', 10)
    claimed = rows.claim(s, group(s)['id'], 70, producer_enabled=True)
    with pytest.raises(ValueError, match='complete'):
        rows.finish(s, claimed, [], 71)
    with pytest.raises(ValueError, match='missing'):
        rows.finish(s, claimed, ['bp_missing'], 71)
    assert group(s)['state'] == 'sealed'
    assert s.rows['coalesce_quota', 'global']['groups'] == 1


def test_revocation_blocks_join_seal_and_fanout(monkeypatch):
    s = store()
    rows.enqueue(s, member('first'), 'key', 10)

    def denied(*args, **kwargs):
        from database.batch_pipeline_privacy import BatchPrivacyBlocked

        raise BatchPrivacyBlocked('synthetic_revocation')

    monkeypatch.setattr(MemoryTransaction, 'check_privacy', denied)
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    with pytest.raises(BatchPrivacyBlocked):
        rows.enqueue(s, member('second', 120), 'key', 11)
    with pytest.raises(BatchPrivacyBlocked):
        rows.claim(s, group(s)['id'], 70, producer_enabled=True)
    assert ('content', 'owner/second') not in s.rows


def test_precise_open_is_idempotent_owner_scoped_and_does_not_promote_priority():
    s = store()
    rows.enqueue(s, member('first'), 'key', 10)
    assert rows.release_for_open(s, 'foreign', 'bp_first', 12) is False
    assert group(s)['release_by'] == 70
    assert rows.release_for_open(s, 'owner', 'bp_first', 12)
    assert rows.release_for_open(s, 'owner', 'bp_first', 13)
    assert group(s)['release_by'] == 12
    assert group(s)['members'][0]['lane'] == 'fresh'
    assert 'priority' not in group(s)


def test_member_receipt_waits_for_all_group_persistence():
    s = store()
    m = member('first')
    m.update(coalesce_group='group', coalesce_target='bp_merged')
    s.rows['intakes', m['job_id']] = deepcopy(m)
    s.rows['content', 'owner/first'] = {'job_id': m['job_id'], 'status': 'processing'}
    status = {
        'job_id': 'bp_merged',
        'status': 'processing',
        'total_files': 2,
        'total_segments': 2,
        'processed_segments': 1,
        'failed_segments': 1,
        'result': {'held_segments': 1},
    }
    assert member_status(s, 'owner', m, lambda *a: status)['result'] is None
    assert member_status(s, 'owner', m, lambda *a: status)['processed_segments'] == 0
    status.update(
        status='completed',
        failed_segments=0,
        result={
            'total_segments': 2,
            'failed_segments': 0,
            'new_memories': ['recording'],
            'updated_memories': [],
            'errors': [],
        },
    )
    mapped = member_status(s, 'owner', m, lambda *a: status)
    assert mapped['job_id'] == 'bp_first'
    assert mapped['total_segments'] == mapped['processed_segments'] == 1
    assert mapped['result']['total_segments'] == 1
    assert 'expires_at' in s.rows['intakes', m['job_id']]
    assert s.rows['content', 'owner/first']['status'] == 'completed'


@pytest.mark.parametrize('gap', [1, 11])
def test_raw_custody_roundtrip_uses_existing_decoder_and_preserves_original_bytes(tmp_path, gap):
    paths = []
    original = []
    for index in range(2):
        path = tmp_path / f'audio_synthetic_pcm16_16000_1_fs160_{1700000000 + index * gap}.bin'
        frame = struct.pack('<h', 1000 + index) * 160
        data = (struct.pack('<I', len(frame)) + frame) * 100
        path.write_bytes(data)
        paths.append(str(path))
        original.append(data)
    packed = _pack(paths, {'uid': 'synthetic'})
    assert packed is not None
    body, size, start, end, seconds, count, names, source_frames = packed
    assert seconds == 1 + gap and count == 1
    assert source_frames == 32000
    assert [__import__('pathlib').Path(path).read_bytes() for path in paths] == original
    destination = tmp_path / 'recovered'
    destination.mkdir()
    arguments, recovered = _unpack(body, destination)
    assert arguments == {'uid': 'synthetic'}
    assert [__import__('pathlib').Path(path).read_bytes() for path in recovered] == original
    package = json.loads(body)
    package['files'][0]['name'] = '../escape.bin'
    with pytest.raises(ValueError, match='path'):
        _unpack(json.dumps(package).encode(), destination)
