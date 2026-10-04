"""Bounded diagnostics for lineage resolution: stage counts, id probe, span buckets.

The ``event=sync_lineage_resolve`` line reports how many returned candidate rows
each filter stage dropped (never ids, text or field values), and a no-rows
lookup may issue exactly one metadata-only document read on the recording id to
say why that row could not be a candidate — without ever promoting it to a
target. At assignment, a stamp-fallback live append reports only the bucketed
extent growth of the live row. All ids and text are synthetic.
"""

import logging
import sys
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import tests.unit.test_sync_v2 as sync_v2_harness
from config import sync_lineage
from config.sync_live_dedupe import SYNC_LINEAGE_LIVE_DEDUPE_ENV
from tests.unit.test_sync_cross_job_assignment import intake
from tests.unit.test_sync_lineage_dedupe_replay import (
    LIVE,
    LIVE_ID,
    NEW,
    T0 as DEDUPE_T0,
    _drive_process_segment,
    live_row,
    prove,
    reworded,
    seeded_store,
    seeded_store_with_donor,
    texts_of,
    wal,
)
from tests.unit.test_sync_recording_lineage import (
    DURATION,
    L,
    ORIGIN,
    at,
    gen_start,
    generation,
    live_text,
    spans,
    sync_chunk,
    upload_straddling_next_two,
)
from utils.firestore_document_size import estimate_firestore_document_bytes
from utils.sync import assignment, recording_lineage
from utils.sync.recording_lineage import resolve_segment_targets, select_segment_targets

SENTINEL_ID = 'SECRET-ROW-ID-9'
SENTINEL_TEXT = 'synthetic secret probe text never logged'


@pytest.fixture(autouse=True)
def default_flags(monkeypatch):
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, raising=False)
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, raising=False)


def rejected_row(mutation):
    row = generation(L)
    row['id'] = SENTINEL_ID
    row.update(mutation)
    return row


