from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Counter, generate_latest
from starlette.requests import Request

from utils import product_metrics as metrics
from utils.journey_metrics_contract import CLIENT_KINDS
from utils.metrics import OMI_PRODUCT_EVENT_TOTAL, OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL

SECRET_UID = 'uid_SHOULD_NEVER_APPEAR'
SECRET_CONVERSATION = 'conv_SHOULD_NEVER_APPEAR'
RAW_VERSION = 'definitely-not-a-version/1.0'


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(metrics, '_builds', set())
    monkeypatch.setattr(metrics, '_per_user_counts', {})


@pytest.fixture
def counter(monkeypatch):
    registry = CollectorRegistry()
    counter = Counter(
        'omi_product_event_total',
        'Events',
        ['event', 'client_kind', 'app_build', 'outcome', 'source', 'op'],
        registry=registry,
    )
    over = Counter(
        'omi_product_event_user_daily_over_total',
        'Daily crossings',
        ['event', 'threshold'],
        registry=registry,
    )
    monkeypatch.setattr(metrics, 'OMI_PRODUCT_EVENT_TOTAL', counter)
    monkeypatch.setattr(metrics, 'OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL', over)
    return registry


def _count(registry, **labels):
    return registry.get_sample_value('omi_product_event_total', labels)


def test_counter_exposition(counter):
    metrics.record_product_event('conversation_created', app_build='240', client_kind='mobile_ios')
    metrics.record_product_event('conversation_created', app_build='240', client_kind='mobile_ios')
    assert (
        _count(
            counter,
            event='conversation_created',
            client_kind='mobile_ios',
            app_build='240',
            outcome='none',
            source='none',
            op='none',
        )
        == 2
    )
    rendered = generate_latest(counter)
    assert b'event="conversation_created"' in rendered
    assert b'client_kind="mobile_ios"' in rendered
    assert b'app_build="240"' in rendered
    assert SECRET_UID.encode() not in rendered


@pytest.mark.parametrize('value', [None, '', 'x' * 33, 'a/b', 'a b', 'é', 'a\n', 123, {}])
def test_reject_unsafe_labels(value):
    assert metrics.sanitize_label(value) == 'unknown'


def test_flutter_build_uses_parse_client_build_not_raw_header():
    request = Request({'type': 'http', 'headers': [(b'x-app-version', b'1.0.522+240')]})
    assert metrics.extract_app_build(request) == '240'


def test_desktop_dotted_version_is_sanitized_not_raw():
    request = Request({'type': 'http', 'headers': [(b'x-app-version', b'0.12.365')]})
    assert metrics.extract_app_build(request) == '0.12.365'


@pytest.mark.parametrize('value', [SECRET_UID, RAW_VERSION, '0.12.365+user-id', '0.12.365\n', 'a' * 1000, None])
def test_reject_non_release_builds(value):
    assert metrics.sanitize_app_build(value) == 'unknown'


def test_closed_vocabularies(counter):
    metrics.record_product_event(SECRET_UID, SECRET_CONVERSATION, 'device-789')
    assert (
        _count(
            counter,
            event='unknown',
            client_kind='unknown',
            app_build='unknown',
            outcome='none',
            source='none',
            op='none',
        )
        == 1
    )


def test_uid_and_raw_version_never_appear_as_labels(counter):
    metrics.record_product_event(
        'conversation_created',
        app_build=RAW_VERSION,
        client_kind='desktop_macos',
        uid=SECRET_UID,
    )
    values = set()
    for family in counter.collect():
        for sample in family.samples:
            values.update(sample.labels.values())
            values.update(sample.labels.keys())
    assert SECRET_UID not in values
    assert RAW_VERSION not in values
    assert 'uid' not in OMI_PRODUCT_EVENT_TOTAL._labelnames
    assert 'uid' not in OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL._labelnames


def test_build_cardinality_cap_is_thread_safe():
    with ThreadPoolExecutor(max_workers=8) as pool:
        labels = list(pool.map(metrics.sanitize_app_build, [f'0.12.{i}' for i in range(256)]))
    assert len(set(labels) - {'unknown'}) == metrics.MAX_APP_BUILDS
    assert len(metrics._builds) == metrics.MAX_APP_BUILDS
    accepted = next(label for label in labels if label != 'unknown')
    assert metrics.sanitize_app_build(accepted) == accepted


@pytest.mark.parametrize(
    'platform,kind',
    [
        ('ios', 'mobile_ios'),
        ('android', 'mobile_android'),
        ('macos', 'desktop_macos'),
        ('windows', 'desktop_windows'),
        ('linux', 'desktop_linux'),
        ('web', 'web'),
        ('', 'unknown'),
    ],
)
def test_request_context(platform, kind):
    request = Request(
        {'type': 'http', 'headers': [(b'x-app-version', b'1.0.85+462'), (b'x-app-platform', platform.encode())]}
    )
    assert metrics.extract_app_build(request) == '462'
    assert metrics.extract_client_kind(request) == kind


def test_absent_version_does_not_use_user_agent_or_build_id_header_as_raw():
    request = Request({'type': 'http', 'headers': [(b'user-agent', b'Omi/0.12.365'), (b'x-app-build', b'not-a-build')]})
    assert metrics.extract_app_build(request) == 'unknown'
    assert metrics.extract_client_kind(request) == 'unknown'


@pytest.mark.parametrize('failure', ['labels', 'inc'])
def test_recording_failure_is_swallowed(monkeypatch, failure):
    counter = MagicMock()
    if failure == 'labels':
        counter.labels.side_effect = RuntimeError('collector failed')
    else:
        counter.labels.return_value.inc.side_effect = RuntimeError('collector failed')
    monkeypatch.setattr(metrics, 'OMI_PRODUCT_EVENT_TOTAL', counter)
    metrics.record_product_event('conversation_created', app_build='240', client_kind='desktop_macos')


