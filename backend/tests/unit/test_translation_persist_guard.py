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
        if fn is conversations_db.materialize_translation:
            # Legacy-path fake: the gate-off/upstream tests assert the legacy
            # update_conversation_segments write; admit materialization so the
            # default-on viewed path persists through this seam too.
            if self._fail_update:
                raise ConnectionError('firestore unavailable')
            self.updates.append(args)
            return {'id': args[2], 'text': args[3], 'translations': [{'lang': args[4], 'text': args[5]}]}
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
    materialization = host.persistence.updates[0]
    # Default-on viewed path: materialize_translation(uid, conversation_id,
    # segment_id, source_text, target, translated_text, **kwargs)
    assert materialization[0] == 'uid-1' and materialization[1] == 'conv-1'
    assert materialization[2] == 'seg-1' and materialization[4] == 'es'
    assert materialization[5] == 'hola'


def test_processor_forwards_existing_spoken_language_profile():
    host = _host(_conversation(), fail_update=False)
    host.language_profile = SimpleNamespace(expected=('pt', 'en'))
    processor = TranscriptProcessor(host)
    assert processor.translation_coordinator.expected_languages == ('pt', 'en')
    assert processor.translation_coordinator.target_language == 'es'
