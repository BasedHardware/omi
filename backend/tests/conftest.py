"""Shared pytest hooks for the whole backend test tree."""

from collections import defaultdict
import os
import sys
from pathlib import Path
import time
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
    terminalreporter.section('Backend unit test file durations')
    slow_files = sorted(_test_file_durations.items(), key=lambda item: item[1], reverse=True)[:limit]
    for test_file, seconds in slow_files:
        terminalreporter.line(f'{seconds:7.2f}s  {test_file}')

    session_start = getattr(config, '_backend_test_start_time', None)
    if session_start is not None:
        terminalreporter.line(f'{time.perf_counter() - session_start:7.2f}s  total pytest session wall time')


def _enforce_fast_unit_duration_guard(session):
    raw_limit = os.environ.get('BACKEND_FAST_UNIT_MAX_SECONDS')
    if not raw_limit or not _collected_unit_files:
        return
    try:
        limit = float(raw_limit)
    except ValueError:
        terminalreporter = session.config.pluginmanager.get_plugin('terminalreporter')
        if terminalreporter is not None:
            terminalreporter.section('Backend fast unit duration guard failures')
            terminalreporter.line(f'Invalid BACKEND_FAST_UNIT_MAX_SECONDS value: {raw_limit}')
        session.exitstatus = 1
        return

    allowlist = _read_duration_allowlist()
    offenders = [
        (test_file, seconds)
        for test_file, seconds in sorted(_test_file_durations.items(), key=lambda item: item[1], reverse=True)
        if seconds > limit and test_file not in allowlist
    ]
    if not offenders:
        return

    terminalreporter = session.config.pluginmanager.get_plugin('terminalreporter')
    if terminalreporter is not None:
        terminalreporter.section('Backend fast unit duration guard failures')
        for test_file, seconds in offenders:
            terminalreporter.line(f'{seconds:7.2f}s > {limit:.2f}s  {test_file}')
        terminalreporter.line(f'Allow intentional exceptions in {_FAST_UNIT_ALLOWLIST.relative_to(BACKEND_DIR)}.')
    session.exitstatus = 1
