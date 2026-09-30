"""Safety-WAL uploads bind per segment to the live recording's rollover generations.

Synthetic replay of the live+sync duplicate: one phone recording (origin id
``REC-ORIGIN``) becomes one live row per silence rollover, while every WAL
carries the origin id. A batch stamped for generation L starts before L and
runs past its end; an unstamped batch straddles the next two generations. The
whole-batch resolver (kill switch off, today's behavior) finds only the first
generation, drops the stamp and creates a sync row. Per-segment lineage binding
appends every segment to the live row that owns its audio. All ids are
synthetic.
"""

import logging
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import tests.unit.test_listen_reconnect_continuity as continuity
import tests.unit.test_sync_v2 as sync_v2_harness
from config import sync_lineage
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import conversations, intake
from utils.sync import recording_lineage, recording_session_target
from utils.sync.assignment_errors import SyncAssignmentSuperseded
from utils.sync.recording_lineage import (
    lineage_resolution_requested,
    resolve_segment_targets,
    select_segment_targets,
)

ORIGIN = 'REC-ORIGIN'
T0 = 1_760_000_000
PERIOD = 360  # one rollover generation every six minutes
DURATION = 232  # live speech, then more than two minutes of silence
GENERATIONS = 50
L = 11  # the generation the phone stamped


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations  # noqa: F401
    from utils.sync import pipeline

    return pipeline


@pytest.fixture(autouse=True)
def default_flag(monkeypatch):
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, raising=False)


def at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc)


def gen_id(k):
    return ORIGIN if k == 0 else f'LIVE-{k:02d}'


def gen_start(k):
    return T0 + PERIOD * k


def live_text(k, i):
    return f'live generation {k} line {i} about the quarterly planning review'


def generation(k, **extra):
    start = gen_start(k)
    row = {
        'id': gen_id(k),
        'started_at': at(start),
        'finished_at': at(start + DURATION),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'discarded': False,
        'status': 'completed',
        'external_data': {
            'recording_session_id': ORIGIN if k == 0 else f'SESSION-{k:02d}',
            'recording_origin_id': ORIGIN,
        },
        'transcript_segments': [
            {'start': 60.0 * i + 1, 'end': 60.0 * i + 9, 'text': live_text(k, i), 'speaker_id': 0, 'is_user': False}
            for i in range(4)
        ],
    }
    row.update(extra)
    return row


def sync_chunk(start, end, text):
    return {
        'id': f'SYNC-{start}',
        'started_at': at(start),
        'finished_at': at(end),
        'source': 'omi',
        'client_device_id': 'pendant',
        'discarded': False,
        'status': 'completed',
        'transcript_segments': [{'start': 0.0, 'end': end - start, 'text': text, 'speaker_id': 0, 'is_user': False}],
    }


def upload_stamped_for_l():
    """Six WAL-minutes stamped for L, 1 s phone clock skew: speech inside L, then after it ended."""
    s = gen_start(L) + 1
    return [
        sync_chunk(s + 1, s + 9, live_text(L, 0)),
        sync_chunk(s + 61, s + 69, live_text(L, 1)),
        sync_chunk(s + 121, s + 129, live_text(L, 2)),
        sync_chunk(s + 181, s + 189, live_text(L, 3)),
        sync_chunk(s + 236, s + 250, 'speech the live socket never received after the last line'),
        sync_chunk(s + 300, s + 340, 'a later remark in the silence before the next generation'),
    ]


def upload_straddling_next_two():
    """Unstamped five WAL-minutes that straddle generations L+1 and L+2."""
    s1, s2 = gen_start(L + 1) + 1, gen_start(L + 2) + 1
    return [
        sync_chunk(s1 + 121, s1 + 129, live_text(L + 1, 2)),
        sync_chunk(s1 + 181, s1 + 189, live_text(L + 1, 3)),
        sync_chunk(s2 + 1, s2 + 9, live_text(L + 2, 0)),
        sync_chunk(s2 + 61, s2 + 69, live_text(L + 2, 1)),
    ]


