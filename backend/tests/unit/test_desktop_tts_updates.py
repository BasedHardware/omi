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
    if function is router.redis_db.check_tts_rate_limit:
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
async def test_desktop_legacy_rollback_keeps_openai_voice_validation(monkeypatch):
    monkeypatch.setenv('TTS_PROVIDER', 'legacy')

    with pytest.raises(HTTPException) as exc_info:
        await router.tts_synthesize(router.TtsSynthesizeRequest(text='hello', voice_id='future_voice'), uid='u')
    assert exc_info.value.status_code == 400
