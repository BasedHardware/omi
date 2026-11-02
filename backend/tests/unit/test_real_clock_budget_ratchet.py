"""Ratchet: tests must not hand production code a tiny REAL-clock budget.

Why: on 2026-10-20 three backend unit tests raced a sub-second real-time budget
and flaked or failed CI: ``SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05`` in
``test_sync_cloud_tasks.py`` (#22758, then the legacy-retire change C10),
``DAILY_SUMMARY_USER_BUDGET_SECONDS = 0.05`` and
``REQUEST_TIMEOUT_SECONDS = 0.02`` (all three fixed in #22767). The shape is
always the same: a test shrinks a production budget/deadline/timeout to tens of
milliseconds and then expects healthy in-process work to finish inside it. On a
loaded CI runner a scheduler hiccup is longer than the budget, so the
"healthy" path times out and the test fails for reasons unrelated to the change
under review.

What is flagged (static AST scan of ``backend/tests/**/*.py``; nothing under
test is imported), when the name matches ``budget|deadline|timeout``
(case-insensitive) and the value is a literal with ``0 < value < 0.5`` seconds:

- attribute assignment: ``module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05``
- attribute patching: ``monkeypatch.setattr(module, 'X_TIMEOUT', 0.02)``,
  ``setattr(...)``, ``patch.object(module, 'X_TIMEOUT', 0.02)``, and the
  dotted-string forms ``monkeypatch.setattr('pkg.mod.X_TIMEOUT', 0.02)`` /
  ``patch('pkg.mod.X_TIMEOUT', 0.02)`` / ``patch(..., new=0.02)`` (also
  ``patch.object(..., new=0.02)``)
- env-backed budgets: ``monkeypatch.setenv('X_TIMEOUT_SECONDS', '0.05')``,
  ``os.environ['X_TIMEOUT_SECONDS'] = '0.05'``, and
  ``patch.dict(os.environ | 'os.environ', {...} | values={...} | X_TIMEOUT='0.05')``
- keyword arguments to code under test: ``drain_tasks(..., timeout=0.1)``,
  ``Budget(deadline_seconds=0.01)``

Not flagged: harness waits whose timeout only bounds the test itself
(``asyncio.wait_for``, ``Event.wait``, ``Queue.get``, ``Thread.join``,
``Future.result``, ``Lock.acquire``), mock call assertions
(``assert_called_with(timeout=...)``), Redis client construction, ``sleep``,
plain local variables, and any value inside a function (decorators included)
that visibly controls the clock: a fake/injected ``clock=`` (not ``None`` or
``time.*``), ``freeze_time``/``freezegun``/``time_machine``, or
``monotonic``/``perf_counter`` replaced by something other than the real
``time.*`` function (``{'monotonic': time.monotonic}`` is a real clock).
Known gap: numbers nested inside a dict/list argument
(``methods_timeout={'GET': 0.001}``) are not inspected.

How to fix a new offender (in order of preference):

1. Inject or patch the clock (``clock=``, a fake ``monotonic``) so the budget
   expires deterministically, or make the stub itself expire the budget (see
   ``_pipeline_expiring_the_handler_budget`` in ``test_sync_cloud_tasks.py``).
2. If the test only needs the timeout path, block the stub on an
   ``asyncio.Event`` that is never set, and keep the budget >= 0.5 s.
3. Otherwise raise the budget to >= 0.5 s so healthy work cannot race it.

Allowlist policy (``real_clock_budget_allowlist.txt`` next to this file): one
line per existing offender, keyed ``path::qualname::name=value`` (no line
numbers), each with an owner, a tracking reference and a reason, e.g.
``# TODO(owner): #22767 why``. It only shrinks: a new offender fails, and so
does an entry that no longer matches anything (delete it when you fix the
test). Duplicate offenders inside one function share one key. Do not add
entries for new code; fix the test instead.

Speed: only files whose lowercased bytes contain a ``budget|deadline|timeout``
name followed directly (``=``, ``,``, ``:``, or ``new=``) by a literal that can
be below 1 are parsed; every flagged shape above satisfies that, so the byte
prefilter only skips files that cannot produce a finding.

Print the current unallowlisted offenders as allowlist lines::

    cd backend && python tests/unit/test_real_clock_budget_ratchet.py
"""

from __future__ import annotations

import ast
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Set, Tuple

import pytest