def spans(chunks):
    return {chunk['id']: (chunk['started_at'].timestamp(), chunk['finished_at'].timestamp()) for chunk in chunks}


def seeded_store(rows=None):
    store = StrictFirestore()
    for row in rows if rows is not None else [generation(k) for k in range(GENERATIONS)]:
        store.rows[('users', 'u', 'conversations', row['id'])] = deepcopy(row)
    return store


def lineage(store):
    return [deepcopy(row) for row in conversations(store) + deleted_rows(store) if row.get('external_data')]


def deleted_rows(store):
    return [value for key, value in store.rows.items() if key[2] == 'conversations' and value.get('deleted')]


def plan(store, chunks, stamp=None, **kwargs):
    return select_segment_targets(
        lineage(store),
        ORIGIN,
        spans(chunks),
        stamped_target=stamp,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        **kwargs,
    )


def replay(store, chunks, targets):
    return [intake(store, chunk, target_id=targets[chunk['id']]) for chunk in chunks]


def texts(store, cid):
    return [segment['text'] for segment in store.rows[('users', 'u', 'conversations', cid)]['transcript_segments']]


# --- Synthetic replay -------------------------------------------------------


def test_stamped_batch_straddling_generation_lands_on_its_live_row():
    store = seeded_store()
    before = {row['id'] for row in conversations(store)}
    chunks = upload_stamped_for_l()
    result = plan(store, chunks, stamp=gen_id(L))
    assert result.outcome == 'bound'
    # Speech that starts after L's last word never overlaps L, so it keeps the stamp.
    assert result.counts == {'bound': 4, 'stamp_overridden': 0, 'stamp_fallback': 2, 'unbound': 0}
    assert set(result.targets.values()) == {gen_id(L)}
    replay(store, chunks, result.targets)
    assert {row['id'] for row in conversations(store)} == before  # no sync row for live audio
    assert 'speech the live socket never received after the last line' in texts(store, gen_id(L))


