"""Ratchet: metric label arguments for reasons/outcomes/providers must be closed vocabularies.

Contract (e) of the backend target architecture. Every ``.labels(reason=...)``,
``.labels(outcome=...)``, ``.labels(provider=...)`` and ``.labels(retry_class=...)``
keyword argument must be one of:

- a string literal that follows the naming convention (``lower_snake``, <= 40 chars);
- a member (or ``.value``) of a reason enum from ``utils.observability.reasons``
  (a class whose name ends in ``Reason``/``Outcome``/``Stage``/``Family``);
- a call to ``reason_label(...)`` or another helper in ``CLOSED_HELPERS``: an
  explicit allowlist of functions reviewed to return a fixed vocabulary (folding
  unknown input to ``unknown``/``other``). A call counts only when its name is
  bound, by a local ``def`` or an import, to the allowlisted defining module; a
  name prefix such as ``bounded_`` proves nothing (some return exception text);
- a conditional or ``or`` of the above.

Anything else (a bare variable, ``str(exc)``, an f-string, a dict lookup, ...)
could carry free text into a label, so it is a violation. Today's offenders are
a shrink-only debt list in ``fixtures/reason_label_debt.json``, keyed by
(path, enclosing def, label keyword, argument shape) with a count, never line
numbers. The test fails when a violation appears or grows (use an enum and
``reason_label``) and when a debt entry is gone or shrank (lower or delete it).

Positional ``.labels('a', b)`` calls are not inspected (the metric definition is
needed to map positions); use keywords.

Regenerate (keeps existing ``why`` strings)::

    cd backend && python tests/unit/test_reason_label_enums.py --write
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter
from enum import StrEnum
from pathlib import Path

import pytest
from prometheus_client import REGISTRY

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.batch_pipeline.recovery_disposition import REASONS, STAGES, RecoveryFailure  # noqa: E402
from utils.observability import reasons  # noqa: E402
from utils.observability.reasons import LiveSttReason, ReasonFamily, reason_label  # noqa: E402
from utils.stt.live_reason import LIVE_STT_FAILURE_REASONS, LIVE_STT_REASONS, normalize_live_stt_reason  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEBT_PATH = BACKEND_DIR / 'tests' / 'unit' / 'fixtures' / 'reason_label_debt.json'
UNREVIEWED = 'pre-existing; unreviewed'

LABEL_KEYWORDS = frozenset({'reason', 'outcome', 'provider', 'retry_class'})
SKIPPED_TOP_LEVEL = frozenset({'tests', 'testing', 'scripts', '.venv', 'venv', 'node_modules', 'docs'})
_LITERAL = re.compile(r'[a-z][a-z0-9_]{0,39}', re.ASCII)
_ENUM_CLASS = re.compile(r'[A-Z]\w*(?:Reason|Outcome|Stage|Family)')
# Helpers reviewed to return a fixed vocabulary, keyed by defining module. Add one only after
# reading it: every return path must be a member of a closed set (or 'unknown'/'other').
CLOSED_HELPERS = frozenset(
    {
        'utils.observability.reasons.reason_label',
        'utils.stt.outcomes.bounded_provider',  # _KNOWN_PROVIDERS else 'unknown'
        'utils.stt.stream_close.bounded_stream_close_provider',  # STT_STREAM_CLOSE_PROVIDERS else 'unknown'
        'utils.stt.stream_close.bounded_stream_close_reason',  # STT_STREAM_CLOSE_REASONS else 'connection_lost'
        'utils.sync.wal_audio_coverage_metrics.bounded_reason',  # REASONS else 'other'
        'utils.sync.cap_hold_reservations._bounded_outcome',  # lane 8 cap-hold: OUTCOMES else 'unknown'
        'utils.translation_core.metrics._bounded_provider',  # fixed provider set else 'other'
        'utils.translation_core.metrics._bounded_reason',  # fixed skip-reason set else 'other'
    }
)


def backend_modules() -> list[Path]:
    paths = []
    for path in sorted(BACKEND_DIR.rglob('*.py')):
        parts = path.relative_to(BACKEND_DIR).parts
        if parts[0] in SKIPPED_TOP_LEVEL or any(part.startswith('.') for part in parts):
            continue
        paths.append(path)
    return paths


def bindings_for(tree: ast.Module, module: str) -> dict[str, str]:
    """Map each module-level name to the qualified object it is bound to (imports and local defs)."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = f'{module}.{node.name}'
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                out[alias.asname or alias.name] = f'{node.module}.{alias.name}'
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    out[alias.asname] = alias.name
    return out


