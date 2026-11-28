"""Experiment ``batch_frame_outcomes``: source-frame verdicts for a completed batch upload.

Off (the default) intake writes no extra field, projection writes nothing and
the status result is the ledger's own result. On, a completed upload that
carried capture-evidence claims reports ``frame_outcomes_v1``: ``text`` where a
committed part's transcript segments lie, ``empty`` for the other frames of a
settled unit, and no verdict for a held, reused or unattributable unit.

The second half covers the batch wake of ``receipt_long_poll``.
"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.cloud.firestore_v1.field_path import FieldPath

from config import reliability_experiments
from config.policy import BatchUnitPolicy, ProjectionPolicy
from database import pipeline_ledger, sync_jobs
from database.batch_pipeline_intake import admit
from database.batch_pipeline_projection import ProjectionStore
from database.sync_ledger import BATCH_PARTIAL_STATUS
from models.sync_job_status import SyncJobStatusResponse
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import frame_outcomes, intake, projection, upload_coalescing
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.repair_lineage import lineage_record
from utils.batch_pipeline.scheduler import owner_key
from utils.capture import batch_coverage
from utils.episodes import transcript_receipts
from utils.stt import batch_language
from utils.sync import legacy_dark
from utils.sync.assignment_errors import SyncAssignmentSuperseded

EXPERIMENT = 'batch_frame_outcomes'
OWNER, JOB = 'synthetic-owner', 'bp_first'
FRAME = 320  # samples in one 20 ms source frame at 16 kHz
COMPLETED = {'new_memories': ['c1'], 'updated_memories': [], 'failed_segments': 0, 'total_segments': 1, 'errors': []}


@pytest.fixture
def experiment(monkeypatch):
    def set_state(on: bool, name: str = EXPERIMENT) -> None:
        if on:
            monkeypatch.setenv(reliability_experiments.ENV, name)
        else:
            monkeypatch.delenv(reliability_experiments.ENV, raising=False)

    return set_state


@pytest.fixture(autouse=True)
def cohort(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', OWNER)
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)


def claim(start, count, root='root-a', epoch=0, rate=16000):
    return {
        'capture_root': root,
        'clock_epoch': epoch,
        'channel': 'mono',
        'codec': 'opus',
        'source_frame_start': start,
        'frame_count': count,
        'rate_hz': rate,
    }


def runs(file_claim, *, first=0, count=None, unit_start=0):
    """Production's own unit provenance for ``count`` frames of one file, from frame ``first``."""
    total = file_claim['frame_count']
    count = total - first if count is None else count
    mapping = {'claim': file_claim, 'offsets': [index * FRAME for index in range(total + 1)], 'incomplete': False}
    return tuple(batch_coverage.piece_runs(mapping, first * FRAME, count * FRAME, unit_start, {}))


def upload(store, claims, units, *, recorded=True):
    """Admit one upload. ``units`` maps a segment id to its coverage runs, as intake holds them."""
    works = [replace(item(segment, owner=OWNER), privacy_generation=0) for segment in units]
    binding = ProjectionBinding(OWNER, JOB, 'content', tuple(units))
    outcome = admit(
        store,
        works,
        binding,
        100,
        namespace='batch_pipeline_test_frames',
        intake={
            'owner_id': OWNER,
            'owner_key': owner_key(OWNER),
            'content_id': 'content',
            'segment_ids': list(units),
            'total_files': len(claims or {}),
            'lane': 'fresh',
            'repair_lineage': lineage_record({'capture_evidence_claims': claims}),
            **(frame_outcomes.intake_runs(units) if recorded else {}),
        },
    )
    assert outcome['outcome'] == 'batch'
    return binding


def settle(store, segment, outcome='success', **fields):
    store.rows['jobs', segment].update(
        state='committed',
        merge_pending=False,
        result={'segment_id': segment, 'result_uri': f'gs://synthetic/{segment}.json', 'outcome': outcome},
        **fields,
    )


def text(store, segment, *parts, uri=None):
    """Projection's record of each part's segment spans, in unit samples."""
    store.rows['intakes', JOB].setdefault(frame_outcomes.TEXT_FIELD, {})[segment] = {
        str(index): {'of': len(parts), 'uri': uri or f'gs://synthetic/{segment}.json', 'spans': list(spans)}
        for index, spans in enumerate(parts)
        if spans is not None
    }


def complete(store, result=None):
    store.rows['content', f'{OWNER}/content'].update(status='completed', result=dict(result or COMPLETED))


def status(store):
    return intake.durable_status(store, OWNER, JOB)


