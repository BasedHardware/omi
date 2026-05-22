#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from utils.stt.provider_evaluation import (  # noqa: E402
    ProviderGateThresholds,
    build_comparison_report,
    compact_markdown_report,
    evaluate_report_gates,
)

try:
    from utils.stt.provider_service import _transcribe_bytes_with_provider, _transcribe_url_with_provider  # noqa: E402
    from utils.stt.providers import STTProviderName, STTWorkload  # noqa: E402

    LIVE_PROVIDER_IMPORT_ERROR = None
except ModuleNotFoundError as e:
    _transcribe_bytes_with_provider = None
    _transcribe_url_with_provider = None
    STTProviderName = None
    STTWorkload = None
    LIVE_PROVIDER_IMPORT_ERROR = e


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Compare Deepgram and AssemblyAI background transcription outputs and apply rollout gates.'
    )
    parser.add_argument(
        '--manifest',
        action='append',
        default=[],
        help='JSON manifest with cases, fixtures, optional audio_url/audio_file, and ledger/rollup files.',
    )
    parser.add_argument('--live', action='store_true', help='Run providers for manifest audio_url/audio_file cases.')
    parser.add_argument('--uid', default=None, help='Optional uid used to write provider ledger rows during live runs.')
    parser.add_argument(
        '--conversation-prefix', default='stt-eval', help='Conversation id prefix for live ledger rows.'
    )
    parser.add_argument('--output-json', default=None, help='Write full JSON report to this path.')
    parser.add_argument('--output-md', default=None, help='Write compact Markdown report to this path.')
    parser.add_argument('--fail-on-warning', action='store_true', help='Return non-zero for warning gates too.')
    parser.add_argument('--max-wer', type=float, default=ProviderGateThresholds.max_transcript_word_error_rate)
    parser.add_argument(
        '--max-segment-delta-ratio', type=float, default=ProviderGateThresholds.max_segment_count_delta_ratio
    )
    parser.add_argument(
        '--max-timestamp-drift', type=float, default=ProviderGateThresholds.max_average_timestamp_drift_seconds
    )
    parser.add_argument(
        '--max-low-confidence-rate', type=float, default=ProviderGateThresholds.max_low_confidence_identity_rate
    )
    parser.add_argument('--max-fallback-rate', type=float, default=ProviderGateThresholds.max_fallback_rate)
    parser.add_argument('--max-failure-rate', type=float, default=ProviderGateThresholds.max_failure_rate)
    parser.add_argument(
        '--allow-missing-instrumentation',
        action='store_true',
        help='Do not warn when fixture cases omit provider ledger or rollup metrics.',
    )
    args = parser.parse_args()

    if not args.manifest:
        parser.error('at least one --manifest is required')

    thresholds = ProviderGateThresholds(
        max_transcript_word_error_rate=args.max_wer,
        max_segment_count_delta_ratio=args.max_segment_delta_ratio,
        max_average_timestamp_drift_seconds=args.max_timestamp_drift,
        max_low_confidence_identity_rate=args.max_low_confidence_rate,
        max_fallback_rate=args.max_fallback_rate,
        max_failure_rate=args.max_failure_rate,
        require_instrumentation=not args.allow_missing_instrumentation,
    )
    cases = []
    skipped_live_cases = []
    for manifest_path in args.manifest:
        manifest = _load_json(Path(manifest_path))
        manifest_cases = manifest.get('cases') if isinstance(manifest, dict) else manifest
        for index, case in enumerate(manifest_cases):
            prepared = _prepare_case(case, Path(manifest_path).parent)
            if args.live and _case_has_audio(case):
                live_case = _run_live_case(
                    case,
                    base_path=Path(manifest_path).parent,
                    uid=args.uid,
                    conversation_id=f'{args.conversation_prefix}-{case.get("id", index)}',
                )
                if live_case:
                    prepared = live_case
                else:
                    skipped_live_cases.append(case.get('id') or str(index))
            cases.append(prepared)

    report = build_comparison_report(cases, thresholds)
    if skipped_live_cases:
        report['skipped_live_cases'] = skipped_live_cases
    markdown = compact_markdown_report(report)
    print(markdown)

    if args.output_json:
        _write_text(Path(args.output_json), json.dumps(report, indent=2, sort_keys=True) + '\n')
    if args.output_md:
        _write_text(Path(args.output_md), markdown + '\n')

    passed, messages = evaluate_report_gates(report, fail_on_warning=args.fail_on_warning)
    if not passed:
        print('\nGate messages:', file=sys.stderr)
        for message in messages:
            print(f'- {message}', file=sys.stderr)
        return 1
    return 0


