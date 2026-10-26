"""Spelling context is grounded, bounded, opt-out, and read once per run."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from utils.llm import known_spellings as hints
from utils.llm import conversation_prompt_context as context


@pytest.fixture
def sources(monkeypatch):
    monkeypatch.delenv('CONVERSATION_KNOWN_SPELLINGS', raising=False)
    vocabulary = MagicMock(return_value=[{'spelling': 'Zev Lark', 'aliases': ['Zeff']}])
    people = MagicMock(return_value=[{'name': 'Tala Quill'}])
    monkeypatch.setattr(hints.dream_store, 'vocabulary', vocabulary)
    monkeypatch.setattr(hints, '_people_spellings', people)
    return vocabulary, people


def prefix(block, uid=None):
    return context.build_conversation_prompt_prefix(
        conversation_id='synthetic-conversation',
        transcript='Zeff will ask Tala to review the draft.',
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        known_spellings=block,
        uid=uid,
    )


@pytest.fixture
def llm_modules(monkeypatch):
    from utils.llm import conversation_processing, working_observations, memories

    @asynccontextmanager
    async def isolated_model(model):
        yield model

    monkeypatch.setattr(conversation_processing, 'isolated_notes_model', isolated_model)
    return conversation_processing, working_observations, memories


@pytest.mark.parametrize('cache_enabled', [False, True])
def test_default_on_block_follows_unchanged_shared_prefix(sources, monkeypatch, cache_enabled):
    monkeypatch.setattr(context, 'route_for_uid', lambda uid: 'new')
    block = hints.conversation_known_spellings('synthetic-owner')
    result = prefix(block, uid='synthetic-owner')
    plain = prefix('', uid='synthetic-owner')
    assert result.context == plain.context
    assert result.shaped_context == plain.shaped_context
    assert result.cache_key == plain.cache_key
    assert result.cache_eligible == plain.cache_eligible
    assert 'Zev Lark' in block and 'Zeff' in block and 'Tala Quill' in block
    assert 'only when the transcript clearly refers to them' in block
    assert 'Never invent a reference' in block
    assert 'infer attendance or speaker identity' in block
    messages = result.messages(cache_enabled=cache_enabled)
    assert messages[:2] == plain.messages(cache_enabled=cache_enabled)
    assert messages[2] == {'role': 'system', 'content': block}


def test_spelling_changes_preserve_explicit_cache_breakpoint(sources, monkeypatch):
    monkeypatch.setattr(context, 'has_cacheable_prefix', lambda text: len(text) > 1000)
    plain = prefix('')
    assert not prefix('Known spellings\n' + 'Synthetic ' * 150).cache_eligible
    long = context.build_conversation_prompt_prefix(
        conversation_id=plain.conversation_id,
        transcript='Synthetic discussion. ' * 100,
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
    )
    first = replace(long, known_spellings=hints.conversation_known_spellings('synthetic-owner'))
    second = replace(long, known_spellings='Known spellings\nSynthetic replacement')
    baseline = long.messages(cache_enabled=True)
    assert first.messages(cache_enabled=True)[:2] == second.messages(cache_enabled=True)[:2] == baseline
    assert baseline[1]['content'][0]['prompt_cache_breakpoint'] == context.EXPLICIT_CACHE_BREAKPOINT
    assert first.messages(cache_enabled=True)[2] != second.messages(cache_enabled=True)[2]


def test_empty_sources_produce_no_block(sources):
    for read in sources:
        read.return_value = []
    result = prefix(hints.conversation_known_spellings('synthetic-owner'))
    assert result.known_spellings == ''
    assert len(result.messages(cache_enabled=True)) == 2


def test_kill_switch_avoids_even_cached_context_and_all_reads(sources, monkeypatch):
    @hints.spelling_context_run
    def run():
        assert hints.conversation_known_spellings('synthetic-owner')
        monkeypatch.setenv('CONVERSATION_KNOWN_SPELLINGS', 'false')
        assert hints.conversation_known_spellings('synthetic-owner') == ''

    run()
    assert 'Known spellings' not in prefix(hints.conversation_known_spellings('synthetic-owner')).context
    for read in sources:
        read.assert_called_once_with('synthetic-owner')


def test_nested_steps_reuse_reads_but_new_run_and_other_owner_read_afresh(sources):
    @hints.spelling_context_run
    def step(uid):
        return hints.conversation_known_spellings(uid)

    @hints.spelling_context_run
    def run():
        assert step('synthetic-owner') == step('synthetic-owner')
        step('different-owner')

    run()
    assert sources[0].call_count == sources[1].call_count == 2
    step('synthetic-owner')
    assert sources[0].call_count == sources[1].call_count == 3


def test_failed_run_clears_scope(sources):
    @hints.spelling_context_run
    def run():
        hints.conversation_known_spellings('synthetic-owner')
        raise ValueError('synthetic failure')

    for _ in range(2):
        with pytest.raises(ValueError):
            run()
    assert sources[0].call_count == sources[1].call_count == 2


@pytest.mark.parametrize('failed_source', [0, 1])
def test_failed_dependency_is_nonfatal_and_cached(sources, monkeypatch, failed_source):
    sources[failed_source].side_effect = RuntimeError('unavailable')
    fallback = MagicMock()
    monkeypatch.setattr(hints, 'record_fallback', fallback)

    @hints.spelling_context_run
    def run():
        first = hints.conversation_known_spellings('synthetic-owner')
        assert first == hints.conversation_known_spellings('synthetic-owner')
        assert ('Tala Quill' if failed_source == 0 else 'Zev Lark') in first

    run()
    fallback.assert_called_once()
    assert fallback.call_args.kwargs['outcome'] == 'degraded'
    for read in sources:
        read.assert_called_once()


def test_block_is_capped_deduplicated_and_canonical_names_are_never_cut():
    vocabulary = [{'spelling': f'Synthetic Term {i}', 'aliases': ['Alias ' * 15] * 5} for i in range(100)]
    people = [{'name': 'Synthetic Person'}, {'name': 'synthetic term 0'}, {'name': '\n\t'}]
    block = hints.render_known_spellings(vocabulary, people)
    assert len(block) <= hints.MAX_CHARACTERS
    entries = [json.loads(line) for line in block.splitlines() if line.startswith('{')]
    assert len(entries) <= hints.MAX_TERMS
    assert any(row['spelling'] == 'Synthetic Person' for row in entries)
    assert len({row['spelling'].casefold() for row in entries}) == len(entries)
    assert all(row['spelling'] in [item['spelling'] for item in vocabulary] + ['Synthetic Person'] for row in entries)


def test_term_cap_and_untrusted_newlines():
    block = hints.render_known_spellings([{'spelling': str(i)} for i in range(100)], [])
    assert len([line for line in block.splitlines() if line.startswith('{')]) == hints.MAX_TERMS
    block = hints.render_known_spellings([{'spelling': 'Quorbi\n\x00Lab', 'aliases': ['Qorby\rLabs']}], [])
    row = json.loads(block.splitlines()[-1])
    assert row == {'spelling': 'Quorbi Lab', 'aliases': ['Qorby Labs']}


def test_real_notes_and_memory_callers_receive_the_same_spelling_block(sources, monkeypatch, llm_modules):
    notes, memories, _ = llm_modules

    monkeypatch.setenv('OMI_SHAPED_AGENT_MODE', 'on')
    block = hints.conversation_known_spellings('synthetic-owner')
    shared = prefix(block, uid='synthetic-owner')
    captured = {}

    class NotesModel:
        async def ainvoke(self, messages):
            captured['notes'] = messages
            return SimpleNamespace(
                content=json.dumps(
                    {
                        'title': 'Draft Review',
                        'overview': 'Review the draft.',
                        'emoji': '📝',
                        'category': 'business',
                        'sections': [],
                        'action_items': [],
                        'events': [],
                    }
                )
            )

    monkeypatch.setattr(notes, 'get_llm', lambda *args, **kwargs: NotesModel())
    notes.get_conversation_notes(
        shared,
        uid='synthetic-owner',
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
    )

    class MemoryModel:
        def invoke(self, messages):
            captured['memories'] = messages
            return SimpleNamespace(content='{"archive_items":[]}')

    memories.extract_l1_memory_archive_items_from_text(
        uid='synthetic-owner',
        source_id='synthetic-conversation',
        source_type='voice_transcript',
        text='Zeff will ask Tala to review the draft.',
        llm=MemoryModel(),
        prompt_prefix=shared,
        persist_route_outcomes=False,
        strict=True,
    )
    note_context = json.loads(captured['notes'][1]['content'])
    assert note_context['known_spellings'] == block
    assert block not in note_context['capture_evidence']
    memory_context = captured['memories'][2]['content'][0]['text']
    assert memory_context == shared.context
    assert block not in memory_context
    assert captured['memories'][3] == {'role': 'system', 'content': block}


def test_external_text_memory_prompt_receives_hints_as_instructions(sources, monkeypatch, llm_modules):
    _, _, memories = llm_modules

    monkeypatch.setattr(memories, '_get_language_instruction', lambda *args: 'Use English.')
    block = hints.conversation_known_spellings('synthetic-owner')
    model = MagicMock(return_value='{"facts":[]}')
    # to_memories uses the existing empty structured response contract.
    llm = SimpleNamespace(invoke=model)
    memories.extract_memories_from_text(
        'synthetic-owner',
        'Zeff will ask Tala to review the draft.',
        'audio',
        user_name='Synthetic Owner',
        memories_str='',
        content_date='2026-10-01',
        llm=llm,
        known_spellings=block,
        strict=True,
    )
    rendered = model.call_args.args[0].to_string()
    assert rendered.count(block) == 1


@pytest.mark.parametrize(
    'signal',
    [
        {'speech_samples': ['synthetic/sample.wav']},
        {'label_evidence': {'manual_labels': 1}},
        {'label_evidence': {'card_confirms': 1}},
        {'label_evidence': {'card_picks': 1}},
        {'label_evidence': {'auto_confirmed': 1}},
        {'aliases': ['Old Synthetic Name']},
        {'is_user_created': True},
    ],
)
def test_stored_user_evidence_admits_mononyms_and_unicode_names(signal):
    for name in ('Tala', 'tala', '林澄', 'Tala Quill'):
        assert hints._trusted_people_spellings([{'name': name, **signal}]) == [{'name': name}]


@pytest.mark.parametrize(
    'name', ['Mhmm', 'Just:', 'just', 'hmm', 'Chinese !', 'Mhmm 123', 'Spanish', 'happy', '123', '!!!', '123 !!!']
)
@pytest.mark.parametrize(
    'signal', [{'speech_samples': ['synthetic/sample.wav']}, {'label_evidence': {'manual_labels': 1}}]
)
def test_junk_names_are_rejected_even_with_stale_evidence(name, signal):
    assert hints._trusted_people_spellings([{'name': name, **signal}]) == []


@pytest.mark.parametrize(
    'signal',
    [
        {},
        {'created_at': 'synthetic-date', 'updated_at': 'synthetic-later-date'},
        {'confidence': 'confirmed', 'voice_readiness': 'ready', 'conversation_count': 40},
        {'created_by': 'user', 'source': 'manual', 'confirmed': True},  # not fields written by our schema
        {'label_evidence': {'auto_corrected': 2}},
        {'label_evidence': {'manual_labels': True}},
        {'label_evidence': {'card_confirms': '2'}},
        {'label_evidence': {'card_picks': -1}},
        {'speech_samples': [None, '', '  ', 1]},
        {'speech_samples': 'synthetic/sample.wav'},
        {'is_user_created': 'true'},
    ],
)
def test_unconfirmed_detections_and_guessed_metadata_are_not_authority(signal):
    assert hints._trusted_people_spellings([{'name': 'Tala Quill', **signal}]) == []
    assert hints._trusted_people_spellings([{'name': '明天重新讨论', **signal}]) == []


def test_renamed_person_does_not_map_old_filler_aliases_into_the_prompt():
    people = hints._trusted_people_spellings([{'name': 'Tala Quill', 'aliases': ['Just', '今天需要讨论']}])
    block = hints.render_known_spellings([], people)
    assert 'Tala Quill' in block and 'Just' not in block and '今天需要讨论' not in block


def test_empty_or_unchanged_aliases_are_not_rename_evidence():
    for name in ('Tala Quill', '明天重新讨论'):
        assert hints._trusted_people_spellings([{'name': name, 'aliases': [None, '', name]}]) == []


def test_dismissed_people_and_empty_names_are_excluded():
    for row in (
        {'name': 'Tala', 'is_dismissed': True},
        {'name': ''},
        {'name': None},
        {'name': '  '},
    ):
        assert hints._trusted_people_spellings([{**row, 'speech_samples': ['synthetic/sample.wav']}]) == []


def test_real_people_read_is_bounded_filtered_and_cached_per_run(monkeypatch):
    client = MagicMock()
    query = client.collection.return_value.document.return_value.collection.return_value
    query.limit.return_value = query
    snapshots = []
    for i, row in enumerate(
        [
            {'name': 'Tala Quill', 'label_evidence': {'manual_labels': 1}},
            {'name': 'Mhmm', 'speech_samples': ['synthetic/sample.wav']},
            {'name': '明天重新讨论'},
            {'name': 'Unconfirmed Synthetic'},
        ]
    ):
        snapshot = MagicMock(id=f'synthetic-person-{i}')
        snapshot.to_dict.return_value = row
        snapshots.append(snapshot)
    query.stream.return_value = snapshots
    monkeypatch.setattr(hints, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(hints.dream_store, 'vocabulary', MagicMock(return_value=[{'spelling': 'Quorbi'}]))
    monkeypatch.delenv('CONVERSATION_KNOWN_SPELLINGS', raising=False)

    @hints.spelling_context_run
    def run():
        first = hints.conversation_known_spellings('synthetic-owner')
        assert first == hints.conversation_known_spellings('synthetic-owner')
        assert 'Tala Quill' in first and 'Quorbi' in first
        assert all(junk not in first for junk in ('Mhmm', '明天重新讨论', 'Unconfirmed Synthetic'))

    run()
    query.limit.assert_called_once_with(200)
    query.stream.assert_called_once()
    run()
    assert query.limit.call_count == query.stream.call_count == 2


@pytest.fixture
def resolution_module():
    from utils.conversations import speaker_resolution

    return speaker_resolution


@pytest.mark.parametrize('people', [[], [{'name': 'Tala', 'speech_samples': ['synthetic/sample.wav']}]])
def test_speaker_resolution_reuses_its_full_list_without_an_extra_query(monkeypatch, resolution_module, people):
    stage = resolution_module
    monkeypatch.delenv('CONVERSATION_KNOWN_SPELLINGS', raising=False)
    monkeypatch.setattr(stage, 'load_owner_embedding', lambda *args, **kwargs: None)
    monkeypatch.setattr(stage, 'named_speaker_prompts_allowed', lambda uid: True)
    original_read = MagicMock(return_value=people)
    monkeypatch.setattr(stage.users_db, 'get_people', original_read)
    extra_read = MagicMock(side_effect=AssertionError('unexpected second People query'))
    monkeypatch.setattr(hints, 'list_people', extra_read)
    monkeypatch.setattr(hints.dream_store, 'vocabulary', MagicMock(return_value=[{'spelling': 'Quorbi'}]))

    @hints.spelling_context_run
    def run():
        stage.load_voiceprints_for_resolution('synthetic-owner', allow_audio_repair=False)
        block = hints.conversation_known_spellings('synthetic-owner')
        assert ('Tala' in block) == bool(people)
        assert block == hints.conversation_known_spellings('synthetic-owner')

    run()
    original_read.assert_called_once_with('synthetic-owner')
    extra_read.assert_not_called()


def test_reused_people_are_capped_and_do_not_leak_between_runs(monkeypatch):
    monkeypatch.delenv('CONVERSATION_KNOWN_SPELLINGS', raising=False)
    monkeypatch.setattr(hints, 'get_firestore_client', lambda: 'synthetic-client')
    read = MagicMock(return_value=[])
    monkeypatch.setattr(hints, 'list_people', read)
    rows = [{'name': 'Mhmm'}] * 200 + [
        {'name': f'Synthetic Person {i}', 'speech_samples': ['synthetic/sample.wav']} for i in range(61)
    ]

    @hints.spelling_context_run
    def seeded_run():
        hints.reuse_people_for_spellings('synthetic-owner', rows)
        spellings = hints._people_spellings('synthetic-owner')
        assert len(spellings) == hints.MAX_TERMS
        assert spellings[0] == {'name': 'Synthetic Person 0'}

    seeded_run()
    read.assert_not_called()
    # A reused list outside processing must not become a process-global cache.
    hints.reuse_people_for_spellings('synthetic-owner', rows)

    @hints.spelling_context_run
    def fresh_run():
        assert hints._people_spellings('synthetic-owner') == []

    fresh_run()
    read.assert_called_once_with('synthetic-client', 'synthetic-owner', limit=200)


def test_trusted_people_spellings_is_public():
    person = {'name': 'Tala Quill', 'speech_samples': ['synthetic/sample.wav']}
    assert hints.trusted_people_spellings([person]) == [{'name': 'Tala Quill'}]
    assert hints.trusted_people_spellings([{'name': 'Spanish', 'speech_samples': ['synthetic/sample.wav']}]) == []


def test_person_filter_does_not_filter_deliberately_learned_vocabulary():
    people = hints.trusted_people_spellings([{'name': 'Spanish'}])
    block = hints.render_known_spellings([{'spelling': 'Spanish', 'aliases': ['Synthetic Alias']}], people)
    assert 'Spanish' in block and 'Synthetic Alias' in block