# A codebase scan: runs in the slow-guardrail lane (tests/slow_guardrail_manifest.txt).
pytestmark = pytest.mark.slow

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = BACKEND_ROOT / 'tests'
ALLOWLIST_PATH = Path(__file__).with_name('real_clock_budget_allowlist.txt')

LIMIT_SECONDS = 0.5

_BUDGET_NAME = re.compile(r'budget|deadline|timeout', re.IGNORECASE)
_KEYWORDS = (b'budget', b'deadline', b'timeout')
# Byte-level superset of every flagged shape, run on lowercased source so only candidate files are parsed:
# a name containing a keyword, an optional closing quote/bracket, one of ``=`` ``,`` ``:``, an optional
# ``float =`` / ``new=``, an optional opening quote, then a literal that can be below 1 (``0.05``, ``.05``, ``5e-2``).
_PREFILTER = re.compile(
    # Possessive quantifiers (Python 3.11+) keep adjacent whitespace runs from backtracking polynomially.
    rb'(?:budget|deadline|timeout)\w*+[\'"]?\]?\s*+[=,:]\s*+(?:\w++\s*+=\s*+)?(?:\(\s*+)*+[\'"]?\s*+\+?'
    rb'(?:0*+\.\d|[\d_]++(?:\.[\d_]*+)?e-\d)'
)
# Clock control: a fake/injected clock, a time-freezing library, or monotonic/perf_counter replaced by something
# other than the real ``time.*`` function. ``'monotonic': time.monotonic`` and ``clock=None`` are real clocks.
# Possessive whitespace/parenthesis/keyword introducers, then a lookahead that rejects a real clock. Rejecting
# ``\s``, ``(`` and a bare ``new=``/``value=`` too means skipping an introducer can never sneak past the check.
_REAL_CLOCK_VALUE = r'\s*+(?:(?:new|value)\s*+=\s*+)?+(?:\(\s*+)*+(?!\s|\(|(?:new|value)\s*=|time\.|None\b)'
_FAKE_CLOCK = re.compile(
    r'fake_?clock|freeze_?time|freezegun|time_machine|'
    rf'\bclock\s*+=(?!=){_REAL_CLOCK_VALUE}|'
    rf'[\'"](?:monotonic|perf_counter)[\'"]\s*+[,:]{_REAL_CLOCK_VALUE}|'
    rf'\.(?:monotonic|perf_counter)\s*+=(?!=){_REAL_CLOCK_VALUE}',
    re.IGNORECASE,
)
# Callees whose timeout bounds the test harness, not the code under test.
_HARNESS_CALLEES = frozenset(
    {
        'wait_for',
        'wait',
        'get',
        'join',
        'result',
        'acquire',
        'put',
        'Redis',
        'StrictRedis',
        'from_url',
        'assert_called_with',
        'assert_called_once_with',
        'assert_any_call',
        'assert_awaited_with',
        'assert_awaited_once_with',
        'assert_any_await',
        'call',
    }
)
_ALLOWLIST_COMMENT = re.compile(r'^TODO\((?P<owner>[^)]+)\):\s*#\d+\s+(?P<reason>\S.*)$')


