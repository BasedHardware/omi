"""Shadow speech cannot become clean through missing rows, ages or serving mix."""

from copy import deepcopy

import pytest

from scripts.rollout.batch_shadow_t2 import census as _census, combine as _combine, query_pages, serving_clock
from scripts.rollout.batch_quality_gate import epoch

NOW = '2026-10-29T06:30:00+00:00'
START = '2026-10-29T06:00:00+00:00'


def terminal(speech, outcome='recovered', **extra):
    return {
        **dict(
            shadow=True,
            outcome=outcome,
            vad='worker',
            speech_seconds=speech,
            speech_loss_seconds=0 if outcome == 'recovered' else speech,
            projection_status='planned' if outcome == 'recovered' else 'empty' if outcome == 'empty' else None,
            created_at=epoch(START),
        ),
        **extra,
    }


def base():
    return {
        'at': NOW,
        'observed_through': NOW,
        'verdict': 'CLEAN',
        'hard3': dict(T1='CLEAN', T2='UNKNOWN', T4='CLEAN'),
        'alerts': ['serving_percent_drift'],
        'reasons': [],
    }


def combine(base, counts, read_time, since, now, prior=None):
    return _combine(base, counts, read_time, since, now, prior, history=[base])


def census(rows, overdue, since=None):
    return _census(rows, overdue, epoch(START) if since is None else since)


def test_preactivation_work_settling_now_cannot_fill_shadow_floor():
    rows = [terminal(4000, created_at=epoch(START) - 1), terminal(1000)]
    counts = census(rows, [])
    assert counts['terminal_unrecovered_speech_denominator_seconds'] == 1000
    assert combine(base(), counts, NOW, START, NOW)['hard3']['T2'] == 'UNKNOWN'


def test_missing_admission_time_is_unknown_not_qualified_speech():
    row = terminal(4000)
    row.pop('created_at')
    counts = census([row], [])
    assert counts['terminal_unrecovered_speech_unknown_units'] == 1
    assert counts['terminal_unrecovered_speech_denominator_seconds'] == 0


def test_settled_rows_in_creation_query_are_not_overdue():
    assert census([terminal(4000)], [{'state': 'settled'}])['overdue_units'] == 0


def test_empty_or_sparse_shadow_never_uses_serving_denominator():
    serving = base()
    serving['t2_speech_denominator_seconds'] = 999999
    for rows in ([], [terminal(3599)]):
        result = combine(serving, census(rows, []), NOW, START, NOW)
        assert result['hard3']['T2'] == 'UNKNOWN'
        assert result['t2_speech_denominator_seconds'] < 3600


def test_complete_measured_shadow_qualifies_t2_and_keeps_soft_alerts():
    result = combine(base(), census([terminal(3600)], []), NOW, START, NOW)
    assert result['hard3'] == dict(T1='CLEAN', T2='CLEAN', T4='CLEAN')
    assert result['t2_evidence_scope'] == 'shadow25'
    assert result['alerts'] == ['serving_percent_drift']
    # A supplied earlier start does not backdate continuous clean samples.
    assert result['observation_started_at'] == NOW and result['observed_samples'] == 1


@pytest.mark.parametrize(
    'bad',
    [
        terminal(1, vad='unknown'),
        terminal(1, outcome='new_kind'),
        terminal(float('nan')),
        terminal(1, speech_loss_seconds=2),
    ],
)
def test_unknown_metadata_never_certifies_clean(bad):
    result = combine(base(), census([terminal(4000), bad], []), NOW, START, NOW)
    assert result['hard3']['T2'] == 'UNKNOWN'


def test_drop_is_expected_unscheduled_work_but_overdue_attempt_blocks():
    rows = [terminal(4000), {'shadow': True, 'outcome': 'dropped', 'vad': 'unknown'}]
    assert census(rows, [])['dropped_units'] == 1
    result = combine(base(), census(rows, [{'state': 'running'}]), NOW, START, NOW)
    assert result['hard3']['T2'] == 'UNKNOWN'


def test_known_shadow_loss_and_serving_harm_remain_hard():
    result = combine(base(), census([terminal(4000), terminal(121, 'error')], []), NOW, START, NOW)
    assert result['hard3']['T2'] == 'TRIP' and 'T2_lost_unit_over120s' in result['reasons']
    serving = base()
    serving['hard3']['T2'] = 'TRIP'
    serving['reasons'] = ['T2_lost_unit_over120s']
    assert combine(serving, census([terminal(4000)], []), NOW, START, NOW)['hard3']['T2'] == 'TRIP'


def test_stale_serving_evidence_does_not_borrow_fresh_shadow_clock():
    serving = base()
    serving['observed_through'] = START
    result = combine(serving, census([terminal(4000)], []), NOW, START, NOW)
    assert set(result['hard3'].values()) == {'UNKNOWN'}


def test_serving_clock_uses_actual_history_not_unknown_serving_t2_floor():
    history = []
    for minute in range(0, 31, 2):
        row = base()
        row['observed_through'] = f'2026-10-29T06:{minute:02}:00+00:00'
        history.append(row)
    result = _combine(base(), census([terminal(4000)], []), NOW, START, NOW, history=history)
    assert result['observation_started_at'] == START and result['observed_samples'] == 16
    assert set(result['hard3'].values()) == {'CLEAN'}
    # A single current row cannot reconstruct a missing half-hour.
    assert serving_clock([base()], START, NOW)['observation_started_at'] == NOW
    history[10]['hard3']['T2'] = 'TRIP'
    clock = serving_clock(history, START, NOW)
    assert clock['observation_started_at'] == '2026-10-29T06:22:00+00:00'


def test_missing_serving_history_never_claims_continuity():
    result = _combine(base(), census([terminal(4000)], []), NOW, START, NOW)
    assert set(result['hard3'].values()) == {'UNKNOWN'}


def test_inference_only_success_never_certifies_projection_speech():
    old = terminal(4000)
    old.pop('projection_status')
    result = combine(base(), census([old], []), NOW, START, NOW)
    assert result['hard3']['T2'] == 'UNKNOWN' and result['t2_speech_denominator_seconds'] == 0


def test_queries_use_masks_stable_read_time_and_no_identifier_output():
    calls = []

    def call(body):
        calls.append(deepcopy(body))
        return [
            {
                'readTime': NOW,
                'document': {
                    'name': 'private/synthetic-id',
                    'fields': {'settled_at': {'doubleValue': 123}, 'shadow': {'booleanValue': True}},
                },
            }
        ]

    rows, clock = query_pages(call, 'batch_pipeline_prod_shadow_jobs', 'settled_at', 0, 123, read_time=NOW)
    assert rows == [{'settled_at': 123, 'shadow': True}] and clock == NOW
    assert calls[0]['readTime'] == NOW
    fields = {f['fieldPath'] for f in calls[0]['structuredQuery']['select']['fields']}
    assert not fields & {'owner_id', 'owner_key', 'item', 'transcript_segments', 'audio_uri'}
    assert 'private/synthetic-id' not in repr(rows)


def test_full_page_budget_fails_closed_instead_of_using_partial_counts():
    response = [{'readTime': NOW, 'document': {'name': 'private/id', 'fields': {'settled_at': {'doubleValue': 123}}}}]
    with pytest.raises(ValueError, match='page_budget'):
        query_pages(lambda _: response, 'batch_pipeline_prod_shadow_jobs', 'settled_at', 0, 123, max_rows=1)
