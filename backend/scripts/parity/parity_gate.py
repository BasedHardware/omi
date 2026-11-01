#!/usr/bin/env python3
"""Parity gate for legacy-sync retirement (contract (j)). Writes ``parity_report.json``.

Surfaces:
  --surface staging      M2 verdict. Staging replay outputs vs the legacy baseline,
                         plus the quality corpus. Rows 1, 1b, 2, 3, 4, 5, 6 (throughput), 7, 8.
  --surface prod-shadow  M3 ladder holds from 25% (contract (g)). The gated prod cohort vs
                         the concurrent legacy population on rows 3-6 (aggregates, ro-prod).
                         Rows 1b/2 (replay half) on David's own recordings are evaluated when
                         --replay-dir is supplied; they are reported but do not gate ADVANCE.

Inputs are files produced by collectors; every one is optional and a missing
input makes its rows PENDING, never PASS:
  --corpus-scores  testing/quality_corpus/score.py output            (rows 1, 2)
  --replay-dir     <key>.batch.json / <key>.legacy.json word lists     (rows 1b, 2)
  --reviewed-outliers  JSON {"<key>": "<explanation ref>"}             (row 1b)
  --fleet-sample   captured fleet_gate.sh stdout                       (rows 3, 4)
  --legacy-baseline JSON {accept_to_summary_p95_seconds, ...}          (row 3)
  --census         JSON: row 4 counts, row 5 counts, rows 7/8 counts  (rows 4, 5, 7, 8)
  --cost           JSON: steady_hours, leases_per_min_per_node, batch/legacy $ parts (row 6)

Exit status: 0 PASS, 1 FAIL, 3 PENDING. The last stdout line is
``PARITY_PASS`` / ``PARITY_FAIL row_<n>`` / ``PARITY_PENDING <reason>``. A FAIL names
the failing row (contract (j)): the lowest data-loss row first (``row_5``, then
``row_7``, which the ramp controller maps to ROLLBACK_ZERO), otherwise the lowest
failing row. The specific ``ParityReason`` stays on the row and in the report, and a
data-loss FAIL also sets ``data_loss=true`` in the report.

Privacy: transcripts and labels are read into memory only; the report holds
counts, rates and opaque sha256-prefixed keys. No GCP access happens here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.parity import fleet_sample, rows  # noqa: E402
from scripts.parity.report_schema import (  # noqa: E402
    EXIT_CODES,
    PROD_SHADOW_GATING_ROWS,
    THRESHOLDS,
    ParityReason,
    ParityReport,
    Status,
    Surface,
    combine,
    verdict_line,
)
from scripts.parity.scorers import median, owner_agreement, percentile, word_errors, words_text  # noqa: E402


class InputError(Exception):
    """Fixed, content-free input errors only."""


def _load_json(path: Path | None) -> Any:
    if path is None:
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        raise InputError('input_unreadable') from None


def opaque_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _words(doc: Any) -> list[dict[str, Any]]:
    words = doc.get('words') if isinstance(doc, dict) else doc
    if not isinstance(words, list):
        raise InputError('replay_words_invalid')
    out = []
    for w in words:
        if not isinstance(w, dict) or 'start' not in w or 'end' not in w:
            raise InputError('replay_words_invalid')
        out.append(w)
    return out


def load_replay_pairs(directory: Path) -> dict[str, tuple[list, list]]:
    """``<key>.batch.json`` + ``<key>.legacy.json`` pairs; unpaired files are ignored."""
    pairs: dict[str, tuple[list, list]] = {}
    for batch_file in sorted(directory.glob('*.batch.json')):
        key = batch_file.name[: -len('.batch.json')]
        legacy_file = directory / f'{key}.legacy.json'
        if not legacy_file.exists():
            continue
        pairs[key] = (_words(_load_json(legacy_file)), _words(_load_json(batch_file)))
    return pairs


def replay_aggregates(pairs: Mapping[str, tuple[list, list]], reviewed: Mapping[str, str] | None = None) -> dict:
    """Rows 1b and 2 (replay half) from batch/legacy word pairs, aggregates only.

    1b: per-conversation WER of batch text against legacy text on the same audio.
    2:  owner-word agreement after optimal label mapping, pooled over words.
    ``reviewed`` keys may be raw or opaque keys; reviewed outliers > 25% pass.
    """
    reviewed = reviewed or {}
    reviewed_keys = set(reviewed) | {opaque_key(k) for k in reviewed}
    rates, outliers, reviewed_count = [], [], 0
    owner_conversations = owner_scored = owner_agree = 0
    for key, (legacy, batch) in pairs.items():
        errors, ref_words = word_errors(words_text(legacy), words_text(batch))
        if ref_words:
            rate = errors / ref_words
            rates.append(rate)
            if rate > THRESHOLDS.agreement_outlier_max:
                if key in reviewed_keys or opaque_key(key) in reviewed_keys:
                    reviewed_count += 1
                else:
                    outliers.append(opaque_key(key))
        agreement = owner_agreement(legacy, batch)
        if agreement['owner_known'] and agreement['owner_scored_words']:
            owner_conversations += 1
            owner_scored += agreement['owner_scored_words']
            owner_agree += agreement['owner_agree_words']
    return {
        'conversations': len(rates),
        'agreement_wer_median': median(rates),
        'agreement_wer_p95': percentile(rates, 95),
        'outliers_over_limit': len(outliers) + reviewed_count,
        'outliers_reviewed': reviewed_count,
        'outliers_unreviewed': len(outliers),
        'outlier_keys': sorted(outliers),
        'owner_conversations': owner_conversations,
        'owner_scored_words': owner_scored,
        'owner_agree_words': owner_agree,
    }


def evaluate(
    surface: Surface,
    *,
    corpus: Mapping[str, Any] | None = None,
    replay: Mapping[str, Any] | None = None,
    gate_sample: Mapping[str, Any] | None = None,
    legacy_baseline: Mapping[str, Any] | None = None,
    census: Mapping[str, Any] | None = None,
    cost: Mapping[str, Any] | None = None,
    window: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> ParityReport:
    row3_in = fleet_sample.row3_aggregates(gate_sample, legacy_baseline) if gate_sample else None
    row4_in = fleet_sample.row4_aggregates(gate_sample, census) if gate_sample else None
    results = [
        rows.row_1(corpus, surface),
        rows.row_1b(replay, surface),
        rows.row_2(corpus, replay, surface),
        rows.row_3(row3_in, surface),
        rows.row_4(row4_in, surface),
        rows.row_5(census, surface),
        rows.row_6(cost, surface),
        rows.row_7(census, surface),
        rows.row_8(census, surface),
    ]
    gating = PROD_SHADOW_GATING_ROWS if surface is Surface.PROD_SHADOW else None
    status, reason, data_loss, failing_row = combine(results, surface, gating)
    supported = rows.max_supported_percent(rows.finite((cost or {}).get('leases_per_min_per_node')))
    stamp = (now or dt.datetime.now(dt.timezone.utc)).isoformat().replace('+00:00', 'Z')
    return ParityReport(
        surface=surface,
        status=status,
        reason=reason,
        rows=tuple(results),
        generated_at=stamp,
        window=dict(window or {}),
        inputs=dict(inputs or {}),
        data_loss=data_loss,
        max_supported_percent=None if supported is None else round(supported, 1),
        failing_row=failing_row,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Parity gate for legacy-sync retirement (contract (j)).')
    parser.add_argument('--surface', required=True, choices=[s.value for s in Surface])
    # Contract (j) pins the prod-shadow invocation with no extra arguments.
    parser.add_argument('--output', type=Path, default=Path('parity_report.json'))
    parser.add_argument('--corpus-scores', type=Path)
    parser.add_argument('--replay-dir', type=Path)
    parser.add_argument('--reviewed-outliers', type=Path)
    parser.add_argument('--fleet-sample', type=Path, help='captured fleet_gate.sh stdout')
    parser.add_argument('--legacy-baseline', type=Path)
    parser.add_argument('--census', type=Path)
    parser.add_argument('--cost', type=Path)
    parser.add_argument('--window-start')
    parser.add_argument('--window-end')
    args = parser.parse_args(argv)
    surface = Surface(args.surface)
    try:
        replay = None
        if args.replay_dir is not None:
            if not args.replay_dir.is_dir():
                raise InputError('replay_dir_missing')
            reviewed = _load_json(args.reviewed_outliers) or {}
            replay = replay_aggregates(load_replay_pairs(args.replay_dir), reviewed)
        gate_sample, gate_status, gate_reason = None, None, None
        if args.fleet_sample is not None:
            try:
                lines = args.fleet_sample.read_text().splitlines()
            except OSError:
                raise InputError('fleet_sample_unreadable') from None
            gate_sample, gate_status, gate_reason = fleet_sample.parse_gate_output(lines)
        inputs = {
            'corpus_scores': bool(args.corpus_scores),
            'replay_conversations': None if replay is None else replay['conversations'],
            'fleet_gate_status': gate_status,
            'fleet_gate_reason': gate_reason,
            'fleet_gate_data_loss_token': fleet_sample.is_data_loss_token(gate_reason),
            'legacy_baseline': bool(args.legacy_baseline),
            'census': bool(args.census),
            'cost': bool(args.cost),
        }
        report = evaluate(
            surface,
            corpus=_load_json(args.corpus_scores),
            replay=replay,
            gate_sample=gate_sample,
            legacy_baseline=_load_json(args.legacy_baseline),
            census=_load_json(args.census),
            cost=_load_json(args.cost),
            window={'start': args.window_start, 'end': args.window_end},
            inputs=inputs,
        )
    except InputError as error:
        print(verdict_line('PARITY', Status.PENDING, ParityReason.INPUT_INVALID) + f' ({error})', flush=True)
        return EXIT_CODES[Status.PENDING]
    body = report.to_json()
    if replay is not None:
        body['replay_outlier_keys'] = replay['outlier_keys']
    args.output.write_text(json.dumps(body, indent=1, sort_keys=True) + '\n')
    for row in report.rows:
        print(f'row {row.row:>2} {row.status.value:<7} {row.reason.value}', flush=True)
    if report.max_supported_percent is not None:
        # Informational (no PARITY_ prefix): the ramp ceiling the measured throughput carries.
        print(f'max_supported_percent {report.max_supported_percent}', flush=True)
    print(verdict_line('PARITY', report.status, report.terminal_reason()), flush=True)
    return EXIT_CODES[report.status]


if __name__ == '__main__':
    sys.exit(main())
