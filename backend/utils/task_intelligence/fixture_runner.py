"""Hermetic runners for versioned task-intelligence fixtures."""

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from typing import Any, cast

from models.task_recommendation import DeterministicFacts, FeedbackSubjectKind, RecommendationSubjectKind
from utils.task_intelligence import recommendations
from utils.task_intelligence.capture_policy import CapturePolicyResult, run_capture_policy

NormalizedSignals = dict[str, Any]
FixtureAdapter = Callable[[dict[str, Any]], NormalizedSignals]
ActionItemExtractor = Callable[..., list[Any]]
ConversationDiscarder = Callable[..., bool]

_EXTRACTION_LOGGER = logging.getLogger('utils.llm.conversation_processing')


class _LiveEvaluationFailureCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.failed = False
        self.failed_prefix: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        for prefix in ('Error extracting action items:', 'Error determining memory discard:'):
            if record.getMessage().startswith(prefix):
                self.failed = True
                self.failed_prefix = prefix
                return


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


def _item_result(item: Any) -> dict[str, Any]:
    return {
        'description': item.description,
        'capture_kind': item.capture_kind,
        'source_segment_ids': item.source_segment_ids,
    }


def _extract_for_live_evaluation(extractor: ActionItemExtractor, *args: Any, **kwargs: Any) -> list[Any]:
    """Turn the production extractor's fail-open [] into an explicit eval failure."""

    capture = _LiveEvaluationFailureCapture()
    previous_propagate = _EXTRACTION_LOGGER.propagate
    _EXTRACTION_LOGGER.addHandler(capture)
    _EXTRACTION_LOGGER.propagate = False
    try:
        try:
            items = extractor(*args, **kwargs)
        except Exception:
            raise RuntimeError('live wake-word evaluation NOT_RUN: extractor call failed') from None
    finally:
        _EXTRACTION_LOGGER.propagate = previous_propagate
        _EXTRACTION_LOGGER.removeHandler(capture)
    if capture.failed:
        raise RuntimeError('live wake-word evaluation NOT_RUN: extractor call failed')
    return items


def _matching_capture_kinds(items: list[dict[str, Any]], required_segment_ids: set[str]) -> list[str | None]:
    return [
        item['capture_kind']
        for item in items
        if required_segment_ids.intersection(item.get('source_segment_ids') or [])
    ]


