"""Retained shared and recovery-core cases after legacy coordinator retirement."""

import logging
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock
import pytest
import yaml
import tests.unit.test_listen_reconnect_continuity as continuity
from config import sync_lineage
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import intake
from tests.unit.test_sync_recording_lineage import (
    L,
    ORIGIN,
    at,
    dependencies,
    gen_id,
    gen_start,
    generation,
    seeded_store,
    sync_chunk,
)
from utils.sync import recording_lineage
from utils.sync.recording_lineage import OUTCOMES, lineage_resolution_requested

S1_CLAIMS = {
    'f.opus': {
        'capture_root': 'a1b2c3d4-1111-4222-8333-444455556666',
        'clock_epoch': 0,
        'source_frame_start': 0,
        'frame_count': 1,
        'rate_hz': 16000,
        'codec': 'opus',
        'channel': 'mono',
    }
}


OFF = ('off', '')


ACTIVE = {
    'unset_allowlist': ('', ''),
    'blank_allowlist': ('', ' , ,'),
    'allowlisted': ('', 'OTHER-A, {uid} ,OTHER-B'),
    'allowlisted_explicit_on': ('true', '{uid}'),
}


INACTIVE = {
    'kill_switch_off': OFF,
    'not_allowlisted': ('', 'OTHER-A,OTHER-B'),
    'prefix_is_not_membership': ('', '{uid}X'),
    'kill_switch_beats_allowlist': ('off', '{uid}'),
    'typo_kill_switch_beats_allowlist': ('of', '{uid}'),
}


def configure(monkeypatch, config, uid):
    flag, allowlist = config
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, allowlist.format(uid=uid))


def test_real_firestore_client_paths_fail_closed_without_io():
    import database._client
    import database.conversations
    import firebase_admin.firestore
    from google.cloud import firestore

    with pytest.raises(AssertionError):
        database._client.get_firestore_client()
    with pytest.raises(AssertionError):
        database.conversations.get_firestore_client()
    with pytest.raises(AssertionError):
        firestore.Client()
    with pytest.raises(AssertionError):
        firebase_admin.firestore.client()


@pytest.mark.parametrize('name', sorted(ACTIVE))
def test_active_configurations_admit_the_owner(monkeypatch, name):
    configure(monkeypatch, ACTIVE[name], 'u')
    assert sync_lineage.sync_lineage_resolve_active_for('u')


@pytest.mark.parametrize('name', sorted(INACTIVE))
def test_inactive_configurations_refuse_the_owner(monkeypatch, name):
    configure(monkeypatch, INACTIVE[name], 'u')
    assert not sync_lineage.sync_lineage_resolve_active_for('u')


def test_allowlist_is_trimmed_csv_membership(monkeypatch):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, '  A1 ,\tB2,,\n')
    admitted = sync_lineage.sync_lineage_resolve_uid_allowed
    assert admitted('A1') and admitted('B2')
    assert not any(admitted(uid) for uid in ('', ' A1', 'A', 'A1,B2', 'C3', None, 7))


def test_empty_allowlist_admits_everyone_and_the_kill_switch_still_wins(monkeypatch):
    for value in ('', ' ', ',', ' , '):
        monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, value)
        assert sync_lineage.sync_lineage_resolve_uid_allowed('ANY-UID')
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, 'false')
    assert not sync_lineage.sync_lineage_resolve_active_for('ANY-UID')


def _decision(monkeypatch, caplog, config, uid='u', s1=False):
    configure(monkeypatch, config, 'u')
    metrics = MagicMock()
    monkeypatch.setattr(recording_lineage, 'OMI_SYNC_LINEAGE_RESOLVE_TOTAL', metrics)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        requested = lineage_resolution_requested(
            uid,
            ORIGIN,
            1.0,
            2.0,
            job_id='00000000-0000-4000-8000-000000000000',
            capture_evidence_claims=deepcopy(S1_CLAIMS) if s1 else None,
            filenames=['f.opus'] if s1 else (),
        )
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()]
    outcomes = [call.kwargs['outcome'] for call in metrics.labels.call_args_list]
    return requested, outcomes, lines


