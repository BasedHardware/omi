"""Hermetic runners for versioned task-intelligence fixtures."""

from collections.abc import Callable
from typing import Any

from models.task_recommendation import DeterministicFacts, FeedbackSubjectKind, RecommendationSubjectKind
from utils.task_intelligence import recommendations
from utils.task_intelligence.capture_policy import CapturePolicyResult, run_capture_policy

NormalizedSignals = dict[str, Any]
FixtureAdapter = Callable[[dict[str, Any]], NormalizedSignals]


def _capture_stub_output(payload: dict[str, Any], *, modality: str) -> NormalizedSignals:
    """Normalize the recorded output of one modality-specific extraction adapter."""

    if not isinstance(payload.get('text'), str) or not payload['text']:
        raise ValueError(f'{modality} adapter requires synthetic source text')
    stub_output = payload.get('stub_output')
    if not isinstance(stub_output, dict):
        raise ValueError(f'{modality} adapter requires a recorded stub_output')
    return dict(stub_output)


def transcript_capture_v2(payload: dict[str, Any]) -> NormalizedSignals:
    return _capture_stub_output(payload, modality='transcript')


def screen_capture_v2(payload: dict[str, Any]) -> NormalizedSignals:
    return _capture_stub_output(payload, modality='screen')


def direct_command_contract(payload: dict[str, Any]) -> NormalizedSignals:
    return dict(payload)


def legacy_reconciliation_contract(payload: dict[str, Any]) -> NormalizedSignals:
    return dict(payload)


TEST_ADAPTERS: dict[str, FixtureAdapter] = {
    'direct_command_contract': direct_command_contract,
    'transcript_capture_v2': transcript_capture_v2,
    'screen_capture_v2': screen_capture_v2,
    'legacy_reconciliation_contract': legacy_reconciliation_contract,
}
KNOWN_TEST_ADAPTERS = frozenset(TEST_ADAPTERS)


def run_capture_case(case: dict[str, Any], modality: str) -> CapturePolicyResult:
    if modality not in {'transcript', 'screen'}:
        raise ValueError(f'unsupported capture modality: {modality}')
    input_payload = case.get('inputs', {}).get(modality)
    if not isinstance(input_payload, dict):
        raise ValueError(f'capture case {case.get("id")} is missing {modality} input')
    adapter = TEST_ADAPTERS[f'{modality}_capture_v2']
    return run_capture_policy(adapter(input_payload))


