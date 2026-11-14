"""Generated grid: pull_storm_reporting band 29. Spec-computed
cell by cell: every literal below was computed from the
documented contract (the reader's hostile-input collapses, the ladder
``min(30.0, 2.0 ** min(failures - 1, 5))`` times a jitter factor clamped
to ``[0.5, 1.0]``, a stamped window raised to a floor under the lane's
horizon) — never from the implementation under test. A cell that fails
means the code drifted from the documented schedule in that case.

Failure-Class: FC-pull-storm-response-and-lease-handoff-booked-as-production-errors
"""

from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.scheduler import pull_backoff_delay, pull_contention_storm_after


def exhausted(stamp=None):
    """A contention exhaustion carrying the case's stamped window."""
    error = FirestoreContentionExhausted('bounded contention')
    if stamp is not None:
        error.retry_after = stamp
    return error


def test_c000000() -> None:
    """failures=1, stamp=true, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000001() -> None:
    """failures=1, stamp=true, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000002() -> None:
    """failures=2, stamp=true, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000003() -> None:
    """failures=2, stamp=true, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000004() -> None:
    """failures=3, stamp=true, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000005() -> None:
    """failures=3, stamp=true, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000006() -> None:
    """failures=4, stamp=true, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000007() -> None:
    """failures=4, stamp=true, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000008() -> None:
    """failures=5, stamp=true, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000009() -> None:
    """failures=5, stamp=true, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000010() -> None:
    """failures=6, stamp=true, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000011() -> None:
    """failures=6, stamp=true, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(True))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000012() -> None:
    """failures=1, stamp=false, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000013() -> None:
    """failures=1, stamp=false, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000014() -> None:
    """failures=2, stamp=false, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000015() -> None:
    """failures=2, stamp=false, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000016() -> None:
    """failures=3, stamp=false, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000017() -> None:
    """failures=3, stamp=false, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000018() -> None:
    """failures=4, stamp=false, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000019() -> None:
    """failures=4, stamp=false, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000020() -> None:
    """failures=5, stamp=false, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000021() -> None:
    """failures=5, stamp=false, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000022() -> None:
    """failures=6, stamp=false, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000023() -> None:
    """failures=6, stamp=false, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(False))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000024() -> None:
    """failures=1, stamp=str, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000025() -> None:
    """failures=1, stamp=str, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000026() -> None:
    """failures=2, stamp=str, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000027() -> None:
    """failures=2, stamp=str, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000028() -> None:
    """failures=3, stamp=str, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000029() -> None:
    """failures=3, stamp=str, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000030() -> None:
    """failures=4, stamp=str, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000031() -> None:
    """failures=4, stamp=str, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000032() -> None:
    """failures=5, stamp=str, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000033() -> None:
    """failures=5, stamp=str, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000034() -> None:
    """failures=6, stamp=str, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000035() -> None:
    """failures=6, stamp=str, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted('1.0'))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000036() -> None:
    """failures=1, stamp=none, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000037() -> None:
    """failures=1, stamp=none, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000038() -> None:
    """failures=2, stamp=none, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000039() -> None:
    """failures=2, stamp=none, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000040() -> None:
    """failures=3, stamp=none, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000041() -> None:
    """failures=3, stamp=none, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000042() -> None:
    """failures=4, stamp=none, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000043() -> None:
    """failures=4, stamp=none, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000044() -> None:
    """failures=5, stamp=none, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000045() -> None:
    """failures=5, stamp=none, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000046() -> None:
    """failures=6, stamp=none, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000047() -> None:
    """failures=6, stamp=none, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(None))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000048() -> None:
    """failures=1, stamp=nan, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000049() -> None:
    """failures=1, stamp=nan, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000050() -> None:
    """failures=2, stamp=nan, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000051() -> None:
    """failures=2, stamp=nan, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000052() -> None:
    """failures=3, stamp=nan, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000053() -> None:
    """failures=3, stamp=nan, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000054() -> None:
    """failures=4, stamp=nan, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000055() -> None:
    """failures=4, stamp=nan, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000056() -> None:
    """failures=5, stamp=nan, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000057() -> None:
    """failures=5, stamp=nan, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000058() -> None:
    """failures=6, stamp=nan, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000059() -> None:
    """failures=6, stamp=nan, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(float('nan')))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000060() -> None:
    """failures=1, stamp=inf, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000061() -> None:
    """failures=1, stamp=inf, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000062() -> None:
    """failures=2, stamp=inf, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000063() -> None:
    """failures=2, stamp=inf, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000064() -> None:
    """failures=3, stamp=inf, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000065() -> None:
    """failures=3, stamp=inf, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000066() -> None:
    """failures=4, stamp=inf, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000067() -> None:
    """failures=4, stamp=inf, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000068() -> None:
    """failures=5, stamp=inf, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000069() -> None:
    """failures=5, stamp=inf, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000070() -> None:
    """failures=6, stamp=inf, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000071() -> None:
    """failures=6, stamp=inf, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(float('inf')))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000072() -> None:
    """failures=1, stamp=neginf, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000073() -> None:
    """failures=1, stamp=neginf, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000074() -> None:
    """failures=2, stamp=neginf, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000075() -> None:
    """failures=2, stamp=neginf, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000076() -> None:
    """failures=3, stamp=neginf, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000077() -> None:
    """failures=3, stamp=neginf, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000078() -> None:
    """failures=4, stamp=neginf, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000079() -> None:
    """failures=4, stamp=neginf, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000080() -> None:
    """failures=5, stamp=neginf, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000081() -> None:
    """failures=5, stamp=neginf, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000082() -> None:
    """failures=6, stamp=neginf, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000083() -> None:
    """failures=6, stamp=neginf, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(float('-inf')))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000084() -> None:
    """failures=1, stamp=zero, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000085() -> None:
    """failures=1, stamp=zero, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000086() -> None:
    """failures=2, stamp=zero, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000087() -> None:
    """failures=2, stamp=zero, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000088() -> None:
    """failures=3, stamp=zero, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000089() -> None:
    """failures=3, stamp=zero, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000090() -> None:
    """failures=4, stamp=zero, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000091() -> None:
    """failures=4, stamp=zero, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000092() -> None:
    """failures=5, stamp=zero, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000093() -> None:
    """failures=5, stamp=zero, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000094() -> None:
    """failures=6, stamp=zero, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000095() -> None:
    """failures=6, stamp=zero, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000096() -> None:
    """failures=1, stamp=negone, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000097() -> None:
    """failures=1, stamp=negone, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000098() -> None:
    """failures=2, stamp=negone, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000099() -> None:
    """failures=2, stamp=negone, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000100() -> None:
    """failures=3, stamp=negone, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000101() -> None:
    """failures=3, stamp=negone, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000102() -> None:
    """failures=4, stamp=negone, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000103() -> None:
    """failures=4, stamp=negone, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000104() -> None:
    """failures=5, stamp=negone, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000105() -> None:
    """failures=5, stamp=negone, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000106() -> None:
    """failures=6, stamp=negone, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000107() -> None:
    """failures=6, stamp=negone, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(-1))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000108() -> None:
    """failures=1, stamp=negzero, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000109() -> None:
    """failures=1, stamp=negzero, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000110() -> None:
    """failures=2, stamp=negzero, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000111() -> None:
    """failures=2, stamp=negzero, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000112() -> None:
    """failures=3, stamp=negzero, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000113() -> None:
    """failures=3, stamp=negzero, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000114() -> None:
    """failures=4, stamp=negzero, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000115() -> None:
    """failures=4, stamp=negzero, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000116() -> None:
    """failures=5, stamp=negzero, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000117() -> None:
    """failures=5, stamp=negzero, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000118() -> None:
    """failures=6, stamp=negzero, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000119() -> None:
    """failures=6, stamp=negzero, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(-0.0))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000120() -> None:
    """failures=1, stamp=huge, jitter=0.5: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 0.5) == 30.0


def test_c000121() -> None:
    """failures=1, stamp=huge, jitter=1.0: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(1, storm, 1.0) == 30.0


