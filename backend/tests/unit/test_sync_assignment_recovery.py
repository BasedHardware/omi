"""Incompatible explicit targets recover temporally; equal partitions behave as before.

Partition compatibility is equality of source, device and lock state. Two locked
captures are compatible, so locked chunks merge and retry exactly like unlocked
ones; only a genuine difference is a mismatch.
"""

from copy import deepcopy
from pathlib import Path
import json
import sys
from unittest.mock import MagicMock

from starlette.datastructures import UploadFile

from google.api_core.exceptions import InvalidArgument
import pytest
import yaml

from config.sync_assignment_recovery import sync_assignment_recovery_enabled
from database import sync_ledger
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cloud_tasks import _load_sync_router_for_fast_path
from tests.unit.test_sync_cross_job_assignment import chunk, conversations, intake
from utils.sync.assignment import auto_mergeable, capture_mismatch, compatible_capture
from utils.sync.assignment_errors import SyncAssignmentConflict
from utils.sync.pipeline import _firestore_error_class

_ALL_TOKENS = {
    'none',
    'source',
    'device',
    'lock',
    'source_device',
    'source_lock',
    'device_lock',
    'source_device_lock',
}

# (fields changed on the stored explicit target, incoming is_locked, bounded token)
_TARGET_MISMATCHES = [
    ({'source': 'desktop'}, False, 'source'),
    ({'client_device_id': 'other-device'}, False, 'device'),
    ({'client_device_id': None}, False, 'device'),
    ({'is_locked': True}, False, 'lock'),
    ({}, True, 'lock'),
    ({'source': 'desktop', 'is_locked': True}, False, 'source_lock'),
]


def _row(store, cid):
    return store.rows[('users', 'u', 'conversations', cid)]


def _spoken(row):
    return [(segment['start'], segment['end'], segment['text']) for segment in row['transcript_segments']]


def _assignment_events(caplog):
    return [r.message for r in caplog.records if 'event=sync_assignment_target' in r.message]


