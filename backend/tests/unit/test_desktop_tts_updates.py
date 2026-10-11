import pytest
from fastapi import HTTPException

from routers import desktop_tts_updates as router
from routers.desktop_tts_updates import ReleaseInfo, _appcast_xml, _is_allowed_openai_voice, _manual_download_url


def _release(**overrides):
    values = {
        "version": "1.0.0",
        "build_number": 1,
        "download_url": "https://example.com/Omi.zip",
        "ed_signature": "signature",
        "published_at": "2026-07-26T00:00:00Z",
        "is_live": True,
    }
    values.update(overrides)
    return ReleaseInfo(**values)


def test_openai_tts_voices_match_rust_contract():
    assert _is_allowed_openai_voice("marin")
    assert _is_allowed_openai_voice("cedar")
    assert not _is_allowed_openai_voice("BAMYoBHLZM7lJgJAmFz0")


def test_appcast_deduplicates_staging_and_preserves_stable_default_channel():
    xml = _appcast_xml(
        [
            _release(version="2.0.0"),
            _release(version="1.0.0", channel="staging"),
            _release(version="3.0.0", channel="stable"),
        ],
        "macos",
    )
    assert "Omi 2.0.0" in xml
    assert "Omi 1.0.0" not in xml
    assert "Omi 3.0.0" in xml
    assert xml.count("<sparkle:channel>") == 1


def test_manual_download_prefers_explicit_dmg_then_github_zip_derivation():
    assert (
        _manual_download_url(_release(manual_download_url="https://example.com/custom.dmg"))
        == "https://example.com/custom.dmg"
    )
    assert _manual_download_url(_release()) == "https://example.com/Omi.dmg"


async def _audio_chunks():
    yield b'mp3'


async def _run_blocking(_executor, function, *_args, **_kwargs):
    if function is router.is_desktop_trial_paywalled:
        return False
    if function is router.redis_db.check_tts_rate_limit_for_user:
        return 0, None
    raise AssertionError(function)


@pytest.mark.asyncio
async def test_desktop_route_uses_shared_gemini_stream_and_style(monkeypatch):
    calls = []

    async def open_stream(**kwargs):
        calls.append(kwargs)
        return _audio_chunks()

    monkeypatch.setattr(router, 'run_blocking', _run_blocking)
    monkeypatch.setattr(router, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(router, 'open_gemini_mp3_stream', open_stream)

    response = await router.tts_synthesize(
        router.TtsSynthesizeRequest(text='hello', voice_id='future_voice', instructions='warm and calm'), uid='u'
    )
    body = b''.join([chunk async for chunk in response.body_iterator])

    assert response.media_type == 'audio/mpeg'
    assert body == b'mp3'
    assert calls == [
        {
            'text': 'hello',
            'voice_id': 'future_voice',
            'client': 'desktop',
            'style': 'warm and calm',
        }
    ]


@pytest.mark.asyncio
async def test_desktop_legacy_rollback_maps_unknown_voice_to_fixed_openai_default(monkeypatch):
    payloads = []

    class _FakeUpstream:
        is_error = False
        status_code = 200
        content = b'mp3'

    async def fake_openai(payload, _api_key):
        payloads.append(payload)
        return _FakeUpstream()

    monkeypatch.setattr(router, 'run_blocking', _run_blocking)
    monkeypatch.setattr(router, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(router, '_openai_tts', fake_openai)
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')

    response = await router.tts_synthesize(router.TtsSynthesizeRequest(text='hello', voice_id='future_voice'), uid='u')

    assert response.status_code == 200
    assert payloads[0]['voice'] == 'cedar'


@pytest.mark.asyncio
async def test_desktop_legacy_rollback_still_rejects_invalid_voice_names(monkeypatch):
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')

    with pytest.raises(HTTPException) as exc_info:
        await router.tts_synthesize(router.TtsSynthesizeRequest(text='hello', voice_id='bad voice'), uid='u')
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_desktop_gemini_does_not_treat_openai_byok_as_funding(monkeypatch):
    calls = []

    async def run_blocking(_executor, function, *_args, **kwargs):
        calls.append((function, kwargs))
        return False if function is router.is_desktop_trial_paywalled else (0, None)

    async def open_stream(**_kwargs):
        return _audio_chunks()

    monkeypatch.setattr(router, 'run_blocking', run_blocking)
    monkeypatch.setattr(router, 'get_byok_key', lambda _provider: 'user-openai-key')
    monkeypatch.setattr(router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(router, 'open_gemini_mp3_stream', open_stream)

    await router.tts_synthesize(router.TtsSynthesizeRequest(text='hello', voice_id='shimmer'), uid='u')

    paywall_call = next(call for call in calls if call[0] is router.is_desktop_trial_paywalled)
    assert paywall_call[1] == {'required_byok_provider': None, 'byok_exempt': False}
    assert any(function is router.redis_db.check_tts_rate_limit_for_user for function, _kwargs in calls)


@pytest.mark.asyncio
async def test_desktop_gemini_provider_401_cannot_invalidate_omi_session(monkeypatch):
    async def fail_stream(**_kwargs):
        raise router.TtsUpstreamError(401)

    monkeypatch.setattr(router, 'run_blocking', _run_blocking)
    monkeypatch.setattr(router, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(router, 'get_tts_provider', lambda: 'gemini')
    monkeypatch.setattr(router, 'open_gemini_mp3_stream', fail_stream)

    with pytest.raises(HTTPException) as exc_info:
        await router.tts_synthesize(router.TtsSynthesizeRequest(text='hello', voice_id='shimmer'), uid='u')

    assert exc_info.value.status_code == 502
