"""Sync backfill alert policy verification and bounded routing reconciliation."""

import json
import subprocess

from scripts.reconcile_sync_backfill_alert_policy import reconcile_policy_channels
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


def test_rate_policy_checks_threshold_and_window_only_when_declared():
    policy = _policy(
        {
            'conditionThreshold': {
                'filter': FILTER,
                'duration': '0s',
                'thresholdValue': 30,
                'aggregations': [{'alignmentPeriod': '1800s', 'perSeriesAligner': 'ALIGN_SUM'}],
            }
        }
    )
    kwargs = dict(condition='threshold', filter_text=FILTER, duration_seconds=0, channels=CHANNELS)
    assert check_policy(policy, **kwargs, threshold_value=30, alignment_period='1800s') == []
    assert check_policy(policy, **kwargs) == []
    assert check_policy(policy, **kwargs, threshold_value=0, alignment_period='60s') == [
        'condition threshold differs',
        'condition alignment period differs',
    ]
    del policy['conditions'][0]['conditionThreshold']['aggregations']
    assert check_policy(policy, **kwargs, alignment_period='1800s') == ['condition alignment period differs']


def test_policy_checks_per_series_aligner_and_trigger_count_when_declared():
    policy = _policy(
        {
            'conditionThreshold': {
                'filter': FILTER,
                'duration': '0s',
                'thresholdValue': 0,
                'aggregations': [{'alignmentPeriod': '300s', 'perSeriesAligner': 'ALIGN_SUM'}],
                'trigger': {'count': 1},
            }
        }
    )
    kwargs = dict(condition='threshold', filter_text=FILTER, duration_seconds=0, channels=CHANNELS)
    assert (
        check_policy(
            policy,
            **kwargs,
            alignment_period='300s',
            per_series_aligner='ALIGN_SUM',
            trigger_count=1,
        )
        == []
    )
    assert check_policy(
        policy,
        **kwargs,
        per_series_aligner='ALIGN_DELTA',
        trigger_count=2,
    ) == ['condition per-series aligner differs', 'condition trigger count differs']


def test_firestore_missing_index_metric_and_alert_contract():
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[3]
    metric = json.loads((repository_root / '.github/monitoring/firestore_missing_index_errors_metric.json').read_text())
    assert 'resource.type="cloud_run_revision"' in metric['filter']
    assert 'textPayload:"The query requires an index"' in metric['filter']
    assert 'jsonPayload.message:"The query requires an index"' in metric['filter']
    assert metric['metricDescriptor']['metricKind'] == 'DELTA'
    assert metric['metricDescriptor']['valueType'] == 'INT64'
    assert metric['labelExtractors']['service_name'] == 'EXTRACT(resource.labels.service_name)'

    action = (repository_root / '.github/actions/sync-backfill-lifecycle/action.yml').read_text()
    assert "inputs.project_id == 'based-hardware'" in action
    assert 'Provision routed Firestore missing-index alert' in action
    assert 'inputs.alert_notification_channels' in action
    assert '--duration=0s' in action
    assert '--comparison=\'> 0\'' in action
    assert '"alignmentPeriod":"300s"' in action
    assert '--per-series-aligner=ALIGN_SUM --trigger-count=1' in action


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


def _managed_policy(*, channels=None, filter_text=FILTER):
    return {
        'name': 'projects/p/alertPolicies/123',
        'displayName': 'Sync backfill dispatch abort',
        'conditions': [{'conditionThreshold': {'filter': filter_text, 'duration': '0s'}}],
        'notificationChannels': CHANNELS if channels is None else channels,
        'enabled': True,
    }


def test_reconciliation_repairs_only_channel_drift_then_rechecks_policy():
    calls = []
    descriptions = [_managed_policy(channels=CHANNELS[:1]), _managed_policy()]

    def runner(args, **_kwargs):
        calls.append(args)
        if args[1:4] == ['monitoring', 'policies', 'describe']:
            return subprocess.CompletedProcess(args, 0, json.dumps(descriptions.pop(0)), '')
        return subprocess.CompletedProcess(args, 0, '', '')

    changed = reconcile_policy_channels(
        project='based-hardware',
        policy_name='projects/p/alertPolicies/123',
        display_name='Sync backfill dispatch abort',
        condition='threshold',
        filter_text=FILTER,
        duration_seconds=0,
        channels=CHANNELS,
        runner=runner,
    )

    assert changed is True
    assert [args[3] for args in calls] == ['describe', 'update', 'describe']
    assert '--set-notification-channels=' + ','.join(CHANNELS) in calls[1]


def test_reconciliation_refuses_condition_drift_without_updating():
    calls = []

    def runner(args, **_kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(_managed_policy(filter_text='stale')), '')

    try:
        reconcile_policy_channels(
            project='based-hardware',
            policy_name='projects/p/alertPolicies/123',
            display_name='Sync backfill dispatch abort',
            condition='threshold',
            filter_text=FILTER,
            duration_seconds=0,
            channels=CHANNELS,
            runner=runner,
        )
    except RuntimeError as exc:
        assert 'condition filter differs' in str(exc)
    else:
        raise AssertionError('condition drift must remain a deployment blocker')
    assert len(calls) == 1


def test_reconciliation_leaves_matching_routing_untouched():
    calls = []

    def runner(args, **_kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(_managed_policy()), '')

    changed = reconcile_policy_channels(
        project='based-hardware',
        policy_name='projects/p/alertPolicies/123',
        display_name='Sync backfill dispatch abort',
        condition='threshold',
        filter_text=FILTER,
        duration_seconds=0,
        channels=CHANNELS,
        runner=runner,
    )
    assert changed is False
    assert len(calls) == 1