def test_every_provenance_rejection_counts_only_its_first_stage():
    rows = [
        generation(L, id=' '),
        generation(L, external_data={'recording_session_id': 'OTHER-REC'}),
        generation(L, deleted=True),
        generation(L, source='phone'),
        generation(L, client_device_id='other-phone'),
        generation(L, is_locked=True),
        generation(L, started_at=at(gen_start(L) + DURATION), finished_at=at(gen_start(L))),
        generation(L, external_data={'recording_session_id': ORIGIN}),
        generation(L),
    ]
    chunk = sync_chunk(gen_start(L) + 61, gen_start(L) + 69, live_text(L, 1))
    plan = select_segment_targets(
        rows,
        ORIGIN,
        spans([chunk]),
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    counts = plan.filter_counts
    assert counts['candidate_count_before'] == len(rows)
    assert counts['candidate_count_after'] == 2
    for key in (
        'dropped_invalid',
        'dropped_unstamped',
        'dropped_deleted',
        'dropped_source',
        'dropped_device',
        'dropped_lock',
        'dropped_interval',
    ):
        assert counts[key] == 1, key
    dropped = sum(counts[key] for key in counts if key.startswith('dropped_'))
    assert counts['candidate_count_after'] + dropped == counts['candidate_count_before']
    assert counts['unstamped_origin'] == 2
    assert plan.binding_reasons == {chunk['id']: 'bound'}


def test_multi_violation_rows_count_only_the_first_exclusion():
    rows = [
        generation(L, source='phone', is_locked=True),
        generation(L, deleted=True, source='phone'),
    ]
    plan = select_segment_targets(
        rows,
        ORIGIN,
        {'seg': (gen_start(L) + 1, gen_start(L) + 9)},
        stamped_target='STAMP',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert plan.filter_counts['dropped_source'] == 1
    assert plan.filter_counts['dropped_deleted'] == 1
    assert 'dropped_lock' not in plan.filter_counts


class _EmptyLineageDb:
    """A lineage module stand-in whose queries return no candidates."""

    def __init__(self, probe_row=None):
        self.probe_row = probe_row
        self.calls = []

    def get_recording_generations(self, *_args, **_kwargs):
        self.calls.append('generations')
        return []

    def get_origin_generation(self, *_args, **_kwargs):
        self.calls.append('origin')
        return []

    def get_recording_id_probe(self, uid, origin_id, *, firestore_client=None):
        self.calls.append('probe')
        return deepcopy(self.probe_row)


@pytest.fixture
def empty_lineage_db(monkeypatch):
    from database import sync_recording_lineage

    fake = _EmptyLineageDb()
    for name in ('get_recording_generations', 'get_origin_generation', 'get_recording_id_probe'):
        monkeypatch.setattr(sync_recording_lineage, name, getattr(fake, name))
    return fake


def resolve_no_rows(empty_db, *, stamp='STAMP', reasons=None, **kwargs):
    chunk = sync_chunk(gen_start(L) + 61, gen_start(L) + 69, SENTINEL_TEXT)
    return resolve_segment_targets(
        'u',
        ORIGIN,
        spans([chunk]),
        stamped_target=stamp,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        binding_reasons=reasons,
        **kwargs,
    )


def test_no_rows_resolve_emits_bounded_stage_counts(empty_lineage_db, caplog):
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        resolve_no_rows(empty_lineage_db)
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()]
    assert len(lines) == 1
    assert len(lines[0]) <= 768
    assert 'candidates=0' in lines[0] and 'accepted=0' in lines[0]
    assert 'id_probe=' in lines[0]
    for forbidden in (SENTINEL_ID, SENTINEL_TEXT, ORIGIN, 'u ', 'STAMP'):
        assert forbidden not in lines[0]


def test_stage_counts_are_capped_only_at_emission(caplog):
    rows = [
        generation(L, id=f'GEN-{i % 8}', ts=gen_start(L) + i, external_data={'recording_session_id': 'OTHER'})
        for i in range(40)
    ]
    plan = select_segment_targets(
        rows,
        ORIGIN,
        spans([sync_chunk(gen_start(L) + 1, gen_start(L) + 2, live_text(L, 0))]),
        stamped_target='STAMP',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert plan.filter_counts['candidate_count_before'] == 40
    assert plan.filter_counts['dropped_unstamped'] == 40
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        recording_lineage._emit(plan, 'SECRET-JOB')
    line = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()][0]
    assert 'candidates=16' in line and 'dropped_unstamped=16' in line
    assert SENTINEL_ID not in line and 'OTHER' not in line and 'SECRET-JOB' not in line


@pytest.mark.parametrize(
    ('mutation', 'expected'),
    [
        (None, 'missing'),
        ({'external_data': {}}, 'unstamped'),
        ({'source': 'phone'}, 'source'),
        ({'client_device_id': 'other-phone'}, 'device'),
        ({'is_locked': True}, 'lock'),
        ({'deleted': True}, 'deleted'),
        ({'started_at': at(gen_start(L) + DURATION), 'finished_at': at(gen_start(L))}, 'interval'),
        ({}, 'compatible'),
    ],
)
def test_no_rows_probe_classifies_the_origin_row(empty_lineage_db, caplog, mutation, expected):
    row = None if mutation is None else generation(L, id=ORIGIN, **mutation)
    empty_lineage_db.probe_row = row
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        targets = resolve_no_rows(empty_lineage_db)
    line = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()][0]
    assert f'id_probe={expected}' in line
    assert set(targets.values()) == {'STAMP'}


def test_probe_failure_never_changes_targets_or_outcome(empty_lineage_db, monkeypatch, caplog):
    from database import sync_recording_lineage as lineage_db

    def boom(*_args, **_kwargs):
        raise RuntimeError('synthetic probe outage with ' + SENTINEL_ID)

    monkeypatch.setattr(lineage_db, 'get_recording_id_probe', boom)
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        targets = resolve_no_rows(empty_lineage_db)
    assert set(targets.values()) == {'STAMP'}
    line = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()][0]
    assert 'id_probe=lookup_failed' in line
    for forbidden in (SENTINEL_ID, SENTINEL_TEXT, 'synthetic probe outage', 'RuntimeError'.upper()):
        assert forbidden not in line
    warnings = [r.getMessage() for r in caplog.records if 'sync_lineage_probe' in r.getMessage()]
    assert warnings and 'synthetic probe outage' not in warnings[0] and SENTINEL_ID not in warnings[0]


