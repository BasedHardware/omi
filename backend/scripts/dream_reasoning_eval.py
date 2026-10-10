#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Five invented reasoning calls through the production transport on a dev tunnel.

No database reads or product effects. Output contains hashes and counts only.
Verify the tunnel's dev destination and accounting/ADC project before --live.
"""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from models.dream_agent import Plan, Triage  # noqa: E402
from scripts.dream_triage_eval import validate_dev  # noqa: E402
from utils import dream_prompt, dream_transport  # noqa: E402
from utils.http_client import close_all_clients  # noqa: E402

FIXTURE = BACKEND_ROOT / 'evals/dream_reasoning/fixture.json'


def messages(fixture, mount):
    assert fixture['version'] == 1
    triage = Triage.model_validate({'clusters': fixture['clusters']})
    assert all(ref in fixture['records'] for cluster in triage.clusters for ref in cluster.refs)
    evidence = dream_prompt.evidence_message(
        fixture['records'],
        Plan,
        mount.budget.tokens,
        names=dream_prompt.person_names(fixture['records']),
        clusters=triage.model_dump(),
    )
    return mount.messages(evidence)


async def run(args):
    validate_dev()
    fixture_bytes = args.fixture.read_bytes()
    fixture = json.loads(fixture_bytes)
    mount = dream_prompt.mount(Plan, 24000)
    framed = messages(fixture, mount)
    report = {
        'project': 'based-hardware-dev',
        'lane': dream_transport.MAIN_LANE,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'fixture_sha256': hashlib.sha256(fixture_bytes).hexdigest(),
        'instructions_sha256': hashlib.sha256(mount.instructions.encode()).hexdigest(),
        'rows': [],
    }
    try:
        for repeat in range(1, 6):
            sink = {'tokens': 0}
            row = {'repeat': repeat}
            started = time.monotonic()
            try:
                async with asyncio.timeout(65):
                    turn = await dream_transport.model_turn(
                        'dream-canary-offline-reasoning-eval',
                        dream_transport.MAIN_LANE,
                        mount,
                        framed,
                        usage_sink=sink,
                    )
                row.update(error=None, kept={name: len(getattr(turn.value, name)) for name in Plan.model_fields})
            except Exception as exc:
                row.update(error=type(exc).__name__, kept={name: 0 for name in Plan.model_fields})
                if isinstance(exc, dream_transport.ValidationError):
                    totals = Counter(sink.get('validation_errors', {}))
                    totals.update(dream_transport.validation_counts(exc))
                    sink['validation_errors'] = dict(totals)
            row.update(
                tokens=sink['tokens'],
                latency_ms=round((time.monotonic() - started) * 1000),
                dropped_invalid=sink.get('dropped_invalid', {}),
                validation_errors=sink.get('validation_errors', {}),
            )
            report['rows'].append(row)
            report['summary'] = summarize(report['rows'])
            args.output.write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            if row['error']:
                raise RuntimeError('dev reasoning eval failed; restore access before repeating')
    finally:
        await close_all_clients()
    print(json.dumps(report['summary']), flush=True)
    if not report['summary']['targets_met']:
        raise RuntimeError('five successful edit-producing reasoning runs required')


def summarize(rows):
    def total(key):
        counts = Counter()
        for row in rows:
            counts.update(row[key])
        return dict(counts)

    errors_by_type = Counter()
    for location, count in total('validation_errors').items():
        errors_by_type[location.rsplit(':', 1)[1]] += count
    return {
        'runs': len(rows),
        'failed_runs': sum(row['error'] is not None for row in rows),
        'kept': total('kept'),
        'dropped_invalid': total('dropped_invalid'),
        'validation_errors': total('validation_errors'),
        'errors_by_type': dict(errors_by_type),
        'tokens': sum(row['tokens'] for row in rows),
        'targets_met': len(rows) == 5 and all(row['error'] is None and row['kept']['edits'] > 0 for row in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--check-fixture', action='store_true')
    parser.add_argument('--fixture', type=Path, default=FIXTURE)
    parser.add_argument('--output', type=Path, default=Path('dream-reasoning-results.json'))
    args = parser.parse_args()
    if args.check_fixture:
        mount = dream_prompt.mount(Plan, 24000)
        framed = messages(json.loads(args.fixture.read_bytes()), mount)
        assert dream_transport.input_ceiling(framed, Plan.model_json_schema()) + 4096 <= mount.budget.tokens
        print('Invented reasoning fixture fits the production Plan prompt and transport budget.')
        return
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
