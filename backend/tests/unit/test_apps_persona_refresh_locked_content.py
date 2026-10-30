"""Persona refresh must keep paywalled context out of model input and stored prompts.

Load the complete production apps module through the sanctioned import-isolation
fixture. Memory models, conversation validation, summary selection and rendering
remain real; persistence and LLM calls are deterministic boundary doubles.
"""

import asyncio
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def persona_refresh(monkeypatch):
    # utils.apps eagerly binds provider/database collaborators. Keep these
    # scoped to this fixture while loading its real implementation and renderer.
    stubs = {
        name: AutoMockModule(name)
        for name in (
            'database.cache',
            'database.redis_db',
            'database.apps',
            'database.auth',
            'database.conversations',
            'database._client',
            'database.users',
            'database.folders',
            'utils.memory.memory_service',
            'utils.stripe',
            'utils.llm.persona',
            'utils.llm.usage_tracker',
            'utils.executors',
            'utils.social',
        )
    }
    with stub_modules(stubs):
        apps = load_module_fresh('utils.apps', str(BACKEND_DIR / 'utils' / 'apps.py'))
        from models.memories import MemoryDB

        recorded = {'memories': [], 'conversations': [], 'saved': [], 'invalidated': []}

        async def inline_run_blocking(_executor, function, *args, **kwargs):
            return function(*args, **kwargs)

        def condense_memories(contents, _name):
            recorded['memories'].append(list(contents))
            return '\n'.join(contents)

        def condense_conversations(histories):
            recorded['conversations'].append(list(histories))
            return '\n'.join(histories)

        monkeypatch.setattr(apps, 'run_blocking', inline_run_blocking)
        monkeypatch.setattr(apps, 'get_user_name', lambda _uid: 'Ada')
        monkeypatch.setattr(apps, 'track_usage', lambda *_args, **_kwargs: nullcontext())
        monkeypatch.setattr(apps, 'condense_memories', condense_memories)
        monkeypatch.setattr(apps, 'condense_conversations', condense_conversations)
        monkeypatch.setattr(apps, 'update_persona_in_db', lambda value: recorded['saved'].append(deepcopy(value)))
        monkeypatch.setattr(apps, 'delete_app_cache_by_id', recorded['invalidated'].append)

        def refresh(memories, conversations, *, previous_prompt=''):
            monkeypatch.setattr(
                apps,
                'MemoryService',
                lambda **_kwargs: SimpleNamespace(read=lambda *_args, **_kwargs: memories),
            )
            monkeypatch.setattr(apps, 'get_conversations', lambda *_args, **_kwargs: deepcopy(conversations))
            # A malformed fixture must not masquerade as successful filtering.
            assert len(apps.deserialize_conversations(conversations)) == len(conversations)
            persona = {
                'id': 'persona-1',
                'uid': 'user-1',
                'connected_accounts': [],
                'persona_prompt': previous_prompt,
            }
            asyncio.run(apps.update_persona_prompt(persona))
            assert len(recorded['saved']) == 1
            assert recorded['saved'][0]['id'] == 'persona-1'
            assert recorded['invalidated'] == ['persona-1']
            return recorded['saved'][0]['persona_prompt']

        yield SimpleNamespace(refresh=refresh, recorded=recorded, MemoryDB=MemoryDB)


def _memory(model, content, *, locked=False, visibility='public'):
    return model(
        id=content,
        uid='user-1',
        content=content,
        created_at=NOW,
        updated_at=NOW,
        is_locked=locked,
        visibility=visibility,
    )


def _conversation(prefix, summary_kind, *, locked=False):
    structured = {
        'title': f'{prefix}_TITLE',
        'overview': f'{prefix}_SUMMARY' if summary_kind == 'overview' else '',
        'category': 'other',
        'action_items': [{'description': f'{prefix}_ACTION', 'completed': False}],
        'events': [{'title': f'{prefix}_EVENT', 'start': NOW, 'duration': 15}],
    }
    if summary_kind == 'sections':
        structured['sections'] = [{'heading': 'Notes', 'body_markdown': f'{prefix}_SUMMARY'}]
    conversation = {
        'id': prefix,
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW,
        'structured': structured,
        'transcript_segments': [
            {
                'id': f'{prefix}-segment',
                'text': f'{prefix}_TRANSCRIPT',
                'speaker': 'SPEAKER_00',
                'is_user': True,
                'start': 0.0,
                'end': 1.0,
            }
        ],
    }
    if locked is not None:
        conversation['is_locked'] = locked
    if summary_kind == 'app':
        conversation['apps_results'] = [{'app_id': 'summary-app', 'content': f'{prefix}_SUMMARY'}]
    return conversation


@pytest.mark.parametrize('summary_kind', ['overview', 'sections', 'app'])
def test_refresh_persists_only_unlocked_public_memory_and_unlocked_conversation_context(persona_refresh, summary_kind):
    model = persona_refresh.MemoryDB
    memories = [
        _memory(model, 'LOCKED_MEMORY', locked=True),
        _memory(model, 'PRIVATE_MEMORY', visibility='private'),
        _memory(model, 'VISIBLE_MEMORY'),
    ]
    conversations = [
        _conversation('LOCKED', summary_kind, locked=True),
        _conversation('VISIBLE', summary_kind),
        _conversation('LEGACY', summary_kind, locked=None),
    ]

    prompt = persona_refresh.refresh(memories, conversations)

    memory_input = '\n'.join(content for call in persona_refresh.recorded['memories'] for content in call)
    conversation_input = '\n'.join(history for call in persona_refresh.recorded['conversations'] for history in call)
    for forbidden in ('LOCKED_MEMORY', 'PRIVATE_MEMORY'):
        assert forbidden not in memory_input
        assert forbidden not in prompt
    assert 'VISIBLE_MEMORY' in memory_input
    assert 'VISIBLE_MEMORY' in prompt
    for field in ('TITLE', 'SUMMARY', 'ACTION', 'EVENT'):
        assert f'LOCKED_{field}' not in conversation_input
        assert f'LOCKED_{field}' not in prompt
        for prefix in ('VISIBLE', 'LEGACY'):
            assert f'{prefix}_{field}' in conversation_input
            assert f'{prefix}_{field}' in prompt
    for prefix in ('LOCKED', 'VISIBLE', 'LEGACY'):
        assert f'{prefix}_TRANSCRIPT' not in conversation_input
        assert f'{prefix}_TRANSCRIPT' not in prompt


def test_refresh_with_only_locked_context_replaces_the_previous_prompt(persona_refresh):
    memories = [_memory(persona_refresh.MemoryDB, 'LOCKED_MEMORY', locked=True)]
    conversations = [_conversation('LOCKED', 'overview', locked=True)]

    prompt = persona_refresh.refresh(memories, conversations, previous_prompt='STALE_PERSONAL_CONTEXT')

    assert persona_refresh.recorded['memories'] == [[]]
    assert all(not history.strip() for call in persona_refresh.recorded['conversations'] for history in call)
    assert 'STALE_PERSONAL_CONTEXT' not in prompt
    assert 'LOCKED_' not in prompt
