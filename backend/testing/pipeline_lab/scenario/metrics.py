"""Per-arm metrics for ``scenario compare``: a small registry of extractors (stdlib only).

An extractor reads one arm's run directory (the ``scenario run`` layout of ``scenario/verdict.py``:
``run.json``, ``verdict.json``, ``<scenario>/result.json``) and returns flat numbers or short labels::

    from pathlib import Path

    from testing.pipeline_lab.scenario.metrics import register_metric, scenario_results


    @register_metric('speakers', description='speaker attribution per scenario')
    def speaker_metrics(run_dir: Path) -> dict[str, int | float | str]:
        out = {}
        for name, result in scenario_results(run_dir):
            out[f'{name}.attributed'] = ...
        return out

``scenario compare`` imports every ``compare_metrics.py`` module under ``testing/pipeline_lab/`` (any depth)
and every module named in ``$OMI_PIPELINE_LAB_METRICS`` (comma separated) before it extracts, so a lane adds
a metric by adding that file: compare.py does not change. Each arm gets a row per key (``<metric>.<key>``),
and every arm other than the baseline a delta against it (:func:`delta`).

Values are numbers or short labels, never text from a run: no transcript, title, name, uid or conversation
id (lab ``AGENTS.md``, Privacy). An extractor that raises, or returns anything but a mapping of string keys to
``int``/``float``/``str``, is an error of that arm's metric: compare reports it and exits 2.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence, Union

MetricValue = Union[int, float, str]
Extractor = Callable[[Path], Mapping[str, MetricValue]]

METRICS_ENV = 'OMI_PIPELINE_LAB_METRICS'
MODULE_NAME = 'compare_metrics'
LAB_DIR = Path(__file__).resolve().parents[1]
LAB_PACKAGE = 'testing.pipeline_lab'
MAX_LABEL = 80  # a string value is a label (an outcome, a mode), not text


class MetricError(ValueError):
    """A metric that cannot be registered or loaded."""


@dataclass(frozen=True)
class Metric:
    name: str
    extractor: Extractor
    description: str = ''


_REGISTRY: dict[str, Metric] = {}


def register_metric(
    name: str, extractor: Optional[Extractor] = None, *, description: str = '', replace: bool = False
) -> Any:
    """Register ``extractor(run_dir) -> {key: number | str}`` as metric ``name``. Usable as a decorator
    (``@register_metric('x')``) or a call (``register_metric('x', fn)``); returns the extractor. A second
    registration of the same name is an error unless ``replace`` (re-importing the same module is not)."""
    if not isinstance(name, str) or not name or '.' in name or name != name.strip():
        raise MetricError(f'metric name {name!r}: a non-empty name without dots or edge spaces')

    def add(fn: Extractor) -> Extractor:
        if not callable(fn):
            raise MetricError(f'metric {name}: the extractor is not callable')
        current = _REGISTRY.get(name)
        same = current is not None and _origin(current.extractor) == _origin(fn)
        if current is not None and not (replace or same):
            raise MetricError(f'metric {name} is already registered by {_origin(current.extractor)}')
        _REGISTRY[name] = Metric(name, fn, description)
        return fn

    return add if extractor is None else add(extractor)


def unregister_metric(name: str) -> None:
    _REGISTRY.pop(name, None)


def registered() -> dict[str, Metric]:
    return dict(sorted(_REGISTRY.items()))


def _origin(fn: Any) -> str:
    return f'{getattr(fn, "__module__", "?")}.{getattr(fn, "__qualname__", repr(fn))}'


# ---- discovery -----------------------------------------------------------------------------------


def metric_modules(env: Optional[Mapping[str, str]] = None, lab_dir: Path = LAB_DIR) -> list[str]:
    """Every ``compare_metrics.py`` under the lab package (sorted), then ``$OMI_PIPELINE_LAB_METRICS``."""
    env = os.environ if env is None else env
    found = []
    for path in sorted(lab_dir.rglob(f'{MODULE_NAME}.py')):
        relative = path.relative_to(lab_dir).with_suffix('')
        if '__pycache__' in relative.parts:
            continue
        found.append('.'.join((LAB_PACKAGE, *relative.parts)))
    extra = [name.strip() for name in (env.get(METRICS_ENV) or '').split(',') if name.strip()]
    return found + [name for name in extra if name not in found]


def load_metric_modules(modules: Optional[Sequence[str]] = None) -> list[str]:
    """Import each module (registering its metrics); a module that fails to import is an error, never skipped."""
    names = list(metric_modules() if modules is None else modules)
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - re-raised with the module named
            raise MetricError(f'metric module {name} failed to import: {type(error).__name__}: {error}') from error
    return names


# ---- extraction and deltas ---------------------------------------------------------------------------


def _valid(value: Any) -> bool:
    if isinstance(value, bool):
        return False  # a flag is reported as 0/1 or a label, so a delta is always defined
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and len(value) <= MAX_LABEL


def extract(run_dir: Path, names: Optional[Sequence[str]] = None) -> tuple[dict[str, MetricValue], dict[str, str]]:
    """``({"<metric>.<key>": value}, {metric: error})`` for one arm's run directory."""
    metrics = registered()
    chosen = list(metrics) if names is None else list(names)
    values: dict[str, MetricValue] = {}
    errors: dict[str, str] = {}
    for name in chosen:
        metric = metrics.get(name)
        if metric is None:
            errors[name] = 'not registered'
            continue
        try:
            out = metric.extractor(Path(run_dir))
        except Exception as error:  # noqa: BLE001 - reported per arm and metric, compare exits 2
            errors[name] = f'{type(error).__name__}: {error}'[:300]
            continue
        if not isinstance(out, Mapping):
            errors[name] = f'returned {type(out).__name__}, not a mapping'
            continue
        bad = [str(k) for k, v in out.items() if not isinstance(k, str) or not k or not _valid(v)]
        if bad:
            errors[name] = f'invalid key or value (numbers or labels of at most {MAX_LABEL} chars): {bad[:5]}'
            continue
        for key in sorted(out):
            values[f'{name}.{key}'] = out[key]
    return values, errors


