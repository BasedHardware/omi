"""Generated grid: pull_storm_reporting band 28. Spec-computed
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
    """failures=true, stamp=0.1, jitter=0.5: storm 0.1, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(True, storm, 0.5) == 0.5


def test_c000001() -> None:
    """failures=true, stamp=0.1, jitter=0.625: storm 0.1, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(True, storm, 0.625) == 0.625


def test_c000002() -> None:
    """failures=true, stamp=0.1, jitter=0.75: storm 0.1, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(True, storm, 0.75) == 0.75


def test_c000003() -> None:
    """failures=true, stamp=0.1, jitter=0.875: storm 0.1, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000004() -> None:
    """failures=true, stamp=0.1, jitter=1.0: storm 0.1, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000005() -> None:
    """failures=true, stamp=0.2, jitter=0.5: storm 0.2, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(True, storm, 0.5) == 0.5


def test_c000006() -> None:
    """failures=true, stamp=0.2, jitter=0.625: storm 0.2, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(True, storm, 0.625) == 0.625


def test_c000007() -> None:
    """failures=true, stamp=0.2, jitter=0.75: storm 0.2, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(True, storm, 0.75) == 0.75


def test_c000008() -> None:
    """failures=true, stamp=0.2, jitter=0.875: storm 0.2, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000009() -> None:
    """failures=true, stamp=0.2, jitter=1.0: storm 0.2, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000010() -> None:
    """failures=true, stamp=0.3, jitter=0.5: storm 0.3, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(True, storm, 0.5) == 0.5


def test_c000011() -> None:
    """failures=true, stamp=0.3, jitter=0.625: storm 0.3, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(True, storm, 0.625) == 0.625


def test_c000012() -> None:
    """failures=true, stamp=0.3, jitter=0.75: storm 0.3, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(True, storm, 0.75) == 0.75


def test_c000013() -> None:
    """failures=true, stamp=0.3, jitter=0.875: storm 0.3, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000014() -> None:
    """failures=true, stamp=0.3, jitter=1.0: storm 0.3, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000015() -> None:
    """failures=true, stamp=0.4, jitter=0.5: storm 0.4, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(True, storm, 0.5) == 0.5


def test_c000016() -> None:
    """failures=true, stamp=0.4, jitter=0.625: storm 0.4, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(True, storm, 0.625) == 0.625


def test_c000017() -> None:
    """failures=true, stamp=0.4, jitter=0.75: storm 0.4, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(True, storm, 0.75) == 0.75


def test_c000018() -> None:
    """failures=true, stamp=0.4, jitter=0.875: storm 0.4, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000019() -> None:
    """failures=true, stamp=0.4, jitter=1.0: storm 0.4, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000020() -> None:
    """failures=true, stamp=0.5, jitter=0.5: storm 0.5, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(True, storm, 0.5) == 0.5


def test_c000021() -> None:
    """failures=true, stamp=0.5, jitter=0.625: storm 0.5, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(True, storm, 0.625) == 0.625


def test_c000022() -> None:
    """failures=true, stamp=0.5, jitter=0.75: storm 0.5, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(True, storm, 0.75) == 0.75


def test_c000023() -> None:
    """failures=true, stamp=0.5, jitter=0.875: storm 0.5, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000024() -> None:
    """failures=true, stamp=0.5, jitter=1.0: storm 0.5, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000025() -> None:
    """failures=true, stamp=0.6, jitter=0.5: storm 0.6, delay 0.6."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(True, storm, 0.5) == 0.6


def test_c000026() -> None:
    """failures=true, stamp=0.6, jitter=0.625: storm 0.6, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(True, storm, 0.625) == 0.625


def test_c000027() -> None:
    """failures=true, stamp=0.6, jitter=0.75: storm 0.6, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(True, storm, 0.75) == 0.75


def test_c000028() -> None:
    """failures=true, stamp=0.6, jitter=0.875: storm 0.6, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000029() -> None:
    """failures=true, stamp=0.6, jitter=1.0: storm 0.6, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000030() -> None:
    """failures=true, stamp=0.7, jitter=0.5: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(True, storm, 0.5) == 0.7


def test_c000031() -> None:
    """failures=true, stamp=0.7, jitter=0.625: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(True, storm, 0.625) == 0.7


def test_c000032() -> None:
    """failures=true, stamp=0.7, jitter=0.75: storm 0.7, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(True, storm, 0.75) == 0.75


def test_c000033() -> None:
    """failures=true, stamp=0.7, jitter=0.875: storm 0.7, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000034() -> None:
    """failures=true, stamp=0.7, jitter=1.0: storm 0.7, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000035() -> None:
    """failures=true, stamp=0.8, jitter=0.5: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(True, storm, 0.5) == 0.8


def test_c000036() -> None:
    """failures=true, stamp=0.8, jitter=0.625: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(True, storm, 0.625) == 0.8


def test_c000037() -> None:
    """failures=true, stamp=0.8, jitter=0.75: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(True, storm, 0.75) == 0.8


def test_c000038() -> None:
    """failures=true, stamp=0.8, jitter=0.875: storm 0.8, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(True, storm, 0.875) == 0.875


def test_c000039() -> None:
    """failures=true, stamp=0.8, jitter=1.0: storm 0.8, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000040() -> None:
    """failures=true, stamp=0.9, jitter=0.5: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(True, storm, 0.5) == 0.9


def test_c000041() -> None:
    """failures=true, stamp=0.9, jitter=0.625: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(True, storm, 0.625) == 0.9


def test_c000042() -> None:
    """failures=true, stamp=0.9, jitter=0.75: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(True, storm, 0.75) == 0.9


def test_c000043() -> None:
    """failures=true, stamp=0.9, jitter=0.875: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(True, storm, 0.875) == 0.9


def test_c000044() -> None:
    """failures=true, stamp=0.9, jitter=1.0: storm 0.9, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000045() -> None:
    """failures=true, stamp=1.0, jitter=0.5: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(True, storm, 0.5) == 1.0


def test_c000046() -> None:
    """failures=true, stamp=1.0, jitter=0.625: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(True, storm, 0.625) == 1.0


def test_c000047() -> None:
    """failures=true, stamp=1.0, jitter=0.75: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(True, storm, 0.75) == 1.0


def test_c000048() -> None:
    """failures=true, stamp=1.0, jitter=0.875: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(True, storm, 0.875) == 1.0


def test_c000049() -> None:
    """failures=true, stamp=1.0, jitter=1.0: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(True, storm, 1.0) == 1.0


def test_c000050() -> None:
    """failures=true, stamp=1.1, jitter=0.5: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(True, storm, 0.5) == 1.1


def test_c000051() -> None:
    """failures=true, stamp=1.1, jitter=0.625: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(True, storm, 0.625) == 1.1


def test_c000052() -> None:
    """failures=true, stamp=1.1, jitter=0.75: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(True, storm, 0.75) == 1.1


def test_c000053() -> None:
    """failures=true, stamp=1.1, jitter=0.875: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(True, storm, 0.875) == 1.1


def test_c000054() -> None:
    """failures=true, stamp=1.1, jitter=1.0: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(True, storm, 1.0) == 1.1


def test_c000055() -> None:
    """failures=true, stamp=1.2, jitter=0.5: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(True, storm, 0.5) == 1.2


def test_c000056() -> None:
    """failures=true, stamp=1.2, jitter=0.625: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(True, storm, 0.625) == 1.2


def test_c000057() -> None:
    """failures=true, stamp=1.2, jitter=0.75: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(True, storm, 0.75) == 1.2


def test_c000058() -> None:
    """failures=true, stamp=1.2, jitter=0.875: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(True, storm, 0.875) == 1.2


def test_c000059() -> None:
    """failures=true, stamp=1.2, jitter=1.0: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(True, storm, 1.0) == 1.2


def test_c000060() -> None:
    """failures=true, stamp=1.3, jitter=0.5: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(True, storm, 0.5) == 1.3


def test_c000061() -> None:
    """failures=true, stamp=1.3, jitter=0.625: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(True, storm, 0.625) == 1.3


def test_c000062() -> None:
    """failures=true, stamp=1.3, jitter=0.75: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(True, storm, 0.75) == 1.3


def test_c000063() -> None:
    """failures=true, stamp=1.3, jitter=0.875: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(True, storm, 0.875) == 1.3


def test_c000064() -> None:
    """failures=true, stamp=1.3, jitter=1.0: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(True, storm, 1.0) == 1.3


def test_c000065() -> None:
    """failures=true, stamp=1.4, jitter=0.5: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(True, storm, 0.5) == 1.4


def test_c000066() -> None:
    """failures=true, stamp=1.4, jitter=0.625: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(True, storm, 0.625) == 1.4


def test_c000067() -> None:
    """failures=true, stamp=1.4, jitter=0.75: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(True, storm, 0.75) == 1.4


def test_c000068() -> None:
    """failures=true, stamp=1.4, jitter=0.875: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(True, storm, 0.875) == 1.4


def test_c000069() -> None:
    """failures=true, stamp=1.4, jitter=1.0: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(True, storm, 1.0) == 1.4


def test_c000070() -> None:
    """failures=true, stamp=1.5, jitter=0.5: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(True, storm, 0.5) == 1.5


def test_c000071() -> None:
    """failures=true, stamp=1.5, jitter=0.625: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(True, storm, 0.625) == 1.5


def test_c000072() -> None:
    """failures=true, stamp=1.5, jitter=0.75: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(True, storm, 0.75) == 1.5


def test_c000073() -> None:
    """failures=true, stamp=1.5, jitter=0.875: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(True, storm, 0.875) == 1.5


def test_c000074() -> None:
    """failures=true, stamp=1.5, jitter=1.0: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(True, storm, 1.0) == 1.5


def test_c000075() -> None:
    """failures=true, stamp=1.6, jitter=0.5: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(True, storm, 0.5) == 1.6


def test_c000076() -> None:
    """failures=true, stamp=1.6, jitter=0.625: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(True, storm, 0.625) == 1.6


def test_c000077() -> None:
    """failures=true, stamp=1.6, jitter=0.75: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(True, storm, 0.75) == 1.6


def test_c000078() -> None:
    """failures=true, stamp=1.6, jitter=0.875: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(True, storm, 0.875) == 1.6


def test_c000079() -> None:
    """failures=true, stamp=1.6, jitter=1.0: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(True, storm, 1.0) == 1.6


def test_c000080() -> None:
    """failures=true, stamp=1.7, jitter=0.5: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(True, storm, 0.5) == 1.7


def test_c000081() -> None:
    """failures=true, stamp=1.7, jitter=0.625: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(True, storm, 0.625) == 1.7


def test_c000082() -> None:
    """failures=true, stamp=1.7, jitter=0.75: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(True, storm, 0.75) == 1.7


def test_c000083() -> None:
    """failures=true, stamp=1.7, jitter=0.875: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(True, storm, 0.875) == 1.7


def test_c000084() -> None:
    """failures=true, stamp=1.7, jitter=1.0: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(True, storm, 1.0) == 1.7


def test_c000085() -> None:
    """failures=true, stamp=1.8, jitter=0.5: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(True, storm, 0.5) == 1.8


def test_c000086() -> None:
    """failures=true, stamp=1.8, jitter=0.625: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(True, storm, 0.625) == 1.8


def test_c000087() -> None:
    """failures=true, stamp=1.8, jitter=0.75: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(True, storm, 0.75) == 1.8


def test_c000088() -> None:
    """failures=true, stamp=1.8, jitter=0.875: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(True, storm, 0.875) == 1.8


def test_c000089() -> None:
    """failures=true, stamp=1.8, jitter=1.0: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(True, storm, 1.0) == 1.8


def test_c000090() -> None:
    """failures=true, stamp=1.9, jitter=0.5: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(True, storm, 0.5) == 1.9


def test_c000091() -> None:
    """failures=true, stamp=1.9, jitter=0.625: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(True, storm, 0.625) == 1.9


def test_c000092() -> None:
    """failures=true, stamp=1.9, jitter=0.75: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(True, storm, 0.75) == 1.9


def test_c000093() -> None:
    """failures=true, stamp=1.9, jitter=0.875: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(True, storm, 0.875) == 1.9


def test_c000094() -> None:
    """failures=true, stamp=1.9, jitter=1.0: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(True, storm, 1.0) == 1.9


def test_c000095() -> None:
    """failures=true, stamp=2.0, jitter=0.5: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(True, storm, 0.5) == 2.0


def test_c000096() -> None:
    """failures=true, stamp=2.0, jitter=0.625: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(True, storm, 0.625) == 2.0


def test_c000097() -> None:
    """failures=true, stamp=2.0, jitter=0.75: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(True, storm, 0.75) == 2.0


def test_c000098() -> None:
    """failures=true, stamp=2.0, jitter=0.875: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(True, storm, 0.875) == 2.0


def test_c000099() -> None:
    """failures=true, stamp=2.0, jitter=1.0: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(True, storm, 1.0) == 2.0


def test_c000100() -> None:
    """failures=true, stamp=2.1, jitter=0.5: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(True, storm, 0.5) == 2.1


def test_c000101() -> None:
    """failures=true, stamp=2.1, jitter=0.625: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(True, storm, 0.625) == 2.1


def test_c000102() -> None:
    """failures=true, stamp=2.1, jitter=0.75: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(True, storm, 0.75) == 2.1


def test_c000103() -> None:
    """failures=true, stamp=2.1, jitter=0.875: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(True, storm, 0.875) == 2.1


def test_c000104() -> None:
    """failures=true, stamp=2.1, jitter=1.0: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(True, storm, 1.0) == 2.1


def test_c000105() -> None:
    """failures=true, stamp=2.2, jitter=0.5: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(True, storm, 0.5) == 2.2


def test_c000106() -> None:
    """failures=true, stamp=2.2, jitter=0.625: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(True, storm, 0.625) == 2.2


def test_c000107() -> None:
    """failures=true, stamp=2.2, jitter=0.75: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(True, storm, 0.75) == 2.2


def test_c000108() -> None:
    """failures=true, stamp=2.2, jitter=0.875: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(True, storm, 0.875) == 2.2


def test_c000109() -> None:
    """failures=true, stamp=2.2, jitter=1.0: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(True, storm, 1.0) == 2.2


def test_c000110() -> None:
    """failures=true, stamp=2.3, jitter=0.5: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(True, storm, 0.5) == 2.3


def test_c000111() -> None:
    """failures=true, stamp=2.3, jitter=0.625: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(True, storm, 0.625) == 2.3


def test_c000112() -> None:
    """failures=true, stamp=2.3, jitter=0.75: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(True, storm, 0.75) == 2.3


def test_c000113() -> None:
    """failures=true, stamp=2.3, jitter=0.875: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(True, storm, 0.875) == 2.3


def test_c000114() -> None:
    """failures=true, stamp=2.3, jitter=1.0: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(True, storm, 1.0) == 2.3


def test_c000115() -> None:
    """failures=true, stamp=2.4, jitter=0.5: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(True, storm, 0.5) == 2.4


def test_c000116() -> None:
    """failures=true, stamp=2.4, jitter=0.625: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(True, storm, 0.625) == 2.4


def test_c000117() -> None:
    """failures=true, stamp=2.4, jitter=0.75: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(True, storm, 0.75) == 2.4


def test_c000118() -> None:
    """failures=true, stamp=2.4, jitter=0.875: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(True, storm, 0.875) == 2.4


def test_c000119() -> None:
    """failures=true, stamp=2.4, jitter=1.0: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(True, storm, 1.0) == 2.4


def test_c000120() -> None:
    """failures=true, stamp=2.5, jitter=0.5: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(True, storm, 0.5) == 2.5


def test_c000121() -> None:
    """failures=true, stamp=2.5, jitter=0.625: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(True, storm, 0.625) == 2.5


def test_c000122() -> None:
    """failures=true, stamp=2.5, jitter=0.75: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(True, storm, 0.75) == 2.5


def test_c000123() -> None:
    """failures=true, stamp=2.5, jitter=0.875: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(True, storm, 0.875) == 2.5


def test_c000124() -> None:
    """failures=true, stamp=2.5, jitter=1.0: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(True, storm, 1.0) == 2.5


def test_c000125() -> None:
    """failures=true, stamp=2.6, jitter=0.5: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(True, storm, 0.5) == 2.6


def test_c000126() -> None:
    """failures=true, stamp=2.6, jitter=0.625: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(True, storm, 0.625) == 2.6


def test_c000127() -> None:
    """failures=true, stamp=2.6, jitter=0.75: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(True, storm, 0.75) == 2.6


def test_c000128() -> None:
    """failures=true, stamp=2.6, jitter=0.875: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(True, storm, 0.875) == 2.6


def test_c000129() -> None:
    """failures=true, stamp=2.6, jitter=1.0: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(True, storm, 1.0) == 2.6


def test_c000130() -> None:
    """failures=true, stamp=2.7, jitter=0.5: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(True, storm, 0.5) == 2.7


def test_c000131() -> None:
    """failures=true, stamp=2.7, jitter=0.625: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(True, storm, 0.625) == 2.7


def test_c000132() -> None:
    """failures=true, stamp=2.7, jitter=0.75: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(True, storm, 0.75) == 2.7


def test_c000133() -> None:
    """failures=true, stamp=2.7, jitter=0.875: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(True, storm, 0.875) == 2.7


def test_c000134() -> None:
    """failures=true, stamp=2.7, jitter=1.0: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(True, storm, 1.0) == 2.7


def test_c000135() -> None:
    """failures=true, stamp=2.8, jitter=0.5: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(True, storm, 0.5) == 2.8


def test_c000136() -> None:
    """failures=true, stamp=2.8, jitter=0.625: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(True, storm, 0.625) == 2.8


def test_c000137() -> None:
    """failures=true, stamp=2.8, jitter=0.75: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(True, storm, 0.75) == 2.8


def test_c000138() -> None:
    """failures=true, stamp=2.8, jitter=0.875: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(True, storm, 0.875) == 2.8


def test_c000139() -> None:
    """failures=true, stamp=2.8, jitter=1.0: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(True, storm, 1.0) == 2.8


def test_c000140() -> None:
    """failures=true, stamp=2.9, jitter=0.5: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(True, storm, 0.5) == 2.9


def test_c000141() -> None:
    """failures=true, stamp=2.9, jitter=0.625: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(True, storm, 0.625) == 2.9


def test_c000142() -> None:
    """failures=true, stamp=2.9, jitter=0.75: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(True, storm, 0.75) == 2.9


def test_c000143() -> None:
    """failures=true, stamp=2.9, jitter=0.875: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(True, storm, 0.875) == 2.9


def test_c000144() -> None:
    """failures=true, stamp=2.9, jitter=1.0: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(True, storm, 1.0) == 2.9


def test_c000145() -> None:
    """failures=true, stamp=3.0, jitter=0.5: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(True, storm, 0.5) == 3.0


def test_c000146() -> None:
    """failures=true, stamp=3.0, jitter=0.625: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(True, storm, 0.625) == 3.0


def test_c000147() -> None:
    """failures=true, stamp=3.0, jitter=0.75: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(True, storm, 0.75) == 3.0


def test_c000148() -> None:
    """failures=true, stamp=3.0, jitter=0.875: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(True, storm, 0.875) == 3.0


def test_c000149() -> None:
    """failures=true, stamp=3.0, jitter=1.0: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(True, storm, 1.0) == 3.0


def test_c000150() -> None:
    """failures=true, stamp=3.1, jitter=0.5: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(True, storm, 0.5) == 3.1


def test_c000151() -> None:
    """failures=true, stamp=3.1, jitter=0.625: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(True, storm, 0.625) == 3.1


def test_c000152() -> None:
    """failures=true, stamp=3.1, jitter=0.75: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(True, storm, 0.75) == 3.1


def test_c000153() -> None:
    """failures=true, stamp=3.1, jitter=0.875: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(True, storm, 0.875) == 3.1


def test_c000154() -> None:
    """failures=true, stamp=3.1, jitter=1.0: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(True, storm, 1.0) == 3.1


def test_c000155() -> None:
    """failures=true, stamp=3.2, jitter=0.5: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(True, storm, 0.5) == 3.2


def test_c000156() -> None:
    """failures=true, stamp=3.2, jitter=0.625: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(True, storm, 0.625) == 3.2


def test_c000157() -> None:
    """failures=true, stamp=3.2, jitter=0.75: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(True, storm, 0.75) == 3.2


def test_c000158() -> None:
    """failures=true, stamp=3.2, jitter=0.875: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(True, storm, 0.875) == 3.2


def test_c000159() -> None:
    """failures=true, stamp=3.2, jitter=1.0: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(True, storm, 1.0) == 3.2


def test_c000160() -> None:
    """failures=true, stamp=3.3, jitter=0.5: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(True, storm, 0.5) == 3.3


def test_c000161() -> None:
    """failures=true, stamp=3.3, jitter=0.625: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(True, storm, 0.625) == 3.3


def test_c000162() -> None:
    """failures=true, stamp=3.3, jitter=0.75: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(True, storm, 0.75) == 3.3


def test_c000163() -> None:
    """failures=true, stamp=3.3, jitter=0.875: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(True, storm, 0.875) == 3.3


def test_c000164() -> None:
    """failures=true, stamp=3.3, jitter=1.0: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(True, storm, 1.0) == 3.3


def test_c000165() -> None:
    """failures=true, stamp=3.4, jitter=0.5: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(True, storm, 0.5) == 3.4


def test_c000166() -> None:
    """failures=true, stamp=3.4, jitter=0.625: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(True, storm, 0.625) == 3.4


def test_c000167() -> None:
    """failures=true, stamp=3.4, jitter=0.75: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(True, storm, 0.75) == 3.4


def test_c000168() -> None:
    """failures=true, stamp=3.4, jitter=0.875: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(True, storm, 0.875) == 3.4


def test_c000169() -> None:
    """failures=true, stamp=3.4, jitter=1.0: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(True, storm, 1.0) == 3.4


def test_c000170() -> None:
    """failures=true, stamp=3.5, jitter=0.5: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(True, storm, 0.5) == 3.5


def test_c000171() -> None:
    """failures=true, stamp=3.5, jitter=0.625: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(True, storm, 0.625) == 3.5


def test_c000172() -> None:
    """failures=true, stamp=3.5, jitter=0.75: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(True, storm, 0.75) == 3.5


def test_c000173() -> None:
    """failures=true, stamp=3.5, jitter=0.875: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(True, storm, 0.875) == 3.5


def test_c000174() -> None:
    """failures=true, stamp=3.5, jitter=1.0: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(True, storm, 1.0) == 3.5


def test_c000175() -> None:
    """failures=true, stamp=3.6, jitter=0.5: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(True, storm, 0.5) == 3.6


def test_c000176() -> None:
    """failures=true, stamp=3.6, jitter=0.625: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(True, storm, 0.625) == 3.6


def test_c000177() -> None:
    """failures=true, stamp=3.6, jitter=0.75: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(True, storm, 0.75) == 3.6


def test_c000178() -> None:
    """failures=true, stamp=3.6, jitter=0.875: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(True, storm, 0.875) == 3.6


def test_c000179() -> None:
    """failures=true, stamp=3.6, jitter=1.0: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(True, storm, 1.0) == 3.6


def test_c000180() -> None:
    """failures=true, stamp=3.7, jitter=0.5: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(True, storm, 0.5) == 3.7


def test_c000181() -> None:
    """failures=true, stamp=3.7, jitter=0.625: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(True, storm, 0.625) == 3.7


def test_c000182() -> None:
    """failures=true, stamp=3.7, jitter=0.75: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(True, storm, 0.75) == 3.7


def test_c000183() -> None:
    """failures=true, stamp=3.7, jitter=0.875: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(True, storm, 0.875) == 3.7


def test_c000184() -> None:
    """failures=true, stamp=3.7, jitter=1.0: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(True, storm, 1.0) == 3.7


def test_c000185() -> None:
    """failures=true, stamp=3.8, jitter=0.5: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(True, storm, 0.5) == 3.8


def test_c000186() -> None:
    """failures=true, stamp=3.8, jitter=0.625: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(True, storm, 0.625) == 3.8


def test_c000187() -> None:
    """failures=true, stamp=3.8, jitter=0.75: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(True, storm, 0.75) == 3.8


def test_c000188() -> None:
    """failures=true, stamp=3.8, jitter=0.875: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(True, storm, 0.875) == 3.8


def test_c000189() -> None:
    """failures=true, stamp=3.8, jitter=1.0: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(True, storm, 1.0) == 3.8


def test_c000190() -> None:
    """failures=true, stamp=3.9, jitter=0.5: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(True, storm, 0.5) == 3.9


def test_c000191() -> None:
    """failures=true, stamp=3.9, jitter=0.625: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(True, storm, 0.625) == 3.9


def test_c000192() -> None:
    """failures=true, stamp=3.9, jitter=0.75: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(True, storm, 0.75) == 3.9


def test_c000193() -> None:
    """failures=true, stamp=3.9, jitter=0.875: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(True, storm, 0.875) == 3.9


def test_c000194() -> None:
    """failures=true, stamp=3.9, jitter=1.0: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(True, storm, 1.0) == 3.9


