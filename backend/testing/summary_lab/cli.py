"""CLI: run the synthetic matrix or compare two run JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testing.summary_lab.compare import compare_runs
from testing.summary_lab.fixtures import load_synthetic_fixtures
from testing.summary_lab.judge import JudgeReport
from testing.summary_lab.pricing import CostEstimate
from testing.summary_lab.render import render_lab_html
from testing.summary_lab.runner import CellResult, LabRun, run_matrix
from testing.summary_lab.seams import recorded_seam
from testing.summary_lab.variants import VARIANTS, VARIANTS_BY_ID, Variant


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _run_from_dict(payload: dict[str, object]) -> LabRun:
    raw_cells = payload.get('cells')
    if not isinstance(raw_cells, list):
        raise ValueError('run JSON missing cells')
    cells: list[CellResult] = []
    for raw in raw_cells:
        if not isinstance(raw, dict):
            continue
        judge_raw = raw.get('judge') or {}
        cost_raw = raw.get('cost') or {}
        if not isinstance(judge_raw, dict) or not isinstance(cost_raw, dict):
            continue
        note = raw.get('note') if isinstance(raw.get('note'), dict) else {}
        cells.append(
            CellResult(
                fixture_id=str(raw.get('fixture_id') or ''),
                variant_id=str(raw.get('variant_id') or ''),
                note=note if isinstance(note, dict) else {},
                judge=JudgeReport(
                    usefulness=float(judge_raw.get('usefulness') or 0),
                    defects=tuple(judge_raw.get('defects') or ()),
                    missing_facts=tuple(judge_raw.get('missing_facts') or ()),
                    filler_hits=int(judge_raw.get('filler_hits') or 0),
                    playback_hits=int(judge_raw.get('playback_hits') or 0),
                    speaker_leaks=int(judge_raw.get('speaker_leaks') or 0),
                ),
                cost=CostEstimate(
                    model=str(cost_raw.get('model') or ''),
                    input_tokens=int(cost_raw.get('input_tokens') or 0),
                    output_tokens=int(cost_raw.get('output_tokens') or 0),
                    usd=float(cost_raw.get('usd') or 0),
                ),
            )
        )
    return LabRun(cells=tuple(cells))


def _cmd_run(args: argparse.Namespace) -> int:
    fixtures = load_synthetic_fixtures(Path(args.fixtures) if args.fixtures else None)
    variant_ids = args.variant or [variant.id for variant in VARIANTS]
    variants: list[Variant] = []
    for variant_id in variant_ids:
        variant = VARIANTS_BY_ID.get(variant_id)
        if variant is None:
            raise SystemExit(f'unknown variant {variant_id!r}')
        variants.append(variant)
    summarize = recorded_seam
    if args.live:
        from testing.summary_lab.seams import production_notes_v2_seam

        summarize = production_notes_v2_seam
    run = run_matrix(fixtures, tuple(variants), summarize=summarize)
    out = Path(args.out)
    _write(out / 'run.json', json.dumps(run.as_dict(), indent=2, ensure_ascii=True) + '\n')
    _write(out / 'lab.html', render_lab_html(run))
    summary = f'cells={len(run.cells)} mean_usefulness={run.mean_usefulness:.3f} ' f'est_usd={run.total_usd:.5f}\n'
    _write(out / 'summary.txt', summary)
    print(summary, end='')
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    left = _run_from_dict(json.loads(Path(args.left).read_text(encoding='utf-8')))
    right = _run_from_dict(json.loads(Path(args.right).read_text(encoding='utf-8')))
    report = compare_runs(left, right)
    text = json.dumps(report.as_dict(), indent=2, ensure_ascii=True) + '\n'
    if args.out:
        _write(Path(args.out), text)
    print(text, end='')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='summary_lab', description='Conversation summary quality lab')
    sub = parser.add_subparsers(dest='command', required=True)

    run_parser = sub.add_parser('run', help='run the synthetic fixture matrix')
    run_parser.add_argument('--fixtures', help='directory of synthetic JSON fixtures')
    run_parser.add_argument('--variant', action='append', help='variant id (repeatable)')
    run_parser.add_argument('--out', required=True, help='output directory')
    run_parser.add_argument(
        '--live',
        action='store_true',
        help='call production get_conversation_notes (needs LLM credentials; not the default)',
    )
    run_parser.set_defaults(func=_cmd_run)

    compare_parser = sub.add_parser('compare', help='compare two run.json files')
    compare_parser.add_argument('--left', required=True)
    compare_parser.add_argument('--right', required=True)
    compare_parser.add_argument('--out')
    compare_parser.set_defaults(func=_cmd_compare)

    args = parser.parse_args(argv)
    return int(args.func(args))
