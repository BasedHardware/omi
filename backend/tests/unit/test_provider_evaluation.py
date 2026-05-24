import json
from pathlib import Path

from utils.stt.provider_evaluation import (
    ProviderGateThresholds,
    build_comparison_report,
    compact_markdown_report,
    evaluate_report_gates,
    summarize_provider_output,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / 'fixtures' / 'stt_provider_eval'


def _load_fixture_case() -> dict:
    manifest = json.loads((FIXTURE_DIR / 'manifest.json').read_text())
    case = manifest['cases'][0]
    return {
        'id': case['id'],
        'deepgram': {
            'transcript': json.loads((FIXTURE_DIR / case['deepgram_fixture']).read_text()),
            'ledger': json.loads((FIXTURE_DIR / case['deepgram_rollup']).read_text()),
        },
        'assemblyai': {
            'transcript': json.loads((FIXTURE_DIR / case['assemblyai_fixture']).read_text()),
            'ledger': json.loads((FIXTURE_DIR / case['assemblyai_rollup']).read_text()),
        },
    }


def _load_manifest_cases() -> list[dict]:
    manifest = json.loads((FIXTURE_DIR / 'manifest.json').read_text())
    cases = []
    for case in manifest['cases']:
        prepared = {
            'id': case['id'],
            'scenario': case.get('scenario'),
            'current_policy_provider': case.get('current_policy_provider'),
        }
        for provider in ('deepgram', 'assemblyai'):
            if provider in case:
                prepared[provider] = case[provider]
                continue
            prepared[provider] = {
                'transcript': json.loads((FIXTURE_DIR / case[f'{provider}_fixture']).read_text()),
                'ledger': json.loads((FIXTURE_DIR / case[f'{provider}_rollup']).read_text()),
            }
        cases.append(prepared)
    return cases


def test_fixture_report_passes_and_includes_cost_identity_and_timing_metrics():
    report = build_comparison_report([_load_fixture_case()])

    assert report['status'] == 'passed'
    assert report['case_count'] == 1
    assert report['aggregate']['assemblyai_estimated_cost_usd'] == 0.00023611
    case = report['cases'][0]
    assert case['comparison']['transcript_word_error_rate'] == 0.0
    assert case['comparison']['average_timestamp_drift_seconds'] > 0.0
    assert case['providers']['assemblyai']['speaker_cluster_count'] == 2
    assert case['providers']['assemblyai']['speaker_word_purity'] == 1.0
    assert case['providers']['assemblyai']['identified_speaker_cluster_count'] == 1
    assert case['providers']['assemblyai']['unknown_speaker_cluster_count'] == 1
    assert case['providers']['assemblyai']['low_confidence_identity_rate'] == 0.5
    assert all(gate['severity'] == 'pass' for gate in case['gates'])


def test_manifest_report_includes_strategy_rollups_gap_report_and_fragmentation_metrics():
    report = build_comparison_report(_load_manifest_cases())

    assert report['status'] == 'passed'
    assert set(report['strategies']) == {'always_deepgram', 'always_assemblyai', 'current_policy', 'shadow_only'}
    assert report['strategies']['always_assemblyai']['provider'] == 'assemblyai'
    assert report['strategies']['shadow_only']['provider'] == 'deepgram'
    assert report['strategies']['current_policy']['provider'] == 'assemblyai'
    assert report['strategies']['always_assemblyai']['split_count'] >= 2
    assert report['strategies']['always_assemblyai']['estimated_cost_per_hour_usd'] > 0
    assert report['assemblyai_gap_report']['status'] == 'limited'
    assert any(
        item['scenario'] == 'saved_real_policy_router_outputs'
        and item['metric'] in {'speaker_word_purity', 'estimated_cost_per_hour_usd'}
        for item in report['assemblyai_gap_report']['limiting_scenarios']
    )
    assert any(gate['gate_group'] == 'speaker_safety' for case in report['cases'] for gate in case['gates'])


def test_threshold_failures_are_reported_for_transcript_drift_and_fallback():
    case = _load_fixture_case()
    case['assemblyai']['transcript']['segments'][0]['text'] = 'Completely unrelated output.'
    case['assemblyai']['ledger']['fallback_count'] = 1

    report = build_comparison_report(
        [case],
        ProviderGateThresholds(max_transcript_word_error_rate=0.05, max_fallback_rate=0.10),
    )
    passed, messages = evaluate_report_gates(report)

    assert report['status'] == 'failed'
    assert not passed
    assert any('transcript_word_error_rate' in message for message in messages)
    assert any('assemblyai_fallback_rate' in message for message in messages)


def test_missing_instrumentation_is_warning_not_failure_by_default():
    case = _load_fixture_case()
    case['assemblyai'].pop('ledger')

    report = build_comparison_report([case])
    passed, messages = evaluate_report_gates(report)
    strict_passed, strict_messages = evaluate_report_gates(report, fail_on_warning=True)

    assert report['status'] == 'passed'
    assert passed
    assert messages == []
    assert not strict_passed
    assert any('assemblyai_instrumentation' in message for message in strict_messages)


def test_provider_result_words_are_grouped_into_cluster_segments():
    payload = {
        'provider': 'assemblyai',
        'model': 'universal-2',
        'words': [
            {'text': 'hello', 'start': 0.0, 'end': 0.2, 'provider_cluster_id': 'A'},
            {'text': 'there', 'start': 0.2, 'end': 0.5, 'provider_cluster_id': 'A'},
            {'text': 'hi', 'start': 0.7, 'end': 0.9, 'provider_cluster_id': 'B'},
        ],
    }

    summary = summarize_provider_output('assemblyai', {'transcript': payload})

    assert summary['segment_count'] == 2
    assert summary['word_count'] == 3
    assert summary['speaker_cluster_count'] == 2


def test_unknown_identity_counts_as_low_confidence():
    summary = summarize_provider_output(
        'assemblyai',
        {
            'transcript': {
                'segments': [
                    {
                        'text': 'hello',
                        'provider_cluster_id': 'A',
                        'speaker_identity_state': 'unknown',
                        'speaker_identity_confidence': None,
                    }
                ]
            }
        },
    )

    assert summary['low_confidence_identity_count'] == 1


def test_low_confidence_identity_counts_clusters_not_segments():
    summary = summarize_provider_output(
        'assemblyai',
        {
            'transcript': {
                'segments': [
                    {
                        'text': 'hello',
                        'provider_cluster_id': 'A',
                        'speaker_identity_state': 'unknown',
                    },
                    {
                        'text': 'again',
                        'provider_cluster_id': 'A',
                        'speaker_identity_state': 'unknown',
                    },
                    {
                        'text': 'there',
                        'provider_cluster_id': 'B',
                        'speaker_identity_state': 'identified',
                        'speaker_identity_confidence': 0.9,
                    },
                ]
            }
        },
    )

    assert summary['low_confidence_identity_count'] == 1
    assert summary['low_confidence_identity_rate'] == 0.5


def test_compact_markdown_report_is_review_friendly():
    report = build_comparison_report(_load_manifest_cases())
    markdown = compact_markdown_report(report)

    assert '# STT Provider Evaluation: PASSED' in markdown
    assert 'fixture_good_meeting' in markdown
    assert 'Strategy Rollup' in markdown
    assert 'AssemblyAI Gap Report' in markdown
    assert 'AssemblyAI default readiness' in markdown
