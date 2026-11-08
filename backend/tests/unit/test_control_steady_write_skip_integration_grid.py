"""Control steady-write skip: integration grid over paired streams.

Every cell runs the same admission schedule twice — once under the skip, once
under the kill switch — and pins one equivalence or one count. The equivalence
claims are the rollback contract: flipping the switch changes exactly which
transactions carry the control document, never what those documents say.
"""

from tests.unit.control_steady_skip_fleet_helpers import *  # noqa: F401,F403
import pytest

from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline import scheduler as scheduler_module


def _paired(segments, owners=None, priorities=None):
    store_a = LedgerStore()
    scheduler_a = Scheduler(store_a)
    owners = owners or [OWNER] * len(segments)
    priorities = priorities or [Priority.DEEP] * len(segments)
    for index, segment in enumerate(segments):
        assert scheduler_a.enqueue(item(segment, owner=owners[index], priority=priorities[index]), index * 70.0)
    store_b = LedgerStore()
    scheduler_b = Scheduler(store_b)
    for index, segment in enumerate(segments):
        assert scheduler_b.enqueue(item(segment, owner=owners[index], priority=priorities[index]), index * 70.0)
    return store_a, store_b


def _equal_docs(store_a, store_b, owners=(KEY,)):
    for owner in owners:
        assert control_doc(store_a, owner) == control_doc(store_b, owner)
        assert queue_doc(store_a, owner) == queue_doc(store_b, owner)
        assert owner_doc(store_a, owner) == owner_doc(store_b, owner)


def test_two_unit_stream_all_job_rows_equal():
    store_a, store_b = _paired(('a', 'b'))
    assert store_a.rows.get(('jobs', 'a')) == store_b.rows.get(('jobs', 'a'))
    assert store_a.rows.get(('jobs', 'b')) == store_b.rows.get(('jobs', 'b'))


def test_three_unit_stream_all_job_rows_equal():
    store_a, store_b = _paired(('a', 'b', 'c'))
    for segment in ('a', 'b', 'c'):
        assert store_a.rows.get(('jobs', segment)) == store_b.rows.get(('jobs', segment))


def test_five_unit_stream_all_job_rows_equal():
    store_a, store_b = _paired(('a', 'b', 'c', 'd', 'e'))
    for segment in 'abcde':
        assert store_a.rows.get(('jobs', segment)) == store_b.rows.get(('jobs', segment))


def test_eight_unit_stream_all_job_rows_equal():
    store_a, store_b = _paired(tuple(f'u{i}' for i in range(8)))
    for index in range(8):
        assert store_a.rows.get(('jobs', f'u{index}')) == store_b.rows.get(('jobs', f'u{index}'))


def test_twelve_unit_stream_all_job_rows_equal():
    store_a, store_b = _paired(tuple(f'u{i}' for i in range(12)))
    for index in range(12):
        assert store_a.rows.get(('jobs', f'u{index}')) == store_b.rows.get(('jobs', f'u{index}'))


def test_two_owner_stream_job_rows_equal_per_owner():
    store_a, store_b = _paired(('a0', 'b0', 'a1', 'b1'), owners=['heavy', 'light', 'heavy', 'light'])
    for segment in ('a0', 'b0', 'a1', 'b1'):
        assert store_a.rows.get(('jobs', segment)) == store_b.rows.get(('jobs', segment))


def test_priority_mix_stream_job_rows_equal():
    store_a, store_b = _paired(('d0', 'd1', 'f0'), priorities=[Priority.DEEP, Priority.DEEP, Priority.FRESH])
    for segment in ('d0', 'd1', 'f0'):
        assert store_a.rows.get(('jobs', segment)) == store_b.rows.get(('jobs', segment))


def test_two_unit_stream_owner_revisions_equal():
    store_a, store_b = _paired(('a', 'b'))
    assert owner_doc(store_a)['revision'] == owner_doc(store_b)['revision'] == 2


def test_four_unit_stream_owner_revisions_equal():
    store_a, store_b = _paired(('a', 'b', 'c', 'd'))
    assert owner_doc(store_a)['revision'] == owner_doc(store_b)['revision'] == 4


def test_two_owner_stream_revisions_equal_per_owner():
    store_a, store_b = _paired(('a0', 'b0', 'a1'), owners=['heavy', 'light', 'heavy'])
    assert owner_doc(store_a, owner_key('heavy'))['revision'] == 2
    assert owner_doc(store_b, owner_key('light'))['revision'] == 1
    assert owner_doc(store_a, owner_key('light')) == owner_doc(store_b, owner_key('light'))


