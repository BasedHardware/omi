#!/usr/bin/env python3
"""MANUAL ONLY: guarded synthetic fixture scoring through the existing JEV gateway.

No account/database/calendar lookups. Never load a backend .env implicitly.
"""

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent


class RealJevClient:
    scoring = 'real'

    def __init__(self, ask):
        self.ask = ask
        self.accounting = []

    def score(self, family_id, state, questions):
        started = time.monotonic()
        attempts = []
        answers = self.ask(
            state,
            questions,
            lane='conversation_relevance',
            outcome_observer=attempts.append,
            record_decision_metrics=False,
        )
        usage = dict(answers.usage) if answers else {}
        # No invented tariff or zero-cost assumption. Gateway usage may omit billing/retries.
        cost = usage.get('cost')
        valid_cost = not isinstance(cost, bool) and isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0
        call = {
            'family_id': family_id,
            'latency_seconds': time.monotonic() - started,
            'cost_usd': cost if valid_cost else None,
            'cost_status': 'reported_by_gateway' if valid_cost else 'COULD NOT DETERMINE',
            'outcome': attempts[-1] if attempts else 'unknown',
            'retry_cost_status': 'COULD NOT DETERMINE',
        }
        self.accounting.append(call)
        print('JEV call:', json.dumps(call, sort_keys=True))
        return None if answers is None else 1.0 - answers.noul('worth_keeping')


def main(argv=None):
    if os.getenv('JEV_PILOT_LIVE') != '1':
        raise SystemExit('Refusing real scoring: explicitly set JEV_PILOT_LIVE=1')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / '.outputs/real')
    parser.add_argument('--max-calls', type=int, required=True, help='Explicit authorized paid call ceiling')
    args = parser.parse_args(argv)
    spec = importlib.util.spec_from_file_location('pilot_harness', HERE / 'harness.py')
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    rows = harness.load_fixtures()
    calls = sum(
        harness._second_opinion(row, harness.baseline(row), harness.MockJevClient())['outcome'] != 'not_eligible'
        for row in rows
    )
    calls += sum(
        harness._second_opinion(row, harness.baseline(row, without_calendar=True), harness.MockJevClient())['outcome']
        != 'not_eligible'
        for row in rows
        if 'R16' in row['rule_ids'] and harness.baseline(row) != harness.baseline(row, without_calendar=True)
    )
    if args.max_calls < calls:
        raise SystemExit(f'Refusing: replay needs {calls} calls; ceiling is {args.max_calls}')
    if not os.getenv('OMI_LLM_GATEWAY_URL', '').strip():
        raise SystemExit('OMI_LLM_GATEWAY_URL must be configured explicitly; no implicit .env reads')
    sys.path.insert(0, str(HERE.parents[1] / 'backend'))
    from utils.llm.jev_client import ask_jev

    client = RealJevClient(ask_jev)
    harness.run(client, output=args.output)
    (args.output / 'accounting.jsonl').write_text(''.join(json.dumps(call) + '\n' for call in client.accounting))


if __name__ == '__main__':
    main()
