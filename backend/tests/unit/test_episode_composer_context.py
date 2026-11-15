"""Owner background stays bounded, relevant and outside episode freshness."""

from datetime import datetime, timedelta, timezone
import subprocess
import sys
from zoneinfo import ZoneInfo

import tiktoken
import pytest
from unittest.mock import create_autospec

from config import episodes as config
from utils.llms import memory as chat_memory
from utils.episodes import composer
from utils.episodes import composer_context as context
from utils.episodes.composer_detail import detail_budget


@pytest.fixture(autouse=True)
def profile_sources(monkeypatch):
    from utils.episodes import composer_context_io as sources

    monkeypatch.setattr(sources, 'profile', lambda *_args: {'profile_text': 'A gardener.'})
    monkeypatch.setattr(sources, 'goals', lambda *_args: [])
    monkeypatch.setattr(sources, 'people', lambda *_args: [])


def member(words=30000, minutes=240):
    at = datetime(2026, 11, 14, tzinfo=timezone.utc)
    return {
        'id': 'synthetic-recording',
        'started_at': at,
        'finished_at': at + timedelta(minutes=minutes),
        'structured': {'title': 'Garden irrigation', 'overview': 'Installing the garden irrigation controller.'},
        'transcript_segments': [{'start': 0, 'end': minutes * 60, 'text': 'irrigation ' * words}],
    }


def tokens(text):
    # The unit harness stubs tiktoken without get_encoding; exercise the safe byte fallback there.
    if not hasattr(tiktoken, 'get_encoding'):
        return len(text.encode('utf-8'))
    return len(tiktoken.get_encoding('o200k_base').encode(text, disallowed_special=()))


def owner_fact(content, **fields):
    return {
        'content': content,
        'kind': 'fact',
        'subject_scope': 'primary_user',
        'subject_attribution': 'user',
        **fields,
    }


def test_selector_reuses_chat_policy_without_importing_runtime_clients():
    assert context.is_prompt_memory_eligible is chat_memory.is_prompt_memory_eligible
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'import sys; from utils.episodes import composer_context; '
            'assert "utils.llms.memory" not in sys.modules; '
            'assert not any(name.startswith("database") for name in sys.modules)',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_relevance_and_visibility_filter_before_prompt_budget():
    memories = [
        owner_fact('My garden irrigation uses a rain sensor.'),
        {'content': 'I am learning violin.'},
        {'content': 'Irrigation locked fact', 'is_locked': True},
        {'content': 'Irrigation rejected fact', 'user_review': False},
        {'content': 'Irrigation invalidated fact', 'invalid_at': 'yesterday'},
    ]
    block = context.relevant_memories([member()], memories)
    assert 'rain sensor' in block and '[primary_user]' in block
    assert all(word not in block for word in ('violin', 'locked', 'rejected', 'invalidated'))


@pytest.mark.parametrize('source', ['list', 'vector'])
def test_loader_layers_strict_legacy_privacy_over_chat_policy(monkeypatch, source):
    from database import goals, users
    from models.memories import MemoryDB
    from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION

    def fact(label, **overrides):
        return MemoryDB.model_construct(
            id=label,
            content=f'Garden irrigation {label}',
            **{
                'ledger_schema_version': LEDGER_SCHEMA_VERSION,
                'kind': 'fact',
                'subject_scope': 'primary_user',
                'intent_backed': True,
                'slot': 'current_focus',
                **overrides,
            },
        )

    allowed = [
        fact('eligible-self'),
        fact('eligible-legacy-self', ledger_schema_version=None, subject_attribution='user'),
    ]
    denied = [
        MemoryDB.model_construct(id='legacy-unstamped', content='Garden irrigation unstamped'),
        MemoryDB.model_construct(
            id='legacy-interesting', content='Garden irrigation interesting', category='interesting'
        ),
        MemoryDB.model_construct(id='legacy-manual', content='Garden irrigation manual', manually_added=True),
        fact('third-party', subject_scope='third_party'),
        fact('unknown-person', subject_scope='unknown'),
        fact('canonical-attributed-third-party', subject_attribution='third_party'),
        fact('canonical-attributed-unknown', subject_attribution='unknown'),
        fact('document', kind='document'),
        fact('trigger', kind='trigger'),
        fact('inference', intent_backed=False),
        fact('unslotted', slot=None),
        fact('future-slot', slot='unreleased_slot'),
        fact('locked', is_locked=True),
        fact('rejected', user_review=False),
        fact('invalidated', invalid_at=datetime.now(timezone.utc)),
        fact('legacy-third-party', ledger_schema_version=None, subject_scope='third_party'),
        fact('legacy-unknown', ledger_schema_version=None, subject_scope='unknown'),
        fact('legacy-attributed-third-party', ledger_schema_version=None, subject_attribution='third_party'),
        fact('legacy-attributed-unknown', ledger_schema_version=None, subject_attribution='unknown'),
        fact('legacy-document', ledger_schema_version=None, kind='document'),
        fact('legacy-null-kind', ledger_schema_version=None, kind=None),
        fact('legacy-null-scope', ledger_schema_version=None, subject_scope=None),
        fact('legacy-null-attribution', ledger_schema_version=None, subject_attribution=None),
        fact('legacy-trigger', ledger_schema_version=None, kind='trigger'),
    ]
    rows = allowed + denied
    monkeypatch.setattr(context, '_list_memories', lambda *_args: rows)
    if source == 'list':
        monkeypatch.setattr(context, '_search_memories', lambda *_args, **_kw: [])
    else:
        from types import SimpleNamespace
        from utils.memory.memory_service import MemoryService

        def search(_self, _uid, _query, **kwargs):
            assert kwargs['result_filter'] is context.composer_memory_eligible
            # Recheck even when an adapter incorrectly returns unsafe hits.
            return [SimpleNamespace(memory=row) for row in rows]

        monkeypatch.setattr(
            MemoryService, 'search', create_autospec(MemoryService.search, side_effect=search, spec_set=True)
        )
    monkeypatch.setattr(users, 'get_ai_user_profile', lambda _uid: {})
    monkeypatch.setattr(goals, 'get_user_goals', lambda *_args, **_kw: [])
    background = context.gather('synthetic', [member()], owner='Synthetic', language='English', timezone='UTC')
    messages = composer.build_messages(
        [member()], owner='Synthetic', tz=ZoneInfo('UTC'), language='English', context=background
    )
    prompt = messages[1][1]
    assert all(row.id in prompt for row in allowed)
    assert all(row.id not in prompt for row in denied)
    assert '[unknown]' not in prompt and '[legacy_unspecified]' not in prompt
    # Chat's legacy compatibility contract is intentionally unchanged tonight.
    assert chat_memory.is_prompt_memory_eligible(denied[-1])
    assert not context.composer_memory_eligible(denied[-1])


