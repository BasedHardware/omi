"""Storm stamp reader grid: every (stamp shape, error carrier) cell.

``pull_contention_storm_after`` reads the stamped window off whichever error carries
one and collapses every hostile shape to ``0.0``. This grid pins the full cross-product:
40 stamp shapes x 5 error carriers = 200 cells, each asserting the reader output and
the first-rung delay it composes to.

Every expected value in this file is a literal transcribed from the
documented contract (the ladder ``min(30.0, 2.0 ** min(failures - 1, 5))``
times a jitter factor in ``[0.5, 1.0]``, a stamped window raised to a floor
under the lane's ``CONTENTION_BACKOFF_CAP_SECONDS`` horizon, the reader's
hostile-input collapses) — computed off-tree from the spec, never from the
implementation under test. A cell that fails means the code drifted from
the documented schedule in that case.

Failure-Class: FC-pull-backoff-collides-inside-the-armed-storm-window
"""

from unittest.mock import Mock

from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.scheduler import pull_backoff_delay, pull_contention_storm_after


class _SubExhausted(FirestoreContentionExhausted):
    """A worker-family subclass: same stamp contract, narrower type."""


def _stamped(error, stamp):
    if stamp is not None:
        error.retry_after = stamp
    return error


def carry_exhausted(stamp=None):
    return _stamped(FirestoreContentionExhausted('bounded contention'), stamp)


def carry_subclass(stamp=None):
    return _stamped(_SubExhausted('bounded contention'), stamp)


def carry_value_error(stamp=None):
    return _stamped(ValueError('foreign carrier'), stamp)


def carry_runtime_error(stamp=None):
    return _stamped(RuntimeError('foreign carrier'), stamp)


def carry_key_error(stamp=None):
    return _stamped(KeyError('foreign carrier'), stamp)


