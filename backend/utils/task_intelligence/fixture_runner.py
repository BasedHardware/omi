"""Hermetic runners for versioned task-intelligence fixtures."""

from collections.abc import Callable
from typing import Any

from models.task_recommendation import DeterministicFacts, RecommendationSubjectKind
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


def transcript_capture_v1(payload: dict[str, Any]) -> NormalizedSignals:
    return _capture_stub_output(payload, modality='transcript')


def screen_capture_v1(payload: dict[str, Any]) -> NormalizedSignals:
    return _capture_stub_output(payload, modality='screen')


def direct_command_contract(payload: dict[str, Any]) -> NormalizedSignals:
    return dict(payload)


def legacy_reconciliation_contract(payload: dict[str, Any]) -> NormalizedSignals:
    return dict(payload)


TEST_ADAPTERS: dict[str, FixtureAdapter] = {
    'direct_command_contract': direct_command_contract,
    'transcript_capture_v1': transcript_capture_v1,
    'screen_capture_v1': screen_capture_v1,
    'legacy_reconciliation_contract': legacy_reconciliation_contract,
}
KNOWN_TEST_ADAPTERS = frozenset(TEST_ADAPTERS)


def run_capture_case(case: dict[str, Any], modality: str) -> CapturePolicyResult:
    if modality not in {'transcript', 'screen'}:
        raise ValueError(f'unsupported capture modality: {modality}')
    input_payload = case.get('inputs', {}).get(modality)
    if not isinstance(input_payload, dict):
        raise ValueError(f'capture case {case.get("id")} is missing {modality} input')
    adapter = TEST_ADAPTERS[f'{modality}_capture_v1']
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
    return recommendations.build_evaluation_subject(
        kind=RecommendationSubjectKind.task,
        subject_id=subject_id,
        destination_task_id=subject_id,
        headline=f'Fixture {subject_id}',
        label=None,
        evidence=evidence,
        facts=facts,
        is_open=bool(raw_facts.get('open', True)),
        unexpired=bool(raw_facts.get('unexpired', True)),
        recent_material_activity=recent_material_activity,
        material_token='fixture-v1',
    )


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
    if len(selected) > 3 or not set(selected).issubset(shortlist_ids):
        raise ValueError('recorded ranking selected an ineligible or excess subject')
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
    'screen_capture_v1',
    'transcript_capture_v1',
]
