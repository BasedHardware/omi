from __future__ import annotations

import logging

from utils.observability import fallback as fallback_mod


class FakeCounterChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def inc(self, amount: float = 1.0):
        self.parent.increments.append((self.labels, amount))


class FakeCounter:
    def __init__(self):
        self.increments: list[tuple[dict[str, str], float]] = []

    def labels(self, **labels):
        return FakeCounterChild(self, labels)


def test_record_fallback_increments_metric_and_logs_same_fields(monkeypatch, caplog):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)

    with caplog.at_level(logging.WARNING, logger=fallback_mod.logger.name):
        fallback_mod.record_fallback(
            component='sync_dispatch',
            from_mode='cloud_tasks',
            to_mode='inline',
            reason='enqueue_failed',
            outcome='degraded',
        )

    assert counter.increments == [
        (
            {
                'component': 'sync_dispatch',
                'from_mode': 'cloud_tasks',
                'to_mode': 'inline',
                'reason': 'enqueue_failed',
                'outcome': 'degraded',
            },
            1.0,
        )
    ]
    assert any(
        'omi_fallback_event' in record.message
        and 'component=sync_dispatch' in record.message
        and 'from=cloud_tasks' in record.message
        and 'to=inline' in record.message
        and 'reason=enqueue_failed' in record.message
        and 'outcome=degraded' in record.message
        for record in caplog.records
    )


def test_record_fallback_buckets_unknown_reason_and_invalid_outcome(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)

    fallback_mod.record_fallback(
        component='not_a_real_component',
        from_mode='Cloud Tasks!',
        to_mode='',
        reason='totally_novel_failure',
        outcome='success',
    )

    labels, amount = counter.increments[0]
    assert amount == 1.0
    assert labels['component'] == 'other'
    assert labels['from_mode'] == 'cloud_tasks_'
    assert labels['to_mode'] == 'none'
    assert labels['reason'] == 'other'
    assert labels['outcome'] == 'degraded'


def test_bucket_reason_respects_allowlist_override():
    assert fallback_mod.bucket_reason('enqueue_failed') == 'enqueue_failed'
    assert fallback_mod.bucket_reason('weird') == 'other'
    assert fallback_mod.bucket_reason('custom', allowed=frozenset({'custom', 'other'})) == 'custom'


def test_record_fallback_never_raises_on_metric_or_log_failure(monkeypatch):
    class BoomCounter:
        def labels(self, **_labels):
            raise RuntimeError('metric boom')

    class BoomLogger:
        def warning(self, *_args, **_kwargs):
            raise RuntimeError('log boom')

    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', BoomCounter())
    fallback_mod.record_fallback(
        component='pusher',
        from_mode='connected',
        to_mode='degraded',
        reason='circuit_open',
        outcome='degraded',
        log=BoomLogger(),
    )


def test_stt_selection_fallback_records_on_capability_mismatch(monkeypatch):
    from utils.stt import streaming as streaming_mod

    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    monkeypatch.setattr(streaming_mod, 'stt_service_models', ['modulate-velma-2'])

    service, lang, model = streaming_mod.get_stt_service_for_language('xx-unsupported')

    assert service == streaming_mod.STTService.deepgram
    assert lang == 'en'
    assert model == 'nova-3'
    assert counter.increments == [
        (
            {
                'component': 'stt_selection',
                'from_mode': 'requested_non_en',
                'to_mode': 'deepgram_en',
                'reason': 'capability_mismatch',
                'outcome': 'degraded',
            },
            1.0,
        )
    ]


def test_hosted_vad_fallback_reason_buckets(monkeypatch):
    import httpx
    import requests
    from utils.stt import vad as vad_mod

    assert vad_mod._hosted_vad_fallback_reason(requests.Timeout()) == 'timeout'
    assert vad_mod._hosted_vad_fallback_reason(httpx.TimeoutException('slow')) == 'timeout'

    response = requests.Response()
    response.status_code = 503
    assert vad_mod._hosted_vad_fallback_reason(requests.HTTPError(response=response)) == 'provider_5xx'

    assert vad_mod._hosted_vad_fallback_reason(RuntimeError('boom')) == 'other'
