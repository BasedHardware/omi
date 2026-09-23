"""Translation/inference patches cannot revive retired IDs or undo merged text."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import conversations as db
from routers.listen import transcripts
from tests.unit.test_manual_speaker_assignments import world, read


@pytest.mark.parametrize('fields', [('translations',), ('person_id', 'is_user', 'speaker_identity_status')])
def test_stale_nonowner_preserves_current_segment_set_and_content(world, fields):
    store, path, old = world
    stale = deepcopy(old)
    stale[0]['translations'] = [{'lang': 'fr', 'text': 'bonjour'}]
    current = dict(old[0], text='Merged speech.', end=5)
    later = dict(old[1], id='later', start=5, end=6)
    store.rows[path]['transcript_segments'] = [current, later]
    result = db.update_conversation_segments('u', 'c', stale, segment_update_fields=fields, return_segments=True)
    assert [s['id'] for s in result] == ['s0', 'later']
    assert result[0]['text'] == 'Merged speech.' and result[0]['end'] == 5
    assert result[1] == later
    assert read(world)['transcript_segments'] == result


@pytest.mark.asyncio
async def test_translation_does_not_publish_a_retired_segment(world):
    store, path, old = world
    cached = deepcopy(store.rows[path])
    store.rows[path]['transcript_segments'] = [old[0]]

    async def persist(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    events = []
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = SimpleNamespace(
        translation_language='fr',
        state=SimpleNamespace(active=True, current_conversation_id='c'),
        request=SimpleNamespace(uid='u'),
        persistence=SimpleNamespace(call=persist),
        send_event=events.append,
    )
    processor.cache = transcripts.ConversationCache(AsyncMock(return_value=cached))
    import asyncio

    processor.translation_lock = asyncio.Lock()
    await processor._on_translation_ready('s1', 'bonjour', 'en', 'c')
    assert events == []
    assert [s['id'] for s in processor.cache.data['transcript_segments']] == ['s0']
    assert [s['id'] for s in read(world)['transcript_segments']] == ['s0']
