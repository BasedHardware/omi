"""Sanitized stage recorder and product outcome / reproduction expectation report."""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any


@dataclass
class StageResult:
    stage: str
    status: str
    duration_ms: float = 0
    reason: str | None = None
    exception_type: str | None = None
    site: str | None = None
    operation: str | None = None
    transaction: str | None = None
    guard: str | None = None
    budget: str | None = None
    missing_input: str | None = None
    observations: list[dict[str, str]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def record_exception(error: BaseException, stage: str, *, operation=None, transaction=None) -> dict[str, str]:
    """Only code identities leave this boundary; never messages or traceback text."""
    tb = error.__traceback__
    site = stage
    retained_capture = False
    while tb:
        frame = tb.tb_frame
        site = f"{frame.f_globals.get('__name__', 'unknown')}.{frame.f_code.co_name}"
        # Identify the specific static raise instruction without reading its
        # runtime message (which could contain captured customer content).
        if site == 'utils.batch_pipeline.live.admit_recording':
            import linecache

            retained_capture = 'raise ValueError(\'retained capture not durable yet\')' in linecache.getline(
                frame.f_code.co_filename, tb.tb_lineno
            )
        tb = tb.tb_next
    kind = type(error).__name__
    if operation is not None and operation not in {'admit', 'due', 'defer', 'read_pending', 'verify', 'driver'}:
        raise ValueError('unknown replay operation')
    reason = f'{stage}:{operation}:{kind}:{site}' if operation else f'{stage}:{kind}:{site}'
    if transaction:
        reason += f':transaction={transaction}'
    if retained_capture and kind == 'ValueError':
        reason += ':retained_capture_not_durable'
    result = {'reason': reason, 'exception_type': kind, 'site': site}
    if operation:
        result['operation'] = operation
    if transaction:
        result['transaction'] = transaction
    return result


def item_report(manifest, stages: list[StageResult]) -> dict:
    stopped = next((s for s in stages if s.status != 'pass'), None)
    expectation_met = not any(s.status == 'not_implemented' for s in stages)
    observed = {s.stage: s for s in stages}
    for name, expectation in manifest.stages.items():
        result = observed.get(name)
        if result is None or result.status == 'not_implemented':
            expectation_met = False
        elif expectation.get('expect') == 'pass':
            expectation_met &= result.status == 'pass'
        else:
            # Include a static allowlisted label for the §6 human-readable seed
            # pattern; arbitrary exception messages are never searched or saved.
            reasons = [o['reason'] for o in result.observations] + [result.reason or '']
            if any(r.endswith(':retained_capture_not_durable') for r in reasons):
                reasons.append('ValueError:retained capture not durable yet')
            expectation_met &= result.status == 'stopped' and any(
                re.search(expectation['expect_reason'], r) is not None for r in reasons
            )
    return {
        'item': manifest.id,
        'tier': manifest.tier,
        'scrub': manifest.scrub,
        'notes': manifest.notes,
        'stages': [asdict(s) for s in stages],
        'furthest_stage': stages[-1].stage if stages else None,
        'stop_reason': stopped.reason if stopped else None,
        'duration_ms': round(sum(s.duration_ms for s in stages), 3),
        'verdict': 'FAIL' if stopped else 'PASS',
        'expectation_met': bool(expectation_met),
        'expectation_verdict': 'PASS' if expectation_met else 'FAIL',
    }


def table(items: list[dict]) -> str:
    rows = ['| item | furthest stage | stop reason | duration | verdict | expectation |', '|---|---|---|---:|---|---|']
    for item in items:
        reason = (item['stop_reason'] or '—').replace('|', '\\|').replace('\n', ' ')
        rows.append(
            f"| {item['item']} | {item['furthest_stage']} | {reason} | "
            f"{item['duration_ms'] / 1000:.3f}s | {item['verdict']} | {item['expectation_verdict']} |"
        )
    return '\n'.join(rows)


def write_report(items: list[dict], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in items:
        (output / f"{item['item']}.json").write_text(json.dumps(item, indent=2) + '\n')
    (output / 'report.json').write_text(json.dumps({'schema_version': 1, 'items': items}, indent=2) + '\n')
    (output / 'report.md').write_text(table(items) + '\n')
