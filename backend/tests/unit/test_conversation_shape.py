"""Conversation shape telemetry: helper contract and production persist seams."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from utils import conversation_shape as shape
from utils.metrics import CONVERSATION_DURATION_BUCKETS, CONVERSATION_SEGMENT_BUCKETS

SECRET_UID = 'uid_SHOULD_NEVER_APPEAR'
SECRET_CONVERSATION = 'conv_SHOULD_NEVER_APPEAR'


@pytest.fixture
def registries(monkeypatch):
    registry = CollectorRegistry()
    duration = Histogram(
        'omi_conversation_duration_seconds',
        'Wall',
        ['source'],
        buckets=CONVERSATION_DURATION_BUCKETS,
        registry=registry,
    )
    speech = Histogram(
        'omi_conversation_speech_seconds',
        'Speech',
        ['source'],
        buckets=CONVERSATION_DURATION_BUCKETS,
        registry=registry,
    )
    segments = Histogram(
        'omi_conversation_segments',
        'Segments',
        ['source'],
        buckets=CONVERSATION_SEGMENT_BUCKETS,
        registry=registry,
    )
    events = Counter(
        'omi_product_event_total',
        'Events',
        ['event', 'client_kind', 'app_build', 'outcome', 'source', 'op'],
        registry=registry,
    )
    monkeypatch.setattr(shape, 'OMI_CONVERSATION_DURATION_SECONDS', duration)
    monkeypatch.setattr(shape, 'OMI_CONVERSATION_SPEECH_SECONDS', speech)
    monkeypatch.setattr(shape, 'OMI_CONVERSATION_SEGMENTS', segments)
    monkeypatch.setattr(
        shape,
        'record_product_event',
        lambda *args, **kwargs: events.labels(
            event=kwargs.get('event', args[0] if args else 'unknown'),
            client_kind='unknown',
            app_build='unknown',
            outcome=kwargs.get('outcome', 'none'),
            source=kwargs.get('source', 'none'),
            op='none',
        ).inc(),
    )
    return registry


def _live_payload() -> dict:
    return {
        'id': SECRET_CONVERSATION,
        'status': 'completed',
        'source': 'omi',
        'started_at': datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        'finished_at': datetime(2026, 9, 19, 12, 0, 11, tzinfo=timezone.utc),
        'transcript_segments': [
            {'start': 0.0, 'end': 4.0, 'text': 'hello'},
            {'start': 5.0, 'end': 10.0, 'text': 'world'},
        ],
    }


def test_classify_source_closed_vocabulary():
    assert shape.classify_conversation_source({'source': 'omi'}) == 'live'
    assert shape.classify_conversation_source({'source': 'omi', 'sync_content_revision': 1}) == 'sync'
    assert shape.classify_conversation_source({'source': 'omi', 'sync_relevance': 'keep'}) == 'sync'
    assert shape.classify_conversation_source({'source': 'desktop'}) == 'desktop'
    assert shape.classify_conversation_source({'source': 'workflow'}) == 'integration'
    assert shape.classify_conversation_source({'source': 'external_integration'}) == 'integration'
    assert shape.classify_conversation_source({'source': 'limitless', 'imported': True}) == 'import'
    assert shape.classify_conversation_source({}) == 'unknown'
    assert shape.classify_conversation_source({'source': SECRET_UID}) == 'live'


def test_observe_records_live_duration_speech_and_segments(registries):
    shape.observe_completed_conversation_shape(SECRET_UID, _live_payload())
    assert (
        registries.get_sample_value(
            'omi_conversation_duration_seconds_count',
            {'source': 'live'},
        )
        == 1
    )
    duration_sum = registries.get_sample_value('omi_conversation_duration_seconds_sum', {'source': 'live'})
    assert duration_sum == 11.0
    speech_sum = registries.get_sample_value('omi_conversation_speech_seconds_sum', {'source': 'live'})
    assert speech_sum == 9.0
    assert registries.get_sample_value('omi_conversation_segments_sum', {'source': 'live'}) == 2.0
    rendered = generate_latest(registries)
    assert SECRET_UID.encode() not in rendered
    assert SECRET_CONVERSATION.encode() not in rendered
    for family in registries.collect():
        for sample in family.samples:
            assert 'uid' not in sample.labels
            assert SECRET_UID not in sample.labels.values()
            assert SECRET_CONVERSATION not in sample.labels.values()


def test_observe_sync_logs_prebucketed_line(registries, caplog):
    payload = _live_payload()
    payload['sync_content_revision'] = 1
    with caplog.at_level('INFO', logger='utils.conversation_shape'):
        shape.observe_completed_conversation_shape(SECRET_UID, payload)
    assert (
        registries.get_sample_value(
            'omi_conversation_duration_seconds_count',
            {'source': 'sync'},
        )
        == 1
    )
    assert 'omi_conversation_shape source=sync duration_le=15 speech_le=10 segments_le=2' in caplog.text
    assert SECRET_UID not in caplog.text
    assert SECRET_CONVERSATION not in caplog.text


def test_observe_fail_open_when_histogram_raises(monkeypatch):
    broken = MagicMock()
    broken.labels.side_effect = RuntimeError('collector failed')
    monkeypatch.setattr(shape, 'OMI_CONVERSATION_DURATION_SECONDS', broken)
    shape.observe_completed_conversation_shape(SECRET_UID, _live_payload())


def test_observe_emits_created_not_finalized_with_closed_source(registries):
    shape.observe_completed_conversation_shape(SECRET_UID, _live_payload())
    created_labels = {
        'event': 'conversation_created',
        'client_kind': 'unknown',
        'app_build': 'unknown',
        'outcome': 'ok',
        'source': 'live',
        'op': 'none',
    }
    assert registries.get_sample_value('omi_product_event_total', created_labels) == 1
    for sample in next(f for f in registries.collect() if f.name == 'omi_product_event').samples:
        assert sample.labels.get('event') != 'conversation_finalized'


def test_zero_init_exports_shape_sources_and_drops_old_user_daily_histogram():
    from utils import metrics as metrics_mod

    exported = metrics_mod.generate_latest().decode()
    assert 'omi_conversation_duration_seconds_bucket{le="120.0",source="live"}' in exported
    assert 'omi_conversation_speech_seconds_bucket{le="120.0",source="sync"}' in exported
    assert 'omi_conversation_segments_bucket{le="5.0",source="desktop"}' in exported
    assert 'omi_product_event_user_daily_over_total{event="conversation_created",threshold="100"}' in exported
    assert 'omi_product_event_user_daily_bucket' not in exported
    assert 'uid=' not in exported
    assert SECRET_UID not in exported
