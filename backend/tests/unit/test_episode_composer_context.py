"""Owner background stays bounded, relevant and outside episode freshness."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import tiktoken

from config import episodes as config
from utils.episodes import composer_context as context
from utils.episodes.composer_detail import detail_budget


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


def test_relevance_and_visibility_filter_before_prompt_budget():
    memories = [
        {'content': 'My garden irrigation uses a rain sensor.', 'subject_attribution': 'user'},
        {'content': 'I am learning violin.'},
        {'content': 'Irrigation locked fact', 'is_locked': True},
        {'content': 'Irrigation rejected fact', 'user_review': False},
        {'content': 'Irrigation invalidated fact', 'invalid_at': 'yesterday'},
    ]
    block = context.relevant_memories([member()], memories)
    assert 'rain sensor' in block and '[user]' in block
    assert all(word not in block for word in ('violin', 'locked', 'rejected', 'invalidated'))


def test_loader_uses_chat_eligibility_for_canonical_memory_prompt(monkeypatch):
    from database import goals, users
    from models.memories import MemoryDB
    from utils.llms import memory as chat_memory
    from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION
    from utils.episodes import composer

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

    rows = [
        fact('eligible-self'),
        fact('third-party', subject_scope='third_party'),
        fact('unknown-person', subject_scope='unknown'),
        fact('document', kind='document'),
        fact('trigger', kind='trigger'),
        fact('inference', intent_backed=False),
        fact('unslotted', slot=None),
        fact('future-slot', slot='unreleased_slot'),
        fact('locked', is_locked=True),
        fact('rejected', user_review=False),
        fact('invalidated', invalid_at=datetime.now(timezone.utc)),
    ]
    monkeypatch.setattr(chat_memory, 'get_prompt_data', lambda _uid: ('Synthetic', [], [], rows))
    monkeypatch.setattr(users, 'get_ai_user_profile', lambda _uid: {})
    monkeypatch.setattr(goals, 'get_user_goals', lambda *_args, **_kw: [])
    background = context.gather('synthetic', [member()], owner='Synthetic', language='English', timezone='UTC')
    messages = composer.build_messages(
        [member()], owner='Synthetic', tz=ZoneInfo('UTC'), language='English', context=background
    )
    prompt = messages[1][1]
    assert 'eligible-self' in prompt
    assert all(row.id not in prompt for row in rows[1:])
    assert 'eligible-self' in chat_memory._render_ledger_prompt_context('Synthetic', rows)
    assert all(row.id not in chat_memory._render_ledger_prompt_context('Synthetic', rows) for row in rows[1:])


def test_background_is_token_bounded_for_multilingual_long_facts():
    memories = [{'content': 'irrigation ' + '园艺浇水计划。' * 2000} for _ in range(50)]
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
    from utils.episodes import composer

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