def test_probe_never_runs_on_degraded_failed_or_truncated_lookups(empty_lineage_db, monkeypatch):
    from database import sync_recording_lineage as lineage_db

    def degraded(*_args, **_kwargs):
        raise TimeoutError('index not serving')

    monkeypatch.setattr(lineage_db, 'get_recording_generations', degraded)
    resolve_no_rows(empty_lineage_db)
    assert 'probe' not in empty_lineage_db.calls

    empty_lineage_db.calls = []
    monkeypatch.setattr(
        lineage_db,
        'get_recording_generations',
        lambda *_a, **_k: [generation(0, id=f'GEN-{i}') for i in range(9)],
    )
    monkeypatch.setattr(lineage_db, 'get_origin_generation', lambda *_a, **_k: [])
    resolve_no_rows(empty_lineage_db)
    assert 'probe' not in empty_lineage_db.calls

    empty_lineage_db.calls = []
    resolve_segment_targets(
        'u',
        ORIGIN,
        {'seg': (float('nan'), 1.0)},
        stamped_target='STAMP',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert 'probe' not in empty_lineage_db.calls


@pytest.mark.parametrize(
    ('env', 'value'),
    [
        (sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, 'off'),
        (sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, 'other-uid'),
        (SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off'),
        (SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'disabled-typo'),
    ],
)
def test_probe_never_runs_when_disabled_or_not_allowlisted(empty_lineage_db, monkeypatch, env, value):
    monkeypatch.setenv(env, value)
    resolve_no_rows(empty_lineage_db)
    assert 'probe' not in empty_lineage_db.calls


@pytest.mark.parametrize(
    ('env', 'value'),
    [
        (SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off'),
        (SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'disabled-typo'),
        (sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, 'other-uid'),
    ],
)
def test_dedupe_off_or_excluded_cohort_emits_only_main_log_fields(empty_lineage_db, monkeypatch, caplog, env, value):
    monkeypatch.setenv(env, value)
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        resolve_no_rows(empty_lineage_db)
    line = [r.getMessage() for r in caplog.records if 'event=sync_lineage_resolve' in r.getMessage()][0]
    assert line.startswith('event=sync_lineage_resolve outcome=')
    assert 'id_probe=' not in line and 'candidates=' not in line and 'dropped_' not in line
    assert 'job_ref=' in line


def test_probe_never_runs_when_rows_were_returned(monkeypatch):
    from database import sync_recording_lineage

    fake = _EmptyLineageDb()
    fake.get_recording_generations = lambda *a, **k: [generation(L)]
    for name in ('get_recording_generations', 'get_origin_generation', 'get_recording_id_probe'):
        monkeypatch.setattr(sync_recording_lineage, name, getattr(fake, name))
    resolve_no_rows(fake)
    assert 'probe' not in fake.calls


def test_probe_read_is_metadata_only_bounded_and_exactly_once():
    from database import sync_recording_lineage as lineage_db

    calls = []

    class Client:
        def collection(self, name):
            calls.append(('collection', name))
            return self

        def document(self, name):
            calls.append(('document', name))
            return self

        def get(self, *, field_paths=None, timeout=None):
            calls.append(('get', tuple(field_paths), timeout))
            return SimpleNamespace(id=ORIGIN, to_dict=lambda: dict(generation(L)))

    row = lineage_db.get_recording_id_probe('u', ORIGIN, firestore_client=Client())
    assert row['id'] == ORIGIN
    gets = [call for call in calls if call[0] == 'get']
    assert gets == [('get', tuple(lineage_db.LINEAGE_FIELD_PATHS), 5.0)]
    assert not any(
        field.startswith(('transcript', 'photos', 'structured', 'overview')) for field in lineage_db.LINEAGE_FIELD_PATHS
    )
    assert calls[:3] == [('collection', 'users'), ('document', 'u'), ('collection', 'conversations')]
    assert calls[3] == ('document', ORIGIN)


def test_binding_reasons_fill_every_token():
    chunks = upload_straddling_next_two()
    select = select_segment_targets(
        [generation(L + 1)],
        ORIGIN,
        spans(chunks),
        stamped_target='STAMP',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert select.binding_reasons == {
        chunks[0]['id']: 'stamp_overridden',
        chunks[1]['id']: 'stamp_overridden',
        chunks[2]['id']: 'stamp_fallback',
        chunks[3]['id']: 'stamp_fallback',
    }
    unstamped = select_segment_targets(
        [],
        ORIGIN,
        spans(chunks[:1]),
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert unstamped.binding_reasons == {chunks[0]['id']: 'unbound'}


def test_resolve_and_fallback_fill_the_out_dict(empty_lineage_db):
    reasons: dict = {}
    resolve_no_rows(empty_lineage_db, reasons=reasons)
    assert set(reasons.values()) == {'stamp_fallback'}
    reasons.clear()
    fallback = recording_lineage.fallback_segment_targets(['a', 'b'], 'STAMP', binding_reasons=reasons)
    assert fallback == {'a': 'STAMP', 'b': 'STAMP'}
    assert reasons == {'a': 'stamp_fallback', 'b': 'stamp_fallback'}
    reasons.clear()
    recording_lineage.fallback_segment_targets(['a'], None, binding_reasons=reasons)
    assert reasons == {'a': 'unbound'}


def _stamp_incoming(texts, skew=40, *, binding='stamp_fallback'):
    incoming = wal(skew, texts)
    incoming['_sync_lineage_binding'] = binding
    return incoming


@pytest.mark.parametrize(('extra_seconds', 'bucket'), [(0, '0'), (30, '0_60'), (100, '60_300'), (400, 'gt_300')])
def test_stamp_fallback_live_append_reports_extent_growth(extra_seconds, bucket):
    store = seeded_store([live_row()])
    incoming = _stamp_incoming(NEW)
    incoming['finished_at'] = incoming['finished_at'] + timedelta(seconds=extra_seconds)
    assigned, created, survivors = intake(store, incoming, target_id=LIVE_ID)
    assert created is False and assigned['id'] == LIVE_ID
    assert '_sync_lineage_binding' not in assigned
    assert '_sync_lineage_binding' not in store.rows[('users', 'u', 'conversations', LIVE_ID)]
    assert assigned['_sync_lineage_dedupe']['span_delta_bucket'] == bucket


def test_all_repeat_stamp_fallback_appends_and_reports_extent_growth():
    row = live_row()
    incoming = _stamp_incoming([reworded(text) for text in LIVE])
    prove(incoming, row)
    store = seeded_store([row])
    assigned, created, survivors = intake(store, incoming, target_id=LIVE_ID)
    assert created is False and len(survivors) == len(LIVE)
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + [reworded(text) for text in LIVE])
    assert assigned['_sync_lineage_dedupe']['span_delta_bucket'] == '0_60'


def test_known_bound_target_reports_none():
    store = seeded_store([live_row()])
    incoming = _stamp_incoming(NEW, binding='bound')
    assigned, _, _ = intake(store, incoming, target_id=LIVE_ID)
    assert assigned['id'] == LIVE_ID
    assert assigned['_sync_lineage_dedupe']['span_delta_bucket'] == 'none'


def test_lineage_off_marker_is_ignored_and_never_logged(monkeypatch):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, 'off')
    store = seeded_store([live_row()])
    assigned, _, _ = intake(store, _stamp_incoming(NEW), target_id=LIVE_ID)
    assert '_sync_lineage_dedupe' not in assigned
    assert '_sync_lineage_stamp_append' not in assigned
    assert '_sync_lineage_binding' not in assigned


def test_attacker_controlled_marker_text_never_reaches_telemetry(caplog):
    store = seeded_store([live_row()])
    incoming = _stamp_incoming(NEW, binding=SENTINEL_TEXT)
    with caplog.at_level(logging.INFO):
        assigned, _, _ = intake(store, incoming, target_id=LIVE_ID)
    assert assigned['_sync_lineage_dedupe']['span_delta_bucket'] == 'none'
    assert SENTINEL_TEXT not in caplog.text


def test_dedupe_off_writes_neither_dedupe_stats_nor_stamp_append(monkeypatch):
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off')
    store = seeded_store([live_row()])
    incoming = _stamp_incoming(NEW)
    incoming['finished_at'] = incoming['finished_at'] + timedelta(seconds=30)
    assigned, created, _ = intake(store, incoming, target_id=LIVE_ID)
    assert created is False and assigned['id'] == LIVE_ID
    assert '_sync_lineage_dedupe' not in assigned
    assert '_sync_lineage_stamp_append' not in assigned


def _extent(start, end):
    return {'id': LIVE_ID, 'started_at': at(start), 'finished_at': at(end)}


@pytest.mark.parametrize(
    ('current', 'result'),
    [
        ({'id': LIVE_ID}, _extent(0, 140)),
        (_extent(70, 0), _extent(0, 140)),
        (_extent(0, 70), _extent(140, 0)),
        ({'id': LIVE_ID, 'started_at': 'not-a-date', 'finished_at': at(70)}, _extent(0, 140)),
        ({'id': LIVE_ID, 'started_at': float('nan'), 'finished_at': float('nan')}, _extent(0, 140)),
    ],
)
def test_span_bucket_rejects_unusable_endpoints(current, result):
    assert assignment._lineage_span_delta_bucket(True, LIVE_ID, current, result) == 'unknown'


def test_stamp_fallback_size_rollover_never_reports_live_stretch(monkeypatch):
    store = seeded_store([live_row()])
    key = ('users', 'u', 'conversations', LIVE_ID)
    budget = estimate_firestore_document_bytes(store.rows[key], None) + 64
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', budget)
    before = deepcopy(store.rows[key])
    assigned, created, _ = intake(store, _stamp_incoming(NEW), target_id=LIVE_ID)
    assert created is True and assigned['id'] != LIVE_ID
    assert store.rows[key] == before
    assert assigned['_sync_lineage_dedupe']['span_delta_bucket'] == '0'


def test_all_repeat_stamp_fallback_with_a_donor_appends_and_reports_growth():
    row = live_row()
    incoming = _stamp_incoming([reworded(text) for text in LIVE])
    prove(incoming, row)
    store = seeded_store_with_donor([row])
    assigned, created, survivors = intake(store, incoming, target_id=LIVE_ID)
    assert created is False and len(survivors) == len(LIVE)
    donor = store.rows[('users', 'u', 'conversations', 'DONOR-1')]
    assert donor['sync_merged_into'] == LIVE_ID and donor['deleted'] is True
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + [reworded(text) for text in LIVE])
    assert assigned['_sync_lineage_dedupe']['span_delta_bucket'] == '0_60'


def test_dedupe_off_persistence_is_unchanged(monkeypatch):
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off')
    with_marker = seeded_store([live_row()])
    without_marker = seeded_store([live_row()])
    intake(with_marker, _stamp_incoming(NEW), target_id=LIVE_ID)
    plain = wal(40, NEW)
    intake(without_marker, plain, target_id=LIVE_ID)
    assert not any(
        '_sync_lineage_binding' in row or '_sync_lineage_stamp_append' in row for row in with_marker.rows.values()
    )
    assert with_marker.rows == without_marker.rows


@pytest.fixture(scope='module')
def pipeline_module():
    from database import conversations  # noqa: F401
    from utils.sync import pipeline

    return pipeline


def test_append_telemetry_carries_the_span_bucket(pipeline_module, monkeypatch, caplog):
    pipeline = pipeline_module
    store = seeded_store([live_row()])
    texts = [reworded(text) for text in LIVE] + NEW
    with caplog.at_level(logging.INFO):
        ok, _, _ = _drive_process_segment(pipeline, monkeypatch, store, texts, lineage_binding='stamp_fallback')
    assert ok is True
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_append' in r.getMessage()]
    assert len(lines) == 1 and 'span_delta_bucket=60_300' in lines[0]


def test_dedupe_off_emits_no_lineage_append_or_stamp_event(pipeline_module, monkeypatch, caplog):
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off')
    pipeline = pipeline_module
    store = seeded_store([live_row()])
    with caplog.at_level(logging.INFO):
        ok, _, _ = _drive_process_segment(
            pipeline, monkeypatch, store, NEW, lineage_binding='stamp_fallback', wal_ts=DEDUPE_T0 + 20
        )
    assert ok is True
    stamp = [r.getMessage() for r in caplog.records if 'event=sync_lineage_stamp_append' in r.getMessage()]
    dedupe = [r.getMessage() for r in caplog.records if 'event=sync_lineage_append ' in r.getMessage()]
    assert stamp == []
    assert dedupe == []


@pytest.fixture
def coordinator():
    module, stubs = sync_v2_harness.TestAsyncCoordinatorBehavioral._load_sync_module()
    try:
        yield module, stubs
    finally:
        sync_v2_harness.TestAsyncCoordinatorBehavioral._cleanup(stubs['saved_modules'])


@pytest.mark.asyncio
async def test_coordinator_forwards_stamp_fallback_to_assignment(coordinator, monkeypatch):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', 'off')
    chunks = [sync_chunk(gen_start(L) + 61, gen_start(L) + 69, SENTINEL_TEXT)]
    paths = {f"/tmp/job-lineage/seg_{chunk['started_at'].timestamp():.0f}.wav": chunk for chunk in chunks}
    pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/job-lineage/w.wav'])
    pipeline._cleanup_files = MagicMock()
    pipeline.retrieve_vad_segments = lambda _path, segmented, _errors: segmented.update(paths)
    pipeline.get_timestamp_from_path = lambda path: paths[path]['started_at'].timestamp()
    pipeline.get_wav_duration = lambda path: (paths[path]['finished_at'] - paths[path]['started_at']).total_seconds()
    pipeline.users_db = MagicMock()
    pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
    pipeline.build_person_embeddings_cache = MagicMock(return_value={})
    pipeline.record_usage = MagicMock()
    captured = {}

    def capture(path, uid, response, lock, errors, source, is_locked, prefs, cache, target, *args, **kwargs):
        captured[paths[path]['id']] = (target, kwargs.get('lineage_binding'))
        response['updated_memories'].add(target or 'sync-row')
        return True

    pipeline.process_segment = capture
    monkeypatch.setattr(
        sys.modules[pipeline.plan_segment_targets.__module__],
        '_load_lineage',
        lambda *_args, **_kwargs: ([], None, False),
    )
    monkeypatch.setattr(
        sys.modules[pipeline.resolve_recording_session_sync_target.__module__],
        '_candidate_rows',
        lambda *_args, **_kwargs: [generation(0)],
    )
    kwargs = SimpleNamespace(
        target_conversation_id='STAMP',
        client_device_id='pendant',
        recording_session_id=ORIGIN,
        audio_start_seconds=chunks[0]['started_at'].timestamp() - 8,
        audio_end_seconds=chunks[-1]['finished_at'].timestamp(),
    )
    await module._run_full_pipeline_background_async(
        'job-lineage', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-lineage', **vars(kwargs)
    )
    assert captured[chunks[0]['id']] == ('STAMP', 'stamp_fallback')


@pytest.mark.asyncio
async def test_coordinator_lineage_off_passes_no_binding_kwarg(coordinator, monkeypatch):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, 'off')
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    chunks = [sync_chunk(gen_start(L) + 61, gen_start(L) + 69, SENTINEL_TEXT)]
    paths = {f"/tmp/job-lineage/seg_{chunk['started_at'].timestamp():.0f}.wav": chunk for chunk in chunks}
    pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/job-lineage/w.wav'])
    pipeline._cleanup_files = MagicMock()
    pipeline.retrieve_vad_segments = lambda _path, segmented, _errors: segmented.update(paths)
    pipeline.get_timestamp_from_path = lambda path: paths[path]['started_at'].timestamp()
    pipeline.get_wav_duration = lambda path: (paths[path]['finished_at'] - paths[path]['started_at']).total_seconds()
    pipeline.users_db = MagicMock()
    pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
    pipeline.build_person_embeddings_cache = MagicMock(return_value={})
    pipeline.record_usage = MagicMock()
    captured = {}

    def capture(path, uid, response, lock, errors, source, is_locked, prefs, cache, target, *args, **kwargs):
        captured[paths[path]['id']] = (target, 'lineage_binding' in kwargs)
        response['updated_memories'].add(target or 'sync-row')
        return True

    pipeline.process_segment = capture
    monkeypatch.setattr(
        sys.modules[pipeline.resolve_recording_session_sync_target.__module__],
        '_candidate_rows',
        lambda *_args, **_kwargs: [],
    )
    kwargs = SimpleNamespace(
        target_conversation_id='STAMP',
        client_device_id='pendant',
        recording_session_id=ORIGIN,
        audio_start_seconds=chunks[0]['started_at'].timestamp() - 8,
        audio_end_seconds=chunks[-1]['finished_at'].timestamp(),
    )
    await module._run_full_pipeline_background_async(
        'job-lineage', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-lineage', **vars(kwargs)
    )
    assert captured[chunks[0]['id']] == (None, False)