def verdicts(store):
    found = status(store)
    assert found['status'] == 'completed'
    ranges = found['result'].get(frame_outcomes.FIELD)
    if ranges is None:
        return None
    # The wire model accepts exactly this shape, and ranges of one key never overlap.
    SyncJobStatusResponse(**found)
    for before, after in zip(ranges, ranges[1:]):
        same = (before['capture_root'], before['clock_epoch']) == (after['capture_root'], after['clock_epoch'])
        assert not same or before['end'] <= after['start']
    return [(r['capture_root'], r['clock_epoch'], r['start'], r['end'], r['status']) for r in ranges]


def test_experiment_is_registered_and_off_by_default(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    assert not reliability_experiments.enabled(EXPERIMENT)
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    assert reliability_experiments.enabled(EXPERIMENT) and not reliability_experiments.unknown()
    assert 'batch' in reliability_experiments.EXPERIMENTS['receipt_long_poll']


# --- status read -----------------------------------------------------------------------------


def test_off_the_completed_result_is_the_baseline_result(experiment):
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1')
    text(store, 'u1', [0, 50 * FRAME])
    complete(store)
    baseline = MemoryStore()
    upload(baseline, {'a.bin': file}, {'u1': runs(file)}, recorded=False)
    settle(baseline, 'u1')
    complete(baseline)

    experiment(False)
    off = status(store)
    assert off == status(baseline)
    assert off['result'] == COMPLETED and frame_outcomes.FIELD not in off['result']
    assert off == {
        'job_id': JOB,
        'status': 'completed',
        'lane': 'fresh',
        'total_files': 1,
        'total_segments': 1,
        'processed_segments': 1,
        'successful_segments': 1,
        'failed_segments': 0,
        'errors': [],
        'result': COMPLETED,
        'poll_after_ms': 0,
        'completed_at': None,
    }

    experiment(True)
    on = status(store)
    assert {**on, 'result': {k: v for k, v in on['result'].items() if k != frame_outcomes.FIELD}} == off
    # The ledger's stored result is never rewritten by a status read.
    assert store.rows['content', f'{OWNER}/content']['result'] == COMPLETED


def test_all_text(experiment):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1')
    text(store, 'u1', [0, 50 * FRAME])
    complete(store)
    assert verdicts(store) == [('root-a', 0, 100, 150, 'text')]


def test_text_with_empty_remainder_marks_every_touched_frame_as_text(experiment):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1')
    # Two segments; the first starts and ends inside a frame, the second is a point word.
    text(store, 'u1', [10 * FRAME + 5, 20 * FRAME - 5, 30 * FRAME + 7, 30 * FRAME + 8])
    complete(store)
    assert verdicts(store) == [
        ('root-a', 0, 100, 110, 'empty'),
        ('root-a', 0, 110, 120, 'text'),
        ('root-a', 0, 120, 130, 'empty'),
        ('root-a', 0, 130, 131, 'text'),
        ('root-a', 0, 131, 150, 'empty'),
    ]


def test_parts_of_one_unit_join_and_a_missing_part_withholds_the_unit(experiment):
    experiment(True)
    file = claim(0, 40)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1')
    text(store, 'u1', [0, 4 * FRAME], [], [30 * FRAME, 40 * FRAME])
    complete(store)
    assert verdicts(store) == [
        ('root-a', 0, 0, 4, 'text'),
        ('root-a', 0, 4, 30, 'empty'),
        ('root-a', 0, 30, 40, 'text'),
    ]
    text(store, 'u1', [0, 4 * FRAME], None, [30 * FRAME, 40 * FRAME])
    assert verdicts(store) == []


@pytest.mark.parametrize('outcome,recovery_state', [('silence', None), ('no_recoverable_speech', 'recovered')])
def test_unit_settled_without_speech_is_empty(experiment, outcome, recovery_state):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1', outcome, recovery_state=recovery_state)
    complete(store)
    assert verdicts(store) == [('root-a', 0, 100, 150, 'empty')]


def test_one_file_split_across_two_units_merges_and_text_wins(experiment):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file, count=25), 'u2': runs(file, first=25)})
    settle(store, 'u1', 'silence')
    settle(store, 'u2', 'silence')
    complete(store)
    assert verdicts(store) == [('root-a', 0, 100, 150, 'empty')]
    settle(store, 'u2')
    text(store, 'u2', [0, 2 * FRAME])
    assert verdicts(store) == [
        ('root-a', 0, 100, 125, 'empty'),
        ('root-a', 0, 125, 127, 'text'),
        ('root-a', 0, 127, 150, 'empty'),
    ]


