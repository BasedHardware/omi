"""Exact prompt inputs, successful-output checkpoints, and flag-off compatibility."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.conversations import llm_input_dedupe as dedupe
from utils.llm import margin_attribution


@pytest.fixture
def enabled(monkeypatch):
    # First-use model loading belongs to setup, outside the per-call CPU budget.
    import models.conversation  # noqa: F401

    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'true')
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **k: {})
    return SimpleNamespace(id='c', sync_content_revision=3)


def test_notes_unchanged_skips_changed_inputs_run(enabled, monkeypatch):
    from models.conversation import Structured

    generate = Mock(return_value=Structured(title='Saved title', overview='Saved summary'))
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


@pytest.mark.parametrize(
    'checkpoint,expected',
    [
        ('none', 'first_completion'),
        ('same', 'same_revision'),
        ('changed', 'changed_revision'),
        ('stale_output', 'unknown'),
        ('unstamped', 'unknown'),
    ],
)
def test_on_open_observes_loaded_checkpoint_without_reusing_it(enabled, monkeypatch, checkpoint, expected):
    from models.structured import Structured

    saved = Structured(title='Saved title', overview='Saved summary')
    prefix = {'context': 'FULL TRANSCRIPT\nSynthetic notes.'}
    row = {'v3_derived': True}
    if checkpoint != 'none':
        row.update(v3_notes_written=True, structured=saved.model_dump())
    if checkpoint not in {'none', 'unstamped'}:
        stamps = {}
        previous = {'context': 'An earlier transcript.'} if checkpoint == 'changed' else prefix
        dedupe.notes('u', enabled, previous, lambda *a, **kw: saved, stamps)
        row.update(stamps)
    if checkpoint == 'stale_output':
        row['structured'] = Structured(title='New title', overview='New summary').model_dump()
    before = dict(row)
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: pytest.fail('foreground notes read a checkpoint'))
    result = Structured(title='Newly generated title')

    def generate(*args, **kwargs):
        assert margin_attribution.header_for('conversation_v3_summary_open') == f'{expected}/unknown'
        return result

    model = Mock(side_effect=generate)
    with dedupe.observe_foreground_completion(row):
        assert dedupe.notes('u', enabled, prefix, model, None) is result
    model.assert_called_once_with(prefix, uid='u', open_loop_out=None)
    assert row == before
    assert margin_attribution.header_for('conversation_v3_summary_open') is None


@pytest.mark.parametrize('words,scaled,regenerates', [(200, True, False), (6000, False, False), (6000, True, True)])
def test_notes_v4_only_rebuys_old_checkpoint_when_scaled_packet_changes(
    enabled, monkeypatch, words, scaled, regenerates
):
    monkeypatch.setattr(dedupe, 'NOTES_UNSCALED_PREVIOUS_VERSION', 'notes-3')
    from models.structured import Structured

    monkeypatch.setattr(dedupe, 'noise_skip_enabled', lambda: True)
    monkeypatch.setenv('CONVERSATION_NOTES_SCALED_DETAIL_ENABLED', str(scaled).lower())
    prefix = {'context': 'FULL TRANSCRIPT\n' + 'detail ' * words}
    captured = []
    fingerprint = dedupe.fingerprint

    def capture(feature, inputs):
        captured.append(inputs)
        return fingerprint(feature, inputs)

    monkeypatch.setattr(dedupe, 'fingerprint', capture)
    generate = Mock(return_value=Structured(title='Saved title', overview='Saved summary'))
    hashes = {}
    dedupe.notes('u', enabled, prefix, generate, hashes)
    inputs_v3 = {key: value for key, value in captured[-1].items() if key != 'scaled_detail'}
    v3 = 'notes-3:' + dedupe.stable_implementation('notes').split(':', 1)[1]
    row = {
        **hashes,
        dedupe.NOTES_HASH: dedupe._fingerprint('notes', inputs_v3, v3),
        'structured': generate.return_value.model_dump(),
    }
    monkeypatch.setattr(dedupe, '_stored', lambda *_a, **_kw: row)
    generate.reset_mock()
    updated = {}
    dedupe.notes('u', enabled, prefix, generate, updated)
    assert generate.call_count == int(regenerates)
    assert ('scaled_detail' in captured[-1]) is regenerates
    assert updated[dedupe.NOTES_HASH] == fingerprint('notes', captured[-1])


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


def test_disabled_dedupe_preserves_calls_and_invalidates_only_metadata(monkeypatch):
    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'false')
    read = Mock(side_effect=AssertionError('must not read'))
    monkeypatch.setattr(dedupe, '_stored', read)
    monkeypatch.setattr(dedupe, 'fingerprint', read)
    generate = Mock(return_value='same')
    conversation = SimpleNamespace(id='c')
    assert dedupe.notes('u', conversation, 'prefix', generate, {}) == 'same'
    generate.assert_called_once_with('prefix', uid='u', open_loop_out=None)
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


def _counter_value(name, feature):
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value(name, {'feature': feature}) or 0


def test_evaluation_counters_report_hit_miss_and_checkpoint_error(enabled, monkeypatch):
    from models.conversation import Structured

    skipped = _counter_value('conversation_llm_input_dedupe_skipped_total', 'notes')
    misses = _counter_value('conversation_llm_input_dedupe_misses_total', 'notes')
    errors = _counter_value('conversation_llm_input_dedupe_checkpoint_errors_total', 'notes')
    l1_misses = _counter_value('conversation_llm_input_dedupe_misses_total', 'l1')

    generate = Mock(return_value=Structured(title='Fresh', overview='Fresh summary'))
    hashes = {}
    dedupe.notes('u', enabled, 'input', generate, hashes)
    assert _counter_value('conversation_llm_input_dedupe_misses_total', 'notes') == misses + 1
    assert _counter_value('conversation_llm_input_dedupe_checkpoint_errors_total', 'notes') == errors

    monkeypatch.setattr(dedupe, '_stored', lambda *a, **k: {**hashes, 'structured': generate.return_value.model_dump()})
    dedupe.notes('u', enabled, 'input', generate, {})
    assert _counter_value('conversation_llm_input_dedupe_skipped_total', 'notes') == skipped + 1
    assert _counter_value('conversation_llm_input_dedupe_misses_total', 'notes') == misses + 1

    monkeypatch.setattr(dedupe, '_stored', lambda *a, **k: {**hashes, 'structured': 'invalid stored shape'})
    dedupe.notes('u', enabled, 'input', generate, {})
    assert _counter_value('conversation_llm_input_dedupe_misses_total', 'notes') == misses + 2
    assert _counter_value('conversation_llm_input_dedupe_checkpoint_errors_total', 'notes') == errors + 1

    dedupe.l1_input('u', enabled, {'text': 'same'})
    assert _counter_value('conversation_llm_input_dedupe_misses_total', 'l1') == l1_misses + 1


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
def test_route_module_changes_invalidate_feature_fingerprints(monkeypatch, route_file):
    """Model routing changes alter the effective output even with identical prompts."""
    from pathlib import Path

    dedupe.routing_digest.cache_clear()
    original = Path.read_bytes
    before = {feature: dedupe.fingerprint(feature, 'same input') for feature in ('notes', 'l1')}

    def changed_route(path):
        contents = original(path)
        return contents + b'\n# changed route' if path.name == route_file else contents

    monkeypatch.setattr(Path, 'read_bytes', changed_route)
    dedupe.routing_digest.cache_clear()
    try:
        for feature, old in before.items():
            assert dedupe.fingerprint(feature, 'same input') != old
    finally:
        dedupe.routing_digest.cache_clear()


def test_empty_notes_checkpoint_is_not_first_summary_success(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from models.structured import Structured
    from utils.conversations import llm_input_dedupe as target

    monkeypatch.setenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'true')
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
    generate.assert_called_once()
    assert output.overview == rich.overview


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


def test_implementation_digest_is_the_explicit_prompt_version():
    # The reuse key is a deliberate version, not a digest of the source tree.
    from config.llm_input_versions import PROMPT_VERSIONS

    assert dedupe.implementation_digest('notes').startswith(PROMPT_VERSIONS['notes'] + ':')
    assert dedupe.implementation_digest('l1').startswith(PROMPT_VERSIONS['l1'] + ':')


@pytest.mark.parametrize('feature', ['notes', 'l1'])
def test_predeploy_checkpoint_survives_deploy_and_repeated_kill_switch_flips(enabled, monkeypatch, feature):
    monkeypatch.setattr(dedupe, 'NOTES_UNSCALED_PREVIOUS_VERSION', 'notes-3')
    from config.llm_input_legacy import LEGACY_IMPLEMENTATIONS
    from models.structured import Structured

    assert LEGACY_IMPLEMENTATIONS[feature], 'migration must include the pre-deploy main checkpoint'
    original = dedupe.implementation_digest
    monkeypatch.setattr(dedupe, 'implementation_digest', lambda _: LEGACY_IMPLEMENTATIONS[feature][0])
    generate = Mock(return_value=Structured(title='Already paid', overview='Useful stored work'))
    if feature == 'notes':
        hashes = {}
        dedupe.notes('u', enabled, {'context': 'unchanged'}, generate, hashes)
        row = {**hashes, 'structured': generate.return_value.model_dump()}
    else:
        digest, _ = dedupe.l1_input('u', enabled, {'text': 'unchanged'})
        row = {dedupe.L1_HASH: digest}
    monkeypatch.setattr(dedupe, 'implementation_digest', original)
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)
    for flag in ('true', 'off', 'true', 'off'):
        monkeypatch.setenv('EPISODE_COMPOSER_REUSE', flag)
        if feature == 'notes':
            hashes = {}
            assert dedupe.notes('u', enabled, {'context': 'unchanged'}, generate, hashes).title == 'Already paid'
            row.update(hashes)
            assert generate.call_count == 1
        else:
            digest, matched = dedupe.l1_input('u', enabled, {'text': 'unchanged'})
            assert matched, f'{flag} re-bought a successful checkpoint'
            row[dedupe.L1_HASH] = digest


@pytest.mark.parametrize('flag', ['true', 'off'])
def test_dependency_qualified_notes_checkpoint_survives_prompt_version_bump(enabled, monkeypatch, flag):
    monkeypatch.setattr(dedupe, 'NOTES_UNSCALED_PREVIOUS_VERSION', 'notes-3')
    from models.structured import Structured

    monkeypatch.setenv('EPISODE_COMPOSER_REUSE', flag)
    dependencies = '|'.join(f'{name}:{version}' for name, version in dedupe.INSTALLED_DEPENDENCY_VERSIONS)
    before_bump = f'notes-2:{dedupe.routing_digest()}:{dependencies}'
    generate = Mock(return_value=Structured(title='Already paid', overview='Useful stored work'))
    hashes = {}
    with monkeypatch.context() as old_process:
        old_process.setattr(dedupe, 'implementation_digest', lambda _: before_bump)
        dedupe.notes('u', enabled, {'context': 'unchanged'}, generate, hashes)
    row = {**hashes, 'structured': generate.return_value.model_dump()}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)

    for _ in range(2):
        current_hashes = {}
        output = dedupe.notes('u', enabled, {'context': 'unchanged'}, generate, current_hashes)
        assert output.title == 'Already paid'
        assert generate.call_count == 1
        assert current_hashes[dedupe.NOTES_HASH] != row[dedupe.NOTES_HASH]

    dedupe.notes('u', enabled, {'context': 'changed'}, generate, {})
    assert generate.call_count == 2


@pytest.mark.parametrize('feature', ['notes', 'l1'])
def test_historical_checkpoint_cannot_mask_changed_route(enabled, monkeypatch, feature):
    from config.llm_input_legacy import LEGACY_IMPLEMENTATIONS

    inputs = {'text': 'unchanged'}
    old = dedupe._fingerprint(feature, inputs, LEGACY_IMPLEMENTATIONS[feature][0])
    monkeypatch.setattr(dedupe, 'routing_digest', lambda: 'new-model-route')
    assert not dedupe._matches(old, feature, inputs, dedupe.fingerprint(feature, inputs))


def test_additive_gist_does_not_rebuy_a_stable_l8a_checkpoint(enabled, monkeypatch):
    monkeypatch.setattr(dedupe, 'NOTES_UNSCALED_PREVIOUS_VERSION', 'notes-3')
    from models.structured import Structured

    original = dedupe.implementation_digest
    monkeypatch.setattr(dedupe, 'implementation_digest', lambda _: f'notes-1:{dedupe.routing_digest()}')
    generate = Mock(return_value=Structured(title='Already paid', overview='Useful stored notes'))
    hashes = {}
    dedupe.notes('u', enabled, 'unchanged', generate, hashes)
    row = {**hashes, 'structured': generate.return_value.model_dump()}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)
    monkeypatch.setattr(dedupe, 'implementation_digest', original)
    assert dedupe.notes('u', enabled, 'unchanged', generate, {}).overview == 'Useful stored notes'
    assert generate.call_count == 1


@pytest.fixture
def dependency_identity():
    # Simulate a fresh process after upgrading an installed distribution.
    dedupe._legacy_implementation_digest.cache_clear()
    yield
    dedupe._legacy_implementation_digest.cache_clear()


@pytest.mark.parametrize('feature', ['notes', 'l1'])
@pytest.mark.parametrize('dependency', ['pydantic', 'langchain-core'])
@pytest.mark.parametrize('flag', ['true', 'off'])
def test_dependency_upgrade_invalidates_checkpoint_in_both_modes(
    enabled, monkeypatch, dependency_identity, feature, dependency, flag
):
    monkeypatch.setenv('EPISODE_COMPOSER_REUSE', flag)
    inputs = {'text': 'unchanged'}
    saved = dedupe.fingerprint(feature, inputs)
    stable = dedupe.stable_implementation(feature)
    monkeypatch.setattr(
        dedupe,
        'INSTALLED_DEPENDENCY_VERSIONS',
        tuple(
            (name, version + '.changed' if name == dependency else version)
            for name, version in dedupe.INSTALLED_DEPENDENCY_VERSIONS
        ),
    )
    dedupe._legacy_implementation_digest.cache_clear()
    digest = dedupe.fingerprint(feature, inputs)
    assert digest != saved
    assert dedupe.stable_implementation(feature) != stable
    assert not dedupe._matches(saved, feature, inputs, digest)


@pytest.mark.parametrize('feature', ['notes', 'l1'])
@pytest.mark.parametrize('dependency', [None, 'pydantic', 'langchain-core'])
@pytest.mark.parametrize('flag', ['true', 'off'])
def test_historical_aliases_require_the_recorded_dependency_versions(
    enabled, monkeypatch, dependency_identity, feature, dependency, flag
):
    monkeypatch.setattr(dedupe, 'NOTES_UNSCALED_PREVIOUS_VERSION', 'notes-3')
    monkeypatch.setenv('EPISODE_COMPOSER_REUSE', flag)
    monkeypatch.setattr(
        dedupe,
        'INSTALLED_DEPENDENCY_VERSIONS',
        tuple(
            (name, version + '.changed' if name == dependency else version)
            for name, version in dedupe.LEGACY_DEPENDENCY_VERSIONS
        ),
    )
    inputs = {'text': 'unchanged'}
    digest = dedupe.fingerprint(feature, inputs)
    for implementation in dedupe.LEGACY_IMPLEMENTATIONS[feature]:
        saved = dedupe._fingerprint(feature, inputs, implementation)
        assert dedupe._matches(saved, feature, inputs, digest) == (dependency is None)


@pytest.mark.parametrize('dependency', ['pydantic', 'langchain-core'])
def test_dependency_upgrade_recomputes_notes_once_then_reuses_across_flag_flips(
    enabled, monkeypatch, dependency_identity, dependency
):
    from models.structured import Structured

    generate = Mock(return_value=Structured(title='Paid notes', overview='Useful stored work'))
    row = {}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)

    def process():
        hashes = {}
        dedupe.notes('u', enabled, {'context': 'unchanged'}, generate, hashes)
        row.update(hashes, structured=generate.return_value.model_dump())

    process()
    monkeypatch.setattr(
        dedupe,
        'INSTALLED_DEPENDENCY_VERSIONS',
        tuple(
            (name, version + '.changed' if name == dependency else version)
            for name, version in dedupe.INSTALLED_DEPENDENCY_VERSIONS
        ),
    )
    dedupe._legacy_implementation_digest.cache_clear()
    for flag in ('true', 'off', 'true', 'off'):
        monkeypatch.setenv('EPISODE_COMPOSER_REUSE', flag)
        process()
        assert generate.call_count == 2


def test_key_modes_do_not_read_dependency_metadata_per_call(enabled, monkeypatch, dependency_identity):
    monkeypatch.setattr(dedupe, 'distribution_version', Mock(side_effect=AssertionError('per-call metadata read')))
    for flag in ('true', 'off'):
        monkeypatch.setenv('EPISODE_COMPOSER_REUSE', flag)
        for feature in ('notes', 'l1'):
            assert dedupe.fingerprint(feature, {'text': 'unchanged'})


@pytest.mark.parametrize(
    'version,words',
    [('notes-3', 200), ('notes-4', 200), ('notes-4', 6000), ('notes-8', 200), ('notes-8', 6000), ('notes-10', 6000)],
)
def test_quality_contract_reuses_clean_old_checkpoint_without_a_paid_call(enabled, monkeypatch, version, words):
    from models.structured import Structured
    from copy import deepcopy

    monkeypatch.setattr(dedupe, 'noise_skip_enabled', lambda: True)
    monkeypatch.setenv('CONVERSATION_NOTES_SCALED_DETAIL_ENABLED', 'true')
    captured = []
    real_fingerprint = dedupe.fingerprint

    def capture(feature, inputs):
        captured.append(deepcopy(inputs))
        return real_fingerprint(feature, inputs)

    monkeypatch.setattr(dedupe, 'fingerprint', capture)
    prefix = {'context': 'FULL TRANSCRIPT\n' + 'budget ' * words}
    note = Structured(title='Pilot budget', overview='The budget is $8,000.')
    generate = Mock(return_value=note)
    hashes = {}
    dedupe.notes('u', enabled, prefix, generate, hashes)
    old_inputs = deepcopy(captured[-1])
    if 'scaled_detail' in old_inputs:
        old_inputs['scaled_detail']['version'] = version
    old_version = version + ':' + dedupe.stable_implementation('notes').split(':', 1)[1]
    row = {
        **hashes,
        dedupe.NOTES_HASH: dedupe._fingerprint('notes', old_inputs, old_version),
        'structured': note.model_dump(),
    }
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)
    claim = Mock(side_effect=AssertionError('clean checkpoint must not reserve a paid repair'))
    monkeypatch.setattr(dedupe, '_claim_quality_repair', claim)
    generate.reset_mock()
    for _ in range(3):
        current = {}
        output = dedupe.notes('u', enabled, prefix, generate, current)
        row.update(current, structured=output.model_dump())
    generate.assert_not_called()
    claim.assert_not_called()
    dedupe.notes('u', enabled, {'context': 'changed content'}, generate, {})
    generate.assert_called_once()


@pytest.mark.parametrize('violation', ['capture_availability', 'empty_heading'])
@pytest.mark.parametrize('repair_fails', [False, True])
def test_only_visible_concrete_violations_get_one_reserved_regeneration(enabled, monkeypatch, violation, repair_fails):
    from models.structured import Structured

    old = Structured(title='Pilot budget', overview='The budget is $8,000. Transcript is missing.')
    if violation == 'empty_heading':
        old = Structured(
            title='Pilot budget',
            overview='The budget is $8,000.',
            sections=[{'heading': '', 'body_markdown': 'Approval Friday.'}],
        )
    generate = Mock(return_value=old)
    hashes = {}
    dedupe.notes('u', enabled, 'unchanged', generate, hashes)
    row = {**hashes, 'structured': old.model_dump()}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)
    claims = set()

    def claim(uid, conversation, saved, key):
        if key in claims:
            return False
        claims.add(key)
        return True

    monkeypatch.setattr(dedupe, '_claim_quality_repair', claim)
    metric = Mock()
    monkeypatch.setattr(dedupe, 'QUALITY_REGENERATIONS', metric)
    generate.reset_mock()
    generate.side_effect = RuntimeError('paid repair failed') if repair_fails else None
    generate.return_value = old  # Even an unsuccessful model repair cannot loop.
    for attempt in range(3):
        current = {}
        if repair_fails and attempt == 0:
            with pytest.raises(RuntimeError):
                dedupe.notes('u', enabled, 'unchanged', generate, current)
            assert current == {}
        else:
            output = dedupe.notes('u', enabled, 'unchanged', generate, current)
            row.update(current, structured=output.model_dump())
    assert generate.call_count == 1 and len(claims) == 1
    metric.labels.assert_called_once_with(reason=violation)
    metric.labels.return_value.inc.assert_called_once()


def test_hidden_checkpoint_is_filtered_without_a_quality_regeneration(enabled, monkeypatch):
    from models.structured import Structured

    old = Structured(title='Pilot budget', overview='Budget approved. Transcript is missing.')
    generate = Mock(return_value=old)
    hashes = {}
    dedupe.notes('u', enabled, 'unchanged', generate, hashes)
    row = {**hashes, 'structured': old.model_dump(), 'relevance_decision': {'verdict': 'discard'}}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)
    claim = Mock(side_effect=AssertionError('hidden output must not reserve a paid repair'))
    monkeypatch.setattr(dedupe, '_claim_quality_repair', claim)
    generate.reset_mock()
    output = dedupe.notes('u', enabled, 'unchanged', generate, {})
    assert output.overview == 'Budget approved.'
    generate.assert_not_called()
    claim.assert_not_called()


def test_filtered_empty_result_is_reused_after_single_quality_repair(enabled, monkeypatch):
    from models.structured import Structured

    old = Structured(title='Pilot budget', overview='Transcript is missing.')
    generate = Mock(return_value=old)
    hashes = {}
    dedupe.notes('u', enabled, 'unchanged', generate, hashes)
    row = {**hashes, 'structured': old.model_dump()}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)
    claim = Mock(return_value=True)
    monkeypatch.setattr(dedupe, '_claim_quality_repair', claim)
    generate.reset_mock()
    generate.return_value = Structured(title='Pilot budget', overview='')
    for _ in range(3):
        current = {}
        output = dedupe.notes('u', enabled, 'unchanged', generate, current)
        row.update(current, structured=output.model_dump())
    generate.assert_called_once()
    claim.assert_called_once()
    assert row[dedupe.QUALITY_FILTER_HASH]


def test_repair_reservation_error_reuses_filtered_output_without_spending(enabled, monkeypatch):
    from models.structured import Structured

    old = Structured(title='Budget', overview='Approval Friday. Transcript is missing.')
    generate = Mock(return_value=old)
    hashes = {}
    dedupe.notes('u', enabled, 'unchanged', generate, hashes)
    row = {**hashes, 'structured': old.model_dump()}
    monkeypatch.setattr(dedupe, '_stored', lambda *a, **kw: row)
    monkeypatch.setattr(dedupe.notes_quality_repair, 'claim', Mock(side_effect=RuntimeError('storage unavailable')))
    generate.reset_mock()
    output = dedupe.notes('u', enabled, 'unchanged', generate, {})
    assert output.overview == 'Approval Friday.'
    generate.assert_not_called()
