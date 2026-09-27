"""The deployment must reject stale same-name sequencer alert policies."""

from scripts.verify_sync_backfill_alert_policy import check_policy

FILTER = (
    'metric.type="logging.googleapis.com/user/sync_backfill_uid_sequencer_stall" AND resource.type="cloud_run_revision"'
)
CHANNELS = ['projects/p/notificationChannels/one', 'projects/p/notificationChannels/two']


def _policy(condition):
    return {'conditions': [condition], 'notificationChannels': CHANNELS, 'enabled': True}


def test_threshold_policy_requires_exact_filter_duration_and_channels():
    policy = _policy({'conditionThreshold': {'filter': FILTER, 'duration': '0s'}})
    assert check_policy(policy, condition='threshold', filter_text=FILTER, duration_seconds=0, channels=CHANNELS) == []
    policy['conditions'][0]['conditionThreshold']['filter'] = 'stale-filter'
    policy['notificationChannels'] = CHANNELS[:1]
    assert check_policy(policy, condition='threshold', filter_text=FILTER, duration_seconds=0, channels=CHANNELS) == [
        'condition filter differs',
        'notification channels differ',
    ]


def test_absence_policy_requires_ten_minute_duration():
    policy = _policy({'conditionAbsent': {'filter': FILTER, 'duration': '600s'}})
    assert check_policy(policy, condition='absent', filter_text=FILTER, duration_seconds=600, channels=CHANNELS) == []
    policy['conditions'][0]['conditionAbsent']['duration'] = '300s'
    assert check_policy(policy, condition='absent', filter_text=FILTER, duration_seconds=600, channels=CHANNELS) == [
        'condition duration differs'
    ]


def test_policy_rejects_missing_condition_or_disabled_policy():
    assert check_policy({}, condition='threshold', filter_text=FILTER, duration_seconds=0, channels=CHANNELS) == [
        'expected exactly one alert condition'
    ]
    policy = _policy({'conditionThreshold': {'filter': FILTER, 'duration': '0s'}})
    policy['enabled'] = False
    assert check_policy(policy, condition='threshold', filter_text=FILTER, duration_seconds=0, channels=CHANNELS) == [
        'policy is disabled'
    ]