def test_query_and_ranking_prefer_people_projects_over_passing_mentions():
    row = member(words=20)
    row['structured'] = {'title': 'Atlas release with Priya', 'overview': 'Atlas delivery and launch checklist.'}
    row['transcript_segments'] = [
        {'text': 'Priya owns the Atlas delivery checklist.'},
        {'text': 'The Atlas launch needs Priya to review the checklist.'},
        {'text': 'I saw a violin outside.'},
    ]
    query = context.retrieval_query([row])
    assert 'priya' in query and 'atlas' in query and 'checklist' in query
    assert tokens(query) <= config.COMPOSER_MEMORY_QUERY_TOKENS
    block = context.relevant_memories(
        [row],
        [
            owner_fact('I enjoy playing violin.'),
            owner_fact('Priya is my colleague on Atlas.'),
            owner_fact('Atlas is my current release project.'),
        ],
    )
    assert 'Priya is my colleague' in block and 'current release project' in block
    assert 'violin' not in block


@pytest.mark.parametrize('missing', ['kind', 'subject_scope', 'subject_attribution'])
def test_legacy_owner_fact_requires_all_explicit_attribution_stamps(missing):
    row = owner_fact('Garden irrigation is my project.')
    assert context.composer_memory_eligible(row)
    row.pop(missing)
    assert not context.composer_memory_eligible(row)


def test_loader_prefers_chat_hydrated_vector_search_and_rechecks_eligibility(monkeypatch):
    from types import SimpleNamespace
    from database import goals, users
    from utils.memory.memory_service import MemoryService

    seen = []

    def search(_self, uid, query, **kwargs):
        seen.append((uid, query, kwargs))
        # Even a buggy adapter returning an unvetted row must not leak it.
        return [
            SimpleNamespace(memory=owner_fact('Irrigation rain sensor.')),
            SimpleNamespace(memory={'content': 'Irrigation locked content.', 'is_locked': True}),
        ]

    monkeypatch.setattr(
        MemoryService, 'search', create_autospec(MemoryService.search, side_effect=search, spec_set=True)
    )
    monkeypatch.setattr(chat_memory, 'get_prompt_data', lambda _uid: (_ for _ in ()).throw(AssertionError('fallback')))
    monkeypatch.setattr(users, 'get_ai_user_profile', lambda _uid: {})
    monkeypatch.setattr(goals, 'get_user_goals', lambda *_a, **_kw: [])
    _, block = context.gather('synthetic', [member()], owner='Synthetic', language='English', timezone='UTC')
    assert len(seen) == 1 and 'irrigation' in seen[0][1]
    options = seen[0][2]
    budget = options.pop('budget')
    assert 0 < budget.remaining_seconds <= 8 and budget.max_documents == 160
    assert options == {
        'limit': 20,
        'candidate_limit': 60,
        'result_filter': context.composer_memory_eligible,
        'vector_only': True,
    }
    assert 'rain sensor' in block and 'locked' not in block