def test_c000195() -> None:
    """failures=true, stamp=4.0, jitter=0.5: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(True, storm, 0.5) == 4.0


def test_c000196() -> None:
    """failures=true, stamp=4.0, jitter=0.625: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(True, storm, 0.625) == 4.0


def test_c000197() -> None:
    """failures=true, stamp=4.0, jitter=0.75: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(True, storm, 0.75) == 4.0


def test_c000198() -> None:
    """failures=true, stamp=4.0, jitter=0.875: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(True, storm, 0.875) == 4.0


def test_c000199() -> None:
    """failures=true, stamp=4.0, jitter=1.0: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(True, storm, 1.0) == 4.0


def test_c000200() -> None:
    """failures=false, stamp=0.1, jitter=0.5: storm 0.1, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(False, storm, 0.5) == 0.5


def test_c000201() -> None:
    """failures=false, stamp=0.1, jitter=0.625: storm 0.1, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(False, storm, 0.625) == 0.625


def test_c000202() -> None:
    """failures=false, stamp=0.1, jitter=0.75: storm 0.1, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(False, storm, 0.75) == 0.75


def test_c000203() -> None:
    """failures=false, stamp=0.1, jitter=0.875: storm 0.1, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000204() -> None:
    """failures=false, stamp=0.1, jitter=1.0: storm 0.1, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000205() -> None:
    """failures=false, stamp=0.2, jitter=0.5: storm 0.2, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(False, storm, 0.5) == 0.5


def test_c000206() -> None:
    """failures=false, stamp=0.2, jitter=0.625: storm 0.2, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(False, storm, 0.625) == 0.625


def test_c000207() -> None:
    """failures=false, stamp=0.2, jitter=0.75: storm 0.2, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(False, storm, 0.75) == 0.75


def test_c000208() -> None:
    """failures=false, stamp=0.2, jitter=0.875: storm 0.2, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000209() -> None:
    """failures=false, stamp=0.2, jitter=1.0: storm 0.2, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000210() -> None:
    """failures=false, stamp=0.3, jitter=0.5: storm 0.3, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(False, storm, 0.5) == 0.5


def test_c000211() -> None:
    """failures=false, stamp=0.3, jitter=0.625: storm 0.3, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(False, storm, 0.625) == 0.625


def test_c000212() -> None:
    """failures=false, stamp=0.3, jitter=0.75: storm 0.3, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(False, storm, 0.75) == 0.75


def test_c000213() -> None:
    """failures=false, stamp=0.3, jitter=0.875: storm 0.3, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000214() -> None:
    """failures=false, stamp=0.3, jitter=1.0: storm 0.3, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000215() -> None:
    """failures=false, stamp=0.4, jitter=0.5: storm 0.4, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(False, storm, 0.5) == 0.5


def test_c000216() -> None:
    """failures=false, stamp=0.4, jitter=0.625: storm 0.4, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(False, storm, 0.625) == 0.625


def test_c000217() -> None:
    """failures=false, stamp=0.4, jitter=0.75: storm 0.4, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(False, storm, 0.75) == 0.75


def test_c000218() -> None:
    """failures=false, stamp=0.4, jitter=0.875: storm 0.4, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000219() -> None:
    """failures=false, stamp=0.4, jitter=1.0: storm 0.4, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000220() -> None:
    """failures=false, stamp=0.5, jitter=0.5: storm 0.5, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(False, storm, 0.5) == 0.5


def test_c000221() -> None:
    """failures=false, stamp=0.5, jitter=0.625: storm 0.5, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(False, storm, 0.625) == 0.625


def test_c000222() -> None:
    """failures=false, stamp=0.5, jitter=0.75: storm 0.5, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(False, storm, 0.75) == 0.75


def test_c000223() -> None:
    """failures=false, stamp=0.5, jitter=0.875: storm 0.5, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000224() -> None:
    """failures=false, stamp=0.5, jitter=1.0: storm 0.5, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000225() -> None:
    """failures=false, stamp=0.6, jitter=0.5: storm 0.6, delay 0.6."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(False, storm, 0.5) == 0.6


def test_c000226() -> None:
    """failures=false, stamp=0.6, jitter=0.625: storm 0.6, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(False, storm, 0.625) == 0.625


def test_c000227() -> None:
    """failures=false, stamp=0.6, jitter=0.75: storm 0.6, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(False, storm, 0.75) == 0.75


def test_c000228() -> None:
    """failures=false, stamp=0.6, jitter=0.875: storm 0.6, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000229() -> None:
    """failures=false, stamp=0.6, jitter=1.0: storm 0.6, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000230() -> None:
    """failures=false, stamp=0.7, jitter=0.5: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(False, storm, 0.5) == 0.7


def test_c000231() -> None:
    """failures=false, stamp=0.7, jitter=0.625: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(False, storm, 0.625) == 0.7


def test_c000232() -> None:
    """failures=false, stamp=0.7, jitter=0.75: storm 0.7, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(False, storm, 0.75) == 0.75


def test_c000233() -> None:
    """failures=false, stamp=0.7, jitter=0.875: storm 0.7, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000234() -> None:
    """failures=false, stamp=0.7, jitter=1.0: storm 0.7, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000235() -> None:
    """failures=false, stamp=0.8, jitter=0.5: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(False, storm, 0.5) == 0.8


def test_c000236() -> None:
    """failures=false, stamp=0.8, jitter=0.625: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(False, storm, 0.625) == 0.8


def test_c000237() -> None:
    """failures=false, stamp=0.8, jitter=0.75: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(False, storm, 0.75) == 0.8


def test_c000238() -> None:
    """failures=false, stamp=0.8, jitter=0.875: storm 0.8, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(False, storm, 0.875) == 0.875


def test_c000239() -> None:
    """failures=false, stamp=0.8, jitter=1.0: storm 0.8, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000240() -> None:
    """failures=false, stamp=0.9, jitter=0.5: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(False, storm, 0.5) == 0.9


def test_c000241() -> None:
    """failures=false, stamp=0.9, jitter=0.625: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(False, storm, 0.625) == 0.9


def test_c000242() -> None:
    """failures=false, stamp=0.9, jitter=0.75: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(False, storm, 0.75) == 0.9


def test_c000243() -> None:
    """failures=false, stamp=0.9, jitter=0.875: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(False, storm, 0.875) == 0.9


def test_c000244() -> None:
    """failures=false, stamp=0.9, jitter=1.0: storm 0.9, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000245() -> None:
    """failures=false, stamp=1.0, jitter=0.5: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(False, storm, 0.5) == 1.0


def test_c000246() -> None:
    """failures=false, stamp=1.0, jitter=0.625: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(False, storm, 0.625) == 1.0


def test_c000247() -> None:
    """failures=false, stamp=1.0, jitter=0.75: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(False, storm, 0.75) == 1.0


def test_c000248() -> None:
    """failures=false, stamp=1.0, jitter=0.875: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(False, storm, 0.875) == 1.0


def test_c000249() -> None:
    """failures=false, stamp=1.0, jitter=1.0: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(False, storm, 1.0) == 1.0


def test_c000250() -> None:
    """failures=false, stamp=1.1, jitter=0.5: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(False, storm, 0.5) == 1.1


def test_c000251() -> None:
    """failures=false, stamp=1.1, jitter=0.625: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(False, storm, 0.625) == 1.1


def test_c000252() -> None:
    """failures=false, stamp=1.1, jitter=0.75: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(False, storm, 0.75) == 1.1


def test_c000253() -> None:
    """failures=false, stamp=1.1, jitter=0.875: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(False, storm, 0.875) == 1.1


def test_c000254() -> None:
    """failures=false, stamp=1.1, jitter=1.0: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(False, storm, 1.0) == 1.1


def test_c000255() -> None:
    """failures=false, stamp=1.2, jitter=0.5: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(False, storm, 0.5) == 1.2


def test_c000256() -> None:
    """failures=false, stamp=1.2, jitter=0.625: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(False, storm, 0.625) == 1.2


def test_c000257() -> None:
    """failures=false, stamp=1.2, jitter=0.75: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(False, storm, 0.75) == 1.2


def test_c000258() -> None:
    """failures=false, stamp=1.2, jitter=0.875: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(False, storm, 0.875) == 1.2


def test_c000259() -> None:
    """failures=false, stamp=1.2, jitter=1.0: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(False, storm, 1.0) == 1.2


def test_c000260() -> None:
    """failures=false, stamp=1.3, jitter=0.5: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(False, storm, 0.5) == 1.3


def test_c000261() -> None:
    """failures=false, stamp=1.3, jitter=0.625: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(False, storm, 0.625) == 1.3


def test_c000262() -> None:
    """failures=false, stamp=1.3, jitter=0.75: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(False, storm, 0.75) == 1.3


def test_c000263() -> None:
    """failures=false, stamp=1.3, jitter=0.875: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(False, storm, 0.875) == 1.3


def test_c000264() -> None:
    """failures=false, stamp=1.3, jitter=1.0: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(False, storm, 1.0) == 1.3


def test_c000265() -> None:
    """failures=false, stamp=1.4, jitter=0.5: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(False, storm, 0.5) == 1.4


def test_c000266() -> None:
    """failures=false, stamp=1.4, jitter=0.625: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(False, storm, 0.625) == 1.4


def test_c000267() -> None:
    """failures=false, stamp=1.4, jitter=0.75: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(False, storm, 0.75) == 1.4


def test_c000268() -> None:
    """failures=false, stamp=1.4, jitter=0.875: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(False, storm, 0.875) == 1.4


def test_c000269() -> None:
    """failures=false, stamp=1.4, jitter=1.0: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(False, storm, 1.0) == 1.4


def test_c000270() -> None:
    """failures=false, stamp=1.5, jitter=0.5: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(False, storm, 0.5) == 1.5


def test_c000271() -> None:
    """failures=false, stamp=1.5, jitter=0.625: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(False, storm, 0.625) == 1.5


def test_c000272() -> None:
    """failures=false, stamp=1.5, jitter=0.75: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(False, storm, 0.75) == 1.5


def test_c000273() -> None:
    """failures=false, stamp=1.5, jitter=0.875: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(False, storm, 0.875) == 1.5


def test_c000274() -> None:
    """failures=false, stamp=1.5, jitter=1.0: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(False, storm, 1.0) == 1.5


def test_c000275() -> None:
    """failures=false, stamp=1.6, jitter=0.5: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(False, storm, 0.5) == 1.6


def test_c000276() -> None:
    """failures=false, stamp=1.6, jitter=0.625: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(False, storm, 0.625) == 1.6


def test_c000277() -> None:
    """failures=false, stamp=1.6, jitter=0.75: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(False, storm, 0.75) == 1.6


def test_c000278() -> None:
    """failures=false, stamp=1.6, jitter=0.875: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(False, storm, 0.875) == 1.6


def test_c000279() -> None:
    """failures=false, stamp=1.6, jitter=1.0: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(False, storm, 1.0) == 1.6


def test_c000280() -> None:
    """failures=false, stamp=1.7, jitter=0.5: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(False, storm, 0.5) == 1.7


def test_c000281() -> None:
    """failures=false, stamp=1.7, jitter=0.625: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(False, storm, 0.625) == 1.7


def test_c000282() -> None:
    """failures=false, stamp=1.7, jitter=0.75: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(False, storm, 0.75) == 1.7


def test_c000283() -> None:
    """failures=false, stamp=1.7, jitter=0.875: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(False, storm, 0.875) == 1.7


def test_c000284() -> None:
    """failures=false, stamp=1.7, jitter=1.0: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(False, storm, 1.0) == 1.7


def test_c000285() -> None:
    """failures=false, stamp=1.8, jitter=0.5: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(False, storm, 0.5) == 1.8


def test_c000286() -> None:
    """failures=false, stamp=1.8, jitter=0.625: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(False, storm, 0.625) == 1.8


def test_c000287() -> None:
    """failures=false, stamp=1.8, jitter=0.75: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(False, storm, 0.75) == 1.8


def test_c000288() -> None:
    """failures=false, stamp=1.8, jitter=0.875: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(False, storm, 0.875) == 1.8


def test_c000289() -> None:
    """failures=false, stamp=1.8, jitter=1.0: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(False, storm, 1.0) == 1.8


def test_c000290() -> None:
    """failures=false, stamp=1.9, jitter=0.5: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(False, storm, 0.5) == 1.9


def test_c000291() -> None:
    """failures=false, stamp=1.9, jitter=0.625: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(False, storm, 0.625) == 1.9


def test_c000292() -> None:
    """failures=false, stamp=1.9, jitter=0.75: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(False, storm, 0.75) == 1.9


def test_c000293() -> None:
    """failures=false, stamp=1.9, jitter=0.875: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(False, storm, 0.875) == 1.9


def test_c000294() -> None:
    """failures=false, stamp=1.9, jitter=1.0: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(False, storm, 1.0) == 1.9


def test_c000295() -> None:
    """failures=false, stamp=2.0, jitter=0.5: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(False, storm, 0.5) == 2.0


def test_c000296() -> None:
    """failures=false, stamp=2.0, jitter=0.625: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(False, storm, 0.625) == 2.0


def test_c000297() -> None:
    """failures=false, stamp=2.0, jitter=0.75: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(False, storm, 0.75) == 2.0


def test_c000298() -> None:
    """failures=false, stamp=2.0, jitter=0.875: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(False, storm, 0.875) == 2.0


def test_c000299() -> None:
    """failures=false, stamp=2.0, jitter=1.0: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(False, storm, 1.0) == 2.0


def test_c000300() -> None:
    """failures=false, stamp=2.1, jitter=0.5: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(False, storm, 0.5) == 2.1


def test_c000301() -> None:
    """failures=false, stamp=2.1, jitter=0.625: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(False, storm, 0.625) == 2.1


def test_c000302() -> None:
    """failures=false, stamp=2.1, jitter=0.75: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(False, storm, 0.75) == 2.1


def test_c000303() -> None:
    """failures=false, stamp=2.1, jitter=0.875: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(False, storm, 0.875) == 2.1


def test_c000304() -> None:
    """failures=false, stamp=2.1, jitter=1.0: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(False, storm, 1.0) == 2.1


def test_c000305() -> None:
    """failures=false, stamp=2.2, jitter=0.5: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(False, storm, 0.5) == 2.2


def test_c000306() -> None:
    """failures=false, stamp=2.2, jitter=0.625: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(False, storm, 0.625) == 2.2


def test_c000307() -> None:
    """failures=false, stamp=2.2, jitter=0.75: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(False, storm, 0.75) == 2.2


def test_c000308() -> None:
    """failures=false, stamp=2.2, jitter=0.875: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(False, storm, 0.875) == 2.2


def test_c000309() -> None:
    """failures=false, stamp=2.2, jitter=1.0: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(False, storm, 1.0) == 2.2


def test_c000310() -> None:
    """failures=false, stamp=2.3, jitter=0.5: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(False, storm, 0.5) == 2.3


def test_c000311() -> None:
    """failures=false, stamp=2.3, jitter=0.625: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(False, storm, 0.625) == 2.3


def test_c000312() -> None:
    """failures=false, stamp=2.3, jitter=0.75: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(False, storm, 0.75) == 2.3


def test_c000313() -> None:
    """failures=false, stamp=2.3, jitter=0.875: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(False, storm, 0.875) == 2.3


def test_c000314() -> None:
    """failures=false, stamp=2.3, jitter=1.0: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(False, storm, 1.0) == 2.3


def test_c000315() -> None:
    """failures=false, stamp=2.4, jitter=0.5: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(False, storm, 0.5) == 2.4


def test_c000316() -> None:
    """failures=false, stamp=2.4, jitter=0.625: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(False, storm, 0.625) == 2.4


def test_c000317() -> None:
    """failures=false, stamp=2.4, jitter=0.75: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(False, storm, 0.75) == 2.4


def test_c000318() -> None:
    """failures=false, stamp=2.4, jitter=0.875: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(False, storm, 0.875) == 2.4


def test_c000319() -> None:
    """failures=false, stamp=2.4, jitter=1.0: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(False, storm, 1.0) == 2.4


def test_c000320() -> None:
    """failures=false, stamp=2.5, jitter=0.5: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(False, storm, 0.5) == 2.5


def test_c000321() -> None:
    """failures=false, stamp=2.5, jitter=0.625: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(False, storm, 0.625) == 2.5


def test_c000322() -> None:
    """failures=false, stamp=2.5, jitter=0.75: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(False, storm, 0.75) == 2.5


def test_c000323() -> None:
    """failures=false, stamp=2.5, jitter=0.875: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(False, storm, 0.875) == 2.5


def test_c000324() -> None:
    """failures=false, stamp=2.5, jitter=1.0: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(False, storm, 1.0) == 2.5


def test_c000325() -> None:
    """failures=false, stamp=2.6, jitter=0.5: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(False, storm, 0.5) == 2.6


def test_c000326() -> None:
    """failures=false, stamp=2.6, jitter=0.625: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(False, storm, 0.625) == 2.6


def test_c000327() -> None:
    """failures=false, stamp=2.6, jitter=0.75: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(False, storm, 0.75) == 2.6


def test_c000328() -> None:
    """failures=false, stamp=2.6, jitter=0.875: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(False, storm, 0.875) == 2.6


def test_c000329() -> None:
    """failures=false, stamp=2.6, jitter=1.0: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(False, storm, 1.0) == 2.6


def test_c000330() -> None:
    """failures=false, stamp=2.7, jitter=0.5: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(False, storm, 0.5) == 2.7


def test_c000331() -> None:
    """failures=false, stamp=2.7, jitter=0.625: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(False, storm, 0.625) == 2.7


def test_c000332() -> None:
    """failures=false, stamp=2.7, jitter=0.75: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(False, storm, 0.75) == 2.7


def test_c000333() -> None:
    """failures=false, stamp=2.7, jitter=0.875: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(False, storm, 0.875) == 2.7


def test_c000334() -> None:
    """failures=false, stamp=2.7, jitter=1.0: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(False, storm, 1.0) == 2.7


def test_c000335() -> None:
    """failures=false, stamp=2.8, jitter=0.5: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(False, storm, 0.5) == 2.8


def test_c000336() -> None:
    """failures=false, stamp=2.8, jitter=0.625: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(False, storm, 0.625) == 2.8


def test_c000337() -> None:
    """failures=false, stamp=2.8, jitter=0.75: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(False, storm, 0.75) == 2.8


def test_c000338() -> None:
    """failures=false, stamp=2.8, jitter=0.875: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(False, storm, 0.875) == 2.8


def test_c000339() -> None:
    """failures=false, stamp=2.8, jitter=1.0: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(False, storm, 1.0) == 2.8


def test_c000340() -> None:
    """failures=false, stamp=2.9, jitter=0.5: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(False, storm, 0.5) == 2.9


def test_c000341() -> None:
    """failures=false, stamp=2.9, jitter=0.625: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(False, storm, 0.625) == 2.9


def test_c000342() -> None:
    """failures=false, stamp=2.9, jitter=0.75: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(False, storm, 0.75) == 2.9


def test_c000343() -> None:
    """failures=false, stamp=2.9, jitter=0.875: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(False, storm, 0.875) == 2.9


def test_c000344() -> None:
    """failures=false, stamp=2.9, jitter=1.0: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(False, storm, 1.0) == 2.9


def test_c000345() -> None:
    """failures=false, stamp=3.0, jitter=0.5: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(False, storm, 0.5) == 3.0


def test_c000346() -> None:
    """failures=false, stamp=3.0, jitter=0.625: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(False, storm, 0.625) == 3.0


def test_c000347() -> None:
    """failures=false, stamp=3.0, jitter=0.75: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(False, storm, 0.75) == 3.0


def test_c000348() -> None:
    """failures=false, stamp=3.0, jitter=0.875: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(False, storm, 0.875) == 3.0


def test_c000349() -> None:
    """failures=false, stamp=3.0, jitter=1.0: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(False, storm, 1.0) == 3.0


def test_c000350() -> None:
    """failures=false, stamp=3.1, jitter=0.5: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(False, storm, 0.5) == 3.1


def test_c000351() -> None:
    """failures=false, stamp=3.1, jitter=0.625: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(False, storm, 0.625) == 3.1


def test_c000352() -> None:
    """failures=false, stamp=3.1, jitter=0.75: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(False, storm, 0.75) == 3.1


def test_c000353() -> None:
    """failures=false, stamp=3.1, jitter=0.875: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(False, storm, 0.875) == 3.1


def test_c000354() -> None:
    """failures=false, stamp=3.1, jitter=1.0: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(False, storm, 1.0) == 3.1


def test_c000355() -> None:
    """failures=false, stamp=3.2, jitter=0.5: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(False, storm, 0.5) == 3.2


def test_c000356() -> None:
    """failures=false, stamp=3.2, jitter=0.625: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(False, storm, 0.625) == 3.2


def test_c000357() -> None:
    """failures=false, stamp=3.2, jitter=0.75: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(False, storm, 0.75) == 3.2


def test_c000358() -> None:
    """failures=false, stamp=3.2, jitter=0.875: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(False, storm, 0.875) == 3.2


def test_c000359() -> None:
    """failures=false, stamp=3.2, jitter=1.0: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(False, storm, 1.0) == 3.2


def test_c000360() -> None:
    """failures=false, stamp=3.3, jitter=0.5: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(False, storm, 0.5) == 3.3


def test_c000361() -> None:
    """failures=false, stamp=3.3, jitter=0.625: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(False, storm, 0.625) == 3.3


def test_c000362() -> None:
    """failures=false, stamp=3.3, jitter=0.75: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(False, storm, 0.75) == 3.3


def test_c000363() -> None:
    """failures=false, stamp=3.3, jitter=0.875: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(False, storm, 0.875) == 3.3


def test_c000364() -> None:
    """failures=false, stamp=3.3, jitter=1.0: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(False, storm, 1.0) == 3.3


def test_c000365() -> None:
    """failures=false, stamp=3.4, jitter=0.5: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(False, storm, 0.5) == 3.4


def test_c000366() -> None:
    """failures=false, stamp=3.4, jitter=0.625: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(False, storm, 0.625) == 3.4


def test_c000367() -> None:
    """failures=false, stamp=3.4, jitter=0.75: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(False, storm, 0.75) == 3.4


def test_c000368() -> None:
    """failures=false, stamp=3.4, jitter=0.875: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(False, storm, 0.875) == 3.4


def test_c000369() -> None:
    """failures=false, stamp=3.4, jitter=1.0: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(False, storm, 1.0) == 3.4


def test_c000370() -> None:
    """failures=false, stamp=3.5, jitter=0.5: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(False, storm, 0.5) == 3.5


def test_c000371() -> None:
    """failures=false, stamp=3.5, jitter=0.625: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(False, storm, 0.625) == 3.5


def test_c000372() -> None:
    """failures=false, stamp=3.5, jitter=0.75: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(False, storm, 0.75) == 3.5


def test_c000373() -> None:
    """failures=false, stamp=3.5, jitter=0.875: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(False, storm, 0.875) == 3.5


def test_c000374() -> None:
    """failures=false, stamp=3.5, jitter=1.0: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(False, storm, 1.0) == 3.5


def test_c000375() -> None:
    """failures=false, stamp=3.6, jitter=0.5: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(False, storm, 0.5) == 3.6


def test_c000376() -> None:
    """failures=false, stamp=3.6, jitter=0.625: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(False, storm, 0.625) == 3.6


def test_c000377() -> None:
    """failures=false, stamp=3.6, jitter=0.75: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(False, storm, 0.75) == 3.6


def test_c000378() -> None:
    """failures=false, stamp=3.6, jitter=0.875: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(False, storm, 0.875) == 3.6


def test_c000379() -> None:
    """failures=false, stamp=3.6, jitter=1.0: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(False, storm, 1.0) == 3.6


def test_c000380() -> None:
    """failures=false, stamp=3.7, jitter=0.5: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(False, storm, 0.5) == 3.7


def test_c000381() -> None:
    """failures=false, stamp=3.7, jitter=0.625: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(False, storm, 0.625) == 3.7


def test_c000382() -> None:
    """failures=false, stamp=3.7, jitter=0.75: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(False, storm, 0.75) == 3.7


def test_c000383() -> None:
    """failures=false, stamp=3.7, jitter=0.875: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(False, storm, 0.875) == 3.7


def test_c000384() -> None:
    """failures=false, stamp=3.7, jitter=1.0: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(False, storm, 1.0) == 3.7


def test_c000385() -> None:
    """failures=false, stamp=3.8, jitter=0.5: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(False, storm, 0.5) == 3.8


def test_c000386() -> None:
    """failures=false, stamp=3.8, jitter=0.625: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(False, storm, 0.625) == 3.8


def test_c000387() -> None:
    """failures=false, stamp=3.8, jitter=0.75: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(False, storm, 0.75) == 3.8


def test_c000388() -> None:
    """failures=false, stamp=3.8, jitter=0.875: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(False, storm, 0.875) == 3.8


def test_c000389() -> None:
    """failures=false, stamp=3.8, jitter=1.0: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(False, storm, 1.0) == 3.8


def test_c000390() -> None:
    """failures=false, stamp=3.9, jitter=0.5: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(False, storm, 0.5) == 3.9