@pytest.mark.parametrize(
    'value,expected',
    [
        (None, True),
        ('true', True),
        ('ON', True),
        ('1', True),
        ('off', False),
        ('false', False),
        ('', False),
        ('typo', False),
    ],
)
def test_recovery_switch(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', raising=False)
    else:
        monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', value)
    assert sync_assignment_recovery_enabled() is expected


def test_mismatch_token_is_bounded_and_agrees_with_compatible_capture():
    seen = set()
    states = [
        {'source': source, 'client_device_id': device, 'is_locked': locked}
        for source in ('omi', 'desktop')
        for device in ('pendant', None)
        for locked in (False, True, None)
    ]
    for left in states:
        for right in states:
            token = capture_mismatch(left, right)
            seen.add(token)
            assert (token == 'none') is compatible_capture(left, right)
            assert capture_mismatch(right, left) == token
    assert seen == _ALL_TOKENS
    # Lock is reported only when the lock state differs, never for locked == locked.
    assert capture_mismatch({'is_locked': True}, {'is_locked': True}) == 'none'
    assert capture_mismatch({'is_locked': None}, {'is_locked': False}) == 'none'
    # Values never leak into the token.
    assert (
        capture_mismatch({'source': 'secret', 'client_device_id': 'private', 'is_locked': True}, {})
        == 'source_device_lock'
    )


def test_locked_sync_row_remains_auto_mergeable():
    assert auto_mergeable({'sync_content_revision': 1, 'is_locked': True})
    assert not auto_mergeable({'sync_content_revision': 1, 'is_locked': True, 'user_title': 'Mine'})


@pytest.mark.parametrize('flag', ['true', 'off'])
@pytest.mark.parametrize('reverse', [False, True])
def test_two_adjacent_locked_chunks_become_one_conversation(monkeypatch, caplog, flag, reverse):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', flag)
    store = StrictFirestore()
    chunks = [dict(chunk('a', 1000), is_locked=True), dict(chunk('b', 1060), is_locked=True)]
    for item in reversed(chunks) if reverse else chunks:
        result, _, _ = intake(store, item)
    rows = conversations(store)
    assert len(rows) == 1
    assert rows[0]['is_locked'] is True and len(rows[0]['transcript_segments']) == 2
    assert result['id'] == rows[0]['id']
    assert not _assignment_events(caplog)


@pytest.mark.parametrize('flag', ['true', 'off'])
@pytest.mark.parametrize('revision', [None, 1])
def test_locked_chunk_appends_to_locked_explicit_target(monkeypatch, caplog, flag, revision):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', flag)
    store = StrictFirestore()
    target = dict(chunk('locked', 1000, text='The first locked part of the talk.'), is_locked=True)
    if revision:
        target['sync_content_revision'] = revision
    store.rows[('users', 'u', 'conversations', 'locked')] = deepcopy(target)
    incoming = dict(chunk('wal', 1060, text='The second locked part of the talk.'), is_locked=True)
    result, created, survivors = intake(store, incoming, target_id='locked')
    assert result['id'] == 'locked' and not created and len(survivors) == 1
    stored = _row(store, 'locked')
    assert stored['is_locked'] is True
    assert [s['text'] for s in stored['transcript_segments']] == [
        'The first locked part of the talk.',
        'The second locked part of the talk.',
    ]
    assert ('users', 'u', 'conversations', 'wal') not in store.rows
    assert not _assignment_events(caplog)


@pytest.mark.parametrize('flag', ['true', 'off'])
@pytest.mark.parametrize('scenario', ['own_anchor', 'explicit_target', 'absorbed_by_neighbor'])
def test_identical_locked_retry_after_commit_before_checkpoint_deduplicates(monkeypatch, caplog, flag, scenario):
    """The assignment committed, the processed-segment checkpoint did not, and the
    same locked chunk is assigned again. It must deduplicate, not conflict."""
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', flag)
    store = StrictFirestore()
    incoming = dict(chunk('wal', 1060, text='A locked sentence that was already saved.'), is_locked=True)
    target_id = None
    if scenario == 'explicit_target':
        target_id = 'locked'
        store.rows[('users', 'u', 'conversations', 'locked')] = dict(
            chunk('locked', 1000, text='The first locked part of the talk.'), is_locked=True, sync_content_revision=1
        )
    elif scenario == 'absorbed_by_neighbor':
        intake(store, dict(chunk('neighbor', 1000, text='An earlier locked sentence.'), is_locked=True))
    first, _, survivors = intake(store, incoming, target_id=target_id)
    assert len(survivors) == 1
    committed = [_spoken(row) for row in conversations(store)]
    retried, created, survivors = intake(store, incoming, target_id=target_id)
    assert retried['id'] == first['id'] and not created and not survivors
    assert _spoken(retried) == _spoken(first)
    after = conversations(store)
    assert len(after) == 1 and [_spoken(row) for row in after] == committed
    assert after[0]['is_locked'] is True
    assert not _assignment_events(caplog)


@pytest.mark.parametrize('flag', ['true', 'off'])
@pytest.mark.parametrize(
    'incoming_locked,field,value,token',
    [
        (False, 'is_locked', True, 'lock'),
        (True, 'is_locked', False, 'lock'),
        (False, 'source', 'desktop', 'source'),
        (True, 'source', 'desktop', 'source'),
        (False, 'client_device_id', 'changed-device', 'device'),
    ],
)
def test_genuinely_changed_retry_anchor_is_fenced(monkeypatch, caplog, flag, incoming_locked, field, value, token):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', flag)
    store = StrictFirestore()
    incoming = dict(chunk('wal', 1000), is_locked=incoming_locked)
    intake(store, incoming)
    _row(store, 'wal')[field] = value
    before = deepcopy(store.rows)
    with pytest.raises(SyncAssignmentConflict) as exc:
        intake(store, incoming, target_id='missing')
    assert exc.value.subtype == 'provenance_mismatch'
    assert store.rows == before
    event = _assignment_events(caplog)[-1]
    assert 'outcome=anchor_rejected' in event and f'mismatch={token}' in event
    assert 'changed-device' not in event and 'desktop' not in event


@pytest.mark.parametrize('target_fields,incoming_locked,token', _TARGET_MISMATCHES)
@pytest.mark.parametrize('compatible_neighbor', [False, True])
def test_incompatible_target_recovers_temporally_and_leaves_the_target_untouched(
    monkeypatch,
    caplog,
    target_fields,
    incoming_locked,
    token,
    compatible_neighbor,
):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', 'true')
    store = StrictFirestore()
    target = dict(chunk('private-target', 1000), **target_fields)
    store.rows[('users', 'u', 'conversations', target['id'])] = deepcopy(target)
    if compatible_neighbor:
        intake(store, dict(chunk('neighbor', 960), is_locked=incoming_locked))
    incoming = dict(chunk('wal', 1010), is_locked=incoming_locked)
    result, created, survivors = intake(store, incoming, target_id=target['id'], candidate_id=target['id'])
    assert result['id'] == ('neighbor' if compatible_neighbor else 'wal')
    assert created is not compatible_neighbor
    assert len(survivors) == 1
    assert _row(store, target['id']) == target
    repeated, created, survivors = intake(store, incoming, target_id=target['id'])
    assert repeated['id'] == result['id'] and not created and not survivors
    assert _row(store, target['id']) == target
    assert len(conversations(store)) == 2
    event = _assignment_events(caplog)[0]
    assert f'mismatch={token} ' in f'{event} ' and 'outcome=temporal_recovery' in event
    assert target['id'] not in event and 'other-device' not in event and 'desktop' not in event


@pytest.mark.parametrize('target_fields,incoming_locked,token', _TARGET_MISMATCHES)
def test_switch_off_rejects_an_incompatible_target_as_before(
    monkeypatch, caplog, target_fields, incoming_locked, token
):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', 'false')
    store = StrictFirestore()
    target = dict(chunk('private-target', 1000), **target_fields)
    store.rows[('users', 'u', 'conversations', target['id'])] = deepcopy(target)
    intake(store, dict(chunk('neighbor', 960), is_locked=incoming_locked))
    before = deepcopy(store.rows)
    with pytest.raises(SyncAssignmentConflict) as exc:
        intake(store, dict(chunk('wal', 1010), is_locked=incoming_locked), target_id=target['id'])
    assert exc.value.subtype == 'provenance_mismatch'
    assert store.rows == before
    events = _assignment_events(caplog)
    assert len(events) == 1
    assert 'outcome=rejected' in events[0] and f'mismatch={token} ' in f'{events[0]} '


def test_missing_target_keeps_temporal_behavior_with_switch_off(monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', 'off')
    store = StrictFirestore()
    intake(store, chunk('neighbor', 1000))
    result, created, _ = intake(store, chunk('wal', 1060), target_id='missing')
    assert not created and result['id'] == 'neighbor'


@pytest.mark.parametrize(
    'message,expected',
    [
        ('Document secret exceeds the maximum allowed size', 'document_size_limit'),
        ('The transaction has expired private-path', 'expired_transaction'),
        ('unexpected confidential detail', 'invalid_argument_other'),
    ],
)
def test_firestore_diagnostics_are_bounded(message, expected):
    assert _firestore_error_class(InvalidArgument(message)) == expected
    assert _firestore_error_class(ValueError(message)) == 'none'


def test_ledger_has_no_permanent_segment_guard():
    """The bounded batch cap is the only pause; nothing reads a per-segment guard."""
    assert not hasattr(sync_ledger, 'get_sync_segment_quarantine')
    assert not hasattr(sync_ledger, 'quarantine_sync_segment')


def test_recovery_flag_reaches_every_sync_host_in_both_environments():
    manifest = yaml.load((Path(__file__).parents[2] / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    for env in manifest['environments'].values():
        hosts = [
            env['cloud_run']['services'][service]
            for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
        ]
        hosts.append(env['gke']['backend-listen'])
        assert all(host['env']['SYNC_ASSIGNMENT_RECOVERY_ENABLED']['value'] == 'true' for host in hosts)


@pytest.fixture
def admission_router():
    module, saved, jobs, bytes_io, _, _ = _load_sync_router_for_fast_path()
    try:
        yield module, jobs, bytes_io
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_paused_persistence_upload_keeps_the_retaining_contract_before_dispatch(admission_router, caplog):
    module, jobs, bytes_io = admission_router
    module.claim_sync_content = MagicMock(
        return_value={'outcome': 'capped', 'failure_key': 'persistent_persistence', 'retry_after': 3600}
    )
    module.start_background_task = MagicMock()
    response = await module.sync_local_files_v2(
        files=[UploadFile(filename='synthetic.opus', file=bytes_io(b'synthetic'))],
        uid='test-uid',
    )
    assert response.status_code == 202
    assert json.loads(response.body)['status'] == 'failed'
    module.mark_job_failed.assert_called_once()
    assert module.mark_job_failed.call_args.kwargs['reason_code'] == 'sync_repeat_failure_paused'
    module.enqueue_sync_job.assert_not_called()
    module.start_background_task.assert_not_called()
    jobs.mark_job_completed.assert_not_called()
    event = next(r.message for r in caplog.records if 'event=sync_repeat_failure_cap' in r.message)
    assert 'outcome=paused' in event and 'failure_key=persistent_persistence' in event
    assert 'quarantined' not in event and 'test-uid' not in event