def _number(node: ast.AST, *, allow_str: bool) -> Optional[float]:
    if not isinstance(node, ast.Constant):
        return None
    value = node.value
    if type(value) in (int, float):
        return float(value)
    if allow_str and isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _string(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return '.'.join(reversed(parts))


def _format(value: float) -> str:
    return format(value, 'g')


def _is_environ(node: ast.AST) -> bool:
    target = _string(node)
    if target is None:
        target = _dotted(node)
    return target.rsplit('.', 1)[-1] == 'environ'


class _Scanner(ast.NodeVisitor):
    def __init__(self, rel_path: str, lines: Sequence[str]) -> None:
        self.rel_path = rel_path
        self.lines = lines
        self.scope: List[str] = []
        self.outer_def: Optional[ast.AST] = None
        self.clock_controlled = False
        self.found: Set[str] = set()

    def _enter(self, node: ast.AST) -> None:
        self.scope.append(node.name)  # type: ignore[attr-defined]
        is_outer_def = self.outer_def is None and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if is_outer_def:
            self.outer_def = node
            # Include decorators so ``@freeze_time(...)`` above the ``def`` counts as clock control.
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])  # type: ignore[attr-defined]
            source = '\n'.join(self.lines[start - 1 : node.end_lineno])  # type: ignore[attr-defined]
            self.clock_controlled = bool(_FAKE_CLOCK.search(source))
        self.generic_visit(node)
        if is_outer_def:
            self.outer_def = None
            self.clock_controlled = False
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _enter

    def _flag(self, name: str, value: Optional[float]) -> None:
        if value is None or not (0 < value < LIMIT_SECONDS) or not _BUDGET_NAME.search(name):
            return
        if self.clock_controlled:
            return
        qualname = '.'.join(self.scope) or '<module>'
        self.found.add(f'{self.rel_path}::{qualname}::{name}={_format(value)}')

    def _assign(self, targets: Sequence[ast.AST], value: Optional[ast.AST]) -> None:
        if value is None:
            return
        for target in targets:
            if isinstance(target, ast.Attribute):
                self._flag(target.attr, _number(value, allow_str=False))
            elif isinstance(target, ast.Subscript) and _is_environ(target.value):
                key = _string(target.slice)
                if key is not None:
                    self._flag(key, _number(value, allow_str=True))

    def visit_Assign(self, node: ast.Assign) -> None:
        self._assign(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._assign([node.target], node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee = _dotted(node.func)
        last = callee.rsplit('.', 1)[-1]
        args = node.args
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}

        if last in ('setattr', 'object') and len(args) >= 2 and _string(args[1]) is not None:
            # setattr(obj, 'NAME', v) / monkeypatch.setattr(obj, 'NAME', v) / patch.object(obj, 'NAME', v | new=v)
            value = args[2] if len(args) >= 3 else keywords.get('new')
            if value is not None:
                self._flag(_string(args[1]), _number(value, allow_str=False))  # type: ignore[arg-type]
        elif last in ('setattr', 'patch') and args and _string(args[0]) is not None:
            # monkeypatch.setattr('pkg.mod.NAME', v) / patch('pkg.mod.NAME', v) / patch('pkg.mod.NAME', new=v)
            value = args[1] if len(args) >= 2 else keywords.get('new')
            if value is not None:
                self._flag(_string(args[0]).rsplit('.', 1)[-1], _number(value, allow_str=False))  # type: ignore[union-attr]
        elif last == 'setenv' and len(args) >= 2 and _string(args[0]) is not None:
            self._flag(_string(args[0]), _number(args[1], allow_str=True))  # type: ignore[arg-type]
        elif last == 'dict' and args and _is_environ(args[0]):
            # patch.dict(os.environ | 'os.environ', {'NAME': '0.05'} | values={...}, NAME='0.05')
            mapping = args[1] if len(args) >= 2 else keywords.get('values')
            if isinstance(mapping, ast.Dict):
                for key, value in zip(mapping.keys, mapping.values):
                    if key is not None and _string(key) is not None:
                        self._flag(_string(key), _number(value, allow_str=True))  # type: ignore[arg-type]
            for name, value in keywords.items():
                self._flag(name, _number(value, allow_str=True))

        if last not in _HARNESS_CALLEES and not last.startswith('assert_'):
            for name, value in keywords.items():
                self._flag(name, _number(value, allow_str=False))
        self.generic_visit(node)


def _might_match(data: bytes) -> bool:
    lowered = data.lower()
    return any(name in lowered for name in _KEYWORDS) and _PREFILTER.search(lowered) is not None


def scan_bytes(rel_path: str, data: bytes) -> Set[str]:
    if not _might_match(data):
        return set()
    source = data.decode('utf-8')
    scanner = _Scanner(rel_path, source.splitlines())
    scanner.visit(ast.parse(source, filename=rel_path))
    return scanner.found


def _test_files() -> Iterator[Path]:
    for path in sorted(TESTS_ROOT.rglob('*.py')):
        if '__pycache__' not in path.parts:
            yield path


@lru_cache(maxsize=1)
def scan_tree() -> frozenset:
    found: Set[str] = set()
    for path in _test_files():
        found |= scan_bytes(path.relative_to(BACKEND_ROOT).as_posix(), path.read_bytes())
    return frozenset(found)


def load_allowlist(path: Path = ALLOWLIST_PATH) -> List[Tuple[str, str]]:
    entries = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        entry, _, comment = line.partition('#')
        entries.append((entry.strip(), comment.strip()))
    return entries


_HOW_TO_FIX = (
    'Inject or patch the clock so the budget expires deterministically, make the stub itself expire the '
    'budget, or keep the budget >= 0.5 s. See the docstring of tests/unit/test_real_clock_budget_ratchet.py.'
)


def test_no_new_tiny_real_clock_budgets() -> None:
    allowed = {entry for entry, _ in load_allowlist()}
    new = sorted(scan_tree() - allowed)
    assert not new, (
        f'{len(new)} test(s) hand production code a real-clock budget under {LIMIT_SECONDS} s, which races a '
        f'loaded CI runner (#22758, #22767):\n  ' + '\n  '.join(new) + f'\n{_HOW_TO_FIX}'
    )


def test_allowlist_has_no_stale_entries() -> None:
    stale = sorted({entry for entry, _ in load_allowlist()} - scan_tree())
    assert not stale, (
        'These real_clock_budget_allowlist.txt entries no longer match a test; delete them so the list only '
        'shrinks:\n  ' + '\n  '.join(stale)
    )


def test_allowlist_entries_are_unique_and_owned() -> None:
    entries = load_allowlist()
    seen: Set[str] = set()
    problems = []
    for entry, comment in entries:
        if entry in seen:
            problems.append(f'duplicate: {entry}')
        seen.add(entry)
        if entry.count('::') != 2 or '=' not in entry.rsplit('::', 1)[-1]:
            problems.append(f'malformed key (want path::qualname::name=value): {entry}')
        if not _ALLOWLIST_COMMENT.match(comment):
            problems.append(f'comment must be "# TODO(owner): #<issue> reason": {entry}')
    assert not problems, '\n'.join(problems)


_SAMPLE = '''
import asyncio, os
from unittest.mock import patch

module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05

def test_flagged(monkeypatch):
    module.REQUEST_TIMEOUT_SECONDS = 0.02
    monkeypatch.setattr(module, 'DAILY_SUMMARY_USER_BUDGET_SECONDS', 0.05)
    monkeypatch.setattr('pkg.mod.FIRST_EVENT_TIMEOUT_SECONDS', 0.01)
    monkeypatch.setenv('STT_ROUTING_REDIS_TIMEOUT_SECONDS', '0.1')
    os.environ['WINDOW_DEADLINE_SECONDS'] = '0.2'
    with patch.object(module, 'PROBE_TIMEOUT', 1e-2), patch('pkg.mod.LIST_BUDGET', new=0.3):
        pass
    with patch.dict(os.environ, {'POST_TIMEOUT_SECONDS': '0.05'}):
        pass
    drain_tasks(tasks, timeout=0.1)

class TestShape:
    def test_method(self):
        shaped.Budget(deadline_seconds=0.01)

async def test_not_flagged(monkeypatch):
    module.REQUEST_TIMEOUT_SECONDS = 0.5
    module.REQUEST_TIMEOUT_SECONDS = 0
    module.RETRY_COUNT = 0.05
    timeout = 0.05
    await asyncio.wait_for(task, timeout=0.05)
    done.wait(timeout=0.01)
    queue.get(timeout=0.01)
    client.post.assert_called_once_with(url, timeout=0.2)
    await asyncio.sleep(0.01)
    monkeypatch.setenv('STT_TIMEOUT_SECONDS', 'off')

def test_fake_clock_is_exempt(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05

def test_injected_clock_is_exempt():
    fetch(timeout_seconds=0.1, clock=fake)

@freeze_time('2026-10-20')
def test_frozen_by_decorator_is_exempt():
    module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05

def test_real_clock_mapping_is_not_a_fake(monkeypatch):
    deps = {'monotonic': time.monotonic}
    module.AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS = 0.05

def test_clock_none_is_not_a_fake():
    fetch(timeout_seconds=0.2, clock=None)

def test_real_clock_via_new_is_not_a_fake():
    with patch.object(module, 'monotonic', new=time.monotonic):
        module.NEW_KW_TIMEOUT_SECONDS = 0.05

def test_parenthesized_real_clock_is_not_a_fake():
    fetch(timeout_seconds=0.3, clock=(time.monotonic))

def test_fake_clock_via_new_is_exempt():
    with patch.object(module, 'monotonic', new=lambda: 0.0):
        module.NEW_KW_TIMEOUT_SECONDS = 0.05

def test_more_spellings(monkeypatch):
    with patch.object(module, 'KW_TIMEOUT_SECONDS', new=0.02):
        pass
    module.PAREN_TIMEOUT_SECONDS = (0.05)
    with patch.dict('os.environ', {'STR_ENV_TIMEOUT': '0.02'}):
        pass
    with patch.dict(os.environ, KW_ENV_DEADLINE=' +0.03'):
        pass
    module.UNDERSCORE_BUDGET = 1_0e-2
'''


def test_scanner_flags_the_flaky_shapes_and_skips_harness_waits() -> None:
    found = scan_bytes('tests/unit/sample.py', _SAMPLE.encode('utf-8'))
    prefix = 'tests/unit/sample.py::'
    assert found == {
        prefix + '<module>::SYNC_JOB_HANDLER_BUDGET_SECONDS=0.05',
        prefix + 'test_flagged::REQUEST_TIMEOUT_SECONDS=0.02',
        prefix + 'test_flagged::DAILY_SUMMARY_USER_BUDGET_SECONDS=0.05',
        prefix + 'test_flagged::FIRST_EVENT_TIMEOUT_SECONDS=0.01',
        prefix + 'test_flagged::STT_ROUTING_REDIS_TIMEOUT_SECONDS=0.1',
        prefix + 'test_flagged::WINDOW_DEADLINE_SECONDS=0.2',
        prefix + 'test_flagged::PROBE_TIMEOUT=0.01',
        prefix + 'test_flagged::LIST_BUDGET=0.3',
        prefix + 'test_flagged::POST_TIMEOUT_SECONDS=0.05',
        prefix + 'test_flagged::timeout=0.1',
        prefix + 'TestShape.test_method::deadline_seconds=0.01',
        prefix + 'test_real_clock_mapping_is_not_a_fake::AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS=0.05',
        prefix + 'test_clock_none_is_not_a_fake::timeout_seconds=0.2',
        prefix + 'test_real_clock_via_new_is_not_a_fake::NEW_KW_TIMEOUT_SECONDS=0.05',
        prefix + 'test_parenthesized_real_clock_is_not_a_fake::timeout_seconds=0.3',
        prefix + 'test_more_spellings::KW_TIMEOUT_SECONDS=0.02',
        prefix + 'test_more_spellings::PAREN_TIMEOUT_SECONDS=0.05',
        prefix + 'test_more_spellings::STR_ENV_TIMEOUT=0.02',
        prefix + 'test_more_spellings::KW_ENV_DEADLINE=0.03',
        prefix + 'test_more_spellings::UNDERSCORE_BUDGET=0.1',
    }


@pytest.mark.parametrize(
    'snippet',
    [
        b'module.REQUEST_TIMEOUT_SECONDS = (0.05)',
        b'drain_tasks(tasks, timeout=(0.05))',
        b"patch('pkg.mod.LIST_BUDGET', new=(0.05))",
        b"monkeypatch.setenv('X_TIMEOUT', ' +0.05')",
        b'module.X_BUDGET = 1_0e-2',
        b"patch.object(module, 'X_TIMEOUT', new=0.02)",
    ],
)
def test_prefilter_admits_every_spelling_the_visitor_flags(snippet: bytes) -> None:
    assert _might_match(snippet)
    assert scan_bytes('x.py', snippet), snippet


def test_prefilter_matches_name_then_small_value_shapes_only() -> None:
    assert not _might_match(b'module.REQUEST_TIMEOUT_SECONDS = 5\nvalue = 0.05\n')
    assert _might_match(b'REQUEST_TIMEOUT_SECONDS: float = 0.05')
    assert _might_match(b"patch.dict(os.environ, {'POST_TIMEOUT_SECONDS': '0.05'})")
    assert _might_match(b"patch('pkg.mod.LIST_BUDGET', new=0.3)")
    assert not _might_match(b'TIMEOUT = 1.5')
    assert not _might_match(b'TIMEOUT = 10.05')
    assert _might_match(b'TIMEOUT = .05')
    assert _might_match(b"setattr(\n    module,\n    'X_TIMEOUT',\n    5e-2,\n)")


if __name__ == '__main__':
    allowed_keys = {entry for entry, _ in load_allowlist()}
    for key in sorted(scan_tree() - allowed_keys):
        print(f'{key}  # TODO(two-lane-lead): #22767 tiny real-clock budget; inject a fake clock or use >= 0.5 s')
    sys.exit(0)
