"""Adversarial shadow contracts; synthetic inputs and hermetic writer only."""

import asyncio
import random
from copy import deepcopy

import pytest

from tests.unit import test_action_item_identity_reprocess as h

identity = h.action_item_identity


@pytest.mark.parametrize('segments', ['segment', {'segment': True}, 42, None])
def test_malformed_segment_containers_are_not_anchors(monkeypatch, caplog, segments):
    row = h._anchored_row('old', 'Synthetic old', ['s'])
    row['provenance'][0]['transcript_segment_ids'] = segments
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', [h._new('Synthetic new', ['s'])], [row])
    assert fields['shadow'] == 'ok'
    assert fields['prior_without_anchor'] == '1'
    assert fields['anchor_pairs'] == '0'


def test_shadow_never_consumes_an_aliased_anchor_iterator(monkeypatch, caplog):
    consumed = []

    def segments():
        consumed.append(True)
        yield 's'

    row = h._anchored_row('old', 'Synthetic old', ['s'])
    row['provenance'][0]['transcript_segment_ids'] = segments()
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', [h._new('Synthetic new', ['s'])], [row])
    assert not consumed
    assert fields['anchor_pairs'] == '0'


def test_shadow_has_a_work_cap_before_reading_anchors(monkeypatch, caplog):
    rows = [h._anchored_row(str(i), 'Synthetic old', ['s']) for i in range(513)]
    monkeypatch.setattr(identity, '_segment_anchor', lambda *a: pytest.fail('cap did not stop anchor work'))
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', [h._new('Synthetic new', ['s'])], rows)
    assert (fields['shadow'], fields['shadow_error']) == ('error', 'budget_exceeded')


def test_large_evidence_is_rejected_without_partial_counts(monkeypatch, caplog):
    row = h._anchored_row('old', 'Synthetic old', [f's{i}' for i in range(513)])
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', [h._new('Synthetic new', ['s0'])], [row])
    assert (fields['shadow'], fields['shadow_error']) == ('error', 'budget_exceeded')
    assert all(fields[key] == '0' for key in identity.SHADOW_FIELDS)


@pytest.mark.parametrize('scenario', ['graph', 'entries', 'id_length', 'total_segments'])
def test_every_shadow_budget_rejects_whole_measurement(monkeypatch, caplog, scenario):
    rows = [h._anchored_row('old', 'Synthetic old', ['s'])]
    items = [h._new('Synthetic new', ['s'])]
    if scenario == 'graph':
        rows = [h._anchored_row(str(i), 'Synthetic old', ['s']) for i in range(257)]
        items *= 256
    elif scenario == 'entries':
        rows[0]['provenance'] *= 65
    elif scenario == 'id_length':
        rows[0]['provenance'][0]['transcript_segment_ids'] = ['s' * 257]
    else:
        rows = [h._anchored_row(str(i), 'Synthetic old', [f's{j}' for j in range(512)]) for i in range(129)]
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', items, rows)
    assert (fields['shadow'], fields['shadow_error']) == ('error', 'budget_exceeded')
    assert all(fields[key] == '0' for key in identity.SHADOW_FIELDS)


@pytest.mark.parametrize('provenance', ['s', {'kind': 'conversation', 'id': 'c'}, 42, None])
def test_malformed_provenance_containers_are_inert(monkeypatch, caplog, provenance):
    row = h._anchored_row('old', 'Synthetic old', ['s'])
    row['provenance'] = provenance
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', [h._new('Synthetic new', ['s'])], [row])
    assert fields['shadow'] == 'ok' and fields['prior_without_anchor'] == '1'
    assert fields['anchor_pairs'] == '0'


def test_exception_class_cannot_inject_log_fields(monkeypatch, caplog):
    private_error = type('private-segment task-text leaked=1', (Exception,), {})

    def broken(*args):
        raise private_error('private exception message')

    monkeypatch.setattr(identity, '_anchor_counts', broken)
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', [], [])
    assert fields['shadow_error'] == 'Exception'
    assert 'private' not in caplog.text and 'leaked' not in caplog.text


