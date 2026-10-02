"""Recovery preserves partition boundaries and retains permanently failing audio."""

from copy import deepcopy
from pathlib import Path

from google.api_core.exceptions import InvalidArgument
import pytest
import yaml

from config.sync_assignment_recovery import sync_assignment_recovery_enabled
from database import sync_ledger
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, conversations, intake
from utils.sync.assignment import capture_mismatch
from utils.sync.assignment_errors import SyncAssignmentConflict
from utils.sync.pipeline import _firestore_error_class


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


@pytest.mark.parametrize(
    'field,value,token',
    [
        ('source', 'desktop', 'source'),
        ('client_device_id', 'other-device', 'device'),
        ('client_device_id', None, 'device'),
        ('is_locked', True, 'lock'),
    ],
)
@pytest.mark.parametrize('compatible_neighbor', [False, True])
def test_mismatch_recovers_without_touching_target_and_retry_dedupes(
    monkeypatch,
    caplog,
    field,
    value,
    token,
    compatible_neighbor,
):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', 'true')
    store = StrictFirestore()
    target = chunk('private-target', 1000)
    target[field] = value
    store.rows[('users', 'u', 'conversations', target['id'])] = deepcopy(target)
    if compatible_neighbor:
        intake(store, chunk('neighbor', 960))
    incoming = chunk('wal', 1010)
    result, created, survivors = intake(store, incoming, target_id=target['id'], candidate_id=target['id'])
    assert result['id'] == ('neighbor' if compatible_neighbor else 'wal')
    assert created is not compatible_neighbor
    assert len(survivors) == 1
    assert store.rows[('users', 'u', 'conversations', target['id'])] == target
    repeated, created, survivors = intake(store, incoming, target_id=target['id'])
    assert repeated['id'] == result['id'] and not created and not survivors
    assert len(conversations(store)) == 2
    event = next(r.message for r in caplog.records if 'event=sync_assignment_target' in r.message)
    assert f'mismatch={token}' in event and 'outcome=temporal_recovery' in event
    assert target['id'] not in event and 'other-device' not in event


def test_locked_to_locked_target_never_appends(monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', 'true')
    store = StrictFirestore()
    target = dict(chunk('locked', 1000), is_locked=True, sync_content_revision=1)
    store.rows[('users', 'u', 'conversations', 'locked')] = deepcopy(target)
    incoming = dict(chunk('wal', 1060), is_locked=True)
    result, created, _ = intake(store, incoming, target_id='locked')
    assert created and result['id'] == 'wal' and result['is_locked']
    assert store.rows[('users', 'u', 'conversations', 'locked')] == target


@pytest.mark.parametrize('field,value', [('is_locked', True), ('source', 'desktop'), ('client_device_id', 'changed')])
def test_changed_retry_anchor_is_not_overwritten_or_silently_consumed(field, value):
    store = StrictFirestore()
    incoming = chunk('wal', 1000)
    intake(store, incoming)
    store.rows[('users', 'u', 'conversations', 'wal')][field] = value
    before = deepcopy(store.rows)
    with pytest.raises(SyncAssignmentConflict) as exc:
        intake(store, incoming, target_id='missing')
    assert exc.value.subtype == 'provenance_mismatch'
    assert store.rows == before


def test_missing_target_keeps_temporal_behavior_with_switch_off(monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', 'off')
    store = StrictFirestore()
    intake(store, chunk('neighbor', 1000))
    result, created, _ = intake(store, chunk('wal', 1060), target_id='missing')
    assert not created and result['id'] == 'neighbor'


def test_combined_mismatch_token_is_bounded():
    assert (
        capture_mismatch({'source': 'secret', 'client_device_id': 'private', 'is_locked': True}, {})
        == 'source_device_lock'
    )
    assert capture_mismatch({}, {}) == 'none'


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


@pytest.mark.parametrize('stale', [False, True])
def test_segment_quarantine_is_owner_fenced_and_survives_rebatch(stale, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    store = StrictFirestore()
    owner = ('users', 'u', 'sync_content_ledger', 'batch-a')
    store.rows[owner] = {'status': 'processing', 'job_id': 'job', 'ledger_run_token': 'token', 'ledger_run_epoch': 2}
    assert sync_ledger.get_sync_segment_quarantine('u', 'segment', firestore_client=store) is None
    stored = sync_ledger.quarantine_sync_segment(
        'u',
        'batch-a',
        'segment',
        'job',
        'persistence:document_size_limit',
        run_token='stale' if stale else 'token',
        run_epoch=2,
        firestore_client=store,
    )
    assert stored is not stale
    fingerprint = sync_ledger.get_sync_segment_quarantine('u', 'segment', firestore_client=store)
    assert fingerprint == (None if stale else 'persistence:document_size_limit')
    assert store.rows[owner]['status'] == 'processing'
    if not stale:
        guard = store.rows[('users', 'u', 'sync_content_ledger', 'quarantine-segment')]
        assert 'expires_at' not in guard and 'transcript_segments' not in guard
        # The lookup has no batch argument, so a different batch cannot re-arm STT.
        assert sync_ledger.get_sync_segment_quarantine('u', 'segment', firestore_client=store) == fingerprint
    with pytest.raises(ValueError, match='unclassified'):
        sync_ledger.quarantine_sync_segment('u', 'batch-a', 'segment', 'job', 'private', firestore_client=store)


def test_recovery_flag_reaches_every_sync_host_in_both_environments():
    manifest = yaml.safe_load((Path(__file__).parents[2] / 'deploy/runtime_env.yaml').read_text())
    for env in manifest['environments'].values():
        hosts = [
            env['cloud_run']['services'][service]
            for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
        ]
        hosts.append(env['gke']['backend-listen'])
        assert all(host['env']['SYNC_ASSIGNMENT_RECOVERY_ENABLED']['value'] == 'true' for host in hosts)
