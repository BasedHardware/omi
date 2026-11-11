"""Pull-contention storm alignment: the shard backoff lands after the measured window.

The shard pull lane's contention handler arms ``_contention_backoff_until``
from the historical ``2 ** failures`` ladder. The store's storm damper
measures the label's hot documents and stamps the armed window onto the
exhausted chain's ``retry_after``; a backoff that discards that stamp
re-enters the window's interior, burns a full five-attempt chain against a
collision the damper had already measured, and re-arms the storm it just
paid to leave — the lockstep burn behind the production
``firestore_transaction_contention outcome=exhausted`` family. These tests
pin the two pure alignment helpers and the scheduler's armed state against
the documented schedule: the ladder rung is unchanged when no window is
stamped, a stamped window raises the floor without ever shortening the
ladder or extending the lane past ``CONTENTION_BACKOFF_CAP_SECONDS``, and
the storm-alignment scanner sees the arm as a wait.

The scheduler-level assertions fail on a tree whose handler still draws the
bare ladder: with ``random.random`` pinned to ``0.0`` (jitter factor 0.5)
the first-rung ladder is exactly ``0.5s``, so a stamped ``3.5s`` window must
arm ``monotonic() + 3.5`` where the bare ladder arms ``+ 0.5``.

Failure-Class: FC-pull-backoff-collides-inside-the-armed-storm-window
"""

from unittest.mock import Mock

from database.batch_pipeline_store import FirestoreStore
from database.firestore_transaction_retry import FirestoreContentionExhausted
from tests.support import storm_alignment_fixture as fixture
from utils.batch_pipeline import scheduler as scheduler_module
from utils.batch_pipeline.contracts import LeasedWork, Priority, WorkItem
from utils.batch_pipeline.scheduler import (
    CONTENTION_BACKOFF_CAP_SECONDS,
    Scheduler,
    pull_backoff_delay,
    pull_backoff_delay as delay,
    pull_contention_storm_after,
)


def item(segment, owner='heavy', capture=1, duration=30, priority=Priority.DEEP, unit_kind='conversation'):
    return WorkItem(segment, owner, capture, f'gs://synthetic/{segment}', duration, priority, unit_kind)


def exhausted(stamp=None):
    error = FirestoreContentionExhausted('bounded contention')
    if stamp is not None:
        error.retry_after = stamp
    return error


# ---------------------------------------------------------------------------
# pull_contention_storm_after: the measured window reader
# ---------------------------------------------------------------------------


def test_reader_returns_stamped_float_window():
    assert pull_contention_storm_after(exhausted(3.5)) == 3.5


def test_reader_returns_stamped_int_window_as_float():
    assert pull_contention_storm_after(exhausted(4)) == 4.0


def test_reader_clamps_to_the_lane_horizon():
    assert pull_contention_storm_after(exhausted(1e9)) == 30.0
    assert pull_contention_storm_after(exhausted(CONTENTION_BACKOFF_CAP_SECONDS)) == 30.0
    assert pull_contention_storm_after(exhausted(CONTENTION_BACKOFF_CAP_SECONDS + 0.5)) == 30.0


def test_reader_keeps_every_real_window_below_the_horizon():
    # The store's damper caps an armed window at 4.0s; every real stamp fits
    # under the pull lane's 30.0s horizon untouched.
    assert FirestoreStore.STORM_DAMPER_CAP_SECONDS == 4.0
    assert FirestoreStore.STORM_DAMPER_CAP_SECONDS < CONTENTION_BACKOFF_CAP_SECONDS
    assert pull_contention_storm_after(exhausted(4.0)) == 4.0


def test_reader_rejects_bool_stamps():
    assert pull_contention_storm_after(exhausted(True)) == 0.0
    assert pull_contention_storm_after(exhausted(False)) == 0.0


def test_reader_rejects_non_numeric_stamps():
    assert pull_contention_storm_after(exhausted('3.5')) == 0.0
    assert pull_contention_storm_after(exhausted(None)) == 0.0
    assert pull_contention_storm_after(exhausted([3.5])) == 0.0


def test_reader_rejects_non_positive_stamps():
    assert pull_contention_storm_after(exhausted(0.0)) == 0.0
    assert pull_contention_storm_after(exhausted(0)) == 0.0
    assert pull_contention_storm_after(exhausted(-1.0)) == 0.0
    assert pull_contention_storm_after(exhausted(-1e-9)) == 0.0


def test_reader_rejects_non_finite_stamps():
    assert pull_contention_storm_after(exhausted(float('nan'))) == 0.0
    assert pull_contention_storm_after(exhausted(float('inf'))) == 0.0
    assert pull_contention_storm_after(exhausted(float('-inf'))) == 0.0


