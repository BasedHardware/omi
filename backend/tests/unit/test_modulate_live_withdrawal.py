"""Default live withdrawal must not disable independent batch or LID calls."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from config.live_stt_registry import registry
from utils.stt import batch_language, live_chain, live_router, pre_recorded, streaming as st
from utils.stt.live_gate import GateState


@pytest.fixture(autouse=True)
def default_registry(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', '')


@pytest.mark.parametrize('raw', [None, '', '  '])
@pytest.mark.parametrize('uid', [None, 'synthetic-owner'])
def test_defaults_keep_modulate_identity_but_exclude_every_live_candidate(monkeypatch, raw, uid):
    if raw is None:
        monkeypatch.delenv('STT_ROUTING_TARGETS_JSON', raising=False)
    else:
        monkeypatch.setenv('STT_ROUTING_TARGETS_JSON', raw)
    targets = registry()
    modulate = next(target for target in targets if target.family == 'modulate')
    assert modulate.id == 'modulate-velma-2'
    assert modulate.ramp_percent == 0
    assert live_router.permission_reason(modulate, uid, 'vi') == 'ramp_skip'
    # Even all-degraded availability escape cannot restore a config withdrawal.
    for stage in (0, 5, 100):
        candidates = live_router.select(targets, {target.id: GateState(stage=stage) for target in targets}, uid, 'vi')
        assert all(target.family != 'modulate' for target in candidates)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['off', 'shadow', 'on', 'router_fault'])
async def test_real_live_chain_never_dials_default_modulate(monkeypatch, mode):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on' if mode == 'router_fault' else mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_, **__: {})
    monkeypatch.setattr(live_chain.health, 'schedule', lambda coroutine, **_: coroutine.close())
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    monkeypatch.setattr(
        live_chain,
        'propose',
        (
            Mock(side_effect=RuntimeError('synthetic router fault'))
            if mode == 'router_fault'
            else Mock(return_value=[registry()[-1]])
        ),
    )
    modulate = AsyncMock(side_effect=AssertionError('withdrawn live provider dialed'))
    soniox = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False, finish=lambda: None))
    _, service = await live_chain.connect_configured_chain(
        primary_service=st.STTService.modulate,
        connect_primary=modulate,
        callbacks={st.STTService.soniox: soniox},
        failed=set(),
        models=['modulate-velma-2', 'soniox'],
        routing_uid='synthetic-owner',
        routing_language='vi',
    )
    assert service == st.STTService.soniox
    modulate.assert_not_awaited()
    soniox.assert_awaited_once()


def test_prerecorded_modulate_selection_and_dispatch_remain_available(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet,modulate-velma-2')
    assert pre_recorded.get_prerecorded_service('vi') == ('modulate', 'multi', 'velma-2')
    provider = Mock()
    provider.transcribe_bytes.return_value = [{'text': 'synthetic', 'timestamp': [0, 1]}]
    monkeypatch.setattr(pre_recorded, 'ModulatePrerecordedProvider', lambda: provider)
    assert (
        pre_recorded.prerecorded_from_bytes(b'synthetic-pcm', language='vi') == provider.transcribe_bytes.return_value
    )
    provider.transcribe_bytes.assert_called_once()


def test_batch_lid_still_calls_its_independent_modulate_endpoint(monkeypatch):
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic')
    monkeypatch.setattr(batch_language, 'probe_wav', lambda *_args, **_kwargs: (b'synthetic-wav', 1.0))
    monkeypatch.setattr(batch_language, 'breaker_allows', lambda *_: True)
    monkeypatch.setattr(batch_language, 'record_breaker_success', lambda *_: None)
    monkeypatch.setattr(batch_language, 'record_vendor_burn', lambda *_: None)
    client = MagicMock()
    client.post.return_value.json.return_value = {'predicted_language_code': 'vi', 'confidence': 0.99}
    context = MagicMock()
    context.__enter__.return_value = client
    monkeypatch.setattr(batch_language.httpx, 'Client', lambda **_: context)
    decision = batch_language.detect(b'synthetic-pcm')
    assert (decision.language, decision.evidence) == ('vi', 'audio_lid')
    assert client.post.call_args.args == (batch_language.LID_URL,)
