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
from database import dream_feedback
from scripts.dream_triage_eval import validate_dev  # noqa: E402
from utils import dream_prompt, dream_transport, dream_guards  # noqa: E402
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
    cases = fixture.get('cases') or [dict(fixture, id='original')]
    framed_cases = [(case, messages(dict(case, version=1), mount)) for case in cases]
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
            for case, framed in framed_cases:
                sink = {'tokens': 0}
                row = {'repeat': repeat, 'case': case['id']}
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
                    plan = dream_guards.filter_plan(turn.value, case['records'], usage_sink=sink)
                    refs = set(case['records'])
                    expected = case.get('expected_kind')
                    matching = [
                        e
                        for e in plan.edits
                        if e.kind == expected
                        and e.target in refs
                        and e.target in e.evidence
                        and (not case.get('after_contains') or case['after_contains'] in e.after)
                    ]
                    privacy_rejected = 0
                    accepted = []
                    for feedback in plan.feedback:
                        try:
                            dream_feedback.validate(
                                feedback, case['records'], [t.model_dump() for t in plan.vocabulary]
                            )
                            accepted.append(feedback)
                        except ValueError:
                            privacy_rejected += 1
                    if privacy_rejected:
                        counts = Counter(sink.get('rejected', {}))
                        counts['privacy_rejected'] += privacy_rejected
                        sink['rejected'] = dict(counts)
                    plan.feedback = dream_guards.cap_feedback(accepted, usage_sink=sink)
                    expected_hit = (
                        bool(matching) if expected else bool(plan.edits) if case['id'] == 'original' else True
                    )
                    if case.get('expect_no_edits'):
                        expected_hit = not plan.edits
                    if case.get('expect_no_overview_edits'):
                        expected_hit = not any(e.kind == 'overview' for e in plan.edits)
                    if case.get('expect_no_feedback'):
                        expected_hit = expected_hit and not plan.feedback
                    row.update(
                        error=None,
                        edits_by_kind=dict(Counter(e.kind for e in plan.edits)),
                        raw_edits_by_kind=dict(Counter(e.kind for e in turn.value.edits)),
                        kept={name: len(getattr(plan, name)) for name in Plan.model_fields},
                        title_proposals=sum(e.kind == 'title' for e in matching),
                        expected_edit_hit=expected_hit,
                        # Every transcription report on this clean bilingual fixture is a false positive.
                        language_false_positives=(
                            sum(f.component == 'transcription' for f in plan.feedback)
                            if case['id'] == 'clean_bilingual'
                            else 0
                        ),
                        feedback_evidence_overlap=privacy_rejected,
                        clean_edits=len(plan.edits) if case['id'] == 'clean_bilingual' else 0,
                    )
                except Exception as exc:
                    row.update(
                        error=type(exc).__name__,
                        edits_by_kind={},
                        raw_edits_by_kind={},
                        kept={name: 0 for name in Plan.model_fields},
                        title_proposals=0,
                        expected_edit_hit=False,
                        language_false_positives=0,
                        feedback_evidence_overlap=0,
                        clean_edits=0,
                    )
                    if isinstance(exc, dream_transport.ValidationError):
                        totals = Counter(sink.get('validation_errors', {}))
                        totals.update(dream_transport.validation_counts(exc))
                        sink['validation_errors'] = dict(totals)
                row.update(
                    tokens=sink['tokens'],
                    latency_ms=round((time.monotonic() - started) * 1000),
                    dropped_invalid=sink.get('dropped_invalid', {}),
                    validation_errors=sink.get('validation_errors', {}),
                    rejected=sink.get('rejected', {}),
                )
                report['rows'].append(row)
                report['summary'] = summarize(report['rows'], expected_runs=5 * len(cases))
                args.output.write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps(row), flush=True)
                if row['error']:
                    raise RuntimeError('dev reasoning eval failed; restore access before repeating')
    finally:
        await close_all_clients()
    print(json.dumps(report['summary']), flush=True)
    if not report['summary']['targets_met']:
        raise RuntimeError('five successful repeats meeting fixture expectations required')


def summarize(rows, *, expected_runs=5):
    def total(key):
        counts = Counter()
        for row in rows:
            counts.update(row.get(key, {}))
        return dict(counts)

    errors_by_type = Counter()
    for location, count in total('validation_errors').items():
        errors_by_type[location.rsplit(':', 1)[1]] += count
    return {
        'runs': len(rows),
        'failed_runs': sum(row['error'] is not None for row in rows),
        'kept': total('kept'),
        'dropped_invalid': total('dropped_invalid'),
        'rejected': total('rejected'),
        'edits_by_kind': total('edits_by_kind'),
        'raw_edits_by_kind': total('raw_edits_by_kind'),
        'validation_errors': total('validation_errors'),
        'errors_by_type': dict(errors_by_type),
        'tokens': sum(row['tokens'] for row in rows),
        'title_proposals': sum(row['title_proposals'] for row in rows),
        'language_false_positives': sum(row['language_false_positives'] for row in rows),
        'feedback_evidence_overlap': sum(row['feedback_evidence_overlap'] for row in rows),
        'targets_met': len(rows) == expected_runs
        and all(
            row['error'] is None
            and row['expected_edit_hit']
            and row['language_false_positives'] == 0
            and row['feedback_evidence_overlap'] == 0
            and row['clean_edits'] == 0
            for row in rows
        ),
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
        fixture = json.loads(args.fixture.read_bytes())
        for case in fixture.get('cases') or [fixture]:
            framed = messages(dict(case, version=1), mount)
            assert dream_transport.input_ceiling(framed, Plan.model_json_schema()) + 4096 <= mount.budget.tokens
        print('Invented reasoning fixture fits the production Plan prompt and transport budget.')
        return
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
