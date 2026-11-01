"""Decoder installation health and observable fallback; real media decode lives in modalities."""

import asyncio
import logging
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.messaging.adapters import decoder, runtime


@pytest.fixture(autouse=True)
def clear_resolver_cache():
    decoder.get_media_decoder.cache_clear()
    yield
    decoder.get_media_decoder.cache_clear()


def test_bundled_decoder_works_without_path(monkeypatch):
    monkeypatch.setenv('PATH', '')
    monkeypatch.delenv('IMAGEIO_FFMPEG_EXE', raising=False)
    assert shutil.which('ffmpeg') is None
    executable = decoder.get_media_decoder()
    import imageio_ffmpeg

    assert Path(executable).resolve().parent == Path(imageio_ffmpeg.__file__).resolve().parent / 'binaries'


def test_system_fallback_is_validated_observable_and_cached(monkeypatch):
    monkeypatch.setattr(decoder, '_wheel_decoder', lambda: (_ for _ in ()).throw(RuntimeError('unavailable')))
    monkeypatch.setattr(decoder.shutil, 'which', lambda name: '/fixture/ffmpeg')
    probe, event = MagicMock(), MagicMock()
    monkeypatch.setattr(decoder, '_probe', probe)
    monkeypatch.setattr(decoder, 'record_fallback', event)
    assert decoder.get_media_decoder() == decoder.get_media_decoder() == '/fixture/ffmpeg'
    probe.assert_called_once_with('/fixture/ffmpeg')
    assert event.call_count == 1 and event.call_args.kwargs['to_mode'] == 'system_ffmpeg'


def test_implicit_system_fallback_from_package_is_observable(monkeypatch):
    monkeypatch.setattr(decoder, '_wheel_decoder', lambda: ('ffmpeg', False))
    monkeypatch.setattr(decoder, '_probe', lambda path: None)
    event = MagicMock()
    monkeypatch.setattr(decoder, 'record_fallback', event)
    assert decoder.get_media_decoder() == 'ffmpeg'
    assert event.call_count == 1 and event.call_args.kwargs['outcome'] == 'recovered'


@pytest.mark.parametrize('system_present', [False, True])
def test_unavailable_or_broken_decoder_is_explicit(monkeypatch, caplog, system_present):
    monkeypatch.setattr(decoder, '_wheel_decoder', lambda: (_ for _ in ()).throw(ImportError('missing')))
    monkeypatch.setattr(decoder.shutil, 'which', lambda name: '/broken/ffmpeg' if system_present else None)

    def broken(path):
        raise OSError('broken executable')

    monkeypatch.setattr(decoder, '_probe', broken)
    with caplog.at_level(logging.ERROR), pytest.raises(
        decoder.MediaDecoderUnavailable, match='Messaging audio decoder unavailable'
    ):
        decoder.get_media_decoder()
    assert decoder.UNAVAILABLE in caplog.text


def test_missing_decoder_is_loud_but_never_blocks_startup(monkeypatch, caplog):
    monkeypatch.setattr(runtime, 'configured_adapters', lambda: (SimpleNamespace(channel='telegram'),))
    monkeypatch.setattr(runtime, 'recover_pending', AsyncMock())
    register = MagicMock()

    def unavailable():
        raise decoder.MediaDecoderUnavailable(decoder.UNAVAILABLE)

    monkeypatch.setattr(runtime, 'get_media_decoder', unavailable)

    async def run():
        result = await runtime.start_adapters(register)
        result[0].set()
        await result[1]

    with caplog.at_level(logging.ERROR):
        asyncio.run(run())
    # Text channels stay registered; the API process must not fail on a voice-only dependency.
    register.assert_called_once()
    assert 'Messaging audio decoder unavailable' in caplog.text


def test_disabled_channels_do_not_require_decoder(monkeypatch):
    monkeypatch.setattr(runtime, 'configured_adapters', lambda: ())
    probe = MagicMock(side_effect=AssertionError('disabled channel probed'))
    monkeypatch.setattr(runtime, 'get_media_decoder', probe)
    assert asyncio.run(runtime.start_adapters(MagicMock())) is None
    probe.assert_not_called()


def test_healthy_startup_probes_off_loop_before_registration(monkeypatch):
    import threading

    events = []
    adapter = SimpleNamespace(channel='telegram')
    monkeypatch.setattr(runtime, 'configured_adapters', lambda: (adapter,))
    monkeypatch.setattr(runtime, 'get_media_decoder', lambda: events.append(('probe', threading.get_ident())))

    async def recover(gateways, stop):
        await stop.wait()

    monkeypatch.setattr(runtime, 'recover_pending', recover)

    def register(channel, actual):
        assert channel == 'telegram' and actual is adapter
        events.append(('register', threading.get_ident()))
        return SimpleNamespace(adapter=actual)

    async def start_and_stop():
        loop_thread = threading.get_ident()
        result = await runtime.start_adapters(register)
        assert result is not None
        stop, task = result
        assert [event for event, _ in events] == ['probe', 'register']
        assert events[0][1] != loop_thread and events[1][1] == loop_thread
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(start_and_stop())