def test_reader_keeps_tiny_positive_windows():
    assert pull_contention_storm_after(exhausted(1e-9)) == 1e-9


def test_reader_returns_zero_without_a_stamp():
    assert pull_contention_storm_after(exhausted(None)) == 0.0
    assert pull_contention_storm_after(FirestoreContentionExhausted('bounded')) == 0.0


def test_reader_returns_zero_for_none_and_foreign_errors_without_stamps():
    assert pull_contention_storm_after(None) == 0.0
    assert pull_contention_storm_after(ValueError('no stamp')) == 0.0


def test_reader_reads_any_error_carrying_the_stamp():
    # Production calls the reader under the FirestoreContentionExhausted
    # isinstance arm; the reader itself is stamp-shaped, not type-bound.
    foreign = ValueError('foreign carrier')
    foreign.retry_after = 2.0
    assert pull_contention_storm_after(foreign) == 2.0


def test_reader_horizon_constant_is_the_documented_lane_cap():
    assert CONTENTION_BACKOFF_CAP_SECONDS == 30.0


# ---------------------------------------------------------------------------
# pull_backoff_delay: the ladder raised to the measured storm
# ---------------------------------------------------------------------------


def test_delay_ladder_first_rung_bounds():
    assert delay(1, 0.0, 0.5) == 0.5
    assert delay(1, 0.0, 1.0) == 1.0


def test_delay_ladder_doubles_per_failure():
    assert delay(2, 0.0, 0.5) == 1.0
    assert delay(2, 0.0, 1.0) == 2.0
    assert delay(3, 0.0, 1.0) == 4.0
    assert delay(4, 0.0, 0.5) == 4.0


def test_delay_ladder_fifth_rung_and_beyond():
    assert delay(6, 0.0, 1.0) == 30.0
    assert delay(7, 0.0, 1.0) == 30.0
    assert delay(32, 0.0, 1.0) == 30.0


def test_delay_storm_raises_the_floor():
    assert delay(1, 3.5, 0.5) == 3.5
    assert delay(2, 2.5, 0.5) == 2.5
    assert delay(1, 30.0, 0.5) == 30.0


def test_delay_ladder_wins_below_the_storm_floor():
    assert delay(3, 0.25, 1.0) == 4.0
    assert delay(1, 0.4, 1.0) == 1.0
    assert delay(1, 0.5, 1.0) == 1.0  # floor at the rung: the ladder value stands


def test_delay_storm_never_extends_past_the_horizon():
    assert delay(1, 1e9, 0.5) == 30.0
    assert delay(2, 1e9, 1.0) == 30.0
    assert delay(32, 1e9, 0.5) == 30.0


def test_delay_hostile_failures_collapse_to_the_first_rung():
    assert delay(0, 0.0, 0.5) == 0.5
    assert delay(-3, 0.0, 0.5) == 0.5
    assert delay(True, 0.0, 0.5) == 0.5
    assert delay('2', 0.0, 0.5) == 0.5
    assert delay(None, 0.0, 0.5) == 0.5
    assert delay(2.0, 0.0, 0.5) == 0.5


def test_delay_hostile_jitter_collapses_to_the_jitter_free_factor():
    assert delay(1, 0.0, None) == 1.0
    assert delay(1, 0.0, 'x') == 1.0
    assert delay(1, 0.0, float('nan')) == 1.0
    assert delay(1, 0.0, float('inf')) == 1.0
    assert delay(1, 0.0, True) == 1.0
    assert delay(1, 0.0, False) == 1.0


def test_delay_jitter_clamps_into_the_documented_band():
    assert delay(1, 0.0, 0.25) == 0.5
    assert delay(1, 0.0, 0.0) == 0.5
    assert delay(1, 0.0, -1.0) == 0.5
    assert delay(1, 0.0, 1.5) == 1.0
    assert delay(1, 0.0, 2) == 1.0


def test_delay_jitter_band_bounds_are_exact():
    assert delay(1, 0.0, 0.5) == 0.5
    assert delay(1, 0.0, 1.0) == 1.0


def test_delay_is_exact_at_every_documented_rung():
    # The ladder arithmetic is dyadic: every documented rung times a band
    # jitter is exactly representable, so the pins are equalities.
    for failures, jitter, expected in [
        (1, 0.5, 0.5),
        (2, 0.5, 1.0),
        (3, 0.5, 2.0),
        (4, 0.5, 4.0),
        (5, 0.5, 8.0),
        (6, 0.5, 15.0),  # rung 6 is 2^5 = 32, capped to 30 before the jitter
        (7, 0.5, 15.0),
        (1, 1.0, 1.0),
        (2, 1.0, 2.0),
        (3, 1.0, 4.0),
        (4, 1.0, 8.0),
        (5, 1.0, 16.0),
        (6, 1.0, 30.0),
    ]:
        assert delay(failures, 0.0, jitter) == expected


