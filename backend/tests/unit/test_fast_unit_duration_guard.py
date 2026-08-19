from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import sys

TESTS_DIR = Path(__file__).resolve().parents[1]
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import conftest as backend_conftest


class _Reporter:
    def __init__(self):
        self.messages: list[str] = []

    def section(self, message):
        self.messages.append(message)

    def line(self, message):
        self.messages.append(message)


class _PluginManager:
    def __init__(self, reporter):
        self._reporter = reporter

    def get_plugin(self, name):
        return self._reporter if name == 'terminalreporter' else None


class _Config:
    def __init__(self, reporter):
        self.pluginmanager = _PluginManager(reporter)


class _Session:
    def __init__(self, reporter):
        self.config = _Config(reporter)
        self.exitstatus = 0


def test_fast_unit_duration_guard_warns_without_failing_below_fail_threshold(monkeypatch):
    reporter = _Reporter()
    session = _Session(reporter)

    monkeypatch.setenv('BACKEND_FAST_UNIT_WARN_SECONDS', '0.1')
    monkeypatch.setenv('BACKEND_FAST_UNIT_FAIL_SECONDS', '0.25')
    monkeypatch.setattr(backend_conftest, '_collected_unit_files', {'tests/unit/test_example.py'})
    monkeypatch.setattr(
        backend_conftest,
        '_test_item_cpu',
        defaultdict(float, {'tests/unit/test_example.py::test_near_target': 0.14}),
    )
    monkeypatch.setattr(backend_conftest, '_read_duration_allowlist', lambda: set())

    backend_conftest._enforce_fast_unit_duration_guard(session)

    assert session.exitstatus == 0
    assert any('warnings' in message for message in reporter.messages)
    assert not any('failures' in message for message in reporter.messages)


def test_fast_unit_duration_guard_fails_above_fail_threshold(monkeypatch):
    reporter = _Reporter()
    session = _Session(reporter)

    monkeypatch.setenv('BACKEND_FAST_UNIT_WARN_SECONDS', '0.1')
    monkeypatch.setenv('BACKEND_FAST_UNIT_FAIL_SECONDS', '0.12')
    monkeypatch.setattr(backend_conftest, '_collected_unit_files', {'tests/unit/test_example.py'})
    monkeypatch.setattr(
        backend_conftest,
        '_test_item_cpu',
        defaultdict(float, {'tests/unit/test_example.py::test_slow': 0.14}),
    )
    monkeypatch.setattr(backend_conftest, '_read_duration_allowlist', lambda: set())

    backend_conftest._enforce_fast_unit_duration_guard(session)

    assert session.exitstatus == 1
    assert any('failures' in message for message in reporter.messages)


def test_fast_unit_duration_guard_rejects_fail_threshold_below_warn_threshold(monkeypatch):
    reporter = _Reporter()
    session = _Session(reporter)

    monkeypatch.setenv('BACKEND_FAST_UNIT_WARN_SECONDS', '0.2')
    monkeypatch.setenv('BACKEND_FAST_UNIT_FAIL_SECONDS', '0.1')
    monkeypatch.setattr(backend_conftest, '_collected_unit_files', {'tests/unit/test_example.py'})
    monkeypatch.setattr(
        backend_conftest,
        '_test_item_cpu',
        defaultdict(float, {'tests/unit/test_example.py::test_fast': 0.01}),
    )

    backend_conftest._enforce_fast_unit_duration_guard(session)

    assert session.exitstatus == 1
    assert any('configuration error' in message for message in reporter.messages)


# The guard measures CPU time because wall-clock inflates under parallel load. CPU
# time inflates too, just less: contention stall cycles are charged to the process,
# so identical work reads higher CPU when the file-isolated runner saturates the
# machine. Measured on an idle vs saturated 8-core host, one file's slowest test read
# 0.03s CPU idle (3 of 3 runs) and 0.05-0.06s saturated -- about 2x. A calibration
# probe cannot cancel this: a cache-resident CPU loop does not inflate at all
# (0.49ms -> 0.46ms median), so the inflation is memory-bound and workload-specific.
# The blocking budget must therefore keep headroom over the warn target, or a test
# that meets the target fails whenever the machine happens to be busy.
_MEASURED_CONTENTION_FACTOR = 2.0


def _shipped_local_thresholds():
    """Read the defaults ``test.sh`` ships so this tracks what developers actually run."""
    runner = (TESTS_DIR.parent / 'test.sh').read_text()
    warn = re.search(r'BACKEND_FAST_UNIT_WARN_SECONDS="\$\{BACKEND_FAST_UNIT_WARN_SECONDS:-([0-9.]+)\}"', runner)
    fail = re.search(r'BACKEND_FAST_UNIT_FAIL_SECONDS="\$\{BACKEND_FAST_UNIT_FAIL_SECONDS:-([0-9.]+)\}"', runner)
    assert warn is not None and fail is not None, 'test.sh no longer declares default fast-unit thresholds'
    return float(warn.group(1)), float(fail.group(1))


def test_shipped_local_budget_survives_contention_inflation(monkeypatch):
    """Regression: the local lane failed a moving set of files under parallel load.

    Two full ``test.sh`` runs on one machine disagreed on 15 files, in both
    directions, and every one of them passed in isolation -- all 15 were duration
    guard failures clustered just above the budget. A test that meets the CPU
    target must not fail merely because the runner was busy.
    """
    warn_limit, fail_limit = _shipped_local_thresholds()
    at_target_under_contention = warn_limit * _MEASURED_CONTENTION_FACTOR

    reporter = _Reporter()
    session = _Session(reporter)
    monkeypatch.setenv('BACKEND_FAST_UNIT_WARN_SECONDS', str(warn_limit))
    monkeypatch.setenv('BACKEND_FAST_UNIT_FAIL_SECONDS', str(fail_limit))
    monkeypatch.setattr(backend_conftest, '_collected_unit_files', {'tests/unit/test_example.py'})
    monkeypatch.setattr(
        backend_conftest,
        '_test_item_cpu',
        defaultdict(float, {'tests/unit/test_example.py::test_at_target': at_target_under_contention}),
    )
    monkeypatch.setattr(backend_conftest, '_read_duration_allowlist', lambda: set())

    backend_conftest._enforce_fast_unit_duration_guard(session)

    assert session.exitstatus == 0, (
        f'a test meeting the {warn_limit}s CPU target measures '
        f'{at_target_under_contention:.2f}s under {_MEASURED_CONTENTION_FACTOR}x contention, '
        f'which the shipped {fail_limit}s local budget fails'
    )