def test_c000391() -> None:
    """failures=false, stamp=3.9, jitter=0.625: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(False, storm, 0.625) == 3.9


def test_c000392() -> None:
    """failures=false, stamp=3.9, jitter=0.75: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(False, storm, 0.75) == 3.9


def test_c000393() -> None:
    """failures=false, stamp=3.9, jitter=0.875: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(False, storm, 0.875) == 3.9


def test_c000394() -> None:
    """failures=false, stamp=3.9, jitter=1.0: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(False, storm, 1.0) == 3.9


def test_c000395() -> None:
    """failures=false, stamp=4.0, jitter=0.5: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(False, storm, 0.5) == 4.0


def test_c000396() -> None:
    """failures=false, stamp=4.0, jitter=0.625: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(False, storm, 0.625) == 4.0


def test_c000397() -> None:
    """failures=false, stamp=4.0, jitter=0.75: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(False, storm, 0.75) == 4.0


def test_c000398() -> None:
    """failures=false, stamp=4.0, jitter=0.875: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(False, storm, 0.875) == 4.0


def test_c000399() -> None:
    """failures=false, stamp=4.0, jitter=1.0: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(False, storm, 1.0) == 4.0


def test_c000400() -> None:
    """failures=zero, stamp=0.1, jitter=0.5: storm 0.1, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(0, storm, 0.5) == 0.5


def test_c000401() -> None:
    """failures=zero, stamp=0.1, jitter=0.625: storm 0.1, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(0, storm, 0.625) == 0.625


def test_c000402() -> None:
    """failures=zero, stamp=0.1, jitter=0.75: storm 0.1, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(0, storm, 0.75) == 0.75


def test_c000403() -> None:
    """failures=zero, stamp=0.1, jitter=0.875: storm 0.1, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000404() -> None:
    """failures=zero, stamp=0.1, jitter=1.0: storm 0.1, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000405() -> None:
    """failures=zero, stamp=0.2, jitter=0.5: storm 0.2, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(0, storm, 0.5) == 0.5


def test_c000406() -> None:
    """failures=zero, stamp=0.2, jitter=0.625: storm 0.2, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(0, storm, 0.625) == 0.625


def test_c000407() -> None:
    """failures=zero, stamp=0.2, jitter=0.75: storm 0.2, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(0, storm, 0.75) == 0.75


def test_c000408() -> None:
    """failures=zero, stamp=0.2, jitter=0.875: storm 0.2, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000409() -> None:
    """failures=zero, stamp=0.2, jitter=1.0: storm 0.2, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000410() -> None:
    """failures=zero, stamp=0.3, jitter=0.5: storm 0.3, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(0, storm, 0.5) == 0.5


def test_c000411() -> None:
    """failures=zero, stamp=0.3, jitter=0.625: storm 0.3, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(0, storm, 0.625) == 0.625


def test_c000412() -> None:
    """failures=zero, stamp=0.3, jitter=0.75: storm 0.3, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(0, storm, 0.75) == 0.75


def test_c000413() -> None:
    """failures=zero, stamp=0.3, jitter=0.875: storm 0.3, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000414() -> None:
    """failures=zero, stamp=0.3, jitter=1.0: storm 0.3, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000415() -> None:
    """failures=zero, stamp=0.4, jitter=0.5: storm 0.4, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(0, storm, 0.5) == 0.5


def test_c000416() -> None:
    """failures=zero, stamp=0.4, jitter=0.625: storm 0.4, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(0, storm, 0.625) == 0.625


def test_c000417() -> None:
    """failures=zero, stamp=0.4, jitter=0.75: storm 0.4, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(0, storm, 0.75) == 0.75


def test_c000418() -> None:
    """failures=zero, stamp=0.4, jitter=0.875: storm 0.4, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000419() -> None:
    """failures=zero, stamp=0.4, jitter=1.0: storm 0.4, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000420() -> None:
    """failures=zero, stamp=0.5, jitter=0.5: storm 0.5, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(0, storm, 0.5) == 0.5


def test_c000421() -> None:
    """failures=zero, stamp=0.5, jitter=0.625: storm 0.5, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(0, storm, 0.625) == 0.625


def test_c000422() -> None:
    """failures=zero, stamp=0.5, jitter=0.75: storm 0.5, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(0, storm, 0.75) == 0.75


def test_c000423() -> None:
    """failures=zero, stamp=0.5, jitter=0.875: storm 0.5, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000424() -> None:
    """failures=zero, stamp=0.5, jitter=1.0: storm 0.5, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000425() -> None:
    """failures=zero, stamp=0.6, jitter=0.5: storm 0.6, delay 0.6."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(0, storm, 0.5) == 0.6


def test_c000426() -> None:
    """failures=zero, stamp=0.6, jitter=0.625: storm 0.6, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(0, storm, 0.625) == 0.625


def test_c000427() -> None:
    """failures=zero, stamp=0.6, jitter=0.75: storm 0.6, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(0, storm, 0.75) == 0.75


def test_c000428() -> None:
    """failures=zero, stamp=0.6, jitter=0.875: storm 0.6, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000429() -> None:
    """failures=zero, stamp=0.6, jitter=1.0: storm 0.6, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000430() -> None:
    """failures=zero, stamp=0.7, jitter=0.5: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(0, storm, 0.5) == 0.7


def test_c000431() -> None:
    """failures=zero, stamp=0.7, jitter=0.625: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(0, storm, 0.625) == 0.7


def test_c000432() -> None:
    """failures=zero, stamp=0.7, jitter=0.75: storm 0.7, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(0, storm, 0.75) == 0.75


def test_c000433() -> None:
    """failures=zero, stamp=0.7, jitter=0.875: storm 0.7, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000434() -> None:
    """failures=zero, stamp=0.7, jitter=1.0: storm 0.7, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000435() -> None:
    """failures=zero, stamp=0.8, jitter=0.5: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(0, storm, 0.5) == 0.8


def test_c000436() -> None:
    """failures=zero, stamp=0.8, jitter=0.625: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(0, storm, 0.625) == 0.8


def test_c000437() -> None:
    """failures=zero, stamp=0.8, jitter=0.75: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(0, storm, 0.75) == 0.8


def test_c000438() -> None:
    """failures=zero, stamp=0.8, jitter=0.875: storm 0.8, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(0, storm, 0.875) == 0.875


def test_c000439() -> None:
    """failures=zero, stamp=0.8, jitter=1.0: storm 0.8, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000440() -> None:
    """failures=zero, stamp=0.9, jitter=0.5: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(0, storm, 0.5) == 0.9


def test_c000441() -> None:
    """failures=zero, stamp=0.9, jitter=0.625: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(0, storm, 0.625) == 0.9


def test_c000442() -> None:
    """failures=zero, stamp=0.9, jitter=0.75: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(0, storm, 0.75) == 0.9


def test_c000443() -> None:
    """failures=zero, stamp=0.9, jitter=0.875: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(0, storm, 0.875) == 0.9


def test_c000444() -> None:
    """failures=zero, stamp=0.9, jitter=1.0: storm 0.9, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000445() -> None:
    """failures=zero, stamp=1.0, jitter=0.5: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(0, storm, 0.5) == 1.0


def test_c000446() -> None:
    """failures=zero, stamp=1.0, jitter=0.625: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(0, storm, 0.625) == 1.0


def test_c000447() -> None:
    """failures=zero, stamp=1.0, jitter=0.75: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(0, storm, 0.75) == 1.0


def test_c000448() -> None:
    """failures=zero, stamp=1.0, jitter=0.875: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(0, storm, 0.875) == 1.0


def test_c000449() -> None:
    """failures=zero, stamp=1.0, jitter=1.0: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(0, storm, 1.0) == 1.0


def test_c000450() -> None:
    """failures=zero, stamp=1.1, jitter=0.5: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(0, storm, 0.5) == 1.1


def test_c000451() -> None:
    """failures=zero, stamp=1.1, jitter=0.625: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(0, storm, 0.625) == 1.1


def test_c000452() -> None:
    """failures=zero, stamp=1.1, jitter=0.75: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(0, storm, 0.75) == 1.1


def test_c000453() -> None:
    """failures=zero, stamp=1.1, jitter=0.875: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(0, storm, 0.875) == 1.1


def test_c000454() -> None:
    """failures=zero, stamp=1.1, jitter=1.0: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(0, storm, 1.0) == 1.1


def test_c000455() -> None:
    """failures=zero, stamp=1.2, jitter=0.5: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(0, storm, 0.5) == 1.2


def test_c000456() -> None:
    """failures=zero, stamp=1.2, jitter=0.625: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(0, storm, 0.625) == 1.2


def test_c000457() -> None:
    """failures=zero, stamp=1.2, jitter=0.75: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(0, storm, 0.75) == 1.2


def test_c000458() -> None:
    """failures=zero, stamp=1.2, jitter=0.875: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(0, storm, 0.875) == 1.2


def test_c000459() -> None:
    """failures=zero, stamp=1.2, jitter=1.0: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(0, storm, 1.0) == 1.2


def test_c000460() -> None:
    """failures=zero, stamp=1.3, jitter=0.5: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(0, storm, 0.5) == 1.3


def test_c000461() -> None:
    """failures=zero, stamp=1.3, jitter=0.625: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(0, storm, 0.625) == 1.3


def test_c000462() -> None:
    """failures=zero, stamp=1.3, jitter=0.75: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(0, storm, 0.75) == 1.3


def test_c000463() -> None:
    """failures=zero, stamp=1.3, jitter=0.875: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(0, storm, 0.875) == 1.3


def test_c000464() -> None:
    """failures=zero, stamp=1.3, jitter=1.0: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(0, storm, 1.0) == 1.3


def test_c000465() -> None:
    """failures=zero, stamp=1.4, jitter=0.5: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(0, storm, 0.5) == 1.4


def test_c000466() -> None:
    """failures=zero, stamp=1.4, jitter=0.625: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(0, storm, 0.625) == 1.4


def test_c000467() -> None:
    """failures=zero, stamp=1.4, jitter=0.75: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(0, storm, 0.75) == 1.4


def test_c000468() -> None:
    """failures=zero, stamp=1.4, jitter=0.875: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(0, storm, 0.875) == 1.4


def test_c000469() -> None:
    """failures=zero, stamp=1.4, jitter=1.0: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(0, storm, 1.0) == 1.4


def test_c000470() -> None:
    """failures=zero, stamp=1.5, jitter=0.5: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(0, storm, 0.5) == 1.5


def test_c000471() -> None:
    """failures=zero, stamp=1.5, jitter=0.625: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(0, storm, 0.625) == 1.5


def test_c000472() -> None:
    """failures=zero, stamp=1.5, jitter=0.75: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(0, storm, 0.75) == 1.5


def test_c000473() -> None:
    """failures=zero, stamp=1.5, jitter=0.875: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(0, storm, 0.875) == 1.5


def test_c000474() -> None:
    """failures=zero, stamp=1.5, jitter=1.0: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(0, storm, 1.0) == 1.5


def test_c000475() -> None:
    """failures=zero, stamp=1.6, jitter=0.5: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(0, storm, 0.5) == 1.6


def test_c000476() -> None:
    """failures=zero, stamp=1.6, jitter=0.625: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(0, storm, 0.625) == 1.6


def test_c000477() -> None:
    """failures=zero, stamp=1.6, jitter=0.75: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(0, storm, 0.75) == 1.6


def test_c000478() -> None:
    """failures=zero, stamp=1.6, jitter=0.875: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(0, storm, 0.875) == 1.6


def test_c000479() -> None:
    """failures=zero, stamp=1.6, jitter=1.0: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(0, storm, 1.0) == 1.6


def test_c000480() -> None:
    """failures=zero, stamp=1.7, jitter=0.5: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(0, storm, 0.5) == 1.7


def test_c000481() -> None:
    """failures=zero, stamp=1.7, jitter=0.625: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(0, storm, 0.625) == 1.7


def test_c000482() -> None:
    """failures=zero, stamp=1.7, jitter=0.75: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(0, storm, 0.75) == 1.7


def test_c000483() -> None:
    """failures=zero, stamp=1.7, jitter=0.875: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(0, storm, 0.875) == 1.7


def test_c000484() -> None:
    """failures=zero, stamp=1.7, jitter=1.0: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(0, storm, 1.0) == 1.7


def test_c000485() -> None:
    """failures=zero, stamp=1.8, jitter=0.5: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(0, storm, 0.5) == 1.8


def test_c000486() -> None:
    """failures=zero, stamp=1.8, jitter=0.625: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(0, storm, 0.625) == 1.8


def test_c000487() -> None:
    """failures=zero, stamp=1.8, jitter=0.75: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(0, storm, 0.75) == 1.8


def test_c000488() -> None:
    """failures=zero, stamp=1.8, jitter=0.875: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(0, storm, 0.875) == 1.8


def test_c000489() -> None:
    """failures=zero, stamp=1.8, jitter=1.0: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(0, storm, 1.0) == 1.8


def test_c000490() -> None:
    """failures=zero, stamp=1.9, jitter=0.5: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(0, storm, 0.5) == 1.9


def test_c000491() -> None:
    """failures=zero, stamp=1.9, jitter=0.625: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(0, storm, 0.625) == 1.9


def test_c000492() -> None:
    """failures=zero, stamp=1.9, jitter=0.75: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(0, storm, 0.75) == 1.9


def test_c000493() -> None:
    """failures=zero, stamp=1.9, jitter=0.875: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(0, storm, 0.875) == 1.9


def test_c000494() -> None:
    """failures=zero, stamp=1.9, jitter=1.0: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(0, storm, 1.0) == 1.9


def test_c000495() -> None:
    """failures=zero, stamp=2.0, jitter=0.5: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(0, storm, 0.5) == 2.0


def test_c000496() -> None:
    """failures=zero, stamp=2.0, jitter=0.625: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(0, storm, 0.625) == 2.0


def test_c000497() -> None:
    """failures=zero, stamp=2.0, jitter=0.75: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(0, storm, 0.75) == 2.0


def test_c000498() -> None:
    """failures=zero, stamp=2.0, jitter=0.875: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(0, storm, 0.875) == 2.0


def test_c000499() -> None:
    """failures=zero, stamp=2.0, jitter=1.0: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(0, storm, 1.0) == 2.0


def test_c000500() -> None:
    """failures=zero, stamp=2.1, jitter=0.5: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(0, storm, 0.5) == 2.1


def test_c000501() -> None:
    """failures=zero, stamp=2.1, jitter=0.625: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(0, storm, 0.625) == 2.1


def test_c000502() -> None:
    """failures=zero, stamp=2.1, jitter=0.75: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(0, storm, 0.75) == 2.1


def test_c000503() -> None:
    """failures=zero, stamp=2.1, jitter=0.875: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(0, storm, 0.875) == 2.1


def test_c000504() -> None:
    """failures=zero, stamp=2.1, jitter=1.0: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(0, storm, 1.0) == 2.1


def test_c000505() -> None:
    """failures=zero, stamp=2.2, jitter=0.5: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(0, storm, 0.5) == 2.2


def test_c000506() -> None:
    """failures=zero, stamp=2.2, jitter=0.625: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(0, storm, 0.625) == 2.2


def test_c000507() -> None:
    """failures=zero, stamp=2.2, jitter=0.75: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(0, storm, 0.75) == 2.2


def test_c000508() -> None:
    """failures=zero, stamp=2.2, jitter=0.875: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(0, storm, 0.875) == 2.2


def test_c000509() -> None:
    """failures=zero, stamp=2.2, jitter=1.0: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(0, storm, 1.0) == 2.2


def test_c000510() -> None:
    """failures=zero, stamp=2.3, jitter=0.5: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(0, storm, 0.5) == 2.3


def test_c000511() -> None:
    """failures=zero, stamp=2.3, jitter=0.625: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(0, storm, 0.625) == 2.3


def test_c000512() -> None:
    """failures=zero, stamp=2.3, jitter=0.75: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(0, storm, 0.75) == 2.3


def test_c000513() -> None:
    """failures=zero, stamp=2.3, jitter=0.875: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(0, storm, 0.875) == 2.3


def test_c000514() -> None:
    """failures=zero, stamp=2.3, jitter=1.0: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(0, storm, 1.0) == 2.3


def test_c000515() -> None:
    """failures=zero, stamp=2.4, jitter=0.5: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(0, storm, 0.5) == 2.4


def test_c000516() -> None:
    """failures=zero, stamp=2.4, jitter=0.625: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(0, storm, 0.625) == 2.4


def test_c000517() -> None:
    """failures=zero, stamp=2.4, jitter=0.75: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(0, storm, 0.75) == 2.4


def test_c000518() -> None:
    """failures=zero, stamp=2.4, jitter=0.875: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(0, storm, 0.875) == 2.4


def test_c000519() -> None:
    """failures=zero, stamp=2.4, jitter=1.0: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(0, storm, 1.0) == 2.4


def test_c000520() -> None:
    """failures=zero, stamp=2.5, jitter=0.5: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(0, storm, 0.5) == 2.5


def test_c000521() -> None:
    """failures=zero, stamp=2.5, jitter=0.625: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(0, storm, 0.625) == 2.5


def test_c000522() -> None:
    """failures=zero, stamp=2.5, jitter=0.75: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(0, storm, 0.75) == 2.5


def test_c000523() -> None:
    """failures=zero, stamp=2.5, jitter=0.875: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(0, storm, 0.875) == 2.5


def test_c000524() -> None:
    """failures=zero, stamp=2.5, jitter=1.0: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(0, storm, 1.0) == 2.5


def test_c000525() -> None:
    """failures=zero, stamp=2.6, jitter=0.5: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(0, storm, 0.5) == 2.6


def test_c000526() -> None:
    """failures=zero, stamp=2.6, jitter=0.625: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(0, storm, 0.625) == 2.6


def test_c000527() -> None:
    """failures=zero, stamp=2.6, jitter=0.75: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(0, storm, 0.75) == 2.6


def test_c000528() -> None:
    """failures=zero, stamp=2.6, jitter=0.875: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(0, storm, 0.875) == 2.6


def test_c000529() -> None:
    """failures=zero, stamp=2.6, jitter=1.0: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(0, storm, 1.0) == 2.6


def test_c000530() -> None:
    """failures=zero, stamp=2.7, jitter=0.5: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(0, storm, 0.5) == 2.7


def test_c000531() -> None:
    """failures=zero, stamp=2.7, jitter=0.625: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(0, storm, 0.625) == 2.7


def test_c000532() -> None:
    """failures=zero, stamp=2.7, jitter=0.75: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(0, storm, 0.75) == 2.7


def test_c000533() -> None:
    """failures=zero, stamp=2.7, jitter=0.875: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(0, storm, 0.875) == 2.7


def test_c000534() -> None:
    """failures=zero, stamp=2.7, jitter=1.0: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(0, storm, 1.0) == 2.7


def test_c000535() -> None:
    """failures=zero, stamp=2.8, jitter=0.5: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(0, storm, 0.5) == 2.8


def test_c000536() -> None:
    """failures=zero, stamp=2.8, jitter=0.625: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(0, storm, 0.625) == 2.8


def test_c000537() -> None:
    """failures=zero, stamp=2.8, jitter=0.75: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(0, storm, 0.75) == 2.8


def test_c000538() -> None:
    """failures=zero, stamp=2.8, jitter=0.875: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(0, storm, 0.875) == 2.8


def test_c000539() -> None:
    """failures=zero, stamp=2.8, jitter=1.0: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(0, storm, 1.0) == 2.8


def test_c000540() -> None:
    """failures=zero, stamp=2.9, jitter=0.5: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(0, storm, 0.5) == 2.9


def test_c000541() -> None:
    """failures=zero, stamp=2.9, jitter=0.625: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(0, storm, 0.625) == 2.9


def test_c000542() -> None:
    """failures=zero, stamp=2.9, jitter=0.75: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(0, storm, 0.75) == 2.9


def test_c000543() -> None:
    """failures=zero, stamp=2.9, jitter=0.875: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(0, storm, 0.875) == 2.9


def test_c000544() -> None:
    """failures=zero, stamp=2.9, jitter=1.0: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(0, storm, 1.0) == 2.9


def test_c000545() -> None:
    """failures=zero, stamp=3.0, jitter=0.5: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(0, storm, 0.5) == 3.0


def test_c000546() -> None:
    """failures=zero, stamp=3.0, jitter=0.625: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(0, storm, 0.625) == 3.0


def test_c000547() -> None:
    """failures=zero, stamp=3.0, jitter=0.75: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(0, storm, 0.75) == 3.0


def test_c000548() -> None:
    """failures=zero, stamp=3.0, jitter=0.875: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(0, storm, 0.875) == 3.0


def test_c000549() -> None:
    """failures=zero, stamp=3.0, jitter=1.0: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(0, storm, 1.0) == 3.0


def test_c000550() -> None:
    """failures=zero, stamp=3.1, jitter=0.5: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(0, storm, 0.5) == 3.1


def test_c000551() -> None:
    """failures=zero, stamp=3.1, jitter=0.625: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(0, storm, 0.625) == 3.1


def test_c000552() -> None:
    """failures=zero, stamp=3.1, jitter=0.75: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(0, storm, 0.75) == 3.1


def test_c000553() -> None:
    """failures=zero, stamp=3.1, jitter=0.875: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(0, storm, 0.875) == 3.1


def test_c000554() -> None:
    """failures=zero, stamp=3.1, jitter=1.0: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(0, storm, 1.0) == 3.1


def test_c000555() -> None:
    """failures=zero, stamp=3.2, jitter=0.5: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(0, storm, 0.5) == 3.2


def test_c000556() -> None:
    """failures=zero, stamp=3.2, jitter=0.625: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(0, storm, 0.625) == 3.2


def test_c000557() -> None:
    """failures=zero, stamp=3.2, jitter=0.75: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(0, storm, 0.75) == 3.2


def test_c000558() -> None:
    """failures=zero, stamp=3.2, jitter=0.875: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(0, storm, 0.875) == 3.2


def test_c000559() -> None:
    """failures=zero, stamp=3.2, jitter=1.0: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(0, storm, 1.0) == 3.2


def test_c000560() -> None:
    """failures=zero, stamp=3.3, jitter=0.5: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(0, storm, 0.5) == 3.3


def test_c000561() -> None:
    """failures=zero, stamp=3.3, jitter=0.625: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(0, storm, 0.625) == 3.3


def test_c000562() -> None:
    """failures=zero, stamp=3.3, jitter=0.75: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(0, storm, 0.75) == 3.3


def test_c000563() -> None:
    """failures=zero, stamp=3.3, jitter=0.875: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(0, storm, 0.875) == 3.3


def test_c000564() -> None:
    """failures=zero, stamp=3.3, jitter=1.0: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(0, storm, 1.0) == 3.3


def test_c000565() -> None:
    """failures=zero, stamp=3.4, jitter=0.5: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(0, storm, 0.5) == 3.4


def test_c000566() -> None:
    """failures=zero, stamp=3.4, jitter=0.625: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(0, storm, 0.625) == 3.4


def test_c000567() -> None:
    """failures=zero, stamp=3.4, jitter=0.75: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(0, storm, 0.75) == 3.4


def test_c000568() -> None:
    """failures=zero, stamp=3.4, jitter=0.875: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(0, storm, 0.875) == 3.4


def test_c000569() -> None:
    """failures=zero, stamp=3.4, jitter=1.0: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(0, storm, 1.0) == 3.4


def test_c000570() -> None:
    """failures=zero, stamp=3.5, jitter=0.5: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(0, storm, 0.5) == 3.5


def test_c000571() -> None:
    """failures=zero, stamp=3.5, jitter=0.625: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(0, storm, 0.625) == 3.5


def test_c000572() -> None:
    """failures=zero, stamp=3.5, jitter=0.75: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(0, storm, 0.75) == 3.5


def test_c000573() -> None:
    """failures=zero, stamp=3.5, jitter=0.875: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(0, storm, 0.875) == 3.5


def test_c000574() -> None:
    """failures=zero, stamp=3.5, jitter=1.0: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(0, storm, 1.0) == 3.5


def test_c000575() -> None:
    """failures=zero, stamp=3.6, jitter=0.5: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(0, storm, 0.5) == 3.6


def test_c000576() -> None:
    """failures=zero, stamp=3.6, jitter=0.625: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(0, storm, 0.625) == 3.6


def test_c000577() -> None:
    """failures=zero, stamp=3.6, jitter=0.75: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(0, storm, 0.75) == 3.6


def test_c000578() -> None:
    """failures=zero, stamp=3.6, jitter=0.875: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(0, storm, 0.875) == 3.6


def test_c000579() -> None:
    """failures=zero, stamp=3.6, jitter=1.0: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(0, storm, 1.0) == 3.6


def test_c000580() -> None:
    """failures=zero, stamp=3.7, jitter=0.5: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(0, storm, 0.5) == 3.7


def test_c000581() -> None:
    """failures=zero, stamp=3.7, jitter=0.625: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(0, storm, 0.625) == 3.7


def test_c000582() -> None:
    """failures=zero, stamp=3.7, jitter=0.75: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(0, storm, 0.75) == 3.7


