"""In-process Firestore billed-read snapshots and request-scoped read tracing."""

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import tomllib
from typing import Iterator

from database.firestore_document_probe import (
    FIRESTORE_BILLED_READS,
    FIRESTORE_BILLED_READS_BY_CALLER,
    install_document_read_probe,
)
from utils.observability.firestore_request_reads import (
    RequestReadTrace,
    bind_request_read_trace,
    reset_request_read_trace,
)

# Importing this test helper is an explicit installation boundary. Scenarios may
# construct firestore.Client directly without importing database._client.
install_document_read_probe()

_BUDGETS_PATH = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'firestore_read_budgets.toml'
_Labels = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ReadSnapshot:
    total: dict[_Labels, float]
    by_caller: dict[_Labels, float]


@dataclass(frozen=True)
class ReadDelta:
    reads: float
    by_caller: dict[str, float]


def _counter_values(counter) -> dict[_Labels, float]:
    metric = counter.collect()[0]
    total_name = f'{metric.name}_total'
    return {
        tuple(sorted(sample.labels.items())): float(sample.value)
        for sample in metric.samples
        if sample.name == total_name and sample.value
    }


def snapshot_reads() -> ReadSnapshot:
    """Capture both billed-read counters without creating missing label children."""
    return ReadSnapshot(
        total=_counter_values(FIRESTORE_BILLED_READS),
        by_caller=_counter_values(FIRESTORE_BILLED_READS_BY_CALLER),
    )


def _positive_delta(after: dict[_Labels, float], before: dict[_Labels, float]) -> dict[_Labels, float]:
    keys = before.keys() | after.keys()
    return {key: after.get(key, 0) - before.get(key, 0) for key in keys if after.get(key, 0) > before.get(key, 0)}


def delta_reads(before: ReadSnapshot) -> ReadDelta:
    """Measure reads since ``before`` and retain caller detail for failures."""
    after = snapshot_reads()
    total = _positive_delta(after.total, before.total)
    callers = _positive_delta(after.by_caller, before.by_caller)
    return ReadDelta(
        reads=sum(total.values()),
        by_caller={json.dumps(dict(labels), sort_keys=True): value for labels, value in callers.items()},
    )


def _budget_row(scenario: str) -> dict:
    with _BUDGETS_PATH.open('rb') as handle:
        rows = tomllib.load(handle)['scenario']
    matches = [row for row in rows if row['scenario'] == scenario]
    if len(matches) != 1:
        raise AssertionError(f'expected exactly one {scenario!r} read-budget row, found {len(matches)}')
    return matches[0]


def read_budget(scenario: str) -> tuple[int, str]:
    """Return ``(budget_reads, unit)`` for one reviewed scenario row."""
    row = _budget_row(scenario)
    return int(row['budget_reads']), row['unit']


def reads_for_caller(delta: ReadDelta, caller: str) -> float:
    return sum(reads for labels, reads in delta.by_caller.items() if json.loads(labels).get('caller') == caller)


def assert_read_budget(scenario: str, measured: float, delta: ReadDelta) -> None:
    """Fail with the scenario, measured value, budget and caller attribution."""
    row = _budget_row(scenario)
    budget, unit = int(row['budget_reads']), row['unit']
    assert measured <= budget, (
        f'{scenario}: measured {measured:g} Firestore reads exceeds budget {budget} per {unit}; '
        f'caller deltas={json.dumps(delta.by_caller, sort_keys=True)}'
    )
    for caller, ceiling in row.get('caller_budget_reads', {}).items():
        reads = reads_for_caller(delta, caller)
        assert 0 < reads <= ceiling, (
            f'{scenario}: expected {caller} to record between 1 and {ceiling} reads per {unit}; '
            f'measured {reads:g}; caller deltas={json.dumps(delta.by_caller, sort_keys=True)}'
        )


@contextmanager
def request_read_trace() -> Iterator[RequestReadTrace]:
    """Bind one request trace and close it before restoring the prior context."""
    trace = RequestReadTrace()
    token = bind_request_read_trace(trace)
    try:
        yield trace
    finally:
        with trace.lock:
            trace.closed = True
        reset_request_read_trace(token)