def test_files_packed_into_one_unit_use_each_run_sample_origin_and_sort_by_key(experiment):
    experiment(True)
    first, second = claim(0, 10, root='root-b'), claim(500, 10, root='root-a', epoch=2)
    # The second file starts one second into the unit, after inserted silence.
    packed = (*runs(first), *runs(second, unit_start=16000))
    store = MemoryStore()
    upload(store, {'a.bin': first, 'b.bin': second}, {'u1': packed})
    settle(store, 'u1')
    text(store, 'u1', [8 * FRAME, 16000 + 3 * FRAME])
    complete(store)
    assert verdicts(store) == [
        ('root-a', 2, 500, 503, 'text'),
        ('root-a', 2, 503, 510, 'empty'),
        ('root-b', 0, 0, 8, 'empty'),
        ('root-b', 0, 8, 10, 'text'),
    ]


def test_job_with_a_held_unit_is_not_completed_and_carries_no_verdicts(experiment):
    experiment(True)
    one, two = claim(0, 10), claim(10, 10)
    store = MemoryStore()
    upload(store, {'a.bin': one, 'b.bin': two}, {'u1': runs(one), 'u2': runs(two)})
    settle(store, 'u1', 'silence')
    store.rows['jobs', 'u2'].update(state='quarantined', recovery_state='held', merge_pending=False)
    waiting = status(store)
    assert waiting['status'] == 'processing' and waiting['result'] is None
    # The held-partial ledger still withholds custody; its result gets no verdicts either.
    partial = {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 1,
        'held_segments': 1,
        'total_segments': 2,
        'errors': [],
        'outcome': 'partial',
    }
    store.rows['content', f'{OWNER}/content'].update(status=BATCH_PARTIAL_STATUS, result=partial)
    held = status(store)
    assert held['status'] == 'processing' and held['reason_code'] == 'batch_unit_held'
    assert held['result'] == partial


@pytest.mark.parametrize(
    'unsettled',
    [
        {'state': 'committed', 'recovery_state': 'held'},
        {'state': 'committed', 'recovery_state': 'failed_held'},
        {'state': 'committed', 'recovery_state': 'cancelled'},
        {'state': 'quarantined', 'recovery_state': 'recovered'},
        {'state': 'dead'},
        {'state': 'committed', 'speech_redrive': {'state': 'running'}},
        {'state': 'committed', 'source_alias': {'segment_id': 'other'}},
        {'state': 'committed', 'shadow': True},
        {'state': 'committed', 'result': {'outcome': 'unsupported_language'}},
        {'state': 'committed', 'result': None},
    ],
)
def test_unsettled_unit_never_gets_a_verdict_while_its_siblings_keep_theirs(experiment, unsettled):
    experiment(True)
    one, two = claim(0, 10), claim(10, 10)
    store = MemoryStore()
    upload(store, {'a.bin': one, 'b.bin': two}, {'u1': runs(one), 'u2': runs(two)})
    settle(store, 'u1', 'silence')
    settle(store, 'u2', 'silence')
    store.rows['jobs', 'u2'].update(unsettled)
    row = store.rows['intakes', JOB]
    jobs = [store.rows['jobs', segment] for segment in ('u1', 'u2')]
    assert frame_outcomes.completed_ranges(row, jobs) == [
        {'capture_root': 'root-a', 'clock_epoch': 0, 'start': 0, 'end': 10, 'status': 'empty'}
    ]
    assert frame_outcomes.completed_ranges(row, jobs[:1]) == frame_outcomes.completed_ranges(row, jobs)


def test_completed_job_withholds_a_unit_whose_recovery_is_still_held(experiment):
    experiment(True)
    one, two = claim(0, 10), claim(10, 10)
    store = MemoryStore()
    upload(store, {'a.bin': one, 'b.bin': two}, {'u1': runs(one), 'u2': runs(two)})
    settle(store, 'u1')
    text(store, 'u1', [0, FRAME])
    settle(store, 'u2', 'silence', recovery_state='held')
    complete(store)
    assert verdicts(store) == [('root-a', 0, 0, 1, 'text'), ('root-a', 0, 1, 10, 'empty')]


def test_text_record_of_another_result_or_no_record_withholds_the_unit(experiment):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1')
    complete(store)
    assert verdicts(store) == []
    text(store, 'u1', [0, FRAME], uri='gs://synthetic/earlier-result.json')
    assert verdicts(store) == []
    text(store, 'u1', [0, FRAME])
    assert verdicts(store) == [('root-a', 0, 100, 101, 'text'), ('root-a', 0, 101, 150, 'empty')]
    for malformed in ([0], [5, 5], [-1, 4], [0, 1.5], 'spans'):
        store.rows['intakes', JOB][frame_outcomes.TEXT_FIELD]['u1']['0']['spans'] = malformed
        assert verdicts(store) == []