def test_c000583() -> None:
    """failures=zero, stamp=3.7, jitter=0.875: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(0, storm, 0.875) == 3.7


def test_c000584() -> None:
    """failures=zero, stamp=3.7, jitter=1.0: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(0, storm, 1.0) == 3.7


def test_c000585() -> None:
    """failures=zero, stamp=3.8, jitter=0.5: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(0, storm, 0.5) == 3.8


def test_c000586() -> None:
    """failures=zero, stamp=3.8, jitter=0.625: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(0, storm, 0.625) == 3.8


def test_c000587() -> None:
    """failures=zero, stamp=3.8, jitter=0.75: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(0, storm, 0.75) == 3.8


def test_c000588() -> None:
    """failures=zero, stamp=3.8, jitter=0.875: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(0, storm, 0.875) == 3.8


def test_c000589() -> None:
    """failures=zero, stamp=3.8, jitter=1.0: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(0, storm, 1.0) == 3.8


def test_c000590() -> None:
    """failures=zero, stamp=3.9, jitter=0.5: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(0, storm, 0.5) == 3.9


def test_c000591() -> None:
    """failures=zero, stamp=3.9, jitter=0.625: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(0, storm, 0.625) == 3.9


def test_c000592() -> None:
    """failures=zero, stamp=3.9, jitter=0.75: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(0, storm, 0.75) == 3.9


def test_c000593() -> None:
    """failures=zero, stamp=3.9, jitter=0.875: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(0, storm, 0.875) == 3.9


def test_c000594() -> None:
    """failures=zero, stamp=3.9, jitter=1.0: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(0, storm, 1.0) == 3.9


def test_c000595() -> None:
    """failures=zero, stamp=4.0, jitter=0.5: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(0, storm, 0.5) == 4.0


def test_c000596() -> None:
    """failures=zero, stamp=4.0, jitter=0.625: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(0, storm, 0.625) == 4.0


def test_c000597() -> None:
    """failures=zero, stamp=4.0, jitter=0.75: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(0, storm, 0.75) == 4.0


def test_c000598() -> None:
    """failures=zero, stamp=4.0, jitter=0.875: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(0, storm, 0.875) == 4.0


def test_c000599() -> None:
    """failures=zero, stamp=4.0, jitter=1.0: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(0, storm, 1.0) == 4.0


def test_c000600() -> None:
    """failures=neg, stamp=0.1, jitter=0.5: storm 0.1, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(-1, storm, 0.5) == 0.5


def test_c000601() -> None:
    """failures=neg, stamp=0.1, jitter=0.625: storm 0.1, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(-1, storm, 0.625) == 0.625


def test_c000602() -> None:
    """failures=neg, stamp=0.1, jitter=0.75: storm 0.1, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(-1, storm, 0.75) == 0.75


def test_c000603() -> None:
    """failures=neg, stamp=0.1, jitter=0.875: storm 0.1, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000604() -> None:
    """failures=neg, stamp=0.1, jitter=1.0: storm 0.1, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000605() -> None:
    """failures=neg, stamp=0.2, jitter=0.5: storm 0.2, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(-1, storm, 0.5) == 0.5


def test_c000606() -> None:
    """failures=neg, stamp=0.2, jitter=0.625: storm 0.2, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(-1, storm, 0.625) == 0.625


def test_c000607() -> None:
    """failures=neg, stamp=0.2, jitter=0.75: storm 0.2, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(-1, storm, 0.75) == 0.75


def test_c000608() -> None:
    """failures=neg, stamp=0.2, jitter=0.875: storm 0.2, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000609() -> None:
    """failures=neg, stamp=0.2, jitter=1.0: storm 0.2, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000610() -> None:
    """failures=neg, stamp=0.3, jitter=0.5: storm 0.3, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(-1, storm, 0.5) == 0.5


def test_c000611() -> None:
    """failures=neg, stamp=0.3, jitter=0.625: storm 0.3, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(-1, storm, 0.625) == 0.625


def test_c000612() -> None:
    """failures=neg, stamp=0.3, jitter=0.75: storm 0.3, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(-1, storm, 0.75) == 0.75


def test_c000613() -> None:
    """failures=neg, stamp=0.3, jitter=0.875: storm 0.3, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000614() -> None:
    """failures=neg, stamp=0.3, jitter=1.0: storm 0.3, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000615() -> None:
    """failures=neg, stamp=0.4, jitter=0.5: storm 0.4, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(-1, storm, 0.5) == 0.5


def test_c000616() -> None:
    """failures=neg, stamp=0.4, jitter=0.625: storm 0.4, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(-1, storm, 0.625) == 0.625


def test_c000617() -> None:
    """failures=neg, stamp=0.4, jitter=0.75: storm 0.4, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(-1, storm, 0.75) == 0.75


def test_c000618() -> None:
    """failures=neg, stamp=0.4, jitter=0.875: storm 0.4, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000619() -> None:
    """failures=neg, stamp=0.4, jitter=1.0: storm 0.4, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000620() -> None:
    """failures=neg, stamp=0.5, jitter=0.5: storm 0.5, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(-1, storm, 0.5) == 0.5


def test_c000621() -> None:
    """failures=neg, stamp=0.5, jitter=0.625: storm 0.5, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(-1, storm, 0.625) == 0.625


def test_c000622() -> None:
    """failures=neg, stamp=0.5, jitter=0.75: storm 0.5, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(-1, storm, 0.75) == 0.75


def test_c000623() -> None:
    """failures=neg, stamp=0.5, jitter=0.875: storm 0.5, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000624() -> None:
    """failures=neg, stamp=0.5, jitter=1.0: storm 0.5, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000625() -> None:
    """failures=neg, stamp=0.6, jitter=0.5: storm 0.6, delay 0.6."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(-1, storm, 0.5) == 0.6


def test_c000626() -> None:
    """failures=neg, stamp=0.6, jitter=0.625: storm 0.6, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(-1, storm, 0.625) == 0.625


def test_c000627() -> None:
    """failures=neg, stamp=0.6, jitter=0.75: storm 0.6, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(-1, storm, 0.75) == 0.75


def test_c000628() -> None:
    """failures=neg, stamp=0.6, jitter=0.875: storm 0.6, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000629() -> None:
    """failures=neg, stamp=0.6, jitter=1.0: storm 0.6, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000630() -> None:
    """failures=neg, stamp=0.7, jitter=0.5: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(-1, storm, 0.5) == 0.7


def test_c000631() -> None:
    """failures=neg, stamp=0.7, jitter=0.625: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(-1, storm, 0.625) == 0.7


def test_c000632() -> None:
    """failures=neg, stamp=0.7, jitter=0.75: storm 0.7, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(-1, storm, 0.75) == 0.75


def test_c000633() -> None:
    """failures=neg, stamp=0.7, jitter=0.875: storm 0.7, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000634() -> None:
    """failures=neg, stamp=0.7, jitter=1.0: storm 0.7, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000635() -> None:
    """failures=neg, stamp=0.8, jitter=0.5: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(-1, storm, 0.5) == 0.8


def test_c000636() -> None:
    """failures=neg, stamp=0.8, jitter=0.625: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(-1, storm, 0.625) == 0.8


def test_c000637() -> None:
    """failures=neg, stamp=0.8, jitter=0.75: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(-1, storm, 0.75) == 0.8


def test_c000638() -> None:
    """failures=neg, stamp=0.8, jitter=0.875: storm 0.8, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(-1, storm, 0.875) == 0.875


def test_c000639() -> None:
    """failures=neg, stamp=0.8, jitter=1.0: storm 0.8, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000640() -> None:
    """failures=neg, stamp=0.9, jitter=0.5: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(-1, storm, 0.5) == 0.9


def test_c000641() -> None:
    """failures=neg, stamp=0.9, jitter=0.625: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(-1, storm, 0.625) == 0.9


def test_c000642() -> None:
    """failures=neg, stamp=0.9, jitter=0.75: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(-1, storm, 0.75) == 0.9


def test_c000643() -> None:
    """failures=neg, stamp=0.9, jitter=0.875: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(-1, storm, 0.875) == 0.9


def test_c000644() -> None:
    """failures=neg, stamp=0.9, jitter=1.0: storm 0.9, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000645() -> None:
    """failures=neg, stamp=1.0, jitter=0.5: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(-1, storm, 0.5) == 1.0


def test_c000646() -> None:
    """failures=neg, stamp=1.0, jitter=0.625: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(-1, storm, 0.625) == 1.0


def test_c000647() -> None:
    """failures=neg, stamp=1.0, jitter=0.75: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(-1, storm, 0.75) == 1.0


def test_c000648() -> None:
    """failures=neg, stamp=1.0, jitter=0.875: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(-1, storm, 0.875) == 1.0


def test_c000649() -> None:
    """failures=neg, stamp=1.0, jitter=1.0: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(-1, storm, 1.0) == 1.0


def test_c000650() -> None:
    """failures=neg, stamp=1.1, jitter=0.5: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(-1, storm, 0.5) == 1.1


def test_c000651() -> None:
    """failures=neg, stamp=1.1, jitter=0.625: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(-1, storm, 0.625) == 1.1


def test_c000652() -> None:
    """failures=neg, stamp=1.1, jitter=0.75: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(-1, storm, 0.75) == 1.1


def test_c000653() -> None:
    """failures=neg, stamp=1.1, jitter=0.875: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(-1, storm, 0.875) == 1.1


def test_c000654() -> None:
    """failures=neg, stamp=1.1, jitter=1.0: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(-1, storm, 1.0) == 1.1


def test_c000655() -> None:
    """failures=neg, stamp=1.2, jitter=0.5: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(-1, storm, 0.5) == 1.2


def test_c000656() -> None:
    """failures=neg, stamp=1.2, jitter=0.625: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(-1, storm, 0.625) == 1.2


def test_c000657() -> None:
    """failures=neg, stamp=1.2, jitter=0.75: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(-1, storm, 0.75) == 1.2


def test_c000658() -> None:
    """failures=neg, stamp=1.2, jitter=0.875: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(-1, storm, 0.875) == 1.2


def test_c000659() -> None:
    """failures=neg, stamp=1.2, jitter=1.0: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(-1, storm, 1.0) == 1.2


def test_c000660() -> None:
    """failures=neg, stamp=1.3, jitter=0.5: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(-1, storm, 0.5) == 1.3


def test_c000661() -> None:
    """failures=neg, stamp=1.3, jitter=0.625: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(-1, storm, 0.625) == 1.3


def test_c000662() -> None:
    """failures=neg, stamp=1.3, jitter=0.75: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(-1, storm, 0.75) == 1.3


def test_c000663() -> None:
    """failures=neg, stamp=1.3, jitter=0.875: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(-1, storm, 0.875) == 1.3


def test_c000664() -> None:
    """failures=neg, stamp=1.3, jitter=1.0: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(-1, storm, 1.0) == 1.3


def test_c000665() -> None:
    """failures=neg, stamp=1.4, jitter=0.5: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(-1, storm, 0.5) == 1.4


def test_c000666() -> None:
    """failures=neg, stamp=1.4, jitter=0.625: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(-1, storm, 0.625) == 1.4


def test_c000667() -> None:
    """failures=neg, stamp=1.4, jitter=0.75: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(-1, storm, 0.75) == 1.4


def test_c000668() -> None:
    """failures=neg, stamp=1.4, jitter=0.875: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(-1, storm, 0.875) == 1.4


def test_c000669() -> None:
    """failures=neg, stamp=1.4, jitter=1.0: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(-1, storm, 1.0) == 1.4


def test_c000670() -> None:
    """failures=neg, stamp=1.5, jitter=0.5: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(-1, storm, 0.5) == 1.5


def test_c000671() -> None:
    """failures=neg, stamp=1.5, jitter=0.625: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(-1, storm, 0.625) == 1.5


def test_c000672() -> None:
    """failures=neg, stamp=1.5, jitter=0.75: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(-1, storm, 0.75) == 1.5


def test_c000673() -> None:
    """failures=neg, stamp=1.5, jitter=0.875: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(-1, storm, 0.875) == 1.5


def test_c000674() -> None:
    """failures=neg, stamp=1.5, jitter=1.0: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(-1, storm, 1.0) == 1.5


def test_c000675() -> None:
    """failures=neg, stamp=1.6, jitter=0.5: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(-1, storm, 0.5) == 1.6


def test_c000676() -> None:
    """failures=neg, stamp=1.6, jitter=0.625: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(-1, storm, 0.625) == 1.6


def test_c000677() -> None:
    """failures=neg, stamp=1.6, jitter=0.75: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(-1, storm, 0.75) == 1.6


def test_c000678() -> None:
    """failures=neg, stamp=1.6, jitter=0.875: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(-1, storm, 0.875) == 1.6


def test_c000679() -> None:
    """failures=neg, stamp=1.6, jitter=1.0: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(-1, storm, 1.0) == 1.6


def test_c000680() -> None:
    """failures=neg, stamp=1.7, jitter=0.5: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(-1, storm, 0.5) == 1.7


def test_c000681() -> None:
    """failures=neg, stamp=1.7, jitter=0.625: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(-1, storm, 0.625) == 1.7


def test_c000682() -> None:
    """failures=neg, stamp=1.7, jitter=0.75: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(-1, storm, 0.75) == 1.7


def test_c000683() -> None:
    """failures=neg, stamp=1.7, jitter=0.875: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(-1, storm, 0.875) == 1.7


def test_c000684() -> None:
    """failures=neg, stamp=1.7, jitter=1.0: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(-1, storm, 1.0) == 1.7


def test_c000685() -> None:
    """failures=neg, stamp=1.8, jitter=0.5: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(-1, storm, 0.5) == 1.8


def test_c000686() -> None:
    """failures=neg, stamp=1.8, jitter=0.625: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(-1, storm, 0.625) == 1.8


def test_c000687() -> None:
    """failures=neg, stamp=1.8, jitter=0.75: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(-1, storm, 0.75) == 1.8


def test_c000688() -> None:
    """failures=neg, stamp=1.8, jitter=0.875: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(-1, storm, 0.875) == 1.8


def test_c000689() -> None:
    """failures=neg, stamp=1.8, jitter=1.0: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(-1, storm, 1.0) == 1.8


def test_c000690() -> None:
    """failures=neg, stamp=1.9, jitter=0.5: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(-1, storm, 0.5) == 1.9


def test_c000691() -> None:
    """failures=neg, stamp=1.9, jitter=0.625: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(-1, storm, 0.625) == 1.9


def test_c000692() -> None:
    """failures=neg, stamp=1.9, jitter=0.75: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(-1, storm, 0.75) == 1.9


def test_c000693() -> None:
    """failures=neg, stamp=1.9, jitter=0.875: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(-1, storm, 0.875) == 1.9


def test_c000694() -> None:
    """failures=neg, stamp=1.9, jitter=1.0: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(-1, storm, 1.0) == 1.9


def test_c000695() -> None:
    """failures=neg, stamp=2.0, jitter=0.5: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(-1, storm, 0.5) == 2.0


def test_c000696() -> None:
    """failures=neg, stamp=2.0, jitter=0.625: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(-1, storm, 0.625) == 2.0


def test_c000697() -> None:
    """failures=neg, stamp=2.0, jitter=0.75: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(-1, storm, 0.75) == 2.0


def test_c000698() -> None:
    """failures=neg, stamp=2.0, jitter=0.875: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(-1, storm, 0.875) == 2.0


def test_c000699() -> None:
    """failures=neg, stamp=2.0, jitter=1.0: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(-1, storm, 1.0) == 2.0


def test_c000700() -> None:
    """failures=neg, stamp=2.1, jitter=0.5: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(-1, storm, 0.5) == 2.1


def test_c000701() -> None:
    """failures=neg, stamp=2.1, jitter=0.625: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(-1, storm, 0.625) == 2.1


def test_c000702() -> None:
    """failures=neg, stamp=2.1, jitter=0.75: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(-1, storm, 0.75) == 2.1


def test_c000703() -> None:
    """failures=neg, stamp=2.1, jitter=0.875: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(-1, storm, 0.875) == 2.1


def test_c000704() -> None:
    """failures=neg, stamp=2.1, jitter=1.0: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(-1, storm, 1.0) == 2.1


def test_c000705() -> None:
    """failures=neg, stamp=2.2, jitter=0.5: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(-1, storm, 0.5) == 2.2


def test_c000706() -> None:
    """failures=neg, stamp=2.2, jitter=0.625: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(-1, storm, 0.625) == 2.2


def test_c000707() -> None:
    """failures=neg, stamp=2.2, jitter=0.75: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(-1, storm, 0.75) == 2.2


def test_c000708() -> None:
    """failures=neg, stamp=2.2, jitter=0.875: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(-1, storm, 0.875) == 2.2


def test_c000709() -> None:
    """failures=neg, stamp=2.2, jitter=1.0: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(-1, storm, 1.0) == 2.2


def test_c000710() -> None:
    """failures=neg, stamp=2.3, jitter=0.5: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(-1, storm, 0.5) == 2.3


def test_c000711() -> None:
    """failures=neg, stamp=2.3, jitter=0.625: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(-1, storm, 0.625) == 2.3


def test_c000712() -> None:
    """failures=neg, stamp=2.3, jitter=0.75: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(-1, storm, 0.75) == 2.3


def test_c000713() -> None:
    """failures=neg, stamp=2.3, jitter=0.875: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(-1, storm, 0.875) == 2.3


def test_c000714() -> None:
    """failures=neg, stamp=2.3, jitter=1.0: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(-1, storm, 1.0) == 2.3


def test_c000715() -> None:
    """failures=neg, stamp=2.4, jitter=0.5: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(-1, storm, 0.5) == 2.4


def test_c000716() -> None:
    """failures=neg, stamp=2.4, jitter=0.625: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(-1, storm, 0.625) == 2.4


def test_c000717() -> None:
    """failures=neg, stamp=2.4, jitter=0.75: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(-1, storm, 0.75) == 2.4


def test_c000718() -> None:
    """failures=neg, stamp=2.4, jitter=0.875: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(-1, storm, 0.875) == 2.4


def test_c000719() -> None:
    """failures=neg, stamp=2.4, jitter=1.0: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(-1, storm, 1.0) == 2.4


def test_c000720() -> None:
    """failures=neg, stamp=2.5, jitter=0.5: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(-1, storm, 0.5) == 2.5


def test_c000721() -> None:
    """failures=neg, stamp=2.5, jitter=0.625: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(-1, storm, 0.625) == 2.5


def test_c000722() -> None:
    """failures=neg, stamp=2.5, jitter=0.75: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(-1, storm, 0.75) == 2.5


def test_c000723() -> None:
    """failures=neg, stamp=2.5, jitter=0.875: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(-1, storm, 0.875) == 2.5


def test_c000724() -> None:
    """failures=neg, stamp=2.5, jitter=1.0: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(-1, storm, 1.0) == 2.5


def test_c000725() -> None:
    """failures=neg, stamp=2.6, jitter=0.5: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(-1, storm, 0.5) == 2.6


def test_c000726() -> None:
    """failures=neg, stamp=2.6, jitter=0.625: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(-1, storm, 0.625) == 2.6


def test_c000727() -> None:
    """failures=neg, stamp=2.6, jitter=0.75: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(-1, storm, 0.75) == 2.6


def test_c000728() -> None:
    """failures=neg, stamp=2.6, jitter=0.875: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(-1, storm, 0.875) == 2.6


def test_c000729() -> None:
    """failures=neg, stamp=2.6, jitter=1.0: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(-1, storm, 1.0) == 2.6


def test_c000730() -> None:
    """failures=neg, stamp=2.7, jitter=0.5: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(-1, storm, 0.5) == 2.7


def test_c000731() -> None:
    """failures=neg, stamp=2.7, jitter=0.625: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(-1, storm, 0.625) == 2.7


def test_c000732() -> None:
    """failures=neg, stamp=2.7, jitter=0.75: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(-1, storm, 0.75) == 2.7


def test_c000733() -> None:
    """failures=neg, stamp=2.7, jitter=0.875: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(-1, storm, 0.875) == 2.7


def test_c000734() -> None:
    """failures=neg, stamp=2.7, jitter=1.0: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(-1, storm, 1.0) == 2.7


def test_c000735() -> None:
    """failures=neg, stamp=2.8, jitter=0.5: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(-1, storm, 0.5) == 2.8


def test_c000736() -> None:
    """failures=neg, stamp=2.8, jitter=0.625: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(-1, storm, 0.625) == 2.8


def test_c000737() -> None:
    """failures=neg, stamp=2.8, jitter=0.75: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(-1, storm, 0.75) == 2.8


def test_c000738() -> None:
    """failures=neg, stamp=2.8, jitter=0.875: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(-1, storm, 0.875) == 2.8


def test_c000739() -> None:
    """failures=neg, stamp=2.8, jitter=1.0: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(-1, storm, 1.0) == 2.8


def test_c000740() -> None:
    """failures=neg, stamp=2.9, jitter=0.5: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(-1, storm, 0.5) == 2.9


def test_c000741() -> None:
    """failures=neg, stamp=2.9, jitter=0.625: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(-1, storm, 0.625) == 2.9


def test_c000742() -> None:
    """failures=neg, stamp=2.9, jitter=0.75: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(-1, storm, 0.75) == 2.9


def test_c000743() -> None:
    """failures=neg, stamp=2.9, jitter=0.875: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(-1, storm, 0.875) == 2.9


def test_c000744() -> None:
    """failures=neg, stamp=2.9, jitter=1.0: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(-1, storm, 1.0) == 2.9


def test_c000745() -> None:
    """failures=neg, stamp=3.0, jitter=0.5: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(-1, storm, 0.5) == 3.0


def test_c000746() -> None:
    """failures=neg, stamp=3.0, jitter=0.625: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(-1, storm, 0.625) == 3.0


def test_c000747() -> None:
    """failures=neg, stamp=3.0, jitter=0.75: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(-1, storm, 0.75) == 3.0


def test_c000748() -> None:
    """failures=neg, stamp=3.0, jitter=0.875: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(-1, storm, 0.875) == 3.0


def test_c000749() -> None:
    """failures=neg, stamp=3.0, jitter=1.0: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(-1, storm, 1.0) == 3.0


def test_c000750() -> None:
    """failures=neg, stamp=3.1, jitter=0.5: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(-1, storm, 0.5) == 3.1


def test_c000751() -> None:
    """failures=neg, stamp=3.1, jitter=0.625: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(-1, storm, 0.625) == 3.1


def test_c000752() -> None:
    """failures=neg, stamp=3.1, jitter=0.75: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(-1, storm, 0.75) == 3.1


def test_c000753() -> None:
    """failures=neg, stamp=3.1, jitter=0.875: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(-1, storm, 0.875) == 3.1


def test_c000754() -> None:
    """failures=neg, stamp=3.1, jitter=1.0: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(-1, storm, 1.0) == 3.1


def test_c000755() -> None:
    """failures=neg, stamp=3.2, jitter=0.5: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(-1, storm, 0.5) == 3.2


def test_c000756() -> None:
    """failures=neg, stamp=3.2, jitter=0.625: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(-1, storm, 0.625) == 3.2


def test_c000757() -> None:
    """failures=neg, stamp=3.2, jitter=0.75: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(-1, storm, 0.75) == 3.2


def test_c000758() -> None:
    """failures=neg, stamp=3.2, jitter=0.875: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(-1, storm, 0.875) == 3.2


def test_c000759() -> None:
    """failures=neg, stamp=3.2, jitter=1.0: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(-1, storm, 1.0) == 3.2


def test_c000760() -> None:
    """failures=neg, stamp=3.3, jitter=0.5: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(-1, storm, 0.5) == 3.3


def test_c000761() -> None:
    """failures=neg, stamp=3.3, jitter=0.625: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(-1, storm, 0.625) == 3.3


def test_c000762() -> None:
    """failures=neg, stamp=3.3, jitter=0.75: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(-1, storm, 0.75) == 3.3


def test_c000763() -> None:
    """failures=neg, stamp=3.3, jitter=0.875: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(-1, storm, 0.875) == 3.3


def test_c000764() -> None:
    """failures=neg, stamp=3.3, jitter=1.0: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(-1, storm, 1.0) == 3.3


def test_c000765() -> None:
    """failures=neg, stamp=3.4, jitter=0.5: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(-1, storm, 0.5) == 3.4


def test_c000766() -> None:
    """failures=neg, stamp=3.4, jitter=0.625: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(-1, storm, 0.625) == 3.4


def test_c000767() -> None:
    """failures=neg, stamp=3.4, jitter=0.75: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(-1, storm, 0.75) == 3.4


def test_c000768() -> None:
    """failures=neg, stamp=3.4, jitter=0.875: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(-1, storm, 0.875) == 3.4


def test_c000769() -> None:
    """failures=neg, stamp=3.4, jitter=1.0: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(-1, storm, 1.0) == 3.4


def test_c000770() -> None:
    """failures=neg, stamp=3.5, jitter=0.5: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(-1, storm, 0.5) == 3.5


def test_c000771() -> None:
    """failures=neg, stamp=3.5, jitter=0.625: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(-1, storm, 0.625) == 3.5


def test_c000772() -> None:
    """failures=neg, stamp=3.5, jitter=0.75: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(-1, storm, 0.75) == 3.5


