from dataclasses import dataclass
from typing import Any, Optional

PRODUCTION_STRATEGIES = ('always_deepgram', 'always_assemblyai', 'current_policy', 'shadow_only')
PROVIDER_BY_STRATEGY = {
    'always_deepgram': 'deepgram',
    'always_assemblyai': 'assemblyai',
    'current_policy': 'assemblyai',
    'shadow_only': 'deepgram',
}
ASSEMBLYAI_COST_PER_HOUR_USD = 0.17
DEEPGRAM_COST_PER_HOUR_USD = 0.408


@dataclass(frozen=True)
class ProviderGateThresholds:
    max_transcript_word_error_rate: float = 0.35
    max_segment_count_delta_ratio: float = 0.75
    max_average_timestamp_drift_seconds: float = 2.5
    max_low_confidence_identity_rate: float = 0.50
    max_fallback_rate: float = 0.10
    max_failure_rate: float = 0.05
    min_speaker_word_purity: float = 0.95
    min_assemblyai_purity_delta_vs_deepgram: float = -0.05
    max_speaker_inflation_ratio: float = 1.75
    max_empty_transcript_rate: float = 0.05
    max_timeout_error_rate: float = 0.05
    max_latency_ratio_vs_deepgram: float = 2.0
    max_cost_ratio_vs_deepgram: float = 3.0
    require_instrumentation: bool = True


def build_comparison_report(
    cases: list[dict[str, Any]],
    thresholds: Optional[ProviderGateThresholds] = None,
) -> dict[str, Any]:
    thresholds = thresholds or ProviderGateThresholds()
    case_reports = [_compare_case(case, thresholds) for case in cases]
    failures = [gate for case in case_reports for gate in case['gates'] if gate['severity'] == 'failure']
    warnings = [gate for case in case_reports for gate in case['gates'] if gate['severity'] == 'warning']
    return {
        'status': 'failed' if failures else 'passed',
        'case_count': len(case_reports),
        'failure_count': len(failures),
        'warning_count': len(warnings),
        'aggregate': _aggregate_case_reports(case_reports),
        'strategies': _strategy_rollups(case_reports),
        'assemblyai_gap_report': _assemblyai_gap_report(case_reports),
        'cases': case_reports,
    }


def evaluate_report_gates(report: dict[str, Any], fail_on_warning: bool = False) -> tuple[bool, list[str]]:
    messages = []
    for case in report.get('cases', []):
        for gate in case.get('gates', []):
            if gate.get('severity') == 'failure' or (fail_on_warning and gate.get('severity') == 'warning'):
                messages.append(f"{case.get('id', 'unknown')}: {gate.get('metric')} {gate.get('message')}")
    return not messages, messages


