"""Unit tests for per-person user voice profiling and deterministic draft polishing (#23541)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from evals.user_voice.eval_user_voice import run_blind_user_voice_eval
from testing.import_isolation import load_module_fresh, stub_modules
from utils.llm.user_voice import (
    MAX_VERBATIM_EXAMPLES,
    MIN_VERBATIM_EXAMPLES,
    USER_VOICE_CACHE_TTL_SECONDS,
    build_user_voice_profile,
    clear_user_voice_cache,
    extract_user_lines_for_person,
    format_user_voice_prompt,
    get_cached_user_voice_profile,
    get_or_build_user_voice_profile,
    is_user_voice_opted_in,
    polish_draft_in_user_voice,
    remember_contact_resolution,
    set_user_voice_opt_in,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def reset_voice_cache():
    clear_user_voice_cache()
    yield
    clear_user_voice_cache()


@pytest.fixture
def two_person_conversations():
    """Fixtures for two people ('Alex' and 'Dr. Patel') the same user writes to differently."""
    return [
        # Casual friend Alex: lowercase fragments, no periods, no exclamation marks
        {
            'id': 'conv-alex-1',
            'is_locked': False,
            'participants': ['Alex'],
            'structured': {'title': 'Catching up with Alex', 'overview': 'Coffee plans'},
            'transcript_segments': [
                {'is_user': True, 'text': 'yo running 5 mins late'},
                {'is_user': False, 'text': 'No worries at all!', 'speaker_name': 'Alex'},
                {'is_user': True, 'text': 'grabbing coffee on the way'},
                {'is_user': True, 'text': 'you still at the spot'},
                {'is_user': True, 'text': 'sounds good see u in a bit'},
            ],
        },
        # Formal colleague Dr. Patel: capitalized sentences, trailing periods, polite greetings
        {
            'id': 'conv-patel-1',
            'is_locked': False,
            'participants': ['Dr. Patel'],
            'structured': {'title': 'Quarterly review with Dr. Patel', 'overview': 'Board slides'},
            'transcript_segments': [
                {'is_user': True, 'text': 'Hello Dr. Patel, I have uploaded the revised quarterly figures.'},
                {'is_user': False, 'text': 'Thanks, I will review them shortly.', 'speaker_name': 'Dr. Patel'},
                {'is_user': True, 'text': 'Please let me know if the Thursday afternoon slot works for you.'},
                {'is_user': True, 'text': 'Thank you for reviewing the draft ahead of the board meeting.'},
                {'is_user': True, 'text': 'I will send the updated slides before 5 PM today.'},
            ],
        },
        # Locked conversation with Alex containing private text that must NEVER leak into the profile
        {
            'id': 'conv-alex-locked',
            'is_locked': True,
            'participants': ['Alex'],
            'structured': {'title': 'Locked Private Chat with Alex', 'overview': 'Confidential'},
            'transcript_segments': [
                {'is_user': True, 'text': 'SECRET_PASSPHRASE_LOCKED_LINE_DO_NOT_INCLUDE!!!'},
                {'is_user': True, 'text': 'ANOTHER_LOCKED_PRIVATE_EXAMPLE!!!'},
            ],
        },
    ]


def test_two_people_same_user_writes_to_differently_produce_distinct_voices(two_person_conversations):
    uid = 'user-23541'
    set_user_voice_opt_in(uid, True)

    alex_profile = get_or_build_user_voice_profile(
        uid,
        'Alex',
        conversations=two_person_conversations,
    )
    patel_profile = get_or_build_user_voice_profile(
        uid,
        'Dr. Patel',
        conversations=two_person_conversations,
    )

    assert alex_profile is not None
    assert patel_profile is not None

    # Alex profile: short lowercase fragments, dominant ending 'nothing', 0% exclamations
    assert alex_profile.dominant_ending == 'nothing'
    assert alex_profile.line_endings['nothing'] >= 0.75
    assert alex_profile.all_lowercase_rate == 1.0
    assert alex_profile.exclamation_rate == 0.0
    assert alex_profile.length_bucket == 'short_fragment'
    assert alex_profile.greetings[0].lower() == 'yo'
    assert MIN_VERBATIM_EXAMPLES <= len(alex_profile.examples) <= MAX_VERBATIM_EXAMPLES

    # Dr. Patel profile: longer capitalized sentences, dominant ending 'period', 0% exclamations
    assert patel_profile.dominant_ending == 'period'
    assert patel_profile.line_endings['period'] == 1.0
    assert patel_profile.lowercase_rate == 0.0
    assert patel_profile.exclamation_rate == 0.0
    assert patel_profile.typical_length_words > alex_profile.typical_length_words
    assert MIN_VERBATIM_EXAMPLES <= len(patel_profile.examples) <= MAX_VERBATIM_EXAMPLES

    # Given the exact same generic assistant draft, the polished outputs for Alex vs Dr. Patel
    # come out in their two distinct voices:
    generic_draft = 'Running 10 minutes late! I will be there soon.'
    alex_draft = polish_draft_in_user_voice(generic_draft, alex_profile)
    patel_draft = polish_draft_in_user_voice(generic_draft, patel_profile)

    assert alex_draft != patel_draft
    # Alex's draft is all lowercase, has no '!', and has no trailing period
    assert alex_draft == alex_draft.lower()
    assert '!' not in alex_draft
    assert not alex_draft.endswith('.')
    # Dr. Patel's draft is capitalized, has no '!', and ends with a period
    assert patel_draft[0].isupper()
    assert '!' not in patel_draft
    assert patel_draft.endswith('.')


def test_locked_conversations_are_strictly_excluded(two_person_conversations):
    uid = 'user-locked-check'
    lines = extract_user_lines_for_person(two_person_conversations, person_name='Alex')
    joined = ' '.join(lines)
    assert 'SECRET_PASSPHRASE_LOCKED_LINE_DO_NOT_INCLUDE' not in joined
    assert 'ANOTHER_LOCKED_PRIVATE_EXAMPLE' not in joined
    assert len(lines) == 4

    profile = build_user_voice_profile(uid, 'Alex', lines)
    prompt = format_user_voice_prompt(profile)
    assert 'SECRET_PASSPHRASE_LOCKED_LINE_DO_NOT_INCLUDE' not in prompt


def test_voice_profile_is_cached_for_seven_days(two_person_conversations):
    uid = 'user-cache-ttl'
    set_user_voice_opt_in(uid, True)
    t0 = 1_700_000_000.0

    assert USER_VOICE_CACHE_TTL_SECONDS == 7 * 24 * 3600

    profile = get_or_build_user_voice_profile(
        uid,
        'Alex',
        conversations=two_person_conversations,
        now=t0,
    )
    assert profile is not None
    assert profile.expires_at == t0 + 7 * 24 * 3600

    # Within 7 days (e.g. day 6): served from cache even if conversations list is empty
    day_6 = t0 + 6 * 24 * 3600
    cached = get_or_build_user_voice_profile(
        uid,
        'Alex',
        conversations=[],
        now=day_6,
    )
    assert cached is not None
    assert cached.sample_count == 4

    # After 7 days (day 7 + 1s): cache entry expires
    after_7_days = t0 + 7 * 24 * 3600 + 1
    assert get_cached_user_voice_profile(uid, 'Alex', now=after_7_days) is None


def test_opt_in_gating_defaults_to_disabled_and_respects_account_and_per_person_settings(two_person_conversations):
    uid = 'user-opt-in'
    assert is_user_voice_opted_in(uid, 'Alex') is False
    assert (
        get_or_build_user_voice_profile(
            uid,
            'Alex',
            conversations=two_person_conversations,
        )
        is None
    )

    # Per-person opt-in enables Alex while leaving others disabled
    set_user_voice_opt_in(uid, True, person_key='Alex')
    assert is_user_voice_opted_in(uid, 'Alex') is True
    assert is_user_voice_opted_in(uid, 'Dr. Patel') is False


def test_language_and_script_mix_detection_for_multilingual_contacts():
    spanish_lines = [
        'hola mateo ya voy en camino',
        'nos vemos en la casa de mamá',
        'todo bien gracias por avisar',
        'vamos mañana temprano',
    ]
    es_profile = build_user_voice_profile('uid-lang', 'Mateo', spanish_lines)
    assert es_profile.primary_language == 'es'
    assert es_profile.script_mix.get('latin', 0) == 1.0

    cjk_lines = [
        '今天下午三点见',
        '我已经到咖啡店了',
        '好的没问题',
    ]
    zh_profile = build_user_voice_profile('uid-lang', 'Lin', cjk_lines)
    assert zh_profile.primary_language == 'zh'
    assert zh_profile.script_mix.get('cjk', 0) > 0.8


@pytest.mark.asyncio
async def test_propose_message_device_tool_applies_per_person_voice_when_opted_in(two_person_conversations):
    fake_redis_mod = ModuleType('database.redis_db')
    store: dict[str, str] = {}

    class _FakeRedis:
        def setex(self, k, _ttl, v):
            store[k] = v

        def get(self, k):
            return store.get(k)

        def delete(self, k):
            return 1 if store.pop(k, None) is not None else 0

    fake_redis_mod.r = _FakeRedis()

    fake_executors_mod = ModuleType('utils.executors')
    fake_executors_mod.db_executor = None

    async def _run_blocking(_exec, fn, *args):
        return fn(*args)

    fake_executors_mod.run_blocking = _run_blocking

    fake_fallback_mod = ModuleType('utils.observability.fallback')
    fake_fallback_mod.record_fallback = lambda **_kw: None

    fake_conv_db_mod = ModuleType('database.conversations')
    fake_conv_db_mod.get_conversations = MagicMock(return_value=two_person_conversations)

    fake_chat_db_mod = ModuleType('database.chat')
    fake_chat_db_mod.get_messages = MagicMock(return_value=[])

    with stub_modules(
        {
            'database.redis_db': fake_redis_mod,
            'utils.executors': fake_executors_mod,
            'utils.observability.fallback': fake_fallback_mod,
            'database.conversations': fake_conv_db_mod,
            'database.chat': fake_chat_db_mod,
        }
    ):
        dt = load_module_fresh(
            'utils.device_tools',
            os.path.join(str(BACKEND_DIR), 'utils', 'device_tools.py'),
        )

        requests: list[dict] = []

        class _Callback:
            async def put_device_tool_request(self, req):
                requests.append(req)
                store[dt.device_tool_result_key('uid-voice', req['call_id'])] = json.dumps(
                    {'ok': True, 'status': 'sent'}
                )

        set_user_voice_opt_in('uid-voice', True)
        remember_contact_resolution(
            'uid-voice',
            [
                {'name': 'Alex', 'phones': ['+15550101']},
                {'name': 'Dr. Patel', 'phones': ['+15550202']},
            ],
        )

        tools = dt.build_device_tools('uid-voice', {'propose_message'}, _Callback(), timeout_seconds=5)
        propose_tool = tools[0]

        # Same draft text sent to Alex (+15550101) vs Dr. Patel (+15550202)
        await propose_tool.ainvoke(
            {'to': ['+15550101'], 'text': 'Hi Alex, I am running 5 minutes late! Be there soon.'}
        )
        await propose_tool.ainvoke({'to': ['+15550202'], 'text': 'i am running 5 minutes late for our meeting!'})

        assert len(requests) == 2
        alex_text = requests[0]['arguments']['text']
        patel_text = requests[1]['arguments']['text']

        assert alex_text != patel_text
        # Alex receives lowercase fragment without trailing period or '!'
        assert alex_text == alex_text.lower()
        assert '!' not in alex_text
        assert not alex_text.endswith('.')
        # Dr. Patel receives capitalized sentence ending with a period and no '!'
        assert patel_text[0].isupper()
        assert '!' not in patel_text
        assert patel_text.endswith('.')


def test_blind_eval_real_lines_vs_drafts_prefers_user_voice():
    report = run_blind_user_voice_eval()
    assert report['total_cases'] >= 3
    assert report['win_rate'] == 1.0
    for case in report['cases']:
        assert case['voiced_distance_to_real'] < case['generic_distance_to_real']
        assert case['blind_preference'] == 'user_voice'