def _prepare_case(case: dict[str, Any], base_path: Path) -> dict[str, Any]:
    prepared = {'id': case.get('id') or case.get('case_id')}
    prepared['deepgram'] = _load_provider_payload(case, base_path, 'deepgram')
    prepared['assemblyai'] = _load_provider_payload(case, base_path, 'assemblyai')
    return prepared


def _load_provider_payload(case: dict[str, Any], base_path: Path, provider: str) -> dict[str, Any]:
    payload = {}
    inline = case.get(provider)
    if inline:
        payload.update(inline)
    fixture_path = case.get(f'{provider}_fixture') or case.get(f'{provider}_transcript')
    if fixture_path:
        payload['transcript'] = _load_json(_resolve_path(base_path, fixture_path))
    ledger_path = case.get(f'{provider}_ledger') or case.get(f'{provider}_rollup')
    if ledger_path:
        payload['ledger'] = _load_json(_resolve_path(base_path, ledger_path))
    return payload


def _run_live_case(
    case: dict[str, Any],
    base_path: Path,
    uid: Optional[str],
    conversation_id: str,
) -> Optional[dict[str, Any]]:
    if LIVE_PROVIDER_IMPORT_ERROR:
        print(
            f"Skipping live case {case.get('id', 'unknown')}: provider dependencies are unavailable "
            f"({LIVE_PROVIDER_IMPORT_ERROR}).",
            file=sys.stderr,
        )
        return None
    if not _credentials_available():
        print(
            f"Skipping live case {case.get('id', 'unknown')}: " 'DEEPGRAM_API_KEY and ASSEMBLYAI_API_KEY are required.',
            file=sys.stderr,
        )
        return None
    workload = STTWorkload(case.get('workload') or STTWorkload.background.value)
    language = case.get('language')
    raw_audio_seconds = float(case.get('raw_audio_seconds') or 0.0)
    common_kwargs = {
        'workload': workload,
        'uid': uid,
        'conversation_id': conversation_id,
        'language': language,
        'model': case.get('model') or 'nova-3',
        'raw_audio_seconds': raw_audio_seconds,
        'return_language': bool(case.get('return_language', False)),
        'diarize': bool(case.get('diarize', True)),
    }
    if case.get('audio_url'):
        deepgram = _transcribe_url_with_provider(STTProviderName.deepgram, case['audio_url'], **common_kwargs)
        assemblyai = _transcribe_url_with_provider(
            STTProviderName.assemblyai,
            case['audio_url'],
            **{**common_kwargs, 'model': case.get('assemblyai_model') or 'universal-2'},
        )
    else:
        audio_bytes = _resolve_path(base_path, case['audio_file']).read_bytes()
        deepgram = _transcribe_bytes_with_provider(STTProviderName.deepgram, audio_bytes, **common_kwargs)
        assemblyai = _transcribe_bytes_with_provider(
            STTProviderName.assemblyai,
            audio_bytes,
            **{**common_kwargs, 'model': case.get('assemblyai_model') or 'universal-2'},
        )
        del audio_bytes
    return {
        'id': case.get('id') or conversation_id,
        'deepgram': {'transcript': {'segments': [segment.dict() for segment in deepgram.segments]}},
        'assemblyai': {'transcript': {'segments': [segment.dict() for segment in assemblyai.segments]}},
    }


def _case_has_audio(case: dict[str, Any]) -> bool:
    return bool(case.get('audio_url') or case.get('audio_file'))


def _credentials_available() -> bool:
    return bool(os.getenv('DEEPGRAM_API_KEY') and os.getenv('ASSEMBLYAI_API_KEY'))


def _load_json(path: Path) -> Any:
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _resolve_path(base_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_path / path


if __name__ == '__main__':
    raise SystemExit(main())