@pytest.mark.parametrize('s1', [False, True])
def test_not_allowlisted_upload_records_a_bounded_id_free_decision(monkeypatch, caplog, s1):
    requested, outcomes, lines = _decision(monkeypatch, caplog, ('', 'OTHER-A,OTHER-B'), s1=s1)
    assert not requested
    assert outcomes == ['not_allowlisted'] and 'not_allowlisted' in OUTCOMES
    assert len(lines) == 1 and 'outcome=not_allowlisted' in lines[0]
    assert 'job_ref=none' in lines[0]
    for forbidden in (ORIGIN, 'OTHER-', '00000000', ' u '):
        assert forbidden not in lines[0]


@pytest.mark.parametrize(
    ('config', 'outcome'), [(OFF, 'disabled'), (('off', 'u'), 'disabled'), (('x', 'u'), 'disabled')]
)
@pytest.mark.parametrize('s1', [False, True])
def test_kill_switch_records_disabled_even_for_an_allowlisted_uid(monkeypatch, caplog, config, outcome, s1):
    requested, outcomes, lines = _decision(monkeypatch, caplog, config, s1=s1)
    assert not requested and outcomes == [outcome]
    assert len(lines) == 1


@pytest.mark.parametrize('name', sorted(ACTIVE))
@pytest.mark.parametrize('s1', [False, True])
def test_admitted_upload_binds_per_segment_without_a_gate_decision(monkeypatch, caplog, name, s1):
    requested, outcomes, lines = _decision(monkeypatch, caplog, ACTIVE[name], s1=s1)
    assert requested == s1
    assert outcomes == ([] if s1 else ['s1_refused'])
    assert len(lines) == (0 if s1 else 1)
    if not s1:
        assert 'outcome=s1_refused' in lines[0] and 'job_ref=none' in lines[0]


def test_ineligible_upload_is_untouched_by_the_gate(monkeypatch, caplog):
    metrics = MagicMock()
    monkeypatch.setattr(recording_lineage, 'OMI_SYNC_LINEAGE_RESOLVE_TOTAL', metrics)
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        for config in (OFF, ('', 'OTHER-A')):
            configure(monkeypatch, config, 'u')
            assert not lineage_resolution_requested('u', None, 1.0, 2.0)
            assert not lineage_resolution_requested('u', ORIGIN, None, 2.0)
    metrics.labels.assert_not_called()
    assert not any('event=sync_lineage_resolve' in r.getMessage() for r in caplog.records)


def test_metric_help_names_every_bounded_outcome():
    from utils.metrics import OMI_SYNC_LINEAGE_RESOLVE_TOTAL

    documented = OMI_SYNC_LINEAGE_RESOLVE_TOTAL._documentation.split('closed set: ')[1].split('|')
    assert tuple(documented) == OUTCOMES


def _pinned_append(monkeypatch, config, store=None):
    configure(monkeypatch, config, 'u')
    store = store or seeded_store([generation(L, audio_timeline={'version': 2})])
    origin = gen_start(L)
    chunk = sync_chunk(origin - 1, origin + 9, 'Synthetic buffered speech before live connected.')
    result, created, survivors = intake(store, chunk, target_id=gen_id(L))
    return (result, created, survivors), deepcopy(store.rows)


@pytest.mark.parametrize('name', sorted(ACTIVE))
def test_admitted_owner_keeps_the_pinned_live_origin(monkeypatch, name):
    (result, _, _), _ = _pinned_append(monkeypatch, ACTIVE[name])
    assert result['started_at'] == at(gen_start(L))
    early = next(s for s in result['transcript_segments'] if s['start'] < 0)
    assert early['audio_alignment'] == 'unplaced'


@pytest.mark.parametrize('name', sorted(INACTIVE))
def test_live_origin_pin_is_independent_of_lineage_rollout(monkeypatch, name):
    off = _pinned_append(monkeypatch, OFF)
    assert off[0][0]['started_at'] == at(gen_start(L))
    assert _pinned_append(monkeypatch, INACTIVE[name]) == off