def test_upload_without_claims_or_without_a_unit_record_omits_the_field(experiment):
    experiment(True)
    file = claim(100, 50)
    for claims, recorded in (({}, True), (None, True), ({'a.bin': file}, False)):
        store = MemoryStore()
        upload(store, claims, {'u1': runs(file)}, recorded=recorded)
        settle(store, 'u1', 'silence')
        complete(store)
        assert verdicts(store) is None
        assert status(store)['result'] == COMPLETED
    # A cached completed receipt has no units at all.
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': ()})
    settle(store, 'u1', 'silence')
    complete(store)
    assert frame_outcomes.RUNS_FIELD not in store.rows['intakes', JOB] and verdicts(store) is None


@pytest.mark.parametrize(
    'claims',
    [
        {'a.bin': {**claim(100, 50), 'clock_epoch': '0'}},
        {'a.bin': {**claim(100, 50), 'frame_count': 0}},
        {'a.bin': {**claim(100, 50), 'source_frame_start': -1}},
        {'a.bin': {**claim(100, 50), 'capture_root': ''}},
        {'a.bin': {**claim(100, 50), 'frame_count': True}},
        {'a.bin': 'not-a-claim'},
        ['not', 'a', 'mapping'],
    ],
)
def test_malformed_claims_omit_the_field(experiment, claims):
    experiment(True)
    store = MemoryStore()
    upload(store, claims, {'u1': runs(claim(100, 50))})
    settle(store, 'u1', 'silence')
    complete(store)
    assert verdicts(store) is None


@pytest.mark.parametrize('lineage', [None, '', 'not json', '[]', '{"capture_evidence_claims": {}}'])
def test_malformed_stored_lineage_or_unit_record_omits_the_field(experiment, lineage):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1', 'silence')
    complete(store)
    good = dict(store.rows['intakes', JOB])
    store.rows['intakes', JOB]['repair_lineage'] = lineage
    assert verdicts(store) is None
    for body in ('not json', '[]', '{"u1": [["root-a", 0, 5, 5, 0, 320]]}', '{"u1": [["root-a", 0, 1, 2, 0, 0]]}'):
        store.rows['intakes', JOB] = {**good, frame_outcomes.RUNS_FIELD: body}
        assert verdicts(store) is None


def test_a_malformed_claim_beside_a_valid_one_keeps_only_the_valid_file(experiment):
    experiment(True)
    good, bad = claim(0, 10), {**claim(50, 10), 'clock_epoch': None}
    store = MemoryStore()
    upload(store, {'a.bin': good, 'b.bin': bad}, {'u1': runs(good)})
    settle(store, 'u1', 'silence')
    complete(store)
    assert verdicts(store) == [('root-a', 0, 0, 10, 'empty')]


def test_frames_outside_the_claims_or_held_by_two_units_give_no_verdict_at_all(experiment):
    experiment(True)
    file = claim(100, 50)
    outside = MemoryStore()
    upload(outside, {'a.bin': claim(100, 40)}, {'u1': runs(file)})
    settle(outside, 'u1', 'silence')
    complete(outside)
    assert verdicts(outside) == []
    twice = MemoryStore()
    upload(twice, {'a.bin': file}, {'u1': runs(file), 'u2': runs(file, first=40)})
    settle(twice, 'u1', 'silence')
    settle(twice, 'u2', 'silence')
    complete(twice)
    assert verdicts(twice) == []


def test_a_fault_while_computing_verdicts_never_breaks_the_status_read(experiment, monkeypatch):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1', 'silence')
    complete(store)
    monkeypatch.setattr(frame_outcomes, 'completed_ranges', Mock(side_effect=RuntimeError('synthetic')))
    assert status(store)['result'] == COMPLETED