def test_c000773() -> None:
    """failures=neg, stamp=3.5, jitter=0.875: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(-1, storm, 0.875) == 3.5


def test_c000774() -> None:
    """failures=neg, stamp=3.5, jitter=1.0: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(-1, storm, 1.0) == 3.5


def test_c000775() -> None:
    """failures=neg, stamp=3.6, jitter=0.5: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(-1, storm, 0.5) == 3.6


def test_c000776() -> None:
    """failures=neg, stamp=3.6, jitter=0.625: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(-1, storm, 0.625) == 3.6


def test_c000777() -> None:
    """failures=neg, stamp=3.6, jitter=0.75: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(-1, storm, 0.75) == 3.6


def test_c000778() -> None:
    """failures=neg, stamp=3.6, jitter=0.875: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(-1, storm, 0.875) == 3.6


def test_c000779() -> None:
    """failures=neg, stamp=3.6, jitter=1.0: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(-1, storm, 1.0) == 3.6


def test_c000780() -> None:
    """failures=neg, stamp=3.7, jitter=0.5: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(-1, storm, 0.5) == 3.7


def test_c000781() -> None:
    """failures=neg, stamp=3.7, jitter=0.625: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(-1, storm, 0.625) == 3.7


def test_c000782() -> None:
    """failures=neg, stamp=3.7, jitter=0.75: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(-1, storm, 0.75) == 3.7


def test_c000783() -> None:
    """failures=neg, stamp=3.7, jitter=0.875: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(-1, storm, 0.875) == 3.7


def test_c000784() -> None:
    """failures=neg, stamp=3.7, jitter=1.0: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(-1, storm, 1.0) == 3.7


def test_c000785() -> None:
    """failures=neg, stamp=3.8, jitter=0.5: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(-1, storm, 0.5) == 3.8


def test_c000786() -> None:
    """failures=neg, stamp=3.8, jitter=0.625: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(-1, storm, 0.625) == 3.8


def test_c000787() -> None:
    """failures=neg, stamp=3.8, jitter=0.75: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(-1, storm, 0.75) == 3.8


def test_c000788() -> None:
    """failures=neg, stamp=3.8, jitter=0.875: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(-1, storm, 0.875) == 3.8


def test_c000789() -> None:
    """failures=neg, stamp=3.8, jitter=1.0: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(-1, storm, 1.0) == 3.8


def test_c000790() -> None:
    """failures=neg, stamp=3.9, jitter=0.5: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(-1, storm, 0.5) == 3.9


def test_c000791() -> None:
    """failures=neg, stamp=3.9, jitter=0.625: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(-1, storm, 0.625) == 3.9


def test_c000792() -> None:
    """failures=neg, stamp=3.9, jitter=0.75: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(-1, storm, 0.75) == 3.9


def test_c000793() -> None:
    """failures=neg, stamp=3.9, jitter=0.875: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(-1, storm, 0.875) == 3.9


def test_c000794() -> None:
    """failures=neg, stamp=3.9, jitter=1.0: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(-1, storm, 1.0) == 3.9


def test_c000795() -> None:
    """failures=neg, stamp=4.0, jitter=0.5: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(-1, storm, 0.5) == 4.0


def test_c000796() -> None:
    """failures=neg, stamp=4.0, jitter=0.625: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(-1, storm, 0.625) == 4.0


def test_c000797() -> None:
    """failures=neg, stamp=4.0, jitter=0.75: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(-1, storm, 0.75) == 4.0


def test_c000798() -> None:
    """failures=neg, stamp=4.0, jitter=0.875: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(-1, storm, 0.875) == 4.0


def test_c000799() -> None:
    """failures=neg, stamp=4.0, jitter=1.0: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(-1, storm, 1.0) == 4.0


def test_c000800() -> None:
    """failures=str, stamp=0.1, jitter=0.5: storm 0.1, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay('5', storm, 0.5) == 0.5


def test_c000801() -> None:
    """failures=str, stamp=0.1, jitter=0.625: storm 0.1, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay('5', storm, 0.625) == 0.625


def test_c000802() -> None:
    """failures=str, stamp=0.1, jitter=0.75: storm 0.1, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay('5', storm, 0.75) == 0.75


def test_c000803() -> None:
    """failures=str, stamp=0.1, jitter=0.875: storm 0.1, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000804() -> None:
    """failures=str, stamp=0.1, jitter=1.0: storm 0.1, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000805() -> None:
    """failures=str, stamp=0.2, jitter=0.5: storm 0.2, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay('5', storm, 0.5) == 0.5


def test_c000806() -> None:
    """failures=str, stamp=0.2, jitter=0.625: storm 0.2, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay('5', storm, 0.625) == 0.625


def test_c000807() -> None:
    """failures=str, stamp=0.2, jitter=0.75: storm 0.2, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay('5', storm, 0.75) == 0.75


def test_c000808() -> None:
    """failures=str, stamp=0.2, jitter=0.875: storm 0.2, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000809() -> None:
    """failures=str, stamp=0.2, jitter=1.0: storm 0.2, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000810() -> None:
    """failures=str, stamp=0.3, jitter=0.5: storm 0.3, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay('5', storm, 0.5) == 0.5


def test_c000811() -> None:
    """failures=str, stamp=0.3, jitter=0.625: storm 0.3, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay('5', storm, 0.625) == 0.625


def test_c000812() -> None:
    """failures=str, stamp=0.3, jitter=0.75: storm 0.3, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay('5', storm, 0.75) == 0.75


def test_c000813() -> None:
    """failures=str, stamp=0.3, jitter=0.875: storm 0.3, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000814() -> None:
    """failures=str, stamp=0.3, jitter=1.0: storm 0.3, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000815() -> None:
    """failures=str, stamp=0.4, jitter=0.5: storm 0.4, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay('5', storm, 0.5) == 0.5


def test_c000816() -> None:
    """failures=str, stamp=0.4, jitter=0.625: storm 0.4, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay('5', storm, 0.625) == 0.625


def test_c000817() -> None:
    """failures=str, stamp=0.4, jitter=0.75: storm 0.4, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay('5', storm, 0.75) == 0.75


def test_c000818() -> None:
    """failures=str, stamp=0.4, jitter=0.875: storm 0.4, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000819() -> None:
    """failures=str, stamp=0.4, jitter=1.0: storm 0.4, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000820() -> None:
    """failures=str, stamp=0.5, jitter=0.5: storm 0.5, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay('5', storm, 0.5) == 0.5


def test_c000821() -> None:
    """failures=str, stamp=0.5, jitter=0.625: storm 0.5, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay('5', storm, 0.625) == 0.625


def test_c000822() -> None:
    """failures=str, stamp=0.5, jitter=0.75: storm 0.5, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay('5', storm, 0.75) == 0.75


def test_c000823() -> None:
    """failures=str, stamp=0.5, jitter=0.875: storm 0.5, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000824() -> None:
    """failures=str, stamp=0.5, jitter=1.0: storm 0.5, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000825() -> None:
    """failures=str, stamp=0.6, jitter=0.5: storm 0.6, delay 0.6."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay('5', storm, 0.5) == 0.6


def test_c000826() -> None:
    """failures=str, stamp=0.6, jitter=0.625: storm 0.6, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay('5', storm, 0.625) == 0.625


def test_c000827() -> None:
    """failures=str, stamp=0.6, jitter=0.75: storm 0.6, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay('5', storm, 0.75) == 0.75


def test_c000828() -> None:
    """failures=str, stamp=0.6, jitter=0.875: storm 0.6, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000829() -> None:
    """failures=str, stamp=0.6, jitter=1.0: storm 0.6, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000830() -> None:
    """failures=str, stamp=0.7, jitter=0.5: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay('5', storm, 0.5) == 0.7


def test_c000831() -> None:
    """failures=str, stamp=0.7, jitter=0.625: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay('5', storm, 0.625) == 0.7


def test_c000832() -> None:
    """failures=str, stamp=0.7, jitter=0.75: storm 0.7, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay('5', storm, 0.75) == 0.75


def test_c000833() -> None:
    """failures=str, stamp=0.7, jitter=0.875: storm 0.7, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000834() -> None:
    """failures=str, stamp=0.7, jitter=1.0: storm 0.7, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000835() -> None:
    """failures=str, stamp=0.8, jitter=0.5: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay('5', storm, 0.5) == 0.8


def test_c000836() -> None:
    """failures=str, stamp=0.8, jitter=0.625: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay('5', storm, 0.625) == 0.8


def test_c000837() -> None:
    """failures=str, stamp=0.8, jitter=0.75: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay('5', storm, 0.75) == 0.8


def test_c000838() -> None:
    """failures=str, stamp=0.8, jitter=0.875: storm 0.8, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay('5', storm, 0.875) == 0.875


def test_c000839() -> None:
    """failures=str, stamp=0.8, jitter=1.0: storm 0.8, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000840() -> None:
    """failures=str, stamp=0.9, jitter=0.5: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay('5', storm, 0.5) == 0.9


def test_c000841() -> None:
    """failures=str, stamp=0.9, jitter=0.625: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay('5', storm, 0.625) == 0.9


def test_c000842() -> None:
    """failures=str, stamp=0.9, jitter=0.75: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay('5', storm, 0.75) == 0.9


def test_c000843() -> None:
    """failures=str, stamp=0.9, jitter=0.875: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay('5', storm, 0.875) == 0.9


def test_c000844() -> None:
    """failures=str, stamp=0.9, jitter=1.0: storm 0.9, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000845() -> None:
    """failures=str, stamp=1.0, jitter=0.5: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay('5', storm, 0.5) == 1.0


def test_c000846() -> None:
    """failures=str, stamp=1.0, jitter=0.625: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay('5', storm, 0.625) == 1.0


def test_c000847() -> None:
    """failures=str, stamp=1.0, jitter=0.75: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay('5', storm, 0.75) == 1.0


def test_c000848() -> None:
    """failures=str, stamp=1.0, jitter=0.875: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay('5', storm, 0.875) == 1.0


def test_c000849() -> None:
    """failures=str, stamp=1.0, jitter=1.0: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay('5', storm, 1.0) == 1.0


def test_c000850() -> None:
    """failures=str, stamp=1.1, jitter=0.5: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay('5', storm, 0.5) == 1.1


def test_c000851() -> None:
    """failures=str, stamp=1.1, jitter=0.625: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay('5', storm, 0.625) == 1.1


def test_c000852() -> None:
    """failures=str, stamp=1.1, jitter=0.75: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay('5', storm, 0.75) == 1.1


def test_c000853() -> None:
    """failures=str, stamp=1.1, jitter=0.875: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay('5', storm, 0.875) == 1.1


def test_c000854() -> None:
    """failures=str, stamp=1.1, jitter=1.0: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay('5', storm, 1.0) == 1.1


def test_c000855() -> None:
    """failures=str, stamp=1.2, jitter=0.5: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay('5', storm, 0.5) == 1.2


def test_c000856() -> None:
    """failures=str, stamp=1.2, jitter=0.625: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay('5', storm, 0.625) == 1.2


def test_c000857() -> None:
    """failures=str, stamp=1.2, jitter=0.75: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay('5', storm, 0.75) == 1.2


def test_c000858() -> None:
    """failures=str, stamp=1.2, jitter=0.875: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay('5', storm, 0.875) == 1.2


def test_c000859() -> None:
    """failures=str, stamp=1.2, jitter=1.0: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay('5', storm, 1.0) == 1.2


def test_c000860() -> None:
    """failures=str, stamp=1.3, jitter=0.5: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay('5', storm, 0.5) == 1.3


def test_c000861() -> None:
    """failures=str, stamp=1.3, jitter=0.625: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay('5', storm, 0.625) == 1.3


def test_c000862() -> None:
    """failures=str, stamp=1.3, jitter=0.75: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay('5', storm, 0.75) == 1.3


def test_c000863() -> None:
    """failures=str, stamp=1.3, jitter=0.875: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay('5', storm, 0.875) == 1.3


def test_c000864() -> None:
    """failures=str, stamp=1.3, jitter=1.0: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay('5', storm, 1.0) == 1.3


def test_c000865() -> None:
    """failures=str, stamp=1.4, jitter=0.5: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay('5', storm, 0.5) == 1.4


def test_c000866() -> None:
    """failures=str, stamp=1.4, jitter=0.625: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay('5', storm, 0.625) == 1.4


def test_c000867() -> None:
    """failures=str, stamp=1.4, jitter=0.75: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay('5', storm, 0.75) == 1.4


def test_c000868() -> None:
    """failures=str, stamp=1.4, jitter=0.875: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay('5', storm, 0.875) == 1.4


def test_c000869() -> None:
    """failures=str, stamp=1.4, jitter=1.0: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay('5', storm, 1.0) == 1.4


def test_c000870() -> None:
    """failures=str, stamp=1.5, jitter=0.5: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay('5', storm, 0.5) == 1.5


def test_c000871() -> None:
    """failures=str, stamp=1.5, jitter=0.625: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay('5', storm, 0.625) == 1.5


def test_c000872() -> None:
    """failures=str, stamp=1.5, jitter=0.75: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay('5', storm, 0.75) == 1.5


def test_c000873() -> None:
    """failures=str, stamp=1.5, jitter=0.875: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay('5', storm, 0.875) == 1.5


def test_c000874() -> None:
    """failures=str, stamp=1.5, jitter=1.0: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay('5', storm, 1.0) == 1.5


def test_c000875() -> None:
    """failures=str, stamp=1.6, jitter=0.5: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay('5', storm, 0.5) == 1.6


def test_c000876() -> None:
    """failures=str, stamp=1.6, jitter=0.625: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay('5', storm, 0.625) == 1.6


def test_c000877() -> None:
    """failures=str, stamp=1.6, jitter=0.75: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay('5', storm, 0.75) == 1.6


def test_c000878() -> None:
    """failures=str, stamp=1.6, jitter=0.875: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay('5', storm, 0.875) == 1.6


def test_c000879() -> None:
    """failures=str, stamp=1.6, jitter=1.0: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay('5', storm, 1.0) == 1.6


def test_c000880() -> None:
    """failures=str, stamp=1.7, jitter=0.5: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay('5', storm, 0.5) == 1.7


def test_c000881() -> None:
    """failures=str, stamp=1.7, jitter=0.625: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay('5', storm, 0.625) == 1.7


def test_c000882() -> None:
    """failures=str, stamp=1.7, jitter=0.75: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay('5', storm, 0.75) == 1.7


def test_c000883() -> None:
    """failures=str, stamp=1.7, jitter=0.875: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay('5', storm, 0.875) == 1.7


def test_c000884() -> None:
    """failures=str, stamp=1.7, jitter=1.0: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay('5', storm, 1.0) == 1.7


def test_c000885() -> None:
    """failures=str, stamp=1.8, jitter=0.5: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay('5', storm, 0.5) == 1.8


def test_c000886() -> None:
    """failures=str, stamp=1.8, jitter=0.625: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay('5', storm, 0.625) == 1.8


def test_c000887() -> None:
    """failures=str, stamp=1.8, jitter=0.75: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay('5', storm, 0.75) == 1.8


def test_c000888() -> None:
    """failures=str, stamp=1.8, jitter=0.875: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay('5', storm, 0.875) == 1.8


def test_c000889() -> None:
    """failures=str, stamp=1.8, jitter=1.0: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay('5', storm, 1.0) == 1.8


def test_c000890() -> None:
    """failures=str, stamp=1.9, jitter=0.5: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay('5', storm, 0.5) == 1.9


def test_c000891() -> None:
    """failures=str, stamp=1.9, jitter=0.625: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay('5', storm, 0.625) == 1.9


def test_c000892() -> None:
    """failures=str, stamp=1.9, jitter=0.75: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay('5', storm, 0.75) == 1.9


def test_c000893() -> None:
    """failures=str, stamp=1.9, jitter=0.875: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay('5', storm, 0.875) == 1.9


def test_c000894() -> None:
    """failures=str, stamp=1.9, jitter=1.0: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay('5', storm, 1.0) == 1.9


def test_c000895() -> None:
    """failures=str, stamp=2.0, jitter=0.5: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay('5', storm, 0.5) == 2.0


def test_c000896() -> None:
    """failures=str, stamp=2.0, jitter=0.625: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay('5', storm, 0.625) == 2.0


def test_c000897() -> None:
    """failures=str, stamp=2.0, jitter=0.75: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay('5', storm, 0.75) == 2.0


def test_c000898() -> None:
    """failures=str, stamp=2.0, jitter=0.875: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay('5', storm, 0.875) == 2.0


def test_c000899() -> None:
    """failures=str, stamp=2.0, jitter=1.0: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay('5', storm, 1.0) == 2.0


def test_c000900() -> None:
    """failures=str, stamp=2.1, jitter=0.5: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay('5', storm, 0.5) == 2.1


def test_c000901() -> None:
    """failures=str, stamp=2.1, jitter=0.625: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay('5', storm, 0.625) == 2.1


def test_c000902() -> None:
    """failures=str, stamp=2.1, jitter=0.75: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay('5', storm, 0.75) == 2.1


def test_c000903() -> None:
    """failures=str, stamp=2.1, jitter=0.875: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay('5', storm, 0.875) == 2.1


def test_c000904() -> None:
    """failures=str, stamp=2.1, jitter=1.0: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay('5', storm, 1.0) == 2.1


def test_c000905() -> None:
    """failures=str, stamp=2.2, jitter=0.5: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay('5', storm, 0.5) == 2.2


def test_c000906() -> None:
    """failures=str, stamp=2.2, jitter=0.625: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay('5', storm, 0.625) == 2.2


def test_c000907() -> None:
    """failures=str, stamp=2.2, jitter=0.75: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay('5', storm, 0.75) == 2.2


def test_c000908() -> None:
    """failures=str, stamp=2.2, jitter=0.875: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay('5', storm, 0.875) == 2.2


def test_c000909() -> None:
    """failures=str, stamp=2.2, jitter=1.0: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay('5', storm, 1.0) == 2.2


def test_c000910() -> None:
    """failures=str, stamp=2.3, jitter=0.5: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay('5', storm, 0.5) == 2.3


def test_c000911() -> None:
    """failures=str, stamp=2.3, jitter=0.625: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay('5', storm, 0.625) == 2.3


def test_c000912() -> None:
    """failures=str, stamp=2.3, jitter=0.75: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay('5', storm, 0.75) == 2.3


def test_c000913() -> None:
    """failures=str, stamp=2.3, jitter=0.875: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay('5', storm, 0.875) == 2.3


def test_c000914() -> None:
    """failures=str, stamp=2.3, jitter=1.0: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay('5', storm, 1.0) == 2.3


def test_c000915() -> None:
    """failures=str, stamp=2.4, jitter=0.5: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay('5', storm, 0.5) == 2.4


def test_c000916() -> None:
    """failures=str, stamp=2.4, jitter=0.625: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay('5', storm, 0.625) == 2.4


def test_c000917() -> None:
    """failures=str, stamp=2.4, jitter=0.75: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay('5', storm, 0.75) == 2.4


def test_c000918() -> None:
    """failures=str, stamp=2.4, jitter=0.875: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay('5', storm, 0.875) == 2.4


def test_c000919() -> None:
    """failures=str, stamp=2.4, jitter=1.0: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay('5', storm, 1.0) == 2.4


def test_c000920() -> None:
    """failures=str, stamp=2.5, jitter=0.5: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay('5', storm, 0.5) == 2.5


def test_c000921() -> None:
    """failures=str, stamp=2.5, jitter=0.625: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay('5', storm, 0.625) == 2.5


def test_c000922() -> None:
    """failures=str, stamp=2.5, jitter=0.75: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay('5', storm, 0.75) == 2.5


def test_c000923() -> None:
    """failures=str, stamp=2.5, jitter=0.875: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay('5', storm, 0.875) == 2.5


def test_c000924() -> None:
    """failures=str, stamp=2.5, jitter=1.0: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay('5', storm, 1.0) == 2.5


def test_c000925() -> None:
    """failures=str, stamp=2.6, jitter=0.5: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay('5', storm, 0.5) == 2.6


def test_c000926() -> None:
    """failures=str, stamp=2.6, jitter=0.625: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay('5', storm, 0.625) == 2.6


def test_c000927() -> None:
    """failures=str, stamp=2.6, jitter=0.75: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay('5', storm, 0.75) == 2.6


def test_c000928() -> None:
    """failures=str, stamp=2.6, jitter=0.875: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay('5', storm, 0.875) == 2.6


def test_c000929() -> None:
    """failures=str, stamp=2.6, jitter=1.0: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay('5', storm, 1.0) == 2.6


def test_c000930() -> None:
    """failures=str, stamp=2.7, jitter=0.5: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay('5', storm, 0.5) == 2.7


def test_c000931() -> None:
    """failures=str, stamp=2.7, jitter=0.625: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay('5', storm, 0.625) == 2.7


def test_c000932() -> None:
    """failures=str, stamp=2.7, jitter=0.75: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay('5', storm, 0.75) == 2.7


def test_c000933() -> None:
    """failures=str, stamp=2.7, jitter=0.875: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay('5', storm, 0.875) == 2.7


def test_c000934() -> None:
    """failures=str, stamp=2.7, jitter=1.0: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay('5', storm, 1.0) == 2.7


def test_c000935() -> None:
    """failures=str, stamp=2.8, jitter=0.5: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay('5', storm, 0.5) == 2.8


def test_c000936() -> None:
    """failures=str, stamp=2.8, jitter=0.625: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay('5', storm, 0.625) == 2.8


def test_c000937() -> None:
    """failures=str, stamp=2.8, jitter=0.75: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay('5', storm, 0.75) == 2.8


def test_c000938() -> None:
    """failures=str, stamp=2.8, jitter=0.875: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay('5', storm, 0.875) == 2.8


def test_c000939() -> None:
    """failures=str, stamp=2.8, jitter=1.0: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay('5', storm, 1.0) == 2.8


def test_c000940() -> None:
    """failures=str, stamp=2.9, jitter=0.5: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay('5', storm, 0.5) == 2.9


def test_c000941() -> None:
    """failures=str, stamp=2.9, jitter=0.625: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay('5', storm, 0.625) == 2.9


def test_c000942() -> None:
    """failures=str, stamp=2.9, jitter=0.75: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay('5', storm, 0.75) == 2.9


def test_c000943() -> None:
    """failures=str, stamp=2.9, jitter=0.875: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay('5', storm, 0.875) == 2.9


def test_c000944() -> None:
    """failures=str, stamp=2.9, jitter=1.0: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay('5', storm, 1.0) == 2.9


def test_c000945() -> None:
    """failures=str, stamp=3.0, jitter=0.5: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay('5', storm, 0.5) == 3.0


def test_c000946() -> None:
    """failures=str, stamp=3.0, jitter=0.625: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay('5', storm, 0.625) == 3.0


def test_c000947() -> None:
    """failures=str, stamp=3.0, jitter=0.75: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay('5', storm, 0.75) == 3.0


def test_c000948() -> None:
    """failures=str, stamp=3.0, jitter=0.875: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay('5', storm, 0.875) == 3.0


def test_c000949() -> None:
    """failures=str, stamp=3.0, jitter=1.0: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay('5', storm, 1.0) == 3.0


def test_c000950() -> None:
    """failures=str, stamp=3.1, jitter=0.5: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay('5', storm, 0.5) == 3.1


def test_c000951() -> None:
    """failures=str, stamp=3.1, jitter=0.625: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay('5', storm, 0.625) == 3.1


def test_c000952() -> None:
    """failures=str, stamp=3.1, jitter=0.75: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay('5', storm, 0.75) == 3.1


def test_c000953() -> None:
    """failures=str, stamp=3.1, jitter=0.875: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay('5', storm, 0.875) == 3.1


def test_c000954() -> None:
    """failures=str, stamp=3.1, jitter=1.0: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay('5', storm, 1.0) == 3.1


def test_c000955() -> None:
    """failures=str, stamp=3.2, jitter=0.5: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay('5', storm, 0.5) == 3.2


def test_c000956() -> None:
    """failures=str, stamp=3.2, jitter=0.625: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay('5', storm, 0.625) == 3.2


def test_c000957() -> None:
    """failures=str, stamp=3.2, jitter=0.75: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay('5', storm, 0.75) == 3.2


def test_c000958() -> None:
    """failures=str, stamp=3.2, jitter=0.875: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay('5', storm, 0.875) == 3.2


def test_c000959() -> None:
    """failures=str, stamp=3.2, jitter=1.0: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay('5', storm, 1.0) == 3.2


def test_c000960() -> None:
    """failures=str, stamp=3.3, jitter=0.5: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay('5', storm, 0.5) == 3.3


