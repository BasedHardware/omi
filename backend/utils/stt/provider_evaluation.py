from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ProviderGateThresholds:
    max_transcript_word_error_rate: float = 0.35
    max_segment_count_delta_ratio: float = 0.75
    max_average_timestamp_drift_seconds: float = 2.5
    max_low_confidence_identity_rate: float = 0.50
    max_fallback_rate: float = 0.10
    max_failure_rate: float = 0.05
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
        '| Cases | Failures | Warnings | Avg WER | Avg timestamp drift | AssemblyAI cost | Deepgram cost |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
        (
            f"| {report.get('case_count', 0)} | {report.get('failure_count', 0)} | "
            f"{report.get('warning_count', 0)} | {_fmt_pct(aggregate.get('average_word_error_rate'))} | "
            f"{_fmt_seconds(aggregate.get('average_timestamp_drift_seconds'))} | "
            f"${aggregate.get('assemblyai_estimated_cost_usd', 0.0):.4f} | "
            f"${aggregate.get('deepgram_estimated_cost_usd', 0.0):.4f} |"
        ),
        '',
        '| Case | WER | Segments DG/AAI | Clusters DG/AAI | Unknown AAI | Low-conf AAI | Fallback AAI | Gates |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |',
    ]
    for case in report.get('cases', []):
        deepgram = case['providers']['deepgram']
        assemblyai = case['providers']['assemblyai']
        gates = ', '.join(
            f"{gate['severity']}:{gate['metric']}" for gate in case.get('gates', []) if gate['severity'] != 'pass'
        )
        lines.append(
            f"| {case['id']} | {_fmt_pct(case['comparison']['transcript_word_error_rate'])} | "
            f"{deepgram['segment_count']}/{assemblyai['segment_count']} | "
            f"{deepgram['speaker_cluster_count']}/{assemblyai['speaker_cluster_count']} | "
            f"{assemblyai['unknown_speaker_cluster_count']} | "
            f"{_fmt_pct(assemblyai['low_confidence_identity_rate'])} | "
            f"{_fmt_pct(assemblyai['fallback_rate'])} | {gates or 'pass'} |"
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
        'providers': {'deepgram': _public_summary(deepgram), 'assemblyai': _public_summary(assemblyai)},
        'comparison': comparison,
        'gates': gates,
    }


def summarize_provider_output(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    transcript = payload.get('transcript') or payload.get('result') or payload
    segments = _extract_segments(transcript)
    ledger = payload.get('ledger') or payload.get('rollup') or {}
    clusters = _speaker_clusters(segments)
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
    identity_confidences = [
        segment.get('speaker_identity_confidence')
        for segment in segments
        if segment.get('speaker_identity_confidence') is not None
    ]
    low_confidence_count = sum(1 for confidence in identity_confidences if float(confidence) < 0.50)
    return {
        'provider': provider,
        'segments': segments,
        'text': _transcript_text(segments),
        'segment_count': len(segments),
        'word_count': sum(len(_words(segment.get('text', ''))) for segment in segments),
        'speaker_cluster_count': len(clusters),
        'identified_speaker_cluster_count': len(identified_clusters),
        'unknown_speaker_cluster_count': max(len(clusters) - len(identified_clusters), 0),
        'low_confidence_identity_count': low_confidence_count,
        'low_confidence_identity_rate': (
            low_confidence_count / len(identity_confidences) if identity_confidences else 0.0
        ),
        'raw_audio_seconds': _number_from_ledger(ledger, 'raw_audio_seconds'),
        'speech_active_seconds': _number_from_ledger(ledger, 'speech_active_seconds'),
        'billable_seconds': _number_from_ledger(ledger, 'billable_seconds'),
        'estimated_cost_usd': _number_from_ledger(ledger, 'estimated_cost_usd'),
        'retry_count': _number_from_ledger(ledger, 'retry_count'),
        'fallback_count': _number_from_ledger(ledger, 'fallback_count'),
        'fallback_rate': _rate_from_ledger(ledger, 'fallback_count'),
        'failure_rate': _failure_rate_from_ledger(ledger),
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
        ),
        _threshold_gate(
            'average_timestamp_drift_seconds',
            comparison['average_timestamp_drift_seconds'],
            thresholds.max_average_timestamp_drift_seconds,
            'warning',
        ),
        _threshold_gate(
            'assemblyai_low_confidence_identity_rate',
            assemblyai['low_confidence_identity_rate'],
            thresholds.max_low_confidence_identity_rate,
            'warning',
        ),
        _threshold_gate(
            'assemblyai_fallback_rate', assemblyai['fallback_rate'], thresholds.max_fallback_rate, 'failure'
        ),
        _threshold_gate('assemblyai_failure_rate', assemblyai['failure_rate'], thresholds.max_failure_rate, 'failure'),
    ]
    if thresholds.require_instrumentation:
        for provider in (deepgram, assemblyai):
            if not provider['has_instrumentation']:
                gates.append(
                    {
                        'metric': f"{provider['provider']}_instrumentation",
                        'severity': 'warning',
                        'value': None,
                        'threshold': 'ledger_or_rollup_required',
                        'message': 'missing provider ledger or rollup metrics',
                    }
                )
    return gates


def _threshold_gate(metric: str, value: float, threshold: float, severity: str) -> dict[str, Any]:
    passed = value <= threshold
    return {
        'metric': metric,
        'severity': 'pass' if passed else severity,
        'value': value,
        'threshold': threshold,
        'message': 'within threshold' if passed else f'{value:.4f} exceeds {threshold:.4f}',
    }


def _number_from_ledger(ledger: dict[str, Any], field: str) -> float:
    value = ledger.get(field, 0.0)
    if isinstance(value, dict) and '__increment' in value:
        value = value['__increment']
    return float(value or 0.0)


def _rate_from_ledger(ledger: dict[str, Any], count_field: str) -> float:
    denominator = float(ledger.get('run_count') or 1.0)
    return _number_from_ledger(ledger, count_field) / denominator


def _failure_rate_from_ledger(ledger: dict[str, Any]) -> float:
    status_counts = ledger.get('status_counts') or {}
    failed = status_counts.get('failed') or status_counts.get('failure') or 0
    denominator = float(ledger.get('run_count') or 1.0)
    return float(failed) / denominator


def _aggregate_case_reports(case_reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not case_reports:
        return {}
    return {
        'average_word_error_rate': _average(case['comparison']['transcript_word_error_rate'] for case in case_reports),
        'average_timestamp_drift_seconds': _average(
            case['comparison']['average_timestamp_drift_seconds'] for case in case_reports
        ),
        'assemblyai_estimated_cost_usd': sum(
            case['providers']['assemblyai']['estimated_cost_usd'] for case in case_reports
        ),
        'deepgram_estimated_cost_usd': sum(
            case['providers']['deepgram']['estimated_cost_usd'] for case in case_reports
        ),
        'assemblyai_billable_seconds': sum(
            case['providers']['assemblyai']['billable_seconds'] for case in case_reports
        ),
        'deepgram_billable_seconds': sum(case['providers']['deepgram']['billable_seconds'] for case in case_reports),
    }


def _average(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _fmt_pct(value) -> str:
    if value is None:
        return 'n/a'
    return f'{float(value) * 100:.1f}%'


def _fmt_seconds(value) -> str:
    if value is None:
        return 'n/a'
    return f'{float(value):.2f}s'
