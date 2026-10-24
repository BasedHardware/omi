"""Per-person user voice for propose_message drafts (#23541).

The fixtures are one user who writes to two people very differently: a sister
(Mia) in lowercase English mixed with Chinese, no full stops, "!" and "haha"; and
a manager (Daniel Park) in capitalised English with full stops and no "!".
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from utils.llm import user_voice
from utils.llm.user_voice import (
    USER_VOICE_CACHE_TTL_SECONDS,
    UserVoiceProfile,
    annotate_contacts_with_voice,
    build_profile,
    get_user_voice_profile,
    handle_key,
    line_ending,
    match_person,
    polish_draft,
    profile_for_recipients,
    profile_prompt_block,
    typed_user_lines,
    user_lines_with_person,
)

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
MIA = {'id': 'p-mia', 'name': 'Mia'}
DANIEL = {'id': 'p-daniel', 'name': 'Daniel Park'}

MIA_USER_LINES = [
    'haha ok wait for me',
    'are you home yet',
    '我快到了 see you soon!',
    'lol that is so you',
    'yes!! 好的',
    'omg i forgot the cake',
    'hey can you grab milk',
    'i am on the train now',
    '明天一起吃饭吗',
    'love it haha',
]
DANIEL_USER_LINES = [
    'Hi Daniel, I pushed the fix to staging.',
    'The review is ready for you.',
    'I can take the Thursday slot.',
    'Thanks, I will update the doc tonight.',
    'The numbers look right to me.',
    'Hi Daniel, quick update on the launch.',
    'I moved the sync to 3 pm.',
    'Let me know if you want the longer version.',
    'Sounds good, I will send it after lunch.',
    'The test suite passes on my side.',
]


def _segments(user_lines, person_id, other_line='mm-hm'):
    segments = []
    for index, text in enumerate(user_lines):
        segments.append({'text': other_line, 'is_user': False, 'person_id': person_id, 'start': index * 2.0})
        segments.append({'text': text, 'is_user': True, 'person_id': None, 'start': index * 2.0 + 1})
    return segments


def _conversations():
    return [
        {'id': 'c-mia', 'started_at': '2026-10-20T10:00:00', 'transcript_segments': _segments(MIA_USER_LINES, 'p-mia')},
        {
            'id': 'c-daniel',
            'started_at': '2026-10-21T10:00:00',
            'transcript_segments': _segments(DANIEL_USER_LINES, 'p-daniel'),
        },
        {
            'id': 'c-locked',
            'is_locked': True,
            'started_at': '2026-10-22T10:00:00',
            'transcript_segments': _segments(['SECRET LOCKED LINE'], 'p-mia'),
        },
        {
            'id': 'c-discarded',
            'discarded': True,
            'started_at': '2026-10-22T11:00:00',
            'transcript_segments': _segments(['DISCARDED LINE'], 'p-mia'),
        },
    ]


def _profile(person, lines):
    return build_profile(person['id'], person['name'], lines, [], now=NOW)


@pytest.fixture
def mia():
    return _profile(MIA, user_lines_with_person(_conversations(), 'p-mia'))


@pytest.fixture
def daniel():
    return _profile(DANIEL, user_lines_with_person(_conversations(), 'p-daniel'))


# --- collecting only the user's own lines ------------------------------------


def test_only_the_users_own_lines_with_that_person_are_used():
    lines = user_lines_with_person(_conversations(), 'p-mia')

    assert lines == MIA_USER_LINES
    assert 'mm-hm' not in lines  # the other speaker's words never count as the user's voice


def test_locked_and_discarded_conversations_are_never_read():
    lines = user_lines_with_person(_conversations(), 'p-mia')

    assert 'SECRET LOCKED LINE' not in lines
    assert 'DISCARDED LINE' not in lines


def test_a_conversation_without_that_person_is_ignored():
    assert 'The review is ready for you.' not in user_lines_with_person(_conversations(), 'p-mia')


def test_typed_lines_are_the_users_text_messages_oldest_first():
    newest_first = [
        {'sender': 'human', 'type': 'text', 'text': 'second'},
        {'sender': 'ai', 'type': 'text', 'text': 'omi reply'},
        {'sender': 'human', 'type': 'day_summary', 'text': 'not typed'},
        {'sender': 'human', 'text': 'first'},
    ]

    assert typed_user_lines(newest_first) == ['first', 'second']


# --- measuring ---------------------------------------------------------------


@pytest.mark.parametrize(
    'text,expected',
    [
        ('ok.', '.'),
        ('好的。', '.'),
        ('yes!', '!'),
        ('really?', '?'),
        ('love it haha', 'laugh'),
        ('see you', 'none'),
        ('wait...', 'ellipsis'),
        ('see https://x.y/z', 'none'),
        ('', None),
    ],
)
def test_line_endings(text, expected):
    assert line_ending(text) == expected


def test_the_same_user_has_two_different_voices(mia, daniel):
    assert mia.endings.get('.', 0) == 0
    assert daniel.endings['.'] >= 80
    assert mia.exclamation_rate > 0 and daniel.exclamation_rate == 0
    assert 'han' in mia.scripts and 'han' not in daniel.scripts
    assert mia.lowercase_start_rate >= 60 and daniel.lowercase_start_rate == 0
    assert 'hi' in daniel.greetings and 'hey' in mia.greetings
    assert len(mia.examples) == user_voice.USER_VOICE_MAX_EXAMPLES
    assert mia.examples[0] == 'love it haha'  # newest first


def test_marks_come_from_typed_lines_when_there_are_enough():
    # STT adds full stops the user never typed; typed lines are the truth for marks.
    spoken = ['I will be there.'] * 10
    typed = ['ok see you'] * 12
    profile = build_profile('p', 'P', spoken, typed, now=NOW)

    assert profile.endings == {'none': 100}
    assert profile.median_chars == len('I will be there.')  # length still comes from that person


def test_few_lines_give_an_unreliable_profile_that_does_not_invent_a_style():
    profile = build_profile('p', 'Sam', ['hey', 'ok'], [], now=NOW)

    assert not profile.is_reliable
    assert 'Few of the user' in profile_prompt_block(profile)
    assert polish_draft('Great to see you!!!', profile).text == 'Great to see you!!!'


# --- the prompt block --------------------------------------------------------


def test_prompt_blocks_describe_each_person_differently(mia, daniel):
    mia_block = profile_prompt_block(mia)
    daniel_block = profile_prompt_block(daniel)

    assert 'Mia' in mia_block and 'Daniel Park' in daniel_block
    assert 'almost never a period' in mia_block
    assert 'use at most 0' in daniel_block
    assert 'han' in mia_block and 'han' not in daniel_block
    assert 'starts lines lowercase' in mia_block
    assert 'style only, never copy facts' in mia_block


def test_no_profile_means_no_block():
    assert profile_prompt_block(None) == ''


# --- the polish pass ---------------------------------------------------------


def test_the_same_draft_is_polished_differently_per_person(mia, daniel):
    draft = 'Sounds good! See you at 7!'

    assert polish_draft(draft, mia).text == 'Sounds good. See you at 7!'
    assert polish_draft(draft, daniel).text == 'Sounds good. See you at 7.'


def test_a_full_stop_the_user_never_types_to_that_person_is_dropped(mia, daniel):
    assert polish_draft('ok see you at 7.', mia).text == 'ok see you at 7'
    assert polish_draft('See you at 7.', daniel).text == 'See you at 7.'


def test_chinese_marks_stay_full_width(mia):
    result = polish_draft('好的！明天见！', mia)

    assert result.text == '好的，明天见！'
    assert result.changes == ['"!" 2 -> 1']


def test_polish_never_changes_words(mia, daniel):
    draft = 'Thanks so much! I really appreciate it! Talk soon.'
    for profile in (mia, daniel):
        polished = polish_draft(draft, profile).text
        strip = lambda s: [w.strip('.!,') for w in s.split()]  # noqa: E731
        assert strip(polished) == strip(draft)


def test_an_email_keeps_its_full_stops(mia):
    draft = 'Hi Mia,\nThe tickets are booked.'

    assert polish_draft(draft, mia).text == draft


def test_no_profile_leaves_the_draft_alone():
    assert polish_draft('Hello!!', None).text == 'Hello!!'


# --- matching a device contact to an Omi person -------------------------------


def test_contact_matching():
    people = [MIA, DANIEL, {'id': 'p-x', 'name': 'Alex'}, {'id': 'p-y', 'name': 'alex'}]

    assert match_person('Daniel Park', people) is DANIEL
    assert match_person('Mia Chen', people) is MIA
    assert match_person('Alex Smith', people) is None  # two Alexes: do not guess
    assert match_person('Nobody', people) is None
    assert match_person('Mia Chen', [{**MIA, 'is_dismissed': True}]) is None


def test_handles_compare_by_digits_and_casefolded_email():
    assert handle_key('+1 (555) 010-0199') == handle_key('5550100199')
    assert handle_key('Mia@Example.com') == 'mia@example.com'
    assert handle_key('12') is None


def test_a_group_message_is_not_polished_as_one_person(mia, daniel):
    voices = {handle_key('+15550100199'): mia, handle_key('+15550100200'): daniel}

    assert profile_for_recipients(voices, ['+1 555 010 0199']) is mia
    assert profile_for_recipients(voices, ['+15550100199', '+15550100200']) is None
    assert profile_for_recipients(voices, ['+15550100199', 'stranger@example.com']) is None
    assert profile_for_recipients(voices, ['+19999999999']) is None


# --- opt-in, cache and the contact seam (IO boundaries faked) ------------------


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0


@pytest.fixture
def fake_redis():
    fake = FakeRedis()
    with patch.object(user_voice, 'redis_client', fake):
        yield fake


@pytest.fixture
def fake_sources():
    calls = {'conversations': 0}

    def get_conversations(uid, limit):
        calls['conversations'] += 1
        return _conversations()

    with (
        patch.object(user_voice.conversations_db, 'get_conversations', get_conversations),
        patch.object(user_voice.chat_db, 'get_messages', lambda uid, limit: []),
    ):
        yield calls


def test_profile_is_cached_encrypted_for_seven_days(fake_redis, fake_sources):
    first = get_user_voice_profile('uid-1', MIA)
    second = get_user_voice_profile('uid-1', MIA)

    assert first == second
    assert fake_sources['conversations'] == 1
    key = 'user_voice:uid-1:p-mia'
    assert fake_redis.ttls[key] == USER_VOICE_CACHE_TTL_SECONDS
    assert 'wait for me' not in fake_redis.store[key]  # the user's lines are not stored in clear


def test_a_cache_from_another_user_cannot_be_read(fake_redis, fake_sources):
    get_user_voice_profile('uid-1', MIA)
    fake_redis.store['user_voice:uid-2:p-mia'] = fake_redis.store['user_voice:uid-1:p-mia']

    assert user_voice._read_cached('uid-2', 'p-mia') is None


def _contacts_result():
    return {
        'ok': True,
        'contacts': [
            {
                'name': 'Mia Chen',
                'preferred_messaging_handle': '+15550100199',
                'phone_numbers': [{'value': '+1 555 010 0199'}],
                'email_addresses': [],
            },
            {'name': 'Unknown Person', 'preferred_messaging_handle': '+15550100300'},
        ],
    }


def test_disabled_by_default_reads_nothing(fake_redis, fake_sources):
    result = _contacts_result()
    with patch.object(user_voice.users_db, 'get_assistant_settings', lambda uid: {}):
        assert annotate_contacts_with_voice('uid-1', result) == {}

    assert fake_sources['conversations'] == 0
    assert all('user_voice' not in c for c in result['contacts'])


def test_opted_in_contacts_that_are_known_people_carry_the_voice(fake_redis, fake_sources):
    result = _contacts_result()
    with (
        patch.object(user_voice.users_db, 'get_assistant_settings', lambda uid: {'drafts': {'user_voice': True}}),
        patch.object(user_voice.users_db, 'get_people', lambda uid: [MIA, DANIEL]),
    ):
        voices = annotate_contacts_with_voice('uid-1', result)

    assert 'Mia' in result['contacts'][0]['user_voice']
    assert 'user_voice' not in result['contacts'][1]
    assert isinstance(voices[handle_key('+15550100199')], UserVoiceProfile)
    json.dumps(result)  # still serialisable for the model


def test_a_run_of_exclamations_collapses_to_one_mark(mia, daniel):
    assert polish_draft('see you at 7!!!', mia).text == 'see you at 7!'
    assert polish_draft('See you at 7!!!', daniel).text == 'See you at 7.'


# --- v2: written lines, questions, scripts by line, greetings (real-message eval 10/24) ---


def test_questions_do_not_count_as_a_line_ending_style():
    # Someone who mostly asks Omi things still ends statements without a mark.
    typed = ['what time is it?', 'can you check the weather?', 'where is my phone?'] * 5 + ['ok on my way'] * 3
    profile = build_profile('p-mia', 'Mia', [], typed, now=NOW)
    assert '?' not in profile.endings
    assert profile.endings == {'none': 100}


def test_written_lines_win_over_typed_lines_for_marks_and_voice():
    typed = ['Please summarise my day.'] * 20
    written = ['omg yes!', 'okk im here!', 'cominggg', 'love you too', 'we ball', 'haha same', 'ok wait', 'see u soon!']
    profile = build_profile('p-mia', 'Mia', [], typed, written_lines=written, now=NOW)
    assert profile.written_lines == 8 and profile.lines == 8
    assert profile.endings.get('.', 0) == 0
    assert profile.exclamation_rate == 38
    assert profile.stretch_rate >= 25
    assert profile.examples[0] == 'see u soon!'
    block = profile_prompt_block(profile)
    assert 'stretches a word' in block and 'almost never a period' in block


def test_scripts_are_shares_of_lines_not_letters():
    # Short Chinese lines would vanish next to long English ones if letters were counted.
    lines = ['好的好的', '门锁了吗', '吃了吗', '我到了', '明天见', 'I replied to the ones in the email already', 'sounds good see you then', 'ok']
    profile = build_profile('p-mia', 'Mia', lines, [], now=NOW)
    assert profile.scripts == {'han': 62, 'latin': 38}
    assert 'write in han script' in profile_prompt_block(profile)


def test_a_rare_greeting_is_not_offered_as_an_opener():
    lines = ['yo whats up'] + ['ok see you there', 'sounds good', 'on my way', 'love that', 'haha true', 'wait what', 'cool cool'] * 2
    profile = build_profile('p-mia', 'Mia', lines, [], now=NOW)
    assert profile.greetings == ['yo'] and profile.greeting_rate < 15
    block = profile_prompt_block(profile)
    assert 'yo' not in block.split('recent lines')[0]
    assert 'almost never opens with a greeting' in block


def test_written_lines_reach_the_cached_profile(fake_redis):
    with (
        patch.object(user_voice, 'user_written_lines', lambda uid, person: ['okk im here!'] * 10),
        patch.object(user_voice.conversations_db, 'get_conversations', lambda uid, limit: []),
        patch.object(user_voice.chat_db, 'get_messages', lambda uid, limit: []),
    ):
        profile = get_user_voice_profile('uid-1', MIA)
    assert profile.written_lines == 10 and profile.version == user_voice.USER_VOICE_PROFILE_VERSION


# Real exchanges, stock replies and the open thread (profile v3). Measured on a
# held-out set of real replies: these lifted a blind voice score from 3.1 to 3.7 / 5.

MIA_EXCHANGES = [
    ('are you coming tonight', 'yesss omw'),
    ('did you eat', 'not yet haha'),
    ('the movie starts at 8', 'okk see you there'),
    ('mom says hi', 'hiii 想她了'),
    ('can you bring the charger', 'okk'),
    ('where are you', 'almost there'),
    ('the train is late again', 'nooo'),
    ('i got the job!!', 'omg so proud of you'),
    ('dinner at 7?', 'okk'),
    ('we are at the corner table', 'coming'),
]


def _mia_with_exchanges():
    return build_profile('p-mia', 'Mia', MIA_USER_LINES, [], written_lines=MIA_USER_LINES, exchanges=MIA_EXCHANGES, now=NOW)


def test_exchanges_and_stock_replies_are_learned():
    profile = _mia_with_exchanges()
    assert len(profile.exchanges) == len(MIA_EXCHANGES)
    assert profile.reply_median_chars <= 12
    assert 'okk' in profile.stock_replies  # sent twice -> a stock reply; once is not enough
    assert 'nooo' not in profile.stock_replies


def test_shots_are_the_closest_exchanges_plus_the_newest():
    profile = _mia_with_exchanges()
    shots = user_voice.pick_shots(profile, 'the train is so late', k=4)
    replies = [e.me for e in shots]
    assert 'nooo' in replies  # closest to what Mia just said
    assert replies[-1] == 'coming'  # the newest is always shown, oldest first
    assert len(shots) == 4


def test_the_block_shows_real_replies_and_the_open_thread():
    profile = _mia_with_exchanges()
    thread = [{'is_user': True, 'text': 'leaving now'}, {'is_user': False, 'text': 'the train is late again'}]
    block = profile_prompt_block(profile, 'the train is late again', thread)
    assert 'Mia: the train is late again  ->  user: nooo' in block
    assert '    user: leaving now' in block
    assert 'MEANING, not the words' in block
    assert '"okk"' in block


def test_no_exchanges_keeps_the_v2_block():
    profile = build_profile('p-mia', 'Mia', MIA_USER_LINES, [], now=NOW)
    block = profile_prompt_block(profile)
    assert 'actually answered' not in block and 'open thread' not in block


def test_attachment_placeholders_are_not_the_users_words():
    profile = build_profile(
        'p-mia', 'Mia', [], [], written_lines=MIA_USER_LINES, exchanges=[('pic?', '[image, not downloaded] ￼'), ('hey', 'hi')], now=NOW
    )
    assert [e.me for e in profile.exchanges] == ['hi']


def test_the_thread_and_exchanges_reach_the_contact(fake_redis, fake_sources):
    result = _contacts_result()
    with (
        patch.object(user_voice.users_db, 'get_assistant_settings', lambda uid: {'drafts': {'user_voice': True}}),
        patch.object(user_voice.users_db, 'get_people', lambda uid: [MIA, DANIEL]),
        patch.object(user_voice, 'user_written_lines', lambda uid, person: MIA_USER_LINES),
        patch.object(user_voice, 'user_written_exchanges', lambda uid, person: MIA_EXCHANGES),
        patch.object(user_voice, 'user_written_thread', lambda uid, person: [{'is_user': False, 'text': 'dinner at 7?'}]),
    ):
        annotate_contacts_with_voice('uid-1', result)
    block = result['contacts'][0]['user_voice']
    assert 'Mia: dinner at 7?  ->  user: okk' in block
    assert '    Mia: dinner at 7?' in block
