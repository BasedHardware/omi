"""Exact prompt inputs, successful-output checkpoints, and flag-off compatibility."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.conversations import llm_input_dedupe as dedupe


@pytest.fixture
def enabled(monkeypatch):
    # First-use model loading belongs to setup, outside the per-call CPU budget.
    import models.conversation  # noqa: F401

    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'true')
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **k: {})
    return SimpleNamespace(id='c', sync_content_revision=3)


def test_notes_unchanged_skips_changed_inputs_run(enabled, monkeypatch):
    from models.conversation import Structured

    generate = Mock(return_value=Structured(title='Saved title'))
    inputs = dict(
        language_code='en',
        tz='UTC',
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        output_language_code='en',
        existing_action_items=[],
        meeting_context='Calendar: planning',
    )
    hashes = {}
    prefix = {'context': 'FULL TRANSCRIPT\nWe will ship Friday.', 'known_spellings': 'Omi'}
    dedupe.notes('u', enabled, prefix, generate, hashes, **inputs)
    row = {**hashes, 'structured': generate.return_value.model_dump()}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **k: row)
    output = dedupe.notes('u', enabled, prefix, generate, {}, **inputs)
    assert output.title == 'Saved title' and generate.call_count == 1
    for name, value in [
        ('language_code', 'fr'),
        ('tz', 'Asia/Tokyo'),
        ('meeting_context', 'Different meeting'),
        ('started_at', datetime(2026, 10, 2, tzinfo=timezone.utc)),
        ('existing_action_items', [{'id': 'new', 'description': 'Ship'}]),
    ]:
        dedupe.notes('u', enabled, prefix, generate, {}, **{**inputs, name: value})
    dedupe.notes('u', enabled, {**prefix, 'context': 'A new word'}, generate, {}, **inputs)
    assert generate.call_count == 7


def test_failed_notes_do_not_stamp_hash(enabled):
    hashes = {}
    with pytest.raises(RuntimeError):
        dedupe.notes('u', enabled, {'context': 'text'}, Mock(side_effect=RuntimeError('provider')), hashes)
    assert hashes == {}


def test_l1_only_reuses_successful_exact_hash(enabled, monkeypatch):
    inputs = {'transcript': 'Remember Friday', 'language': 'en', 'date': '2026-10-01', 'context': {'owner': 'David'}}
    digest, matched = dedupe.l1_input('u', enabled, inputs)
    assert digest and not matched
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **k: {dedupe.L1_HASH: digest})
    assert dedupe.l1_input('u', enabled, inputs) == (digest, True)
    for name, value in [
        ('transcript', 'Remember Saturday'),
        ('language', 'fr'),
        ('date', '2026-10-02'),
        ('context', {'owner': 'Someone else'}),
    ]:
        changed, matched = dedupe.l1_input('u', enabled, {**inputs, name: value})
        assert changed != digest and not matched


def test_memory_l1_route_retarget_alone_invalidates_successful_hash(monkeypatch):
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    routes = {'memory_l1': 'old-model', 'memories': 'unchanged-model', 'conv_structure': 'notes-model'}
    monkeypatch.setattr(dedupe, 'get_route_ref', lambda feature: {'feature': feature, 'model': routes[feature]})
    conversation = SimpleNamespace(id='c', sync_content_revision=1)
    inputs = {'transcript': 'synthetic input', 'language': 'en'}
    digest, matched = dedupe.l1_input('u', conversation, inputs)
    assert digest and not matched
    conversation.l1_llm_input_hash = digest
    assert dedupe.l1_input('u', conversation, inputs) == (digest, True)
    routes['memory_l1'] = 'new-model'
    changed, matched = dedupe.l1_input('u', conversation, inputs)
    assert changed != digest and not matched


def test_disabled_dedupe_preserves_calls_and_invalidates_only_metadata(monkeypatch):
    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'false')
    read = Mock(side_effect=AssertionError('must not read'))
    monkeypatch.setattr(dedupe, '_stored', read)
    monkeypatch.setattr(dedupe, 'fingerprint', read)
    generate = Mock(return_value='same')
    conversation = SimpleNamespace(id='c')
    assert dedupe.notes('u', conversation, 'prefix', generate, {}) == 'same'
    generate.assert_called_once_with('prefix', uid='u')
    assert dedupe.l1_input('u', conversation, object()) == (None, False)
    invalidation = Mock(return_value=False)
    monkeypatch.setattr(dedupe, 'invalidate_l1', invalidation)
    assert not dedupe.l1_succeeded('u', conversation, None)
    invalidation.assert_called_once_with('u', conversation, db_client=None)
    read.assert_not_called()


def test_unknown_input_objects_are_rejected_instead_of_stringified():
    with pytest.raises(TypeError):
        dedupe.fingerprint('notes', object())


def test_new_capture_records_first_success_hash_without_reading_missing_id(enabled, monkeypatch):
    monkeypatch.setattr(dedupe, '_stored', Mock(side_effect=AssertionError('new captures have no stored row')))
    hashes = {}
    generate = Mock(return_value='new notes')
    assert dedupe.notes('u', SimpleNamespace(), {'conversation_id': 'generated'}, generate, hashes) == 'new notes'
    assert hashes[dedupe.NOTES_HASH]
    generate.assert_called_once()


@pytest.fixture(scope='module')
def memory_module():
    import importlib
    from testing.import_isolation import stub_modules

    with stub_modules({}):
        pc = importlib.import_module('utils.conversations.process_conversation')
        from models.conversation import Conversation
        from models.structured import Structured
        from models.transcript_segment import TranscriptSegment

        yield pc, Conversation, Structured, TranscriptSegment


@pytest.fixture
def memory_stack(memory_module, monkeypatch):
    pc, Conversation, Structured, TranscriptSegment = memory_module
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    conversation = Conversation(
        id='memory-input',
        sync_content_revision=1,
        created_at=now,
        started_at=now,
        finished_at=now,
        source='omi',
        language='en',
        structured=Structured(title='Saved'),
        transcript_segments=[TranscriptSegment(text='We will ship Friday.', start=0, end=10, is_user=False)],
    )
    service = Mock()
    monkeypatch.setattr(pc, 'MemoryService', lambda **_: service)
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda *_: 'en')
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda *_: 'UTC')
    monkeypatch.setattr(pc, 'get_user_name', lambda *_: 'David')
    monkeypatch.setattr(pc, 'conversation_known_spellings', lambda *_: 'Omi')
    monkeypatch.setattr(pc, '_stored_meeting_context', lambda *_: None)
    monkeypatch.setattr(pc, 'rich_roster_inputs', lambda *_: (None, False))
    monkeypatch.setattr(pc, 'conversation_transcript_and_speaker_map', lambda *_: ('Ship Friday', {}))
    monkeypatch.setattr(pc, 'may_attribute_to_owner', lambda *_: True)
    monkeypatch.setattr(pc, '_rejected_memory_examples_for_l1', lambda *_, **__: ())
    yield pc, conversation, service


def test_l1_orchestration_only_stamps_after_replacement_and_skips_exact_retry(enabled, memory_stack, monkeypatch):
    pc, conversation, service = memory_stack
    row = {}
    monkeypatch.setattr(dedupe, '_stored', lambda *_, **__: row)
    stamps = []

    def succeeded(uid, conv, digest, **kwargs):
        service.replace_conversation_memories.assert_called()
        stamps.append(digest)
        row[dedupe.L1_HASH] = digest
        return True

    monkeypatch.setattr(dedupe, 'l1_succeeded', succeeded)
    extract = Mock(return_value=[])
    monkeypatch.setattr(pc, 'extract_canonical_l1_memory_candidates', extract)
    pc._extract_memories_canonical('u', conversation, db_client=Mock())
    pc._extract_memories_canonical('u', conversation, db_client=Mock())
    assert extract.call_count == 1 and len(stamps) == 1
    service.replace_conversation_memories.assert_called_once()
    conversation.transcript_segments[0].text += ' Actually Saturday.'
    pc._extract_memories_canonical('u', conversation, db_client=Mock())
    assert extract.call_count == 2 and len(stamps) == 2


def test_l1_failed_extraction_or_replacement_never_stamps(enabled, memory_stack, monkeypatch):
    pc, conversation, service = memory_stack
    stamp = Mock()
    monkeypatch.setattr(dedupe, 'l1_succeeded', stamp)
    monkeypatch.setattr(
        pc, 'extract_canonical_l1_memory_candidates', Mock(side_effect=pc.MemoryExtractionError('provider'))
    )
    pc._extract_memories_canonical('u', conversation, db_client=Mock())
    service.replace_conversation_memories.assert_not_called()
    stamp.assert_not_called()
    monkeypatch.setattr(pc, 'extract_canonical_l1_memory_candidates', Mock(return_value=[]))
    service.replace_conversation_memories.side_effect = RuntimeError('storage unavailable')
    with pytest.raises(RuntimeError):
        pc._extract_memories_canonical('u', conversation, db_client=Mock())
    stamp.assert_not_called()


def test_notes_checkpoint_does_not_describe_a_replaced_output(enabled, monkeypatch):
    from models.conversation import Structured

    generate = Mock(return_value=Structured(title='Original successful notes'))
    hashes = {}
    dedupe.notes('u', enabled, {'context': 'original transcript'}, generate, hashes)
    # Another writer or a flag-off pass replaces the structure without an
    # accompanying fingerprint update. Input A must not reuse output B.
    row = {**hashes, 'structured': Structured(title='A different output').model_dump()}
    monkeypatch.setattr(dedupe, '_stored', lambda *_, **__: row)
    dedupe.notes('u', enabled, {'context': 'original transcript'}, generate, {})
    assert generate.call_count == 2


def test_invalid_checkpoint_output_is_a_cache_miss(enabled, monkeypatch):
    hashes = {}
    generate = Mock(return_value='valid generated output')
    dedupe.notes('u', enabled, 'input', generate, hashes)
    monkeypatch.setattr(dedupe, '_stored', lambda *_: {**hashes, 'structured': 'invalid stored shape'})
    assert dedupe.notes('u', enabled, 'input', generate, {}) == 'valid generated output'
    assert generate.call_count == 2


@pytest.mark.parametrize('enabled_flag', [False, True])
def test_l1_checkpoint_uses_injected_client_even_when_disabled(memory_stack, monkeypatch, enabled_flag):
    from database import _client
    from google.cloud import firestore

    _, conversation, _ = memory_stack
    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', str(enabled_flag).lower())
    global_client = Mock(side_effect=AssertionError('must use injected client, never ADC'))
    monkeypatch.setattr(_client, 'get_firestore_client', global_client)
    monkeypatch.setattr(firestore, 'transactional', lambda commit: commit)
    client = Mock()
    ref = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    digest = dedupe.fingerprint('l1', {'text': 'same'}) if enabled_flag else None
    ref.get.return_value.exists = True
    ref.get.return_value.to_dict.return_value = {
        'sync_content_revision': conversation.sync_content_revision,
        dedupe.L1_HASH: digest or 'old-success',
    }
    assert dedupe.l1_input('u', conversation, {'text': 'same'}, db_client=client) == (digest, enabled_flag)
    assert dedupe.l1_succeeded('u', conversation, digest, db_client=client)
    if enabled_flag:
        client.transaction.return_value.update.assert_called_once_with(ref, {dedupe.L1_HASH: digest})
    else:
        ref.update.assert_called_once()
        assert ref.update.call_args.args == ({dedupe.L1_HASH: None},)
    global_client.assert_not_called()


@pytest.mark.parametrize('route_file', ['model_config.py', 'model_constants.py', 'clients.py', 'providers.py'])
def test_route_module_changes_invalidate_both_feature_fingerprints(monkeypatch, route_file):
    from pathlib import Path

    original = Path.read_bytes
    dedupe.implementation_digest.cache_clear()
    before = {feature: dedupe.fingerprint(feature, 'same input') for feature in ('notes', 'l1')}

    def changed_route(path):
        contents = original(path)
        return contents + b'\n# changed route' if path.name == route_file else contents

    try:
        monkeypatch.setattr(Path, 'read_bytes', changed_route)
        dedupe.implementation_digest.cache_clear()
        for feature, old in before.items():
            assert dedupe.fingerprint(feature, 'same input') != old
    finally:
        dedupe.implementation_digest.cache_clear()


@pytest.mark.parametrize('summary_gate', [False, True])
def test_empty_notes_checkpoint_is_not_first_summary_success(monkeypatch, summary_gate):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from models.structured import Structured
    from utils.conversations import llm_input_dedupe as target

    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true' if summary_gate else 'false')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)
    empty = Structured(title='Server transcript title', overview='')
    rich = Structured(title='Generated title', overview='A supported synthetic summary')
    monkeypatch.setattr(target, 'fingerprint', lambda *_: 'same-input')
    monkeypatch.setattr(
        target,
        '_stored',
        lambda *_: {
            target.NOTES_HASH: 'same-input',
            target.NOTES_OUTPUT_HASH: target.output_fingerprint(empty),
            'structured': empty.model_dump(),
            'discarded': False,
        },
    )
    monkeypatch.setattr(target, 'record_feature', lambda *_: None)
    generate = Mock(return_value=rich)
    output = target.notes('u', SimpleNamespace(id='c'), [], generate, {})
    if summary_gate:
        generate.assert_called_once()
        assert output.overview == rich.overview
    else:
        generate.assert_not_called()
        assert output.overview == ''


def test_effective_packet_cohort_and_version_invalidate_notes_checkpoint(enabled, monkeypatch):
    from utils.llm import notes_packet
    from config.refactor_modes import uid_digest

    owner = 'synthetic-packet-account'
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'shadow')
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', raising=False)
    monkeypatch.delenv('NOTES_PACKET_V2_MODE_SERVE_PERCENT', raising=False)
    generate = Mock(return_value='synthetic output')

    def digest():
        hashes = {}
        dedupe.notes(owner, enabled, 'synthetic prefix', generate, hashes)
        return hashes[dedupe.NOTES_HASH]

    legacy = digest()
    monkeypatch.setenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', uid_digest(owner))
    serving = digest()
    assert serving != legacy
    monkeypatch.setattr(notes_packet, 'PACKET_VERSION', notes_packet.PACKET_VERSION + 1)
    assert digest() != serving
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    assert digest() == legacy


def test_implementation_digest_tracks_packet_output_language_and_evidence_modules():
    # Read the actual dependency closure; a missing/renamed module must invalidate generation.
    dedupe.implementation_digest.cache_clear()
    assert len(dedupe.implementation_digest('notes')) == 64
