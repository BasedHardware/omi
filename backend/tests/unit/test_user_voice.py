"""Unit tests for per-person user voice profiling and ``propose_message`` draft polishing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from utils import device_tools
from utils.device_tools import build_device_tools, device_tool_result_key
from utils.llm import user_voice
from utils.llm.user_voice import (
    USER_VOICE_CACHE_TTL_SECONDS,
    build_propose_message_voice_prompt_for_turn,
    build_user_voice_profile,
    cache_user_voice_profile,
    clear_user_voice_state_for_tests,
    get_cached_user_voice_profile,
    get_or_build_user_voice_profile,
    is_user_voice_enabled,
    polish_draft_in_user_voice,
    set_user_voice_enabled,
)


@pytest.fixture(autouse=True)
def reset_user_voice_state():
    clear_user_voice_state_for_tests()
    with patch.object(user_voice, 'redis_client', None):
        yield
    clear_user_voice_state_for_tests()


@pytest.fixture
def two_person_fixtures():
    """Fixtures for two people ('alex-friend' and 'dr-chen') the same user writes to very differently."""
    conversations = [
        # Person 1: Alex (close friend — short lowercase lines, no periods, no exclamations, 'yo'/'hey')
        {
            'id': 'conv-alex-1',
            'is_locked': False,
            'person_ids': ['person-alex'],
            'participants': ['Alex'],
            'transcript_segments': [
                {'text': 'yo are you free around 7', 'is_user': True, 'person_id': None},
                {'text': 'Yeah I can do 7!', 'is_user': False, 'person_id': 'person-alex'},
                {'text': 'hey running 5 mins late', 'is_user': True, 'person_id': None},
                {'text': 'sounds good see u outside', 'is_user': True, 'person_id': None},
                {'text': 'yo grabbed us a table in the back', 'is_user': True, 'person_id': None},
            ],
        },
        # Person 2: Dr. Chen (professional contact — full sentences, periods, capitalized greetings, longer)
        {
            'id': 'conv-chen-1',
            'is_locked': False,
            'person_ids': ['person-chen'],
            'participants': ['Dr. Chen'],
            'transcript_segments': [
                {
                    'text': 'Hello Dr. Chen, thank you for reviewing the updated clinical protocol today.',
                    'is_user': True,
                    'person_id': None,
                },
                {
                    'text': 'Happy to help, let us discuss the timeline.',
                    'is_user': False,
                    'person_id': 'person-chen',
                },
                {
                    'text': 'Hi Dr. Chen, I have attached the revised budget figures for Thursday.',
                    'is_user': True,
                    'person_id': None,
                },
                {
                    'text': 'Good morning Dr. Chen, please let me know if 2 PM works for our call.',
                    'is_user': True,
                    'person_id': None,
                },
                {
                    'text': 'Hello Dr. Chen, we finalized the slides and sent them to the board.',
                    'is_user': True,
                    'person_id': None,
                },
            ],
        },
        # Locked conversation with Alex — must be excluded from profiling!
        {
            'id': 'conv-alex-locked',
            'is_locked': True,
            'person_ids': ['person-alex'],
            'participants': ['Alex'],
            'transcript_segments': [
                {
                    'text': 'SECRET LOCKED LINE WITH EXCLAMATIONS!!! 🎉🎉🎉',
                    'is_user': True,
                    'person_id': None,
                },
                {
                    'text': 'ANOTHER LOCKED LINE THAT MUST NEVER APPEAR IN EXAMPLES!!! 🎉',
                    'is_user': True,
                    'person_id': None,
                },
            ],
        },
    ]

    messages = [
        {
            'sender': 'human',
            'person_id': 'person-alex',
            'recipient': '+15550101',
            'text': 'hey can we push dinner to 7:30',
        },
        {
            'sender': 'human',
            'person_id': 'person-chen',
            'recipient': 'chen@clinic.org',
            'text': 'Hello Dr. Chen, thank you for the quick turnaround on the draft.',
        },
    ]
    return conversations, messages


def test_builds_distinct_profiles_for_two_people_same_user(two_person_fixtures):
    conversations, messages = two_person_fixtures

    alex_profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id='person-alex',
        person_name='Alex',
        recipient='+15550101',
    )
    chen_profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id='person-chen',
        person_name='Dr. Chen',
        recipient='chen@clinic.org',
    )

    # Alex: short, bare endings ('none'), zero exclamation rate, lowercase starts, casual greetings
    assert alex_profile.dominant_ending == 'none'
    assert alex_profile.exclamation_rate == 0.0
    assert alex_profile.max_exclamations_per_line == 0
    assert alex_profile.lowercase_start_rate >= 0.8
    assert alex_profile.typical_word_count < chen_profile.typical_word_count
    assert any(g.lower().startswith(('yo', 'hey')) for g in alex_profile.greetings)
    assert 3 <= len(alex_profile.examples) <= 5

    # Dr. Chen: longer, period endings ('period'), uppercase starts, formal greetings
    assert chen_profile.dominant_ending == 'period'
    assert chen_profile.ending_rates['period'] >= 0.8
    assert chen_profile.lowercase_start_rate == 0.0
    assert any(g.lower().startswith(('hello', 'hi', 'good morning')) for g in chen_profile.greetings)
    assert 3 <= len(chen_profile.examples) <= 5


def test_locked_conversations_are_excluded(two_person_fixtures):
    conversations, messages = two_person_fixtures

    alex_profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id='person-alex',
        person_name='Alex',
    )

    for example in alex_profile.examples:
        assert 'SECRET LOCKED' not in example
        assert 'ANOTHER LOCKED' not in example
    assert alex_profile.emoji_rate == 0.0
    assert alex_profile.exclamation_rate == 0.0


def test_conversations_merely_about_person_and_sender_none_messages_are_ignored():
    conversations = [
        # Conversation with someone else that merely mentions Alex in title/overview and has a substring recipient
        {
            'id': 'conv-about-alex',
            'is_locked': False,
            'person_ids': ['person-other'],
            'participants': ['Bob'],
            'recipients': ['+15550101999'],
            'structured': {
                'title': 'Talking about Alex',
                'overview': 'Discussed Alex project timeline.',
            },
            'transcript_segments': [
                {'text': 'Formal sentence about Alex that ends with a period.', 'is_user': True},
            ],
        },
    ]
    messages = [
        # Missing sender must NOT be treated as user-authored
        {'sender': None, 'person_id': 'person-alex', 'text': 'Assistant output with missing sender!'},
        {'sender': 'ai', 'person_id': 'person-alex', 'text': 'Another assistant line!'},
    ]
    profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id='person-alex',
        person_name='Alex',
        recipient='+15550101',
    )
    assert profile.sample_count == 0


def test_language_and_script_mix_detection():
    bilingual_convs = [
        {
            'id': 'conv-bilingual',
            'is_locked': False,
            'person_ids': ['person-lin'],
            'transcript_segments': [
                {'text': 'hey 今天晚上见', 'is_user': True},
                {'text': 'ok 我七点到餐厅', 'is_user': True},
                {'text': 'sounds good 待会见', 'is_user': True},
            ],
        }
    ]
    profile = build_user_voice_profile(conversations=bilingual_convs, person_id='person-lin', person_name='Lin')
    assert 'latin' in profile.script_mix
    assert 'cjk' in profile.script_mix
    assert 'cjk' in profile.languages


def test_opt_in_gate_and_seven_day_cache(two_person_fixtures):
    conversations, messages = two_person_fixtures
    uid = 'user-42'

    # Default is opted out.
    assert is_user_voice_enabled(uid, 'person-alex') is False
    assert (
        get_or_build_user_voice_profile(
            uid,
            person_id='person-alex',
            conversations=conversations,
            messages=messages,
        )
        is None
    )

    # Enable account-level opt-in.
    set_user_voice_enabled(uid, True)
    assert is_user_voice_enabled(uid, 'person-alex') is True

    clock = [1_700_000_000.0]
    profile = get_or_build_user_voice_profile(
        uid,
        person_id='person-alex',
        person_name='Alex',
        conversations=conversations,
        messages=messages,
        now_fn=lambda: clock[0],
    )
    assert profile is not None
    assert profile.dominant_ending == 'none'

    # Cached for 7 days: still present at 6 days 23 hours, even with empty inputs.
    clock[0] += USER_VOICE_CACHE_TTL_SECONDS - 3600
    cached = get_cached_user_voice_profile(uid, 'person-alex', now_fn=lambda: clock[0])
    assert cached is not None
    assert cached.examples == profile.examples

    # Expired after 7 days.
    clock[0] += 3601
    assert get_cached_user_voice_profile(uid, 'person-alex', now_fn=lambda: clock[0]) is None


def test_deterministic_polish_fixes_ending_punctuation_and_exclamation_count(two_person_fixtures):
    conversations, messages = two_person_fixtures
    alex_profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id='person-alex',
        person_name='Alex',
    )
    chen_profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id='person-chen',
        person_name='Dr. Chen',
    )

    # AI-sounding draft to Alex: over-punctuated with "!" and trailing period/emoji.
    raw_to_alex = 'Hey! Sounds great — I will see you at 7! 😊'
    polished_alex = polish_draft_in_user_voice(raw_to_alex, alex_profile)
    assert polished_alex == 'hey sounds great I will see you at 7'
    assert '!' not in polished_alex
    assert '.' not in polished_alex
    assert '😊' not in polished_alex
    assert '—' not in polished_alex
    assert polished_alex[0].islower()

    # Draft to Dr. Chen missing terminal period and containing AI exclamations.
    raw_to_chen = 'Hello Dr. Chen! I sent over the revised protocol!!'
    polished_chen = polish_draft_in_user_voice(raw_to_chen, chen_profile)
    assert '!' not in polished_chen
    assert polished_chen.endswith('.')
    assert polished_chen.startswith('Hello Dr. Chen,')


@pytest.mark.asyncio
async def test_propose_message_applies_user_voice_polish_before_opening_sheet(two_person_fixtures):
    conversations, messages = two_person_fixtures
    uid = 'uid-voice-1'
    set_user_voice_enabled(uid, True)

    alex_profile = build_user_voice_profile(
        conversations=conversations,
        messages=messages,
        person_id='person-alex',
        person_name='Alex',
        recipient='+15550101',
    )
    cache_user_voice_profile(uid, '+15550101', alex_profile)

    prompt_block = build_propose_message_voice_prompt_for_turn(uid, recipient='+15550101')
    assert '<user_voice_profile' in prompt_block
    assert 'no trailing period' in prompt_block

    requests = []

    class Callback:
        async def put_device_tool_request(self, req):
            requests.append(req)

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def setex(self, key, _ttl, value):
            self.store[key] = value

        def get(self, key):
            return self.store.get(key)

        def delete(self, key):
            return 1 if self.store.pop(key, None) is not None else 0

    fake_redis = FakeRedis()

    async def _inline(_executor, fn, *args):
        return fn(*args)

    with (
        patch.object(device_tools, 'redis_client', fake_redis),
        patch.object(device_tools, 'run_blocking', _inline),
    ):
        tool = build_device_tools(uid, {'propose_message'}, Callback(), timeout_seconds=5)[0]

        async def answer():
            while not requests:
                await asyncio.sleep(0.01)
            call_id = requests[0]['call_id']
            fake_redis.setex(
                device_tool_result_key(uid, call_id),
                60,
                json.dumps({'ok': True, 'status': 'sent'}),
            )

        task = asyncio.create_task(answer())
        await tool.ainvoke({'to': ['+15550101'], 'text': 'Hey! Running 5 mins late!'})
        await task

    assert len(requests) == 1
    sent_text = requests[0]['arguments']['text']
    assert sent_text == 'hey running 5 mins late'


@pytest.mark.asyncio
async def test_end_to_end_call_site_loads_stored_conversations_and_polishes_without_preseeded_cache(
    two_person_fixtures,
):
    """Exercises the production call sites (no hand-passed conversations or pre-seeded cache)."""
    conversations, stored_messages = two_person_fixtures
    uid = 'uid-e2e-prod'
    stored_people = [
        {'id': 'person-alex', 'name': 'Alex'},
        {'id': 'person-chen', 'name': 'Dr. Chen'},
    ]

    requests = []

    class Callback:
        async def put_device_tool_request(self, req):
            requests.append(req)

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def setex(self, key, _ttl, value):
            self.store[key] = value

        def get(self, key):
            return self.store.get(key)

        def delete(self, key):
            return 1 if self.store.pop(key, None) is not None else 0

    fake_redis = FakeRedis()

    async def _inline(_executor, fn, *args):
        return fn(*args)

    turn_messages = [
        {'sender': 'human', 'text': 'Can you text Alex that I am running 5 mins late?'},
    ]

    with (
        patch.object(
            user_voice,
            '_load_user_voice_settings',
            return_value={'user_voice_enabled': True},
        ),
        patch.object(
            user_voice,
            '_load_user_conversations_and_messages',
            return_value=(conversations, stored_messages, stored_people),
        ),
        patch.object(device_tools, 'redis_client', fake_redis),
        patch.object(device_tools, 'run_blocking', _inline),
    ):
        # 1. Agentic turn prompt builder resolves "Alex" from the user turn and stored conversations.
        prompt_block = build_propose_message_voice_prompt_for_turn(uid, messages=turn_messages)
        assert '<user_voice_profile recipient="Alex">' in prompt_block
        assert 'no trailing period' in prompt_block
        assert 'yo are you free around 7' in prompt_block

        # 2. Device tools: search_contacts resolves Alex -> +15550101, then propose_message polishes draft.
        tools = {
            t.name: t
            for t in build_device_tools(
                uid,
                {'search_contacts', 'propose_message'},
                Callback(),
                timeout_seconds=5,
            )
        }

        async def answer_search():
            while len(requests) < 1:
                await asyncio.sleep(0.01)
            call_id = requests[0]['call_id']
            fake_redis.setex(
                device_tool_result_key(uid, call_id),
                60,
                json.dumps(
                    {
                        'ok': True,
                        'contacts': [{'name': 'Alex', 'phones': ['+15550101']}],
                    }
                ),
            )

        t1 = asyncio.create_task(answer_search())
        await tools['search_contacts'].ainvoke({'query': 'Alex'})
        await t1

        async def answer_propose():
            while len(requests) < 2:
                await asyncio.sleep(0.01)
            call_id = requests[1]['call_id']
            fake_redis.setex(
                device_tool_result_key(uid, call_id),
                60,
                json.dumps({'ok': True, 'status': 'sent'}),
            )

        t2 = asyncio.create_task(answer_propose())
        await tools['propose_message'].ainvoke({'to': ['+15550101'], 'text': 'Hey! Running 5 mins late!'})
        await t2

    assert requests[1]['tool'] == 'propose_message'
    assert requests[1]['arguments']['text'] == 'hey running 5 mins late'


def test_blind_eval_fixtures():
    from evals.user_voice.eval_blind import evaluate_fixtures

    fixtures_path = Path(__file__).resolve().parents[2] / 'evals' / 'user_voice' / 'fixtures.json'
    summary = evaluate_fixtures(fixtures_path)
    assert summary['total_cases'] == 3
    assert summary['unstyled_detected_as_ai'] == 3
    assert summary['polished_indistinguishable_from_real'] == 3
