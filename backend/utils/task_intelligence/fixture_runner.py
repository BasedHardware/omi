"""Hermetic runners for versioned task-intelligence fixtures."""

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import logging
from typing import Any, cast

from models.task_recommendation import DeterministicFacts, FeedbackSubjectKind, RecommendationSubjectKind
from utils.conversations.wake_word import WAKE_WORD_MARKER, find_wake_word_segment_ids
from utils.llm.wake_word_adjudication import WakeWordAdjudication
from utils.task_intelligence import recommendations
from utils.task_intelligence.capture_policy import CapturePolicyResult, run_capture_policy
from utils.task_intelligence.conversation_capture_policy import (
    WakeWordCaptureGate,
    evaluate_action_item_capture_policy,
)

NormalizedSignals = dict[str, Any]
FixtureAdapter = Callable[[dict[str, Any]], NormalizedSignals]
ActionItemExtractor = Callable[..., list[Any]]
ConversationDiscarder = Callable[..., bool]
WakeWordAdjudicator = Callable[..., WakeWordAdjudication]

_EXTRACTION_LOGGER = logging.getLogger('utils.llm.conversation_processing')
_ADJUDICATION_LOGGER = logging.getLogger('utils.llm.wake_word_adjudication')


class _LiveEvaluationFailureCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.failed = False
        self.failed_prefix: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        for prefix in (
            'Error extracting action items:',
            'Error determining memory discard:',
            'Error adjudicating wake-word invocations:',
        ):
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
        'capture_confidence': getattr(item, 'capture_confidence', None),
        'ownership_confidence': getattr(item, 'ownership_confidence', None),
        'capture_owner': getattr(item, 'capture_owner', None),
        'concrete_deliverable': getattr(item, 'concrete_deliverable', None),
        'source_segment_ids': list(item.source_segment_ids),
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


def _fixture_segment_value(segment: Mapping[str, Any], field: str) -> Any:
    if field == 'speaker_label':
        return segment.get(field) or ('User' if segment.get('speaker_role') == 'primary_user' else 'Speaker')
    return segment.get(field)


def _case_segments(case: dict[str, Any]) -> list[dict[str, Any]]:
    fields = ('id', 'start', 'end', 'speaker_label', 'speaker_role', 'text')
    return [dict(zip(fields, segment)) for segment in case['segments']]


def _render_fixture_transcript(segments: list[dict[str, Any]], matched_segment_ids: set[str]) -> str:
    lines: list[str] = []
    for segment in segments:
        marker = f'{WAKE_WORD_MARKER} ' if segment['id'] in matched_segment_ids else ''
        lines.append(
            f"[segment:{segment['id']} {segment['start']:.3f}-{segment['end']:.3f}] "
            f"{marker}{_fixture_segment_value(segment, 'speaker_label')}: {segment['text']}"
        )
    return '\n\n'.join(lines)


def _speaker_labels(segments: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            'segment_id': segment['id'],
            'speaker_label': str(_fixture_segment_value(segment, 'speaker_label')),
            'speaker_role': segment['speaker_role'],
        }
        for segment in segments
    ]


def _adjudicate_for_live_evaluation(adjudicator: WakeWordAdjudicator, **kwargs: Any) -> WakeWordAdjudication:
    capture = _LiveEvaluationFailureCapture()
    previous_propagate = _ADJUDICATION_LOGGER.propagate
    _ADJUDICATION_LOGGER.addHandler(capture)
    _ADJUDICATION_LOGGER.propagate = False
    try:
        try:
            result = adjudicator(**kwargs)
        except Exception:
            raise RuntimeError('live wake-word evaluation NOT_RUN: adjudicator call failed') from None
    finally:
        _ADJUDICATION_LOGGER.propagate = previous_propagate
        _ADJUDICATION_LOGGER.removeHandler(capture)
    if capture.failed_prefix == 'Error adjudicating wake-word invocations:':
        raise RuntimeError('live wake-word evaluation NOT_RUN: adjudicator call failed')
    try:
        return WakeWordAdjudication.model_validate(result)
    except Exception:
        raise RuntimeError('live wake-word evaluation NOT_RUN: adjudicator returned invalid output') from None


def _effective_capture_kind(signals: Any) -> str | None:
    for field, value in (
        ('explicit_command', 'explicit_command'),
        ('clear_commitment', 'clear_commitment'),
        ('direct_request', 'direct_request'),
        ('inferred_next_step', 'inferred_next_step'),
    ):
        if getattr(signals, field):
            return value
    return None


