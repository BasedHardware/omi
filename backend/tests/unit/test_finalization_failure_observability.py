import logging

from fastapi import HTTPException
from prometheus_client import generate_latest

from utils.observability import finalization


def test_every_bounded_failure_child_is_exported_at_zero_before_first_failure():
    payload = generate_latest(finalization.FINALIZATION_FAILURES_TOTAL).decode('utf-8')
    for reason in finalization.FinalizationFailureReason:
        assert f'reason="{reason.value}"' in payload


def test_finalization_failure_classifier_has_closed_operational_reasons():
    stale = type(
        'ConversationFinalizationError',
        (RuntimeError,),
        {'code': 'fanout_completion_conflict'},
    )('private error text')

    assert (
        finalization.classify_finalization_failure(
            HTTPException(status_code=503, detail='Memory writes are globally paused')
        )
        is finalization.FinalizationFailureReason.memory_fence
    )
    assert (
        finalization.classify_finalization_failure(
            HTTPException(status_code=503, detail='Memory write control is invalid')
        )
        is finalization.FinalizationFailureReason.memory_config
    )
    assert finalization.classify_finalization_failure(TimeoutError('provider response with private text')) is (
        finalization.FinalizationFailureReason.provider
    )
    assert finalization.classify_finalization_failure(stale) is finalization.FinalizationFailureReason.stale
    assert finalization.classify_finalization_failure(ValueError('private transcript text')) is (
        finalization.FinalizationFailureReason.processing
    )


def test_finalization_failure_metric_uses_only_the_bounded_reason(monkeypatch):
    calls = []

    class _Metric:
        def labels(self, **labels):
            calls.append(labels)
            return self

        def inc(self):
            calls.append('inc')

    monkeypatch.setattr(finalization, 'FINALIZATION_FAILURES_TOTAL', _Metric())

    finalization.record_finalization_failure(finalization.FinalizationFailureReason.memory_fence)

    assert calls == [{'reason': 'memory_fence'}, 'inc']


def test_finalization_failure_metric_failure_is_fail_open_and_logs_once(monkeypatch, caplog):
    class _BrokenMetric:
        def labels(self, **_labels):
            raise RuntimeError('private provider response')

    monkeypatch.setattr(finalization, 'FINALIZATION_FAILURES_TOTAL', _BrokenMetric())
    monkeypatch.setattr(finalization, '_metric_warning_emitted', False)

    with caplog.at_level(logging.WARNING, logger=finalization.logger.name):
        finalization.record_finalization_failure(finalization.FinalizationFailureReason.provider)
        finalization.record_finalization_failure(finalization.FinalizationFailureReason.provider)

    messages = [record.getMessage() for record in caplog.records]
    assert messages == ['finalization_failure_metric_record_failed']
