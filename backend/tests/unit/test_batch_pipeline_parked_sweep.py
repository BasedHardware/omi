from utils.batch_pipeline.parked_sweep import ParkedSweep, summarize


def test_sample_uses_bounded_reasons_and_age_buckets():
    rows = [
        {'owner_key': 'a', 'quarantined_at': 1, 'quarantine_diagnostic': {'worker_reason': ['malformed']}},
        {
            'owner_key': 'a',
            'quarantined_at': 99_000,
            'recovery': {'started_at': 1, 'failure': {'reason': 'empty_asr'}},
        },
        {'quarantined_at': float('nan'), 'quarantine_diagnostic': {'exception_class': 'lease_expired'}},
    ]
    assert summarize(rows, 100_000) == {
        'oldest_age_seconds': 99_999,
        'distinct_known_owners': 1,
        'reason_age': [
            {'reason': 'lease_expired', 'age_bucket': 'unknown', 'units': 1},
            {'reason': 'post_submit_empty_asr', 'age_bucket': 'under_1h', 'units': 1},
            {'reason': 'unknown', 'age_bucket': 'at_least_24h', 'units': 1},
        ],
    }


def test_disabled_sweep_does_not_access_store(monkeypatch):
    monkeypatch.setenv('BATCH_PARKED_JOB_SWEEPER_ENABLED', 'false')
    sweep = ParkedSweep(None)
    sweep.tick(100_000)
    assert sweep.last_attempt_hour == -1
