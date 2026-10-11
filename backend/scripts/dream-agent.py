#!/usr/bin/env python3
"""Use only an authorized local/dev environment; flags default off."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.dream_agent import Caps, mode
from database import dream_store, dream_feedback
from utils.dream_agent import run_pass, drain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid')
    parser.add_argument('--seed-ref', action='append', default=[], help='collection/id of authorized dev data')
    parser.add_argument('--feedback-patterns', action='store_true')
    args = parser.parse_args()
    if args.feedback_patterns:
        print(json.dumps(dream_feedback.read_patterns(k=Caps.from_env().anonymous_k)))
        return
    if mode() == 'off':
        parser.error('DREAM_AGENT_MODE is off')
    if args.seed_ref:
        if not args.uid:
            parser.error('--seed-ref requires --uid')
        refs = [tuple(ref.split('/', 1)) for ref in args.seed_ref]
        if any(len(ref) != 2 for ref in refs):
            parser.error('seed references must be collection/id')
        dream_store.mark_dirty(args.uid, refs)
    result = asyncio.run(run_pass(args.uid) if args.uid else drain())
    # Print metadata only; the encrypted per-user run doc contains proposed content.
    reports = result if isinstance(result, list) else [result]
    print(
        json.dumps([{key: r.get(key) for key in ('status', 'run_id', 'tokens', 'cost_usd_reserved')} for r in reports])
    )


if __name__ == '__main__':
    main()