def test_row_pinned_while_admitted_follows_the_new_config_without_moving_speech(monkeypatch):
    """A later append after narrowing is the OFF append on that row, and no line moves in absolute time."""
    _, touched = _pinned_append(monkeypatch, ACTIVE['allowlisted'])
    key = ('users', 'u', 'conversations', gen_id(L))

    def absolute(rows):
        row = rows[key]
        return sorted((row['started_at'].timestamp() + s['start'], s['text']) for s in row['transcript_segments'])

    before = absolute(touched)
    origin = gen_start(L)
    later = sync_chunk(origin - 4, origin - 3, 'Synthetic even earlier buffered speech.')
    outcomes = {}
    for name, config in (('narrowed', ('', 'OTHER-A')), ('off', OFF)):
        configure(monkeypatch, config, 'u')
        store = StrictFirestore(touched)
        outcomes[name] = (intake(store, deepcopy(later), target_id=gen_id(L)), deepcopy(store.rows))
    assert outcomes['narrowed'] == outcomes['off']
    after = absolute(outcomes['narrowed'][1])
    assert set(before) <= set(after) and (origin - 4, later['transcript_segments'][0]['text']) in after
    # A retry of the landed append under the narrowed config changes nothing.
    configure(monkeypatch, ('', 'OTHER-A'), 'u')
    store = StrictFirestore(outcomes['narrowed'][1])
    _, created, survivors = intake(store, deepcopy(later), target_id=gen_id(L))
    assert not created and not survivors
    assert absolute(store.rows) == after


def _live_write(monkeypatch, config):
    from database import conversations as db

    configure(monkeypatch, config, 'u')
    path = ('users', 'u', 'conversations', 'c')
    segment = dict(id='s0', speaker='SPEAKER_00', speaker_id=4, text='Synthetic speech', start=0, end=1, is_user=True)
    store = StrictFirestore(
        {
            path: dict(
                id='c',
                status='in_progress',
                transcript_segments=[segment],
                sync_live_target=True,
                sync_content_revision=1,
                data_protection_level='standard',
            )
        }
    )
    fresh = dict(segment, id='fresh', text='A distinct later synthetic sentence.', start=10, end=12)
    for _ in range(2):  # the second write is an unchanged retry
        db.update_conversation_segments('u', 'c', [], firestore_client=store, live_segments=[fresh])
    return store.rows[path]


@pytest.mark.parametrize('name', sorted(ACTIVE))
def test_admitted_owner_fences_older_processors_on_fresh_live_speech(monkeypatch, name):
    assert _live_write(monkeypatch, ACTIVE[name])['sync_content_revision'] == 2


@pytest.mark.parametrize('name', sorted(INACTIVE))
def test_live_target_fence_is_independent_of_lineage_rollout(monkeypatch, name):
    off = _live_write(monkeypatch, OFF)
    assert off['sync_content_revision'] == 2
    assert _live_write(monkeypatch, INACTIVE[name]) == off


def _reprocess(pipeline, monkeypatch, config, *, language='en', row_status='in_progress'):
    configure(monkeypatch, config, 'u')
    row = generation(
        L,
        status=row_status,
        sync_live_target=True,
        sync_content_revision=1,
        created_at=at(gen_start(L)),
        structured={'title': 'Synthetic review'},
    )
    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_args: deepcopy(row))
    process = MagicMock()
    monkeypatch.setattr(pipeline, 'process_conversation', process)
    pipeline._reprocess_conversation_after_update('u', row['id'], language)
    return process.call_args_list


@pytest.mark.parametrize('name', sorted(ACTIVE))
def test_admitted_owner_defers_enrichment_of_an_open_live_row(dependencies, monkeypatch, name):
    assert _reprocess(dependencies, monkeypatch, ACTIVE[name]) == []