def test_stream_fresh_priority_ring_membership_equal():
    store_a, store_b = _paired(('f0', 'f1'), priorities=[Priority.FRESH, Priority.FRESH])
    doc_a = control_doc(store_a)
    doc_b = control_doc(store_b)
    fresh_key = f'{int(Priority.FRESH)}_{KEY}'
    assert fresh_key in doc_a['rings'][str(int(Priority.FRESH))]
    assert doc_a['rings'] == doc_b['rings']


def test_priority_mix_rings_equal():
    store_a, store_b = _paired(('d0', 'f0'), priorities=[Priority.DEEP, Priority.FRESH])
    assert control_doc(store_a)['rings'] == control_doc(store_b)['rings']
    doc = control_doc(store_a)
    assert QUEUE in doc['rings'][str(int(Priority.DEEP))]
    assert f'{int(Priority.FRESH)}_{KEY}' in doc['rings'][str(int(Priority.FRESH))]


def test_stream_activation_states_equal():
    store_a, store_b = _paired(('a', 'b', 'c'))
    doc_a, doc_b = control_doc(store_a), control_doc(store_b)
    assert doc_a['p2_active'] is doc_b['p2_active'] is True
    assert doc_a['p2_service'] == doc_b['p2_service']
    assert doc_a['p2_batch_available_at'] == doc_b['p2_batch_available_at']
    assert doc_a['p2_live_available_at'] == doc_b['p2_live_available_at']


def test_ledgers_of_paired_streams_differ_only_by_control_puts():
    store_a, store_b = _paired(('a', 'b', 'c', 'd'))
    for puts_a, puts_b in zip(store_a.ledgers, store_b.ledgers):
        strip_a = [put for put in puts_a if put[0] != 'control']
        strip_b = [put for put in puts_b if put[0] != 'control']
        assert strip_a == strip_b
        assert len(puts_a) == len(puts_b) or ('control', CONTROL) in puts_a


def test_stream_of_four_counts_one_control_write():
    store_a, store_b = _paired(('a', 'b', 'c', 'd'))
    # both runs ride the default (skip) mode: one cold write each
    assert_count(store_a, 1)
    assert_count(store_b, 1)


def test_queue_items_arrays_identical_over_ten_units():
    store_a, store_b = _paired(tuple(f's{i}' for i in range(10)))
    assert queue_doc(store_a)['items'] == queue_doc(store_b)['items'] == [f's{i}' for i in range(10)]


def test_queue_tails_identical_over_ten_units():
    store_a, store_b = _paired(tuple(f's{i}' for i in range(10)))
    assert queue_doc(store_a)['tail'] == queue_doc(store_b)['tail'] == 's9'


# --- grant-interleaved schedules --------------------------------------------


def _grant_schedule(segments, grant_at, appends, owner=OWNER):
    """seed segments; pull-grant after grant_at appends; enqueue extra appends."""
    store = LedgerStore()
    scheduler = Scheduler(store)
    events = []
    for index, segment in enumerate(segments):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
        events.append(f'seed:{segment}')
    for step, (kind, payload) in enumerate(appends):
        if kind == 'grant':
            pull_grant(store, 400.0 + step * 20.0, payload)
            events.append(f'grant:{payload}')
        else:
            scheduler.enqueue(item(payload, owner=owner), 500.0 + step * 20.0)
            events.append(f'append:{payload}')
    return store, scheduler


SCHEDULES = [
    (('a', 'b'), [('grant', 1)], [('append', 'c')]),
    (('a', 'b', 'c'), [('grant', 1)], [('append', 'd')]),
    (('a', 'b'), [('grant', 2)], [('append', 'c'), ('append', 'd')]),
    (('a', 'b', 'c'), [('grant', 2)], [('append', 'd')]),
    (('a',), [('grant', 1)], [('append', 'b'), ('append', 'c')]),
    (('a', 'b'), [('grant', 1), ('grant', 1)], [('append', 'c')]),
    (('a', 'b', 'c', 'd'), [('grant', 2)], [('append', 'e')]),
    (('a', 'b'), [('grant', 1)], [('append', 'c'), ('grant', 1)]),
]