def _score_items(items: list[Any], gate: WakeWordCaptureGate | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in items:
        evaluation = evaluate_action_item_capture_policy(item, gate)
        signals = evaluation.signals
        result = _item_result(item)
        result['policy_capture_kind'] = _effective_capture_kind(signals)
        result['policy_outcome'] = evaluation.policy.outcome
        results.append(result)
    return results


def _ambient_set(items: list[dict[str, Any]], matched_segment_ids: set[str]) -> set[tuple[Any, ...]]:
    return {
        (
            item['description'],
            item['capture_kind'],
            item['policy_outcome'],
            tuple(sorted(item['source_segment_ids'])),
        )
        for item in items
        if not matched_segment_ids.intersection(item['source_segment_ids'])
    }


def _ambient_policy_distribution(
    case_trials: list[dict[str, Any]],
    arm: str,
    matched_segment_ids: set[str],
) -> list[dict[str, Any]]:
    """Aggregate policy outcomes across trials without comparing sampled wording."""

    counts: Counter[tuple[tuple[str, ...], str, str]] = Counter()
    for trial in case_trials:
        for item in trial['outputs'][arm]:
            source_segment_ids = tuple(sorted(str(segment_id) for segment_id in item['source_segment_ids']))
            if matched_segment_ids.intersection(source_segment_ids):
                continue
            counts[
                (
                    source_segment_ids,
                    str(item['policy_capture_kind'] or 'none'),
                    str(item['policy_outcome']),
                )
            ] += 1
    return [
        {
            'source_segment_ids': list(source_segment_ids),
            'policy_capture_kind': policy_capture_kind,
            'policy_outcome': policy_outcome,
            'count': count,
        }
        for (source_segment_ids, policy_capture_kind, policy_outcome), count in sorted(counts.items())
    ]


def _has_direct_outcome(items: list[dict[str, Any]], segment_id: str) -> bool:
    """True when a segment was scored as an explicit command.

    INV-TASK-2 deleted ``create_direct``; an explicit command now proposes a
    Candidate. The wake-word evaluation still needs to know whether an arm
    treated a segment as a command, which is what the adjudicator is for.
    """

    return any(
        item.get('policy_capture_kind') == 'explicit_command' and segment_id in item['source_segment_ids']
        for item in items
    )


def _verdict_for_segment(adjudication: WakeWordAdjudication, segment_id: str) -> list[str]:
    return [invocation.verdict for invocation in adjudication.invocations if segment_id in invocation.segment_ids]


def _evaluate_three_arms(
    case: dict[str, Any],
    arms: dict[str, list[dict[str, Any]]],
    adjudication: WakeWordAdjudication,
    matched_segment_ids: set[str],
) -> dict[str, Any]:
    ambient_sets = {arm: _ambient_set(items, matched_segment_ids) for arm, items in arms.items()}
    command_ids = case.get('expected_command_segment_ids', [])
    non_command_ids = case.get('expected_non_command_segment_ids', [])
    split = case.get('split_assertion')
    split_correct: bool | None = None
    if isinstance(split, dict):
        command_verdicts = _verdict_for_segment(adjudication, split['command_segment_id'])
        rejection_verdicts = _verdict_for_segment(adjudication, split['rejection_segment_id'])
        split_correct = 'task_command' in command_verdicts and any(
            verdict not in {'task_command', 'memory_command'} for verdict in rejection_verdicts
        )
    return {
        'stage2_fired': bool(matched_segment_ids),
        'matched_segment_ids': sorted(matched_segment_ids),
        'false_create_direct': {
            arm: {segment_id: _has_direct_outcome(items, segment_id) for segment_id in non_command_ids}
            for arm, items in arms.items()
        },
        'command_create_direct': {
            arm: {segment_id: _has_direct_outcome(items, segment_id) for segment_id in command_ids}
            for arm, items in arms.items()
        },
        # These arms share the same extraction sample, so an exact comparison
        # isolates adjudicator interference instead of measuring LLM sampling noise.
        'adjudicator_ambient_items_set_equal': (ambient_sets['marker_only'] == ambient_sets['marker_adjudicator']),
        'control_arms_set_equal': (
            len({frozenset(_ambient_set(items, set())) for items in arms.values()}) == 1
            if case.get('control') is True
            else None
        ),
        'paired_invocations_split': split_correct,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def run_live_wake_word_evaluation(
    capture: dict[str, Any],
    *,
    trials: int,
    extractor: ActionItemExtractor,
    adjudicator: WakeWordAdjudicator,
) -> dict[str, Any]:
    """Run realistic conversations through baseline, marker-only, and conjunction-gate arms."""

    if trials < 3:
        raise ValueError('live wake-word evaluation requires at least 3 trials per case')
    results: dict[str, list[dict[str, Any]]] = {}
    evaluations: list[dict[str, Any]] = []
    ambient_distribution_comparisons: dict[str, dict[str, Any]] = {}
    stage2_calls = 0
    for case in capture.get('wake_word_evaluation_cases', []):
        segments = _case_segments(case)
        matched_segment_ids = set(find_wake_word_segment_ids(segments))
        unmarked_transcript = _render_fixture_transcript(segments, set())
        marked_transcript = _render_fixture_transcript(segments, matched_segment_ids)
        case_trials: list[dict[str, Any]] = []
        for _ in range(trials):
            baseline_items = _extract_for_live_evaluation(
                extractor,
                unmarked_transcript,
                datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
                'multi',
                'UTC',
                task_intelligence_capture=True,
                trusted_wake_word_markers=False,
            )
            if matched_segment_ids:
                marked_items = _extract_for_live_evaluation(
                    extractor,
                    marked_transcript,
                    datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
                    'multi',
                    'UTC',
                    task_intelligence_capture=True,
                    trusted_wake_word_markers=True,
                )
            else:
                # The control has identical transcripts and prompt flags. Reuse
                # the same model sample so equality means policy equality rather
                # than accidental agreement between nondeterministic completions.
                marked_items = baseline_items
            adjudication = WakeWordAdjudication()
            gate = None
            if matched_segment_ids:
                stage2_calls += 1
                adjudication = _adjudicate_for_live_evaluation(
                    adjudicator,
                    marked_transcript=marked_transcript,
                    matched_segment_ids=matched_segment_ids,
                    action_items=marked_items,
                    speaker_labels=_speaker_labels(segments),
                    transcript_segments=segments,
                )
                gate = WakeWordCaptureGate(frozenset(matched_segment_ids), adjudication)
            arms = {
                'baseline': _score_items(baseline_items, None),
                'marker_only': _score_items(marked_items, None),
                'marker_adjudicator': _score_items(marked_items, gate),
            }
            evaluation = _evaluate_three_arms(case, arms, adjudication, matched_segment_ids)
            evaluations.append(evaluation)
            case_trials.append(
                {
                    'outputs': arms,
                    'adjudication': adjudication.model_dump(mode='json'),
                    'evaluation': evaluation,
                }
            )
        results[case['id']] = case_trials
        baseline_distribution = _ambient_policy_distribution(case_trials, 'baseline', matched_segment_ids)
        marker_distribution = _ambient_policy_distribution(case_trials, 'marker_only', matched_segment_ids)
        ambient_distribution_comparisons[case['id']] = {
            'baseline': baseline_distribution,
            'marker_only': marker_distribution,
            'distributions_match': baseline_distribution == marker_distribution,
        }

    arms = ('baseline', 'marker_only', 'marker_adjudicator')
    false_denominator = sum(
        len(case.get('expected_non_command_segment_ids', [])) * trials
        for case in capture.get('wake_word_evaluation_cases', [])
    )
    command_denominator = sum(
        len(case.get('expected_command_segment_ids', [])) * trials
        for case in capture.get('wake_word_evaluation_cases', [])
    )
    false_counts = {
        arm: sum(value for evaluation in evaluations for value in evaluation['false_create_direct'][arm].values())
        for arm in arms
    }
    command_counts = {
        arm: sum(value for evaluation in evaluations for value in evaluation['command_create_direct'][arm].values())
        for arm in arms
    }
    marker_rate = _rate(false_counts['marker_only'], false_denominator)
    adjudicator_rate = _rate(false_counts['marker_adjudicator'], false_denominator)
    improved = marker_rate is not None and adjudicator_rate is not None and adjudicator_rate < marker_rate
    return {
        'trials_per_case': trials,
        'arms': list(arms),
        'cases': results,
        'measurement': {
            'conversation_trials': len(evaluations),
            'stage2_calls': stage2_calls,
            'false_create_direct_denominator': false_denominator,
            'false_create_direct_count': false_counts,
            'false_create_direct_rate': {arm: _rate(false_counts[arm], false_denominator) for arm in arms},
            'command_create_direct_denominator': command_denominator,
            'command_create_direct_count': command_counts,
            'command_create_direct_rate': {arm: _rate(command_counts[arm], command_denominator) for arm in arms},
            'adjudicator_ambient_no_interference_trials': sum(
                evaluation['adjudicator_ambient_items_set_equal'] is True for evaluation in evaluations
            ),
            'baseline_marker_ambient_distribution_comparisons': ambient_distribution_comparisons,
            'baseline_marker_ambient_distribution_match_cases': sum(
                comparison['distributions_match'] is True for comparison in ambient_distribution_comparisons.values()
            ),
            'control_unchanged_trials': sum(evaluation['control_arms_set_equal'] is True for evaluation in evaluations),
            'paired_split_trials': sum(evaluation['paired_invocations_split'] is True for evaluation in evaluations),
        },
        'shipping_decision': {
            'false_create_direct_improved_vs_marker_only': improved,
            'recommendation': 'keep_adjudicator' if improved else 'drop_adjudicator',
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
            case_trials.append({'outputs': pair, 'evaluation': evaluation})
        results[case['id']] = case_trials
    return {
        'trials_per_case': trials,
        'cases': results,
        'measurement': {
            'paired_trials': len(evaluations),
            'discard_changed': sum(result['discard_changed'] for result in evaluations),
            'marked_kept': sum(result['marked_kept'] for result in evaluations),
            'marked_discarded': sum(not result['marked_kept'] for result in evaluations),
            'marked_all_kept': all(result['marked_kept'] for result in evaluations),
            'unmarked_discarded': sum(result['unmarked_discarded'] for result in evaluations),
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
