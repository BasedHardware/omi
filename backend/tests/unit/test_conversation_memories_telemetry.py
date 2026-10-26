"""Behavioral contract for the backend Conversation Memories Extracted telemetry.

Mirrors test_integration_sync_telemetry.py: a fake PostHog client captures emits,
and every test asserts the closed schema, the zero/failure boundaries, and the
durable retry/idempotency behavior (at most one analytics success per
(uid, conversation) across re-finalization), and that no conversation id, memory
text, transcript content, prompts, provider payloads, or exception strings can
reach PostHog.
"""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from utils.product_telemetry import set_product_telemetry_client_for_tests as set_posthog_client_for_tests
from utils import product_telemetry

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
from utils.conversations import process_conversation


class FakePosthog:
    def __init__(self):
        self.calls = []

    def capture(self, *, distinct_id, event, properties):
        self.calls.append({'distinct_id': distinct_id, 'event': event, 'properties': dict(properties)})


class _FakeDurableClaim:
    """Mimics Firestore ``create``: a permanent marker exists after the first
    claim and cannot be re-acquired by later retries."""

    def __init__(self):
        self.claimed: set[tuple[str, str]] = set()

    def acquire(self, uid: str, conversation_id: str) -> bool:
        key = (uid, conversation_id)
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True


@pytest.fixture(autouse=True)
def _reset_posthog_client():
    set_posthog_client_for_tests(None)
    yield
    set_posthog_client_for_tests(None)


@pytest.fixture(autouse=True)
def _fake_durable_claim(monkeypatch):
    """Replace the Firestore marker with an in-memory atomic-create equivalent
    so tests assert permanent retry semantics hermetically."""
    claim = _FakeDurableClaim()
    monkeypatch.setattr(met, "try_claim_conversation_memory_analytics", claim.acquire)
    return claim


def _emit(uid, conversation_id, *, count, source=SOURCE_TRANSCRIPTION, path=PATH_CANONICAL):
    emit_conversation_memories_extracted(
        uid, conversation_id, ConversationMemoryExtractionResult(count=count, source=source, path=path)
    )


def test_emits_one_bounded_event_after_successful_persistence():
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)

    _emit('uid-1', 'conv-1', count=2, source=SOURCE_TRANSCRIPTION, path=PATH_CANONICAL)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call['distinct_id'] == 'uid-1'
    assert call['event'] == 'Conversation Memories Extracted'
    # Closed extraction dimensions plus shared server defaults.
    assert set(call['properties'].keys()) == {
        'memory_count_bucket',
        'source',
        'path',
        'source_platform',
        'emitter',
        'environment',
        'test',
    }
    assert call['properties']['memory_count_bucket'] == '2'
    assert call['properties']['source'] == 'transcription'
    assert call['properties']['path'] == 'canonical'


def test_zero_extraction_emits_nothing():
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)
    _emit('uid-1', 'conv-1', count=0)
    assert fake.calls == []


def test_empty_uid_or_conversation_id_emits_nothing():
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)
    _emit('', 'conv-1', count=3)
    _emit('uid-1', '', count=3)
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
    set_posthog_client_for_tests(fake)
    _emit('uid-1', 'conv-1', count=count)
    assert fake.calls[0]['properties']['memory_count_bucket'] == expected


