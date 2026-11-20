"""Seed registration: the ``corpus add-day`` tool (local files only, never the network)."""

from __future__ import annotations

import argparse
from typing import Any

from testing.pipeline_lab.registry import ToolContext


def corpus_add_day(ctx: ToolContext) -> dict[str, Any]:
    from pathlib import Path

    from testing.pipeline_lab.seed.corpus import add_day

    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab corpus add-day')
    parser.add_argument('--snapshot', required=True, help='local snapshot directory (fetch-owner-audio format)')
    parser.add_argument('--date', required=True, help='YYYY-MM-DD, local to --timezone')
    parser.add_argument('--timezone', required=True, help='IANA zone, e.g. America/Los_Angeles')
    parser.add_argument('--day-id', help='corpus day id (default: the date)')
    parser.add_argument('--audio-dir', help='local directory of <conversation_id>.<ext> clips (or an index.json)')
    parser.add_argument('--audio-sample-rate', type=int, default=16000, help='rate for non-WAV clips')
    parser.add_argument('--label', help='snapshot label recorded in day.json (default: the directory name)')
    parser.add_argument('--replace', action='store_true', help='rebuild an existing corpus day')
    args = parser.parse_args(ctx.argv)
    return add_day(
        ctx.store,
        Path(args.snapshot),
        args.date,
        args.timezone,
        day_id=args.day_id,
        audio_dir=Path(args.audio_dir) if args.audio_dir else None,
        label=args.label,
        audio_sample_rate=args.audio_sample_rate,
        replace=args.replace,
    )


def register(registry: Any) -> None:
    registry.add_tool('corpus-add-day', corpus_add_day)