def classify(node: ast.expr, bindings: dict[str, str] | None = None) -> str | None:
    """Return None when the argument is a closed vocabulary, else a short shape name."""
    bindings = bindings or {}
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return None if _LITERAL.fullmatch(node.value) else 'bad_literal'
        return 'non_string_constant'
    if isinstance(node, ast.IfExp):
        return classify(node.body, bindings) or classify(node.orelse, bindings)
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            shape = classify(value, bindings)
            if shape is not None:
                return shape
        return None
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            name, target = func.id, bindings.get(func.id)
        elif isinstance(func, ast.Attribute):
            base = bindings.get(func.value.id) if isinstance(func.value, ast.Name) else None
            name, target = func.attr, (f'{base}.{func.attr}' if base else None)
        else:
            name, target = '', None
        if target in CLOSED_HELPERS:
            return None
        return f'call:{name or "?"}'
    if isinstance(node, ast.Attribute):
        base = node.value
        if node.attr == 'value' and isinstance(base, ast.Attribute):
            base = base.value
        if isinstance(base, ast.Name) and _ENUM_CLASS.fullmatch(base.id):
            return None
        return 'attribute'
    if isinstance(node, ast.Name):
        return 'name'
    if isinstance(node, ast.JoinedStr):
        return 'fstring'
    if isinstance(node, ast.Subscript):
        return 'subscript'
    return type(node).__name__.lower()


class _Visitor(ast.NodeVisitor):
    def __init__(self, bindings: dict[str, str]) -> None:
        self.bindings = bindings
        self.scope: list[str] = []
        self.sites: Counter[tuple[str, str, str]] = Counter()

    def _enter(self, node: ast.AST) -> None:
        self.scope.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = visit_FunctionDef = visit_AsyncFunctionDef = _enter

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'labels':
            for keyword in node.keywords:
                if keyword.arg in LABEL_KEYWORDS:
                    shape = classify(keyword.value, self.bindings)
                    if shape is not None:
                        self.sites[('.'.join(self.scope) or '<module>', keyword.arg, shape)] += 1
        self.generic_visit(node)


def scan_source(source: str, module: str = '<source>') -> Counter[tuple[str, str, str]]:
    tree = ast.parse(source)
    visitor = _Visitor(bindings_for(tree, module))
    visitor.visit(tree)
    return visitor.sites


def scan() -> dict[tuple[str, str, str, str], int]:
    sites: dict[tuple[str, str, str, str], int] = {}
    for path in backend_modules():
        try:
            module = '.'.join(path.relative_to(BACKEND_DIR).with_suffix('').parts)
            counts = scan_source(path.read_text(encoding='utf-8'), module)
        except SyntaxError:
            continue
        relative = path.relative_to(BACKEND_DIR).as_posix()
        for (qualname, keyword, shape), count in counts.items():
            sites[(relative, qualname, keyword, shape)] = count
    return sites


def load_debt() -> dict[tuple[str, str, str, str], dict]:
    data = json.loads(DEBT_PATH.read_text(encoding='utf-8'))
    return {(e['path'], e['function'], e['label'], e['shape']): e for e in data['entries']}


def _describe(key: tuple[str, str, str, str]) -> str:
    return f'{key[0]}::{key[1]} .labels({key[2]}=<{key[3]}>)'


@pytest.fixture(scope='module')
def scanned():
    return scan()