def test_c000122() -> None:
    """failures=2, stamp=huge, jitter=0.5: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(2, storm, 0.5) == 30.0


def test_c000123() -> None:
    """failures=2, stamp=huge, jitter=1.0: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(2, storm, 1.0) == 30.0


def test_c000124() -> None:
    """failures=3, stamp=huge, jitter=0.5: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(3, storm, 0.5) == 30.0


def test_c000125() -> None:
    """failures=3, stamp=huge, jitter=1.0: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(3, storm, 1.0) == 30.0


def test_c000126() -> None:
    """failures=4, stamp=huge, jitter=0.5: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(4, storm, 0.5) == 30.0


def test_c000127() -> None:
    """failures=4, stamp=huge, jitter=1.0: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(4, storm, 1.0) == 30.0


def test_c000128() -> None:
    """failures=5, stamp=huge, jitter=0.5: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(5, storm, 0.5) == 30.0


def test_c000129() -> None:
    """failures=5, stamp=huge, jitter=1.0: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(5, storm, 1.0) == 30.0


def test_c000130() -> None:
    """failures=6, stamp=huge, jitter=0.5: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(6, storm, 0.5) == 30.0


def test_c000131() -> None:
    """failures=6, stamp=huge, jitter=1.0: storm 30.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e308))
    assert storm == 30.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000132() -> None:
    """failures=1, stamp=tiny, jitter=0.5: storm 1e-308, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000133() -> None:
    """failures=1, stamp=tiny, jitter=1.0: storm 1e-308, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000134() -> None:
    """failures=2, stamp=tiny, jitter=0.5: storm 1e-308, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000135() -> None:
    """failures=2, stamp=tiny, jitter=1.0: storm 1e-308, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000136() -> None:
    """failures=3, stamp=tiny, jitter=0.5: storm 1e-308, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000137() -> None:
    """failures=3, stamp=tiny, jitter=1.0: storm 1e-308, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000138() -> None:
    """failures=4, stamp=tiny, jitter=0.5: storm 1e-308, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000139() -> None:
    """failures=4, stamp=tiny, jitter=1.0: storm 1e-308, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000140() -> None:
    """failures=5, stamp=tiny, jitter=0.5: storm 1e-308, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000141() -> None:
    """failures=5, stamp=tiny, jitter=1.0: storm 1e-308, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000142() -> None:
    """failures=6, stamp=tiny, jitter=0.5: storm 1e-308, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000143() -> None:
    """failures=6, stamp=tiny, jitter=1.0: storm 1e-308, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1e-308))
    assert storm == 1e-308
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000144() -> None:
    """failures=1, stamp=subminus, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000145() -> None:
    """failures=1, stamp=subminus, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000146() -> None:
    """failures=2, stamp=subminus, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000147() -> None:
    """failures=2, stamp=subminus, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000148() -> None:
    """failures=3, stamp=subminus, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000149() -> None:
    """failures=3, stamp=subminus, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000150() -> None:
    """failures=4, stamp=subminus, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000151() -> None:
    """failures=4, stamp=subminus, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000152() -> None:
    """failures=5, stamp=subminus, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000153() -> None:
    """failures=5, stamp=subminus, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000154() -> None:
    """failures=6, stamp=subminus, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000155() -> None:
    """failures=6, stamp=subminus, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(-1e-308))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0


