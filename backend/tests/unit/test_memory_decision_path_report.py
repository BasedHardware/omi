from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts import memory_decision_path_report as measurement

FIXTURE = Path(__file__).parent / 'fixtures' / 'memory_decision_path_events.jsonl'


def _fixture_report() -> dict[str, Any]:
    entries, syntax_errors = measurement.load_entries(str(FIXTURE))
    events, invalid = measurement.parse_events(entries, syntax_errors=syntax_errors)
    return measurement.build_report(
        events,
        source={'kind': 'fixture'},
        input_entries=len(entries),
        invalid_entries=invalid,
    )


def _capture(uid: str, memory_id: str, *, disagreed: bool) -> dict[str, Any]:
    return {
        'stage': 'capture',
        'uid': uid,
        'memory_id': memory_id,
        'conversation_id': f'conv-{memory_id}',
        'capture_regime': 'omi',
        'subject_attribution': 'third_party' if disagreed else 'user',
        'model_about': 'primary_user',
        'attribution_disagreed': disagreed,
        'distinct_speaker_ids': 2,
    }


def test_fixture_covers_regimes_speaker_buckets_and_every_promotion_failure_mode() -> None:
    entries, syntax_errors = measurement.load_entries(str(FIXTURE))
    events, invalid = measurement.parse_events(entries, syntax_errors=syntax_errors)

    assert not invalid
    assert {event['capture_regime'] for event in events if event['stage'] == 'capture'} == {
        'desktop',
        'omi',
        'phone',
    }
    assert {
        measurement.speaker_bucket(event['distinct_speaker_ids']) for event in events if event['stage'] == 'capture'
    } == {'0', '1-3', '4-6', '7-10', '11-15', '16+'}
    assert {event['attribution_disagreed'] for event in events if event['stage'] == 'capture'} == {False, True}
    assert {event['status'] for event in events if event['stage'] == 'promotion' and event['status'] != 'applied'} == {
        'candidate_hydration_failed',
        'flex_deferred',
        'decision_invalid',
        'recurrence_handoff_failed',
        'apply_failed',
        'batch_aborted',
    }


def test_report_deduplicates_capture_and_uses_explicit_denominators() -> None:
    report = _fixture_report()

    assert report['status'] == 'complete'
    assert report['quality']['duplicate_capture_events_removed'] == 1
    assert report['totals'] == {
        'capture_memories': 8,
        'capture_conversations': 7,
        'capture_users': 3,
        'promotion_applied_decisions': 5,
        'promotion_failure_attempts': 6,
        'promotion_users': 3,
    }
    disagreement = report['capture']['attribution_disagreed']['true']
    assert disagreement['event_weighted']['numerator'] == 3
    assert disagreement['event_weighted']['denominator'] == 8
    assert disagreement['event_weighted']['rate'] == pytest.approx(3 / 8)
    assert disagreement['user_macro']['denominator_users'] == 3
    assert disagreement['user_macro']['rate'] == pytest.approx(((2 / 3) + (1 / 4) + 0) / 3)
    assert disagreement['event_weighted']['ci95']['lower'] < 3 / 8
    assert disagreement['event_weighted']['ci95']['upper'] > 3 / 8


def test_capture_regime_and_speaker_bucket_metrics_use_the_named_grain() -> None:
    report = _fixture_report()
    capture = report['capture']

    assert capture['regime_memory_share']['desktop']['event_weighted']['numerator'] == 3
    assert capture['regime_memory_share']['desktop']['event_weighted']['denominator'] == 8
    assert capture['regime_conversation_share']['desktop']['event_weighted']['numerator'] == 2
    assert capture['regime_conversation_share']['desktop']['event_weighted']['denominator'] == 7
    assert capture['disagreement_by_regime']['desktop']['event_weighted']['numerator'] == 1
    assert capture['disagreement_by_regime']['desktop']['event_weighted']['denominator'] == 3
    assert capture['disagreement_by_regime']['desktop']['user_macro']['rate'] == pytest.approx(0.25)
    assert capture['disagreement_by_distinct_speaker_ids']['11-15']['event_weighted']['numerator'] == 1
    assert capture['disagreement_by_distinct_speaker_ids']['11-15']['event_weighted']['denominator'] == 1


def test_user_macro_rate_prevents_one_heavy_user_from_becoming_the_population() -> None:
    raw = [_capture('heavy', f'm-{index}', disagreed=False) for index in range(10)]
    raw.append(_capture('light', 'm-light', disagreed=True))
    events, invalid = measurement.parse_events(raw)
    report = measurement.build_report(
        events,
        source={'kind': 'test'},
        input_entries=len(raw),
        invalid_entries=invalid,
    )

    metric = report['capture']['attribution_disagreed']['true']
    assert metric['event_weighted']['rate'] == pytest.approx(1 / 11)
    assert metric['event_weighted']['denominator'] == 11
    assert metric['user_macro']['rate'] == pytest.approx(0.5)
    assert metric['user_macro']['denominator_users'] == 2