@pytest.mark.parametrize('on', [False, True])
def test_coalesced_member_never_receives_or_stores_its_target_verdicts(monkeypatch, experiment, on):
    experiment(on)
    file = claim(100, 50)
    store = MemoryStore()
    upload(store, {'a.bin': file}, {'u1': runs(file)})
    settle(store, 'u1', 'silence')
    complete(store)
    store.rows['intakes', 'bp_member'] = {'owner_id': OWNER, 'coalesce_group': 'group', 'coalesce_target': JOB}
    readers = []
    monkeypatch.setattr(upload_coalescing, 'member_status', lambda _store, _uid, _intake, read: readers.append(read))
    intake.durable_status(store, OWNER, 'bp_member')
    (read,) = readers
    # Both readers carry the caller's poll flag; off, the reader is the ordinary status read.
    assert read.keywords == {'poll': False}
    assert read.func is (intake._status_without_frame_outcomes if on else intake.durable_status)
    target = read(store, OWNER, JOB)
    assert target['status'] == 'completed' and target['result'] == COMPLETED
    # The target's own poll still carries them.
    assert (verdicts(store) is not None) is on


# --- intake ----------------------------------------------------------------------------------


def test_intake_record_keeps_only_whole_16k_frames_production_already_derived():
    file = claim(100, 50)
    assert frame_outcomes.intake_runs({'u1': runs(file), 'silent': ()}) == {
        frame_outcomes.RUNS_FIELD: '{"u1":[["root-a",0,100,150,0,320]]}'
    }
    # 8 kHz sources and frames cut by a unit boundary have no run, hence no record and no verdict.
    assert runs(claim(100, 50, rate=8000)) == ()
    mapping = {'claim': file, 'offsets': [index * FRAME for index in range(51)], 'incomplete': False}
    cut = batch_coverage.piece_runs(mapping, 100, 10 * FRAME, 0, {})
    assert [(run['start'], run['end']) for run in cut] == [(101, 110)]
    assert frame_outcomes.intake_runs({'u1': ()}) == {}
    assert frame_outcomes.intake_runs({'u1': ({'key': {'capture_root': 'r', 'clock_epoch': 'default'}},)}) == {}
    assert frame_outcomes.intake_runs({'u1': ({'start': 1},)}) == {}
    huge = {f'u{index}': runs(claim(index * 100, 50, root='r' * 4000)) for index in range(80)}
    assert frame_outcomes.intake_runs(huge) == {}


@pytest.mark.parametrize('on', [False, True])
async def test_accept_upload_records_unit_frames_only_with_the_experiment(monkeypatch, experiment, on):
    # Same harness as test_batch_intake_outcome: a real accept_upload over a held-audio decoder.
    experiment(on)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = MemoryStore()
    store.namespace = 'batch_pipeline_dev'
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: legacy_dark.LegacySyncMode.ON)
    monkeypatch.setattr(intake, 'serving_for', lambda *a, **k: False)
    monkeypatch.setattr(intake, 'admission_language_exclusion_enabled', lambda: False)
    monkeypatch.setattr(intake, 'language_guard_enabled', lambda: False)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
    )
    monkeypatch.setattr(intake, 'with_context', lambda wav, ctx: wav)
    artifacts = Mock()
    artifacts.stage_audio = Mock(return_value='gs://synthetic/audio.bin')
    monkeypatch.setattr(intake, 'artifacts_for', Mock(return_value=artifacts))

    def authorize(_store, _work, snapshots):
        snapshots['user'] = {}
        snapshots['conversations'] = {}
        return ProtectionContext('standard', 0)

    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    admitted = {}

    def record_admit(*args, **kwargs):
        admitted.update(kwargs['intake'])
        return {'outcome': 'batch', 'job_id': 'bp_job'}

    monkeypatch.setattr(intake, 'admit', record_admit)
    queued = {'job_id': 'bp_job', 'status': 'queued', 'total_files': 1, 'total_segments': 0, 'poll_after_ms': 0}
    monkeypatch.setattr(intake, 'durable_status', lambda *a, **k: {**queued, 'lane': 'fresh'})
    monkeypatch.setattr(
        batch_language,
        'resolve_language',
        lambda *a, **k: SimpleNamespace(
            language='en', parakeet_safe=True, evidence=None, confidence=1.0, probe_seconds=0.0
        ),
    )
    file = claim(100, 50)

    def decode(_max_seconds):
        yield SimpleNamespace(capture_at=0.0, duration_seconds=1.0, wav=b'x', coverage_runs=runs(file))
        yield SimpleNamespace(capture_at=5.0, duration_seconds=1.0, wav=b'y', coverage_runs=())

    response = await intake.accept_upload(
        uid='test-uid',
        job_id='job',
        content_id='content',
        paths=[],
        lane='fresh',
        recording_age_seconds=60,
        source='omi',
        should_lock=False,
        conversation_id=None,
        client_device_id=None,
        client_platform='ios',
        policy=BatchUnitPolicy(batch_enabled=True, batch_percent=5),
        decode=decode,
        intake_context={'capture_evidence_claims': {'a.bin': file}},
    )
    assert response.status_code == 202
    baseline_keys = {
        'owner_id',
        'owner_key',
        'content_id',
        'conversation_id',
        'segment_ids',
        'total_files',
        'total_audio_seconds',
        'lane',
        'raw_capture_paths',
        'repair_lineage',
        'repair_languages',
    }
    assert admitted['raw_capture_paths'] == []
    if on:
        assert set(admitted) == baseline_keys | {frame_outcomes.RUNS_FIELD}
        first = admitted['segment_ids'][0]
        assert admitted[frame_outcomes.RUNS_FIELD] == '{"%s":[["root-a",0,100,150,0,320]]}' % first
    else:
        assert set(admitted) == baseline_keys


