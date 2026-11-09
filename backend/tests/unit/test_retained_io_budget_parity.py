"""The fetch/decode budget parity grid: the shared decode budget never grants a
second reservation for one segment or past its seconds cap, released
reservations re-submit, prepared-decode receipts are identity matched and
one-shot, cancellation discards the whole prefix, and closing releases the
budget exactly once per receipt.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import threading

import pytest

from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace

from utils.batch_pipeline.worker_io import DecodeBudget, FirstDecode, PreparedFlight


def unit(segment_id='a', duration=10.0):
    return SimpleNamespace(segment_id=segment_id, duration_seconds=duration)


class FakeExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, decode, item):
        future = Future()
        future.set_result(('decoded', item.segment_id))
        self.submitted.append(item.segment_id)
        return future


def test_budget_grants_one_reservation_per_segment():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    assert budget.submit(executor, None, unit('a')) is not None
    assert budget.submit(executor, None, unit('a')) is None


def test_budget_tracks_granted_seconds():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    budget.submit(executor, None, unit('a', duration=10.0))
    assert budget.seconds == 10.0


def test_budget_refuses_beyond_the_seconds_cap():
    budget = DecodeBudget(10.0)
    executor = FakeExecutor()
    assert budget.submit(executor, None, unit('a', duration=6.0)) is not None
    assert budget.submit(executor, None, unit('b', duration=6.0)) is None


def test_budget_grants_up_to_the_exact_cap():
    budget = DecodeBudget(10.0)
    executor = FakeExecutor()
    assert budget.submit(executor, None, unit('a', duration=6.0)) is not None
    assert budget.submit(executor, None, unit('b', duration=4.0)) is not None


def test_release_restores_the_seconds():
    budget = DecodeBudget(10.0)
    executor = FakeExecutor()
    budget.submit(executor, None, unit('a', duration=6.0))
    budget.release(unit('a', duration=6.0))
    assert budget.seconds == 0.0


def test_released_segment_can_re_submit():
    budget = DecodeBudget(10.0)
    executor = FakeExecutor()
    budget.submit(executor, None, unit('a', duration=6.0))
    budget.release(unit('a', duration=6.0))
    assert budget.submit(executor, None, unit('a', duration=6.0)) is not None


def test_release_of_unknown_segment_raises():
    budget = DecodeBudget(10.0)
    with pytest.raises(KeyError):
        budget.release(unit('ghost', duration=1.0))


def test_different_segments_get_their_own_reservations():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    assert budget.submit(executor, None, unit('a')) is not None
    assert budget.submit(executor, None, unit('b')) is not None


def test_zero_duration_unit_still_reserves_identity():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    assert budget.submit(executor, None, unit('a', duration=0.0)) is not None
    assert budget.submit(executor, None, unit('a', duration=0.0)) is None


def test_submit_executes_the_decode_callable():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    future = budget.submit(executor, None, unit('a'))
    assert future.result() == ('decoded', 'a')


def test_first_decode_take_returns_the_future_result():
    budget = DecodeBudget(1800)
    it = unit('a')
    handle = FirstDecode(budget, it, Future())
    handle.future.set_result('samples')
    assert handle.take(it) == 'samples'


def test_first_decode_take_refuses_a_foreign_item():
    handle = FirstDecode(DecodeBudget(), unit('a'), Future())
    with pytest.raises(ValueError):
        handle.take(unit('b'))


def test_first_decode_take_refuses_a_cancelled_receipt():
    handle = FirstDecode(DecodeBudget(), unit('a'), Future())
    handle.cancel()
    with pytest.raises(ValueError):
        handle.take(unit('a'))


def test_first_decode_take_refuses_after_close():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit('a')
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    handle.close()
    with pytest.raises(ValueError):
        handle.take(it)


def test_first_decode_close_releases_the_budget():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit('a', duration=5.0)
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    assert budget.seconds == 5.0
    handle.close()
    assert budget.seconds == 0.0


def test_first_decode_close_is_idempotent():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit('a')
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    handle.close()
    handle.close()
    assert budget.seconds == 0.0


def test_first_decode_cancel_flags_the_receipt():
    handle = FirstDecode(DecodeBudget(), unit('a'), Future())
    handle.cancel()
    assert handle.cancelled is True


def test_first_decode_segment_ids_name_the_unit():
    handle = FirstDecode(DecodeBudget(), unit('a'), Future())
    assert handle.segment_ids == ('a',)


def test_first_decode_close_without_a_future_is_fatal():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit('a')
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    handle.future = None
    with pytest.raises(RuntimeError):
        handle.close()


def test_first_decode_take_waits_for_a_running_future():
    budget = DecodeBudget(1800)
    it = unit('a')
    future = Future()
    handle = FirstDecode(budget, it, future)
    future.set_result('late')
    assert handle.take(it) == 'late'


def test_prepared_flight_needs_at_least_one_handle():
    with pytest.raises(ValueError):
        PreparedFlight([])


def test_prepared_flight_names_its_prefix_in_order():
    handles = [FirstDecode(DecodeBudget(), unit(sid), Future()) for sid in ('a', 'b', 'c')]
    flight = PreparedFlight(handles)
    assert flight.segment_ids == ('a', 'b', 'c')
    assert flight.item is handles[0].item
    assert flight.future is handles[0].future


def test_prepared_flight_decodes_pairs_items_with_futures():
    handles = [FirstDecode(DecodeBudget(), unit(sid), Future()) for sid in ('a', 'b')]
    flight = PreparedFlight(handles)
    pairs = flight.decodes()
    assert [it.segment_id for it, _ in pairs] == ['a', 'b']
    assert [future for _, future in pairs] == [handles[0].future, handles[1].future]


def test_prepared_flight_cancel_discards_the_prefix():
    handles = [FirstDecode(DecodeBudget(), unit(sid), Future()) for sid in ('a', 'b')]
    flight = PreparedFlight(handles)
    flight.cancel()
    assert flight.cancelled is True
    assert all(handle.cancelled for handle in handles)


def test_prepared_flight_release_settled_closes_done_receipts():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    one = unit('a')
    two = unit('b')
    done = budget.submit(executor, None, one)
    running = Future()
    handles = [FirstDecode(budget, one, done), FirstDecode(budget, two, running)]
    flight = PreparedFlight(handles)
    flight.release_settled()
    assert handles[0]._closed is True
    assert handles[1]._closed is False


def test_prepared_flight_close_closes_every_receipt():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    one = unit('a')
    two = unit('b')
    done = budget.submit(executor, None, one)
    running = budget.submit(executor, None, two)
    handles = [FirstDecode(budget, one, done), FirstDecode(budget, two, running)]
    flight = PreparedFlight(handles)
    flight.close()
    assert all(handle._closed for handle in handles)
    assert budget.seconds == 0.0


def test_prepared_flight_close_surfaces_the_first_error_last():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit('a')
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    handle.future = None
    flight = PreparedFlight([handle])
    with pytest.raises(RuntimeError):
        flight.close()


def test_real_executor_budget_cycle_roundtrips():
    budget = DecodeBudget(1800)
    it = unit('a', duration=5.0)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = budget.submit(pool, lambda item: 'samples', it)
        handle = FirstDecode(budget, it, future)
        assert handle.take(it) == 'samples'
        handle.close()
    assert budget.seconds == 0.0


def test_released_reservation_frees_room_for_another_segment():
    budget = DecodeBudget(10.0)
    executor = FakeExecutor()
    assert budget.submit(executor, None, unit("a", duration=6.0)) is not None
    assert budget.submit(executor, None, unit("b", duration=6.0)) is None
    budget.release(unit("a", duration=6.0))
    assert budget.submit(executor, None, unit("b", duration=6.0)) is not None


def test_zero_cap_budget_refuses_positive_duration_units():
    budget = DecodeBudget(0.0)
    executor = FakeExecutor()
    assert budget.submit(executor, None, unit("a", duration=0.1)) is None
    assert budget.submit(executor, None, unit("a", duration=0.0)) is not None


def test_first_decode_close_twice_keeps_budget_consistent():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit("a", duration=7.0)
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    handle.close()
    handle.close()
    assert budget.seconds == 0.0
    assert budget.submit(executor, None, unit("a", duration=7.0)) is not None


def test_first_decode_take_twice_returns_the_same_result():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit("a")
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    assert handle.take(it) == ("decoded", "a")
    assert handle.take(it) == ("decoded", "a")


def test_first_decode_cancel_then_close_releases_the_budget_once():
    budget = DecodeBudget(1800)
    executor = FakeExecutor()
    it = unit("a", duration=4.0)
    handle = FirstDecode(budget, it, budget.submit(executor, None, it))
    handle.cancel()
    handle.close()
    assert budget.seconds == 0.0
    handle.close()


def test_prepared_flight_segment_ids_survive_cancel():
    handles = [FirstDecode(DecodeBudget(), unit(sid), Future()) for sid in ("a", "b", "c")]
    flight = PreparedFlight(handles)
    flight.cancel()
    assert flight.segment_ids == ("a", "b", "c")