def test_promotion_failures_do_not_inflate_applied_rejections() -> None:
    promotion = _fixture_report()['promotion']

    reject = promotion['applied_routes']['reject']['event_weighted']
    assert (reject['numerator'], reject['denominator']) == (2, 5)
    rejection_rule = promotion['rejection_reason_codes']['create:other_speaker:third_party:weak_or_none'][
        'event_weighted'
    ]
    assert (rejection_rule['numerator'], rejection_rule['denominator']) == (2, 2)
    assert promotion['failure_statuses']['decision_invalid']['event_weighted']['denominator'] == 6
    assert 'output_invalid:partition_mismatch' in promotion['failure_reason_codes']


def test_machine_output_contains_no_user_ids_and_every_rate_has_a_denominator() -> None:
    report = _fixture_report()
    encoded = json.dumps(report, sort_keys=True)
    assert '"u1"' not in encoded
    assert '"u2"' not in encoded
    assert '"u3"' not in encoded

    def check(value: Any) -> None:
        if isinstance(value, dict):
            if 'rate' in value:
                assert 'denominator' in value or 'denominator_users' in value
            for nested in value.values():
                check(nested)
        elif isinstance(value, list):
            for nested in value:
                check(nested)

    check(report)


def test_human_output_prints_ratios_and_states_unavailable_diarization_metrics() -> None:
    rendered = measurement.render_human(_fixture_report())

    assert '37.5% (3/8 memories' in rendered
    assert 'user mean 30.6% across 3 users' in rendered
    assert 'owner-silent, multi-owner, or clean/degraded diarization' in rendered
    assert 'Operational failure statuses (attempt grain)' in rendered


def test_empty_input_is_honest_and_emits_no_rates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty = tmp_path / 'empty.jsonl'
    empty.write_text('', encoding='utf-8')

    exit_code = measurement.main(['--input', str(empty), '--format', 'json'])

    assert exit_code == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'empty'
    assert report['totals']['capture_memories'] == 0
    assert report['capture']['attribution_disagreed'] == {}
    assert report['quality']['input_entries'] == 0


def test_invalid_only_input_is_incomplete_not_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    invalid_input = tmp_path / 'invalid.jsonl'
    invalid_input.write_text(json.dumps({'textPayload': f'{measurement.EVENT_NAME} not-json'}), encoding='utf-8')

    exit_code = measurement.main(['--input', str(invalid_input), '--format', 'json'])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert report['status'] == 'incomplete'
    assert report['quality']['invalid_entries'] == 1


def test_invalid_entries_are_counted_instead_of_guessed() -> None:
    entries = [
        _capture('u1', 'valid', disagreed=False),
        {**_capture('u1', 'bad-speakers', disagreed=False), 'distinct_speaker_ids': True},
        {'textPayload': f'{measurement.EVENT_NAME} not-json'},
    ]
    events, invalid = measurement.parse_events(entries)

    assert len(events) == 1
    assert invalid == {
        'capture_distinct_speaker_ids_invalid': 1,
        'event_json_invalid': 1,
    }


def test_cloud_query_is_bounded_and_truncation_fails_closed(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # --project falls back to GOOGLE_CLOUD_PROJECT before DEFAULT_PROJECT, and other
    # suites set that variable process-wide at import time (test_working_observations_
    # extractor.py does `os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test")`).
    # Asserting the built-in default therefore has to own the environment, or this
    # passes alone and fails whenever one of those files is collected first.
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    captured: dict[str, Any] = {}

    def fetcher(**kwargs: Any) -> list[Any]:
        captured.update(kwargs)
        return [_capture('u1', 'm1', disagreed=False), _capture('u2', 'm2', disagreed=True)]

    exit_code = measurement.main(
        [
            '--start',
            '2026-08-20T00:00:00Z',
            '--end',
            '2026-08-21T00:00:00Z',
            '--limit',
            '2',
            '--format',
            'json',
        ],
        fetcher=fetcher,
    )

    assert exit_code == 3
    assert captured['project'] == 'based-hardware'
    assert captured['start'] == datetime(2026, 8, 20, tzinfo=timezone.utc)
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'incomplete'
    assert report['quality']['query_truncated'] is True
    assert report['quality']['input_entries'] == 2
    assert report['quality']['query_limit'] == 2


def test_gcloud_reader_uses_text_and_json_payloads_without_shell_interpolation() -> None:
    captured: dict[str, Any] = {}

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured['command'] = command
        captured['kwargs'] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout='[]', stderr='')

    entries = measurement.fetch_cloud_logging_entries(
        project='test-project',
        start=datetime(2026, 8, 20, tzinfo=timezone.utc),
        end=datetime(2026, 8, 21, tzinfo=timezone.utc),
        limit=123,
        run=run,
    )

    assert entries == []
    assert captured['command'][:3] == ['gcloud', 'logging', 'read']
    assert 'textPayload:"canonical_memory_decision_path.v1"' in captured['command'][3]
    assert 'jsonPayload.message:"canonical_memory_decision_path.v1"' in captured['command'][3]
    assert '--limit=123' in captured['command']
    assert captured['kwargs'] == {'check': False, 'capture_output': True, 'text': True}