# --- projection ------------------------------------------------------------------------------


def test_segment_spans_follow_the_unit_sample_clock():
    started = SimpleNamespace(timestamp=lambda: 1000.5)
    incoming = {
        'started_at': started,
        'transcript_segments': [
            {'start': 1.0, 'end': 2.0},
            {'start': 1.5, 'end': 3.0},
            {'start': 4.0, 'end': 4.0},
        ],
    }
    # The part starts half a second into its unit; overlapping segments merge; a point word keeps one sample.
    assert frame_outcomes.segment_samples(incoming, 1000.0) == [24000, 56000, 72000, 72001]
    assert frame_outcomes.segment_samples({'started_at': started, 'transcript_segments': []}, 1000.0) == []
    for broken in (
        {'started_at': started, 'transcript_segments': [{'speaker_id_scope': 'sync:fixture'}]},
        {'started_at': started, 'transcript_segments': [{'start': 2.0, 'end': 1.0}]},
        {'started_at': started, 'transcript_segments': [{'start': -5.0, 'end': 1.0}]},
        {'transcript_segments': []},
    ):
        assert frame_outcomes.segment_samples(broken, 1000.0) is None
    many = [{'start': index, 'end': index + 0.5} for index in range(frame_outcomes.MAX_PART_SPANS + 1)]
    assert frame_outcomes.segment_samples({'started_at': started, 'transcript_segments': many}, 1000.5) is None


class IntakeRows:
    """The projection store's ``ref(table, key).update`` over a MemoryStore row."""

    def __init__(self, store):
        self.store = store

    def ref(self, table, key):
        def update(fields):
            row = self.store.rows[table, key]  # A missing row raises, as Firestore's update does.
            for path, value in fields.items():
                *parents, leaf = FieldPath.from_api_repr(path).parts
                for name in parents:
                    row = row.setdefault(name, {})
                row[leaf] = value

        return SimpleNamespace(update=update)


def test_projection_record_feeds_the_status_read_end_to_end(experiment):
    experiment(True)
    file = claim(100, 50)
    store = MemoryStore()
    binding = upload(store, {'a.bin': file}, {'0123abc': runs(file)})
    settle(store, '0123abc')
    unit = WorkItem('0123abc', OWNER, 1000.0, 'gs://synthetic/audio', 1.0, Priority.DEEP)
    entry = {'result': store.rows['jobs', '0123abc']['result']}
    started = SimpleNamespace(timestamp=lambda: 1000.0)
    spans = frame_outcomes.segment_samples(
        {'started_at': started, 'transcript_segments': [{'start': 0.2, 'end': 0.4}]}, unit.capture_at
    )
    frame_outcomes.record_part(IntakeRows(store), binding, unit, entry, 0, 2, spans)
    complete(store)
    assert verdicts(store) == []  # The second part has not settled yet.
    frame_outcomes.record_part(IntakeRows(store), binding, unit, entry, 1, 2, [])
    assert verdicts(store) == [
        ('root-a', 0, 100, 110, 'empty'),
        ('root-a', 0, 110, 120, 'text'),
        ('root-a', 0, 120, 150, 'empty'),
    ]


