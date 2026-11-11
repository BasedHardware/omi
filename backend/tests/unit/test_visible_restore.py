"""Paid preview retirement keeps the capture loop independent of provider dialing.

FC-preview-dial-blocks-capture-control: the optional mobile dial no longer
exists. Exercise the surviving receiver paths so custody cannot regain a
synchronous dependency on that paid preview.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.listen import receiver as receiver_module
from routers.listen.receiver import ListenReceiver


@pytest.mark.asyncio
async def test_batch_initialization_and_deferred_open_never_dial_paid_preview(monkeypatch):
    dial = AsyncMock(side_effect=AssertionError('batch capture cannot dial a paid preview'))
    monkeypatch.setattr(receiver_module, 'process_audio_modulate', dial)
    monkeypatch.setattr(receiver_module, 'server_batch_suppresses_live', lambda _host: True)
    monkeypatch.setattr(receiver_module, 'admit_local_preview', lambda _host: None)
    host = SimpleNamespace(server_batch_only=False)
    receiver = SimpleNamespace(host=host)
    assert await ListenReceiver._initialize_stt(receiver)
    assert host.server_batch_only and receiver.cloud_live_suppressed
    assert await ListenReceiver._open_deferred_stream(receiver)
    dial.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_flush_retains_custody_without_a_provider_dial(monkeypatch):
    custody = AsyncMock()
    dial = AsyncMock(side_effect=AssertionError('custody cannot wait on a paid preview'))
    monkeypatch.setattr(receiver_module, 'claim_preview_batch_custody', custody)
    monkeypatch.setattr(receiver_module, 'process_audio_modulate', dial)
    receiver = SimpleNamespace(host=SimpleNamespace(server_batch_only=True))
    buffer = bytearray(b'\x01\x00' * 160)
    await ListenReceiver._flush_stt_buffer(receiver, buffer)
    custody.assert_awaited_once_with(receiver)
    assert not buffer and receiver._stt_buffer_start_sample is None
    dial.assert_not_awaited()