def test_unstamped_batch_is_split_across_the_generations_that_own_its_audio():
    store = seeded_store()
    before = {row['id'] for row in conversations(store)}
    chunks = upload_straddling_next_two()
    result = plan(store, chunks)
    assert result.outcome == 'split_across_generations'
    assert [result.targets[chunk['id']] for chunk in chunks] == [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2
    replay(store, chunks, result.targets)
    assert {row['id'] for row in conversations(store)} == before


def test_replay_has_no_repeated_speech_when_live_and_sync_wording_match():
    store = seeded_store()
    for chunks, stamp in ((upload_stamped_for_l(), gen_id(L)), (upload_straddling_next_two(), None)):
        replay(store, chunks, plan(store, chunks, stamp=stamp).targets)
    for k in (L, L + 1, L + 2):
        assert len(texts(store, gen_id(k))) == len(set(texts(store, gen_id(k))))


def test_residual_differently_worded_overlap_still_repeats_on_the_live_row():
    """Known residual: off the exact live timestamps, dedupe needs identical normalized text."""
    store = seeded_store()
    s = gen_start(L) + 1  # one second of phone clock skew
    chunks = [
        sync_chunk(s + 1, s + 9, 'Live generation 11, line 0: about the quarterly planning review!'),
        sync_chunk(s + 61, s + 69, 'live generation eleven line one about quarterly planning reviews'),
    ]
    replay(store, chunks, plan(store, chunks, stamp=gen_id(L)).targets)
    assert len(texts(store, gen_id(L))) == 4 + 2  # both reworded repeats survive the text dedupe


def test_retry_binds_the_same_rows_and_appends_nothing_new():
    store = seeded_store()
    uploads = ((upload_stamped_for_l(), gen_id(L)), (upload_straddling_next_two(), None))
    first = [plan(store, chunks, stamp=stamp).targets for chunks, stamp in uploads]
    for (chunks, _), targets in zip(uploads, first):
        replay(store, chunks, targets)
    snapshot = deepcopy(store.rows)
    again = [plan(store, chunks, stamp=stamp).targets for chunks, stamp in uploads]
    assert again == first
    for (chunks, _), targets in zip(uploads, again):
        for _, created, survivors in replay(store, chunks, targets):
            assert not created and not survivors
    conversation_rows = lambda rows: {k: v for k, v in rows.items() if k[2] == 'conversations'}  # noqa: E731
    assert {k: v['transcript_segments'] for k, v in conversation_rows(store.rows).items()} == {
        k: v['transcript_segments'] for k, v in conversation_rows(snapshot).items()
    }


@pytest.mark.asyncio
async def test_kill_switch_off_reproduces_the_whole_batch_outcome(monkeypatch, dependencies):
    """Today's behavior: only the origin-id row is a candidate, so the batch loses its stamp."""
    pipeline = dependencies
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, 'off')
    store = seeded_store()
    candidates = [row for row in lineage(store) if row['external_data']['recording_session_id'] == ORIGIN]
    monkeypatch.setattr(recording_session_target, '_candidate_rows', lambda *_args, **_kwargs: candidates)

    async def run_inline(_executor, fn, *args):
        return fn(*args)

    monkeypatch.setattr(pipeline, 'run_blocking', run_inline)
    chunks = upload_stamped_for_l()
    start, end = chunks[0]['started_at'].timestamp() - 1, chunks[-1]['finished_at'].timestamp()
    assert not lineage_resolution_requested(ORIGIN, start, end)
    target = await pipeline._resolve_safety_wal_target(
        'u', gen_id(L), ORIGIN, pipeline.ConversationSource.omi, 'pendant', False, start, end
    )
    assert target is None
    before = {row['id'] for row in conversations(store)}
    replay(store, chunks, {chunk['id']: target for chunk in chunks})
    assert {row['id'] for row in conversations(store)} - before == {chunks[0]['id']}


def test_upload_without_recording_id_keeps_temporal_assignment():
    assert not lineage_resolution_requested(None, 1.0, 2.0)
    store = seeded_store()
    s = gen_start(L + 3)
    chunk = sync_chunk(s + 61, s + 69, 'an old client upload without recording proof')
    _, created, _ = intake(store, chunk)
    assert created  # temporal intake never adopts a live row, exactly as before


# --- Fallback and override --------------------------------------------------


def test_unique_generation_overrides_a_stale_stamp():
    store = seeded_store()
    chunks = upload_straddling_next_two()[:2]
    result = plan(store, chunks, stamp=gen_id(L))
    assert result.outcome == 'stamp_overridden'
    assert set(result.targets.values()) == {gen_id(L + 1)}


@pytest.mark.parametrize(
    ('rows', 'reason'),
    [([], 'no_rows'), ([generation(L)], 'interval_miss')],
)
def test_no_unique_generation_falls_back_to_the_stamp_or_stays_unbound(rows, reason):
    chunks = upload_straddling_next_two()
    stamped = select_segment_targets(
        rows, ORIGIN, spans(chunks), stamped_target='STAMP', source='omi', client_device_id='pendant', is_locked=False
    )
    assert stamped.outcome == 'stamp_fallback' and stamped.reason == reason
    assert set(stamped.targets.values()) == {'STAMP'}
    unstamped = select_segment_targets(
        rows, ORIGIN, spans(chunks), stamped_target=None, source='omi', client_device_id='pendant', is_locked=False
    )
    assert unstamped.outcome == reason and set(unstamped.targets.values()) == {None}


