"""Reversible hide for empty rollover stubs: shape, lease fence and plan allowlist.

The 2026-11-16 listen rollover storm left in-progress batch_live_v1 rows that
received a first frame but never committed audio. They are hidden through the
existing reversible no-speech terminal only when both retained-object listings
are empty, the row has exactly that empty shape, and no recording session still
holds its lease. No row or audio object is deleted; the operator undo restores it.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from tests.unit import test_no_speech_terminal as storage_tests
from utils.batch_pipeline import no_speech

UID, CID = storage_tests.UID, storage_tests.CID
ROW_PATH = storage_tests.ROW_PATH
NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


def stub(**changes):
    row = {
        'record_lane_owner': 'batch_live_v1',
        'server_batch_only': True,
        'status': 'in_progress',
        'created_at': NOW - timedelta(hours=10),
        'private_cloud_sync_enabled': True,
        'server_batch_audio_received': True,
        'audio_files': [],
        'transcript_segments': [],
    }
    row.update(changes)
    return row


def test_storm_stub_shape_is_recognized():
    assert no_speech.empty_stub_shape(stub())


@pytest.mark.parametrize(
    'changes',
    [
        {'server_batch_audio_received': False},
        {'server_batch_audio_received': None},
        {'server_batch_audio_closed': True},
        {'record_audio_closed': True},
        {'server_batch_audio_start': 1.0},
        {'server_batch_audio_end': 2.0},
        {'has_content': True},
        {'audio_files': [{'duration': 1.0}]},
        {'transcript_segments': [{'text': 'x'}]},
        {'photos': [{'id': 'p'}]},
        {'record_sealed_at': NOW},
        {'record_wal_handoff_present': True},
        {'listen_batch_producer': {'version': 1, 'token': 't', 'phase': 'active'}},
    ],
)
def test_any_sign_of_audio_custody_or_a_live_producer_is_not_a_stub(changes):
    assert not no_speech.empty_stub_shape(stub(**changes))


def test_measure_row_classifies_an_empty_stub_only_with_both_listings_empty(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [])
    monkeypatch.setattr(no_speech, '_legacy_chunks', lambda *a, **k: [])
    assert no_speech._measure_row(object(), UID, CID, stub()) == ('empty_stub', None, None, 0, 0)
    # Not the stub shape: the original refusal is unchanged.
    assert no_speech._measure_row(object(), UID, CID, stub(has_content=True))[0] == 'coverage_incomplete'
    monkeypatch.setattr(no_speech, '_legacy_chunks', lambda *a, **k: [{'path': 'chunks/x'}])
    assert no_speech._measure_row(object(), UID, CID, stub())[0] == 'retained_audio_unmeasured'


def test_a_retained_raw_object_routes_to_measurement_not_the_stub_class(monkeypatch):
    monkeypatch.setattr(no_speech, '_raw_refs', lambda *a, **k: [{'path': 'raw-live/x'}])
    monkeypatch.setattr(no_speech, '_measure', lambda *a, **k: (0.0, 1.0))
    assert no_speech._measure_row(object(), UID, CID, stub())[0] == 'no_speech'


class FakeStore:
    namespace = 'batch_pipeline_test_nospeech'

    def __init__(self):
        self.client = Mock()

    def run(self, body):
        return body(Mock())


def plan(monkeypatch, rows, *, lease=None, actionable=None):
    """rows: list of (row, disposition) planned for distinct synthetic paths."""
    paths = [f'users/{UID}/conversations/c{i}' for i in range(len(rows))]
    by_path = dict(zip(paths, rows))
    monkeypatch.setattr(no_speech, 'privacy_read', lambda *a, **k: 7)
    monkeypatch.setattr(
        no_speech, '_snapshot', lambda store, uid, cid: (by_path[f'users/{uid}/conversations/{cid}'][0], 'rev-1')
    )
    monkeypatch.setattr(no_speech, '_job_exists', lambda *a, **k: False)
    monkeypatch.setattr(
        no_speech,
        '_measure_row',
        lambda storage, uid, cid, row: (
            by_path[f'users/{uid}/conversations/{cid}'][1],
            0.0 if by_path[f'users/{uid}/conversations/{cid}'][1] == 'no_speech' else None,
            1.0 if by_path[f'users/{uid}/conversations/{cid}'][1] == 'no_speech' else None,
            0,
            0,
        ),
    )
    monkeypatch.setattr(no_speech.jobs_db, 'recording_session_lease_expiry', lambda *a, **k: lease)
    return no_speech.plan_no_speech(FakeStore(), paths, object(), run_id='run-1', now=NOW, actionable=actionable)


def test_a_live_recording_session_lease_refuses_the_stub(monkeypatch):
    planned = plan(monkeypatch, [(stub(), 'empty_stub')], lease=NOW + timedelta(minutes=3))
    entry = planned['entries'][0]
    assert entry['disposition'] == 'lease_active'
    assert 'row_sha256' not in entry
    assert no_speech.summary(planned)['actionable'] == 0


@pytest.mark.parametrize('lease', [None, NOW - timedelta(hours=9)])
def test_expired_or_absent_lease_binds_the_stub_for_approval(monkeypatch, lease):
    planned = plan(monkeypatch, [(stub(), 'empty_stub')], lease=lease)
    entry = planned['entries'][0]
    assert entry['disposition'] == 'empty_stub'
    assert entry['exit'] == 'operator_undo_restores_original_fields'
    assert entry['row_sha256'] and entry['revision'] == 'rev-1'


def test_restricted_plan_binds_only_its_allowlist_and_the_digest(monkeypatch):
    rows = [(stub(), 'empty_stub'), (storage_tests.original_row(), 'no_speech')]
    restricted = plan(monkeypatch, rows, actionable=('empty_stub',))
    assert restricted['actionable'] == ['empty_stub']
    stub_entry, speech_entry = restricted['entries']
    assert 'row_sha256' in stub_entry and 'row_sha256' not in speech_entry
    report = no_speech.summary(restricted)
    assert report['actionable'] == 1 and report['skipped'] == 1
    unrestricted = plan(monkeypatch, rows)
    assert 'actionable' not in unrestricted
    assert unrestricted['plan_sha256'] != restricted['plan_sha256']


def test_unknown_allowlist_is_refused(monkeypatch):
    with pytest.raises(ValueError):
        plan(monkeypatch, [(stub(), 'empty_stub')], actionable=('delete',))


def test_apply_hides_only_allowlisted_stubs_with_zero_speech_and_audio(monkeypatch):
    rows = [(stub(), 'empty_stub'), (storage_tests.original_row(), 'no_speech')]
    planned = plan(monkeypatch, rows, actionable=('empty_stub',))
    monkeypatch.setattr(no_speech, 'no_speech_terminal_enabled', lambda: True)
    monkeypatch.setattr(
        no_speech, '_reprove', lambda store, storage, entry, now: (UID, entry['path'].rsplit('/', 1)[1], None, None)
    )
    close = Mock(return_value='rev-2')
    monkeypatch.setattr(no_speech.lifecycle, 'close_no_speech_capture', close)
    ledger = Mock()
    outcomes = no_speech.apply_no_speech(FakeStore(), planned, planned['plan_sha256'], object(), ledger=ledger)
    assert outcomes == {'closed': 1, 'no_speech': 1}
    assert close.call_count == 1
    assert close.call_args.kwargs['speech_seconds'] == 0.0 and close.call_args.kwargs['audio_seconds'] == 0.0


def test_apply_reproof_refuses_a_stub_whose_lease_became_live(monkeypatch):
    planned = plan(monkeypatch, [(stub(), 'empty_stub')], lease=None, actionable=('empty_stub',))
    monkeypatch.setattr(no_speech, 'no_speech_terminal_enabled', lambda: True)
    monkeypatch.setattr(no_speech, 'row_state', lambda row: planned['entries'][0]['row_sha256'])
    monkeypatch.setattr(
        no_speech.jobs_db,
        'recording_session_lease_expiry',
        lambda *a, **k: datetime.now(timezone.utc) + timedelta(minutes=3),
    )
    monkeypatch.setattr(no_speech.lifecycle, 'close_no_speech_capture', Mock(side_effect=AssertionError('closed')))
    outcomes = no_speech.apply_no_speech(FakeStore(), planned, planned['plan_sha256'], object(), ledger=Mock())
    assert outcomes == {'lease_active': 1}
