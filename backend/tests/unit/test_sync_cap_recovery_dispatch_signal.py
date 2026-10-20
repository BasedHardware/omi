"""Explicit provider-call signal covers real pre-dispatch exits in both modes."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import threading
from unittest.mock import Mock, AsyncMock

import pytest

from utils.sync import pipeline


@pytest.mark.parametrize('enforce', [False, True])
@pytest.mark.parametrize('exit_at', ['url', 'keyterms', 'cap', 'provider_error', 'empty'])
def test_real_segment_reports_provider_boundary_without_changing_flag_off_calls(monkeypatch, enforce, exit_at):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    monkeypatch.setattr(pipeline, 'ambiguous_binding_pending', lambda *_: False)
    gate = Mock(return_value=exit_at != 'cap')
    monkeypatch.setattr(pipeline, 'sync_allowed', gate)
    monkeypatch.setattr(
        pipeline,
        'get_syncing_file_temporal_signed_url',
        Mock(side_effect=RuntimeError('synthetic URL failure') if exit_at == 'url' else None, return_value='url'),
    )
    monkeypatch.setattr(pipeline, 'schedule_syncing_temporal_file_deletion', Mock())
    monkeypatch.setattr(
        pipeline,
        'keyterms',
        AsyncMock(
            side_effect=RuntimeError('synthetic keyterms failure') if exit_at == 'keyterms' else None, return_value=[]
        ),
    )
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', Mock(return_value=('modulate', 'en', 'velma-2')))
    stt = Mock(
        side_effect=RuntimeError('synthetic provider failure') if exit_at == 'provider_error' else None,
        return_value=([], 'en'),
    )
    monkeypatch.setattr(pipeline, 'prerecorded', stt)
    monkeypatch.setattr(pipeline, 'record_cap_audio', Mock())
    monkeypatch.setattr(pipeline, 'get_wav_duration', Mock(return_value=20))
    monkeypatch.setattr(pipeline, 'funded_allowance', Mock(return_value=Mock(reason='available')))
    monkeypatch.setattr(pipeline, '_record_empty_segment_as_silence', Mock())
    # This test owns the provider-boundary fixture. Result custody is covered
    # against real transactions separately; never invoke a real DB here.
    checkpoint = Mock(return_value=True)
    monkeypatch.setattr(pipeline.cap_recovery_provider.sync_cap_recovery, 'provider_checkpoint', checkpoint)
    outcome, errors = {}, []
    assert not pipeline.process_segment(
        '1792152000.wav',
        'synthetic',
        {},
        threading.Lock(),
        errors,
        cap_recovery=True,
        cap_recovery_checkpoint={'attempt': 1},
        deferred_outcome=outcome,
    )
    if enforce:
        called = exit_at in {'provider_error', 'empty'}
        assert outcome['provider_called'] is called
        assert stt.call_count == int(called)
        assert checkpoint.call_count == (2 if exit_at == 'empty' else int(called))
        assert outcome.get('recovery_ambiguous', False) is (exit_at == 'empty')
    else:
        assert 'provider_called' not in outcome
        assert 'recovery_ambiguous' not in outcome
        assert stt.call_count == 0  # Recovery remains paused when execution is disabled.
        gate.assert_not_called()
        checkpoint.assert_not_called()