def test_delay_storm_floor_is_exact_for_stamped_windows():
    for failures, storm, jitter, expected in [
        (1, 0.5, 0.5, 0.5),  # equal: the ladder stands
        (1, 0.75, 0.5, 0.75),
        (1, 4.0, 0.5, 4.0),
        (4, 4.0, 0.5, 4.0),  # ladder 4.0 * 0.5 = 2.0 < 4.0
        (6, 40.0, 1.0, 30.0),  # rung 6 is 2^5 = 32, capped to 30; storm beyond the horizon
    ]:
        assert delay(failures, storm, jitter) == expected


def test_delay_cap_interaction_ladder_and_storm_both_clamped():
    assert delay(6, 0.0, 1.0) == 30.0  # rung 32 -> ladder cap
    assert delay(6, 40.0, 1.0) == 30.0  # storm above cap -> horizon
    assert delay(6, 4.0, 1.0) == 30.0  # rung 32 -> ladder cap, real storm below it


# ---------------------------------------------------------------------------
# Scheduler.pull: the armed state consumes the measured window
# ---------------------------------------------------------------------------


def _queue(monkeypatch, now, randomness=0.0):
    store_hits = []

    class _Store:
        def run(self, body, *, operation=None):
            store_hits.append(operation)
            return body(None)

    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: randomness)
    return Scheduler(_Store())


def test_pull_arms_the_stamped_window_not_the_bare_ladder(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    lease = LeasedWork(item('leased'), 'synthetic-token', 1, 120.0)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[[lease], exhausted(3.5)]))

    assert queue.pull(0, 2) == [lease]
    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 103.5
    assert queue._contention_failures == 1


def test_pull_stamped_below_the_ladder_keeps_the_ladder_rung(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[exhausted(0.25)]))

    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 100.5


def test_pull_capped_stamp_lands_at_the_horizon(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[exhausted(1e9)]))

    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 130.0


def test_pull_int_stamp_lands_at_the_window(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[exhausted(4)]))

    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 104.0


def test_pull_without_a_stamp_keeps_the_documented_ladder(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[exhausted(None)]))

    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 100.5


def test_pull_hostile_stamp_keeps_the_documented_ladder(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[exhausted(float('nan'))]))

    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 100.5


def test_pull_second_failure_stacks_the_next_window(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    monkeypatch.setattr(
        queue,
        '_pull_one',
        Mock(side_effect=[exhausted(None), exhausted(2.5)]),
    )

    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 100.5
    assert queue.pull(100) == []  # inside the backoff: suppressed, no third attempt
    assert queue._contention_failures == 1
    now[0] = 100.5
    assert queue.pull(1) == []  # second chain exhausts with a 2.5s stamp
    # Ladder rung two (2 * 0.5 = 1.0) loses to the 2.5s measured window.
    assert queue._contention_backoff_until == 103.0
    assert queue._contention_failures == 2


def test_pull_stamped_backoff_still_returns_prior_leases(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    lease = LeasedWork(item('leased'), 'synthetic-token', 1, 120.0)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[[lease], exhausted(3.5)]))

    assert queue.pull(0, 2) == [lease]
    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 103.5


