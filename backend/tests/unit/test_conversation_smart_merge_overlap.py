"""Overlap-aware predecessor selection (CONVERSATION_SMART_MERGE_OVERLAP_PREDECESSOR_ENABLED).

With the flag on, a proven sync-created duplicate that overlaps (or sits within
the split window of) a live new conversation stops pretending to be its
predecessor: the selection walks the same six-row window in the same order,
skips up to three such rows, and lets everything else block exactly as before.
Flag off keeps byte-identical behavior. All text is synthetic.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import conversation_smart_merge as config
from config.jev_decisions import JEV_MODEL
from database import conversations as conversations_db
from database import smart_merge as smart_merge_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from tests.unit.test_conversation_smart_merge import T0, UID, World
from utils import metrics
from utils.conversations import smart_merge
from utils.conversations import smart_merge_policy as policy
from utils.conversations.smart_merge_state import Fragment, state_sha256

OVERLAP_ENV = 'CONVERSATION_SMART_MERGE_OVERLAP_PREDECESSOR_ENABLED'


def _project(row, fields):
    out = {}
    for path in fields:
        keys = path.split('.')
        value = row
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                break
            value = value[key]
        else:
            target = out
            for key in keys[:-1]:
                target = target.setdefault(key, {})
            target[keys[-1]] = value
    return out


class OverlapWorld(World):
    def __init__(self, monkeypatch):
        super().__init__(monkeypatch)
        self.lookup_calls = []
        inner = self.preceding

        def lookup(uid, **kwargs):
            self.lookup_calls.append(dict(kwargs))
            include_capture_metadata = kwargs.pop('include_capture_metadata', False)
            rows = inner(uid, **kwargs)
            fields = tuple(config.PRECEDING_METADATA_FIELDS)
            if include_capture_metadata:
                fields += tuple(config.OVERLAP_CAPTURE_FIELDS)
            return [_project(row, fields) for row in rows]

        monkeypatch.setattr(smart_merge_db, 'find_preceding_conversations', lookup)

    def overlap_metrics(self):
        self.overlap_calls = []
        self.monkeypatch.setattr(
            metrics.OMI_CONVERSATION_SMART_MERGE_PREDECESSOR_OVERLAP_TOTAL,
            'labels',
            lambda **labels: SimpleNamespace(inc=lambda: self.overlap_calls.append(labels)),
        )

    def decision_metrics(self):
        self.decision_calls = []
        self.monkeypatch.setattr(
            smart_merge, 'record_conversation_smart_merge', lambda **kw: self.decision_calls.append(kw)
        )
        self.audit_calls = []
        self.monkeypatch.setattr(
            smart_merge, 'record_conversation_smart_merge_audit', lambda *a: self.audit_calls.append(a)
        )

    def set_segments(self, cid, segments):
        row = self.get(UID, cid)
        row['transcript_segments'] = segments
        self.store.rows[('users', UID, 'conversations', cid)] = conversations_db.encode_conversation_for_write(
            UID, row, 'enhanced'
        )


def _segments(cid, minutes):
    seconds = minutes * 60.0
    return [
        {
            'id': f'{cid}-s{i}',
            'text': f"{' '.join(['synthetic'] * 30)} {cid} {i}",
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': i == 0,
            'start': start,
            'end': start + 5.0,
        }
        for i, start in enumerate((0.0, seconds - 5.0))
    ]


def _sync(world, cid, start_min, end_min, **extra):
    return world.add(cid, start_min, end_min - start_min, sync_content_revision=2, sync_live_target=False, **extra)


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv(OVERLAP_ENV, 'on')
    return OverlapWorld(monkeypatch)


@pytest.fixture
def world_off(monkeypatch):
    monkeypatch.delenv(OVERLAP_ENV, raising=False)
    return OverlapWorld(monkeypatch)


@pytest.mark.parametrize('raw', ['true', ' ON ', '1', 'yes'])
def test_overlap_flag_on_values(monkeypatch, raw):
    monkeypatch.setenv(config.SMART_MERGE_OVERLAP_ENV, raw)
    assert config.smart_merge_overlap_predecessor_enabled() is True


@pytest.mark.parametrize('raw', ['', '   ', 'off', 'false', 'merge', 'bogus', '0'])
def test_overlap_flag_is_default_off_and_fail_closed(monkeypatch, raw):
    monkeypatch.setenv(config.SMART_MERGE_OVERLAP_ENV, raw)
    assert config.smart_merge_overlap_predecessor_enabled() is False
    monkeypatch.delenv(config.SMART_MERGE_OVERLAP_ENV, raising=False)
    assert config.smart_merge_overlap_predecessor_enabled() is False


def test_projection_constants_match_the_lookup_tuple():
    assert tuple(smart_merge_db._PRECEDING_FIELDS) == tuple(config.PRECEDING_METADATA_FIELDS)
    assert config.OVERLAP_CAPTURE_FIELDS == (
        'sync_content_revision',
        'sync_live_target',
        'manual_speaker_assignments',
    )
    assert set(config.OVERLAP_CAPTURE_FIELDS).isdisjoint(config.PRECEDING_METADATA_FIELDS)


class _Query:
    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        def step(*args, **kwargs):
            self.log.append((name, args, kwargs))
            return self

        return step

    def stream(self):
        return iter([])


def test_lookup_appends_exactly_the_capture_fields_only_when_enabled():
    log = []
    client = SimpleNamespace(collection=lambda name: _Query(log))
    smart_merge_db.find_preceding_conversations(UID, source='omi', created_before=T0, limit=6, firestore_client=client)
    baseline = next(args[0] for name, args, _ in log if name == 'select')
    assert baseline == list(config.PRECEDING_METADATA_FIELDS)

    log.clear()
    smart_merge_db.find_preceding_conversations(
        UID, source='omi', created_before=T0, limit=6, include_capture_metadata=True, firestore_client=client
    )
    extended = next(args[0] for name, args, _ in log if name == 'select')
    assert extended[: len(baseline)] == baseline
    assert extended[len(baseline) :] == ['sync_content_revision', 'sync_live_target', 'manual_speaker_assignments']


def test_off_lookup_rows_carry_no_capture_evidence(world_off):
    world_off.add('p', 0, 5)
    _sync(world_off, 'p2', 7, 16)
    world_off.add('n', 10, 15)
    seen = []
    real = smart_merge.select_predecessor
    world_off.monkeypatch.setattr(
        smart_merge, 'select_predecessor', lambda new, rows, **kw: seen.append(rows) or real(new, rows, **kw)
    )
    assert world_off.finish('n') is False
    assert seen and all(
        'sync_content_revision' not in row and 'manual_speaker_assignments' not in row for row in seen[0]
    )


def test_sync_duplicate_overlapping_a_live_capture_is_skipped(world):
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    untouched_p2 = deepcopy(world.raw('p2'))

    assert world.finish('n') is True

    donor = world.raw('n')
    assert donor['sync_merged_into'] == 'p' and donor['deleted'] is True
    assert world.raw('n')['smart_merge_decision']['candidate_id'] == 'p'
    assert world.raw('n')['smart_merge_decision']['predecessor_skipped_overlap'] == 1
    assert world.raw('p2') == untouched_p2
    assert world.get(UID, 'p')['sync_merged_from'] == ['n']


def test_under_window_nonoverlap_sync_row_is_skipped(world):
    world.add('p', 0, 5)
    _sync(world, 'p2', 2, 9)
    world.add('n', 10, 15)
    p2 = world.raw('p2')
    assert p2['finished_at'] == T0 + timedelta(minutes=9)
    assert (world.raw('n')['started_at'] - p2['finished_at']).total_seconds() == 60.0
    world.jev_answers = [0.5]
    assert world.finish('n') is True
    assert world.raw('n')['smart_merge_decision']['candidate_id'] == 'p'


def test_stretch_ignores_the_skipped_duplicate(world):
    world.add('old', -10, 5)
    world.add('p', 0, 5)
    _sync(world, 'p2', -1, 16, created_at=T0 + timedelta(minutes=7))
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    untouched_p2 = deepcopy(world.raw('p2'))
    assert world.finish('n') is True
    record = world.raw('n')['smart_merge_decision']
    assert record['candidate_id'] == 'p' and record['stretch_count'] == 1
    state = world.jev_calls[0]['state']
    assert 'title old' in state and 'title p2' not in state
    assert world.raw('p2') == untouched_p2


@pytest.mark.parametrize('answer,decision', [(0.34, 'kept'), (0.35, 'merged'), (None, 'kept')])
def test_jev_outcomes_follow_the_chosen_row_not_the_skipped_one(world, answer, decision):
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    world.jev_answers = [answer]
    assert world.finish('n') is (decision == 'merged')
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == decision and record['candidate_id'] == 'p'
    assert (world.raw('n').get('deleted') is True) is (decision == 'merged')


def _barrier_keeps(world):
    world.add('p', 0, 5)
    world.add('n', 10, 15)
    assert world.finish('n') is False
    assert world.jev_calls == []
    assert not world.raw('n').get('deleted') and 'smart_merge' not in world.raw('p')


def test_live_overlap_row_is_a_barrier_not_a_skip(world):
    world.add('p2', 7, 9)
    _barrier_keeps(world)


def test_explicit_live_target_enrichment_is_a_barrier(world):
    world.add('p2', 7, 9, sync_content_revision=2, sync_live_target=True)
    _barrier_keeps(world)


@pytest.mark.parametrize(
    'extra',
    [
        {},
        {'sync_content_revision': 'bogus'},
        {'sync_content_revision': True},
        {'sync_content_revision': 0},
        {'sync_content_revision': -1},
        {'sync_content_revision': 2},
        {'sync_content_revision': 2, 'sync_live_target': None},
        {'sync_content_revision': 2, 'sync_live_target': False, 'manual_speaker_assignments': {'0': 'self'}},
    ],
    ids=[
        'absent',
        'malformed',
        'bool',
        'zero',
        'negative',
        'target_unset',
        'target_null',
        'manual_speaker',
    ],
)
def test_unproven_or_curated_capture_evidence_never_skips(world, extra):
    world.add('p2', 7, 9, **extra)
    _barrier_keeps(world)


def test_smart_merge_state_row_never_skips(world):
    world.add(
        'p2',
        7,
        9,
        sync_content_revision=2,
        sync_live_target=False,
        smart_merge={'role': 'survivor', 'revision': 1, 'refreshed_revision': 1},
    )
    _barrier_keeps(world)


@pytest.mark.parametrize(
    'extra',
    [
        {'sync_content_revision': True},
        {'sync_content_revision': 'bad'},
        {'sync_content_revision': '0'},
        {'sync_content_revision': 0.5},
        {'sync_content_revision': -1},
        {'sync_live_target': 'false'},
    ],
    ids=['bool', 'malformed', 'string_zero', 'float', 'negative', 'malformed_target'],
)
def test_sync_new_conversation_evidence_never_skips(world, extra):
    _sync(world, 'p2', 7, 16)
    world.add('p', 0, 5)
    world.add('n', 10, 15, **extra)
    assert world.finish('n') is False
    assert world.jev_calls == []


@pytest.mark.parametrize('revision', [0, None])
def test_live_new_row_with_missing_or_zero_revision_still_skips(world, revision):
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15, sync_content_revision=revision)
    world.jev_answers = [0.5]
    assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'


def test_sync_new_row_with_explicit_live_target_still_skips(world):
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15, sync_content_revision=4, sync_live_target=True)
    world.jev_answers = [0.5]
    assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'


def test_different_device_rows_are_ignored_and_never_merge_across_partitions(world):
    _sync(world, 'p2', 7, 16, client_device_id='pendant-2')
    world.add('p', 0, 5)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'
    record = world.raw('n')['smart_merge_decision']
    assert 'predecessor_skipped_overlap' not in record


def test_only_the_matching_partition_can_block(world):
    _sync(world, 'p2', 7, 16, client_device_id='pendant-2')
    world.add('n', 10, 15)
    assert world.finish('n') is False
    assert world.jev_calls == []


@pytest.mark.parametrize(
    'extra',
    [
        {'status': 'processing'},
        {'relevance_decision': {'trigger': 'client_finalize'}},
        {'starred': True},
        {'smart_merge': {'role': 'survivor', 'revision': 2, 'refreshed_revision': 1}},
    ],
    ids=['busy', 'user_ended', 'user_managed', 'refresh_debt'],
)
def test_ineligible_sync_rows_are_barriers_not_skips(world, extra):
    _sync(world, 'p2', 7, 16, **extra)
    _barrier_keeps(world)


def _skip_then_gate(world, expected_reason, caplog, p_extra=None, setup=None):
    world.add('p', 0, 5, **(p_extra or {}))
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    if setup:
        setup()
    with caplog.at_level('INFO'):
        assert world.finish('n') is False
    assert world.jev_calls == []
    assert not world.raw('n').get('deleted')
    assert 'smart_merge_decision' not in world.raw('n')
    assert any(
        f'reason={expected_reason}' in line and 'predecessor_skipped_overlap=1' in line for line in caplog.messages
    )


@pytest.mark.parametrize(
    'p_extra,reason',
    [
        ({'uses_custom_stt': True}, 'refresh_unavailable'),
        ({'manual_speaker_assignments': {'0': 'self'}}, 'user_managed'),
        ({'relevance_decision': {'trigger': 'client_finalize'}}, 'predecessor_user_ended'),
        ({'status': 'failed'}, 'predecessor_not_completed'),
    ],
)
def test_metadata_gates_apply_after_a_skip(world, caplog, p_extra, reason):
    _skip_then_gate(world, reason, caplog, p_extra=p_extra)


def test_owed_refresh_gate_applies_after_a_skip(world, caplog, monkeypatch):
    monkeypatch.setattr(
        smart_merge,
        'refresh_survivor',
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('refresh down')),
    )
    _skip_then_gate(
        world,
        'predecessor_refresh_pending',
        caplog,
        p_extra={'smart_merge': {'role': 'survivor', 'revision': 2, 'refreshed_revision': 1}},
    )


def test_wake_word_gate_applies_after_a_skip(world, caplog):
    def setup():
        segments = world.get(UID, 'p')['transcript_segments']
        segments = [dict(segments[0], text='hey omi what is on my calendar')] + segments
        world.set_segments('p', segments)

    _skip_then_gate(world, 'wake_word', caplog, setup=setup)


def test_long_wall_gap_gate_applies_after_a_skip(world, caplog):
    world.add('p', -80, 10)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    with caplog.at_level('INFO'):
        assert world.finish('n') is False
    assert world.jev_calls == []
    assert any('reason=gap_out_of_window' in line for line in caplog.messages)


def test_short_speech_gap_gate_applies_after_a_skip(world, caplog):
    def setup():
        segments = world.get(UID, 'p')['transcript_segments']
        segments = segments + [dict(segments[-1], id='p-late', start=590.0, end=595.0)]
        world.set_segments('p', segments)

    _skip_then_gate(world, 'gap_out_of_window', caplog, setup=setup)


@pytest.mark.parametrize('cid', ['p', 'n'])
def test_too_few_words_gate_applies_after_a_skip(world, caplog, cid):
    def setup():
        world.set_segments(
            cid,
            [
                {
                    'id': f'{cid}-short',
                    'text': 'few words',
                    'speaker': 'SPEAKER_00',
                    'speaker_id': 0,
                    'is_user': False,
                    'start': 0.0,
                    'end': 5.0,
                }
            ],
        )

    _skip_then_gate(world, 'too_few_words', caplog, setup=setup)


def test_span_cap_gate_applies_after_a_skip(world, caplog):
    world.add('p', -181, 186)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    with caplog.at_level('INFO'):
        assert world.finish('n') is False
    assert world.jev_calls == []
    assert any('reason=span_cap' in line and 'predecessor_skipped_overlap=1' in line for line in caplog.messages)


def test_segment_cap_gate_applies_after_a_skip(world, caplog, monkeypatch):
    monkeypatch.setattr(policy, 'MAX_MERGED_SEGMENTS', 3)
    _skip_then_gate(world, 'segment_cap', caplog)


def test_fragment_cap_gate_applies_after_a_skip(world, caplog, monkeypatch):
    monkeypatch.setattr(policy, 'MAX_FRAGMENTS', 2)
    fragments = [
        Fragment(id='f0', started_at=T0, finished_at=T0 + timedelta(minutes=2), title='t', overview='o'),
        Fragment(
            id='p', started_at=T0 + timedelta(minutes=3), finished_at=T0 + timedelta(minutes=5), title='t', overview='o'
        ),
    ]
    _skip_then_gate(
        world,
        'fragment_cap',
        caplog,
        p_extra={
            'smart_merge': {
                'role': 'survivor',
                'revision': 1,
                'refreshed_revision': 1,
                'fragments': [f.as_ledger_entry() for f in fragments],
            }
        },
    )


def test_failing_gate_does_not_hunt_for_an_earlier_row(world):
    world.add('old', -30, 10)
    _sync(world, 'p', 0, 5, starred=True)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    assert world.finish('n') is False
    assert world.jev_calls == []


def test_three_skips_reach_the_real_predecessor(world, caplog):
    world.add('p', 0, 5)
    _sync(world, 's1', 6, 9)
    _sync(world, 's2', 7, 10)
    _sync(world, 's3', 8, 14)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    with caplog.at_level('INFO'):
        assert world.finish('n') is True
    assert world.raw('n')['sync_merged_into'] == 'p'
    assert world.raw('n')['smart_merge_decision']['predecessor_skipped_overlap'] == 3
    assert any('decision=merged' in line and 'predecessor_skipped_overlap=3' in line for line in caplog.messages)


def test_the_fourth_overlapping_row_is_a_barrier(world):
    world.add('p', 0, 5)
    _sync(world, 's1', 6, 9)
    _sync(world, 's2', 7, 10)
    _sync(world, 's3', 8, 14)
    _sync(world, 's4', 9, 17)
    world.add('n', 10, 15)
    assert world.finish('n') is False
    assert world.jev_calls == [] and 'smart_merge_decision' not in world.raw('n')


def test_six_row_window_exhaustion_records_the_skips(world, caplog):
    world.add('p', -30, 10)
    for index in range(3):
        _sync(world, f's{index}', 6 + index, 10 + index)
    for index in range(3):
        world.add(f'other{index}', 6 + index, 4, client_device_id='pendant-2')
    world.add('n', 10, 15)
    with caplog.at_level('INFO'):
        assert world.finish('n') is False
    assert world.jev_calls == []
    assert any('reason=no_predecessor' in line and 'predecessor_skipped_overlap=3' in line for line in caplog.messages)


def test_a_concurrent_edit_of_the_chosen_row_still_rejects(world):
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    world.on_ask = lambda: world.raw('p').update(starred=True)
    assert world.finish('n') is False
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'user_managed'
    assert record['predecessor_skipped_overlap'] == 1
    assert not world.raw('n').get('deleted')


_CURATIONS = [
    {'starred': True},
    {'manual_speaker_assignments': {'0': 'self'}},
    {'status': 'processing'},
    {'sync_live_target': True},
    {'source': 'desktop'},
    {'client_device_id': 'pendant-2'},
    {'is_locked': True},
    {'finished_at': T0 + timedelta(minutes=7)},
    {'smart_merge': {'role': 'survivor', 'revision': 2, 'refreshed_revision': 1}},
]


@pytest.mark.parametrize(
    'mutation',
    _CURATIONS,
    ids=[next(iter(m)) for m in _CURATIONS],
)
def test_a_concurrent_change_of_the_skipped_row_rejects(world, mutation):
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    world.on_ask = lambda: world.raw('p2').update(mutation)
    assert world.finish('n') is False
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'survivor_changed'
    assert record['predecessor_skipped_overlap'] == 1
    assert not world.raw('n').get('deleted')
    assert 'smart_merge' not in world.raw('p')
    for key, value in mutation.items():
        assert world.raw('p2')[key] == value


def test_a_concurrent_delete_of_the_skipped_row_rejects(world):
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    world.on_ask = lambda: world.store.rows.pop(('users', UID, 'conversations', 'p2'))
    assert world.finish('n') is False
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'survivor_changed'
    assert record['predecessor_skipped_overlap'] == 1
    assert not world.raw('n').get('deleted')
    assert 'smart_merge' not in world.raw('p')
    assert world.raw('p2') is None


def test_each_skipped_row_is_rechecked_inside_the_transaction(world, monkeypatch):
    world.add('p', 0, 5)
    for index in range(3):
        _sync(world, f's{index}', 6 + index, 10 + index)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    untouched = {sid: deepcopy(world.raw(sid)) for sid in ('s0', 's1', 's2')}
    reads = []
    real_get = StrictFirestoreDocument.get

    def spy(ref, transaction=None, **kwargs):
        if transaction is not None:
            reads.append(ref.path)
        return real_get(ref, transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', spy)
    assert world.finish('n') is True
    for sid in ('s0', 's1', 's2'):
        assert reads.count(('users', UID, 'conversations', sid)) == 1
        assert world.raw(sid) == untouched[sid]
    assert world.raw('n')['smart_merge_decision']['predecessor_skipped_overlap'] == 3


def test_no_skip_passes_no_skipped_guard_kwargs(world):
    calls = []
    real = smart_merge_db.absorb_conversation
    world.monkeypatch.setattr(
        smart_merge_db, 'absorb_conversation', lambda *a, **kw: calls.append(kw) or real(*a, **kw)
    )
    world.add('p', 0, 5)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    assert world.finish('n') is True
    assert len(calls) == 1
    assert 'skipped_predecessor_ids' not in calls[0] and 'predecessor_skip_check' not in calls[0]


def _always_skippable(candidate, new):
    return True


@pytest.mark.parametrize(
    'skipped,checker',
    [
        (('a', 'b', 'c', 'd'), _always_skippable),
        (('x', 'x'), _always_skippable),
        (('n',), _always_skippable),
        (('p',), _always_skippable),
        (('x',), None),
    ],
    ids=['over_max', 'duplicate', 'donor_id', 'survivor_id', 'no_checker'],
)
def test_absorb_rejects_malformed_skipped_lists_without_running_the_plan(world, skipped, checker):
    world.add('p', 0, 5)
    world.add('n', 10, 15)
    before = deepcopy(world.store.rows)
    result = smart_merge_db.absorb_conversation(
        UID,
        'p',
        'n',
        expected_revision=0,
        plan=lambda *a: pytest.fail('plan executed'),
        skipped_predecessor_ids=skipped,
        predecessor_skip_check=checker,
        firestore_client=world.store,
    )
    assert (result.outcome, result.reason) == ('rejected', 'survivor_changed')
    assert world.store.rows == before


@pytest.mark.parametrize('skipped,label', [(1, '1'), (2, '2'), (3, '3'), (4, 'other'), (17, 'other')])
def test_overlap_metric_is_bounded(monkeypatch, skipped, label):
    seen = []
    monkeypatch.setattr(
        metrics.OMI_CONVERSATION_SMART_MERGE_PREDECESSOR_OVERLAP_TOTAL,
        'labels',
        lambda **kw: SimpleNamespace(inc=lambda: seen.append(kw)),
    )
    metrics.record_conversation_smart_merge_predecessor_overlap(mode='merge', skipped=skipped)
    assert seen == [{'mode': 'merge', 'skipped': label}]


def test_overlap_metric_counts_each_selection_once(world):
    world.overlap_metrics()
    world.add('p', 0, 5)
    _sync(world, 'p2', 7, 16)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    assert world.finish('n') is True
    assert world.overlap_calls == [{'mode': 'merge', 'skipped': '1'}]


def test_no_skip_means_no_metric_and_no_log_suffix(world, caplog):
    world.overlap_metrics()
    world.add('p', 0, 5)
    world.add('n', 10, 15)
    world.jev_answers = [0.5]
    with caplog.at_level('INFO'):
        assert world.finish('n') is True
    assert world.overlap_calls == []
    merged = next(line for line in caplog.messages if 'decision=merged' in line)
    assert 'predecessor_skipped_overlap' not in merged
    assert 'predecessor_skipped_overlap' not in world.raw('n')['smart_merge_decision']


_FROZEN = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenMeta(type):
    def __instancecheck__(cls, other):
        return isinstance(other, datetime)

    def __subclasscheck__(cls, other):
        return issubclass(other, datetime)


class _FrozenDateTime(metaclass=_FrozenMeta):
    now = classmethod(lambda cls, tz=None: _FROZEN if tz is None else _FROZEN.astimezone(tz))


_BASELINE_MERGE_RECORD = {
    'version': 1,
    'mode': 'merge',
    'decision': 'merged',
    'reason': 'jev_same',
    'decided_by': 'jev',
    'p_same': 0.5,
    'threshold': 0.35,
    'model': JEV_MODEL,
    'question_version': 'adjacent_merge_a_iv1',
    'candidate_id': 'p',
    'gap_seconds': 300.0,
    'speech_gap_seconds': 300.0,
    'stretch_count': 0,
    'state_sha256': '0c8e1904d629fb7b57f3ff0e57cd62711dfe9754822528d21dedc9f429396622',
    'decided_at': _FROZEN,
}
_BASELINE_MERGE_METRICS = [
    {'mode': 'merge', 'decision': 'merge', 'reason': 'absorbed', 'gap_seconds': 300.0, 'p_same': 0.5}
]
_BASELINE_OVERLAP_METRICS = [
    {'mode': 'merge', 'decision': 'skip', 'reason': 'gap_out_of_window', 'gap_seconds': -360.0}
]
_BASELINE_MERGE_LOG = 'event=smart_merge mode=merge decision=merged p_same=0.5 uid=user-1 conversation=n survivor=p flattened_ancestor_count=0'
_BASELINE_OVERLAP_LOG = 'event=smart_merge decision=skip reason=gap_out_of_window uid=user-1 conversation=n'


def _lookup_kwargs(created_min):
    return {'source': 'omi', 'created_before': T0 + timedelta(minutes=created_min), 'limit': 6}


@pytest.mark.parametrize('flag_value', [None, 'false'], ids=['unset', 'explicit_false'])
def test_flag_off_is_byte_identical_to_baseline_merge(world_off, caplog, monkeypatch, flag_value):
    if flag_value is not None:
        monkeypatch.setenv(OVERLAP_ENV, flag_value)
    world_off.overlap_metrics()
    world_off.decision_metrics()
    world_off.monkeypatch.setattr(smart_merge, 'datetime', _FrozenDateTime)
    world_off.add('p', 0, 10)
    world_off.add('n', 15, 10)
    world_off.jev_answers = [0.5]
    with caplog.at_level('INFO'):
        assert world_off.finish('n') is True
    assert dict(world_off.raw('n')['smart_merge_decision']) == _BASELINE_MERGE_RECORD
    assert world_off.lookup_calls == [_lookup_kwargs(15)]
    assert world_off.decision_calls == _BASELINE_MERGE_METRICS
    assert world_off.audit_calls == [('written',)]
    assert world_off.overlap_calls == []
    smart_merge_lines = [line for line in caplog.messages if 'event=smart_merge ' in line and 'audit' not in line]
    assert smart_merge_lines == [_BASELINE_MERGE_LOG]
    assert len(world_off.jev_calls) == 1
    state = world_off.jev_calls[0]['state']
    assert state_sha256(state) == _BASELINE_MERGE_RECORD['state_sha256']


@pytest.mark.parametrize('flag_value', [None, 'false'], ids=['unset', 'explicit_false'])
def test_flag_off_is_byte_identical_to_baseline_overlap(world_off, caplog, monkeypatch, flag_value):
    if flag_value is not None:
        monkeypatch.setenv(OVERLAP_ENV, flag_value)
    world_off.overlap_metrics()
    world_off.decision_metrics()
    world_off.monkeypatch.setattr(smart_merge, 'datetime', _FrozenDateTime)
    world_off.add('p', 0, 5)
    world_off.add('p2', 7, 9, sync_content_revision=2, sync_live_target=False)
    world_off.add('n', 10, 5)
    world_off.jev_answers = [0.5]
    with caplog.at_level('INFO'):
        assert world_off.finish('n') is False
    assert 'smart_merge_decision' not in world_off.raw('n')
    assert world_off.lookup_calls == [_lookup_kwargs(10)]
    assert world_off.decision_calls == _BASELINE_OVERLAP_METRICS
    assert world_off.audit_calls == []
    assert world_off.overlap_calls == []
    smart_merge_lines = [line for line in caplog.messages if 'event=smart_merge ' in line and 'audit' not in line]
    assert smart_merge_lines == [_BASELINE_OVERLAP_LOG]
    assert world_off.jev_calls == []
