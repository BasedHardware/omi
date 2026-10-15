"""Socket-wide owner acquisition/repair ceilings and owner-only retry cost."""

import asyncio
from types import SimpleNamespace
from routers.listen import speakers
from tests.unit.test_owner_speaker_profiles import _Persistence


def test_socket_owner_retries_and_audio_repair_have_total_ceilings(monkeypatch):
    from unittest.mock import Mock

    clock = [0.0]
    monkeypatch.setattr(speakers.time, 'monotonic', lambda: clock[0])
    read = Mock(return_value=None)
    people = Mock(return_value=[])
    repairs = []
    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', read)
    monkeypatch.setattr(speakers.user_db, 'get_people', people)
    monkeypatch.setattr(speakers, 'named_speaker_prompts_allowed', lambda uid: True)
    monkeypatch.setattr(speakers, 'load_owner_embedding', lambda *a, **kw: repairs.append(kw['allow_audio_repair']))
    matcher = speakers.SpeakerMatcher(
        SimpleNamespace(request=SimpleNamespace(uid='u'), persistence=_Persistence(), has_speech_profile=True)
    )
    matcher._profile_conversation_id = 'c'

    async def retry():
        await matcher._load_profiles()
        for _ in range(100):
            clock[0] = max(clock[0] + 1000, matcher._profile_retry_after)
            await matcher.refresh_for_conversation('c')

    asyncio.run(retry())
    assert read.call_count == 8
    assert sum(repairs) == 3
    assert people.call_count == 1
