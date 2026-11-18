"""Interim ingest CLI until lane ``core`` wires these into ``python -m testing.pipeline_lab``.

    python -m testing.pipeline_lab.lanes timeline --day DAY [--vad]
    python -m testing.pipeline_lab.lanes record-stt --day DAY --run RUN --provider P --model M \
        [--language L] [--budget-usd 1.0]          # the only billable command
    python -m testing.pipeline_lab.lanes replay --day DAY --run RUN --provider P --model M [--sync-mode exact|span]

All paths come from ``OMI_PIPELINE_LAB_ROOT``. JSON summary on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.lanes')
    sub = parser.add_subparsers(dest='command', required=True)
    t = sub.add_parser('timeline')
    t.add_argument('--day', required=True)
    t.add_argument('--vad', action='store_true', help='also run local Silero VAD over every clip')
    for name in ('record-stt', 'replay'):
        p = sub.add_parser(name)
        p.add_argument('--day', required=True)
        p.add_argument('--run', required=True)
        p.add_argument('--provider', required=True)
        p.add_argument('--model', required=True)
        p.add_argument('--language', default=None)
        p.add_argument('--vocabulary', default='', help='comma-separated, in production order')
        if name == 'record-stt':
            p.add_argument('--budget-usd', type=float, required=True)
        else:
            p.add_argument('--sync-mode', choices=('exact', 'span'), default='exact')
            p.add_argument('--streaming-via', choices=('record', 'sync'), default=None)
    args = parser.parse_args(argv)

    if args.command == 'timeline':
        from testing.pipeline_lab.timeline.build import build_day_timeline

        timeline = build_day_timeline(args.day, vad=args.vad)
        print(json.dumps({'coverage': timeline['coverage'], 'evaluable_boundaries': timeline['evaluable_boundaries']}))
        return 0

    vocabulary = tuple(v for v in args.vocabulary.split(',') if v)
    if args.command == 'record-stt':
        from testing.pipeline_lab.cassette.adapters import PrerecordedAdapter
        from testing.pipeline_lab.cassette.recorder import InMemoryLedger, Recorder
        from testing.pipeline_lab.lanes.day import record_day_cassettes
        from testing.pipeline_lab.timeline.paths import lab_root

        # Interim cap: core's persistent ledger replaces InMemoryLedger at integration.
        recorder = Recorder(
            PrerecordedAdapter(provider=args.provider, model=args.model),
            InMemoryLedger(args.budget_usd),
            vendor_log=lab_root() / 'runs' / args.run / 'vendor_log.jsonl',
        )
        summary = record_day_cassettes(args.day, recorder, language=args.language, vocabulary=vocabulary)
        print(json.dumps(summary))
        return 0

    from testing.pipeline_lab.lanes.day import STTSelection, replay_day

    results = replay_day(
        args.day,
        args.run,
        STTSelection(args.provider, args.model, args.language, vocabulary),
        sync_mode=args.sync_mode,
        streaming_via=args.streaming_via,
    )
    counts: dict[str, int] = {}
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    print(json.dumps({'conversations': len(results), 'outcomes': counts}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