def test_stamp_exhausted_00() -> None:
    """carrier=exhausted, stamp=no-stamp: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted())
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_01() -> None:
    """carrier=exhausted, stamp=None: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_02() -> None:
    """carrier=exhausted, stamp=True: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_03() -> None:
    """carrier=exhausted, stamp=False: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_04() -> None:
    """carrier=exhausted, stamp=int-0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_05() -> None:
    """carrier=exhausted, stamp=float-0.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(0.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_06() -> None:
    """carrier=exhausted, stamp=int-minus-1: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_07() -> None:
    """carrier=exhausted, stamp=float-minus-0.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(-0.5))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_08() -> None:
    """carrier=exhausted, stamp=minus-1e9: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(-1000000000.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_09() -> None:
    """carrier=exhausted, stamp=nan: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_10() -> None:
    """carrier=exhausted, stamp=inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_11() -> None:
    """carrier=exhausted, stamp=minus-inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_12() -> None:
    """carrier=exhausted, stamp=empty-str: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(''))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_13() -> None:
    """carrier=exhausted, stamp=str-3.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted('3.5'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_14() -> None:
    """carrier=exhausted, stamp=str-abc: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted('abc'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_15() -> None:
    """carrier=exhausted, stamp=list-2.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted([2.0]))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_16() -> None:
    """carrier=exhausted, stamp=empty-dict: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted({}))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_17() -> None:
    """carrier=exhausted, stamp=empty-tuple: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(()))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_18() -> None:
    """carrier=exhausted, stamp=1e-12: reader 1e-12, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(1e-12))
    assert storm == 1e-12
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_19() -> None:
    """carrier=exhausted, stamp=1e-09: reader 1e-09, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(1e-09))
    assert storm == 1e-09
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_20() -> None:
    """carrier=exhausted, stamp=0.1: reader 0.1, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_21() -> None:
    """carrier=exhausted, stamp=0.2: reader 0.2, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_22() -> None:
    """carrier=exhausted, stamp=0.25: reader 0.25, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(0.25))
    assert storm == 0.25
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_23() -> None:
    """carrier=exhausted, stamp=0.3: reader 0.3, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_24() -> None:
    """carrier=exhausted, stamp=0.5: reader 0.5, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_25() -> None:
    """carrier=exhausted, stamp=0.75: reader 0.75, first-rung delay 0.75."""
    storm = pull_contention_storm_after(carry_exhausted(0.75))
    assert storm == 0.75
    assert pull_backoff_delay(1, storm, 0.5) == 0.75


def test_stamp_exhausted_26() -> None:
    """carrier=exhausted, stamp=int-1: reader 1.0, first-rung delay 1.0."""
    storm = pull_contention_storm_after(carry_exhausted(1))
    assert storm == 1.0
    assert pull_backoff_delay(1, storm, 0.5) == 1.0


def test_stamp_exhausted_27() -> None:
    """carrier=exhausted, stamp=1.5: reader 1.5, first-rung delay 1.5."""
    storm = pull_contention_storm_after(carry_exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(1, storm, 0.5) == 1.5


def test_stamp_exhausted_28() -> None:
    """carrier=exhausted, stamp=int-2: reader 2.0, first-rung delay 2.0."""
    storm = pull_contention_storm_after(carry_exhausted(2))
    assert storm == 2.0
    assert pull_backoff_delay(1, storm, 0.5) == 2.0


def test_stamp_exhausted_29() -> None:
    """carrier=exhausted, stamp=2.5: reader 2.5, first-rung delay 2.5."""
    storm = pull_contention_storm_after(carry_exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(1, storm, 0.5) == 2.5


def test_stamp_exhausted_30() -> None:
    """carrier=exhausted, stamp=int-3: reader 3.0, first-rung delay 3.0."""
    storm = pull_contention_storm_after(carry_exhausted(3))
    assert storm == 3.0
    assert pull_backoff_delay(1, storm, 0.5) == 3.0


def test_stamp_exhausted_31() -> None:
    """carrier=exhausted, stamp=3.5: reader 3.5, first-rung delay 3.5."""
    storm = pull_contention_storm_after(carry_exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(1, storm, 0.5) == 3.5


def test_stamp_exhausted_32() -> None:
    """carrier=exhausted, stamp=4.0: reader 4.0, first-rung delay 4.0."""
    storm = pull_contention_storm_after(carry_exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(1, storm, 0.5) == 4.0


def test_stamp_exhausted_33() -> None:
    """carrier=exhausted, stamp=int-5: reader 5.0, first-rung delay 5.0."""
    storm = pull_contention_storm_after(carry_exhausted(5))
    assert storm == 5.0
    assert pull_backoff_delay(1, storm, 0.5) == 5.0


def test_stamp_exhausted_34() -> None:
    """carrier=exhausted, stamp=int-8: reader 8.0, first-rung delay 8.0."""
    storm = pull_contention_storm_after(carry_exhausted(8))
    assert storm == 8.0
    assert pull_backoff_delay(1, storm, 0.5) == 8.0


def test_stamp_exhausted_35() -> None:
    """carrier=exhausted, stamp=int-16: reader 16.0, first-rung delay 16.0."""
    storm = pull_contention_storm_after(carry_exhausted(16))
    assert storm == 16.0
    assert pull_backoff_delay(1, storm, 0.5) == 16.0


def test_stamp_exhausted_36() -> None:
    """carrier=exhausted, stamp=29.5: reader 29.5, first-rung delay 29.5."""
    storm = pull_contention_storm_after(carry_exhausted(29.5))
    assert storm == 29.5
    assert pull_backoff_delay(1, storm, 0.5) == 29.5


def test_stamp_exhausted_37() -> None:
    """carrier=exhausted, stamp=29.999999: reader 29.999999, first-rung delay 29.999999."""
    storm = pull_contention_storm_after(carry_exhausted(29.999999))
    assert storm == 29.999999
    assert pull_backoff_delay(1, storm, 0.5) == 29.999999


def test_stamp_exhausted_38() -> None:
    """carrier=exhausted, stamp=30.0: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_exhausted(30.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_exhausted_39() -> None:
    """carrier=exhausted, stamp=1e9: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_exhausted(1000000000.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_exhausted_subclass_00() -> None:
    """carrier=exhausted-subclass, stamp=no-stamp: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass())
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_01() -> None:
    """carrier=exhausted-subclass, stamp=None: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(None))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_02() -> None:
    """carrier=exhausted-subclass, stamp=True: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(True))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_03() -> None:
    """carrier=exhausted-subclass, stamp=False: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(False))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_04() -> None:
    """carrier=exhausted-subclass, stamp=int-0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_05() -> None:
    """carrier=exhausted-subclass, stamp=float-0.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(0.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_06() -> None:
    """carrier=exhausted-subclass, stamp=int-minus-1: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(-1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_07() -> None:
    """carrier=exhausted-subclass, stamp=float-minus-0.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(-0.5))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_08() -> None:
    """carrier=exhausted-subclass, stamp=minus-1e9: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(-1000000000.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_09() -> None:
    """carrier=exhausted-subclass, stamp=nan: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_10() -> None:
    """carrier=exhausted-subclass, stamp=inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_11() -> None:
    """carrier=exhausted-subclass, stamp=minus-inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_12() -> None:
    """carrier=exhausted-subclass, stamp=empty-str: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(''))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_13() -> None:
    """carrier=exhausted-subclass, stamp=str-3.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass('3.5'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_14() -> None:
    """carrier=exhausted-subclass, stamp=str-abc: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass('abc'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_15() -> None:
    """carrier=exhausted-subclass, stamp=list-2.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass([2.0]))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_16() -> None:
    """carrier=exhausted-subclass, stamp=empty-dict: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass({}))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_17() -> None:
    """carrier=exhausted-subclass, stamp=empty-tuple: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(()))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_18() -> None:
    """carrier=exhausted-subclass, stamp=1e-12: reader 1e-12, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(1e-12))
    assert storm == 1e-12
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_19() -> None:
    """carrier=exhausted-subclass, stamp=1e-09: reader 1e-09, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(1e-09))
    assert storm == 1e-09
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_20() -> None:
    """carrier=exhausted-subclass, stamp=0.1: reader 0.1, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_21() -> None:
    """carrier=exhausted-subclass, stamp=0.2: reader 0.2, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_22() -> None:
    """carrier=exhausted-subclass, stamp=0.25: reader 0.25, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(0.25))
    assert storm == 0.25
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_23() -> None:
    """carrier=exhausted-subclass, stamp=0.3: reader 0.3, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_24() -> None:
    """carrier=exhausted-subclass, stamp=0.5: reader 0.5, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_subclass(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_exhausted_subclass_25() -> None:
    """carrier=exhausted-subclass, stamp=0.75: reader 0.75, first-rung delay 0.75."""
    storm = pull_contention_storm_after(carry_subclass(0.75))
    assert storm == 0.75
    assert pull_backoff_delay(1, storm, 0.5) == 0.75


def test_stamp_exhausted_subclass_26() -> None:
    """carrier=exhausted-subclass, stamp=int-1: reader 1.0, first-rung delay 1.0."""
    storm = pull_contention_storm_after(carry_subclass(1))
    assert storm == 1.0
    assert pull_backoff_delay(1, storm, 0.5) == 1.0


def test_stamp_exhausted_subclass_27() -> None:
    """carrier=exhausted-subclass, stamp=1.5: reader 1.5, first-rung delay 1.5."""
    storm = pull_contention_storm_after(carry_subclass(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(1, storm, 0.5) == 1.5


def test_stamp_exhausted_subclass_28() -> None:
    """carrier=exhausted-subclass, stamp=int-2: reader 2.0, first-rung delay 2.0."""
    storm = pull_contention_storm_after(carry_subclass(2))
    assert storm == 2.0
    assert pull_backoff_delay(1, storm, 0.5) == 2.0


def test_stamp_exhausted_subclass_29() -> None:
    """carrier=exhausted-subclass, stamp=2.5: reader 2.5, first-rung delay 2.5."""
    storm = pull_contention_storm_after(carry_subclass(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(1, storm, 0.5) == 2.5


def test_stamp_exhausted_subclass_30() -> None:
    """carrier=exhausted-subclass, stamp=int-3: reader 3.0, first-rung delay 3.0."""
    storm = pull_contention_storm_after(carry_subclass(3))
    assert storm == 3.0
    assert pull_backoff_delay(1, storm, 0.5) == 3.0


def test_stamp_exhausted_subclass_31() -> None:
    """carrier=exhausted-subclass, stamp=3.5: reader 3.5, first-rung delay 3.5."""
    storm = pull_contention_storm_after(carry_subclass(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(1, storm, 0.5) == 3.5


def test_stamp_exhausted_subclass_32() -> None:
    """carrier=exhausted-subclass, stamp=4.0: reader 4.0, first-rung delay 4.0."""
    storm = pull_contention_storm_after(carry_subclass(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(1, storm, 0.5) == 4.0


def test_stamp_exhausted_subclass_33() -> None:
    """carrier=exhausted-subclass, stamp=int-5: reader 5.0, first-rung delay 5.0."""
    storm = pull_contention_storm_after(carry_subclass(5))
    assert storm == 5.0
    assert pull_backoff_delay(1, storm, 0.5) == 5.0


def test_stamp_exhausted_subclass_34() -> None:
    """carrier=exhausted-subclass, stamp=int-8: reader 8.0, first-rung delay 8.0."""
    storm = pull_contention_storm_after(carry_subclass(8))
    assert storm == 8.0
    assert pull_backoff_delay(1, storm, 0.5) == 8.0


def test_stamp_exhausted_subclass_35() -> None:
    """carrier=exhausted-subclass, stamp=int-16: reader 16.0, first-rung delay 16.0."""
    storm = pull_contention_storm_after(carry_subclass(16))
    assert storm == 16.0
    assert pull_backoff_delay(1, storm, 0.5) == 16.0


def test_stamp_exhausted_subclass_36() -> None:
    """carrier=exhausted-subclass, stamp=29.5: reader 29.5, first-rung delay 29.5."""
    storm = pull_contention_storm_after(carry_subclass(29.5))
    assert storm == 29.5
    assert pull_backoff_delay(1, storm, 0.5) == 29.5


def test_stamp_exhausted_subclass_37() -> None:
    """carrier=exhausted-subclass, stamp=29.999999: reader 29.999999, first-rung delay 29.999999."""
    storm = pull_contention_storm_after(carry_subclass(29.999999))
    assert storm == 29.999999
    assert pull_backoff_delay(1, storm, 0.5) == 29.999999


def test_stamp_exhausted_subclass_38() -> None:
    """carrier=exhausted-subclass, stamp=30.0: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_subclass(30.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_exhausted_subclass_39() -> None:
    """carrier=exhausted-subclass, stamp=1e9: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_subclass(1000000000.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_value_error_carrier_00() -> None:
    """carrier=value-error-carrier, stamp=no-stamp: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error())
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_01() -> None:
    """carrier=value-error-carrier, stamp=None: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(None))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_02() -> None:
    """carrier=value-error-carrier, stamp=True: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(True))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_03() -> None:
    """carrier=value-error-carrier, stamp=False: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(False))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_04() -> None:
    """carrier=value-error-carrier, stamp=int-0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_05() -> None:
    """carrier=value-error-carrier, stamp=float-0.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(0.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_06() -> None:
    """carrier=value-error-carrier, stamp=int-minus-1: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(-1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_07() -> None:
    """carrier=value-error-carrier, stamp=float-minus-0.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(-0.5))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_08() -> None:
    """carrier=value-error-carrier, stamp=minus-1e9: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(-1000000000.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_09() -> None:
    """carrier=value-error-carrier, stamp=nan: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_10() -> None:
    """carrier=value-error-carrier, stamp=inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_11() -> None:
    """carrier=value-error-carrier, stamp=minus-inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_12() -> None:
    """carrier=value-error-carrier, stamp=empty-str: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(''))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_13() -> None:
    """carrier=value-error-carrier, stamp=str-3.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error('3.5'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_14() -> None:
    """carrier=value-error-carrier, stamp=str-abc: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error('abc'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_15() -> None:
    """carrier=value-error-carrier, stamp=list-2.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error([2.0]))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_16() -> None:
    """carrier=value-error-carrier, stamp=empty-dict: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error({}))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_17() -> None:
    """carrier=value-error-carrier, stamp=empty-tuple: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(()))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_18() -> None:
    """carrier=value-error-carrier, stamp=1e-12: reader 1e-12, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(1e-12))
    assert storm == 1e-12
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_19() -> None:
    """carrier=value-error-carrier, stamp=1e-09: reader 1e-09, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(1e-09))
    assert storm == 1e-09
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_20() -> None:
    """carrier=value-error-carrier, stamp=0.1: reader 0.1, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_21() -> None:
    """carrier=value-error-carrier, stamp=0.2: reader 0.2, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_22() -> None:
    """carrier=value-error-carrier, stamp=0.25: reader 0.25, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(0.25))
    assert storm == 0.25
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_23() -> None:
    """carrier=value-error-carrier, stamp=0.3: reader 0.3, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_24() -> None:
    """carrier=value-error-carrier, stamp=0.5: reader 0.5, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_value_error(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_value_error_carrier_25() -> None:
    """carrier=value-error-carrier, stamp=0.75: reader 0.75, first-rung delay 0.75."""
    storm = pull_contention_storm_after(carry_value_error(0.75))
    assert storm == 0.75
    assert pull_backoff_delay(1, storm, 0.5) == 0.75


def test_stamp_value_error_carrier_26() -> None:
    """carrier=value-error-carrier, stamp=int-1: reader 1.0, first-rung delay 1.0."""
    storm = pull_contention_storm_after(carry_value_error(1))
    assert storm == 1.0
    assert pull_backoff_delay(1, storm, 0.5) == 1.0


def test_stamp_value_error_carrier_27() -> None:
    """carrier=value-error-carrier, stamp=1.5: reader 1.5, first-rung delay 1.5."""
    storm = pull_contention_storm_after(carry_value_error(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(1, storm, 0.5) == 1.5


def test_stamp_value_error_carrier_28() -> None:
    """carrier=value-error-carrier, stamp=int-2: reader 2.0, first-rung delay 2.0."""
    storm = pull_contention_storm_after(carry_value_error(2))
    assert storm == 2.0
    assert pull_backoff_delay(1, storm, 0.5) == 2.0


def test_stamp_value_error_carrier_29() -> None:
    """carrier=value-error-carrier, stamp=2.5: reader 2.5, first-rung delay 2.5."""
    storm = pull_contention_storm_after(carry_value_error(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(1, storm, 0.5) == 2.5


def test_stamp_value_error_carrier_30() -> None:
    """carrier=value-error-carrier, stamp=int-3: reader 3.0, first-rung delay 3.0."""
    storm = pull_contention_storm_after(carry_value_error(3))
    assert storm == 3.0
    assert pull_backoff_delay(1, storm, 0.5) == 3.0


def test_stamp_value_error_carrier_31() -> None:
    """carrier=value-error-carrier, stamp=3.5: reader 3.5, first-rung delay 3.5."""
    storm = pull_contention_storm_after(carry_value_error(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(1, storm, 0.5) == 3.5


def test_stamp_value_error_carrier_32() -> None:
    """carrier=value-error-carrier, stamp=4.0: reader 4.0, first-rung delay 4.0."""
    storm = pull_contention_storm_after(carry_value_error(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(1, storm, 0.5) == 4.0


def test_stamp_value_error_carrier_33() -> None:
    """carrier=value-error-carrier, stamp=int-5: reader 5.0, first-rung delay 5.0."""
    storm = pull_contention_storm_after(carry_value_error(5))
    assert storm == 5.0
    assert pull_backoff_delay(1, storm, 0.5) == 5.0


def test_stamp_value_error_carrier_34() -> None:
    """carrier=value-error-carrier, stamp=int-8: reader 8.0, first-rung delay 8.0."""
    storm = pull_contention_storm_after(carry_value_error(8))
    assert storm == 8.0
    assert pull_backoff_delay(1, storm, 0.5) == 8.0


def test_stamp_value_error_carrier_35() -> None:
    """carrier=value-error-carrier, stamp=int-16: reader 16.0, first-rung delay 16.0."""
    storm = pull_contention_storm_after(carry_value_error(16))
    assert storm == 16.0
    assert pull_backoff_delay(1, storm, 0.5) == 16.0


def test_stamp_value_error_carrier_36() -> None:
    """carrier=value-error-carrier, stamp=29.5: reader 29.5, first-rung delay 29.5."""
    storm = pull_contention_storm_after(carry_value_error(29.5))
    assert storm == 29.5
    assert pull_backoff_delay(1, storm, 0.5) == 29.5


def test_stamp_value_error_carrier_37() -> None:
    """carrier=value-error-carrier, stamp=29.999999: reader 29.999999, first-rung delay 29.999999."""
    storm = pull_contention_storm_after(carry_value_error(29.999999))
    assert storm == 29.999999
    assert pull_backoff_delay(1, storm, 0.5) == 29.999999


def test_stamp_value_error_carrier_38() -> None:
    """carrier=value-error-carrier, stamp=30.0: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_value_error(30.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_value_error_carrier_39() -> None:
    """carrier=value-error-carrier, stamp=1e9: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_value_error(1000000000.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_runtime_error_carrier_00() -> None:
    """carrier=runtime-error-carrier, stamp=no-stamp: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error())
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_01() -> None:
    """carrier=runtime-error-carrier, stamp=None: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(None))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_02() -> None:
    """carrier=runtime-error-carrier, stamp=True: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(True))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_03() -> None:
    """carrier=runtime-error-carrier, stamp=False: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(False))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_04() -> None:
    """carrier=runtime-error-carrier, stamp=int-0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_05() -> None:
    """carrier=runtime-error-carrier, stamp=float-0.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(0.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_06() -> None:
    """carrier=runtime-error-carrier, stamp=int-minus-1: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(-1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_07() -> None:
    """carrier=runtime-error-carrier, stamp=float-minus-0.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(-0.5))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_08() -> None:
    """carrier=runtime-error-carrier, stamp=minus-1e9: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(-1000000000.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_09() -> None:
    """carrier=runtime-error-carrier, stamp=nan: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_10() -> None:
    """carrier=runtime-error-carrier, stamp=inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_11() -> None:
    """carrier=runtime-error-carrier, stamp=minus-inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_12() -> None:
    """carrier=runtime-error-carrier, stamp=empty-str: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(''))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_13() -> None:
    """carrier=runtime-error-carrier, stamp=str-3.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error('3.5'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_14() -> None:
    """carrier=runtime-error-carrier, stamp=str-abc: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error('abc'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_15() -> None:
    """carrier=runtime-error-carrier, stamp=list-2.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error([2.0]))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_16() -> None:
    """carrier=runtime-error-carrier, stamp=empty-dict: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error({}))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_17() -> None:
    """carrier=runtime-error-carrier, stamp=empty-tuple: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(()))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_18() -> None:
    """carrier=runtime-error-carrier, stamp=1e-12: reader 1e-12, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(1e-12))
    assert storm == 1e-12
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_19() -> None:
    """carrier=runtime-error-carrier, stamp=1e-09: reader 1e-09, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(1e-09))
    assert storm == 1e-09
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_20() -> None:
    """carrier=runtime-error-carrier, stamp=0.1: reader 0.1, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_21() -> None:
    """carrier=runtime-error-carrier, stamp=0.2: reader 0.2, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_22() -> None:
    """carrier=runtime-error-carrier, stamp=0.25: reader 0.25, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(0.25))
    assert storm == 0.25
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_23() -> None:
    """carrier=runtime-error-carrier, stamp=0.3: reader 0.3, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_24() -> None:
    """carrier=runtime-error-carrier, stamp=0.5: reader 0.5, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_runtime_error(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_runtime_error_carrier_25() -> None:
    """carrier=runtime-error-carrier, stamp=0.75: reader 0.75, first-rung delay 0.75."""
    storm = pull_contention_storm_after(carry_runtime_error(0.75))
    assert storm == 0.75
    assert pull_backoff_delay(1, storm, 0.5) == 0.75


def test_stamp_runtime_error_carrier_26() -> None:
    """carrier=runtime-error-carrier, stamp=int-1: reader 1.0, first-rung delay 1.0."""
    storm = pull_contention_storm_after(carry_runtime_error(1))
    assert storm == 1.0
    assert pull_backoff_delay(1, storm, 0.5) == 1.0


def test_stamp_runtime_error_carrier_27() -> None:
    """carrier=runtime-error-carrier, stamp=1.5: reader 1.5, first-rung delay 1.5."""
    storm = pull_contention_storm_after(carry_runtime_error(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(1, storm, 0.5) == 1.5


def test_stamp_runtime_error_carrier_28() -> None:
    """carrier=runtime-error-carrier, stamp=int-2: reader 2.0, first-rung delay 2.0."""
    storm = pull_contention_storm_after(carry_runtime_error(2))
    assert storm == 2.0
    assert pull_backoff_delay(1, storm, 0.5) == 2.0


def test_stamp_runtime_error_carrier_29() -> None:
    """carrier=runtime-error-carrier, stamp=2.5: reader 2.5, first-rung delay 2.5."""
    storm = pull_contention_storm_after(carry_runtime_error(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(1, storm, 0.5) == 2.5


def test_stamp_runtime_error_carrier_30() -> None:
    """carrier=runtime-error-carrier, stamp=int-3: reader 3.0, first-rung delay 3.0."""
    storm = pull_contention_storm_after(carry_runtime_error(3))
    assert storm == 3.0
    assert pull_backoff_delay(1, storm, 0.5) == 3.0


def test_stamp_runtime_error_carrier_31() -> None:
    """carrier=runtime-error-carrier, stamp=3.5: reader 3.5, first-rung delay 3.5."""
    storm = pull_contention_storm_after(carry_runtime_error(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(1, storm, 0.5) == 3.5


def test_stamp_runtime_error_carrier_32() -> None:
    """carrier=runtime-error-carrier, stamp=4.0: reader 4.0, first-rung delay 4.0."""
    storm = pull_contention_storm_after(carry_runtime_error(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(1, storm, 0.5) == 4.0


def test_stamp_runtime_error_carrier_33() -> None:
    """carrier=runtime-error-carrier, stamp=int-5: reader 5.0, first-rung delay 5.0."""
    storm = pull_contention_storm_after(carry_runtime_error(5))
    assert storm == 5.0
    assert pull_backoff_delay(1, storm, 0.5) == 5.0


def test_stamp_runtime_error_carrier_34() -> None:
    """carrier=runtime-error-carrier, stamp=int-8: reader 8.0, first-rung delay 8.0."""
    storm = pull_contention_storm_after(carry_runtime_error(8))
    assert storm == 8.0
    assert pull_backoff_delay(1, storm, 0.5) == 8.0


def test_stamp_runtime_error_carrier_35() -> None:
    """carrier=runtime-error-carrier, stamp=int-16: reader 16.0, first-rung delay 16.0."""
    storm = pull_contention_storm_after(carry_runtime_error(16))
    assert storm == 16.0
    assert pull_backoff_delay(1, storm, 0.5) == 16.0


def test_stamp_runtime_error_carrier_36() -> None:
    """carrier=runtime-error-carrier, stamp=29.5: reader 29.5, first-rung delay 29.5."""
    storm = pull_contention_storm_after(carry_runtime_error(29.5))
    assert storm == 29.5
    assert pull_backoff_delay(1, storm, 0.5) == 29.5


def test_stamp_runtime_error_carrier_37() -> None:
    """carrier=runtime-error-carrier, stamp=29.999999: reader 29.999999, first-rung delay 29.999999."""
    storm = pull_contention_storm_after(carry_runtime_error(29.999999))
    assert storm == 29.999999
    assert pull_backoff_delay(1, storm, 0.5) == 29.999999


def test_stamp_runtime_error_carrier_38() -> None:
    """carrier=runtime-error-carrier, stamp=30.0: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_runtime_error(30.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_runtime_error_carrier_39() -> None:
    """carrier=runtime-error-carrier, stamp=1e9: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_runtime_error(1000000000.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_key_error_carrier_00() -> None:
    """carrier=key-error-carrier, stamp=no-stamp: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error())
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_01() -> None:
    """carrier=key-error-carrier, stamp=None: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(None))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_02() -> None:
    """carrier=key-error-carrier, stamp=True: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(True))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_03() -> None:
    """carrier=key-error-carrier, stamp=False: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(False))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_04() -> None:
    """carrier=key-error-carrier, stamp=int-0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_05() -> None:
    """carrier=key-error-carrier, stamp=float-0.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(0.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_06() -> None:
    """carrier=key-error-carrier, stamp=int-minus-1: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(-1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_07() -> None:
    """carrier=key-error-carrier, stamp=float-minus-0.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(-0.5))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_08() -> None:
    """carrier=key-error-carrier, stamp=minus-1e9: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(-1000000000.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_09() -> None:
    """carrier=key-error-carrier, stamp=nan: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_10() -> None:
    """carrier=key-error-carrier, stamp=inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_11() -> None:
    """carrier=key-error-carrier, stamp=minus-inf: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_12() -> None:
    """carrier=key-error-carrier, stamp=empty-str: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(''))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_13() -> None:
    """carrier=key-error-carrier, stamp=str-3.5: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error('3.5'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_14() -> None:
    """carrier=key-error-carrier, stamp=str-abc: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error('abc'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_15() -> None:
    """carrier=key-error-carrier, stamp=list-2.0: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error([2.0]))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_16() -> None:
    """carrier=key-error-carrier, stamp=empty-dict: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error({}))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_17() -> None:
    """carrier=key-error-carrier, stamp=empty-tuple: reader 0.0, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(()))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_18() -> None:
    """carrier=key-error-carrier, stamp=1e-12: reader 1e-12, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(1e-12))
    assert storm == 1e-12
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_19() -> None:
    """carrier=key-error-carrier, stamp=1e-09: reader 1e-09, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(1e-09))
    assert storm == 1e-09
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_20() -> None:
    """carrier=key-error-carrier, stamp=0.1: reader 0.1, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_21() -> None:
    """carrier=key-error-carrier, stamp=0.2: reader 0.2, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_22() -> None:
    """carrier=key-error-carrier, stamp=0.25: reader 0.25, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(0.25))
    assert storm == 0.25
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_23() -> None:
    """carrier=key-error-carrier, stamp=0.3: reader 0.3, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_24() -> None:
    """carrier=key-error-carrier, stamp=0.5: reader 0.5, first-rung delay 0.5."""
    storm = pull_contention_storm_after(carry_key_error(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_stamp_key_error_carrier_25() -> None:
    """carrier=key-error-carrier, stamp=0.75: reader 0.75, first-rung delay 0.75."""
    storm = pull_contention_storm_after(carry_key_error(0.75))
    assert storm == 0.75
    assert pull_backoff_delay(1, storm, 0.5) == 0.75


def test_stamp_key_error_carrier_26() -> None:
    """carrier=key-error-carrier, stamp=int-1: reader 1.0, first-rung delay 1.0."""
    storm = pull_contention_storm_after(carry_key_error(1))
    assert storm == 1.0
    assert pull_backoff_delay(1, storm, 0.5) == 1.0


def test_stamp_key_error_carrier_27() -> None:
    """carrier=key-error-carrier, stamp=1.5: reader 1.5, first-rung delay 1.5."""
    storm = pull_contention_storm_after(carry_key_error(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(1, storm, 0.5) == 1.5


def test_stamp_key_error_carrier_28() -> None:
    """carrier=key-error-carrier, stamp=int-2: reader 2.0, first-rung delay 2.0."""
    storm = pull_contention_storm_after(carry_key_error(2))
    assert storm == 2.0
    assert pull_backoff_delay(1, storm, 0.5) == 2.0


def test_stamp_key_error_carrier_29() -> None:
    """carrier=key-error-carrier, stamp=2.5: reader 2.5, first-rung delay 2.5."""
    storm = pull_contention_storm_after(carry_key_error(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(1, storm, 0.5) == 2.5


def test_stamp_key_error_carrier_30() -> None:
    """carrier=key-error-carrier, stamp=int-3: reader 3.0, first-rung delay 3.0."""
    storm = pull_contention_storm_after(carry_key_error(3))
    assert storm == 3.0
    assert pull_backoff_delay(1, storm, 0.5) == 3.0


def test_stamp_key_error_carrier_31() -> None:
    """carrier=key-error-carrier, stamp=3.5: reader 3.5, first-rung delay 3.5."""
    storm = pull_contention_storm_after(carry_key_error(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(1, storm, 0.5) == 3.5


def test_stamp_key_error_carrier_32() -> None:
    """carrier=key-error-carrier, stamp=4.0: reader 4.0, first-rung delay 4.0."""
    storm = pull_contention_storm_after(carry_key_error(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(1, storm, 0.5) == 4.0


def test_stamp_key_error_carrier_33() -> None:
    """carrier=key-error-carrier, stamp=int-5: reader 5.0, first-rung delay 5.0."""
    storm = pull_contention_storm_after(carry_key_error(5))
    assert storm == 5.0
    assert pull_backoff_delay(1, storm, 0.5) == 5.0


def test_stamp_key_error_carrier_34() -> None:
    """carrier=key-error-carrier, stamp=int-8: reader 8.0, first-rung delay 8.0."""
    storm = pull_contention_storm_after(carry_key_error(8))
    assert storm == 8.0
    assert pull_backoff_delay(1, storm, 0.5) == 8.0


def test_stamp_key_error_carrier_35() -> None:
    """carrier=key-error-carrier, stamp=int-16: reader 16.0, first-rung delay 16.0."""
    storm = pull_contention_storm_after(carry_key_error(16))
    assert storm == 16.0
    assert pull_backoff_delay(1, storm, 0.5) == 16.0


def test_stamp_key_error_carrier_36() -> None:
    """carrier=key-error-carrier, stamp=29.5: reader 29.5, first-rung delay 29.5."""
    storm = pull_contention_storm_after(carry_key_error(29.5))
    assert storm == 29.5
    assert pull_backoff_delay(1, storm, 0.5) == 29.5


def test_stamp_key_error_carrier_37() -> None:
    """carrier=key-error-carrier, stamp=29.999999: reader 29.999999, first-rung delay 29.999999."""
    storm = pull_contention_storm_after(carry_key_error(29.999999))
    assert storm == 29.999999
    assert pull_backoff_delay(1, storm, 0.5) == 29.999999


def test_stamp_key_error_carrier_38() -> None:
    """carrier=key-error-carrier, stamp=30.0: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_key_error(30.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_stamp_key_error_carrier_39() -> None:
    """carrier=key-error-carrier, stamp=1e9: reader 30.0, first-rung delay 30.0."""
    storm = pull_contention_storm_after(carry_key_error(1000000000.0))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0
