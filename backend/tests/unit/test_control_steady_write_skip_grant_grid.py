"""Control steady-write skip: grant and transition ledger grid.

The skip must move exactly one write: the content-free warm append put. The
pull's service advance keeps its own ledger, every transition path keeps the
no-control ledger it always had, and append/grant interleavings lose exactly
one write per warm append. Each cell below pins one such claim against the
live scheduler.
"""

from tests.unit.control_steady_skip_fleet_helpers import *  # noqa: F401,F403


def test_grant_writes_control_after_a_seeded_stream():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    assert ('control', CONTROL) in store.ledgers[-1]


def test_grant_advances_service_by_cost_over_owner_count():
    store = LedgerStore()
    run_stream(store, ('a',))
    pull_grant(store, 400.0, 1)
    assert control_doc(store)['p2_service'] == 30.0


def test_two_grants_advance_service_twice():
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    pull_grant(store, 420.0, 1)
    assert control_doc(store)['p2_service'] == 60.0


def test_multi_lease_grant_advances_service_once_per_lease():
    store = LedgerStore()
    run_stream(store, ('a', 'b', 'c'))
    pull_grant(store, 400.0, 3)
    assert control_doc(store)['p2_service'] == 90.0


def test_multi_lease_grant_writes_control_on_one_ledger():
    store = LedgerStore()
    run_stream(store, ('a', 'b', 'c'))
    pull_grant(store, 400.0, 3)
    control_ledgers = [puts for puts in store.ledgers if ('control', CONTROL) in puts]
    assert len(control_ledgers) == 2  # one cold append + one grant


def test_grant_then_warm_append_then_grant_counts_four_control_writes():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('d', owner=OWNER), 410.0)
    pull_grant(store, 420.0, 1)
    assert_count(store, 3)


def test_warm_append_after_a_undrained_grant_carries_no_control_write():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('d', owner=OWNER), 410.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_grant_ledger_alone_carries_control():
    store = LedgerStore()
    run_stream(store, ('a',))
    pull_grant(store, 400.0, 1)
    assert ('control', CONTROL) in store.ledgers[-1]


def test_defer_transition_never_writes_control():
    store = LedgerStore()
    scheduler = run_stream(store, ('a',))
    leases = pull_grant(store, 400.0, 1)
    scheduler.defer('a', leases[0].token, 401.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_release_transition_never_writes_control():
    store = LedgerStore()
    scheduler = run_stream(store, ('a',))
    leases = pull_grant(store, 400.0, 1)
    scheduler.release('a', leases[0].token, 401.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_heartbeat_transition_never_writes_control():
    store = LedgerStore()
    scheduler = run_stream(store, ('a',))
    leases = pull_grant(store, 400.0, 1)
    scheduler.heartbeat('a', leases[0].token, 401.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_quarantine_transition_never_writes_control():
    store = LedgerStore()
    scheduler = run_stream(store, ('a',))
    leases = pull_grant(store, 400.0, 1)
    scheduler.fail('a', leases[0].token, 401.0, quarantine=True)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_recover_requeue_of_a_warm_owner_skips_control():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    leases = pull_grant(store, 400.0, 1)
    scheduler.defer('a', leases[0].token, 401.0)
    scheduler.recover(500.0)
    for ledger in store.ledgers[-1:]:
        assert ('control', CONTROL) not in ledger


def test_recover_requeue_ledger_still_carries_queue_and_job():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    leases = pull_grant(store, 400.0, 1)
    scheduler.defer('a', leases[0].token, 401.0)
    scheduler.recover(500.0)
    ledger = store.ledgers[-1]
    assert any(table == 'queues' for table, _ in ledger)
    assert any(table == 'jobs' for table, _ in ledger)


def test_grant_service_advance_matches_the_kill_switch_value(monkeypatch):
    store_a = LedgerStore()
    run_stream(store_a, ('a',))
    pull_grant(store_a, 400.0, 1)
    monkeypatch.setenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', 'false')
    store_b = LedgerStore()
    run_stream(store_b, ('a',))
    pull_grant(store_b, 400.0, 1)
    assert control_doc(store_a) == control_doc(store_b)


def test_interleave_totals_differ_by_exactly_the_skips(monkeypatch):
    store_a = LedgerStore()
    sched = run_stream(store_a, ('a', 'b', 'c'))
    pull_grant(store_a, 400.0, 1)
    sched.enqueue(item('d', owner=OWNER), 410.0)
    monkeypatch.setenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', 'false')
    store_b = LedgerStore()
    sched = run_stream(store_b, ('a', 'b', 'c'))
    pull_grant(store_b, 400.0, 1)
    sched.enqueue(item('d', owner=OWNER), 410.0)
    assert_count(store_a, 2)
    assert_count(store_b, 5)


def test_grant_then_append_queue_and_owner_writes_survive():
    store = LedgerStore()
    scheduler = run_stream(store, ('a',))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('b', owner=OWNER), 410.0)
    assert ('queues', QUEUE) in store.ledgers[-1]
    assert ('owners', KEY) in store.ledgers[-1]
    assert ('jobs', 'b') in store.ledgers[-1]


def test_ring_membership_survives_grants_and_warm_appends():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('c', owner=OWNER), 410.0)
    assert QUEUE in control_doc(store)['rings'][str(int(Priority.DEEP))]


def test_availability_floors_stay_zero_across_grants_and_appends():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('c', owner=OWNER), 410.0)
    doc = control_doc(store)
    assert doc['p2_batch_available_at'] == 0.0
    assert doc['p2_live_available_at'] == 0.0


