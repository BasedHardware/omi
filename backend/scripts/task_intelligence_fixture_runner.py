#!/usr/bin/env python3
"""Run hermetic fixtures and an optional three-arm live wake-word policy evaluation."""

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from utils.task_intelligence.contracts import load_fixture
from utils.task_intelligence.fixture_runner import (
    run_fixture_suite,
    run_live_wake_word_discard_evaluation,
    run_live_wake_word_evaluation,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--live-wake-word-eval',
        action='store_true',
        help='Run baseline, marker-only, and marker+adjudicator policy arms on realistic conversations.',
    )
    parser.add_argument('--trials', type=int, default=3, help='Live trials per wake-word fixture case (minimum 3).')
    return parser


def main() -> None:
    args = _parser().parse_args()
    capture = load_fixture('capture_v2.json')
    result = run_fixture_suite(
        capture=capture,
        association=load_fixture('association_v1.json'),
        ranking=load_fixture('ranking_v2.json'),
    )
    if args.live_wake_word_eval:
        from utils.llm.conversation_processing import extract_action_items, should_discard_conversation
        from utils.llm.wake_word_adjudication import adjudicate_wake_word_invocations

        gateway_enabled = os.getenv('OMI_LLM_GATEWAY_FEATURE_MODE', '').strip().casefold() in {
            '1',
            'true',
            'yes',
            'gateway',
        }
        if not os.getenv('OPENAI_API_KEY') and not (gateway_enabled and os.getenv('OMI_LLM_GATEWAY_URL')):
            raise SystemExit(
                'live wake-word evaluation NOT_RUN: configure OPENAI_API_KEY or the enabled Omi LLM gateway'
            )
        result['wake_word_discard_live_evaluation'] = run_live_wake_word_discard_evaluation(
            capture,
            trials=max(1, args.trials),
            discarder=should_discard_conversation,
        )
        result['wake_word_live_evaluation'] = run_live_wake_word_evaluation(
            capture,
            trials=max(3, args.trials),
            extractor=extract_action_items,
            adjudicator=adjudicate_wake_word_invocations,
        )
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