def test_c000961() -> None:
    """failures=str, stamp=3.3, jitter=0.625: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay('5', storm, 0.625) == 3.3


def test_c000962() -> None:
    """failures=str, stamp=3.3, jitter=0.75: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay('5', storm, 0.75) == 3.3


def test_c000963() -> None:
    """failures=str, stamp=3.3, jitter=0.875: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay('5', storm, 0.875) == 3.3


def test_c000964() -> None:
    """failures=str, stamp=3.3, jitter=1.0: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay('5', storm, 1.0) == 3.3


def test_c000965() -> None:
    """failures=str, stamp=3.4, jitter=0.5: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay('5', storm, 0.5) == 3.4


def test_c000966() -> None:
    """failures=str, stamp=3.4, jitter=0.625: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay('5', storm, 0.625) == 3.4


def test_c000967() -> None:
    """failures=str, stamp=3.4, jitter=0.75: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay('5', storm, 0.75) == 3.4


def test_c000968() -> None:
    """failures=str, stamp=3.4, jitter=0.875: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay('5', storm, 0.875) == 3.4


def test_c000969() -> None:
    """failures=str, stamp=3.4, jitter=1.0: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay('5', storm, 1.0) == 3.4


def test_c000970() -> None:
    """failures=str, stamp=3.5, jitter=0.5: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay('5', storm, 0.5) == 3.5


def test_c000971() -> None:
    """failures=str, stamp=3.5, jitter=0.625: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay('5', storm, 0.625) == 3.5


def test_c000972() -> None:
    """failures=str, stamp=3.5, jitter=0.75: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay('5', storm, 0.75) == 3.5


def test_c000973() -> None:
    """failures=str, stamp=3.5, jitter=0.875: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay('5', storm, 0.875) == 3.5


def test_c000974() -> None:
    """failures=str, stamp=3.5, jitter=1.0: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay('5', storm, 1.0) == 3.5


def test_c000975() -> None:
    """failures=str, stamp=3.6, jitter=0.5: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay('5', storm, 0.5) == 3.6


def test_c000976() -> None:
    """failures=str, stamp=3.6, jitter=0.625: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay('5', storm, 0.625) == 3.6


def test_c000977() -> None:
    """failures=str, stamp=3.6, jitter=0.75: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay('5', storm, 0.75) == 3.6


def test_c000978() -> None:
    """failures=str, stamp=3.6, jitter=0.875: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay('5', storm, 0.875) == 3.6


def test_c000979() -> None:
    """failures=str, stamp=3.6, jitter=1.0: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay('5', storm, 1.0) == 3.6


def test_c000980() -> None:
    """failures=str, stamp=3.7, jitter=0.5: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay('5', storm, 0.5) == 3.7


def test_c000981() -> None:
    """failures=str, stamp=3.7, jitter=0.625: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay('5', storm, 0.625) == 3.7


def test_c000982() -> None:
    """failures=str, stamp=3.7, jitter=0.75: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay('5', storm, 0.75) == 3.7


def test_c000983() -> None:
    """failures=str, stamp=3.7, jitter=0.875: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay('5', storm, 0.875) == 3.7


def test_c000984() -> None:
    """failures=str, stamp=3.7, jitter=1.0: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay('5', storm, 1.0) == 3.7


def test_c000985() -> None:
    """failures=str, stamp=3.8, jitter=0.5: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay('5', storm, 0.5) == 3.8


def test_c000986() -> None:
    """failures=str, stamp=3.8, jitter=0.625: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay('5', storm, 0.625) == 3.8


def test_c000987() -> None:
    """failures=str, stamp=3.8, jitter=0.75: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay('5', storm, 0.75) == 3.8


def test_c000988() -> None:
    """failures=str, stamp=3.8, jitter=0.875: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay('5', storm, 0.875) == 3.8


def test_c000989() -> None:
    """failures=str, stamp=3.8, jitter=1.0: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay('5', storm, 1.0) == 3.8


def test_c000990() -> None:
    """failures=str, stamp=3.9, jitter=0.5: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay('5', storm, 0.5) == 3.9


def test_c000991() -> None:
    """failures=str, stamp=3.9, jitter=0.625: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay('5', storm, 0.625) == 3.9


def test_c000992() -> None:
    """failures=str, stamp=3.9, jitter=0.75: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay('5', storm, 0.75) == 3.9


def test_c000993() -> None:
    """failures=str, stamp=3.9, jitter=0.875: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay('5', storm, 0.875) == 3.9


def test_c000994() -> None:
    """failures=str, stamp=3.9, jitter=1.0: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay('5', storm, 1.0) == 3.9


def test_c000995() -> None:
    """failures=str, stamp=4.0, jitter=0.5: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay('5', storm, 0.5) == 4.0


def test_c000996() -> None:
    """failures=str, stamp=4.0, jitter=0.625: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay('5', storm, 0.625) == 4.0


def test_c000997() -> None:
    """failures=str, stamp=4.0, jitter=0.75: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay('5', storm, 0.75) == 4.0


def test_c000998() -> None:
    """failures=str, stamp=4.0, jitter=0.875: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay('5', storm, 0.875) == 4.0


def test_c000999() -> None:
    """failures=str, stamp=4.0, jitter=1.0: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay('5', storm, 1.0) == 4.0


def test_c001000() -> None:
    """failures=float, stamp=0.1, jitter=0.5: storm 0.1, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.5


def test_c001001() -> None:
    """failures=float, stamp=0.1, jitter=0.625: storm 0.1, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.625


def test_c001002() -> None:
    """failures=float, stamp=0.1, jitter=0.75: storm 0.1, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.75


def test_c001003() -> None:
    """failures=float, stamp=0.1, jitter=0.875: storm 0.1, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001004() -> None:
    """failures=float, stamp=0.1, jitter=1.0: storm 0.1, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001005() -> None:
    """failures=float, stamp=0.2, jitter=0.5: storm 0.2, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.5


def test_c001006() -> None:
    """failures=float, stamp=0.2, jitter=0.625: storm 0.2, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.625


def test_c001007() -> None:
    """failures=float, stamp=0.2, jitter=0.75: storm 0.2, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.75


def test_c001008() -> None:
    """failures=float, stamp=0.2, jitter=0.875: storm 0.2, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001009() -> None:
    """failures=float, stamp=0.2, jitter=1.0: storm 0.2, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001010() -> None:
    """failures=float, stamp=0.3, jitter=0.5: storm 0.3, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.5


def test_c001011() -> None:
    """failures=float, stamp=0.3, jitter=0.625: storm 0.3, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.625


def test_c001012() -> None:
    """failures=float, stamp=0.3, jitter=0.75: storm 0.3, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.75


def test_c001013() -> None:
    """failures=float, stamp=0.3, jitter=0.875: storm 0.3, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001014() -> None:
    """failures=float, stamp=0.3, jitter=1.0: storm 0.3, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001015() -> None:
    """failures=float, stamp=0.4, jitter=0.5: storm 0.4, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.5


def test_c001016() -> None:
    """failures=float, stamp=0.4, jitter=0.625: storm 0.4, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.625


def test_c001017() -> None:
    """failures=float, stamp=0.4, jitter=0.75: storm 0.4, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.75


def test_c001018() -> None:
    """failures=float, stamp=0.4, jitter=0.875: storm 0.4, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001019() -> None:
    """failures=float, stamp=0.4, jitter=1.0: storm 0.4, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001020() -> None:
    """failures=float, stamp=0.5, jitter=0.5: storm 0.5, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.5


def test_c001021() -> None:
    """failures=float, stamp=0.5, jitter=0.625: storm 0.5, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.625


def test_c001022() -> None:
    """failures=float, stamp=0.5, jitter=0.75: storm 0.5, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.75


def test_c001023() -> None:
    """failures=float, stamp=0.5, jitter=0.875: storm 0.5, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001024() -> None:
    """failures=float, stamp=0.5, jitter=1.0: storm 0.5, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001025() -> None:
    """failures=float, stamp=0.6, jitter=0.5: storm 0.6, delay 0.6."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.6


def test_c001026() -> None:
    """failures=float, stamp=0.6, jitter=0.625: storm 0.6, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.625


def test_c001027() -> None:
    """failures=float, stamp=0.6, jitter=0.75: storm 0.6, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.75


def test_c001028() -> None:
    """failures=float, stamp=0.6, jitter=0.875: storm 0.6, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001029() -> None:
    """failures=float, stamp=0.6, jitter=1.0: storm 0.6, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001030() -> None:
    """failures=float, stamp=0.7, jitter=0.5: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.7


def test_c001031() -> None:
    """failures=float, stamp=0.7, jitter=0.625: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.7


def test_c001032() -> None:
    """failures=float, stamp=0.7, jitter=0.75: storm 0.7, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.75


def test_c001033() -> None:
    """failures=float, stamp=0.7, jitter=0.875: storm 0.7, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001034() -> None:
    """failures=float, stamp=0.7, jitter=1.0: storm 0.7, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001035() -> None:
    """failures=float, stamp=0.8, jitter=0.5: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.8


def test_c001036() -> None:
    """failures=float, stamp=0.8, jitter=0.625: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.8


def test_c001037() -> None:
    """failures=float, stamp=0.8, jitter=0.75: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.8


def test_c001038() -> None:
    """failures=float, stamp=0.8, jitter=0.875: storm 0.8, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.875


def test_c001039() -> None:
    """failures=float, stamp=0.8, jitter=1.0: storm 0.8, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001040() -> None:
    """failures=float, stamp=0.9, jitter=0.5: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(5.0, storm, 0.5) == 0.9


def test_c001041() -> None:
    """failures=float, stamp=0.9, jitter=0.625: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(5.0, storm, 0.625) == 0.9


def test_c001042() -> None:
    """failures=float, stamp=0.9, jitter=0.75: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(5.0, storm, 0.75) == 0.9


def test_c001043() -> None:
    """failures=float, stamp=0.9, jitter=0.875: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(5.0, storm, 0.875) == 0.9


def test_c001044() -> None:
    """failures=float, stamp=0.9, jitter=1.0: storm 0.9, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001045() -> None:
    """failures=float, stamp=1.0, jitter=0.5: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.0


def test_c001046() -> None:
    """failures=float, stamp=1.0, jitter=0.625: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.0


def test_c001047() -> None:
    """failures=float, stamp=1.0, jitter=0.75: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.0


def test_c001048() -> None:
    """failures=float, stamp=1.0, jitter=0.875: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.0


def test_c001049() -> None:
    """failures=float, stamp=1.0, jitter=1.0: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.0


def test_c001050() -> None:
    """failures=float, stamp=1.1, jitter=0.5: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.1


def test_c001051() -> None:
    """failures=float, stamp=1.1, jitter=0.625: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.1


def test_c001052() -> None:
    """failures=float, stamp=1.1, jitter=0.75: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.1


def test_c001053() -> None:
    """failures=float, stamp=1.1, jitter=0.875: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.1


def test_c001054() -> None:
    """failures=float, stamp=1.1, jitter=1.0: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.1


def test_c001055() -> None:
    """failures=float, stamp=1.2, jitter=0.5: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.2


def test_c001056() -> None:
    """failures=float, stamp=1.2, jitter=0.625: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.2


def test_c001057() -> None:
    """failures=float, stamp=1.2, jitter=0.75: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.2


def test_c001058() -> None:
    """failures=float, stamp=1.2, jitter=0.875: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.2


def test_c001059() -> None:
    """failures=float, stamp=1.2, jitter=1.0: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.2


def test_c001060() -> None:
    """failures=float, stamp=1.3, jitter=0.5: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.3


def test_c001061() -> None:
    """failures=float, stamp=1.3, jitter=0.625: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.3


def test_c001062() -> None:
    """failures=float, stamp=1.3, jitter=0.75: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.3


def test_c001063() -> None:
    """failures=float, stamp=1.3, jitter=0.875: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.3


def test_c001064() -> None:
    """failures=float, stamp=1.3, jitter=1.0: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.3


def test_c001065() -> None:
    """failures=float, stamp=1.4, jitter=0.5: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.4


def test_c001066() -> None:
    """failures=float, stamp=1.4, jitter=0.625: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.4


def test_c001067() -> None:
    """failures=float, stamp=1.4, jitter=0.75: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.4


def test_c001068() -> None:
    """failures=float, stamp=1.4, jitter=0.875: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.4


def test_c001069() -> None:
    """failures=float, stamp=1.4, jitter=1.0: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.4


def test_c001070() -> None:
    """failures=float, stamp=1.5, jitter=0.5: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.5


def test_c001071() -> None:
    """failures=float, stamp=1.5, jitter=0.625: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.5


def test_c001072() -> None:
    """failures=float, stamp=1.5, jitter=0.75: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.5


def test_c001073() -> None:
    """failures=float, stamp=1.5, jitter=0.875: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.5


def test_c001074() -> None:
    """failures=float, stamp=1.5, jitter=1.0: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.5


def test_c001075() -> None:
    """failures=float, stamp=1.6, jitter=0.5: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.6


def test_c001076() -> None:
    """failures=float, stamp=1.6, jitter=0.625: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.6


def test_c001077() -> None:
    """failures=float, stamp=1.6, jitter=0.75: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.6


def test_c001078() -> None:
    """failures=float, stamp=1.6, jitter=0.875: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.6


def test_c001079() -> None:
    """failures=float, stamp=1.6, jitter=1.0: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.6


def test_c001080() -> None:
    """failures=float, stamp=1.7, jitter=0.5: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.7


def test_c001081() -> None:
    """failures=float, stamp=1.7, jitter=0.625: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.7


def test_c001082() -> None:
    """failures=float, stamp=1.7, jitter=0.75: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.7


def test_c001083() -> None:
    """failures=float, stamp=1.7, jitter=0.875: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.7


def test_c001084() -> None:
    """failures=float, stamp=1.7, jitter=1.0: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.7


def test_c001085() -> None:
    """failures=float, stamp=1.8, jitter=0.5: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.8


def test_c001086() -> None:
    """failures=float, stamp=1.8, jitter=0.625: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.8


def test_c001087() -> None:
    """failures=float, stamp=1.8, jitter=0.75: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.8


def test_c001088() -> None:
    """failures=float, stamp=1.8, jitter=0.875: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.8


def test_c001089() -> None:
    """failures=float, stamp=1.8, jitter=1.0: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.8


def test_c001090() -> None:
    """failures=float, stamp=1.9, jitter=0.5: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(5.0, storm, 0.5) == 1.9


def test_c001091() -> None:
    """failures=float, stamp=1.9, jitter=0.625: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(5.0, storm, 0.625) == 1.9


def test_c001092() -> None:
    """failures=float, stamp=1.9, jitter=0.75: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(5.0, storm, 0.75) == 1.9


def test_c001093() -> None:
    """failures=float, stamp=1.9, jitter=0.875: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(5.0, storm, 0.875) == 1.9


def test_c001094() -> None:
    """failures=float, stamp=1.9, jitter=1.0: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(5.0, storm, 1.0) == 1.9


def test_c001095() -> None:
    """failures=float, stamp=2.0, jitter=0.5: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.0


def test_c001096() -> None:
    """failures=float, stamp=2.0, jitter=0.625: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.0


def test_c001097() -> None:
    """failures=float, stamp=2.0, jitter=0.75: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.0


def test_c001098() -> None:
    """failures=float, stamp=2.0, jitter=0.875: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.0


def test_c001099() -> None:
    """failures=float, stamp=2.0, jitter=1.0: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.0


def test_c001100() -> None:
    """failures=float, stamp=2.1, jitter=0.5: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.1


def test_c001101() -> None:
    """failures=float, stamp=2.1, jitter=0.625: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.1


def test_c001102() -> None:
    """failures=float, stamp=2.1, jitter=0.75: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.1


def test_c001103() -> None:
    """failures=float, stamp=2.1, jitter=0.875: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.1


def test_c001104() -> None:
    """failures=float, stamp=2.1, jitter=1.0: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.1


def test_c001105() -> None:
    """failures=float, stamp=2.2, jitter=0.5: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.2


def test_c001106() -> None:
    """failures=float, stamp=2.2, jitter=0.625: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.2


def test_c001107() -> None:
    """failures=float, stamp=2.2, jitter=0.75: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.2


def test_c001108() -> None:
    """failures=float, stamp=2.2, jitter=0.875: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.2


def test_c001109() -> None:
    """failures=float, stamp=2.2, jitter=1.0: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.2


def test_c001110() -> None:
    """failures=float, stamp=2.3, jitter=0.5: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.3


def test_c001111() -> None:
    """failures=float, stamp=2.3, jitter=0.625: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.3


def test_c001112() -> None:
    """failures=float, stamp=2.3, jitter=0.75: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.3


def test_c001113() -> None:
    """failures=float, stamp=2.3, jitter=0.875: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.3


def test_c001114() -> None:
    """failures=float, stamp=2.3, jitter=1.0: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.3


def test_c001115() -> None:
    """failures=float, stamp=2.4, jitter=0.5: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.4


def test_c001116() -> None:
    """failures=float, stamp=2.4, jitter=0.625: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.4


def test_c001117() -> None:
    """failures=float, stamp=2.4, jitter=0.75: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.4


def test_c001118() -> None:
    """failures=float, stamp=2.4, jitter=0.875: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.4


def test_c001119() -> None:
    """failures=float, stamp=2.4, jitter=1.0: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.4


def test_c001120() -> None:
    """failures=float, stamp=2.5, jitter=0.5: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.5


def test_c001121() -> None:
    """failures=float, stamp=2.5, jitter=0.625: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.5


def test_c001122() -> None:
    """failures=float, stamp=2.5, jitter=0.75: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.5


def test_c001123() -> None:
    """failures=float, stamp=2.5, jitter=0.875: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.5


def test_c001124() -> None:
    """failures=float, stamp=2.5, jitter=1.0: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.5


def test_c001125() -> None:
    """failures=float, stamp=2.6, jitter=0.5: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.6


def test_c001126() -> None:
    """failures=float, stamp=2.6, jitter=0.625: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.6


def test_c001127() -> None:
    """failures=float, stamp=2.6, jitter=0.75: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.6


def test_c001128() -> None:
    """failures=float, stamp=2.6, jitter=0.875: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.6


def test_c001129() -> None:
    """failures=float, stamp=2.6, jitter=1.0: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.6


def test_c001130() -> None:
    """failures=float, stamp=2.7, jitter=0.5: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.7


def test_c001131() -> None:
    """failures=float, stamp=2.7, jitter=0.625: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.7


def test_c001132() -> None:
    """failures=float, stamp=2.7, jitter=0.75: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.7


def test_c001133() -> None:
    """failures=float, stamp=2.7, jitter=0.875: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.7


def test_c001134() -> None:
    """failures=float, stamp=2.7, jitter=1.0: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.7


def test_c001135() -> None:
    """failures=float, stamp=2.8, jitter=0.5: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.8


def test_c001136() -> None:
    """failures=float, stamp=2.8, jitter=0.625: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.8


def test_c001137() -> None:
    """failures=float, stamp=2.8, jitter=0.75: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.8


def test_c001138() -> None:
    """failures=float, stamp=2.8, jitter=0.875: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.8


def test_c001139() -> None:
    """failures=float, stamp=2.8, jitter=1.0: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.8


def test_c001140() -> None:
    """failures=float, stamp=2.9, jitter=0.5: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(5.0, storm, 0.5) == 2.9


def test_c001141() -> None:
    """failures=float, stamp=2.9, jitter=0.625: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(5.0, storm, 0.625) == 2.9


def test_c001142() -> None:
    """failures=float, stamp=2.9, jitter=0.75: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(5.0, storm, 0.75) == 2.9


def test_c001143() -> None:
    """failures=float, stamp=2.9, jitter=0.875: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(5.0, storm, 0.875) == 2.9


def test_c001144() -> None:
    """failures=float, stamp=2.9, jitter=1.0: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(5.0, storm, 1.0) == 2.9


def test_c001145() -> None:
    """failures=float, stamp=3.0, jitter=0.5: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.0


def test_c001146() -> None:
    """failures=float, stamp=3.0, jitter=0.625: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.0


def test_c001147() -> None:
    """failures=float, stamp=3.0, jitter=0.75: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.0


def test_c001148() -> None:
    """failures=float, stamp=3.0, jitter=0.875: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.0


def test_c001149() -> None:
    """failures=float, stamp=3.0, jitter=1.0: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.0


def test_c001150() -> None:
    """failures=float, stamp=3.1, jitter=0.5: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.1


def test_c001151() -> None:
    """failures=float, stamp=3.1, jitter=0.625: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.1


def test_c001152() -> None:
    """failures=float, stamp=3.1, jitter=0.75: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.1


def test_c001153() -> None:
    """failures=float, stamp=3.1, jitter=0.875: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.1


def test_c001154() -> None:
    """failures=float, stamp=3.1, jitter=1.0: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.1


def test_c001155() -> None:
    """failures=float, stamp=3.2, jitter=0.5: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.2


def test_c001156() -> None:
    """failures=float, stamp=3.2, jitter=0.625: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.2


def test_c001157() -> None:
    """failures=float, stamp=3.2, jitter=0.75: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.2


def test_c001158() -> None:
    """failures=float, stamp=3.2, jitter=0.875: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.2


def test_c001159() -> None:
    """failures=float, stamp=3.2, jitter=1.0: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.2


def test_c001160() -> None:
    """failures=float, stamp=3.3, jitter=0.5: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.3


def test_c001161() -> None:
    """failures=float, stamp=3.3, jitter=0.625: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.3


def test_c001162() -> None:
    """failures=float, stamp=3.3, jitter=0.75: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.3


def test_c001163() -> None:
    """failures=float, stamp=3.3, jitter=0.875: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.3


def test_c001164() -> None:
    """failures=float, stamp=3.3, jitter=1.0: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.3


def test_c001165() -> None:
    """failures=float, stamp=3.4, jitter=0.5: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.4


def test_c001166() -> None:
    """failures=float, stamp=3.4, jitter=0.625: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.4


def test_c001167() -> None:
    """failures=float, stamp=3.4, jitter=0.75: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.4


def test_c001168() -> None:
    """failures=float, stamp=3.4, jitter=0.875: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.4


def test_c001169() -> None:
    """failures=float, stamp=3.4, jitter=1.0: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.4


def test_c001170() -> None:
    """failures=float, stamp=3.5, jitter=0.5: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.5


def test_c001171() -> None:
    """failures=float, stamp=3.5, jitter=0.625: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.5


def test_c001172() -> None:
    """failures=float, stamp=3.5, jitter=0.75: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.5


def test_c001173() -> None:
    """failures=float, stamp=3.5, jitter=0.875: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.5


def test_c001174() -> None:
    """failures=float, stamp=3.5, jitter=1.0: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.5


def test_c001175() -> None:
    """failures=float, stamp=3.6, jitter=0.5: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.6


def test_c001176() -> None:
    """failures=float, stamp=3.6, jitter=0.625: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.6


def test_c001177() -> None:
    """failures=float, stamp=3.6, jitter=0.75: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.6


def test_c001178() -> None:
    """failures=float, stamp=3.6, jitter=0.875: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.6


def test_c001179() -> None:
    """failures=float, stamp=3.6, jitter=1.0: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.6


def test_c001180() -> None:
    """failures=float, stamp=3.7, jitter=0.5: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.7


def test_c001181() -> None:
    """failures=float, stamp=3.7, jitter=0.625: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.7


def test_c001182() -> None:
    """failures=float, stamp=3.7, jitter=0.75: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.7


def test_c001183() -> None:
    """failures=float, stamp=3.7, jitter=0.875: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.7


def test_c001184() -> None:
    """failures=float, stamp=3.7, jitter=1.0: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.7


def test_c001185() -> None:
    """failures=float, stamp=3.8, jitter=0.5: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.8


def test_c001186() -> None:
    """failures=float, stamp=3.8, jitter=0.625: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.8


def test_c001187() -> None:
    """failures=float, stamp=3.8, jitter=0.75: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.8


def test_c001188() -> None:
    """failures=float, stamp=3.8, jitter=0.875: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.8


def test_c001189() -> None:
    """failures=float, stamp=3.8, jitter=1.0: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.8


def test_c001190() -> None:
    """failures=float, stamp=3.9, jitter=0.5: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(5.0, storm, 0.5) == 3.9


def test_c001191() -> None:
    """failures=float, stamp=3.9, jitter=0.625: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(5.0, storm, 0.625) == 3.9


def test_c001192() -> None:
    """failures=float, stamp=3.9, jitter=0.75: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(5.0, storm, 0.75) == 3.9


def test_c001193() -> None:
    """failures=float, stamp=3.9, jitter=0.875: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(5.0, storm, 0.875) == 3.9


def test_c001194() -> None:
    """failures=float, stamp=3.9, jitter=1.0: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(5.0, storm, 1.0) == 3.9


def test_c001195() -> None:
    """failures=float, stamp=4.0, jitter=0.5: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(5.0, storm, 0.5) == 4.0


def test_c001196() -> None:
    """failures=float, stamp=4.0, jitter=0.625: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(5.0, storm, 0.625) == 4.0