def test_pull_clean_window_after_a_stamped_backoff_resets_the_state(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    monkeypatch.setattr(queue, '_pull_one', Mock(side_effect=[exhausted(3.5), []]))

    assert queue.pull(1) == []
    assert queue._contention_backoff_until == 103.5
    now[0] = 103.5
    assert queue.pull(1) == []
    assert queue._contention_failures == 0
    assert queue._contention_backoff_until == 0.0


def test_pull_suppresses_reentry_inside_the_stamped_window(monkeypatch):
    now = [100.0]
    queue = _queue(monkeypatch, now)
    pull_one = Mock(side_effect=[exhausted(3.5), []])
    monkeypatch.setattr(queue, '_pull_one', pull_one)

    assert queue.pull(1) == []
    now[0] = 101.0  # inside the 3.5s window
    assert queue.pull(1) == []
    assert pull_one.call_count == 1
    now[0] = 103.5  # window over
    assert queue.pull(1) == []
    assert pull_one.call_count == 2


# ---------------------------------------------------------------------------
# The scanner sees the state-armed backoff as a wait
# ---------------------------------------------------------------------------


ARM_SURFACE_SOURCE = """
class Shard:
    def pull(self, error):
        try:
            return work()
        except FirestoreContentionExhausted:
            with lock:
                self._contention_backoff_until = now() + delay
            return []
"""


def test_scanner_flags_an_armed_backoff_without_alignment():
    verdicts = fixture.catalog_source(ARM_SURFACE_SOURCE, 'synthetic.py')
    assert verdicts['Shard.pull'] == (
        'bare contention re-offer: Shard.pull catches/classifies a contention '
        'loss and waits 1x without consuming the measured storm window'
    )


ALIGNED_BY_HELPER_SOURCE = """
class Shard:
    def pull(self, error):
        try:
            return work()
        except FirestoreContentionExhausted:
            with lock:
                storm = pull_contention_storm_after(error)
                self._contention_backoff_until = now() + delay
            return []
"""


def test_scanner_clears_an_arm_that_consumes_the_helper():
    assert fixture.catalog_source(ALIGNED_BY_HELPER_SOURCE, 'synthetic.py')['Shard.pull'] is None


ALIGNED_BY_STAMP_SOURCE = """
class Shard:
    def pull(self, error):
        try:
            return work()
        except FirestoreContentionExhausted:
            with lock:
                self._contention_backoff_until = now() + error.retry_after
            return []
"""


def test_scanner_clears_an_arm_that_reads_the_stamped_window():
    assert fixture.catalog_source(ALIGNED_BY_STAMP_SOURCE, 'synthetic.py')['Shard.pull'] is None


LITERAL_ZERO_CLEAR_SOURCE = """
class Shard:
    def __init__(self):
        self._contention_backoff_until = 0.0

    def reset(self):
        self._contention_backoff_until = 0

    def pull(self, error):
        try:
            return work()
        except FirestoreContentionExhausted:
            return []
"""


def test_scanner_does_not_count_literal_zero_clears_as_waits():
    verdicts = fixture.catalog_source(LITERAL_ZERO_CLEAR_SOURCE, 'synthetic.py')
    assert verdicts['Shard.__init__'] is None
    assert verdicts['Shard.reset'] is None
    assert verdicts['Shard.pull'] is None


AUGMENTED_ARM_SOURCE = """
class Shard:
    def pull(self, error):
        try:
            return work()
        except FirestoreContentionExhausted:
            self._contention_backoff_until += residual
            return []
"""


def test_scanner_counts_an_augmented_arm_as_a_wait():
    assert fixture.catalog_source(AUGMENTED_ARM_SOURCE, 'synthetic.py')['Shard.pull'] == (
        'bare contention re-offer: Shard.pull catches/classifies a contention '
        'loss and waits 1x without consuming the measured storm window'
    )


UNRELATED_ASSIGNMENT_SOURCE = """
class Shard:
    def pull(self, error):
        try:
            return work()
        except FirestoreContentionExhausted:
            self._attempts_until = self._attempts_until + 1
            return []
"""


def test_scanner_ignores_assignments_to_unrelated_names():
    assert fixture.catalog_source(UNRELATED_ASSIGNMENT_SOURCE, 'synthetic.py')['Shard.pull'] is None


ANNOTATED_ARM_SOURCE = """
class Shard:
    def pull(self, error) -> None:
        try:
            return work()
        except FirestoreContentionExhausted:
            self._contention_backoff_until: float = now() + delay
            return []
"""


def test_scanner_counts_an_annotated_arm_as_a_wait():
    assert fixture.catalog_source(ANNOTATED_ARM_SOURCE, 'synthetic.py')['Shard.pull'] == (
        'bare contention re-offer: Shard.pull catches/classifies a contention '
        'loss and waits 1x without consuming the measured storm window'
    )


def test_family_fixed_posture_stays_clean_with_the_pull_lane_landed():
    assert fixture.fixed_findings() == {}


def test_family_ablated_blackout_is_the_restrike_lane_plus_the_pull_lane():
    assert set(fixture.ablated_findings()) == set(fixture.EXPECTED_ABLATED_FLIPS)


def test_real_pull_surface_is_clean_when_landed_and_flagged_when_dealigned():
    assert fixture.finding_for(fixture.FIXED, 'utils/batch_pipeline/scheduler.py', 'Scheduler.pull') is None
    assert fixture.finding_for(fixture.ABLATED, 'utils/batch_pipeline/scheduler.py', 'Scheduler.pull') == (
        'bare contention re-offer: Scheduler.pull catches/classifies a contention '
        'loss and waits 1x without consuming the measured storm window'
    )


def test_family_inventory_still_judges_every_function():
    assert len(fixture.inventory()) >= 1000