def test_invalid_source_and_path_fall_back_to_closed_values():
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)
    # Unknown enum values collapse to a closed default, never an open string.
    emit_conversation_memories_extracted(
        'uid-1',
        'conv-1',
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


def test_posthog_failure_is_swallowed_and_records_bounded_fallback(monkeypatch):
    class ExplodingPosthog:
        def capture(self, **kwargs):
            raise RuntimeError('private')

    set_posthog_client_for_tests(ExplodingPosthog())
    fallbacks = []
    monkeypatch.setattr(product_telemetry, 'record_fallback', lambda **fields: fallbacks.append(fields))
    _emit('u', 'c', count=1)
    assert fallbacks[0]['outcome'] == 'degraded'


def test_payload_properties_carry_no_content_or_identifiers():
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)
    _emit('uid-secret-uid', 'conv-secret-1', count=2, source=SOURCE_EXTERNAL_INTEGRATION, path=PATH_LEGACY)

    props = fake.calls[0]['properties']
    # The uid is the analytics identity (distinct_id), never a property. The
    # conversation id is the dedup lock key only. The property bag carries only
    # bounded dimensions — no conversation id, memory text, transcript content,
    # prompts, provider payloads, or exception strings.
    assert set(props.keys()) == {
        'memory_count_bucket',
        'source',
        'path',
        'source_platform',
        'emitter',
        'environment',
        'test',
    }
    blob = repr(props)
    for forbidden in (
        'conv-secret-1',
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


def test_retry_for_same_conversation_does_not_re_emit():
    """Re-finalization of the same conversation must not inflate the metric: the
    first successful pass emits exactly once; a retry that re-persists finds the
    durable per-conversation slot already claimed and emits nothing."""
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)

    _emit('uid-1', 'conv-A', count=2)
    _emit('uid-1', 'conv-A', count=2)  # retry / re-finalization of the same conversation
    _emit('uid-1', 'conv-A', count=1)  # third retry with a different count still deduped

    assert len(fake.calls) == 1
    assert fake.calls[0]['properties']['memory_count_bucket'] == '2'


def test_distinct_conversations_emit_independently():
    """The dedup key is (uid, conversation_id); different conversations each emit."""
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)

    _emit('uid-1', 'conv-A', count=2)
    _emit('uid-1', 'conv-B', count=3)
    _emit('uid-2', 'conv-A', count=1)  # different user, same conversation id string -> distinct

    assert len(fake.calls) == 3
    assert {c['properties']['memory_count_bucket'] for c in fake.calls} == {'2', '3', '1'}


def test_durable_claim_outage_skips_telemetry_and_retry_never_duplicates(monkeypatch):
    """A durable-claim outage must fail closed: extraction continues, but no
    unverified success is captured. A later retry after an already-claimed
    conversation is still suppressed, proving cache loss cannot re-open it."""

    def _raising_claim(_uid, _conversation_id):
        raise RuntimeError('firestore down')

    monkeypatch.setattr(met, "try_claim_conversation_memory_analytics", _raising_claim)
    fallbacks = []
    monkeypatch.setattr(met, 'record_fallback', lambda **fields: fallbacks.append(fields))
    fake = FakePosthog()
    set_posthog_client_for_tests(fake)

    # Must not raise, and must not emit a potentially duplicate success.
    _emit('uid-1', 'conv-A', count=2)
    assert fake.calls == []
    assert fallbacks == [
        {
            'component': 'memory_analytics',
            'from_mode': 'durable_claim',
            'to_mode': 'telemetry_skipped',
            'reason': 'other',
            'outcome': 'degraded',
            'log': met.logger,
        }
    ]

    claimed = _FakeDurableClaim()
    claimed.claimed.add(('uid-1', 'conv-A'))
    monkeypatch.setattr(met, "try_claim_conversation_memory_analytics", claimed.acquire)
    _emit('uid-1', 'conv-A', count=2)
    assert fake.calls == []


def test_posthog_constructor_failure_is_fail_open_at_public_extraction_boundary(monkeypatch):
    result = ConversationMemoryExtractionResult(count=1, source=SOURCE_TRANSCRIPTION, path=PATH_CANONICAL)
    monkeypatch.setattr(process_conversation, '_extract_memories_inner', lambda _uid, _conversation: result)
    monkeypatch.setattr(process_conversation, '_sweep_owned_writer_mode', lambda _uid: None)
    monkeypatch.setattr(process_conversation, 'track_usage', lambda *_args: nullcontext())
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'phc_configured-test-key')
    constructor = []

    def broken(_name):
        constructor.append(True)
        raise RuntimeError('private')

    monkeypatch.setattr(product_telemetry.importlib, 'import_module', broken)
    process_conversation.extract_memories(
        'uid-1', SimpleNamespace(id='conv-1', source=ConversationSource.external_integration)
    )
    assert constructor == [True]
