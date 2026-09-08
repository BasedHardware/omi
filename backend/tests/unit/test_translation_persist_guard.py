"""Regression: a failed translation persist must not escape and abort the rest of the batch.

TranscriptProcessor._on_translation_ready is the callback TranslationCoordinator invokes for each
finished translation. Before the listen split the whole body was wrapped in
`try/except Exception: logger.error(...)` (routers/transcribe.py at e8adfc5623^). The split dropped
that guard, and the caller (_flush_batch in utils/translation_coordinator.py) catches only
(RuntimeError, ValueError). So a transient persist error, for example a Firestore/network failure
from update_conversation_segments, escapes the batch loop and silently drops the translations for
every remaining segment in that batch. The coordinator runs the callback from a bare task, so
nothing surfaces except an unretrieved-task warning.

Seam: TranscriptProcessor takes only a host, so this builds a fake host by constructor injection
and drives the real callback. No patching and no sys.modules mutation. The conversation id differs
from the session's current conversation so the load goes through persistence rather than the cache.
"""

from types import SimpleNamespace

from routers.listen.transcripts import TranscriptProcessor
from utils.transcribe_store import conversations_db


class _Persistence:
    def __init__(self, conversation: dict, fail_update: bool) -> None:
        self._conversation = conversation
        self._fail_update = fail_update
        self.updates: list[tuple] = []

    async def call(self, fn, *args, **kwargs):
        if fn is conversations_db.get_conversation:
            return self._conversation
        if fn is conversations_db.update_conversation_segments:
            if self._fail_update:
                raise ConnectionError('firestore unavailable')
            self.updates.append(args)
            return None
        return None


def _conversation() -> dict:
    return {'id': 'conv-1', 'transcript_segments': [{'id': 'seg-1', 'text': 'hello', 'translations': []}]}


def _host(conversation: dict, *, fail_update: bool) -> SimpleNamespace:
    return SimpleNamespace(
        limits=SimpleNamespace(max_segment_buffer_size=100, max_photo_buffer_size=100),
        # A different current conversation forces the persistence load path.
        state=SimpleNamespace(active=True, current_conversation_id='other-conversation'),
        persistence=_Persistence(conversation, fail_update),
        request=SimpleNamespace(uid='uid-1'),
        translation_language='es',
        send_event=lambda event: None,
    )


async def test_persist_failure_does_not_escape_the_callback():
    host = _host(_conversation(), fail_update=True)
    processor = TranscriptProcessor(host)

    # Must not raise. _flush_batch only catches (RuntimeError, ValueError), so an escaping error
    # aborts the batch loop and drops the remaining segments' translations.
    await processor._on_translation_ready('seg-1', 'hola', 'es', 'conv-1')


async def test_successful_persist_still_writes_the_translation():
    host = _host(_conversation(), fail_update=False)
    processor = TranscriptProcessor(host)

    await processor._on_translation_ready('seg-1', 'hola', 'es', 'conv-1')

    assert host.persistence.updates, 'the translation should have been persisted'
    persisted_segments = host.persistence.updates[0][2]
    assert persisted_segments[0]['translations'][0]['text'] == 'hola'
    assert persisted_segments[0]['translations'][0]['lang'] == 'es'