def test_t1_events_record_expected_labels(counter):
    metrics.record_product_event('conversation_finalized', client_kind='desktop_macos', outcome='ok')
    metrics.record_product_event('duplicate_capture_detected')
    metrics.record_product_event('sync_job_enqueued', client_kind='mobile_ios', app_build='240', uid=SECRET_UID)
    metrics.record_product_event(
        'chat_message_sent', client_kind='mobile_ios', outcome='quota_exceeded', uid=SECRET_UID
    )
    metrics.record_product_event(
        'desktop_chat_completion', client_kind='desktop_macos', outcome='success', app_build='365'
    )
    assert (
        _count(
            counter,
            event='conversation_finalized',
            client_kind='desktop_macos',
            app_build='unknown',
            outcome='ok',
            source='none',
            op='none',
        )
        == 1
    )
    assert (
        _count(
            counter,
            event='chat_message_sent',
            client_kind='mobile_ios',
            app_build='unknown',
            outcome='quota_exceeded',
            source='none',
            op='none',
        )
        == 1
    )


def test_t2_events_record_source_and_op(counter):
    metrics.record_product_event('memory_created', source='import', uid=SECRET_UID, count=3)
    metrics.record_product_event('memory_updated', op='visibility')
    metrics.record_product_event('action_item_mutated', op='batch_delete')
    metrics.record_product_event('conversation_sync_mutation', outcome='replayed')
    metrics.record_product_event('app_enabled', op='disable')
    assert (
        _count(
            counter,
            event='memory_created',
            client_kind='unknown',
            app_build='unknown',
            outcome='none',
            source='import',
            op='none',
        )
        == 3
    )
    assert (
        _count(
            counter,
            event='app_enabled',
            client_kind='unknown',
            app_build='unknown',
            outcome='none',
            source='none',
            op='disable',
        )
        == 1
    )


def test_observe_per_user_daily_crosses_each_threshold_once_without_uid_label(counter):
    for _ in range(6):
        metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    family = next(f for f in counter.collect() if f.name == 'omi_product_event_user_daily_over')
    for sample in family.samples:
        assert 'uid' not in sample.labels
        assert SECRET_UID not in sample.labels.values()
        assert 'app_build' not in sample.labels
    assert (
        counter.get_sample_value(
            'omi_product_event_user_daily_over_total',
            {'event': 'conversation_created', 'threshold': '5'},
        )
        == 1
    )
    assert (
        counter.get_sample_value(
            'omi_product_event_user_daily_over_total',
            {'event': 'conversation_created', 'threshold': '10'},
        )
        is None
    )
    metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    # Tally is 7: still below 10, and threshold 5 must not increment again.
    assert (
        counter.get_sample_value(
            'omi_product_event_user_daily_over_total',
            {'event': 'conversation_created', 'threshold': '5'},
        )
        == 1
    )


def test_record_product_event_drives_per_user_threshold_for_selected_events(counter):
    metrics.record_product_event('memory_created', uid=SECRET_UID, app_build='240', source='client', count=5)
    assert (
        counter.get_sample_value(
            'omi_product_event_user_daily_over_total',
            {'event': 'memory_created', 'threshold': '5'},
        )
        == 1
    )


def test_observe_per_user_daily_fail_open(monkeypatch):
    broken = MagicMock()
    broken.labels.side_effect = RuntimeError('collector failed')
    monkeypatch.setattr(metrics, 'OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL', broken)
    metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')


def test_observe_per_user_daily_does_not_replay_crossings_after_pod_rotation(counter):
    for _ in range(6):
        metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    metrics._per_user_counts.clear()
    for _ in range(3):
        metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    assert (
        counter.get_sample_value(
            'omi_product_event_user_daily_over_total',
            {'event': 'conversation_created', 'threshold': '5'},
        )
        == 1
    )
    for _ in range(2):
        metrics.observe_per_user_daily('conversation_created', SECRET_UID, '240')
    assert (
        counter.get_sample_value(
            'omi_product_event_user_daily_over_total',
            {'event': 'conversation_created', 'threshold': '5'},
        )
        == 2
    )


def test_zero_init_covers_event_by_client_kind_not_app_build():
    names = set(OMI_PRODUCT_EVENT_TOTAL._labelnames)
    assert names == {'event', 'client_kind', 'app_build', 'outcome', 'source', 'op'}
    children = {
        tuple(sorted(sample.labels.items()))
        for family in OMI_PRODUCT_EVENT_TOTAL.collect()
        for sample in family.samples
        if sample.name == 'omi_product_event_total'
    }
    expected = {
        (
            ('app_build', 'unknown'),
            ('client_kind', kind),
            ('event', event),
            ('op', 'none'),
            ('outcome', 'none'),
            ('source', 'none'),
        )
        for event in metrics.EVENTS
        for kind in CLIENT_KINDS
    }
    assert expected <= children
    unknown_only = {dict(child)['app_build'] for child in expected}
    assert unknown_only == {'unknown'}
    over_names = set(OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL._labelnames)
    assert over_names == {'event', 'threshold'}
    over_children = {
        tuple(sorted(sample.labels.items()))
        for family in OMI_PRODUCT_EVENT_USER_DAILY_OVER_TOTAL.collect()
        for sample in family.samples
        if sample.name == 'omi_product_event_user_daily_over_total'
    }
    expected_over = {
        (('event', event), ('threshold', str(threshold)))
        for event in metrics.PER_USER_DAILY_EVENTS
        for threshold in metrics.USER_DAILY_THRESHOLDS
    }
    assert expected_over <= over_children
