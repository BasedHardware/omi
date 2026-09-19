from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Counter, generate_latest
from starlette.requests import Request

from utils import product_metrics as metrics


@pytest.fixture(autouse=True)
def fresh_versions(monkeypatch):
    monkeypatch.setattr(metrics, '_versions', set())


@pytest.fixture
def counter(monkeypatch):
    registry = CollectorRegistry()
    counter = Counter('omi_product_event_total', 'Events', ['event', 'app_version', 'surface'], registry=registry)
    monkeypatch.setattr(metrics, 'OMI_PRODUCT_EVENT_TOTAL', counter)
    return registry


def test_counter_exposition(counter):
    metrics.record_product_event('conversation_created', '0.12.365', 'desktop')
    metrics.record_product_event('conversation_created', '0.12.365', 'desktop')
    assert (
        counter.get_sample_value(
            'omi_product_event_total',
            {'event': 'conversation_created', 'app_version': '0.12.365', 'surface': 'desktop'},
        )
        == 2
    )
    assert (
        b'omi_product_event_total{app_version="0.12.365",event="conversation_created",surface="desktop"} 2.0'
        in generate_latest(counter)
    )


@pytest.mark.parametrize('value', [None, '', 'x' * 33, 'a/b', 'a b', 'é', 'a\n', 123, {}])
def test_reject_unsafe_labels(value):
    assert metrics.sanitize_label(value) == 'unknown'


def test_label_length_boundary():
    assert metrics.sanitize_label('a' * 32) == 'a' * 32


@pytest.mark.parametrize('value', ['user-123', '0.12.365+user-id', '0.12.365\n', 'a' * 1000, None])
def test_reject_non_release_versions(value):
    assert metrics.sanitize_app_version(value) == 'unknown'


def test_closed_vocabularies(counter):
    metrics.record_product_event('user-123', 'conversation-456', 'device-789')
    assert (
        counter.get_sample_value(
            'omi_product_event_total', dict(event='unknown', app_version='unknown', surface='unknown')
        )
        == 1
    )


def test_version_cardinality_cap_is_thread_safe():
    with ThreadPoolExecutor(max_workers=8) as pool:
        labels = list(pool.map(metrics.sanitize_app_version, [f'0.12.{i}' for i in range(256)]))
    assert len(set(labels) - {'unknown'}) == metrics.MAX_APP_VERSIONS
    assert len(metrics._versions) == metrics.MAX_APP_VERSIONS
    accepted = next(label for label in labels if label != 'unknown')
    assert metrics.sanitize_app_version(accepted) == accepted


@pytest.mark.parametrize(
    'platform,surface',
    [
        ('ios', 'mobile'),
        ('android', 'mobile'),
        ('macos', 'desktop'),
        ('windows', 'desktop'),
        ('linux', 'desktop'),
        ('web', 'unknown'),
        ('', 'unknown'),
    ],
)
def test_request_context(platform, surface):
    request = Request(
        {'type': 'http', 'headers': [(b'x-app-version', b'0.12.365'), (b'x-app-platform', platform.encode())]}
    )
    assert metrics.extract_app_version(request) == '0.12.365'
    assert metrics.extract_surface(request) == surface


def test_absent_version_does_not_use_user_agent_or_build():
    request = Request({'type': 'http', 'headers': [(b'user-agent', b'Omi/0.12.365'), (b'x-app-build', b'365')]})
    assert metrics.extract_app_version(request) == 'unknown'
    assert metrics.extract_surface(request) == 'unknown'


@pytest.mark.parametrize('failure', ['labels', 'inc'])
def test_recording_failure_is_swallowed(monkeypatch, failure):
    counter = MagicMock()
    if failure == 'labels':
        counter.labels.side_effect = RuntimeError('collector failed')
    else:
        counter.labels.return_value.inc.side_effect = RuntimeError('collector failed')
    monkeypatch.setattr(metrics, 'OMI_PRODUCT_EVENT_TOTAL', counter)
    metrics.record_product_event('conversation_created', '0.12.365', 'desktop')


def test_flutter_version_retains_numeric_build():
    request = Request({'type': 'http', 'headers': [(b'x-app-version', b'1.0.85+462')]})
    assert metrics.extract_app_version(request) == '1.0.85+462'
