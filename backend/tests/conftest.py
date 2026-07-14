"""Shared pytest hooks for the whole backend test tree."""

from collections import defaultdict
import os
import sys
from pathlib import Path
import time
import pytest
from types import ModuleType

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

# Some canonical memory modules transitively import utils.llm.clients which
# instantiates OpenAI clients at module import time; that requires an API key
# even when the client is never called. Provide a fake key so collection does
# not crash.
os.environ.setdefault('OPENAI_API_KEY', 'fake-key-for-hermetic-tests')

# Canonical memory modules transitively import utils.llm.clients which calls
# tiktoken.encoding_for_model() at module import time; that downloads an
# encoding file from the network and breaks hermetic CI. Stub it out before
# any test module imports the chain.
if 'tiktoken' not in sys.modules:
    _tiktoken_stub = ModuleType('tiktoken')
    _tiktoken_stub.encoding_for_model = lambda model: type('Encoding', (), {'encode': lambda self, text: list(text)})()
    sys.modules['tiktoken'] = _tiktoken_stub

from testing.hermetic_network import block_outbound_network

_network_guard = None
_test_file_durations = defaultdict(float)
_test_item_durations = defaultdict(float)
_test_item_cpu = defaultdict(float)
_collected_unit_files = set()

_UNIT_TEST_ROOTS = (
    BACKEND_DIR / 'tests' / 'unit',
    BACKEND_DIR / 'tests' / 'services',
    BACKEND_DIR / 'tests' / 'routers',
)
_FAST_UNIT_ALLOWLIST = BACKEND_DIR / 'tests' / 'fast_unit_duration_allowlist.txt'


def _env_enabled(name, default='1'):
    return os.environ.get(name, default).lower() not in {'0', 'false', 'no', 'off'}


def _backend_relative(path):
    try:
        return Path(path).resolve().relative_to(BACKEND_DIR).as_posix()
    except ValueError:
        return None


def _is_unit_test_path(path):
    resolved = Path(path).resolve()
    return any(resolved.is_relative_to(root) for root in _UNIT_TEST_ROOTS)


def _read_duration_allowlist():
    if not _FAST_UNIT_ALLOWLIST.exists():
        return set()
    entries = set()
    for line in _FAST_UNIT_ALLOWLIST.read_text().splitlines():
        entry = line.split('#', 1)[0].strip()
        if entry:
            entries.add(entry.removeprefix('backend/'))
    return entries


def pytest_sessionstart(session):
    global _network_guard
    _network_guard = block_outbound_network()
    _network_guard.__enter__()
    session.config._backend_test_start_time = time.perf_counter()


def pytest_collection_finish(session):
    _collected_unit_files.clear()
    for item in session.items:
        if _is_unit_test_path(item.path):
            test_file = _backend_relative(item.path)
            if test_file is not None:
                _collected_unit_files.add(test_file)


def pytest_runtest_logreport(report):
    if report.when not in {'setup', 'call', 'teardown'}:
        return
    test_file = _backend_relative(report.fspath)
    if test_file is not None and test_file in _collected_unit_files:
        _test_file_durations[test_file] += report.duration
        _test_item_durations[report.nodeid] += report.duration


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """Measure per-test CPU time (call phase only) for the duration guard.

    CPU time (``time.process_time``) is load-independent: a test that does X ms of work
    reads ~X ms whether the machine is idle or running many sibling pytest processes, so a
    hard limit is deterministic (unlike wall-clock ``report.duration``, which inflates under
    parallel contention). Only the *call* phase is measured so that shared class/file setup
    (FastAPI app / TestClient construction, per-process module import) — which file-isolated
    runs charge once to the first test — is not misattributed as a per-test regression. The
    advisory timing summary still reports wall-clock for visibility.
    """
    start = time.process_time()
    yield
    if _is_unit_test_path(item.path):
        _test_item_cpu[item.nodeid] += time.process_time() - start


def pytest_sessionfinish(session, exitstatus):
    global _network_guard
    _enforce_fast_unit_duration_guard(session)
    if _network_guard is not None:
        _network_guard.__exit__(None, None, None)
        _network_guard = None


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _env_enabled('BACKEND_PYTEST_TIMING_SUMMARY'):
        return
    if len(_collected_unit_files) <= 1:
        return
    if not _test_file_durations:
        return

    limit = int(os.environ.get('BACKEND_PYTEST_SLOW_FILE_LIMIT', '10'))
    item_limit = int(os.environ.get('BACKEND_PYTEST_SLOW_TEST_LIMIT', '10'))
    if _test_item_durations:
        terminalreporter.section('Backend unit test durations')
        slow_items = sorted(_test_item_durations.items(), key=lambda item: item[1], reverse=True)[:item_limit]
        for test_id, seconds in slow_items:
            terminalreporter.line(f'{seconds:7.2f}s  {test_id}')

    terminalreporter.section('Backend unit test file durations')
    slow_files = sorted(_test_file_durations.items(), key=lambda item: item[1], reverse=True)[:limit]
    for test_file, seconds in slow_files:
        terminalreporter.line(f'{seconds:7.2f}s  {test_file}')

    session_start = getattr(config, '_backend_test_start_time', None)
    if session_start is not None:
        terminalreporter.line(f'{time.perf_counter() - session_start:7.2f}s  total pytest session wall time')