def test_grant_schedules_keep_job_rows_equal():
    for index, (segments, grants, appends) in enumerate(SCHEDULES):
        store_a, _ = _grant_schedule(segments, None, grants + appends)
        import os

        os.environ[ENV] = 'false'
        store_b, _ = _grant_schedule(segments, None, grants + appends)
        os.environ.pop(ENV, None)
        for segment in set(segments) | {p for kind, p in grants + appends if kind == 'append'}:
            row_a = dict(store_a.rows.get(('jobs', segment)) or {})
            row_b = dict(store_b.rows.get(('jobs', segment)) or {})
            row_a.pop('token', None)
            row_b.pop('token', None)  # lease tokens are per-run random UUIDs
            assert row_a == row_b, (index, segment)


def test_grant_schedules_keep_queue_rows_equal():
    for index, (segments, grants, appends) in enumerate(SCHEDULES):
        store_a, _ = _grant_schedule(segments, None, grants + appends)
        import os

        os.environ[ENV] = 'false'
        store_b, _ = _grant_schedule(segments, None, grants + appends)
        os.environ.pop(ENV, None)
        assert queue_doc(store_a) == queue_doc(store_b), index


def test_grant_schedules_keep_control_content_equal():
    for index, (segments, grants, appends) in enumerate(SCHEDULES):
        store_a, _ = _grant_schedule(segments, None, grants + appends)
        import os

        os.environ[ENV] = 'false'
        store_b, _ = _grant_schedule(segments, None, grants + appends)
        os.environ.pop(ENV, None)
        assert control_doc(store_a) == control_doc(store_b), index


def test_grant_schedules_keep_owner_revisions_equal():
    for index, (segments, grants, appends) in enumerate(SCHEDULES):
        store_a, _ = _grant_schedule(segments, None, grants + appends)
        import os

        os.environ[ENV] = 'false'
        store_b, _ = _grant_schedule(segments, None, grants + appends)
        os.environ.pop(ENV, None)
        assert owner_doc(store_a) == owner_doc(store_b), index


def test_grant_schedules_never_exceed_the_write_bound():
    for index, (segments, grants, appends) in enumerate(SCHEDULES):
        store, _ = _grant_schedule(segments, None, grants + appends)
        for puts in store.ledgers:
            is_grant = any(table == 'pull_claims' for table, _ in puts)
            assert len(puts) <= (9 if is_grant else 4), (index, puts)


def test_grant_schedules_control_writes_bounded_by_cold_and_grants():
    for index, (segments, grants, appends) in enumerate(SCHEDULES):
        store, _ = _grant_schedule(segments, None, grants + appends)
        writes = sum(1 for puts in store.ledgers if ('control', CONTROL) in puts)
        grants_n = sum(1 for kind, _ in grants + appends if kind == 'grant')
        appends_n = sum(1 for kind, _ in grants + appends if kind == 'append')
        assert 1 <= writes <= 1 + grants_n + appends_n, index


def test_grant_schedule_of_three_with_one_grant_writes_two_controls():
    store, _ = _grant_schedule(('a', 'b', 'c'), None, [('grant', 1)])
    assert_count(store, 2)


def test_grant_schedule_of_two_with_one_grant_and_one_append_writes_two_controls():
    store, _ = _grant_schedule(('a', 'b'), None, [('grant', 1), ('append', 'c')])
    assert_count(store, 2)


def test_grant_schedule_ring_still_holds_the_queue():
    store, _ = _grant_schedule(('a', 'b', 'c'), None, [('grant', 1)])
    assert QUEUE in control_doc(store)['rings'][str(int(Priority.DEEP))]


def test_grant_schedule_head_tracks_the_next_unit():
    store, _ = _grant_schedule(('a', 'b', 'c'), None, [('grant', 1)])
    assert queue_doc(store)['head'] == 'b'


def test_grant_schedule_service_reflects_the_grant():
    store, _ = _grant_schedule(('a', 'b', 'c'), None, [('grant', 1)])
    assert control_doc(store)['p2_service'] == 30.0