def test_c001197() -> None:
    """failures=float, stamp=4.0, jitter=0.75: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(5.0, storm, 0.75) == 4.0


def test_c001198() -> None:
    """failures=float, stamp=4.0, jitter=0.875: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(5.0, storm, 0.875) == 4.0


def test_c001199() -> None:
    """failures=float, stamp=4.0, jitter=1.0: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(5.0, storm, 1.0) == 4.0


def test_c001200() -> None:
    """failures=none, stamp=0.1, jitter=0.5: storm 0.1, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(None, storm, 0.5) == 0.5


def test_c001201() -> None:
    """failures=none, stamp=0.1, jitter=0.625: storm 0.1, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(None, storm, 0.625) == 0.625


def test_c001202() -> None:
    """failures=none, stamp=0.1, jitter=0.75: storm 0.1, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(None, storm, 0.75) == 0.75


def test_c001203() -> None:
    """failures=none, stamp=0.1, jitter=0.875: storm 0.1, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001204() -> None:
    """failures=none, stamp=0.1, jitter=1.0: storm 0.1, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001205() -> None:
    """failures=none, stamp=0.2, jitter=0.5: storm 0.2, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(None, storm, 0.5) == 0.5


def test_c001206() -> None:
    """failures=none, stamp=0.2, jitter=0.625: storm 0.2, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(None, storm, 0.625) == 0.625


def test_c001207() -> None:
    """failures=none, stamp=0.2, jitter=0.75: storm 0.2, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(None, storm, 0.75) == 0.75


def test_c001208() -> None:
    """failures=none, stamp=0.2, jitter=0.875: storm 0.2, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001209() -> None:
    """failures=none, stamp=0.2, jitter=1.0: storm 0.2, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001210() -> None:
    """failures=none, stamp=0.3, jitter=0.5: storm 0.3, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(None, storm, 0.5) == 0.5


def test_c001211() -> None:
    """failures=none, stamp=0.3, jitter=0.625: storm 0.3, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(None, storm, 0.625) == 0.625


def test_c001212() -> None:
    """failures=none, stamp=0.3, jitter=0.75: storm 0.3, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(None, storm, 0.75) == 0.75


def test_c001213() -> None:
    """failures=none, stamp=0.3, jitter=0.875: storm 0.3, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001214() -> None:
    """failures=none, stamp=0.3, jitter=1.0: storm 0.3, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001215() -> None:
    """failures=none, stamp=0.4, jitter=0.5: storm 0.4, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(None, storm, 0.5) == 0.5


def test_c001216() -> None:
    """failures=none, stamp=0.4, jitter=0.625: storm 0.4, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(None, storm, 0.625) == 0.625


def test_c001217() -> None:
    """failures=none, stamp=0.4, jitter=0.75: storm 0.4, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(None, storm, 0.75) == 0.75


def test_c001218() -> None:
    """failures=none, stamp=0.4, jitter=0.875: storm 0.4, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001219() -> None:
    """failures=none, stamp=0.4, jitter=1.0: storm 0.4, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001220() -> None:
    """failures=none, stamp=0.5, jitter=0.5: storm 0.5, delay 0.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(None, storm, 0.5) == 0.5


def test_c001221() -> None:
    """failures=none, stamp=0.5, jitter=0.625: storm 0.5, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(None, storm, 0.625) == 0.625


def test_c001222() -> None:
    """failures=none, stamp=0.5, jitter=0.75: storm 0.5, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(None, storm, 0.75) == 0.75


def test_c001223() -> None:
    """failures=none, stamp=0.5, jitter=0.875: storm 0.5, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001224() -> None:
    """failures=none, stamp=0.5, jitter=1.0: storm 0.5, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001225() -> None:
    """failures=none, stamp=0.6, jitter=0.5: storm 0.6, delay 0.6."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(None, storm, 0.5) == 0.6


def test_c001226() -> None:
    """failures=none, stamp=0.6, jitter=0.625: storm 0.6, delay 0.625."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(None, storm, 0.625) == 0.625


def test_c001227() -> None:
    """failures=none, stamp=0.6, jitter=0.75: storm 0.6, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(None, storm, 0.75) == 0.75


def test_c001228() -> None:
    """failures=none, stamp=0.6, jitter=0.875: storm 0.6, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001229() -> None:
    """failures=none, stamp=0.6, jitter=1.0: storm 0.6, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001230() -> None:
    """failures=none, stamp=0.7, jitter=0.5: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(None, storm, 0.5) == 0.7


def test_c001231() -> None:
    """failures=none, stamp=0.7, jitter=0.625: storm 0.7, delay 0.7."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(None, storm, 0.625) == 0.7


def test_c001232() -> None:
    """failures=none, stamp=0.7, jitter=0.75: storm 0.7, delay 0.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(None, storm, 0.75) == 0.75


def test_c001233() -> None:
    """failures=none, stamp=0.7, jitter=0.875: storm 0.7, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001234() -> None:
    """failures=none, stamp=0.7, jitter=1.0: storm 0.7, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001235() -> None:
    """failures=none, stamp=0.8, jitter=0.5: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(None, storm, 0.5) == 0.8


def test_c001236() -> None:
    """failures=none, stamp=0.8, jitter=0.625: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(None, storm, 0.625) == 0.8


def test_c001237() -> None:
    """failures=none, stamp=0.8, jitter=0.75: storm 0.8, delay 0.8."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(None, storm, 0.75) == 0.8


def test_c001238() -> None:
    """failures=none, stamp=0.8, jitter=0.875: storm 0.8, delay 0.875."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(None, storm, 0.875) == 0.875


def test_c001239() -> None:
    """failures=none, stamp=0.8, jitter=1.0: storm 0.8, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001240() -> None:
    """failures=none, stamp=0.9, jitter=0.5: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(None, storm, 0.5) == 0.9


def test_c001241() -> None:
    """failures=none, stamp=0.9, jitter=0.625: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(None, storm, 0.625) == 0.9


def test_c001242() -> None:
    """failures=none, stamp=0.9, jitter=0.75: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(None, storm, 0.75) == 0.9


def test_c001243() -> None:
    """failures=none, stamp=0.9, jitter=0.875: storm 0.9, delay 0.9."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(None, storm, 0.875) == 0.9


def test_c001244() -> None:
    """failures=none, stamp=0.9, jitter=1.0: storm 0.9, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001245() -> None:
    """failures=none, stamp=1.0, jitter=0.5: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(None, storm, 0.5) == 1.0


def test_c001246() -> None:
    """failures=none, stamp=1.0, jitter=0.625: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(None, storm, 0.625) == 1.0


def test_c001247() -> None:
    """failures=none, stamp=1.0, jitter=0.75: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(None, storm, 0.75) == 1.0


def test_c001248() -> None:
    """failures=none, stamp=1.0, jitter=0.875: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(None, storm, 0.875) == 1.0


def test_c001249() -> None:
    """failures=none, stamp=1.0, jitter=1.0: storm 1.0, delay 1.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(None, storm, 1.0) == 1.0


def test_c001250() -> None:
    """failures=none, stamp=1.1, jitter=0.5: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(None, storm, 0.5) == 1.1


def test_c001251() -> None:
    """failures=none, stamp=1.1, jitter=0.625: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(None, storm, 0.625) == 1.1


def test_c001252() -> None:
    """failures=none, stamp=1.1, jitter=0.75: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(None, storm, 0.75) == 1.1


def test_c001253() -> None:
    """failures=none, stamp=1.1, jitter=0.875: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(None, storm, 0.875) == 1.1


def test_c001254() -> None:
    """failures=none, stamp=1.1, jitter=1.0: storm 1.1, delay 1.1."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(None, storm, 1.0) == 1.1


def test_c001255() -> None:
    """failures=none, stamp=1.2, jitter=0.5: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(None, storm, 0.5) == 1.2


def test_c001256() -> None:
    """failures=none, stamp=1.2, jitter=0.625: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(None, storm, 0.625) == 1.2


def test_c001257() -> None:
    """failures=none, stamp=1.2, jitter=0.75: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(None, storm, 0.75) == 1.2


def test_c001258() -> None:
    """failures=none, stamp=1.2, jitter=0.875: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(None, storm, 0.875) == 1.2


def test_c001259() -> None:
    """failures=none, stamp=1.2, jitter=1.0: storm 1.2, delay 1.2."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(None, storm, 1.0) == 1.2


def test_c001260() -> None:
    """failures=none, stamp=1.3, jitter=0.5: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(None, storm, 0.5) == 1.3


def test_c001261() -> None:
    """failures=none, stamp=1.3, jitter=0.625: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(None, storm, 0.625) == 1.3


def test_c001262() -> None:
    """failures=none, stamp=1.3, jitter=0.75: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(None, storm, 0.75) == 1.3


def test_c001263() -> None:
    """failures=none, stamp=1.3, jitter=0.875: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(None, storm, 0.875) == 1.3


def test_c001264() -> None:
    """failures=none, stamp=1.3, jitter=1.0: storm 1.3, delay 1.3."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(None, storm, 1.0) == 1.3


def test_c001265() -> None:
    """failures=none, stamp=1.4, jitter=0.5: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(None, storm, 0.5) == 1.4


def test_c001266() -> None:
    """failures=none, stamp=1.4, jitter=0.625: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(None, storm, 0.625) == 1.4


def test_c001267() -> None:
    """failures=none, stamp=1.4, jitter=0.75: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(None, storm, 0.75) == 1.4


def test_c001268() -> None:
    """failures=none, stamp=1.4, jitter=0.875: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(None, storm, 0.875) == 1.4


def test_c001269() -> None:
    """failures=none, stamp=1.4, jitter=1.0: storm 1.4, delay 1.4."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(None, storm, 1.0) == 1.4


def test_c001270() -> None:
    """failures=none, stamp=1.5, jitter=0.5: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(None, storm, 0.5) == 1.5


def test_c001271() -> None:
    """failures=none, stamp=1.5, jitter=0.625: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(None, storm, 0.625) == 1.5


def test_c001272() -> None:
    """failures=none, stamp=1.5, jitter=0.75: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(None, storm, 0.75) == 1.5


def test_c001273() -> None:
    """failures=none, stamp=1.5, jitter=0.875: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(None, storm, 0.875) == 1.5


def test_c001274() -> None:
    """failures=none, stamp=1.5, jitter=1.0: storm 1.5, delay 1.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(None, storm, 1.0) == 1.5


def test_c001275() -> None:
    """failures=none, stamp=1.6, jitter=0.5: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(None, storm, 0.5) == 1.6


def test_c001276() -> None:
    """failures=none, stamp=1.6, jitter=0.625: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(None, storm, 0.625) == 1.6


def test_c001277() -> None:
    """failures=none, stamp=1.6, jitter=0.75: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(None, storm, 0.75) == 1.6


def test_c001278() -> None:
    """failures=none, stamp=1.6, jitter=0.875: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(None, storm, 0.875) == 1.6


def test_c001279() -> None:
    """failures=none, stamp=1.6, jitter=1.0: storm 1.6, delay 1.6."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(None, storm, 1.0) == 1.6


def test_c001280() -> None:
    """failures=none, stamp=1.7, jitter=0.5: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(None, storm, 0.5) == 1.7


def test_c001281() -> None:
    """failures=none, stamp=1.7, jitter=0.625: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(None, storm, 0.625) == 1.7


def test_c001282() -> None:
    """failures=none, stamp=1.7, jitter=0.75: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(None, storm, 0.75) == 1.7


def test_c001283() -> None:
    """failures=none, stamp=1.7, jitter=0.875: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(None, storm, 0.875) == 1.7


def test_c001284() -> None:
    """failures=none, stamp=1.7, jitter=1.0: storm 1.7, delay 1.7."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(None, storm, 1.0) == 1.7


def test_c001285() -> None:
    """failures=none, stamp=1.8, jitter=0.5: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(None, storm, 0.5) == 1.8


def test_c001286() -> None:
    """failures=none, stamp=1.8, jitter=0.625: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(None, storm, 0.625) == 1.8


def test_c001287() -> None:
    """failures=none, stamp=1.8, jitter=0.75: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(None, storm, 0.75) == 1.8


def test_c001288() -> None:
    """failures=none, stamp=1.8, jitter=0.875: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(None, storm, 0.875) == 1.8


def test_c001289() -> None:
    """failures=none, stamp=1.8, jitter=1.0: storm 1.8, delay 1.8."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(None, storm, 1.0) == 1.8


def test_c001290() -> None:
    """failures=none, stamp=1.9, jitter=0.5: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(None, storm, 0.5) == 1.9


def test_c001291() -> None:
    """failures=none, stamp=1.9, jitter=0.625: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(None, storm, 0.625) == 1.9


def test_c001292() -> None:
    """failures=none, stamp=1.9, jitter=0.75: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(None, storm, 0.75) == 1.9


def test_c001293() -> None:
    """failures=none, stamp=1.9, jitter=0.875: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(None, storm, 0.875) == 1.9


def test_c001294() -> None:
    """failures=none, stamp=1.9, jitter=1.0: storm 1.9, delay 1.9."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(None, storm, 1.0) == 1.9


def test_c001295() -> None:
    """failures=none, stamp=2.0, jitter=0.5: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(None, storm, 0.5) == 2.0


def test_c001296() -> None:
    """failures=none, stamp=2.0, jitter=0.625: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(None, storm, 0.625) == 2.0


def test_c001297() -> None:
    """failures=none, stamp=2.0, jitter=0.75: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(None, storm, 0.75) == 2.0


def test_c001298() -> None:
    """failures=none, stamp=2.0, jitter=0.875: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(None, storm, 0.875) == 2.0


def test_c001299() -> None:
    """failures=none, stamp=2.0, jitter=1.0: storm 2.0, delay 2.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(None, storm, 1.0) == 2.0


def test_c001300() -> None:
    """failures=none, stamp=2.1, jitter=0.5: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(None, storm, 0.5) == 2.1


def test_c001301() -> None:
    """failures=none, stamp=2.1, jitter=0.625: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(None, storm, 0.625) == 2.1


def test_c001302() -> None:
    """failures=none, stamp=2.1, jitter=0.75: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(None, storm, 0.75) == 2.1


def test_c001303() -> None:
    """failures=none, stamp=2.1, jitter=0.875: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(None, storm, 0.875) == 2.1


def test_c001304() -> None:
    """failures=none, stamp=2.1, jitter=1.0: storm 2.1, delay 2.1."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(None, storm, 1.0) == 2.1


def test_c001305() -> None:
    """failures=none, stamp=2.2, jitter=0.5: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(None, storm, 0.5) == 2.2


def test_c001306() -> None:
    """failures=none, stamp=2.2, jitter=0.625: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(None, storm, 0.625) == 2.2


def test_c001307() -> None:
    """failures=none, stamp=2.2, jitter=0.75: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(None, storm, 0.75) == 2.2


def test_c001308() -> None:
    """failures=none, stamp=2.2, jitter=0.875: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(None, storm, 0.875) == 2.2


def test_c001309() -> None:
    """failures=none, stamp=2.2, jitter=1.0: storm 2.2, delay 2.2."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(None, storm, 1.0) == 2.2


def test_c001310() -> None:
    """failures=none, stamp=2.3, jitter=0.5: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(None, storm, 0.5) == 2.3


def test_c001311() -> None:
    """failures=none, stamp=2.3, jitter=0.625: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(None, storm, 0.625) == 2.3


def test_c001312() -> None:
    """failures=none, stamp=2.3, jitter=0.75: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(None, storm, 0.75) == 2.3


def test_c001313() -> None:
    """failures=none, stamp=2.3, jitter=0.875: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(None, storm, 0.875) == 2.3


def test_c001314() -> None:
    """failures=none, stamp=2.3, jitter=1.0: storm 2.3, delay 2.3."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(None, storm, 1.0) == 2.3


def test_c001315() -> None:
    """failures=none, stamp=2.4, jitter=0.5: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(None, storm, 0.5) == 2.4


def test_c001316() -> None:
    """failures=none, stamp=2.4, jitter=0.625: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(None, storm, 0.625) == 2.4


def test_c001317() -> None:
    """failures=none, stamp=2.4, jitter=0.75: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(None, storm, 0.75) == 2.4


def test_c001318() -> None:
    """failures=none, stamp=2.4, jitter=0.875: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(None, storm, 0.875) == 2.4


def test_c001319() -> None:
    """failures=none, stamp=2.4, jitter=1.0: storm 2.4, delay 2.4."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(None, storm, 1.0) == 2.4


def test_c001320() -> None:
    """failures=none, stamp=2.5, jitter=0.5: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(None, storm, 0.5) == 2.5


def test_c001321() -> None:
    """failures=none, stamp=2.5, jitter=0.625: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(None, storm, 0.625) == 2.5


def test_c001322() -> None:
    """failures=none, stamp=2.5, jitter=0.75: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(None, storm, 0.75) == 2.5


def test_c001323() -> None:
    """failures=none, stamp=2.5, jitter=0.875: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(None, storm, 0.875) == 2.5


def test_c001324() -> None:
    """failures=none, stamp=2.5, jitter=1.0: storm 2.5, delay 2.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(None, storm, 1.0) == 2.5


def test_c001325() -> None:
    """failures=none, stamp=2.6, jitter=0.5: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(None, storm, 0.5) == 2.6


def test_c001326() -> None:
    """failures=none, stamp=2.6, jitter=0.625: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(None, storm, 0.625) == 2.6


def test_c001327() -> None:
    """failures=none, stamp=2.6, jitter=0.75: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(None, storm, 0.75) == 2.6


def test_c001328() -> None:
    """failures=none, stamp=2.6, jitter=0.875: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(None, storm, 0.875) == 2.6


def test_c001329() -> None:
    """failures=none, stamp=2.6, jitter=1.0: storm 2.6, delay 2.6."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(None, storm, 1.0) == 2.6


def test_c001330() -> None:
    """failures=none, stamp=2.7, jitter=0.5: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(None, storm, 0.5) == 2.7


def test_c001331() -> None:
    """failures=none, stamp=2.7, jitter=0.625: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(None, storm, 0.625) == 2.7


def test_c001332() -> None:
    """failures=none, stamp=2.7, jitter=0.75: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(None, storm, 0.75) == 2.7


def test_c001333() -> None:
    """failures=none, stamp=2.7, jitter=0.875: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(None, storm, 0.875) == 2.7


def test_c001334() -> None:
    """failures=none, stamp=2.7, jitter=1.0: storm 2.7, delay 2.7."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(None, storm, 1.0) == 2.7


def test_c001335() -> None:
    """failures=none, stamp=2.8, jitter=0.5: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(None, storm, 0.5) == 2.8


def test_c001336() -> None:
    """failures=none, stamp=2.8, jitter=0.625: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(None, storm, 0.625) == 2.8


def test_c001337() -> None:
    """failures=none, stamp=2.8, jitter=0.75: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(None, storm, 0.75) == 2.8


def test_c001338() -> None:
    """failures=none, stamp=2.8, jitter=0.875: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(None, storm, 0.875) == 2.8


def test_c001339() -> None:
    """failures=none, stamp=2.8, jitter=1.0: storm 2.8, delay 2.8."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(None, storm, 1.0) == 2.8


def test_c001340() -> None:
    """failures=none, stamp=2.9, jitter=0.5: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(None, storm, 0.5) == 2.9


def test_c001341() -> None:
    """failures=none, stamp=2.9, jitter=0.625: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(None, storm, 0.625) == 2.9


def test_c001342() -> None:
    """failures=none, stamp=2.9, jitter=0.75: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(None, storm, 0.75) == 2.9


def test_c001343() -> None:
    """failures=none, stamp=2.9, jitter=0.875: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(None, storm, 0.875) == 2.9


def test_c001344() -> None:
    """failures=none, stamp=2.9, jitter=1.0: storm 2.9, delay 2.9."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(None, storm, 1.0) == 2.9


def test_c001345() -> None:
    """failures=none, stamp=3.0, jitter=0.5: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(None, storm, 0.5) == 3.0


def test_c001346() -> None:
    """failures=none, stamp=3.0, jitter=0.625: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(None, storm, 0.625) == 3.0


def test_c001347() -> None:
    """failures=none, stamp=3.0, jitter=0.75: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(None, storm, 0.75) == 3.0


def test_c001348() -> None:
    """failures=none, stamp=3.0, jitter=0.875: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(None, storm, 0.875) == 3.0


def test_c001349() -> None:
    """failures=none, stamp=3.0, jitter=1.0: storm 3.0, delay 3.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(None, storm, 1.0) == 3.0


def test_c001350() -> None:
    """failures=none, stamp=3.1, jitter=0.5: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(None, storm, 0.5) == 3.1


def test_c001351() -> None:
    """failures=none, stamp=3.1, jitter=0.625: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(None, storm, 0.625) == 3.1


def test_c001352() -> None:
    """failures=none, stamp=3.1, jitter=0.75: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(None, storm, 0.75) == 3.1


def test_c001353() -> None:
    """failures=none, stamp=3.1, jitter=0.875: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(None, storm, 0.875) == 3.1


def test_c001354() -> None:
    """failures=none, stamp=3.1, jitter=1.0: storm 3.1, delay 3.1."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(None, storm, 1.0) == 3.1


def test_c001355() -> None:
    """failures=none, stamp=3.2, jitter=0.5: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(None, storm, 0.5) == 3.2


def test_c001356() -> None:
    """failures=none, stamp=3.2, jitter=0.625: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(None, storm, 0.625) == 3.2


def test_c001357() -> None:
    """failures=none, stamp=3.2, jitter=0.75: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(None, storm, 0.75) == 3.2


def test_c001358() -> None:
    """failures=none, stamp=3.2, jitter=0.875: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(None, storm, 0.875) == 3.2


def test_c001359() -> None:
    """failures=none, stamp=3.2, jitter=1.0: storm 3.2, delay 3.2."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(None, storm, 1.0) == 3.2


def test_c001360() -> None:
    """failures=none, stamp=3.3, jitter=0.5: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(None, storm, 0.5) == 3.3


def test_c001361() -> None:
    """failures=none, stamp=3.3, jitter=0.625: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(None, storm, 0.625) == 3.3


def test_c001362() -> None:
    """failures=none, stamp=3.3, jitter=0.75: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(None, storm, 0.75) == 3.3


def test_c001363() -> None:
    """failures=none, stamp=3.3, jitter=0.875: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(None, storm, 0.875) == 3.3


def test_c001364() -> None:
    """failures=none, stamp=3.3, jitter=1.0: storm 3.3, delay 3.3."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(None, storm, 1.0) == 3.3


def test_c001365() -> None:
    """failures=none, stamp=3.4, jitter=0.5: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(None, storm, 0.5) == 3.4


def test_c001366() -> None:
    """failures=none, stamp=3.4, jitter=0.625: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(None, storm, 0.625) == 3.4


def test_c001367() -> None:
    """failures=none, stamp=3.4, jitter=0.75: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(None, storm, 0.75) == 3.4


def test_c001368() -> None:
    """failures=none, stamp=3.4, jitter=0.875: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(None, storm, 0.875) == 3.4


def test_c001369() -> None:
    """failures=none, stamp=3.4, jitter=1.0: storm 3.4, delay 3.4."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(None, storm, 1.0) == 3.4


def test_c001370() -> None:
    """failures=none, stamp=3.5, jitter=0.5: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(None, storm, 0.5) == 3.5


def test_c001371() -> None:
    """failures=none, stamp=3.5, jitter=0.625: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(None, storm, 0.625) == 3.5


def test_c001372() -> None:
    """failures=none, stamp=3.5, jitter=0.75: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(None, storm, 0.75) == 3.5


def test_c001373() -> None:
    """failures=none, stamp=3.5, jitter=0.875: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(None, storm, 0.875) == 3.5


def test_c001374() -> None:
    """failures=none, stamp=3.5, jitter=1.0: storm 3.5, delay 3.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(None, storm, 1.0) == 3.5


def test_c001375() -> None:
    """failures=none, stamp=3.6, jitter=0.5: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(None, storm, 0.5) == 3.6


def test_c001376() -> None:
    """failures=none, stamp=3.6, jitter=0.625: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(None, storm, 0.625) == 3.6


def test_c001377() -> None:
    """failures=none, stamp=3.6, jitter=0.75: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(None, storm, 0.75) == 3.6


def test_c001378() -> None:
    """failures=none, stamp=3.6, jitter=0.875: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(None, storm, 0.875) == 3.6


def test_c001379() -> None:
    """failures=none, stamp=3.6, jitter=1.0: storm 3.6, delay 3.6."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(None, storm, 1.0) == 3.6


def test_c001380() -> None:
    """failures=none, stamp=3.7, jitter=0.5: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(None, storm, 0.5) == 3.7


def test_c001381() -> None:
    """failures=none, stamp=3.7, jitter=0.625: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(None, storm, 0.625) == 3.7


def test_c001382() -> None:
    """failures=none, stamp=3.7, jitter=0.75: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(None, storm, 0.75) == 3.7


def test_c001383() -> None:
    """failures=none, stamp=3.7, jitter=0.875: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(None, storm, 0.875) == 3.7


def test_c001384() -> None:
    """failures=none, stamp=3.7, jitter=1.0: storm 3.7, delay 3.7."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(None, storm, 1.0) == 3.7