def _evaluate_pair(case: dict[str, Any], pair: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    required_ids = set(case['required_marked_source_segment_ids'])
    expected_kind = case['expected_marked_capture_kind']
    unmarked_kinds = _matching_capture_kinds(pair['unmarked'], required_ids)
    marked_kinds = _matching_capture_kinds(pair['marked'], required_ids)
    ordinary_ids = set(case.get('ordinary_source_segment_ids', []))
    unmarked_source_ids = {
        segment_id for item in pair['unmarked'] for segment_id in (item.get('source_segment_ids') or [])
    }
    marked_source_ids = {segment_id for item in pair['marked'] for segment_id in (item.get('source_segment_ids') or [])}
    unmarked_ordinary_kinds = _matching_capture_kinds(pair['unmarked'], ordinary_ids)
    marked_ordinary_kinds = _matching_capture_kinds(pair['marked'], ordinary_ids)
    marked_expected_kind = not marked_kinds if expected_kind is None else expected_kind in marked_kinds
    return {
        'unmarked_wake_capture_kinds': unmarked_kinds,
        'marked_wake_capture_kinds': marked_kinds,
        'marked_expected_kind': marked_expected_kind,
        'capture_kind_changed': (
            expected_kind in marked_kinds and expected_kind not in unmarked_kinds if expected_kind is not None else None
        ),
        'marked_provenance_complete': (
            any(
                item.get('capture_kind') == expected_kind
                and required_ids.issubset(set(item.get('source_segment_ids') or []))
                for item in pair['marked']
            )
            if expected_kind is not None
            else None
        ),
        'ordinary_extraction_preserved': (
            ordinary_ids.issubset(unmarked_source_ids) and ordinary_ids.issubset(marked_source_ids)
            if ordinary_ids
            else None
        ),
        'ordinary_capture_kinds_unchanged': (
            sorted(unmarked_ordinary_kinds, key=str) == sorted(marked_ordinary_kinds, key=str) if ordinary_ids else None
        ),
    }


def run_live_wake_word_evaluation(
    capture: dict[str, Any], *, trials: int, extractor: ActionItemExtractor
) -> dict[str, Any]:
    """Run paired synthetic transcripts through the supplied production extractor."""

    results: dict[str, list[dict[str, Any]]] = {}
    evaluations: list[dict[str, Any]] = []
    for case in capture.get('wake_word_extractor_cases', []):
        case_trials: list[dict[str, Any]] = []
        for _ in range(trials):
            pair: dict[str, list[dict[str, Any]]] = {}
            for treatment in ('unmarked', 'marked'):
                items = _extract_for_live_evaluation(
                    extractor,
                    case[f'{treatment}_transcript'],
                    datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
                    'multi',
                    'UTC',
                    task_intelligence_capture=True,
                    trusted_wake_word_markers=treatment == 'marked',
                )
                pair[treatment] = [_item_result(item) for item in items]
            evaluation = _evaluate_pair(case, pair)
            evaluations.append(evaluation)
            case_trials.append({'outputs': pair, 'evaluation': evaluation})
        results[case['id']] = case_trials
    return {
        'trials_per_case': trials,
        'cases': results,
        'measurement': {
            'paired_trials': len(evaluations),
            'marked_expected_kind': sum(result['marked_expected_kind'] for result in evaluations),
            'capture_kind_changed': sum(result['capture_kind_changed'] is True for result in evaluations),
            'marked_provenance_complete': sum(result['marked_provenance_complete'] is True for result in evaluations),
            'ordinary_extraction_preserved': sum(
                result['ordinary_extraction_preserved'] is True for result in evaluations
            ),
            'ordinary_capture_kinds_unchanged': sum(
                result['ordinary_capture_kinds_unchanged'] is True for result in evaluations
            ),
        },
    }


def _discard_for_live_evaluation(discarder: ConversationDiscarder, *args: Any, **kwargs: Any) -> bool:
    """Turn the production discarder's fail-open False into an explicit eval failure."""

    capture = _LiveEvaluationFailureCapture()
    previous_propagate = _EXTRACTION_LOGGER.propagate
    _EXTRACTION_LOGGER.addHandler(capture)
    _EXTRACTION_LOGGER.propagate = False
    try:
        try:
            # cast to ``object`` so the fail-closed isinstance guard below stays a real
            # runtime check: the protocol declares ``-> bool``, which makes it statically dead.
            discarded = cast(object, discarder(*args, **kwargs))
        except Exception:
            raise RuntimeError('live wake-word discard evaluation NOT_RUN: discarder call failed') from None
    finally:
        failure_prefix = capture.failed_prefix
        _EXTRACTION_LOGGER.propagate = previous_propagate
        _EXTRACTION_LOGGER.removeHandler(capture)
    if failure_prefix == 'Error determining memory discard:':
        raise RuntimeError('live wake-word discard evaluation NOT_RUN: discarder call failed')
    if not isinstance(discarded, bool):
        raise RuntimeError('live wake-word discard evaluation NOT_RUN: discarder returned a non-boolean result')
    return discarded


def run_live_wake_word_discard_evaluation(
    capture: dict[str, Any], *, trials: int, discarder: ConversationDiscarder
) -> dict[str, Any]:
    """Run short paired transcripts through the supplied production discard gate."""

    results: dict[str, list[dict[str, Any]]] = {}
    evaluations: list[dict[str, Any]] = []
    negative_control_evaluations: list[dict[str, Any]] = []
    for case in capture.get('wake_word_discard_cases', []):
        case_trials: list[dict[str, Any]] = []
        for _ in range(trials):
            pair: dict[str, dict[str, bool]] = {}
            for treatment in ('unmarked', 'marked'):
                discarded = _discard_for_live_evaluation(
                    discarder,
                    case[f'{treatment}_transcript'],
                    case.get('photos'),
                    case['duration_seconds'],
                    trusted_wake_word_markers=treatment == 'marked',
                )
                pair[treatment] = {'discarded': discarded}
            unmarked_discarded = pair['unmarked']['discarded']
            marked_kept = not pair['marked']['discarded']
            evaluation = {
                'unmarked_discarded': unmarked_discarded,
                'marked_kept': marked_kept,
                'discard_changed': unmarked_discarded and marked_kept,
            }
            evaluations.append(evaluation)
            if case.get('negative_control') is True:
                negative_control_evaluations.append(evaluation)
            case_trials.append({'outputs': pair, 'evaluation': evaluation})
        results[case['id']] = case_trials
    return {
        'trials_per_case': trials,
        'cases': results,
        'measurement': {
            'paired_trials': len(evaluations),
            'discard_changed': sum(result['discard_changed'] for result in evaluations),
            'marked_kept': sum(result['marked_kept'] for result in evaluations),
            'unmarked_discarded': sum(result['unmarked_discarded'] for result in evaluations),
            'negative_control_trials': len(negative_control_evaluations),
            'negative_control_preserved': sum(
                result['unmarked_discarded'] and not result['marked_kept'] for result in negative_control_evaluations
            ),
        },
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
    'run_live_wake_word_discard_evaluation',
    'run_live_wake_word_evaluation',
    'run_recorded_association_case',
    'run_recorded_ranking_case',
    'screen_capture_v2',
    'transcript_capture_v2',
    'validate_ranking_selection',
]
