"""Spelling context is grounded, bounded, opt-out, and read once per run."""

import json
from contextlib import asynccontextmanager
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


def test_default_on_block_reaches_shared_and_shaped_context(sources, monkeypatch):
    monkeypatch.setattr(context, 'route_for_uid', lambda uid: 'new')
    block = hints.conversation_known_spellings('synthetic-owner')
    result = prefix(block, uid='synthetic-owner')
    assert 'Known spellings' in result.context
    assert 'Zev Lark' in result.context and 'Zeff' in result.context and 'Tala Quill' in result.context
    assert 'only when the transcript clearly refers to them' in result.context
    assert 'Never invent a reference' in result.context
    assert 'infer attendance or speaker identity' in result.context
    assert block in result.shaped_context
    messages = result.messages(cache_enabled=False)
    assert messages[1]['content'][0]['text'].count('Known spellings') == 1


def test_empty_sources_produce_no_block(sources):
    for read in sources:
        read.return_value = []
    result = prefix(hints.conversation_known_spellings('synthetic-owner'))
    assert 'Known spellings' not in result.context


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
    note_evidence = json.loads(captured['notes'][1]['content'])['capture_evidence']
    assert note_evidence.count(block) == 1
    memory_context = captured['memories'][2]['content'][0]['text']
    assert memory_context.count(block) == 1
    assert 'Zev Lark' in note_evidence and 'Zev Lark' in memory_context


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
