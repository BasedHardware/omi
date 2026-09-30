"""Staged rollout of sync lineage binding: ``SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST``.

Every sync-side behavior the kill switch turns on is gated by uid, and a uid
outside a non-empty allowlist must be indistinguishable from the kill switch
being off at each site: the per-segment binding request, the pinned live
origin on a sync append, the live revision fence, and the open-live enrichment
deferral. Each site test compares the non-admitted outcome against the OFF
outcome itself, not merely against "not the new behavior". All ids are
synthetic; ``u`` and ``uid`` are the owners the shared harnesses write under.
"""

import logging
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

import tests.unit.test_listen_reconnect_continuity as continuity
from config import sync_lineage
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import intake
from tests.unit.test_sync_recording_lineage import (  # noqa: F401 - fixtures
    L,
    ORIGIN,
    _drive,
    at,
    coordinator,
    dependencies,
    gen_id,
    gen_start,
    generation,
    seeded_store,
    sync_chunk,
    upload_straddling_next_two,
)
from utils.sync import recording_lineage
from utils.sync.recording_lineage import OUTCOMES, lineage_resolution_requested

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# (kill switch value, allowlist template); ``{uid}`` is the owner under test.
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


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, raising=False)
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, raising=False)


# --- Parsing ------------------------------------------------------------------


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


# --- Site 1: per-segment binding request (backend-sync, backend REST) ------------


def _decision(monkeypatch, caplog, config, uid='u'):
    configure(monkeypatch, config, 'u')
    metrics = MagicMock()
    monkeypatch.setattr(recording_lineage, 'OMI_SYNC_LINEAGE_RESOLVE_TOTAL', metrics)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        requested = lineage_resolution_requested(uid, ORIGIN, 1.0, 2.0, job_id='00000000-0000-4000-8000-000000000000')
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()]
    outcomes = [call.kwargs['outcome'] for call in metrics.labels.call_args_list]
    return requested, outcomes, lines


def test_not_allowlisted_upload_records_a_bounded_id_free_decision(monkeypatch, caplog):
    requested, outcomes, lines = _decision(monkeypatch, caplog, ('', 'OTHER-A,OTHER-B'))
    assert not requested
    assert outcomes == ['not_allowlisted'] and 'not_allowlisted' in OUTCOMES
    assert len(lines) == 1 and 'outcome=not_allowlisted' in lines[0]
    assert 'job_ref=none' in lines[0]
    for forbidden in (ORIGIN, 'OTHER-', '00000000', ' u '):
        assert forbidden not in lines[0]


@pytest.mark.parametrize(
    ('config', 'outcome'), [(OFF, 'disabled'), (('off', 'u'), 'disabled'), (('x', 'u'), 'disabled')]
)
def test_kill_switch_records_disabled_even_for_an_allowlisted_uid(monkeypatch, caplog, config, outcome):
    requested, outcomes, lines = _decision(monkeypatch, caplog, config)
    assert not requested and outcomes == [outcome]
    assert len(lines) == 1


@pytest.mark.parametrize('name', sorted(ACTIVE))
def test_admitted_upload_binds_per_segment_without_a_gate_decision(monkeypatch, caplog, name):
    requested, outcomes, lines = _decision(monkeypatch, caplog, ACTIVE[name])
    assert requested and outcomes == [] and lines == []


def test_ineligible_upload_is_untouched_by_the_gate(monkeypatch, caplog):
    for config in (OFF, ('', 'OTHER-A')):
        configure(monkeypatch, config, 'u')
        assert not lineage_resolution_requested('u', None, 1.0, 2.0)
        assert not lineage_resolution_requested('u', ORIGIN, None, 2.0)


def test_metric_help_names_every_bounded_outcome():
    from utils.metrics import OMI_SYNC_LINEAGE_RESOLVE_TOTAL

    documented = OMI_SYNC_LINEAGE_RESOLVE_TOTAL._documentation.split('closed set: ')[1].split('|')
    assert tuple(documented) == OUTCOMES


async def _coordinate(module, stubs, monkeypatch, config, *, processed=(), partial=None):
    """One coordinator attempt for harness owner ``uid``; returns (targets, enrichment intents)."""
    configure(monkeypatch, config, 'uid')
    chunks = upload_straddling_next_two()
    captured, kwargs = _drive(module, stubs, chunks, monkeypatch, stamp=gen_id(L))
    pipeline = stubs['pipeline']
    pipeline.get_sync_job = MagicMock(return_value={'partial_result': partial or {}})
    by_id = {chunk['id']: f"/tmp/job-lineage/seg_{chunk['started_at'].timestamp():.0f}.wav" for chunk in chunks}
    pipeline.get_processed_segments = MagicMock(return_value={by_id[cid] for cid in processed})
    enriched = []
    pipeline._reprocess_merged_conversations = lambda _uid, response, *_a, **_k: enriched.append(
        dict(response.pop('_merged', {}))
    )
    await module._run_full_pipeline_background_async(
        'job-lineage', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-lineage', task_mode=True, **vars(kwargs)
    )
    return [captured.get(chunk['id'], 'SKIPPED') for chunk in chunks], enriched


@pytest.mark.asyncio
@pytest.mark.parametrize('name', sorted(INACTIVE))
async def test_coordinator_for_a_refused_uid_is_the_kill_switch_outcome(coordinator, monkeypatch, name):
    module, stubs = coordinator
    off = await _coordinate(module, stubs, monkeypatch, OFF)
    assert off == ([None] * 4, [{}])  # whole-batch resolver: stamp dropped, no lineage retry intent
    assert await _coordinate(module, stubs, monkeypatch, INACTIVE[name]) == off


