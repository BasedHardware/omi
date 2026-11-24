"""Post-deploy check measures settlements after release, including old admissions."""

import pytest

from scripts.batch_recovery_large_held_check import summarize


def document(duration=3357, settled=200, reason='provider_failed'):
    recovery = {'failure': {'mapValue': {'fields': {'reason': {'stringValue': reason}}}}}
    if settled is not None:
        recovery['settled_at'] = {'doubleValue': settled}
    return {
        'document': {
            'fields': {
                'duration_seconds': {'doubleValue': duration},
                'recovery': {'mapValue': {'fields': recovery}},
            }
        }
    }


def test_counts_new_settlements_and_excludes_old_short_or_other_failures():
    result = summarize(
        [
            document(),
            document(settled=99),
            document(duration=3277),
            document(reason='empty_asr'),
            document(settled=None),
            {},
        ],
        100,
    )
    assert result == {'new_large_provider_failed_held': 1, 'unknown_settlement_time': 1}


def test_query_error_never_reports_clean():
    with pytest.raises(ValueError, match='query error'):
        summarize([{'error': {'status': 'PERMISSION_DENIED'}}], 100)
