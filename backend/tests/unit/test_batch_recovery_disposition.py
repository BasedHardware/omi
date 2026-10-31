"""Recovery boundaries retain content-free failure causes."""

import asyncio
import logging
import traceback
from unittest.mock import AsyncMock, Mock

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline import recovery_disposition as disposition
from utils.batch_pipeline import recovery_recognizers as recognizers
from utils.stt import soniox_batch


@pytest.mark.parametrize('stage', sorted(disposition.STAGES))
def test_at_stage_logs_type_without_private_message_or_traceback(caplog, stage):
    operation = Mock(side_effect=ConnectionError('PRIVATE_SYNTHETIC_SENTINEL'))
    with caplog.at_level(logging.WARNING), pytest.raises(disposition.RecoveryFailure) as raised:
        disposition.at_stage(stage, 'provider_failed', operation)
    failure = raised.value
    assert (failure.stage, failure.reason, str(failure)) == (stage, 'provider_failed', 'provider_failed')
    assert failure.__cause__ is None and failure.__suppress_context__
    assert caplog.messages == [
        f'event=batch_recovery_stage_failure stage={stage} reason=provider_failed exception_type=ConnectionError'
    ]
    assert all(record.exc_info is None for record in caplog.records)
    assert 'PRIVATE_SYNTHETIC_SENTINEL' not in caplog.text
    assert 'PRIVATE_SYNTHETIC_SENTINEL' not in ''.join(traceback.format_exception(failure))


@pytest.mark.parametrize('failure', [disposition.RecoveryFailure('strict_vad', 'vad_failed'), BatchPrivacyBlocked()])
def test_at_stage_preserves_typed_failures_without_logging(failure, caplog):
    with pytest.raises(type(failure)) as raised:
        disposition.at_stage('provider', 'provider_failed', Mock(side_effect=failure))
    assert raised.value is failure
    assert not caplog.records


def test_broken_logging_cannot_replace_the_recovery_failure(monkeypatch):
    monkeypatch.setattr(disposition.logger, 'warning', Mock(side_effect=RuntimeError('logging failed')))
    with pytest.raises(disposition.RecoveryFailure) as raised:
        disposition.at_stage('provider', 'provider_failed', Mock(side_effect=TimeoutError('private')))
    assert raised.value.reason == 'provider_failed' and raised.value.__suppress_context__


@pytest.mark.parametrize('broken_logging', [False, True])
def test_async_soniox_boundary_logs_type_and_preserves_failure(monkeypatch, caplog, broken_logging):
    monkeypatch.setattr(recognizers, 'run_blocking', AsyncMock(return_value=(b'audio', 1.0, [])))
    provider = AsyncMock(side_effect=ConnectionError('PRIVATE_SYNTHETIC_SENTINEL'))
    monkeypatch.setattr(soniox_batch, 'transcribe_async', provider)
    payload = Mock()
    monkeypatch.setattr(recognizers, 'independent_payload', payload)
    if broken_logging:
        monkeypatch.setattr(disposition.logger, 'warning', Mock(side_effect=RuntimeError('logging failed')))
    with caplog.at_level(logging.WARNING), pytest.raises(disposition.RecoveryFailure) as raised:
        asyncio.run(recognizers.second_transcribe_async(object(), b'input', object(), second_chance=True))
    failure = raised.value
    assert (failure.stage, failure.reason, str(failure)) == ('provider', 'provider_failed', 'provider_failed')
    assert failure.__cause__ is None and failure.__suppress_context__
    provider.assert_awaited_once_with(b'audio', 1.0, second_chance=True)
    payload.assert_not_called()
    if not broken_logging:
        assert caplog.messages == [
            'event=batch_recovery_stage_failure stage=provider reason=provider_failed exception_type=ConnectionError'
        ]
    assert all(record.exc_info is None for record in caplog.records)
    assert 'PRIVATE_SYNTHETIC_SENTINEL' not in caplog.text
    assert 'PRIVATE_SYNTHETIC_SENTINEL' not in ''.join(traceback.format_exception(failure))
