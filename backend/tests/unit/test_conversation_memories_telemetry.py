"""Behavioral contract for the backend Conversation Memories Extracted telemetry.

Mirrors test_integration_sync_telemetry.py: a fake PostHog client captures emits,
and every test asserts the closed schema, the zero/failure/idempotency boundaries,
and that no conversation id, memory text, transcript content, prompts, provider
payloads, or exception strings can reach PostHog.
"""

from types import SimpleNamespace

import pytest

from models.conversation import ConversationSource
from utils.conversations import memory_extraction_telemetry as met
from utils.conversations.memory_extraction_telemetry import (
    PATH_CANONICAL,
    PATH_LEGACY,
    SOURCE_EXTERNAL_INTEGRATION,
    SOURCE_TRANSCRIPTION,
    ConversationMemoryExtractionResult,
    emit_conversation_memories_extracted,
    source_for_conversation,
)


class FakePosthog:
    def __init__(self):
        self.calls = []

    def capture(self, *, distinct_id, event, properties):
        self.calls.append({'distinct_id': distinct_id, 'event': event, 'properties': dict(properties)})


@pytest.fixture(autouse=True)
def _reset_posthog_client():
    met.set_posthog_client_for_tests(None)
    yield
    met.set_posthog_client_for_tests(None)


def _emit(uid, *, count, source=SOURCE_TRANSCRIPTION, path=PATH_CANONICAL):
    emit_conversation_memories_extracted(uid, ConversationMemoryExtractionResult(count=count, source=source, path=path))


def test_emits_one_bounded_event_after_successful_persistence():
    fake = FakePosthog()
    met.set_posthog_client_for_tests(fake)

    _emit('uid-1', count=2, source=SOURCE_TRANSCRIPTION, path=PATH_CANONICAL)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call['distinct_id'] == 'uid-1'
    assert call['event'] == 'Conversation Memories Extracted'
    # Closed schema: exactly three bounded dimensions.
    assert set(call['properties'].keys()) == {'memory_count_bucket', 'source', 'path'}
    assert call['properties']['memory_count_bucket'] == '2'
    assert call['properties']['source'] == 'transcription'
    assert call['properties']['path'] == 'canonical'


def test_zero_extraction_emits_nothing():
    fake = FakePosthog()
    met.set_posthog_client_for_tests(fake)
    _emit('uid-1', count=0)
    assert fake.calls == []


def test_empty_uid_emits_nothing():
    fake = FakePosthog()
    met.set_posthog_client_for_tests(fake)
    _emit('', count=3)
    assert fake.calls == []


@pytest.mark.parametrize(
    'count,expected',
    [
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4_9'),
        (9, '4_9'),
        (10, '10_plus'),
        (49, '10_plus'),
    ],
)
def test_memory_count_is_bucketed_not_raw(count, expected):
    fake = FakePosthog()
    met.set_posthog_client_for_tests(fake)
    _emit('uid-1', count=count)
    assert fake.calls[0]['properties']['memory_count_bucket'] == expected


def test_invalid_source_and_path_fall_back_to_closed_values():
    fake = FakePosthog()
    met.set_posthog_client_for_tests(fake)
    # Unknown enum values collapse to a closed default, never an open string.
    emit_conversation_memories_extracted(
        'uid-1',
        ConversationMemoryExtractionResult(count=1, source='prompt-injection', path='exotic'),
    )
    props = fake.calls[0]['properties']
    assert props['source'] == SOURCE_TRANSCRIPTION
    assert props['path'] == PATH_LEGACY


def test_source_for_conversation_distinguishes_transcript_from_external_integration():
    assert source_for_conversation(SimpleNamespace(source=ConversationSource.omi)) == SOURCE_TRANSCRIPTION
    assert (
        source_for_conversation(SimpleNamespace(source=ConversationSource.external_integration))
        == SOURCE_EXTERNAL_INTEGRATION
    )
    # Missing source defaults to transcription (the transcript path).
    assert source_for_conversation(SimpleNamespace(source=None)) == SOURCE_TRANSCRIPTION


def test_posthog_failure_is_swallowed_and_never_breaks_extraction():
    class ExplodingPosthog:
        def capture(self, *, distinct_id, event, properties):
            raise RuntimeError('posthog down')

    met.set_posthog_client_for_tests(ExplodingPosthog())
    # Must not raise — telemetry is fail-open.
    _emit('uid-1', count=2)


def test_payload_properties_carry_no_content_or_identifiers():
    fake = FakePosthog()
    met.set_posthog_client_for_tests(fake)
    _emit('uid-secret-uid', count=2, source=SOURCE_EXTERNAL_INTEGRATION, path=PATH_LEGACY)

    props = fake.calls[0]['properties']
    # The uid is the analytics identity (distinct_id), never a property. The
    # property bag carries only bounded dimensions — no conversation id, memory
    # text, transcript content, prompts, provider payloads, or exception strings.
    assert set(props.keys()) == {'memory_count_bucket', 'source', 'path'}
    blob = repr(props)
    for forbidden in (
        'conversation_id',
        'conversation.id',
        'transcript',
        'memory_text',
        'content',
        'prompt',
        'gemini',
        'error',
        'uid-secret-uid',
    ):
        assert forbidden not in blob


def test_emit_is_idempotent_per_pass_and_count_reflects_the_pass():
    """One call == one event; re-invocation (re-finalization) re-emits the true
    count for that pass — never a cached or stale value, never a duplicate value
    for a single pass."""
    fake = FakePosthog()
    met.set_posthog_client_for_tests(fake)
    _emit('uid-1', count=3)
    _emit('uid-1', count=1)  # a later pass persisted a different count
    assert [c['properties']['memory_count_bucket'] for c in fake.calls] == ['3', '1']
    assert all(c['distinct_id'] == 'uid-1' for c in fake.calls)
