"""Pull backoff state grid: chained exhaustions, exact armed deadlines.

The armed ``_contention_backoff_until`` deadline is the real lane behavior. Each
cell drives the real scheduler through 1-3 chained contention losses with one stamp
shape and one jitter draw, advancing the clock exactly to the previous window, and
pins the exact armed deadline, the failure count, and the in-window suppression:
12 stamp shapes x 4 jitter draws x 3 chain depths = 144 cells.

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
from utils.batch_pipeline import scheduler as scheduler_module
from utils.batch_pipeline.scheduler import Scheduler


class _StormStore:
    """A pull-lane store stub: the grid drives the handler directly."""

    def run(self, body, *, operation=None):
        return body(None)


def exhausted(stamp=None):
    """A contention exhaustion carrying the case's stamped window."""
    error = FirestoreContentionExhausted('bounded contention')
    if stamp is not None:
        error.retry_after = stamp
    return error


def test_state_stamp00_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=no-stamp, random draw 0.0: arms 100.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp00_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=no-stamp, random draw 0.0: arms 101.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp00_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=no-stamp, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp00_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=no-stamp, random draw 0.25: arms 100.625s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.625
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp00_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=no-stamp, random draw 0.25: arms 101.875s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.875
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp00_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=no-stamp, random draw 0.25: arms 104.375s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.375
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp00_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=no-stamp, random draw 0.5: arms 100.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp00_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=no-stamp, random draw 0.5: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp00_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=no-stamp, random draw 0.5: arms 105.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp00_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=no-stamp, random draw 0.9: arms 100.95s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.95
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp00_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=no-stamp, random draw 0.9: arms 102.85000000000001s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.85000000000001
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp00_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=no-stamp, random draw 0.9: arms 106.65s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted() for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.65
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp01_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=None, random draw 0.0: arms 100.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp01_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=None, random draw 0.0: arms 101.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp01_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=None, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp01_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=None, random draw 0.25: arms 100.625s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.625
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp01_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=None, random draw 0.25: arms 101.875s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.875
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp01_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=None, random draw 0.25: arms 104.375s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.375
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp01_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=None, random draw 0.5: arms 100.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp01_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=None, random draw 0.5: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp01_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=None, random draw 0.5: arms 105.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp01_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=None, random draw 0.9: arms 100.95s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.95
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp01_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=None, random draw 0.9: arms 102.85000000000001s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.85000000000001
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp01_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=None, random draw 0.9: arms 106.65s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(None) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.65
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp02_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-0.0, random draw 0.0: arms 100.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp02_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-0.0, random draw 0.0: arms 101.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp02_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-0.0, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp02_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-0.0, random draw 0.25: arms 100.625s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.625
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp02_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-0.0, random draw 0.25: arms 101.875s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.875
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp02_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-0.0, random draw 0.25: arms 104.375s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.375
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp02_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-0.0, random draw 0.5: arms 100.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp02_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-0.0, random draw 0.5: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp02_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-0.0, random draw 0.5: arms 105.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp02_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-0.0, random draw 0.9: arms 100.95s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.95
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp02_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-0.0, random draw 0.9: arms 102.85000000000001s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.85000000000001
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp02_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-0.0, random draw 0.9: arms 106.65s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.65
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp03_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.0: arms 100.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp03_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.0: arms 101.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp03_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp03_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.25: arms 100.625s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.625
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp03_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.25: arms 101.875s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.875
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp03_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.25: arms 104.375s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.375
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp03_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.5: arms 100.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp03_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.5: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp03_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.5: arms 105.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp03_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.9: arms 100.95s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.95
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp03_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.9: arms 102.85000000000001s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.85000000000001
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp03_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=float-minus-1.0, random draw 0.9: arms 106.65s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(-1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.65
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp04_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=nan, random draw 0.0: arms 100.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp04_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=nan, random draw 0.0: arms 101.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp04_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=nan, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp04_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=nan, random draw 0.25: arms 100.625s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.625
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp04_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=nan, random draw 0.25: arms 101.875s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.875
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp04_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=nan, random draw 0.25: arms 104.375s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.375
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp04_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=nan, random draw 0.5: arms 100.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp04_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=nan, random draw 0.5: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp04_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=nan, random draw 0.5: arms 105.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp04_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=nan, random draw 0.9: arms 100.95s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.95
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp04_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=nan, random draw 0.9: arms 102.85000000000001s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.85000000000001
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp04_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=nan, random draw 0.9: arms 106.65s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(float('nan')) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.65
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp05_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.25, random draw 0.0: arms 100.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp05_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.25, random draw 0.0: arms 101.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp05_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.25, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp05_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.25, random draw 0.25: arms 100.625s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.625
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp05_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.25, random draw 0.25: arms 101.875s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.875
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp05_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.25, random draw 0.25: arms 104.375s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.375
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp05_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.25, random draw 0.5: arms 100.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp05_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.25, random draw 0.5: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp05_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.25, random draw 0.5: arms 105.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp05_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.25, random draw 0.9: arms 100.95s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.95
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp05_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.25, random draw 0.9: arms 102.85000000000001s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.85000000000001
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp05_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.25, random draw 0.9: arms 106.65s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.25) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.65
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp06_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.5, random draw 0.0: arms 100.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp06_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.5, random draw 0.0: arms 101.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp06_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.5, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp06_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.5, random draw 0.25: arms 100.625s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.625
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp06_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.5, random draw 0.25: arms 101.875s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 101.875
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp06_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.5, random draw 0.25: arms 104.375s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.375
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp06_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.5, random draw 0.5: arms 100.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp06_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.5, random draw 0.5: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp06_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.5, random draw 0.5: arms 105.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp06_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=0.5, random draw 0.9: arms 100.95s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 100.95
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp06_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=0.5, random draw 0.9: arms 102.85000000000001s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.85000000000001
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp06_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=0.5, random draw 0.9: arms 106.65s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(0.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.65
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp07_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1.0, random draw 0.0: arms 101.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 101.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp07_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1.0, random draw 0.0: arms 102.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp07_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1.0, random draw 0.0: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp07_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1.0, random draw 0.25: arms 101.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 101.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp07_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1.0, random draw 0.25: arms 102.25s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.25
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp07_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1.0, random draw 0.25: arms 104.75s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 104.75
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp07_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1.0, random draw 0.5: arms 101.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 101.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp07_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1.0, random draw 0.5: arms 102.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp07_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1.0, random draw 0.5: arms 105.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 105.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp07_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1.0, random draw 0.9: arms 101.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 101.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp07_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1.0, random draw 0.9: arms 102.9s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 102.9
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp07_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1.0, random draw 0.9: arms 106.7s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.7
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp08_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=2.0, random draw 0.0: arms 102.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 102.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp08_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=2.0, random draw 0.0: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp08_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=2.0, random draw 0.0: arms 106.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp08_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=2.0, random draw 0.25: arms 102.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 102.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp08_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=2.0, random draw 0.25: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp08_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=2.0, random draw 0.25: arms 106.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 106.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp08_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=2.0, random draw 0.5: arms 102.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 102.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp08_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=2.0, random draw 0.5: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp08_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=2.0, random draw 0.5: arms 107.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 107.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp08_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=2.0, random draw 0.9: arms 102.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 102.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp08_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=2.0, random draw 0.9: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp08_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=2.0, random draw 0.9: arms 107.8s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(2.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 107.8
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp09_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=3.5, random draw 0.0: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp09_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=3.5, random draw 0.0: arms 107.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 107.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp09_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=3.5, random draw 0.0: arms 110.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 110.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp09_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=3.5, random draw 0.25: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp09_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=3.5, random draw 0.25: arms 107.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 107.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp09_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=3.5, random draw 0.25: arms 110.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 110.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp09_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=3.5, random draw 0.5: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp09_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=3.5, random draw 0.5: arms 107.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 107.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp09_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=3.5, random draw 0.5: arms 110.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 110.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp09_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=3.5, random draw 0.9: arms 103.5s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 103.5
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp09_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=3.5, random draw 0.9: arms 107.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 107.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp09_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=3.5, random draw 0.9: arms 110.8s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(3.5) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 110.8
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp10_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=4.0, random draw 0.0: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp10_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=4.0, random draw 0.0: arms 108.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 108.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp10_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=4.0, random draw 0.0: arms 112.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 112.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp10_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=4.0, random draw 0.25: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp10_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=4.0, random draw 0.25: arms 108.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 108.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp10_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=4.0, random draw 0.25: arms 112.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 112.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp10_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=4.0, random draw 0.5: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp10_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=4.0, random draw 0.5: arms 108.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 108.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp10_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=4.0, random draw 0.5: arms 112.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 112.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp10_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=4.0, random draw 0.9: arms 104.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 104.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp10_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=4.0, random draw 0.9: arms 108.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 108.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp10_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=4.0, random draw 0.9: arms 112.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(4.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 112.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp11_r0_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1e9, random draw 0.0: arms 130.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 130.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp11_r0_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1e9, random draw 0.0: arms 160.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 160.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp11_r0_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1e9, random draw 0.0: arms 190.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.0)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 190.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp11_r1_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1e9, random draw 0.25: arms 130.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 130.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp11_r1_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1e9, random draw 0.25: arms 160.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 160.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp11_r1_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1e9, random draw 0.25: arms 190.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.25)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 190.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp11_r2_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1e9, random draw 0.5: arms 130.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 130.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp11_r2_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1e9, random draw 0.5: arms 160.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 160.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp11_r2_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1e9, random draw 0.5: arms 190.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.5)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 190.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3