def compact_markdown_report(report: dict[str, Any]) -> str:
    aggregate = report.get('aggregate', {})
    lines = [
        f"# STT Provider Evaluation: {report.get('status', 'unknown').upper()}",
        '',
        '| Cases | Failures | Warnings | Avg WER | Avg timestamp drift | AAI purity | DG purity | AAI cost/hr | DG cost/hr |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
        (
            f"| {report.get('case_count', 0)} | {report.get('failure_count', 0)} | "
            f"{report.get('warning_count', 0)} | {_fmt_pct(aggregate.get('average_word_error_rate'))} | "
            f"{_fmt_seconds(aggregate.get('average_timestamp_drift_seconds'))} | "
            f"{_fmt_pct(aggregate.get('assemblyai_speaker_word_purity'))} | "
            f"{_fmt_pct(aggregate.get('deepgram_speaker_word_purity'))} | "
            f"${aggregate.get('assemblyai_estimated_cost_per_hour_usd', 0.0):.3f} | "
            f"${aggregate.get('deepgram_estimated_cost_per_hour_usd', 0.0):.3f} |"
        ),
        '',
        '## Strategy Rollup',
        '',
        '| Strategy | Provider | Purity | Covered speakers | App speakers | Inflation | Empty | Fallback | Timeout/error | Cost/hr |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    for name, strategy in report.get('strategies', {}).items():
        lines.append(
            f"| {name} | {strategy.get('provider', 'mixed')} | "
            f"{_fmt_pct(strategy.get('speaker_word_purity'))} | "
            f"{strategy.get('covered_speaker_count', 0):.1f} | "
            f"{strategy.get('app_visible_speaker_count', 0):.1f} | "
            f"{strategy.get('speaker_inflation_ratio', 0.0):.2f} | "
            f"{_fmt_pct(strategy.get('empty_transcript_rate'))} | "
            f"{_fmt_pct(strategy.get('fallback_rate'))} | "
            f"{_fmt_pct(strategy.get('timeout_error_rate'))} | "
            f"${strategy.get('estimated_cost_per_hour_usd', 0.0):.3f} |"
        )
    lines.extend(
        [
            '',
            '## Cases',
            '',
            '| Case | Scenario | WER | Purity DG/AAI | App speakers DG/AAI | Splits AAI | Recon AAI | Fallback AAI | Gates |',
            '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |',
        ]
    )
    for case in report.get('cases', []):
        deepgram = case['providers']['deepgram']
        assemblyai = case['providers']['assemblyai']
        gates = ', '.join(
            f"{gate['severity']}:{gate['metric']}" for gate in case.get('gates', []) if gate['severity'] != 'pass'
        )
        lines.append(
            f"| {case['id']} | {case.get('scenario', 'unspecified')} | "
            f"{_fmt_pct(case['comparison']['transcript_word_error_rate'])} | "
            f"{_fmt_pct(deepgram['speaker_word_purity'])}/{_fmt_pct(assemblyai['speaker_word_purity'])} | "
            f"{deepgram['app_visible_speaker_count']}/{assemblyai['app_visible_speaker_count']} | "
            f"{assemblyai['split_count']} | "
            f"{assemblyai['accepted_reconciliation_count']}/{assemblyai['rejected_reconciliation_count']} | "
            f"{_fmt_pct(assemblyai['fallback_rate'])} | {gates or 'pass'} |"
        )
    gap_report = report.get('assemblyai_gap_report') or {}
    lines.extend(['', '## AssemblyAI Gap Report', ''])
    lines.append(f"Status: {gap_report.get('status', 'unknown')}.")
    limiting_scenarios = gap_report.get('limiting_scenarios') or []
    for item in limiting_scenarios:
        lines.append(
            f"- {item['scenario']}: {item['metric']} ({item['assemblyai_value']} vs {item['deepgram_value']}) "
            f"- likely cause: {item['likely_cause']}; mitigation: {item['mitigation']}"
        )
    if not limiting_scenarios:
        lines.append('- No material AssemblyAI gap detected in offline synthetic/saved-output fixtures.')
    lines.extend(
        [
            '',
            'Synthetic and saved-output gates are necessary but insufficient for default health decisions. '
            'Use this gap report to track AssemblyAI default readiness and rollback thresholds with privacy-safe real-session evidence.',
        ]
    )
    return '\n'.join(lines)


def _compare_case(case: dict[str, Any], thresholds: ProviderGateThresholds) -> dict[str, Any]:
    deepgram = summarize_provider_output('deepgram', case.get('deepgram') or {})
    assemblyai = summarize_provider_output('assemblyai', case.get('assemblyai') or {})
    comparison = {
        'transcript_word_error_rate': _word_error_rate(deepgram['text'], assemblyai['text']),
        'segment_count_delta': assemblyai['segment_count'] - deepgram['segment_count'],
        'segment_count_delta_ratio': _ratio_delta(assemblyai['segment_count'], deepgram['segment_count']),
        'word_count_delta': assemblyai['word_count'] - deepgram['word_count'],
        'word_count_delta_ratio': _ratio_delta(assemblyai['word_count'], deepgram['word_count']),
        'average_timestamp_drift_seconds': _average_timestamp_drift_seconds(
            deepgram['segments'], assemblyai['segments']
        ),
    }
    gates = _evaluate_case_gates(deepgram, assemblyai, comparison, thresholds)
    return {
        'id': case.get('id') or case.get('case_id') or 'unknown',
        'scenario': case.get('scenario') or case.get('type') or 'unspecified',
        'current_policy_provider': case.get('current_policy_provider') or 'assemblyai',
        'providers': {'deepgram': _public_summary(deepgram), 'assemblyai': _public_summary(assemblyai)},
        'comparison': comparison,
        'gates': gates,
    }


def summarize_provider_output(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    transcript = payload.get('transcript') or payload.get('result') or payload
    segments = _extract_segments(transcript)
    ledger = payload.get('ledger') or payload.get('rollup') or {}
    clusters = _speaker_clusters(segments)
    oracle_speakers = _oracle_speakers(segments)
    word_count = sum(len(_words(segment.get('text', ''))) for segment in segments)
    raw_audio_seconds = _number_from_ledger(ledger, 'raw_audio_seconds')
    billable_seconds = _number_from_ledger(ledger, 'billable_seconds')
    estimated_cost_usd = _estimated_cost_usd(provider, ledger, billable_seconds or raw_audio_seconds)
    latency_seconds = _latency_seconds(ledger)
    timeout_error_count = _timeout_error_count(ledger)
    run_count = _run_count(ledger)
    identified_clusters = {
        _cluster_id(segment)
        for segment in segments
        if _cluster_id(segment)
        and (
            segment.get('person_id')
            or segment.get('is_user') is True
            or segment.get('speaker_identity_state') in ('identified', 'user')
        )
    }
    low_confidence_clusters = set()
    for segment in segments:
        cluster_id = _cluster_id(segment)
        if not cluster_id:
            continue
        state = segment.get('speaker_identity_state')
        confidence = segment.get('speaker_identity_confidence')
        if state == 'unknown':
            low_confidence_clusters.add(cluster_id)
        elif confidence is not None and float(confidence) < 0.50:
            low_confidence_clusters.add(cluster_id)
    return {
        'provider': provider,
        'segments': segments,
        'text': _transcript_text(segments),
        'segment_count': len(segments),
        'word_count': word_count,
        'speaker_cluster_count': len(clusters),
        'provider_cluster_count': len(clusters),
        'covered_speaker_count': len(oracle_speakers),
        'app_visible_speaker_count': len(clusters),
        'speaker_inflation_ratio': (len(clusters) / len(oracle_speakers) if oracle_speakers else 0.0),
        'speaker_word_purity': _speaker_word_purity(segments),
        'empty_transcript_rate': 1.0 if word_count == 0 else 0.0,
        'identified_speaker_cluster_count': len(identified_clusters),
        'unknown_speaker_cluster_count': max(len(clusters) - len(identified_clusters), 0),
        'low_confidence_identity_count': len(low_confidence_clusters),
        'low_confidence_identity_rate': (len(low_confidence_clusters) / len(clusters) if clusters else 0.0),
        'raw_audio_seconds': raw_audio_seconds,
        'speech_active_seconds': _number_from_ledger(ledger, 'speech_active_seconds'),
        'billable_seconds': billable_seconds,
        'estimated_cost_usd': estimated_cost_usd,
        'estimated_cost_per_hour_usd': _cost_per_hour(estimated_cost_usd, billable_seconds or raw_audio_seconds),
        'latency_seconds': latency_seconds,
        'runtime_seconds': _runtime_seconds(ledger, latency_seconds),
        'retry_count': _number_from_ledger(ledger, 'retry_count'),
        'split_count': _number_from_ledger(ledger, 'split_count'),
        'accepted_reconciliation_count': _number_from_ledger(ledger, 'accepted_reconciliation_count'),
        'rejected_reconciliation_count': _number_from_ledger(ledger, 'rejected_reconciliation_count'),
        'fallback_count': _number_from_ledger(ledger, 'fallback_count'),
        'fallback_rate': _rate_from_ledger(ledger, 'fallback_count'),
        'failure_rate': _failure_rate_from_ledger(ledger),
        'timeout_error_count': timeout_error_count,
        'timeout_error_rate': timeout_error_count / run_count,
        'has_instrumentation': bool(ledger),
    }


def _public_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if key not in ('segments', 'text')}


def _extract_segments(transcript: Any) -> list[dict[str, Any]]:
    if isinstance(transcript, dict) and isinstance(transcript.get('segments'), list):
        return [_normalize_segment(segment) for segment in transcript['segments']]
    if isinstance(transcript, list):
        return [_normalize_segment(segment) for segment in transcript]
    if isinstance(transcript, dict) and isinstance(transcript.get('utterances'), list) and transcript.get('utterances'):
        return [_normalize_provider_utterance(utterance, transcript) for utterance in transcript['utterances']]
    if isinstance(transcript, dict) and isinstance(transcript.get('words'), list):
        return _segments_from_words(transcript['words'], transcript)
    if isinstance(transcript, dict) and transcript.get('text'):
        return [_normalize_segment(transcript)]
    return []


def _normalize_segment(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        'text': str(segment.get('text') or segment.get('transcript') or '').strip(),
        'start': float(segment.get('start') or 0.0),
        'end': float(segment.get('end') or 0.0),
        'provider_cluster_id': segment.get('provider_cluster_id'),
        'provider_speaker_label': segment.get('provider_speaker_label'),
        'speaker': segment.get('speaker'),
        'oracle_speaker': segment.get('oracle_speaker') or segment.get('expected_speaker'),
        'person_id': segment.get('person_id'),
        'is_user': segment.get('is_user'),
        'speaker_identity_state': segment.get('speaker_identity_state'),
        'speaker_identity_confidence': segment.get('speaker_identity_confidence'),
    }


def _normalize_provider_utterance(utterance: dict[str, Any], transcript: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_segment(utterance)
    normalized['provider_cluster_id'] = utterance.get('provider_cluster_id')
    normalized['provider_speaker_label'] = utterance.get('speaker_label') or utterance.get('provider_speaker_label')
    normalized['stt_provider'] = transcript.get('provider')
    normalized['stt_model'] = transcript.get('model')
    return normalized


def _segments_from_words(words: list[dict[str, Any]], transcript: dict[str, Any]) -> list[dict[str, Any]]:
    segments = []
    current = None
    for word in words:
        cluster_id = word.get('provider_cluster_id') or word.get('speaker')
        if current is None or current.get('provider_cluster_id') != cluster_id:
            if current:
                current['text'] = ' '.join(current.pop('_words'))
                segments.append(current)
            current = {
                'text': '',
                '_words': [],
                'start': float(word.get('start') or 0.0),
                'end': float(word.get('end') or 0.0),
                'provider_cluster_id': cluster_id,
                'provider_speaker_label': word.get('speaker_label') or word.get('provider_speaker_label'),
                'oracle_speaker': word.get('oracle_speaker') or word.get('expected_speaker'),
                'stt_provider': transcript.get('provider'),
                'stt_model': transcript.get('model'),
            }
        current['_words'].append(str(word.get('text') or word.get('word') or ''))
        current['end'] = float(word.get('end') or current['end'])
    if current:
        current['text'] = ' '.join(current.pop('_words'))
        segments.append(current)
    return segments


def _speaker_clusters(segments: list[dict[str, Any]]) -> set[str]:
    return {cluster_id for cluster_id in (_cluster_id(segment) for segment in segments) if cluster_id}


def _cluster_id(segment: dict[str, Any]) -> Optional[str]:
    return segment.get('provider_cluster_id') or segment.get('provider_speaker_label') or segment.get('speaker')


def _transcript_text(segments: list[dict[str, Any]]) -> str:
    return ' '.join(segment.get('text', '') for segment in segments).strip()


def _words(text: str) -> list[str]:
    normalized = ''.join(character.lower() if character.isalnum() else ' ' for character in text)
    return [word for word in normalized.split() if word]


def _word_error_rate(reference: str, hypothesis: str) -> float:
    reference_words = _words(reference)
    hypothesis_words = _words(hypothesis)
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    return _levenshtein_distance(reference_words, hypothesis_words) / len(reference_words)


def _levenshtein_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for index, reference_word in enumerate(reference, start=1):
        current = [index]
        for other_index, hypothesis_word in enumerate(hypothesis, start=1):
            current.append(
                min(
                    previous[other_index] + 1,
                    current[other_index - 1] + 1,
                    previous[other_index - 1] + (reference_word != hypothesis_word),
                )
            )
        previous = current
    return previous[-1]


def _ratio_delta(value: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if value == 0 else 1.0
    return abs(value - baseline) / baseline


def _average_timestamp_drift_seconds(reference: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> float:
    pair_count = min(len(reference), len(candidate))
    if not pair_count:
        return 0.0
    drift = 0.0
    for index in range(pair_count):
        drift += abs(reference[index].get('start', 0.0) - candidate[index].get('start', 0.0))
        drift += abs(reference[index].get('end', 0.0) - candidate[index].get('end', 0.0))
    return drift / (pair_count * 2)


def _evaluate_case_gates(
    deepgram: dict[str, Any],
    assemblyai: dict[str, Any],
    comparison: dict[str, Any],
    thresholds: ProviderGateThresholds,
) -> list[dict[str, Any]]:
    empty_transcript_threshold = (
        1.0 if deepgram['word_count'] == 0 and assemblyai['word_count'] == 0 else thresholds.max_empty_transcript_rate
    )
    gates = [
        _threshold_gate(
            'transcript_word_error_rate',
            comparison['transcript_word_error_rate'],
            thresholds.max_transcript_word_error_rate,
            'failure',
        ),
        _threshold_gate(
            'segment_count_delta_ratio',
            comparison['segment_count_delta_ratio'],
            thresholds.max_segment_count_delta_ratio,
            'failure',
            gate_group='speaker_safety',
        ),
        _threshold_gate(
            'average_timestamp_drift_seconds',
            comparison['average_timestamp_drift_seconds'],
            thresholds.max_average_timestamp_drift_seconds,
            'warning',
            gate_group='rollout_readiness',
        ),
        _threshold_gate(
            'assemblyai_low_confidence_identity_rate',
            assemblyai['low_confidence_identity_rate'],
            thresholds.max_low_confidence_identity_rate,
            'warning',
            gate_group='speaker_safety',
        ),
        _threshold_gate(
            'assemblyai_fallback_rate', assemblyai['fallback_rate'], thresholds.max_fallback_rate, 'failure'
        ),
        _threshold_gate('assemblyai_failure_rate', assemblyai['failure_rate'], thresholds.max_failure_rate, 'failure'),
        _threshold_gate(
            'assemblyai_speaker_word_purity',
            assemblyai['speaker_word_purity'],
            thresholds.min_speaker_word_purity,
            'failure',
            minimum=True,
            gate_group='speaker_safety',
        ),
        _threshold_gate(
            'assemblyai_speaker_inflation_ratio',
            assemblyai['speaker_inflation_ratio'],
            thresholds.max_speaker_inflation_ratio,
            'failure',
            gate_group='speaker_safety',
        ),
        _threshold_gate(
            'assemblyai_empty_transcript_rate',
            assemblyai['empty_transcript_rate'],
            empty_transcript_threshold,
            'failure',
            gate_group='default_viability',
        ),
        _threshold_gate(
            'assemblyai_timeout_error_rate',
            assemblyai['timeout_error_rate'],
            thresholds.max_timeout_error_rate,
            'failure',
            gate_group='rollout_readiness',
        ),
        _threshold_gate(
            'assemblyai_purity_delta_vs_deepgram',
            assemblyai['speaker_word_purity'] - deepgram['speaker_word_purity'],
            thresholds.min_assemblyai_purity_delta_vs_deepgram,
            'failure',
            minimum=True,
            gate_group='speaker_safety',
        ),
        _threshold_gate(
            'assemblyai_latency_ratio_vs_deepgram',
            _safe_ratio(assemblyai['latency_seconds'], deepgram['latency_seconds']),
            thresholds.max_latency_ratio_vs_deepgram,
            'warning',
            gate_group='rollout_readiness',
        ),
        _threshold_gate(
            'assemblyai_cost_ratio_vs_deepgram',
            _safe_ratio(assemblyai['estimated_cost_per_hour_usd'], deepgram['estimated_cost_per_hour_usd']),
            thresholds.max_cost_ratio_vs_deepgram,
            'warning',
            gate_group='default_viability',
        ),
    ]
    if thresholds.require_instrumentation:
        for provider in (deepgram, assemblyai):
            if not provider['has_instrumentation']:
                gates.append(
                    {
                        'metric': f"{provider['provider']}_instrumentation",
                        'severity': 'warning',
                        'gate_group': 'rollout_readiness',
                        'value': None,
                        'threshold': 'ledger_or_rollup_required',
                        'message': 'missing provider ledger or rollup metrics',
                    }
                )
    return gates


def _threshold_gate(
    metric: str,
    value: float,
    threshold: float,
    severity: str,
    minimum: bool = False,
    gate_group: str = 'default_viability',
) -> dict[str, Any]:
    passed = value >= threshold if minimum else value <= threshold
    direction = 'below' if minimum else 'exceeds'
    return {
        'metric': metric,
        'severity': 'pass' if passed else severity,
        'gate_group': gate_group,
        'value': value,
        'threshold': threshold,
        'message': 'within threshold' if passed else f'{value:.4f} {direction} {threshold:.4f}',
    }


def _number_from_ledger(ledger: dict[str, Any], field: str) -> float:
    value = ledger.get(field, 0.0)
    if isinstance(value, dict) and '__increment' in value:
        value = value['__increment']
    return float(value or 0.0)


def _run_count(ledger: dict[str, Any]) -> float:
    return float(ledger.get('run_count') or 1.0)


def _estimated_cost_usd(provider: str, ledger: dict[str, Any], billed_seconds: float) -> float:
    recorded = _number_from_ledger(ledger, 'estimated_cost_usd')
    if recorded:
        return recorded
    if provider == 'assemblyai':
        return billed_seconds / 3600 * ASSEMBLYAI_COST_PER_HOUR_USD
    if provider == 'deepgram':
        return billed_seconds / 3600 * DEEPGRAM_COST_PER_HOUR_USD
    return 0.0


def _cost_per_hour(cost: float, seconds: float) -> float:
    return cost / seconds * 3600 if seconds else 0.0


def _latency_seconds(ledger: dict[str, Any]) -> float:
    for field in ('latency_seconds', 'duration_seconds', 'elapsed_seconds'):
        value = _number_from_ledger(ledger, field)
        if value:
            return value
    return 0.0


def _runtime_seconds(ledger: dict[str, Any], latency_seconds: float) -> float:
    for field in ('runtime_seconds', 'wall_time_seconds'):
        value = _number_from_ledger(ledger, field)
        if value:
            return value
    return latency_seconds


def _timeout_error_count(ledger: dict[str, Any]) -> float:
    status_counts = ledger.get('status_counts') or {}
    return float(
        _number_from_ledger(ledger, 'timeout_count')
        + _number_from_ledger(ledger, 'error_count')
        + status_counts.get('timeout', 0)
        + status_counts.get('timed_out', 0)
        + status_counts.get('failed', 0)
        + status_counts.get('failure', 0)
    )


def _rate_from_ledger(ledger: dict[str, Any], count_field: str) -> float:
    denominator = float(ledger.get('run_count') or 1.0)
    return _number_from_ledger(ledger, count_field) / denominator


def _failure_rate_from_ledger(ledger: dict[str, Any]) -> float:
    status_counts = ledger.get('status_counts') or {}
    failed = status_counts.get('failed') or status_counts.get('failure') or 0
    denominator = float(ledger.get('run_count') or 1.0)
    return float(failed) / denominator


def _oracle_speakers(segments: list[dict[str, Any]]) -> set[str]:
    return {str(segment['oracle_speaker']) for segment in segments if segment.get('oracle_speaker')}


def _speaker_word_purity(segments: list[dict[str, Any]]) -> float:
    cluster_counts: dict[str, dict[str, int]] = {}
    total_words = 0
    for segment in segments:
        cluster_id = _cluster_id(segment)
        oracle_speaker = segment.get('oracle_speaker')
        if not cluster_id or not oracle_speaker:
            continue
        word_count = len(_words(segment.get('text', '')))
        if word_count == 0:
            continue
        total_words += word_count
        cluster_counts.setdefault(str(cluster_id), {})
        cluster_counts[str(cluster_id)][str(oracle_speaker)] = (
            cluster_counts[str(cluster_id)].get(str(oracle_speaker), 0) + word_count
        )
    if not total_words:
        return 1.0
    pure_words = sum(max(counts.values()) for counts in cluster_counts.values())
    return pure_words / total_words


def _safe_ratio(value: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if value == 0 else 999.0
    return value / baseline


def _aggregate_case_reports(case_reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not case_reports:
        return {}
    assemblyai = [case['providers']['assemblyai'] for case in case_reports]
    deepgram = [case['providers']['deepgram'] for case in case_reports]
    assemblyai_seconds = sum(provider['billable_seconds'] or provider['raw_audio_seconds'] for provider in assemblyai)
    deepgram_seconds = sum(provider['billable_seconds'] or provider['raw_audio_seconds'] for provider in deepgram)
    assemblyai_cost = sum(provider['estimated_cost_usd'] for provider in assemblyai)
    deepgram_cost = sum(provider['estimated_cost_usd'] for provider in deepgram)
    return {
        'average_word_error_rate': _average(case['comparison']['transcript_word_error_rate'] for case in case_reports),
        'average_timestamp_drift_seconds': _average(
            case['comparison']['average_timestamp_drift_seconds'] for case in case_reports
        ),
        'assemblyai_speaker_word_purity': _weighted_average(assemblyai, 'speaker_word_purity', 'word_count'),
        'deepgram_speaker_word_purity': _weighted_average(deepgram, 'speaker_word_purity', 'word_count'),
        'assemblyai_estimated_cost_usd': assemblyai_cost,
        'deepgram_estimated_cost_usd': deepgram_cost,
        'assemblyai_estimated_cost_per_hour_usd': _cost_per_hour(assemblyai_cost, assemblyai_seconds),
        'deepgram_estimated_cost_per_hour_usd': _cost_per_hour(deepgram_cost, deepgram_seconds),
        'assemblyai_billable_seconds': sum(provider['billable_seconds'] for provider in assemblyai),
        'deepgram_billable_seconds': sum(provider['billable_seconds'] for provider in deepgram),
    }


def _strategy_rollups(case_reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {strategy: _strategy_rollup(case_reports, strategy) for strategy in PRODUCTION_STRATEGIES}


def _strategy_rollup(case_reports: list[dict[str, Any]], strategy: str) -> dict[str, Any]:
    selected = []
    providers = set()
    for case in case_reports:
        provider_name = PROVIDER_BY_STRATEGY.get(strategy) or case.get('current_policy_provider') or 'assemblyai'
        providers.add(provider_name)
        selected.append(case['providers'][provider_name])
    cost = sum(provider['estimated_cost_usd'] for provider in selected)
    seconds = sum(provider['billable_seconds'] or provider['raw_audio_seconds'] for provider in selected)
    return {
        'provider': next(iter(providers)) if len(providers) == 1 else 'mixed',
        'speaker_word_purity': _weighted_average(selected, 'speaker_word_purity', 'word_count'),
        'covered_speaker_count': _average(provider['covered_speaker_count'] for provider in selected),
        'app_visible_speaker_count': _average(provider['app_visible_speaker_count'] for provider in selected),
        'speaker_inflation_ratio': _average(provider['speaker_inflation_ratio'] for provider in selected),
        'split_count': sum(provider['split_count'] for provider in selected),
        'accepted_reconciliation_count': sum(provider['accepted_reconciliation_count'] for provider in selected),
        'rejected_reconciliation_count': sum(provider['rejected_reconciliation_count'] for provider in selected),
        'fallback_count': sum(provider['fallback_count'] for provider in selected),
        'provider_cluster_count': sum(provider['provider_cluster_count'] for provider in selected),
        'empty_transcript_rate': _average(provider['empty_transcript_rate'] for provider in selected),
        'latency_seconds': _average(provider['latency_seconds'] for provider in selected),
        'runtime_seconds': _average(provider['runtime_seconds'] for provider in selected),
        'timeout_error_rate': _average(provider['timeout_error_rate'] for provider in selected),
        'fallback_rate': _average(provider['fallback_rate'] for provider in selected),
        'failure_rate': _average(provider['failure_rate'] for provider in selected),
        'estimated_cost_usd': cost,
        'estimated_cost_per_hour_usd': _cost_per_hour(cost, seconds),
    }


def _assemblyai_gap_report(case_reports: list[dict[str, Any]]) -> dict[str, Any]:
    limiting_scenarios = []
    for case in case_reports:
        deepgram = case['providers']['deepgram']
        assemblyai = case['providers']['assemblyai']
        candidates = [
            (
                'speaker_word_purity',
                assemblyai['speaker_word_purity'],
                deepgram['speaker_word_purity'],
                assemblyai['speaker_word_purity'] < deepgram['speaker_word_purity'] - 0.02,
            ),
            (
                'covered_speaker_count',
                assemblyai['covered_speaker_count'],
                deepgram['covered_speaker_count'],
                assemblyai['covered_speaker_count'] < deepgram['covered_speaker_count'],
            ),
            (
                'empty_transcript_rate',
                assemblyai['empty_transcript_rate'],
                deepgram['empty_transcript_rate'],
                assemblyai['empty_transcript_rate'] > deepgram['empty_transcript_rate'],
            ),
            (
                'latency_seconds',
                assemblyai['latency_seconds'],
                deepgram['latency_seconds'],
                assemblyai['latency_seconds'] > deepgram['latency_seconds'] * 2 and assemblyai['latency_seconds'] > 0,
            ),
            (
                'timeout_error_rate',
                assemblyai['timeout_error_rate'],
                deepgram['timeout_error_rate'],
                assemblyai['timeout_error_rate'] > deepgram['timeout_error_rate'],
            ),
            (
                'estimated_cost_per_hour_usd',
                assemblyai['estimated_cost_per_hour_usd'],
                deepgram['estimated_cost_per_hour_usd'],
                assemblyai['estimated_cost_per_hour_usd'] > deepgram['estimated_cost_per_hour_usd'] * 3
                and deepgram['estimated_cost_per_hour_usd'] > 0,
            ),
        ]
        for metric, assemblyai_value, deepgram_value, limited in candidates:
            if limited:
                limiting_scenarios.append(
                    {
                        'case_id': case['id'],
                        'scenario': case.get('scenario') or case['id'],
                        'metric': metric,
                        'assemblyai_value': round(float(assemblyai_value), 4),
                        'deepgram_value': round(float(deepgram_value), 4),
                        'likely_cause': _likely_cause(metric),
                        'mitigation': _mitigation(metric),
                    }
                )
                break
    return {
        'status': 'limited' if limiting_scenarios else 'no_material_gap_detected',
        'limiting_scenarios': limiting_scenarios,
    }


def _likely_cause(metric: str) -> str:
    return {
        'speaker_word_purity': 'provider-local clusters mix speakers before Omi identity matching',
        'covered_speaker_count': 'provider diarization missed a speaker or no-speech gating discarded speech',
        'empty_transcript_rate': 'low-signal/no-speech handling produced an empty or failed transcript',
        'latency_seconds': 'AssemblyAI async job latency exceeds Deepgram for this workload shape',
        'timeout_error_rate': 'provider timeout or retry exhaustion path is not default-safe',
        'estimated_cost_per_hour_usd': 'provider billable duration or pricing is too high for default background volume',
    }.get(metric, 'AssemblyAI trails the Deepgram comparator on this gate')


def _mitigation(metric: str) -> str:
    return {
        'speaker_word_purity': 'keep split-before-match enabled and gate rollout on fragmentation plus purity budgets',
        'covered_speaker_count': 'use Deepgram fallback for affected low-signal cases until AssemblyAI closes coverage',
        'empty_transcript_rate': 'preserve no-speech detection and fallback controls before default promotion',
        'latency_seconds': 'keep latency SLO alerts and fallback controls before expanding default traffic',
        'timeout_error_rate': 'use Deepgram fallback and provider health gates from TICKET-027',
        'estimated_cost_per_hour_usd': 'review billable seconds, requested add-ons, and provider pricing before changing defaults',
    }.get(metric, 'capture in TICKET-028 rollout tradeoffs before promoting AssemblyAI')


def _average(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _weighted_average(items: list[dict[str, Any]], value_field: str, weight_field: str) -> float:
    denominator = sum(float(item.get(weight_field) or 0.0) for item in items)
    if denominator == 0:
        return _average(item.get(value_field, 0.0) for item in items)
    return (
        sum(float(item.get(value_field) or 0.0) * float(item.get(weight_field) or 0.0) for item in items) / denominator
    )


def _fmt_pct(value) -> str:
    if value is None:
        return 'n/a'
    return f'{float(value) * 100:.1f}%'


def _fmt_seconds(value) -> str:
    if value is None:
        return 'n/a'
    return f'{float(value):.2f}s'