@pytest.mark.parametrize('name', sorted(INACTIVE))
def test_refused_owner_reprocesses_exactly_as_the_kill_switch(dependencies, monkeypatch, name):
    off = _reprocess(dependencies, monkeypatch, OFF)
    assert off == []
    assert _reprocess(dependencies, monkeypatch, INACTIVE[name]) == off


@pytest.mark.parametrize('config', [('', 'OTHER-A'), OFF])
@pytest.mark.parametrize('status', ['completed', 'in_progress'])
def test_owed_refresh_finishes_completed_rows_but_never_closes_live_rows(dependencies, monkeypatch, config, status):
    calls = _reprocess(
        dependencies, monkeypatch, config, language=dependencies._LINEAGE_RETRY_LANGUAGE, row_status=status
    )
    assert len(calls) == (1 if status == 'completed' else 0)
    if calls:
        assert calls[0].kwargs['language_code'] == 'en'


def test_admitted_refresh_debt_survives_both_receipt_stores_and_excludes_fenced_rows():
    response = {
        'new_memories': {'NEW'},
        'updated_memories': {'LIVE', 'FENCED'},
        '_fenced_conversation_ids': {'FENCED'},
        '_merged': {'LIVE': 'en', 'NEW': 'en', 'FENCED': 'en'},
    }
    off = recording_lineage.lineage_partial_result(response, False)
    assert 'lineage_enrichment_pending' not in off
    admitted = recording_lineage.lineage_partial_result(response, True)
    assert admitted['lineage_enrichment_pending'] == ['LIVE']
    durable = recording_lineage.merge_lineage_partial_results(off, admitted)
    retry = dict(response, updated_memories={'LIVE'}, _merged={})
    recording_lineage.restore_lineage_enrichment_intent(retry, durable, False, 'stored-language')
    assert retry['_merged'] == {'LIVE': 'stored-language'}
    assert recording_lineage.lineage_partial_result(retry, False)['lineage_enrichment_pending'] == ['LIVE']
    retry['_fenced_conversation_ids'] = {'LIVE'}
    assert 'lineage_enrichment_pending' not in recording_lineage.lineage_partial_result(retry, False)


@pytest.mark.asyncio
@pytest.mark.parametrize(('config', 'stamped'), [(('', 'OTHER-A'), True), (('off', '{uid}'), False)])
async def test_live_origin_stamp_ignores_the_allowlist(monkeypatch, config, stamped):
    configure(monkeypatch, config, 'original')
    harness = continuity.CaptureHarness(monkeypatch)
    first = harness.connect(client_id='fresh')
    await first.prepare()
    origin = harness.rows['fresh']['external_data'].get('recording_origin_id')
    assert origin == ('fresh' if stamped else None)


GATED_SERVICES = (
    ('cloud_run', 'backend'),  # inline BYOK sync (routers/sync.py)
    ('cloud_run', 'backend-sync'),
    ('cloud_run', 'backend-sync-backfill'),
    ('cloud_run', 'backend-integration'),  # full main:app also mounts sync and listen
    ('gke', 'backend-listen'),  # live revision fence
)


def _declared(env_config, kind, service):
    services = env_config['cloud_run']['services'] if kind == 'cloud_run' else env_config['gke']
    entry = (services[service].get('env') or {}).get(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV)
    return None if entry is None else entry.get('value')


@pytest.fixture(scope='module')
def runtime_env_manifest():
    """The composed deploy manifest (large; parsed once, with the C loader when available)."""
    text = (Path(__file__).resolve().parents[2] / 'deploy' / 'runtime_env.yaml').read_text()
    return yaml.load(text, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))


def test_all_gated_services_resolve_private_cohorts_without_manifest_allowlists(runtime_env_manifest):
    prod, dev = runtime_env_manifest['environments']['prod'], runtime_env_manifest['environments']['dev']
    values = {_declared(prod, kind, service) for kind, service in GATED_SERVICES if kind == 'cloud_run'}
    assert values == {None}
    assert sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV not in str(prod['cloud_run'])
    assert _declared(prod, 'gke', 'backend-listen')
    assert all(_declared(dev, kind, service) in (None, '') for kind, service in GATED_SERVICES)
