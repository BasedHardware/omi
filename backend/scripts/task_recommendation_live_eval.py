#!/usr/bin/env python3
"""Run the versioned What Matters Now fixture evaluation outside merge-gating CI."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from models.task_recommendation import (  # noqa: E402
    DeterministicFacts,
    FeedbackSubjectKind,
    RecommendationSubjectKind,
)
from utils.task_intelligence import recommendations  # noqa: E402
from utils.task_intelligence.fixture_runner import validate_ranking_selection  # noqa: E402
from utils.task_intelligence.live_recommendation_judgment import LiveRecommendationJudgment  # noqa: E402

if '--live' in sys.argv:
    from utils.llm.clients import get_llm as _get_live_llm  # noqa: E402
else:
    _get_live_llm = None

DEFAULT_FIXTURE = BACKEND_ROOT / 'tests' / 'unit' / 'fixtures' / 'task_intelligence' / 'ranking_v2.json'


class RecordedJudgment:
    model_version = 'recorded:ranking.v2'

    def __init__(self, selected_ids: list[str]):
        self.selected_ids = selected_ids

    def judge(self, subjects: list[recommendations.EvaluationSubject]) -> list[recommendations.JudgmentSelection]:
        eligible_ids = {subject.subject_id for subject in subjects}
        return [
            recommendations.JudgmentSelection(
                subject_kind=next(subject.kind for subject in subjects if subject.subject_id == subject_id),
                subject_id=subject_id,
                why_now='Recorded fixture selection.',
                recommended_action='Continue',
            )
            for subject_id in self.selected_ids
            if subject_id in eligible_ids
        ]


def _live_llm():
    if _get_live_llm is None:
        raise RuntimeError('live LLM provider is unavailable without --live')
    return _get_live_llm('what_matters_now')


def _subject(payload: dict[str, Any], *, device_id: str) -> recommendations.EvaluationSubject:
    raw_facts = payload['facts']
    facts = DeterministicFacts.model_validate(
        {key: value for key, value in raw_facts.items() if key in DeterministicFacts.model_fields}
    )
    evidence = recommendations.valid_evidence(payload.get('evidence_refs', []), device_id=device_id)
    recent_material_activity = bool(
        payload.get('recent_material_activity', raw_facts.get('recent_material_activity', False))
    )
    kind = RecommendationSubjectKind(payload.get('subject_kind', RecommendationSubjectKind.task.value))
    feedback_kind = FeedbackSubjectKind.workstream if kind == RecommendationSubjectKind.agent_open_loop else None
    return recommendations.build_evaluation_subject(
        kind=kind,
        subject_id=payload['subject_id'],
        feedback_subject_kind=feedback_kind,
        feedback_subject_id=payload.get('workstream_id') if feedback_kind else None,
        destination_task_id=payload['subject_id'] if kind == RecommendationSubjectKind.task else None,
        destination_workstream_id=payload.get('workstream_id'),
        headline=str(payload.get('headline') or f"Synthetic fixture {payload['subject_id']}"),
        label=payload.get('label'),
        evidence=evidence,
        facts=facts,
        is_open=bool(raw_facts.get('open', True)),
        unexpired=bool(raw_facts.get('unexpired', True)),
        recent_material_activity=recent_material_activity,
        material_token='fixture-v1',
        evidence_preview=payload.get('evidence_preview'),
        explicit_user_intent=bool(payload.get('explicit_user_intent', False)),
    )


def validate_live_selection(
    case: dict[str, Any],
    selections: list[recommendations.JudgmentSelection],
    shortlist: list[recommendations.EvaluationSubject],
) -> list[str]:
    """Validate both the taste fixture and the production shortlist boundary."""

    shortlist_keys = {(subject.kind, subject.subject_id) for subject in shortlist}
    valid_selections = [
        selection for selection in selections if (selection.subject_kind, selection.subject_id) in shortlist_keys
    ]
    violations = validate_ranking_selection(case, [selection.subject_id for selection in valid_selections])
    out_of_shortlist = sorted(
        f'{selection.subject_kind.value}:{selection.subject_id}'
        for selection in selections
        if (selection.subject_kind, selection.subject_id) not in shortlist_keys
    )
    if out_of_shortlist:
        violations.append('out_of_shortlist:' + ','.join(out_of_shortlist))
    return violations


def run(fixture_path: Path, *, live: bool) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text())
    case_reports = []
    for case in fixture['cases']:
        device_id = str(case.get('current_context', {}).get('device_id') or '')
        subjects = [_subject(subject, device_id=device_id) for subject in case['subjects']]
        shortlist = recommendations.filter_shortlist(subjects, set())
        if live:
            judgment: recommendations.RecommendationJudgment = LiveRecommendationJudgment(_live_llm)
        else:
            judgment = RecordedJudgment(case['recorded_judgment'])
        selections = judgment.judge(shortlist)
        selected_ids = [selection.subject_id for selection in selections]
        shortlist_ids = [subject.subject_id for subject in shortlist]
        violations = validate_live_selection(case, selections, shortlist)
        case_reports.append(
            {
                'case_id': case['id'],
                'model_version': judgment.model_version,
                'shortlist_ids': shortlist_ids,
                'shortlist_keys': [f'{subject.kind.value}:{subject.subject_id}' for subject in shortlist],
                'selected_ids': selected_ids,
                'selected_keys': [f'{selection.subject_kind.value}:{selection.subject_id}' for selection in selections],
                'violations': violations,
                'passed': not violations,
            }
        )
    return {
        'schema_version': fixture['schema_version'],
        'policy_version': fixture['policy_version'],
        'prompt_version': recommendations.PROMPT_VERSION,
        'mode': 'live' if live else 'recorded-dry-run',
        'cases': case_reports,
        'passed': all(case['passed'] for case in case_reports),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument('--live', action='store_true', help='make the separately authorized live model call')
    args = parser.parse_args()
    if args.live:
        if os.getenv('CI') and os.getenv('GITHUB_EVENT_NAME') != 'workflow_dispatch':
            parser.error('live recommendation evals may not run in merge-gating CI')
        if os.getenv('OMI_TASK_RECOMMENDATION_LIVE_EVAL') != '1':
            parser.error('set OMI_TASK_RECOMMENDATION_LIVE_EVAL=1 to authorize live evaluation')
    report = run(args.fixture, live=args.live)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