def test_adjacent_generations_inside_the_edge_allowance_are_ambiguous():
    end = gen_start(1) + DURATION
    rows = [generation(1), generation(2, started_at=at(end + 3))]
    chunk = sync_chunk(end - 1, end + 10, 'straddles the rollover')
    result = select_segment_targets(
        rows, ORIGIN, spans([chunk]), stamped_target=None, source='omi', client_device_id='pendant', is_locked=False
    )
    assert result.targets == {chunk['id']: None} and result.reason == 'interval_miss'


def test_overlapping_generations_never_pick_one():
    """A row whose interval grew over its successor (e.g. an earlier stamp append) is ambiguous."""
    rows = [generation(1, finished_at=at(gen_start(2) + DURATION)), generation(2)]
    chunk = sync_chunk(gen_start(2) + 61, gen_start(2) + 69, live_text(2, 1))
    result = select_segment_targets(
        rows, ORIGIN, spans([chunk]), stamped_target='STAMP', source='omi', client_device_id='pendant', is_locked=False
    )
    assert result.targets == {chunk['id']: 'STAMP'} and result.reason == 'interval_miss'


@pytest.mark.parametrize(
    'mutation',
    [
        {'client_device_id': 'other-phone'},
        {'source': 'phone'},
        {'is_locked': True},
        {'external_data': {'recording_session_id': 'SESSION-X', 'recording_origin_id': 'OTHER-ORIGIN'}},
    ],
)
def test_other_partitions_and_recordings_never_bind(mutation):
    chunks = upload_straddling_next_two()[:1]
    result = select_segment_targets(
        [generation(L + 1, **mutation)],
        ORIGIN,
        spans(chunks),
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert result.targets == {chunks[0]['id']: None}


def test_generation_created_before_the_origin_stamp_binds_through_the_origin_row():
    legacy = generation(0, external_data={'recording_session_id': ORIGIN})
    chunk = sync_chunk(gen_start(0) + 61, gen_start(0) + 69, live_text(0, 1))
    result = select_segment_targets(
        [legacy], ORIGIN, spans([chunk]), stamped_target=None, source='omi', client_device_id='pendant', is_locked=False
    )
    assert result.targets == {chunk['id']: ORIGIN}


# --- Tombstones and user-managed live rows ----------------------------------


def smart_merged(store, survivor_k, donor_k):
    survivor = store.rows[('users', 'u', 'conversations', gen_id(survivor_k))]
    donor = store.rows[('users', 'u', 'conversations', gen_id(donor_k))]
    survivor.update(
        finished_at=donor['finished_at'],
        sync_content_revision=1,
        smart_merge={'role': 'survivor'},
        transcript_segments=survivor['transcript_segments']
        + [
            dict(segment, start=segment['start'] + PERIOD * (donor_k - survivor_k))
            for segment in donor['transcript_segments']
        ],
    )
    donor.update(deleted=True, discarded=True, sync_merged_into=gen_id(survivor_k), smart_merge={'role': 'donor'})


def test_donor_generation_resolves_to_its_survivor():
    store = seeded_store()
    smart_merged(store, L + 1, L + 2)
    chunks = upload_straddling_next_two()
    result = plan(store, chunks)
    assert result.outcome == 'bound'  # both generations are one conversation now
    assert set(result.targets.values()) == {gen_id(L + 1)}
    before = {row['id'] for row in conversations(store)}
    replay(store, chunks, result.targets)
    assert {row['id'] for row in conversations(store)} == before


def test_donor_whose_survivor_is_outside_the_lineage_redirects_in_intake():
    store = seeded_store()
    smart_merged(store, L + 1, L + 2)
    survivor_key = ('users', 'u', 'conversations', gen_id(L + 1))
    store.rows[survivor_key]['external_data'] = {'recording_session_id': 'OTHER', 'recording_origin_id': 'OTHER'}
    s = gen_start(L + 2)
    chunks = [sync_chunk(s + 100, s + 110, 'late repair audio for the folded generation')]
    result = plan(store, chunks)
    assert set(result.targets.values()) == {gen_id(L + 2)}  # the donor; intake follows its redirect
    replay(store, chunks, result.targets)
    assert 'late repair audio for the folded generation' in texts(store, gen_id(L + 1))


def test_deleted_survivor_supersedes_the_audio_instead_of_recreating_a_row():
    store = seeded_store()
    smart_merged(store, L + 1, L + 2)
    del store.rows[('users', 'u', 'conversations', gen_id(L + 1))]
    chunks = upload_straddling_next_two()[2:]
    result = plan(store, chunks)
    assert set(result.targets.values()) == {gen_id(L + 2)}
    before = {row['id'] for row in conversations(store)}
    with pytest.raises(SyncAssignmentSuperseded):
        intake(store, chunks[0], target_id=result.targets[chunks[0]['id']])
    assert {row['id'] for row in conversations(store)} == before


@pytest.mark.parametrize(
    'managed',
    [{'starred': True}, {'user_title': 'Planning'}, {'has_photos': True}, {'visibility': 'shared'}],
)
def test_user_managed_live_generation_keeps_its_identity_and_markers(managed):
    store = seeded_store([generation(L + 1, **managed)])
    chunks = upload_straddling_next_two()[:2]
    replay(store, chunks, plan(store, chunks).targets)
    row = store.rows[('users', 'u', 'conversations', gen_id(L + 1))]
    assert {row['id'] for row in conversations(store)} == {gen_id(L + 1)}
    assert all(row[key] == value for key, value in managed.items())


# --- Lookup, truncation, fail-open, telemetry --------------------------------


class _LineageDb:
    """In-memory stand-in for database.sync_recording_lineage with the real query semantics."""

    def __init__(self, rows, *, fail=False):
        self.rows = rows
        self.fail = fail
        self.calls = []

    def get_recording_generations(self, uid, origin_id, *, started_before, limit, firestore_client=None):
        self.calls.append('generations')
        if self.fail:
            raise TimeoutError('deadline')
        matching = [
            row
            for row in self.rows
            if (row.get('external_data') or {}).get('recording_origin_id') == origin_id
            and row['started_at'] <= started_before
        ]
        matching.sort(key=lambda row: (row['started_at'], row['id']), reverse=True)
        return deepcopy(matching[: limit + 1])

    def get_origin_generation(self, uid, origin_id, *, limit, firestore_client=None):
        self.calls.append('origin')
        matching = [
            row for row in self.rows if (row.get('external_data') or {}).get('recording_session_id') == origin_id
        ]
        return deepcopy(matching[: limit + 1])


@pytest.fixture
def lineage_db(monkeypatch):
    from database import sync_recording_lineage

    fake = _LineageDb([generation(k) for k in range(GENERATIONS)])
    for name in ('get_recording_generations', 'get_origin_generation'):
        monkeypatch.setattr(sync_recording_lineage, name, getattr(fake, name))
    return fake


def resolve(chunks, stamp=None):
    return resolve_segment_targets(
        'u',
        ORIGIN,
        spans(chunks),
        stamped_target=stamp,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        job_id='00000000-0000-4000-8000-000000000000',
    )


def test_long_recording_reads_one_bounded_window(lineage_db):
    chunks = upload_straddling_next_two()
    targets = resolve(chunks)
    assert [targets[chunk['id']] for chunk in chunks] == [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2
    assert lineage_db.calls == ['generations']  # the origin row is older than the window


def test_audio_older_than_the_read_window_is_not_guessed(lineage_db):
    old = sync_chunk(gen_start(2) + 61, gen_start(2) + 69, live_text(2, 1))
    new = upload_straddling_next_two()[0]
    targets = resolve([old, new], stamp='STAMP')
    assert targets == {old['id']: 'STAMP', new['id']: gen_id(L + 1)}


def test_recording_from_before_the_origin_stamp_reads_the_origin_row(lineage_db):
    lineage_db.rows = [generation(0, external_data={'recording_session_id': ORIGIN}), generation(1, external_data={})]
    chunk = sync_chunk(gen_start(0) + 61, gen_start(0) + 69, live_text(0, 1))
    assert resolve([chunk]) == {chunk['id']: ORIGIN}
    assert lineage_db.calls == ['generations', 'origin']


def test_lookup_failure_fails_open_to_the_stamp(lineage_db, monkeypatch, caplog):
    lineage_db.fail = True
    fallback = MagicMock()
    monkeypatch.setattr(recording_lineage, 'record_fallback', fallback)
    chunks = upload_straddling_next_two()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        assert set(resolve(chunks, stamp='STAMP').values()) == {'STAMP'}
        assert set(resolve(chunks).values()) == {None}
    assert fallback.call_count == 2
    assert 'event=sync_lineage_resolve outcome=lookup_failed' in caplog.text


def test_planning_error_fails_open_and_never_raises(lineage_db, monkeypatch):
    def boom(*_args, **_kwargs):
        raise KeyError('bad row')

    monkeypatch.setattr(recording_lineage, 'select_segment_targets', boom)
    chunks = upload_straddling_next_two()
    assert set(resolve(chunks, stamp='STAMP').values()) == {'STAMP'}


def test_decision_log_is_bounded_and_carries_no_ids(lineage_db, caplog):
    chunks = upload_straddling_next_two()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        resolve(chunks, stamp=gen_id(L))
    lines = [record.getMessage() for record in caplog.records if 'event=sync_lineage_resolve' in record.getMessage()]
    assert len(lines) == 1
    assert 'outcome=split_across_generations reason=none segments=4 bound=0 stamp_overridden=4' in lines[0]
    for forbidden in (ORIGIN, 'LIVE-', 'SYNC-', ' u ', 'quarterly'):
        assert forbidden not in lines[0]


class _FakeQuery:
    def __init__(self, docs):
        self.docs = docs
        self.ops = []

    def collection(self, name):
        self.ops.append(('collection', name))
        return self

    def document(self, name):
        self.ops.append(('document', name))
        return self

    def where(self, *, filter):
        self.ops.append(('where', filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field_path, direction):
        self.ops.append(('order_by', field_path, direction))
        return self

    def select(self, field_paths):
        self.ops.append(('select', tuple(field_paths)))
        return self

    def limit(self, count):
        self.ops.append(('limit', count))
        return self

    def stream(self):
        return iter(self.docs)


def test_lineage_reads_are_bounded_indexed_and_transcript_free(monkeypatch):
    from database import sync_recording_lineage as lineage_db

    reads = []
    monkeypatch.setattr(lineage_db, 'record_firestore_read', lambda *args: reads.append(args))
    doc = SimpleNamespace(id='LIVE-01', to_dict=lambda: {'started_at': at(T0)})
    before = at(T0 + 600)
    query = _FakeQuery([doc])
    rows = lineage_db.get_recording_generations('u', ORIGIN, started_before=before, limit=8, firestore_client=query)
    assert rows == [{'started_at': at(T0), 'id': 'LIVE-01'}]
    assert query.ops[:3] == [('collection', 'users'), ('document', 'u'), ('collection', 'conversations')]
    assert query.ops[3:6] == [
        ('where', 'external_data.recording_origin_id', '==', ORIGIN),
        ('where', 'started_at', '<=', before),
        ('order_by', 'started_at', 'DESCENDING'),
    ]
    selected = query.ops[6][1]
    assert query.ops[7] == ('limit', 9)
    assert not any(field.startswith(('transcript', 'photos', 'structured')) for field in selected)
    origin = _FakeQuery([])
    assert lineage_db.get_origin_generation('u', ORIGIN, limit=5, firestore_client=origin) == []
    assert ('where', 'external_data.recording_session_id', '==', ORIGIN) in origin.ops and ('limit', 6) in origin.ops
    assert [(family.value, mode.value, count) for family, mode, count in reads] == [
        ('sync_recording_lineage', 'bounded', 1),
        ('sync_recording_lineage', 'bounded', 0),
    ]


# --- Kill switch --------------------------------------------------------------


@pytest.mark.parametrize(('value', 'enabled'), [('', True), ('true', True), ('on', True), ('1', True)])
def test_unset_or_on_values_keep_the_feature_on(monkeypatch, value, enabled):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, value)
    assert sync_lineage.sync_lineage_resolve_enabled() is enabled


@pytest.mark.parametrize('value', ['off', 'false', '0', 'no', 'of', 'disabled-typo'])
def test_off_and_unrecognized_values_disable_it(monkeypatch, value, caplog):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, value)
    assert not sync_lineage.sync_lineage_resolve_enabled()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        assert not lineage_resolution_requested(ORIGIN, 1.0, 2.0)
    assert 'event=sync_lineage_resolve outcome=disabled' in caplog.text


# --- Coordinator call site ----------------------------------------------------


@pytest.fixture
def coordinator():
    """The routers.sync behavioral harness; import-heavy, so built outside the call budget."""
    module, stubs = sync_v2_harness.TestAsyncCoordinatorBehavioral._load_sync_module()
    try:
        yield module, stubs
    finally:
        sync_v2_harness.TestAsyncCoordinatorBehavioral._cleanup(stubs['saved_modules'])


def _drive(module, stubs, chunks, monkeypatch, *, stamp):
    pipeline = stubs['pipeline']
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
        captured[paths[path]['id']] = target
        response['updated_memories'].add(target or 'sync-row')
        return True

    pipeline.process_segment = capture
    monkeypatch.setattr(
        sys.modules[pipeline.resolve_segment_targets.__module__],
        '_load_lineage',
        lambda *_args: ([generation(k) for k in range(GENERATIONS)], None),
    )
    candidates = [generation(0)]
    monkeypatch.setattr(
        sys.modules[pipeline.resolve_recording_session_sync_target.__module__],
        '_candidate_rows',
        lambda *_args, **_kwargs: candidates,
    )
    return captured, SimpleNamespace(
        target_conversation_id=stamp,
        client_device_id='pendant',
        recording_session_id=ORIGIN,
        audio_start_seconds=chunks[0]['started_at'].timestamp() - 8,
        audio_end_seconds=chunks[-1]['finished_at'].timestamp(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('flag', ['', 'off'])
async def test_coordinator_forwards_each_segment_its_generation(coordinator, monkeypatch, flag):
    module, stubs = coordinator
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    chunks = upload_straddling_next_two()
    captured, kwargs = _drive(module, stubs, chunks, monkeypatch, stamp=gen_id(L))
    await module._run_full_pipeline_background_async(
        'job-lineage', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-lineage', **vars(kwargs)
    )
    expected = [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2 if flag == '' else [None] * 4
    assert [captured[chunk['id']] for chunk in chunks] == expected


# --- Live origin stamp ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize('flag', ['', 'off'])
async def test_every_live_generation_names_its_origin_recording(monkeypatch, flag):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    harness = continuity.CaptureHarness(monkeypatch)
    first = harness.connect(client_id='fresh')
    await first.prepare()
    assert first.host.state.current_conversation_id == 'fresh'
    harness.now = harness.rows['original']['finished_at'] + timedelta(seconds=300)
    rollover = harness.connect()
    await rollover.prepare()
    generation_id = rollover.host.state.current_conversation_id
    assert generation_id != 'original'
    assert harness.rows[generation_id]['external_data']['recording_session_id'] != 'original'
    origins = [harness.rows[cid]['external_data'].get('recording_origin_id') for cid in ('fresh', generation_id)]
    assert origins == (['fresh', 'original'] if flag == '' else [None, None])