def test_label_arguments_match_debt_list(scanned):
    debt = load_debt()
    problems = []
    for key, count in sorted(scanned.items()):
        allowed = debt.get(key, {}).get('count', 0)
        if count > allowed:
            problems.append(
                f'NEW {_describe(key)} count {count} > debt {allowed}: pass a member of a reason enum '
                f'(utils/observability/reasons.py) through reason_label(), or a CLOSED_HELPERS helper.'
            )
    for key, entry in sorted(debt.items()):
        if scanned.get(key, 0) < entry['count']:
            problems.append(
                f'STALE {_describe(key)} debt count {entry["count"]} > current {scanned.get(key, 0)}: '
                f'lower or delete the entry in {DEBT_PATH.relative_to(BACKEND_DIR)}.'
            )
    assert not problems, '\n'.join(problems)


def test_every_debt_entry_has_a_reason():
    for key, entry in load_debt().items():
        assert isinstance(entry.get('why'), str) and entry['why'].strip(), _describe(key)
        assert isinstance(entry.get('count'), int) and entry['count'] > 0, _describe(key)


def test_classifier_accepts_closed_and_rejects_free_text():
    source = '''
from utils.observability.reasons import reason_label
from utils.stt.outcomes import bounded_provider
import utils.stt.stream_close as close

def f(exc, reason, family):
    A.labels(reason='timeout')
    A.labels(reason=LiveSttReason.TIMEOUT.value)
    A.labels(reason=RampReason.GATE_PASS)
    A.labels(outcome=reason_label(family, reason, LiveSttReason))
    A.labels(provider=bounded_provider(reason))
    A.labels(reason=close.bounded_stream_close_reason(reason))
    A.labels(outcome='ok' if reason else 'failed')
    A.labels(reason=reason)
    A.labels(reason=str(exc))
    A.labels(reason=f'err_{reason}')
    A.labels(reason='Has Spaces')
    A.labels(reason=exc.reason)
    A.labels(reason=MAP[reason])
    A.labels(reason=reason or 'unknown')
    A.labels(component=reason)
'''
    assert dict(scan_source(source)) == {
        ('f', 'reason', 'name'): 2,
        ('f', 'reason', 'call:str'): 1,
        ('f', 'reason', 'fstring'): 1,
        ('f', 'reason', 'bad_literal'): 1,
        ('f', 'reason', 'attribute'): 1,
        ('f', 'reason', 'subscript'): 1,
    }


def test_classifier_rejects_prefix_named_helpers_outside_the_allowlist():
    """`bounded_*`/`_bounded_*` is a naming habit, not a guarantee: these return exception text."""
    source = '''
from utils.sync.telemetry import bounded_exception_reason
from utils.llm.gateway_error_contract import _bounded_error_text
from utils.observability.reasons import reason_label_from_exc

def _bounded_outcome(exc):
    return str(exc)

def f(exc):
    A.labels(reason=bounded_exception_reason(exc))
    A.labels(reason=_bounded_error_text(exc))
    A.labels(reason=reason_label_from_exc(exc))
    A.labels(outcome=_bounded_outcome(exc))
    A.labels(reason=bucket_reason(exc))
'''
    assert dict(scan_source(source, 'utils.example')) == {
        ('f', 'reason', 'call:bounded_exception_reason'): 1,
        ('f', 'reason', 'call:_bounded_error_text'): 1,
        ('f', 'reason', 'call:reason_label_from_exc'): 1,
        ('f', 'outcome', 'call:_bounded_outcome'): 1,
        ('f', 'reason', 'call:bucket_reason'): 1,
    }
    # The same local helper is closed only in its reviewed defining module.
    assert not scan_source(source.replace('    A.labels(reason=', '    # '), 'utils.sync.cap_hold_reservations')


def test_every_closed_helper_exists_where_the_allowlist_says():
    for qualified in sorted(CLOSED_HELPERS):
        module, _, name = qualified.rpartition('.')
        tree = ast.parse((BACKEND_DIR / (module.replace('.', '/') + '.py')).read_text(encoding='utf-8'))
        assert any(isinstance(node, ast.FunctionDef) and node.name == name for node in tree.body), qualified


def test_reason_enums_follow_the_naming_convention():
    enums = [v for v in vars(reasons).values() if isinstance(v, type) and issubclass(v, StrEnum) and v is not StrEnum]
    assert enums
    for enum in enums:
        assert re.fullmatch(r'[A-Z]\w*(?:Reason|Outcome|Stage|Family)', enum.__name__), enum.__name__
        if enum is reasons.ReasonFamily:
            continue
        assert enum.UNKNOWN.value == 'unknown', enum.__name__
        for member in enum:
            assert _LITERAL.fullmatch(member.value), f'{enum.__name__}.{member.name}={member.value!r}'