def test_state_stamp11_r3_chain1(monkeypatch) -> None:
    """1 chained exhaustion(s), stamp=1e9, random draw 0.9: arms 130.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(1)])
    for _ in range(1):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 1
    assert queue._contention_backoff_until == 130.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 1


def test_state_stamp11_r3_chain2(monkeypatch) -> None:
    """2 chained exhaustion(s), stamp=1e9, random draw 0.9: arms 160.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(2)])
    for _ in range(2):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 2
    assert queue._contention_backoff_until == 160.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 2


def test_state_stamp11_r3_chain3(monkeypatch) -> None:
    """3 chained exhaustion(s), stamp=1e9, random draw 0.9: arms 190.0s and suppresses inside."""
    now = [100.0]
    monkeypatch.setattr(scheduler_module, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scheduler_module.random, 'random', lambda: 0.9)
    queue = Scheduler(_StormStore())
    queue._pull_one = Mock(side_effect=[exhausted(1000000000.0) for _ in range(3)])
    for _ in range(3):
        assert queue.pull(1) == []
        now[0] = queue._contention_backoff_until
    assert queue._contention_failures == 3
    assert queue._contention_backoff_until == 190.0
    now[0] = queue._contention_backoff_until - 0.01
    assert queue.pull(1) == []
    assert queue._contention_failures == 3