def test_search_outage_omits_memories_without_list_fallback(monkeypatch):
    from utils.metrics import OMI_FALLBACK_TOTAL

    counter = OMI_FALLBACK_TOTAL.labels(
        component='conversation_notes',
        from_mode='episode_memories',
        to_mode='without_memories',
        reason='transport_error',
        outcome='degraded',
    )._value
    before = counter.get()
    monkeypatch.setattr(
        context, '_search_memories', lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError('synthetic'))
    )
    monkeypatch.setattr(context, '_list_memories', lambda *_a: pytest.fail('no list fallback after search failure'))
    profile, block = context.gather('synthetic', [member()], owner='Synthetic', language='English', timezone='UTC')
    assert profile == '{"name": "Synthetic", "output_language": "English"}' and block == ''
    assert counter.get() == before + 1


def test_background_is_token_bounded_for_multilingual_long_facts():
    memories = [owner_fact('irrigation ' + '园艺浇水计划。' * 2000) for _ in range(50)]
    assert 0 < tokens(context.relevant_memories([member()], memories)) <= config.COMPOSER_MEMORY_TOKENS
    owner = context.owner_block(
        owner='Synthetic',
        language='Chinese',
        timezone='UTC',
        profile={'ai_user_profile': {'profile_text': '园艺。' * 20000}},
        goals=[],
        people=[],
    )
    assert tokens(owner) <= config.COMPOSER_PROFILE_TOKENS


def test_long_episode_budget_and_short_sparse_speech_do_not_share_ceiling(monkeypatch):
    cap, guidance = detail_budget([member()])
    assert cap == 15 and '2550-3450' in guidance
    short_cap, short_guidance = detail_budget([member(200, 5)])
    assert short_cap == 4 and '85-115' in short_guidance
    assert '85-115' in detail_budget([member(200, 240)])[1]
    monkeypatch.setenv(config.EPISODE_COMPOSER_DETAIL_ENV, 'false')
    assert detail_budget([member()]) == (8, '')


def test_profile_renders_only_selected_fields_and_people():
    block = context.owner_block(
        owner='Synthetic',
        language='English',
        timezone='UTC',
        profile={'private_key': 'never-render', 'ai_user_profile': {'profile_text': 'A gardener.'}},
        goals=[{'title': 'Plant trees', 'private': 'never-render'}],
        people=[
            {'name': 'Alex', 'relationship': 'friend', 'voice_secret': 'never-render'},
            {'name': 'Dismissed', 'is_dismissed': True},
        ],
    )
    assert all(v in block for v in ('gardener', 'Plant trees', 'friend'))
    assert 'never-render' not in block and 'Dismissed' not in block


def test_prompt_contains_guarded_background_and_scales_output(monkeypatch):

    row = member()
    messages = composer.build_messages(
        [row], owner='Synthetic', tz=ZoneInfo('UTC'), language='English', context=('A gardener', 'A rain sensor')
    )
    assert '2550-3450' in messages[0][1] and 'do not establish attendance' in messages[0][1]
    assert 'do not turn a possible suggestion into an assigned task' in messages[0][1]
    assert 'Do not infer whole-day coverage' in messages[0][1]
    assert 'About the owner' in messages[1][1] and 'Relevant memories' in messages[1][1]
    assert messages[1][1].index('Transcript:') < messages[1][1].index('About the owner')
    before = composer.fingerprint([row])
    monkeypatch.setenv(config.EPISODE_COMPOSER_CONTEXT_ENV, 'false')
    monkeypatch.setenv(config.EPISODE_COMPOSER_DETAIL_ENV, 'false')
    legacy = composer.build_messages(
        [row], owner='Synthetic', tz=ZoneInfo('UTC'), language='English', context=('changed', 'changed')
    )
    assert composer.fingerprint([row]) == before and config.COMPOSER_VERSION == 'episode_composer_v2'
    assert 'About the owner' not in legacy[1][1]
    assert legacy[0][1] == composer.SYSTEM_PROMPT.format(owner='Synthetic', language='English', max_chapters=8)


def test_more_than_eight_chapters_survive_write_and_wire(monkeypatch):
    from utils.episodes import composer, service

    row = member()
    row['transcript_segments'] = [
        {'start': i * 900, 'end': (i + 1) * 900, 'text': 'irrigation ' * 2000} for i in range(15)
    ]
    chapters = [
        {
            'title': f'Topic {i}',
            'start': f'{i//4:02}:{(i%4)*15:02}:00',
            'points': [{'text': 'Decision', 'details': ['Supporting detail']}],
        }
        for i in range(15)
    ]
    data = {'title': 'Garden', 'lede': 'Garden plans', 'chapters': chapters}
    updates = composer.to_updates(data, [row], ZoneInfo('UTC'))
    assert len(updates['moments']) == 15
    wire = service.to_wire({'id': 'synthetic', **updates})
    assert len(wire['moments']) == 15
    assert all(m['points'][0]['details'] == ['Supporting detail'] for m in wire['moments'])
    monkeypatch.setenv(config.EPISODE_COMPOSER_DETAIL_ENV, 'false')
    assert len(composer.to_updates(data, [row], ZoneInfo('UTC'))['moments']) == 8
