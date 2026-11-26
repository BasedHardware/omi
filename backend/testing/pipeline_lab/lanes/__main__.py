"""Ingest commands. ``python -m testing.pipeline_lab record-stt ...`` routes here through the
plugin; this module also runs on its own (and is what the ``transcribe`` stage runs in the arm):

    python -m testing.pipeline_lab.lanes timeline --day DAY [--vad]
    python -m testing.pipeline_lab.lanes record-stt --day DAY --adapter prerecorded|parakeet_batch \
        [--provider P] --model M [--language L] --budget-usd 1.0 [--sync-exact]   # the only billable command
    python -m testing.pipeline_lab.lanes replay --day DAY --run RUN --provider P --model M \
        [--sync-mode span|exact] [--streaming-via sync|record|none]

Paths come from ``OMI_PIPELINE_LAB_ROOT``. JSON summary on stdout.

``record-stt`` records one conversation-level cassette per conversation by default (``span``
mode for both lanes, RULINGS 13); ``--sync-exact`` records per VAD file for sync captures
instead. Spend goes through core's persistent ledger under ``$ROOT/stt_records/<id>/`` with
the vendor log beside it, so the cap holds across invocations of the same record id.
Streaming captures replay through the sync driver as a labelled stand-in until M3 (RULINGS 14).
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _record(args: argparse.Namespace) -> dict:
    from testing.pipeline_lab.cassette.adapters import make_adapter
    from testing.pipeline_lab.cassette.recorder import Recorder
    from testing.pipeline_lab.contracts import utc_iso
    from testing.pipeline_lab.lanes.day import record_day_cassettes
    from testing.pipeline_lab.ledger import SpendLedger
    from testing.pipeline_lab.store import atomic_write_json, ensure_private_dir, lab_root, private_subdir, safe_segment

    root = ensure_private_dir(lab_root())  # refuses a root inside git, a foreign or an open directory
    safe_segment(args.day, 'day id')
    record_id = safe_segment(args.record_id or f'{args.day}-{args.adapter}', 'record id')
    directory = private_subdir(root / 'stt_records' / record_id)
    options = {'window_seconds': args.window_seconds} if args.adapter == 'parakeet_batch' else {}
    adapter = make_adapter(args.adapter, provider=args.provider, model=args.model, **options)
    ledger = SpendLedger(directory / 'ledger.json', budget_usd=args.budget_usd)
    recorder = Recorder(adapter, ledger, vendor_log=directory / 'vendor_log.jsonl', root=root)
    summary = record_day_cassettes(
        args.day,
        recorder,
        language=args.language,
        vocabulary=tuple(v for v in args.vocabulary.split(',') if v),
        sync_exact=args.sync_exact,
        root=root,
    )
    summary.update(
        record_id=record_id,
        adapter=adapter.name,
        provider=adapter.provider,
        model=adapter.model,
        mode='exact' if args.sync_exact else 'span',
        spend=ledger.snapshot(),
    )
    atomic_write_json(directory / 'record.json', {**summary, 'day_id': args.day, 'at': utc_iso()})
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.lanes')
    sub = parser.add_subparsers(dest='command', required=True)
    t = sub.add_parser('timeline')
    t.add_argument('--day', required=True)
    t.add_argument('--vad', action='store_true', help='also run local Silero VAD over every clip')
    for name in ('record-stt', 'replay'):
        p = sub.add_parser(name)
        p.add_argument('--day', required=True)
        p.add_argument('--provider', default=None)
        p.add_argument('--model', default=None)
        p.add_argument('--language', default=None)
        p.add_argument('--vocabulary', default='', help='comma-separated, in production order')
        if name == 'record-stt':
            p.add_argument('--adapter', choices=('prerecorded', 'parakeet_batch', 'stub'), default='prerecorded')
            p.add_argument('--budget-usd', type=float, required=True)
            p.add_argument('--record-id', help='ledger + vendor log id (default <day>-<adapter>)')
            p.add_argument('--sync-exact', action='store_true', help='per-VAD-file cassettes for sync captures')
            p.add_argument('--window-seconds', type=float, default=30.0, help='parakeet_batch window length')
        else:
            p.add_argument('--run', required=True)
            p.add_argument('--sync-mode', choices=('exact', 'span'), default='span')
            p.add_argument('--streaming-via', choices=('record', 'sync', 'none'), default='sync')
    args = parser.parse_args(argv)

    if args.command == 'timeline':
        from testing.pipeline_lab.timeline.build import build_day_timeline

        timeline = build_day_timeline(args.day, vad=args.vad)
        print(json.dumps({'coverage': timeline['coverage'], 'evaluable_boundaries': timeline['evaluable_boundaries']}))
        return 0

    if args.command == 'record-stt':
        if args.adapter == 'prerecorded' and not (args.provider and args.model):
            parser.error('--provider and --model are required for the prerecorded adapter')
        from testing.pipeline_lab.store import ensure_private_dir, lab_root, private_tempdir

        with private_tempdir(ensure_private_dir(lab_root())):
            print(json.dumps(_record(args)))
        return 0

    # Replay plays recorded cassettes only: no vendor or cloud credential may reach the product code it runs.
    from testing.pipeline_lab.stack.runtime_env import SECRETISH
    from testing.pipeline_lab.worktrees import _SCRUB_EXACT

    for key in [k for k in os.environ if k in _SCRUB_EXACT or SECRETISH.search(k)]:
        del os.environ[key]

    from testing.pipeline_lab.lanes.day import STTSelection, replay_day
    from testing.pipeline_lab.store import ensure_private_dir, lab_root, safe_segment

    if not (args.provider and args.model):
        parser.error('--provider and --model name the cassettes to play')
    vocabulary = tuple(v for v in args.vocabulary.split(',') if v)
    root = ensure_private_dir(lab_root())
    from testing.pipeline_lab.store import private_tempdir

    with private_tempdir(root):  # the product STT code's own temp files stay inside the lab root
        results = replay_day(
            safe_segment(args.day, 'day id'),
            safe_segment(args.run, 'run id'),
            STTSelection(args.provider, args.model, args.language, vocabulary),
            sync_mode=args.sync_mode,
            streaming_via=None if args.streaming_via == 'none' else args.streaming_via,
            root=root,
        )
    counts: dict[str, int] = {}
    errors: dict[str, int] = {}
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
        if r.error:
            errors[r.error] = errors.get(r.error, 0) + 1
    print(json.dumps({'conversations': len(results), 'outcomes': counts, 'errors': errors}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