def test_projection_record_is_best_effort():
    binding = ProjectionBinding(OWNER, JOB, 'content', ('segment',))
    unit = WorkItem('segment', OWNER, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    store = Mock()
    frame_outcomes.record_part(store, binding, unit, {}, 0, 1, None)
    store.ref.assert_not_called()
    store.ref.return_value.update.side_effect = RuntimeError('synthetic outage')
    frame_outcomes.record_part(store, binding, unit, {}, 0, 1, [0, 16])
    frame_outcomes.record_part(IntakeRows(MemoryStore()), binding, unit, {}, 0, 1, [0, 16])  # no intake row


SEGMENT = {'id': 's1', 'start': 0.25, 'end': 0.75, 'speaker_id_scope': 'sync:fixture'}


def projector_for(monkeypatch, segments, **payload_fields):
    payload = {
        'words': [{'word': 'Fixture.', 'timestamp': [0, 1]}],
        'audio_seconds': 1,
        'speech_seconds': 1,
        'diarization': {'turns': []},
        **payload_fields,
    }
    projector = projection.Projector(Mock(), Mock(return_value=payload))
    projector.store = Mock()
    projector.finish_part = Mock()
    row = {'id': 'record', 'transcript_segments': segments}
    monkeypatch.setattr(
        projection,
        'build_incoming',
        lambda *a, **kw: {**row, 'started_at': Mock(timestamp=lambda: 0), 'finished_at': Mock(timestamp=lambda: 1)},
    )
    monkeypatch.setattr(projection.conversations_db, 'get_closest_conversation_to_timestamps', lambda *a: None)
    monkeypatch.setattr(batch_coverage, 'record_projection', Mock())
    monkeypatch.setattr(transcript_receipts, 'enqueue', Mock())
    return projector, row


@pytest.mark.parametrize('on', [False, True])
def test_assign_parts_records_a_committed_part_only_with_the_experiment(monkeypatch, experiment, on):
    experiment(on)
    binding = ProjectionBinding(OWNER, JOB, 'content', ('segment',))
    unit = WorkItem('segment', OWNER, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    projector, row = projector_for(monkeypatch, [SEGMENT])
    receipt = {'state': 'persisted', 'conversation_id': 'record'}
    projector.store.session.return_value.persist.return_value = receipt
    order = []

    def assign(uid, incoming, **kwargs):
        kwargs['after_assign'](Mock(), (row, False, []))
        order.append('commit')
        return row, False, []

    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', assign)
    projector.store.ref.return_value.update.side_effect = lambda fields: order.append('record')
    projector.assign_parts(unit, {'result': {'result_uri': 'fixture'}}, binding)
    projector.finish_part.assert_called_once()
    assert projector.finish_part.call_args.args[2] is receipt
    if not on:
        projector.store.ref.assert_not_called()
        assert order == ['commit']
        return
    assert order == ['commit', 'record']
    projector.store.ref.assert_called_once_with('intakes', JOB)
    projector.store.ref.return_value.update.assert_called_once_with(
        {f'{frame_outcomes.TEXT_FIELD}.segment.`0`': {'of': 1, 'uri': 'fixture', 'spans': [4000, 12000]}}
    )


def test_assign_parts_leaves_no_record_for_a_superseded_or_failed_assignment(monkeypatch, experiment):
    experiment(True)
    binding = ProjectionBinding(OWNER, JOB, 'content', ('segment',))
    unit = WorkItem('segment', OWNER, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    projector, _ = projector_for(monkeypatch, [SEGMENT])
    superseded = {'state': 'ready', 'disposition': 'superseded', 'conversation_id': None, 'speech_seconds': 0.0}
    projector.store.session.return_value.persist_empty.return_value = superseded
    monkeypatch.setattr(
        projection.conversations_db, 'assign_sync_conversation', Mock(side_effect=SyncAssignmentSuperseded('fixture'))
    )
    projector.assign_parts(unit, {'result': {'result_uri': 'fixture'}}, binding)
    projector.store.ref.assert_not_called()
    monkeypatch.setattr(
        projection.conversations_db, 'assign_sync_conversation', Mock(side_effect=RuntimeError('synthetic'))
    )
    with pytest.raises(RuntimeError):
        projector.assign_parts(unit, {'result': {'result_uri': 'fixture'}}, binding, policy=ProjectionPolicy())
    projector.store.ref.assert_not_called()


def test_assign_parts_records_a_part_without_segments_as_no_text_and_survives_a_record_fault(monkeypatch, experiment):
    experiment(True)
    binding = ProjectionBinding(OWNER, JOB, 'content', ('segment',))
    unit = WorkItem('segment', OWNER, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    projector, _ = projector_for(monkeypatch, [])
    empty = {'state': 'ready', 'conversation_id': None, 'speech_seconds': 0.0}
    projector.store.session.return_value.persist_empty.return_value = empty
    projector.store.ref.return_value.update.side_effect = RuntimeError('synthetic outage')
    projector.assign_parts(unit, {'result': {'result_uri': 'fixture'}}, binding)
    projector.store.ref.return_value.update.assert_called_once_with(
        {f'{frame_outcomes.TEXT_FIELD}.segment.`0`': {'of': 1, 'uri': 'fixture', 'spans': []}}
    )
    assert projector.finish_part.call_args.args[2] is empty


# --- receipt_long_poll: batch wake -------------------------------------------------------------


def completion_store(monkeypatch, *, changed=True):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setattr(pipeline_ledger, 'advance', lambda *args, **kwargs: True)
    redis = Mock()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    store = ProjectionStore(SimpleNamespace(client=Mock(), namespace='synthetic'))
    store.policy = lambda _: ProjectionPolicy()
    store._mirror = lambda *args, **kwargs: None
    store.run = lambda operation, policy=None: ({'outcome': 'success'}, changed, 4.5)
    return store, redis


@pytest.mark.parametrize('on', [False, True])
def test_first_batch_completion_publishes_a_wake_only_with_the_experiment(monkeypatch, experiment, on):
    experiment(on, 'receipt_long_poll')
    store, redis = completion_store(monkeypatch)
    binding = ProjectionBinding(OWNER, JOB, 'content', ('segment',))
    assert store.complete('segment', binding, 1234.5, {'seconds': 4.5})['outcome'] == 'success'
    if on:
        redis.publish.assert_called_once_with(sync_jobs.receipt_channel(OWNER), JOB)
    else:
        redis.publish.assert_not_called()


def test_batch_wake_is_only_for_a_new_phone_completion_and_never_fails_it(monkeypatch, experiment):
    experiment(True, 'receipt_long_poll')
    binding = ProjectionBinding(OWNER, JOB, 'content', ('segment',))
    replayed, redis = completion_store(monkeypatch, changed=False)
    assert replayed.complete('segment', binding, 2.0, {'seconds': 4.5})['outcome'] == 'success'
    redis.publish.assert_not_called()
    native, redis = completion_store(monkeypatch)
    recording = replace(binding, target_conversation_id='capture', record_origin=True, native_record=True)
    assert native.complete('segment', recording, 2.0, {'seconds': 4.5})['outcome'] == 'success'
    redis.publish.assert_not_called()
    broken, redis = completion_store(monkeypatch)
    redis.publish.side_effect = RuntimeError('synthetic redis outage')
    assert broken.complete('segment', binding, 2.0, {'seconds': 4.5})['outcome'] == 'success'
    redis.publish.assert_called_once()
    # The frame-outcome switch alone publishes nothing.
    experiment(True, EXPERIMENT)
    other, redis = completion_store(monkeypatch)
    other.complete('segment', binding, 2.0, {'seconds': 4.5})
    redis.publish.assert_not_called()


def test_batch_wake_names_each_coalesced_member_handle(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    redis = Mock()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    binding = ProjectionBinding(OWNER, 'bp_target', 'content', ('segment',))
    ProjectionStore._wake_receipt_waiters(binding, [('intakes', 'bp_member_a'), ('intakes', 'bp_member_b')])
    channel = sync_jobs.receipt_channel(OWNER)
    assert [call.args for call in redis.publish.call_args_list] == [
        (channel, 'bp_target'),
        (channel, 'bp_member_a'),
        (channel, 'bp_member_b'),
    ]


def test_assign_parts_records_every_part_including_one_without_words(monkeypatch, experiment):
    experiment(True)
    binding = ProjectionBinding(OWNER, JOB, 'content', ('segment',))
    unit = WorkItem('segment', OWNER, 0, 'gs://synthetic/audio', 300, Priority.DEEP)
    # Two VAD groups more than two minutes apart; only the first holds a word.
    projector, row = projector_for(
        monkeypatch,
        [SEGMENT],
        audio_seconds=300,
        speech_seconds=2,
        speech_spans=[{'start': 0, 'end': 1}, {'start': 250, 'end': 251}],
    )
    projector.store.session.return_value.persist.return_value = {'state': 'persisted', 'conversation_id': 'record'}
    projector.store.session.return_value.persist_empty.return_value = {'state': 'ready', 'conversation_id': None}

    def assign(uid, incoming, **kwargs):
        kwargs['after_assign'](Mock(), (row, False, []))
        return row, False, []

    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', assign)
    projector.assign_parts(unit, {'result': {'result_uri': 'fixture'}}, binding)
    assert [call.args[0] for call in projector.store.ref.return_value.update.call_args_list] == [
        {f'{frame_outcomes.TEXT_FIELD}.segment.`0`': {'of': 2, 'uri': 'fixture', 'spans': [4000, 12000]}},
        {f'{frame_outcomes.TEXT_FIELD}.segment.`1`': {'of': 2, 'uri': 'fixture', 'spans': []}},
    ]