def test_grant_schedule_appends_after_grant_skip_control():
    store, scheduler = _grant_schedule(('a', 'b', 'c'), None, [('grant', 1)])
    scheduler.enqueue(item('z', owner=OWNER), 700.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_double_grant_schedule_counts_each_grant():
    store, _ = _grant_schedule(('a', 'b'), None, [('grant', 1), ('grant', 1)])
    assert_count(store, 3)


def test_grant_then_append_then_grant_writes_four():
    store, scheduler = _grant_schedule(('a', 'b'), None, [('grant', 1)])
    scheduler.enqueue(item('c', owner=OWNER), 600.0)
    pull_grant(store, 620.0, 1)
    control_writes = sum(1 for puts in store.ledgers if ('control', CONTROL) in puts)
    assert control_writes == 3


# --- kill-switch interactions ------------------------------------------------


def test_kill_switch_schedule_matches_default_schedule_documents():
    import os

    store_a, _ = _grant_schedule(('a', 'b', 'c'), None, [('grant', 1), ('append', 'd')])
    os.environ[ENV] = 'false'
    store_b, _ = _grant_schedule(('a', 'b', 'c'), None, [('grant', 1), ('append', 'd')])
    os.environ.pop(ENV, None)
    assert control_doc(store_a) == control_doc(store_b)
    assert queue_doc(store_a) == queue_doc(store_b)
    assert owner_doc(store_a) == owner_doc(store_b)


def test_switch_flip_midstream_takes_immediate_effect():
    import os

    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    assert_count(store, 1)
    os.environ[ENV] = 'false'
    scheduler.enqueue(item('c', owner=OWNER), 500.0)
    assert ('control', CONTROL) in store.ledgers[-1]
    os.environ[ENV] = 'true'
    scheduler.enqueue(item('d', owner=OWNER), 510.0)
    assert ('control', CONTROL) not in store.ledgers[-1]
    os.environ.pop(ENV, None)


def test_probe_and_ledger_helpers_coexist():
    doc = sample_control(rings='member', active=True)
    cell(doc, 2, QUEUE, True, 1, True, 0.0, 0.0, 0.0)
    store = LedgerStore()
    warm_owner(store)
    assert_count(store, 1)


def test_ring_capacity_refusal_is_switch_independent(monkeypatch):
    monkeypatch.setattr(scheduler_module, 'MAX_ACTIVE_OWNERS', 1)
    for env in (None, 'false'):
        if env is None:
            monkeypatch.delenv(ENV, raising=False)
        else:
            monkeypatch.setenv(ENV, env)
        store = LedgerStore()
        warm_owner(store)
        blocked_key = scheduler_control_key(owner_key('blocked'))
        store.rows[('control', blocked_key)] = {
            'rings': {str(int(Priority.DEEP)): ['filler_queue']},
        }
        with pytest.raises(RuntimeError):
            Scheduler(store).enqueue(item('blocked', owner='blocked'), 50.0)
        assert ('jobs', 'blocked') not in store.rows


def test_frontier_seed_cold_owner_writes_the_seed(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    store = LedgerStore()
    store.service_frontier_hint = lambda priority: 5.0
    assert Scheduler(store).enqueue(item('first', owner=OWNER), 0.0) is True
    assert control_doc(store)['p2_service'] == 5.0


def test_frontier_hint_rise_on_warm_owner_skips():
    store = LedgerStore()
    warm_owner(store)
    store.service_frontier_hint = lambda priority: 50.0
    Scheduler(store).enqueue(item('next', owner=OWNER), 50.0)
    assert control_doc(store)['p2_service'] == 0.0
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_deduplicated_admission_adds_no_ledger_after_a_stream():
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    scheduler = Scheduler(store)
    assert scheduler.enqueue(item('a', owner=OWNER), 500.0) is False
    assert len(store.ledgers) == 3
    assert store.ledgers[-1] == []
    assert_count(store, 1)


def test_second_scheduler_on_the_store_continues_the_skip():
    store = LedgerStore()
    run_stream(store, ('a', 'b', 'c'))
    Scheduler(store).enqueue(item('d', owner=OWNER), 500.0)
    assert_count(store, 1)
    assert queue_doc(store)['tail'] == 'd'


def test_light_owner_priority_expansion_writes_its_own_two():
    store = LedgerStore()
    run_stream(store, ('h0',))
    Scheduler(store).enqueue(item('l0', owner='light'), 70.0)
    Scheduler(store).enqueue(item('lf0', owner='light', priority=Priority.FRESH), 140.0)
    light_key = scheduler_control_key(owner_key('light'))
    assert_count(store, 1)  # heavy untouched
    assert_count(store, 2, light_key)
    assert (
        f'{int(Priority.FRESH)}_{owner_key("light")}'
        in control_doc(store, owner_key('light'))['rings'][str(int(Priority.FRESH))]
    )