def _enforce_fast_unit_duration_guard(session):
    raw_warn_limit = os.environ.get('BACKEND_FAST_UNIT_WARN_SECONDS')
    raw_fail_limit = os.environ.get('BACKEND_FAST_UNIT_FAIL_SECONDS')
    if (not raw_warn_limit and not raw_fail_limit) or not _collected_unit_files:
        return

    terminalreporter = session.config.pluginmanager.get_plugin('terminalreporter')
    warn_limit = _parse_fast_unit_limit(raw_warn_limit, 'BACKEND_FAST_UNIT_WARN_SECONDS', terminalreporter)
    fail_limit = _parse_fast_unit_limit(raw_fail_limit, 'BACKEND_FAST_UNIT_FAIL_SECONDS', terminalreporter)
    if warn_limit is None and raw_warn_limit:
        session.exitstatus = 1
        return
    if fail_limit is None and raw_fail_limit:
        session.exitstatus = 1
        return

    if warn_limit is None:
        warn_limit = fail_limit
    if fail_limit is not None and warn_limit is not None and fail_limit < warn_limit:
        terminalreporter = session.config.pluginmanager.get_plugin('terminalreporter')
        if terminalreporter is not None:
            terminalreporter.section('Backend fast unit duration guard configuration error')
            terminalreporter.line(
                'BACKEND_FAST_UNIT_FAIL_SECONDS must be greater than or equal to ' 'BACKEND_FAST_UNIT_WARN_SECONDS.'
            )
        session.exitstatus = 1
        return

    # The guard measures per-test CPU time (``_test_item_cpu``), not wall-clock. CPU time is
    # load-independent: a test that does X ms of work reads ~X ms whether the machine is idle or
    # running many sibling pytest processes, whereas wall-clock ``report.duration`` inflates
    # unpredictably under parallel contention and makes a hard limit flake. Sleep/wait-based
    # slowness (real asyncio sleeps, network, stress) is excluded from the PR unit lane via
    # ``slow``/``integration`` markers, so CPU time is the right signal here. The advisory
    # timing summary in pytest_terminal_summary still reports wall-clock for visibility.
    # The warning threshold is the target for fast unit tests. The failure threshold is the
    # blocking budget; local pre-push stays strict, while CI uses a broad sanity ceiling so
    # cross-machine CPU differences do not make unrelated pull requests flaky.

    allowlist = _read_duration_allowlist()
    unit_test_items = {
        nodeid: seconds
        for nodeid, seconds in _test_item_cpu.items()
        if nodeid.split('::', 1)[0] in _collected_unit_files
    }
    warning_offenders = [
        (test_id, seconds)
        for test_id, seconds in sorted(unit_test_items.items(), key=lambda item: item[1], reverse=True)
        if (
            warn_limit is not None
            and seconds > warn_limit
            and (fail_limit is None or seconds <= fail_limit)
            and not _duration_allowlisted(test_id, allowlist)
        )
    ]
    failure_offenders = [
        (test_id, seconds)
        for test_id, seconds in sorted(unit_test_items.items(), key=lambda item: item[1], reverse=True)
        if fail_limit is not None and seconds > fail_limit and not _duration_allowlisted(test_id, allowlist)
    ]
    if not warning_offenders and not failure_offenders:
        return

    if terminalreporter is not None:
        if warning_offenders:
            terminalreporter.section('Backend fast unit duration guard warnings (CPU time)')
            for test_id, seconds in warning_offenders:
                terminalreporter.line(f'{seconds:7.2f}s > {warn_limit:.2f}s  {test_id}')
        if failure_offenders:
            terminalreporter.section('Backend fast unit duration guard failures (CPU time)')
            for test_id, seconds in failure_offenders:
                terminalreporter.line(f'{seconds:7.2f}s > {fail_limit:.2f}s  {test_id}')
        terminalreporter.line(
            f'(CPU time, call phase only; warn limit = {warn_limit:.2f}s'
            + (f', fail limit = {fail_limit:.2f}s.)' if fail_limit is not None else '.)')
        )
        terminalreporter.line(f'Allow intentional exceptions in {_FAST_UNIT_ALLOWLIST.relative_to(BACKEND_DIR)}.')
    if failure_offenders:
        session.exitstatus = 1


def _parse_fast_unit_limit(raw_value, name, terminalreporter):
    if raw_value is None or raw_value == '':
        return None
    try:
        return float(raw_value)
    except ValueError:
        if terminalreporter is not None:
            terminalreporter.section('Backend fast unit duration guard configuration error')
            terminalreporter.line(f'Invalid {name} value: {raw_value}')
        return None


def _duration_allowlisted(test_id, allowlist):
    test_file = test_id.split('::', 1)[0]
    return test_id in allowlist or test_file in allowlist