def delta(baseline: Optional[MetricValue], value: Optional[MetricValue]) -> Optional[MetricValue]:
    """``value - baseline`` for two numbers (rounded to 6 places); ``"same"``/``"changed"`` for labels;
    ``None`` when either side is missing or one is a number and the other a label."""
    if baseline is None or value is None:
        return None
    numeric = (isinstance(baseline, (int, float)), isinstance(value, (int, float)))
    if all(numeric):
        diff = value - baseline  # type: ignore[operator]
        return diff if isinstance(diff, int) else round(diff, 6)
    if any(numeric):
        return None
    return 'same' if baseline == value else 'changed'


def table(
    values: Mapping[str, Mapping[str, MetricValue]], baseline: str
) -> tuple[list[str], dict[str, dict[str, Optional[MetricValue]]]]:
    """``(keys, deltas)``: every key any arm reported (sorted) and each non-baseline arm's delta per key."""
    keys = sorted({key for row in values.values() for key in row})
    base = values.get(baseline) or {}
    deltas = {
        arm: {key: delta(base.get(key), row.get(key)) for key in keys} for arm, row in values.items() if arm != baseline
    }
    return keys, deltas


# ---- helpers for extractors ----------------------------------------------------------------------------


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def scenario_results(run_dir: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """``(name, result.json)`` of each scenario the arm ran, in ``verdict.json`` order (repeat 1 only);
    a scenario whose result.json is unreadable gives ``{}``."""
    run_dir = Path(run_dir)
    verdict = _read(run_dir / 'verdict.json') or {}
    for row in verdict.get('scenarios') or []:
        name = str(row.get('name'))
        result = _read(run_dir / name / 'result.json')
        yield name, result if isinstance(result, dict) else {}


def verdict_rows(run_dir: Path) -> list[dict[str, Any]]:
    verdict = _read(Path(run_dir) / 'verdict.json') or {}
    return [row for row in verdict.get('scenarios') or [] if isinstance(row, dict)]


# ---- built-in metrics -------------------------------------------------------------------------------

OPS_KEYS = ('reads', 'writes', 'deletes', 'noop_writes')
# scenario/checks.py OUTCOMES, every one reported (0 included) so each arm has the same keys.
OUTCOME_KEYS = ('passed', 'xfail', 'failed', 'xpass', 'nondeterministic', 'error')
VENDOR_KEYS = ('stt', 'llm')


@register_metric('ops', description='operation counts summed over the arm\'s scenarios (scenario/budget.py)')
def ops_totals(run_dir: Path) -> dict[str, MetricValue]:
    totals = {key: 0 for key in (*OPS_KEYS, *(f'vendor_{k}' for k in VENDOR_KEYS))}
    for row in verdict_rows(run_dir):
        ops = row.get('ops') or {}
        for key in OPS_KEYS:
            totals[key] += int(ops.get(key) or 0)
        vendor = ops.get('vendor_calls') or {}
        for key in VENDOR_KEYS:
            totals[f'vendor_{key}'] += int(vendor.get(key) or 0)
    return totals


@register_metric('outcomes', description='scenarios per outcome, and checks passed')
def outcome_counts(run_dir: Path) -> dict[str, MetricValue]:
    out: dict[str, MetricValue] = {key: 0 for key in OUTCOME_KEYS}
    out.update(checks_passed=0, checks=0)
    for row in verdict_rows(run_dir):
        key = str(row.get('outcome') or 'error')
        out[key] = int(out.get(key, 0)) + 1
        checks = row.get('checks') or []
        out['checks'] = int(out['checks']) + len(checks)
        out['checks_passed'] = int(out['checks_passed']) + sum(1 for check in checks if check.get('passed'))
    return out