def run_recorded_association_case(case: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a recorded adjudicator result for hermetic CI."""

    candidates = case.get('candidate_workstreams')
    judgment = case.get('recorded_judgment')
    if not isinstance(candidates, list) or not isinstance(judgment, dict):
        raise ValueError('association case requires candidates and recorded_judgment')
    candidate_ids = {candidate.get('workstream_id') for candidate in candidates if isinstance(candidate, dict)}
    selected = judgment.get('workstream_id')
    if selected is not None and selected not in candidate_ids:
        raise ValueError('recorded association selected an unknown workstream')
    if not isinstance(judgment.get('material'), bool):
        raise ValueError('recorded association requires material boolean')
    return judgment


def _fixture_ranking_subject(subject: dict[str, Any], *, device_id: str | None) -> recommendations.EvaluationSubject:
    subject_id = subject.get('subject_id')
    if not isinstance(subject_id, str) or not subject_id:
        raise ValueError('ranking subject requires subject_id')
    raw_facts = subject.get('facts')
    if not isinstance(raw_facts, dict):
        raise ValueError('ranking subject requires deterministic facts')
    facts = DeterministicFacts.model_validate(
        {key: value for key, value in raw_facts.items() if key in DeterministicFacts.model_fields}
    )
    evidence = recommendations.valid_evidence(subject.get('evidence_refs', []), device_id=device_id)
    recent_material_activity = bool(
        subject.get('recent_material_activity', raw_facts.get('recent_material_activity', False))
    )
    kind = RecommendationSubjectKind(subject.get('subject_kind', RecommendationSubjectKind.task.value))
    feedback_kind = FeedbackSubjectKind.workstream if kind == RecommendationSubjectKind.agent_open_loop else None
    return recommendations.build_evaluation_subject(
        kind=kind,
        subject_id=subject_id,
        feedback_subject_kind=feedback_kind,
        feedback_subject_id=subject.get('workstream_id') if feedback_kind else None,
        destination_task_id=subject_id if kind == RecommendationSubjectKind.task else None,
        destination_workstream_id=subject.get('workstream_id'),
        headline=str(subject.get('headline') or f'Fixture {subject_id}'),
        label=subject.get('label'),
        evidence=evidence,
        facts=facts,
        is_open=bool(raw_facts.get('open', True)),
        unexpired=bool(raw_facts.get('unexpired', True)),
        recent_material_activity=recent_material_activity,
        material_token='fixture-v1',
        evidence_preview=subject.get('evidence_preview'),
        explicit_user_intent=bool(subject.get('explicit_user_intent', False)),
    )


def validate_ranking_selection(case: dict[str, Any], selected: list[str]) -> list[str]:
    """Return bounded fixture-contract violations for recorded and live judgments."""

    selected_set = set(selected)
    violations: list[str] = []
    forbidden = sorted(selected_set.intersection(case.get('must_not_select', [])))
    if forbidden:
        violations.append('forbidden:' + ','.join(forbidden))
    missing = sorted(set(case.get('must_select', [])).difference(selected_set))
    if missing:
        violations.append('missing:' + ','.join(missing))
    for index, choices in enumerate(case.get('must_select_one_of', [])):
        if not selected_set.intersection(choices):
            violations.append(f'missing_one_of:{index}')
    max_selected = int(case.get('max_selected', 3))
    if len(selected) > max_selected:
        violations.append(f'too_many:{len(selected)}>{max_selected}')
    if case.get('expected_empty') is True and selected:
        violations.append('expected_empty')
    for index, duplicate_group in enumerate(case.get('duplicate_groups', [])):
        if len(selected_set.intersection(duplicate_group)) > 1:
            violations.append(f'duplicate_group:{index}')
    return violations


def run_recorded_ranking_case(case: dict[str, Any]) -> list[str]:
    """Apply production shortlist gates before accepting a recorded judgment."""

    subjects = case.get('subjects')
    selected = case.get('recorded_judgment')
    if not isinstance(subjects, list) or not isinstance(selected, list):
        raise ValueError('ranking case requires subjects and recorded_judgment')
    current_context = case.get('current_context')
    device_id = current_context.get('device_id') if isinstance(current_context, dict) else None
    built_subjects = [_fixture_ranking_subject(subject, device_id=device_id) for subject in subjects]
    shortlist_ids = {subject.subject_id for subject in recommendations.filter_shortlist(built_subjects, set())}
    if not set(selected).issubset(shortlist_ids):
        raise ValueError('recorded ranking selected an ineligible or excess subject')
    violations = validate_ranking_selection(case, selected)
    if violations:
        raise ValueError('recorded ranking violates fixture contract: ' + ','.join(violations))
    return selected


def run_fixture_suite(
    *, capture: dict[str, Any], association: dict[str, Any], ranking: dict[str, Any]
) -> dict[str, Any]:
    capture_results: dict[str, dict[str, dict[str, str]]] = {}
    for case in capture['cases']:
        capture_results[case['id']] = {
            modality: run_capture_case(case, modality).__dict__ for modality in ('transcript', 'screen')
        }
    association_results = {case['id']: run_recorded_association_case(case) for case in association['cases']}
    ranking_results = {case['id']: run_recorded_ranking_case(case) for case in ranking['cases']}
    return {
        'capture': capture_results,
        'association': association_results,
        'ranking': ranking_results,
    }


__all__ = [
    'CapturePolicyResult',
    'KNOWN_TEST_ADAPTERS',
    'TEST_ADAPTERS',
    'direct_command_contract',
    'legacy_reconciliation_contract',
    'run_capture_case',
    'run_capture_policy',
    'run_fixture_suite',
    'run_recorded_association_case',
    'run_recorded_ranking_case',
    'screen_capture_v2',
    'transcript_capture_v2',
    'validate_ranking_selection',
]
