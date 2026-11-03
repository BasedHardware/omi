"""An explicit client preference cannot revive the retired plain streaming slot."""

from unittest.mock import Mock

import pytest

from utils.stt import streaming


@pytest.mark.parametrize('configured', [None, ['parakeet', 'modulate-velma-2', 'soniox']])
def test_explicit_parakeet_falls_back_and_switch_can_readmit(monkeypatch, configured):
    monkeypatch.delenv('STT_GPU_FLEET_OFF', raising=False)
    monkeypatch.delenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', raising=False)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.invalid')
    if configured is not None:
        monkeypatch.setattr(streaming, 'stt_service_models', configured)
    fallback = Mock()
    monkeypatch.setattr(streaming, 'record_fallback', fallback)
    assert (
        streaming.get_stt_service_for_language('en', multi_lang_enabled=False, preferred_service='parakeet')[0]
        == streaming.STTService.modulate
    )
    assert fallback.call_args.kwargs['component'] == 'stt_selection'
    assert fallback.call_args.kwargs['outcome'] == 'degraded'
    assert fallback.call_args.kwargs['from_mode'] == 'parakeet'
    monkeypatch.setenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', 'true')
    # Legacy deployment lists can immediately restore the preference. With a new
    # two-vendor literal, the switch restores only the default last-resort hop.
    if configured is not None:
        assert (
            streaming.get_stt_service_for_language('en', multi_lang_enabled=False, preferred_service='parakeet')[0]
            == streaming.STTService.parakeet
        )
    assert (
        streaming.get_stt_service_for_language(
            'en', multi_lang_enabled=False, exclude=frozenset({'modulate', 'soniox'})
        )[0]
        == streaming.STTService.parakeet
    )