@pytest.mark.parametrize('error', [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
def test_shadow_propagates_cancellation_and_process_exit(monkeypatch, error):
    def broken(*args):
        raise error()

    monkeypatch.setattr(identity, '_anchor_counts', broken)
    with pytest.raises(error):
        identity.plan_replacement('c', [], [])


def test_random_graph_counts_match_independent_oracle(monkeypatch):
    rng = random.Random(8021)
    monkeypatch.delenv(h.ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENV, raising=False)
    monkeypatch.delenv(h.ACTION_ITEM_IDENTITY_PRESERVE_ENV, raising=False)
    witnessed = set()
    for _ in range(250):
        old_ids = [[f's{i}' for i in range(5) if rng.randrange(3) == 0] for _ in range(rng.randrange(1, 9))]
        new_ids = [[f's{i}' for i in range(5) if rng.randrange(3) == 0] for _ in range(rng.randrange(1, 9))]
        prior = [h._anchored_row(str(i), f'Synthetic old {i}', ids + ids) for i, ids in enumerate(old_ids)]
        items = [h._new(f'Synthetic new {i}', ids) for i, ids in enumerate(new_ids)]
        for row in prior:
            row['sync_requested'] = rng.randrange(4) == 0
        eligible = [i for i, row in enumerate(prior) if not row['sync_requested']]
        # Independent edge-set oracle (not the implementation's degree representation).
        edges = {(i, j) for i in eligible for j in range(len(items)) if set(old_ids[i]).intersection(new_ids[j])}
        paired = {(i, j) for i, j in edges if sum(a == i for a, b in edges) == sum(b == j for a, b in edges) == 1}
        plan = identity.plan_replacement('c', items, prior)
        snapshot = deepcopy((items, prior, plan))
        counts = identity._anchor_counts('c', items, prior, plan, True)
        assert snapshot == (items, prior, plan)
        assert counts['anchor_pairs'] == len(paired)
        assert counts['anchor_ambiguous'] == len({i for i, j in edges}) - len(paired)
        assert counts['prior_without_anchor'] == sum(not old_ids[i] for i in eligible)
        assert counts['new_without_anchor'] == sum(not ids for ids in new_ids)
        disjoint = sum(bool(old_ids[i]) and not any(a == i for a, b in edges) for i in eligible)
        assert counts['unmatched_prior'] == (
            counts['unmatched_prior_ineligible']
            + counts['prior_without_anchor']
            + counts['anchor_pairs']
            + counts['anchor_ambiguous']
            + disjoint
        )
        witnessed.update(name for name in ('anchor_pairs', 'anchor_ambiguous', 'prior_without_anchor') if counts[name])
    assert witnessed == {'anchor_pairs', 'anchor_ambiguous', 'prior_without_anchor'}


def test_dense_two_hundred_segment_overlap_and_multiple_conversations(monkeypatch, caplog):
    ids = [f's{i}' for i in range(200)]
    prior = [h._anchored_row('old', 'Synthetic old', ids)]
    prior[0]['provenance'] += h._provenance(['donor-only'], 'other')
    items = [h._new('Synthetic new', ids + ['donor-only']), h._new('Synthetic donor', ['donor-only'])]
    _, fields = h._shadow_of(caplog, monkeypatch, 'c', items, prior)
    assert (fields['anchor_pairs'], fields['anchor_ambiguous']) == ('1', '0')


def test_adversarial_full_writer_trace_has_shadow_off_parity(monkeypatch, caplog):
    def run(flag):
        world = h._anchored_world(monkeypatch, flag)
        h._process(world, 'conv-1', h.FIRST)
        tasks = world.store.tasks('conv-1')
        for n, (task_id, _) in enumerate(tasks.items()):
            row = world.store.docs[f'users/{h.UID}/action_items/{task_id}']
            row['provenance'] += h._provenance(['s1', 's1'], 'other')
            if n == 0:
                row['sync_requested'] = True
            if n == 1:
                row['provenance'][0]['transcript_segment_ids'] = 's3'
        before = deepcopy(world.store.docs)
        world.deferred = True
        h._process(world, 'conv-1', h.REPROCESS, h.ProcessingTrigger.SMART_MERGE)
        world.drain()
        trace = (
            world.store.events,
            world.events,
            world.reminders,
            world.external,
            world.creates,
            world.store.docs,
            world.apple_pushes,
            before,
        )
        return h._without_anchor_projection(h._scrub(trace))

    assert run(None) == run('off')


def test_flag_is_read_at_each_call(monkeypatch):
    monkeypatch.setenv(h.ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENV, 'off')
    assert identity.prior_read_kwargs() == {}
    monkeypatch.setenv(h.ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENV, 'on')
    assert identity.prior_read_kwargs() == {'extra_fields': ('provenance',)}
    monkeypatch.setenv(h.ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENV, 'typo')
    assert identity.prior_read_kwargs() == {}


def test_extra_projection_never_leaks_to_later_callers_or_legacy_harvest(monkeypatch):
    world = h._anchored_world(monkeypatch, None)
    h._process(world, 'conv-1', h.FIRST)
    task_id = next(iter(world.store.tasks('conv-1')))
    world.store.docs[f'users/{h.UID}/action_items/{task_id}'].pop('completed')
    original_fields = h.action_items_db.ACTION_ITEMS_LIST_SELECT_FIELDS
    world.store.events.clear()
    widened = h.action_items_db.get_action_items_by_conversation(h.UID, 'conv-1', extra_fields=('provenance',))
    reads = [event for event in world.store.events if event[0] == 'query' and event[3]]
    assert any('provenance' in event[3] for event in reads)
    legacy_reads = [event for event in reads if 'completed' not in dict(event[2])]
    assert legacy_reads and all(event[3] == list(original_fields) for event in legacy_reads)
    assert any(row['provenance'] for row in widened)
    world.store.events.clear()
    lean = h.action_items_db.get_action_items_by_conversation(h.UID, 'conv-1')
    assert all(not row['provenance'] for row in lean)
    assert all(event[3] == list(original_fields) for event in world.store.events if event[0] == 'query' and event[3])
    assert h.action_items_db.ACTION_ITEMS_LIST_SELECT_FIELDS == original_fields