@pytest.mark.asyncio
@pytest.mark.parametrize('name', sorted(ACTIVE))
async def test_coordinator_replay_binds_generations_for_an_admitted_uid(coordinator, monkeypatch, name):
    module, stubs = coordinator
    targets, _ = await _coordinate(module, stubs, monkeypatch, ACTIVE[name])
    assert targets == [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2
    # A retry under the same configuration plans the same rows.
    assert (await _coordinate(module, stubs, monkeypatch, ACTIVE[name]))[0] == targets


@pytest.mark.asyncio
async def test_allowlist_change_between_attempts_reroutes_only_unlanded_segments_to_the_new_config(
    coordinator, monkeypatch
):
    """Decision: the gate is evaluated per attempt, like the kill switch.

    Landed segments are skipped by the processed-segment ledger and never
    re-bound; the rest go exactly where a pure run under the new configuration
    sends them. The lineage retry-intent marker follows the attempt too.
    """
    module, stubs = coordinator
    chunks = upload_straddling_next_two()
    landed = [chunk['id'] for chunk in chunks[:2]]
    partial = {'updated_memories': [gen_id(L + 1)]}
    admitted, refused = ('', '{uid}'), ('', 'OTHER-A')
    pure_off, _ = await _coordinate(module, stubs, monkeypatch, OFF)
    pure_on, _ = await _coordinate(module, stubs, monkeypatch, admitted)
    narrowed, narrowed_intent = await _coordinate(
        module, stubs, monkeypatch, refused, processed=landed, partial=partial
    )
    assert narrowed == ['SKIPPED'] * 2 + pure_off[2:]
    assert narrowed_intent == [{}]
    widened, widened_intent = await _coordinate(module, stubs, monkeypatch, admitted, processed=landed, partial=partial)
    assert widened == ['SKIPPED'] * 2 + pure_on[2:]
    assert widened_intent == [{gen_id(L + 1): stubs['pipeline']._LINEAGE_RETRY_LANGUAGE}]


# --- Site 2: pinned live origin on a sync append (assign_in_transaction) -------


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
def test_refused_owner_appends_exactly_as_the_kill_switch(monkeypatch, name):
    off = _pinned_append(monkeypatch, OFF)
    assert off[0][0]['started_at'] == at(gen_start(L) - 1)  # OFF rebases on the early WAL
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


# --- Site 3: live revision fence (backend-listen update_conversation_segments) -


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
def test_refused_owner_live_write_is_the_kill_switch_write(monkeypatch, name):
    off = _live_write(monkeypatch, OFF)
    assert off['sync_content_revision'] == 1
    assert _live_write(monkeypatch, INACTIVE[name]) == off


# --- Site 4: open-live enrichment deferral (_reprocess_conversation_after_update)


def _reprocess(pipeline, monkeypatch, config):
    configure(monkeypatch, config, 'u')
    row = generation(
        L,
        status='in_progress',
        sync_live_target=True,
        sync_content_revision=1,
        created_at=at(gen_start(L)),
        structured={'title': 'Synthetic review'},
    )
    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_args: deepcopy(row))
    process = MagicMock()
    monkeypatch.setattr(pipeline, 'process_conversation', process)
    pipeline._reprocess_conversation_after_update('u', row['id'], 'en')
    return process.call_args_list


@pytest.mark.parametrize('name', sorted(ACTIVE))
def test_admitted_owner_defers_enrichment_of_an_open_live_row(dependencies, monkeypatch, name):
    assert _reprocess(dependencies, monkeypatch, ACTIVE[name]) == []


@pytest.mark.parametrize('name', sorted(INACTIVE))
def test_refused_owner_reprocesses_exactly_as_the_kill_switch(dependencies, monkeypatch, name):
    off = _reprocess(dependencies, monkeypatch, OFF)
    assert len(off) == 1
    assert _reprocess(dependencies, monkeypatch, INACTIVE[name]) == off


# --- Metadata-only origin stamp stays on the kill switch alone -----------------


@pytest.mark.asyncio
@pytest.mark.parametrize(('config', 'stamped'), [(('', 'OTHER-A'), True), (('off', '{uid}'), False)])
async def test_live_origin_stamp_ignores_the_allowlist(monkeypatch, config, stamped):
    configure(monkeypatch, config, 'original')
    harness = continuity.CaptureHarness(monkeypatch)
    first = harness.connect(client_id='fresh')
    await first.prepare()
    origin = harness.rows['fresh']['external_data'].get('recording_origin_id')
    assert origin == ('fresh' if stamped else None)


# --- Deployment wiring ------------------------------------------------------------

# Every service that runs a gated site. A service without the variable admits
# everyone, so the staged value must be identical on all of them.
GATED_SERVICES = (
    ('cloud_run', 'backend'),  # inline BYOK sync (routers/sync.py)
    ('cloud_run', 'backend-sync'),
    ('cloud_run', 'backend-sync-backfill'),
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


def test_prod_stages_one_identical_allowlist_on_every_gated_service_and_dev_admits_everyone(runtime_env_manifest):
    prod, dev = runtime_env_manifest['environments']['prod'], runtime_env_manifest['environments']['dev']
    values = {_declared(prod, kind, service) for kind, service in GATED_SERVICES}
    assert len(values) == 1 and all(values), values
    assert all(uid.strip() for uid in next(iter(values)).split(','))
    assert all(_declared(dev, kind, service) in (None, '') for kind, service in GATED_SERVICES)