def test_grant_on_a_second_owner_writes_its_control():
    store = LedgerStore()
    run_stream(store, ('a',))
    run_stream(store, ('l0',), owner='light')
    pull_grant(store, 400.0, 1)
    light_key = scheduler_control_key(owner_key('light'))
    assert any(('control', light_key) in puts for puts in store.ledgers)


def test_grant_write_set_stays_within_its_bound():
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    assert len(store.ledgers[-1]) <= 5


def test_append_ledgers_stay_within_their_bound_across_a_grant():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('c', owner=OWNER), 410.0)
    for index in (0, -1):
        assert len(store.ledgers[index]) <= 4


def test_pull_on_an_empty_store_writes_nothing():
    store = LedgerStore()
    leases = pull_grant(store, 400.0, 1)
    assert leases == []
    assert store.ledgers == []


def test_pull_limit_above_inventory_grants_what_exists():
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    leases = pull_grant(store, 400.0, 5)
    assert [lease.item.segment_id for lease in leases] == ['a', 'b']


def test_second_pull_grants_the_next_unit():
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    leases = pull_grant(store, 420.0, 1)
    assert [lease.item.segment_id for lease in leases] == ['b']


def test_grant_does_not_touch_the_queue_items_of_later_units():
    store = LedgerStore()
    run_stream(store, ('a', 'b', 'c'))
    pull_grant(store, 400.0, 1)
    assert queue_doc(store)['items'] == ['b', 'c']


def test_grant_head_advances_to_the_next_unit():
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    assert queue_doc(store)['head'] == 'b'


def test_complete_transition_never_writes_control():
    from utils.batch_pipeline.contracts import WorkResult

    store = LedgerStore()
    scheduler = run_stream(store, ('a',))
    leases = pull_grant(store, 400.0, 1)
    result = WorkResult(segment_id='a', result_uri='u/1', outcome='success')
    scheduler.complete(result, leases[0].token, 401.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_fail_transition_without_quarantine_never_writes_control():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    leases = pull_grant(store, 400.0, 1)
    scheduler.fail('a', leases[0].token, 401.0)
    assert ('control', CONTROL) not in store.ledgers[-1]


def test_grant_control_write_is_a_real_change_not_a_skip():
    store = LedgerStore()
    run_stream(store, ('a',))
    before = dict(control_doc(store))
    pull_grant(store, 400.0, 1)
    assert control_doc(store) != before


def test_warm_append_between_grants_is_the_only_skipped_write():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('c', owner=OWNER), 410.0)
    pull_grant(store, 420.0, 1)
    assert ('control', CONTROL) not in store.ledgers[-2]
    assert ('control', CONTROL) in store.ledgers[-1]


def test_owner_revision_counts_appends_only():
    store = LedgerStore()
    scheduler = run_stream(store, ('a', 'b'))
    pull_grant(store, 400.0, 1)
    scheduler.enqueue(item('c', owner=OWNER), 410.0)
    pull_grant(store, 420.0, 1)
    assert owner_doc(store)['revision'] == 3


def test_owner_revision_identical_under_the_kill_switch(monkeypatch):
    store_a = LedgerStore()
    sched = run_stream(store_a, ('a', 'b', 'c'))
    pull_grant(store_a, 400.0, 1)
    sched.enqueue(item('d', owner=OWNER), 410.0)
    monkeypatch.setenv('BATCH_PIPELINE_CONTROL_STEADY_WRITE_SKIP_ENABLED', 'false')
    store_b = LedgerStore()
    sched = run_stream(store_b, ('a', 'b', 'c'))
    pull_grant(store_b, 400.0, 1)
    sched.enqueue(item('d', owner=OWNER), 410.0)
    assert owner_doc(store_a)['revision'] == 4
    assert owner_doc(store_a) == owner_doc(store_b)


def test_fresh_priority_grant_writes_its_own_cells():
    store = LedgerStore()
    run_stream(store, ('f0',), priority=Priority.FRESH)
    pull_grant(store, 400.0, 1)
    assert control_doc(store)['p0_service'] == 30.0


def test_grant_after_conversion_append_keeps_the_array_ledger():
    store = LedgerStore()
    run_stream(store, ('a', 'b'))
    assert queue_doc(store)['link_mode'] == 'fifo_array'
    pull_grant(store, 400.0, 1)
    assert ('control', CONTROL) in store.ledgers[-1]


def test_double_grant_of_same_unit_impossible():
    store = LedgerStore()
    run_stream(store, ('a',))
    first = pull_grant(store, 400.0, 1)
    second = pull_grant(store, 405.0, 1)
    assert len(first) == 1 and second == []