def test_c000156() -> None:
    """failures=1, stamp=boolint, jitter=0.5: storm 0.0, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 0.5) == 0.5


def test_c000157() -> None:
    """failures=1, stamp=boolint, jitter=1.0: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(1, storm, 1.0) == 1.0


def test_c000158() -> None:
    """failures=2, stamp=boolint, jitter=0.5: storm 0.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 0.5) == 1.0


def test_c000159() -> None:
    """failures=2, stamp=boolint, jitter=1.0: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(2, storm, 1.0) == 2.0


def test_c000160() -> None:
    """failures=3, stamp=boolint, jitter=0.5: storm 0.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 0.5) == 2.0


def test_c000161() -> None:
    """failures=3, stamp=boolint, jitter=1.0: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(3, storm, 1.0) == 4.0


def test_c000162() -> None:
    """failures=4, stamp=boolint, jitter=0.5: storm 0.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 0.5) == 4.0


def test_c000163() -> None:
    """failures=4, stamp=boolint, jitter=1.0: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(4, storm, 1.0) == 8.0


def test_c000164() -> None:
    """failures=5, stamp=boolint, jitter=0.5: storm 0.0, delay 8.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 0.5) == 8.0


def test_c000165() -> None:
    """failures=5, stamp=boolint, jitter=1.0: storm 0.0, delay 16.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(5, storm, 1.0) == 16.0


def test_c000166() -> None:
    """failures=6, stamp=boolint, jitter=0.5: storm 0.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 0.5) == 15.0


def test_c000167() -> None:
    """failures=6, stamp=boolint, jitter=1.0: storm 0.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1 == 1))
    assert storm == 0.0
    assert pull_backoff_delay(6, storm, 1.0) == 30.0