def test_c001385() -> None:
    """failures=none, stamp=3.8, jitter=0.5: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(None, storm, 0.5) == 3.8


def test_c001386() -> None:
    """failures=none, stamp=3.8, jitter=0.625: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(None, storm, 0.625) == 3.8


def test_c001387() -> None:
    """failures=none, stamp=3.8, jitter=0.75: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(None, storm, 0.75) == 3.8


def test_c001388() -> None:
    """failures=none, stamp=3.8, jitter=0.875: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(None, storm, 0.875) == 3.8


def test_c001389() -> None:
    """failures=none, stamp=3.8, jitter=1.0: storm 3.8, delay 3.8."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(None, storm, 1.0) == 3.8


def test_c001390() -> None:
    """failures=none, stamp=3.9, jitter=0.5: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(None, storm, 0.5) == 3.9


def test_c001391() -> None:
    """failures=none, stamp=3.9, jitter=0.625: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(None, storm, 0.625) == 3.9


def test_c001392() -> None:
    """failures=none, stamp=3.9, jitter=0.75: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(None, storm, 0.75) == 3.9


def test_c001393() -> None:
    """failures=none, stamp=3.9, jitter=0.875: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(None, storm, 0.875) == 3.9


def test_c001394() -> None:
    """failures=none, stamp=3.9, jitter=1.0: storm 3.9, delay 3.9."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(None, storm, 1.0) == 3.9


def test_c001395() -> None:
    """failures=none, stamp=4.0, jitter=0.5: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(None, storm, 0.5) == 4.0


def test_c001396() -> None:
    """failures=none, stamp=4.0, jitter=0.625: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(None, storm, 0.625) == 4.0


def test_c001397() -> None:
    """failures=none, stamp=4.0, jitter=0.75: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(None, storm, 0.75) == 4.0


def test_c001398() -> None:
    """failures=none, stamp=4.0, jitter=0.875: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(None, storm, 0.875) == 4.0


def test_c001399() -> None:
    """failures=none, stamp=4.0, jitter=1.0: storm 4.0, delay 4.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(None, storm, 1.0) == 4.0


def test_c001400() -> None:
    """failures=bigfloat, stamp=0.1, jitter=0.5: storm 0.1, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001401() -> None:
    """failures=bigfloat, stamp=0.1, jitter=0.625: storm 0.1, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001402() -> None:
    """failures=bigfloat, stamp=0.1, jitter=0.75: storm 0.1, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001403() -> None:
    """failures=bigfloat, stamp=0.1, jitter=0.875: storm 0.1, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001404() -> None:
    """failures=bigfloat, stamp=0.1, jitter=1.0: storm 0.1, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.1))
    assert storm == 0.1
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001405() -> None:
    """failures=bigfloat, stamp=0.2, jitter=0.5: storm 0.2, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001406() -> None:
    """failures=bigfloat, stamp=0.2, jitter=0.625: storm 0.2, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001407() -> None:
    """failures=bigfloat, stamp=0.2, jitter=0.75: storm 0.2, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001408() -> None:
    """failures=bigfloat, stamp=0.2, jitter=0.875: storm 0.2, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001409() -> None:
    """failures=bigfloat, stamp=0.2, jitter=1.0: storm 0.2, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.2))
    assert storm == 0.2
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001410() -> None:
    """failures=bigfloat, stamp=0.3, jitter=0.5: storm 0.3, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001411() -> None:
    """failures=bigfloat, stamp=0.3, jitter=0.625: storm 0.3, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001412() -> None:
    """failures=bigfloat, stamp=0.3, jitter=0.75: storm 0.3, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001413() -> None:
    """failures=bigfloat, stamp=0.3, jitter=0.875: storm 0.3, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001414() -> None:
    """failures=bigfloat, stamp=0.3, jitter=1.0: storm 0.3, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.3))
    assert storm == 0.3
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001415() -> None:
    """failures=bigfloat, stamp=0.4, jitter=0.5: storm 0.4, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001416() -> None:
    """failures=bigfloat, stamp=0.4, jitter=0.625: storm 0.4, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001417() -> None:
    """failures=bigfloat, stamp=0.4, jitter=0.75: storm 0.4, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001418() -> None:
    """failures=bigfloat, stamp=0.4, jitter=0.875: storm 0.4, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001419() -> None:
    """failures=bigfloat, stamp=0.4, jitter=1.0: storm 0.4, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.4))
    assert storm == 0.4
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001420() -> None:
    """failures=bigfloat, stamp=0.5, jitter=0.5: storm 0.5, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001421() -> None:
    """failures=bigfloat, stamp=0.5, jitter=0.625: storm 0.5, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001422() -> None:
    """failures=bigfloat, stamp=0.5, jitter=0.75: storm 0.5, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001423() -> None:
    """failures=bigfloat, stamp=0.5, jitter=0.875: storm 0.5, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001424() -> None:
    """failures=bigfloat, stamp=0.5, jitter=1.0: storm 0.5, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.5))
    assert storm == 0.5
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001425() -> None:
    """failures=bigfloat, stamp=0.6, jitter=0.5: storm 0.6, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001426() -> None:
    """failures=bigfloat, stamp=0.6, jitter=0.625: storm 0.6, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001427() -> None:
    """failures=bigfloat, stamp=0.6, jitter=0.75: storm 0.6, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001428() -> None:
    """failures=bigfloat, stamp=0.6, jitter=0.875: storm 0.6, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001429() -> None:
    """failures=bigfloat, stamp=0.6, jitter=1.0: storm 0.6, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.6))
    assert storm == 0.6
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001430() -> None:
    """failures=bigfloat, stamp=0.7, jitter=0.5: storm 0.7, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001431() -> None:
    """failures=bigfloat, stamp=0.7, jitter=0.625: storm 0.7, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001432() -> None:
    """failures=bigfloat, stamp=0.7, jitter=0.75: storm 0.7, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001433() -> None:
    """failures=bigfloat, stamp=0.7, jitter=0.875: storm 0.7, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001434() -> None:
    """failures=bigfloat, stamp=0.7, jitter=1.0: storm 0.7, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.7))
    assert storm == 0.7
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001435() -> None:
    """failures=bigfloat, stamp=0.8, jitter=0.5: storm 0.8, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001436() -> None:
    """failures=bigfloat, stamp=0.8, jitter=0.625: storm 0.8, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001437() -> None:
    """failures=bigfloat, stamp=0.8, jitter=0.75: storm 0.8, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001438() -> None:
    """failures=bigfloat, stamp=0.8, jitter=0.875: storm 0.8, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001439() -> None:
    """failures=bigfloat, stamp=0.8, jitter=1.0: storm 0.8, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.8))
    assert storm == 0.8
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001440() -> None:
    """failures=bigfloat, stamp=0.9, jitter=0.5: storm 0.9, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001441() -> None:
    """failures=bigfloat, stamp=0.9, jitter=0.625: storm 0.9, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001442() -> None:
    """failures=bigfloat, stamp=0.9, jitter=0.75: storm 0.9, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001443() -> None:
    """failures=bigfloat, stamp=0.9, jitter=0.875: storm 0.9, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001444() -> None:
    """failures=bigfloat, stamp=0.9, jitter=1.0: storm 0.9, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(0.9))
    assert storm == 0.9
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001445() -> None:
    """failures=bigfloat, stamp=1.0, jitter=0.5: storm 1.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001446() -> None:
    """failures=bigfloat, stamp=1.0, jitter=0.625: storm 1.0, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001447() -> None:
    """failures=bigfloat, stamp=1.0, jitter=0.75: storm 1.0, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001448() -> None:
    """failures=bigfloat, stamp=1.0, jitter=0.875: storm 1.0, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001449() -> None:
    """failures=bigfloat, stamp=1.0, jitter=1.0: storm 1.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.0))
    assert storm == 1.0
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001450() -> None:
    """failures=bigfloat, stamp=1.1, jitter=0.5: storm 1.1, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001451() -> None:
    """failures=bigfloat, stamp=1.1, jitter=0.625: storm 1.1, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001452() -> None:
    """failures=bigfloat, stamp=1.1, jitter=0.75: storm 1.1, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001453() -> None:
    """failures=bigfloat, stamp=1.1, jitter=0.875: storm 1.1, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001454() -> None:
    """failures=bigfloat, stamp=1.1, jitter=1.0: storm 1.1, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.1))
    assert storm == 1.1
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001455() -> None:
    """failures=bigfloat, stamp=1.2, jitter=0.5: storm 1.2, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001456() -> None:
    """failures=bigfloat, stamp=1.2, jitter=0.625: storm 1.2, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001457() -> None:
    """failures=bigfloat, stamp=1.2, jitter=0.75: storm 1.2, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001458() -> None:
    """failures=bigfloat, stamp=1.2, jitter=0.875: storm 1.2, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001459() -> None:
    """failures=bigfloat, stamp=1.2, jitter=1.0: storm 1.2, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.2))
    assert storm == 1.2
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001460() -> None:
    """failures=bigfloat, stamp=1.3, jitter=0.5: storm 1.3, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001461() -> None:
    """failures=bigfloat, stamp=1.3, jitter=0.625: storm 1.3, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001462() -> None:
    """failures=bigfloat, stamp=1.3, jitter=0.75: storm 1.3, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001463() -> None:
    """failures=bigfloat, stamp=1.3, jitter=0.875: storm 1.3, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001464() -> None:
    """failures=bigfloat, stamp=1.3, jitter=1.0: storm 1.3, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.3))
    assert storm == 1.3
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001465() -> None:
    """failures=bigfloat, stamp=1.4, jitter=0.5: storm 1.4, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001466() -> None:
    """failures=bigfloat, stamp=1.4, jitter=0.625: storm 1.4, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001467() -> None:
    """failures=bigfloat, stamp=1.4, jitter=0.75: storm 1.4, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001468() -> None:
    """failures=bigfloat, stamp=1.4, jitter=0.875: storm 1.4, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001469() -> None:
    """failures=bigfloat, stamp=1.4, jitter=1.0: storm 1.4, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.4))
    assert storm == 1.4
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001470() -> None:
    """failures=bigfloat, stamp=1.5, jitter=0.5: storm 1.5, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001471() -> None:
    """failures=bigfloat, stamp=1.5, jitter=0.625: storm 1.5, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001472() -> None:
    """failures=bigfloat, stamp=1.5, jitter=0.75: storm 1.5, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001473() -> None:
    """failures=bigfloat, stamp=1.5, jitter=0.875: storm 1.5, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001474() -> None:
    """failures=bigfloat, stamp=1.5, jitter=1.0: storm 1.5, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.5))
    assert storm == 1.5
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001475() -> None:
    """failures=bigfloat, stamp=1.6, jitter=0.5: storm 1.6, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001476() -> None:
    """failures=bigfloat, stamp=1.6, jitter=0.625: storm 1.6, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001477() -> None:
    """failures=bigfloat, stamp=1.6, jitter=0.75: storm 1.6, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001478() -> None:
    """failures=bigfloat, stamp=1.6, jitter=0.875: storm 1.6, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001479() -> None:
    """failures=bigfloat, stamp=1.6, jitter=1.0: storm 1.6, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.6))
    assert storm == 1.6
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001480() -> None:
    """failures=bigfloat, stamp=1.7, jitter=0.5: storm 1.7, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001481() -> None:
    """failures=bigfloat, stamp=1.7, jitter=0.625: storm 1.7, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001482() -> None:
    """failures=bigfloat, stamp=1.7, jitter=0.75: storm 1.7, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001483() -> None:
    """failures=bigfloat, stamp=1.7, jitter=0.875: storm 1.7, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001484() -> None:
    """failures=bigfloat, stamp=1.7, jitter=1.0: storm 1.7, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.7))
    assert storm == 1.7
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001485() -> None:
    """failures=bigfloat, stamp=1.8, jitter=0.5: storm 1.8, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001486() -> None:
    """failures=bigfloat, stamp=1.8, jitter=0.625: storm 1.8, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001487() -> None:
    """failures=bigfloat, stamp=1.8, jitter=0.75: storm 1.8, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001488() -> None:
    """failures=bigfloat, stamp=1.8, jitter=0.875: storm 1.8, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001489() -> None:
    """failures=bigfloat, stamp=1.8, jitter=1.0: storm 1.8, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.8))
    assert storm == 1.8
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001490() -> None:
    """failures=bigfloat, stamp=1.9, jitter=0.5: storm 1.9, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001491() -> None:
    """failures=bigfloat, stamp=1.9, jitter=0.625: storm 1.9, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001492() -> None:
    """failures=bigfloat, stamp=1.9, jitter=0.75: storm 1.9, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001493() -> None:
    """failures=bigfloat, stamp=1.9, jitter=0.875: storm 1.9, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001494() -> None:
    """failures=bigfloat, stamp=1.9, jitter=1.0: storm 1.9, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(1.9))
    assert storm == 1.9
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001495() -> None:
    """failures=bigfloat, stamp=2.0, jitter=0.5: storm 2.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001496() -> None:
    """failures=bigfloat, stamp=2.0, jitter=0.625: storm 2.0, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001497() -> None:
    """failures=bigfloat, stamp=2.0, jitter=0.75: storm 2.0, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001498() -> None:
    """failures=bigfloat, stamp=2.0, jitter=0.875: storm 2.0, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001499() -> None:
    """failures=bigfloat, stamp=2.0, jitter=1.0: storm 2.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.0))
    assert storm == 2.0
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001500() -> None:
    """failures=bigfloat, stamp=2.1, jitter=0.5: storm 2.1, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001501() -> None:
    """failures=bigfloat, stamp=2.1, jitter=0.625: storm 2.1, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001502() -> None:
    """failures=bigfloat, stamp=2.1, jitter=0.75: storm 2.1, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001503() -> None:
    """failures=bigfloat, stamp=2.1, jitter=0.875: storm 2.1, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001504() -> None:
    """failures=bigfloat, stamp=2.1, jitter=1.0: storm 2.1, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.1))
    assert storm == 2.1
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001505() -> None:
    """failures=bigfloat, stamp=2.2, jitter=0.5: storm 2.2, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001506() -> None:
    """failures=bigfloat, stamp=2.2, jitter=0.625: storm 2.2, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001507() -> None:
    """failures=bigfloat, stamp=2.2, jitter=0.75: storm 2.2, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001508() -> None:
    """failures=bigfloat, stamp=2.2, jitter=0.875: storm 2.2, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001509() -> None:
    """failures=bigfloat, stamp=2.2, jitter=1.0: storm 2.2, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.2))
    assert storm == 2.2
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001510() -> None:
    """failures=bigfloat, stamp=2.3, jitter=0.5: storm 2.3, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001511() -> None:
    """failures=bigfloat, stamp=2.3, jitter=0.625: storm 2.3, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001512() -> None:
    """failures=bigfloat, stamp=2.3, jitter=0.75: storm 2.3, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001513() -> None:
    """failures=bigfloat, stamp=2.3, jitter=0.875: storm 2.3, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001514() -> None:
    """failures=bigfloat, stamp=2.3, jitter=1.0: storm 2.3, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.3))
    assert storm == 2.3
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001515() -> None:
    """failures=bigfloat, stamp=2.4, jitter=0.5: storm 2.4, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001516() -> None:
    """failures=bigfloat, stamp=2.4, jitter=0.625: storm 2.4, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001517() -> None:
    """failures=bigfloat, stamp=2.4, jitter=0.75: storm 2.4, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001518() -> None:
    """failures=bigfloat, stamp=2.4, jitter=0.875: storm 2.4, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001519() -> None:
    """failures=bigfloat, stamp=2.4, jitter=1.0: storm 2.4, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.4))
    assert storm == 2.4
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001520() -> None:
    """failures=bigfloat, stamp=2.5, jitter=0.5: storm 2.5, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001521() -> None:
    """failures=bigfloat, stamp=2.5, jitter=0.625: storm 2.5, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001522() -> None:
    """failures=bigfloat, stamp=2.5, jitter=0.75: storm 2.5, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001523() -> None:
    """failures=bigfloat, stamp=2.5, jitter=0.875: storm 2.5, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001524() -> None:
    """failures=bigfloat, stamp=2.5, jitter=1.0: storm 2.5, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.5))
    assert storm == 2.5
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001525() -> None:
    """failures=bigfloat, stamp=2.6, jitter=0.5: storm 2.6, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001526() -> None:
    """failures=bigfloat, stamp=2.6, jitter=0.625: storm 2.6, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001527() -> None:
    """failures=bigfloat, stamp=2.6, jitter=0.75: storm 2.6, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001528() -> None:
    """failures=bigfloat, stamp=2.6, jitter=0.875: storm 2.6, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001529() -> None:
    """failures=bigfloat, stamp=2.6, jitter=1.0: storm 2.6, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.6))
    assert storm == 2.6
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001530() -> None:
    """failures=bigfloat, stamp=2.7, jitter=0.5: storm 2.7, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001531() -> None:
    """failures=bigfloat, stamp=2.7, jitter=0.625: storm 2.7, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001532() -> None:
    """failures=bigfloat, stamp=2.7, jitter=0.75: storm 2.7, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001533() -> None:
    """failures=bigfloat, stamp=2.7, jitter=0.875: storm 2.7, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001534() -> None:
    """failures=bigfloat, stamp=2.7, jitter=1.0: storm 2.7, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.7))
    assert storm == 2.7
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001535() -> None:
    """failures=bigfloat, stamp=2.8, jitter=0.5: storm 2.8, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001536() -> None:
    """failures=bigfloat, stamp=2.8, jitter=0.625: storm 2.8, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001537() -> None:
    """failures=bigfloat, stamp=2.8, jitter=0.75: storm 2.8, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001538() -> None:
    """failures=bigfloat, stamp=2.8, jitter=0.875: storm 2.8, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001539() -> None:
    """failures=bigfloat, stamp=2.8, jitter=1.0: storm 2.8, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.8))
    assert storm == 2.8
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001540() -> None:
    """failures=bigfloat, stamp=2.9, jitter=0.5: storm 2.9, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001541() -> None:
    """failures=bigfloat, stamp=2.9, jitter=0.625: storm 2.9, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001542() -> None:
    """failures=bigfloat, stamp=2.9, jitter=0.75: storm 2.9, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001543() -> None:
    """failures=bigfloat, stamp=2.9, jitter=0.875: storm 2.9, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001544() -> None:
    """failures=bigfloat, stamp=2.9, jitter=1.0: storm 2.9, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(2.9))
    assert storm == 2.9
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001545() -> None:
    """failures=bigfloat, stamp=3.0, jitter=0.5: storm 3.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001546() -> None:
    """failures=bigfloat, stamp=3.0, jitter=0.625: storm 3.0, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001547() -> None:
    """failures=bigfloat, stamp=3.0, jitter=0.75: storm 3.0, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001548() -> None:
    """failures=bigfloat, stamp=3.0, jitter=0.875: storm 3.0, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001549() -> None:
    """failures=bigfloat, stamp=3.0, jitter=1.0: storm 3.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.0))
    assert storm == 3.0
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001550() -> None:
    """failures=bigfloat, stamp=3.1, jitter=0.5: storm 3.1, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001551() -> None:
    """failures=bigfloat, stamp=3.1, jitter=0.625: storm 3.1, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001552() -> None:
    """failures=bigfloat, stamp=3.1, jitter=0.75: storm 3.1, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001553() -> None:
    """failures=bigfloat, stamp=3.1, jitter=0.875: storm 3.1, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001554() -> None:
    """failures=bigfloat, stamp=3.1, jitter=1.0: storm 3.1, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.1))
    assert storm == 3.1
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001555() -> None:
    """failures=bigfloat, stamp=3.2, jitter=0.5: storm 3.2, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001556() -> None:
    """failures=bigfloat, stamp=3.2, jitter=0.625: storm 3.2, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001557() -> None:
    """failures=bigfloat, stamp=3.2, jitter=0.75: storm 3.2, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001558() -> None:
    """failures=bigfloat, stamp=3.2, jitter=0.875: storm 3.2, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001559() -> None:
    """failures=bigfloat, stamp=3.2, jitter=1.0: storm 3.2, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.2))
    assert storm == 3.2
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001560() -> None:
    """failures=bigfloat, stamp=3.3, jitter=0.5: storm 3.3, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001561() -> None:
    """failures=bigfloat, stamp=3.3, jitter=0.625: storm 3.3, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001562() -> None:
    """failures=bigfloat, stamp=3.3, jitter=0.75: storm 3.3, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001563() -> None:
    """failures=bigfloat, stamp=3.3, jitter=0.875: storm 3.3, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001564() -> None:
    """failures=bigfloat, stamp=3.3, jitter=1.0: storm 3.3, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.3))
    assert storm == 3.3
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001565() -> None:
    """failures=bigfloat, stamp=3.4, jitter=0.5: storm 3.4, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001566() -> None:
    """failures=bigfloat, stamp=3.4, jitter=0.625: storm 3.4, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001567() -> None:
    """failures=bigfloat, stamp=3.4, jitter=0.75: storm 3.4, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001568() -> None:
    """failures=bigfloat, stamp=3.4, jitter=0.875: storm 3.4, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001569() -> None:
    """failures=bigfloat, stamp=3.4, jitter=1.0: storm 3.4, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.4))
    assert storm == 3.4
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001570() -> None:
    """failures=bigfloat, stamp=3.5, jitter=0.5: storm 3.5, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001571() -> None:
    """failures=bigfloat, stamp=3.5, jitter=0.625: storm 3.5, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001572() -> None:
    """failures=bigfloat, stamp=3.5, jitter=0.75: storm 3.5, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001573() -> None:
    """failures=bigfloat, stamp=3.5, jitter=0.875: storm 3.5, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001574() -> None:
    """failures=bigfloat, stamp=3.5, jitter=1.0: storm 3.5, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.5))
    assert storm == 3.5
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001575() -> None:
    """failures=bigfloat, stamp=3.6, jitter=0.5: storm 3.6, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001576() -> None:
    """failures=bigfloat, stamp=3.6, jitter=0.625: storm 3.6, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001577() -> None:
    """failures=bigfloat, stamp=3.6, jitter=0.75: storm 3.6, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001578() -> None:
    """failures=bigfloat, stamp=3.6, jitter=0.875: storm 3.6, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001579() -> None:
    """failures=bigfloat, stamp=3.6, jitter=1.0: storm 3.6, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.6))
    assert storm == 3.6
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001580() -> None:
    """failures=bigfloat, stamp=3.7, jitter=0.5: storm 3.7, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001581() -> None:
    """failures=bigfloat, stamp=3.7, jitter=0.625: storm 3.7, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001582() -> None:
    """failures=bigfloat, stamp=3.7, jitter=0.75: storm 3.7, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001583() -> None:
    """failures=bigfloat, stamp=3.7, jitter=0.875: storm 3.7, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001584() -> None:
    """failures=bigfloat, stamp=3.7, jitter=1.0: storm 3.7, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.7))
    assert storm == 3.7
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001585() -> None:
    """failures=bigfloat, stamp=3.8, jitter=0.5: storm 3.8, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001586() -> None:
    """failures=bigfloat, stamp=3.8, jitter=0.625: storm 3.8, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001587() -> None:
    """failures=bigfloat, stamp=3.8, jitter=0.75: storm 3.8, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001588() -> None:
    """failures=bigfloat, stamp=3.8, jitter=0.875: storm 3.8, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001589() -> None:
    """failures=bigfloat, stamp=3.8, jitter=1.0: storm 3.8, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.8))
    assert storm == 3.8
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001590() -> None:
    """failures=bigfloat, stamp=3.9, jitter=0.5: storm 3.9, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001591() -> None:
    """failures=bigfloat, stamp=3.9, jitter=0.625: storm 3.9, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001592() -> None:
    """failures=bigfloat, stamp=3.9, jitter=0.75: storm 3.9, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001593() -> None:
    """failures=bigfloat, stamp=3.9, jitter=0.875: storm 3.9, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001594() -> None:
    """failures=bigfloat, stamp=3.9, jitter=1.0: storm 3.9, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(3.9))
    assert storm == 3.9
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0


def test_c001595() -> None:
    """failures=bigfloat, stamp=4.0, jitter=0.5: storm 4.0, delay 15.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(10**6, storm, 0.5) == 15.0


def test_c001596() -> None:
    """failures=bigfloat, stamp=4.0, jitter=0.625: storm 4.0, delay 18.75."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(10**6, storm, 0.625) == 18.75


def test_c001597() -> None:
    """failures=bigfloat, stamp=4.0, jitter=0.75: storm 4.0, delay 22.5."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(10**6, storm, 0.75) == 22.5


def test_c001598() -> None:
    """failures=bigfloat, stamp=4.0, jitter=0.875: storm 4.0, delay 26.25."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(10**6, storm, 0.875) == 26.25


def test_c001599() -> None:
    """failures=bigfloat, stamp=4.0, jitter=1.0: storm 4.0, delay 30.0."""
    storm = pull_contention_storm_after(exhausted(4.0))
    assert storm == 4.0
    assert pull_backoff_delay(10**6, storm, 1.0) == 30.0
