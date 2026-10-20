#!/usr/bin/env python3
"""D2 edge shadow gate over listen-edge's Prometheus metrics.

Reads one or two scrapes of listen-edge ``/metrics`` (text format). With two,
the gate is computed over the counter deltas (the hold window). Reports VAD
window agreement per codec and variant, the gate-open offset p95 and the
edge's decode+VAD time per mirrored audio second, and checks plan D's D2 gate:

- window agreement >= 99.5% over compared windows (agree / (agree + disagree));
- coverage >= 95%: compared windows over all listen windows (not_comparable and unmatched
  ones, e.g. failover gates, are outside the ratio and must stay small);
- gate-open offset p95 <= 32 ms;
- edge decode+VAD <= 7.92 ms per audio second (6.6 ms/s within 20%).

Usage:
    python scripts/edge_shadow_gate.py after.prom [--before before.prom]

Exit status is non-zero when a gate fails or nothing was compared.
"""

import argparse
import math
import re
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

AGREEMENT_GATE = 0.995
# Windows from later listen gates (failover replacements) and unmatched ones
# are outside the agreement ratio; they must stay a small share of the total.
COVERAGE_GATE = 0.95
OPEN_OFFSET_P95_GATE_MS = 32.0
EDGE_MS_PER_AUDIO_SECOND_GATE = 6.6 * 1.2

_SAMPLE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(\S+)$')
_LABEL = re.compile(r'(\w+)="([^"]*)"')

Series = Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float]


def parse(text: str) -> Series:
    out: Series = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        m = _SAMPLE.match(line.strip())
        if not m:
            continue
        labels = tuple(sorted(_LABEL.findall(m.group(2) or '')))
        try:
            out[(m.group(1), labels)] = float(m.group(3))
        except ValueError:
            continue
    return out


class CounterReset(ValueError):
    """A counter went down between scrapes (pod restart); the delta is meaningless."""


def delta(after: Series, before: Optional[Series]) -> Series:
    if before is None:
        return after
    out: Series = {}
    for k, v in after.items():
        d = v - before.get(k, 0.0)
        if d < 0 and k[0].endswith(('_total', '_count', '_sum', '_bucket')):
            raise CounterReset(f'{k[0]} went down between scrapes; scrape one pod across the hold')
        out[k] = d
    return out


def p95(values: Sequence[float]) -> float:
    """Nearest-rank p95; 0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def histogram_quantile(series: Series, name: str, q: float) -> Optional[float]:
    """Upper bound of the bucket holding quantile ``q`` (conservative)."""
    buckets = sorted(
        (float(dict(labels)['le']), v)
        for (n, labels), v in series.items()
        if n == f'{name}_bucket' and dict(labels).get('le') not in (None, '+Inf')
    )
    total = series.get((f'{name}_count', ()), 0.0)
    if total <= 0:
        return None
    for le, count in buckets:
        if count >= q * total:
            return le
    return math.inf


def evaluate(series: Series) -> Tuple[bool, List[str]]:
    lines: List[str] = []
    compare: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for (name, labels), v in series.items():
        if name == 'omi_edge_shadow_window_compare_total':
            d = dict(labels)
            compare[(d['codec'], d['variant'])][d['result']] += v

    agreed = compared = 0.0
    for (codec, variant), r in sorted(compare.items()):
        a = r['agree_speech'] + r['agree_silence']
        n = a + r['edge_speech_only'] + r['listen_speech_only']
        agreed += a
        compared += n
        if n or r['not_comparable'] or r['unmatched']:
            lines.append(
                f'{codec:6} {variant:5} compared {n:10.0f} agreement {a / n if n else float("nan"):.4%} '
                f'edge_only {r["edge_speech_only"]:.0f} listen_only {r["listen_speech_only"]:.0f} '
                f'not_comparable {r["not_comparable"]:.0f} unmatched {r["unmatched"]:.0f}'
            )
    uncovered = sum(r['not_comparable'] + r['unmatched'] for r in compare.values())
    coverage = compared / (compared + uncovered) if compared + uncovered else 0.0
    agreement = agreed / compared if compared else 0.0
    open_p95 = histogram_quantile(series, 'omi_edge_shadow_gate_open_offset_seconds', 0.95)
    processing = sum(v for (n, _), v in series.items() if n == 'omi_edge_shadow_processing_seconds_total')
    audio = sum(v for (n, _), v in series.items() if n == 'omi_edge_shadow_audio_seconds_total')
    ms_per_s = processing * 1000 / audio if audio else 0.0

    agree_ok = compared > 0 and agreement >= AGREEMENT_GATE
    coverage_ok = compared > 0 and coverage >= COVERAGE_GATE
    open_ok = open_p95 is not None and open_p95 * 1000 <= OPEN_OFFSET_P95_GATE_MS
    cpu_ok = audio > 0 and ms_per_s <= EDGE_MS_PER_AUDIO_SECOND_GATE
    lines.append(
        f'agreement {agreement:.4%} over {compared:.0f} windows: {"PASS" if agree_ok else "FAIL"} '
        f'(>= {AGREEMENT_GATE:.1%})'
    )
    lines.append(
        f'coverage {coverage:.2%} (compared / all listen windows, rest not_comparable or unmatched): '
        f'{"PASS" if coverage_ok else "FAIL"} (>= {COVERAGE_GATE:.0%})'
    )
    lines.append(
        f'gate-open offset p95 <= {"n/a" if open_p95 is None else f"{open_p95 * 1000:.0f}"} ms: '
        f'{"PASS" if open_ok else "FAIL"} (<= {OPEN_OFFSET_P95_GATE_MS:.0f} ms)'
    )
    lines.append(
        f'edge decode+VAD {ms_per_s:.2f} ms per audio second: {"PASS" if cpu_ok else "FAIL"} '
        f'(<= {EDGE_MS_PER_AUDIO_SECOND_GATE:.2f})'
    )
    return agree_ok and coverage_ok and open_ok and cpu_ok, lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('after', help='listen-edge /metrics scrape at the end of the hold')
    parser.add_argument('--before', help='scrape at the start of the hold (gate over the delta)')
    args = parser.parse_args()
    with open(args.after) as f:
        after = parse(f.read())
    before = None
    if args.before:
        with open(args.before) as f:
            before = parse(f.read())
    try:
        series = delta(after, before)
    except CounterReset as reset:
        print(f'GATE FAIL: {reset}')
        return 2
    ok, lines = evaluate(series)
    print('\n'.join(lines))
    print('GATE', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