def test_reason_label_counts_unknown_without_raising():

    def unknown_count() -> float:
        return REGISTRY.get_sample_value('omi_reason_unknown_total', {'family': 'live_stt'}) or 0.0

    before = unknown_count()
    assert reason_label(ReasonFamily.LIVE_STT, 'timeout', LiveSttReason) == 'timeout'
    assert reason_label(ReasonFamily.LIVE_STT, LiveSttReason.CANCELLED, LiveSttReason) == 'cancelled'
    assert reason_label(ReasonFamily.LIVE_STT, 'unknown', LiveSttReason) == 'unknown'
    assert unknown_count() == before
    assert reason_label(ReasonFamily.LIVE_STT, 'ConnectionError: private', LiveSttReason) == 'unknown'
    assert reason_label(ReasonFamily.LIVE_STT, None, LiveSttReason) == 'unknown'
    assert reason_label(ReasonFamily.LIVE_STT, object(), LiveSttReason) == 'unknown'
    assert unknown_count() == before + 3


def test_migrated_constants_are_unchanged_and_misses_are_counted():

    assert len(LIVE_STT_REASONS) == 33 and LIVE_STT_REASONS == LIVE_STT_FAILURE_REASONS | {'text', 'no_text'}
    assert 'unknown' not in LIVE_STT_REASONS and {'cancelled', 'replay_ring_overflow'} <= LIVE_STT_FAILURE_REASONS

    def count(family: str) -> float:
        return REGISTRY.get_sample_value('omi_reason_unknown_total', {'family': family}) or 0.0

    assert 'unknown' not in REASONS and 'operation_failed' in REASONS and 'provider' in STAGES
    live_before, recovery_before = count('live_stt'), count('recovery_failure')
    assert normalize_live_stt_reason(None, 'free text diagnostic') == 'connection_lost'
    assert normalize_live_stt_reason(None, None) == 'connection_lost'
    assert normalize_live_stt_reason('timeout') == 'timeout'
    assert count('live_stt') == live_before + 1
    failure = RecoveryFailure('not_a_stage', 'not a reason')
    assert (failure.stage, failure.reason) == ('provider', 'operation_failed')
    assert count('recovery_failure') == recovery_before + 1


def test_live_stt_unknown_ratio_counts_every_normalization():
    """L14-1: hits feed omi_reason_total too, so a rare free-text fold is not a ratio of ~1."""

    def sample(name: str) -> float:
        return REGISTRY.get_sample_value(name, {'family': 'live_stt'}) or 0.0

    total_before, unknown_before = sample('omi_reason_total'), sample('omi_reason_unknown_total')
    assert normalize_live_stt_reason('timeout') == 'timeout'
    assert (sample('omi_reason_total'), sample('omi_reason_unknown_total')) == (total_before + 1, unknown_before)
    for _ in range(98):
        normalize_live_stt_reason(None, 'connection_lost')
    assert normalize_live_stt_reason(None, 'ws send closed: 1006') == 'connection_lost'
    total, unknown = sample('omi_reason_total') - total_before, sample('omi_reason_unknown_total') - unknown_before
    assert (total, unknown) == (100, 1)
    assert unknown / total < 0.02


def _write_debt() -> None:
    previous = load_debt() if DEBT_PATH.exists() else {}
    entries = [
        {
            'path': key[0],
            'function': key[1],
            'label': key[2],
            'shape': key[3],
            'count': count,
            'why': previous.get(key, {}).get('why', UNREVIEWED),
        }
        for key, count in sorted(scan().items())
    ]
    DEBT_PATH.write_text(json.dumps({'entries': entries}, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {len(entries)} entries ({sum(e["count"] for e in entries)} sites) to {DEBT_PATH}')


if __name__ == '__main__':
    if sys.argv[1:] == ['--write']:
        _write_debt()
    else:
        raise SystemExit(f'usage: {sys.argv[0]} --write')
