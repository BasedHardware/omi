"""Conversation titles name the identified people in the conversation (#3602).

Notes v2 already knows who spoke: hard-evidence speaker bindings (voice profile /
tagged person) reach the prompt as ``spk`` map lines. The general (non-meeting)
notes path never told the model to use those names in the title, nor which bound
name is the account owner. These tests pin the contract:

- the speaker map remembers which clusters are the account owner and how much each
  cluster said, without changing the shared prefix bytes;
- the prefix exposes the non-owner people worth naming (most-spoken first, minor
  speakers excluded) and the owner names;
- title rules are static (cacheable) while the names stay in the volatile suffix;
- a title that omits every identified person is deterministically led by their
  name(s); titles that already name them, and rich meeting notes, are untouched.
"""

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

# firebase_admin reaches google.auth.credentials lazily. Same guard as test_conversation_notes_v2.
import google.auth.credentials  # noqa: F401

from models.other import Person
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import stub_modules

STARTED_AT = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules({}):
        import utils.conversations.transcript_for_llm  # noqa: F401
        import utils.llm.conversation_processing  # noqa: F401
        import utils.llm.conversation_prompt_prefix  # noqa: F401
        import utils.llm.meeting_notes_validation  # noqa: F401

        yield


def _seg(segment_id, text, *, speaker='SPEAKER_00', is_user=True, person_id=None, scope=None):
    return TranscriptSegment(
        id=segment_id,
        text=text,
        speaker=speaker,
        is_user=is_user,
        person_id=person_id,
        speaker_id_scope=scope,
        start=0.0,
        end=2.0,
    )


def _person(person_id, name):
    return Person(id=person_id, name=name, created_at=STARTED_AT, updated_at=STARTED_AT)


# Sarah's two turns in the three-party conversation: 25 and 13 words.
SARAH_LONG = (
    'we are about ten percent over on vendors so I want to cut the events line '
    'and move the offsite to march instead of february'
)
SARAH_SHORT = 'march works and I will send the revised numbers to finance on friday'


def _three_party_conversation():
    # Cluster 0 is the owner (David), cluster 1 is a tagged person (Sarah Chen) who
    # carries the conversation, cluster 2 is a tagged person (Lee) who only says hi.
    return SimpleNamespace(
        transcript_segments=[
            _seg('s1', 'hey so where are we on the budget for next quarter'),
            _seg(
                's2',
                'we are about ten percent over on vendors so I want to cut the events line '
                'and move the offsite to march instead of february',
                speaker='SPEAKER_01',
                is_user=False,
                person_id='p-sarah',
            ),
            _seg('s3', 'hi', speaker='SPEAKER_02', is_user=False, person_id='p-lee'),
            _seg(
                's4',
                'march works and I will send the revised numbers to finance on friday',
                speaker='SPEAKER_01',
                is_user=False,
                person_id='p-sarah',
            ),
            _seg('s5', 'sounds good, thanks'),
        ]
    )


def _people():
    return [_person('p-sarah', 'Sarah Chen'), _person('p-lee', 'Lee')]


def _prefix_for(conversation, monkeypatch, *, owner_name='David', people=None, calendar_context=None):
    from utils.conversations import transcript_for_llm
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: owner_name)
    transcript, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map(
        'uid-1', conversation, _people() if people is None else people
    )
    return build_conversation_prompt_prefix(
        conversation_id='conv-names',
        transcript=transcript,
        started_at=STARTED_AT,
        timezone_name='UTC',
        language_code='en',
        calendar_context=calendar_context,
        speaker_map=speaker_map,
        transcript_segment_ids=[segment.id for segment in conversation.transcript_segments],
    )


def _notes(prefix, monkeypatch, *, title, rich=False, roster=None):
    from utils.llm import conversation_processing

    captured: dict = {}

    class Model:
        def invoke(self, messages):
            captured['messages'] = messages
            return SimpleNamespace(
                content=json.dumps(
                    {
                        'title': title,
                        'overview': 'compatibility',
                        'emoji': '💬',
                        'category': 'work',
                        'sections': [],
                        'action_items': [],
                        'events': [],
                    }
                )
            )

    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *_a, **_k: Model())
    monkeypatch.setattr(conversation_processing, 'shared_conversation_cache_supported', lambda: False)
    structured = conversation_processing.get_conversation_notes(
        prefix,
        started_at=STARTED_AT,
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=True,
        rich_context_enabled=rich,
        roster=roster,
    )
    return structured, captured['messages']


def _text(message) -> str:
    content = message.content
    if isinstance(content, list):
        return '\n'.join(part.get('text', '') for part in content if isinstance(part, dict))
    return str(content)


def test_speaker_map_keeps_scoped_hard_identity_evidence(monkeypatch):
    from utils.conversations import transcript_for_llm

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: 'David')
    _, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map(
        'uid-1', _three_party_conversation(), _people()
    )

    # Still the plain cluster -> name mapping every existing caller reads.
    assert speaker_map == {0: 'David', 1: 'Sarah Chen', 2: 'Lee'}
    assert speaker_map.owner_name == 'David'
    assert [
        (cluster.speaker_id, cluster.scope, cluster.owner, cluster.names, cluster.words)
        for cluster in speaker_map.clusters
    ] == [(0, None, True, (), 14), (1, None, False, ('Sarah Chen',), 38), (2, None, False, ('Lee',), 1)]


def test_prefix_title_people_exclude_owner_and_minor_speakers(monkeypatch):
    prefix = _prefix_for(_three_party_conversation(), monkeypatch)

    assert prefix.title_people == ('Sarah Chen',)
    assert prefix.owner_names == ('David',)


def test_title_people_do_not_change_shared_prefix_bytes(monkeypatch):
    from utils.conversations import transcript_for_llm
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    conversation = _three_party_conversation()
    prefix = _prefix_for(conversation, monkeypatch)
    transcript, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map(
        'uid-1', conversation, _people()
    )
    plain = build_conversation_prompt_prefix(
        conversation_id='conv-names',
        transcript=transcript,
        started_at=STARTED_AT,
        timezone_name='UTC',
        language_code='en',
        speaker_map=dict(speaker_map),
        transcript_segment_ids=[segment.id for segment in conversation.transcript_segments],
    )

    assert prefix.context == plain.context
    # A bare mapping cannot say which name is the account owner, so it names nobody.
    assert plain.title_people == ()
    assert plain.owner_names == ()


def test_unresolved_and_owner_only_conversations_have_no_title_people(monkeypatch):
    monologue = SimpleNamespace(
        transcript_segments=[
            _seg('s1', 'note to self buy more coffee filters'),
            _seg('s2', 'someone said thanks', speaker='SPEAKER_01', is_user=False),
        ]
    )

    prefix = _prefix_for(monologue, monkeypatch)

    assert prefix.title_people == ()
    assert prefix.owner_names == ('David',)


# Merged and multi-source transcripts keep each source's speaker ids, scoped by
# ``speaker_id_scope``, while the rendered ``spk`` lines key on the id alone.


def test_reused_speaker_id_bound_to_different_people_names_nobody(monkeypatch):
    # Id 1 is Lee (who only said hi) in source A and Sarah (who carried the talk) in
    # source B. ``spk 1 Lee`` would credit Sarah's words to Lee, so name nobody.
    merged = SimpleNamespace(
        transcript_segments=[
            _seg('a1', 'hey so where are we on the budget for next quarter', scope='conv-a'),
            _seg('a2', 'hi', speaker='SPEAKER_01', is_user=False, person_id='p-lee', scope='conv-a'),
            _seg('b1', 'sounds good, thanks', scope='conv-b'),
            _seg('b2', SARAH_LONG, speaker='SPEAKER_01', is_user=False, person_id='p-sarah', scope='conv-b'),
        ]
    )

    prefix = _prefix_for(merged, monkeypatch)

    assert 'spk 1 Lee' in prefix.context  # rendered map bytes are unchanged
    assert prefix.title_people == ()
    assert prefix.owner_names == ('David',)


def test_reused_speaker_id_that_is_the_owner_in_another_source_names_nobody(monkeypatch):
    # Source B tagged the owner's voice with their own person record ("David Miller");
    # source A marks the same id as the account owner. The owner is never a title person.
    people = _people() + [_person('p-david-miller', 'David Miller')]
    merged = SimpleNamespace(
        transcript_segments=[
            _seg('b1', SARAH_LONG, is_user=False, person_id='p-david-miller', scope='conv-b'),
            _seg('a1', 'sounds good, thanks', scope='conv-a'),
            _seg('a2', SARAH_SHORT, speaker='SPEAKER_01', is_user=False, person_id='p-sarah', scope='conv-a'),
        ]
    )

    prefix = _prefix_for(merged, monkeypatch, people=people)

    assert prefix.title_people == ()
    assert prefix.owner_names == ('David',)


def test_title_share_counts_only_the_scope_where_the_person_is_bound(monkeypatch):
    # Id 1 is Sarah for three words in source A and an unidentified voice in source B.
    merged = SimpleNamespace(
        transcript_segments=[
            _seg('a1', 'hey so where are we on the budget for next quarter', scope='conv-a'),
            _seg('a2', 'yes that works', speaker='SPEAKER_01', is_user=False, person_id='p-sarah', scope='conv-a'),
            _seg('b1', f'{SARAH_LONG} {SARAH_SHORT}', speaker='SPEAKER_01', is_user=False, scope='conv-b'),
        ]
    )

    prefix = _prefix_for(merged, monkeypatch)

    assert prefix.title_people == ()


def test_reused_speaker_id_bound_to_the_same_person_is_still_named(monkeypatch):
    merged = SimpleNamespace(
        transcript_segments=[
            _seg('a1', 'hey so where are we on the budget for next quarter', scope='conv-a'),
            _seg('a2', SARAH_LONG, speaker='SPEAKER_01', is_user=False, person_id='p-sarah', scope='conv-a'),
            _seg('b1', SARAH_SHORT, speaker='SPEAKER_01', is_user=False, person_id='p-sarah', scope='conv-b'),
        ]
    )

    prefix = _prefix_for(merged, monkeypatch)

    assert prefix.title_people == ('Sarah Chen',)


def _calendar(*names):
    from models.calendar_context import CalendarMeetingContext, MeetingParticipant

    return CalendarMeetingContext(
        calendar_event_id='event-1',
        title='Sync',
        start_time=STARTED_AT,
        duration_minutes=30,
        participants=[MeetingParticipant(name=name) for name in names],
    )


def test_calendar_guessed_owner_cluster_is_never_a_title_person(monkeypatch):
    # The owner's voice was not recognized and Bob is tagged. The legacy one-name
    # calendar guard binds the owner's cluster to "David Miller" by elimination; that
    # guess may reach the spk map, never the title.
    conversation = SimpleNamespace(
        transcript_segments=[
            _seg('s1', 'owner talking a lot about the plan for the week ' * 3, is_user=False),
            _seg(
                's2',
                'bob replies with details on the budget ' * 2,
                speaker='SPEAKER_01',
                is_user=False,
                person_id='p-bob',
            ),
        ]
    )

    prefix = _prefix_for(
        conversation, monkeypatch, people=[_person('p-bob', 'Bob')], calendar_context=_calendar('David Miller', 'Bob')
    )
    structured, _ = _notes(prefix, monkeypatch, title='Weekly plan')

    assert 'spk 0 David Miller' in prefix.context
    assert prefix.title_people == ('Bob',)
    assert prefix.owner_names == ()
    assert structured.title == 'Bob: Weekly plan'


def test_calendar_guessed_owner_split_cluster_is_never_a_title_person(monkeypatch):
    # The owner is recognized as "David", but one unresolved diarization split of their
    # voice is bound to the calendar's "David Miller" by elimination.
    conversation = SimpleNamespace(
        transcript_segments=[
            _seg('s1', 'owner talking about plan ' * 3),
            _seg(
                's2',
                'bob replies with details on the budget ' * 2,
                speaker='SPEAKER_01',
                is_user=False,
                person_id='p-bob',
            ),
            _seg('s3', 'owner again split cluster talking talking ' * 2, speaker='SPEAKER_02', is_user=False),
        ]
    )

    prefix = _prefix_for(
        conversation, monkeypatch, people=[_person('p-bob', 'Bob')], calendar_context=_calendar('David Miller', 'Bob')
    )

    assert 'spk 2 David Miller' in prefix.context
    assert prefix.title_people == ('Bob',)
    assert prefix.owner_names == ('David',)


def test_title_rules_are_static_while_names_stay_volatile(monkeypatch):
    prefix = _prefix_for(_three_party_conversation(), monkeypatch)

    _, messages = _notes(prefix, monkeypatch, title='Sarah Chen Moves the Offsite to March')
    static, volatile = _text(messages[0]), _text(messages[1])

    assert 'TITLE' in static
    assert 'account owner' in static
    assert 'Sarah Chen' not in static
    assert 'PEOPLE IN THIS CONVERSATION' in volatile
    assert '- Sarah Chen' in volatile
    assert '- Account owner (never name them in the title): David' in volatile


def test_title_that_omits_identified_person_is_led_by_their_name(monkeypatch):
    prefix = _prefix_for(_three_party_conversation(), monkeypatch)

    structured, _ = _notes(prefix, monkeypatch, title='Q2 Budget Cuts and Offsite Move')

    assert structured.title == 'Sarah Chen: Q2 Budget Cuts and Offsite Move'


@pytest.mark.parametrize(
    'title',
    [
        'Sarah Chen Moves the Offsite to March',
        'Sarah Trims Vendor Spend for Q2',
        'Budget Review with sarah',
    ],
)
def test_title_that_already_names_the_person_is_kept(monkeypatch, title):
    prefix = _prefix_for(_three_party_conversation(), monkeypatch)

    structured, _ = _notes(prefix, monkeypatch, title=title)

    assert structured.title == title


def test_lead_is_language_neutral_and_joins_at_most_two_people():
    from utils.llm.meeting_notes_validation import lead_title_with_people

    assert lead_title_with_people('Revisión del presupuesto', ('Sarah Chen',)) == (
        'Sarah Chen: Revisión del presupuesto',
        True,
    )
    assert lead_title_with_people('Launch Plan', ('Sarah Chen', 'John Park', 'Ana')) == (
        'Sarah Chen & John Park: Launch Plan',
        True,
    )


def test_lead_drops_second_person_rather_than_exceeding_title_length():
    from utils.llm.meeting_notes_validation import TWO_NAME_LEAD_MAX_CHARACTERS, lead_title_with_people

    title = 'Quarterly Vendor Spend Review and Offsite Rescheduling'
    led, changed = lead_title_with_people(title, ('Sarah Chen', 'Johnathan Park'))

    assert changed
    assert led == f'Sarah Chen: {title}'
    assert len(f'Sarah Chen & Johnathan Park: {title}') > TWO_NAME_LEAD_MAX_CHARACTERS


def test_one_name_lead_is_never_truncated():
    from utils.llm.meeting_notes_validation import TWO_NAME_LEAD_MAX_CHARACTERS, lead_title_with_people

    title = 'Quarterly Vendor Spend Review, Offsite Rescheduling and the Events Budget'
    led, changed = lead_title_with_people(title, ('Sarah Chen',))

    assert changed
    assert led == f'Sarah Chen: {title}'
    assert len(led) > TWO_NAME_LEAD_MAX_CHARACTERS


def test_lead_strips_whitespace_around_names():
    from utils.llm.meeting_notes_validation import lead_title_with_people

    assert lead_title_with_people('Budget', ('Sarah ',)) == ('Sarah: Budget', True)
    assert lead_title_with_people('Budget', (' Sarah', ' ', 'John ')) == ('Sarah & John: Budget', True)


def test_title_people_compare_names_without_surrounding_whitespace(monkeypatch):
    # "Sarah " (source A) and "Sarah" (source B) are one person, and a person record
    # named "David" is the owner whose profile name is "David ".
    people = [_person('p-sarah-a', 'Sarah '), _person('p-sarah-b', 'Sarah'), _person('p-david', 'David')]
    conversation = SimpleNamespace(
        transcript_segments=[
            _seg('a1', 'hey so where are we on the budget for next quarter', scope='conv-a'),
            _seg('a2', SARAH_LONG, speaker='SPEAKER_01', is_user=False, person_id='p-sarah-a', scope='conv-a'),
            _seg('b1', SARAH_SHORT, speaker='SPEAKER_01', is_user=False, person_id='p-sarah-b', scope='conv-b'),
            _seg(
                'b2', 'thanks everyone for joining us today', speaker='SPEAKER_02', is_user=False, person_id='p-david'
            ),
        ]
    )

    prefix = _prefix_for(conversation, monkeypatch, owner_name='David ', people=people)

    assert prefix.title_people == ('Sarah',)
    assert prefix.owner_names == ('David',)


@pytest.mark.parametrize(
    ('title', 'people'),
    [
        ('', ('Sarah Chen',)),
        ('   ', ('Sarah Chen',)),
        ('Grocery List', ()),
    ],
)
def test_lead_never_invents_a_title_or_a_name(title, people):
    from utils.llm.meeting_notes_validation import lead_title_with_people

    assert lead_title_with_people(title, people) == (title, False)


def test_name_match_is_whole_word_and_escapes_punctuation():
    from utils.llm.meeting_notes_validation import title_names_any_person

    assert title_names_any_person("Catch-up with O'Neill", ("Pat O'Neil",)) is False
    assert title_names_any_person("Pat O'Neil Reviews Launch", ("Pat O'Neil",)) is True
    assert title_names_any_person('Sarahville Trip Planning', ('Sarah Chen',)) is False
    assert title_names_any_person('Al.Ex Sync', ('Al.Ex',)) is True
    assert title_names_any_person('Leeds Office Move', ('Lee',)) is False
    assert title_names_any_person('Leeds Office Move', ('Lee Park',)) is False


@pytest.mark.parametrize(
    ('title', 'people'),
    [
        ('Chen Reviews Q2 Budget', ('Sarah Chen',)),
        ("Catch-up with O'Neil", ("Pat O'Neil",)),
    ],
)
def test_surname_only_mention_already_names_the_person(title, people):
    from utils.llm.meeting_notes_validation import lead_title_with_people

    assert lead_title_with_people(title, people) == (title, False)


def test_short_surname_is_not_a_mention():
    from utils.llm.meeting_notes_validation import lead_title_with_people

    # A two-letter surname matches too much ("Li-ion") to count on its own.
    assert lead_title_with_people('Li-ion Battery Supply Review', ('Wei Li',)) == (
        'Wei Li: Li-ion Battery Supply Review',
        True,
    )


@pytest.mark.parametrize(
    ('title', 'people'),
    [
        ('王伟讨论预算', ('王伟',)),  # Chinese: no spaces between words
        ('田中さんと予算会議', ('田中 太郎',)),  # Japanese: family name only, honorific attached
        ('김민준과 예산 회의', ('김민준',)),  # Korean: particle attached to the name
        ('สมชายประชุมงบประมาณ', ('สมชาย',)),  # Thai: no spaces between words
        ('与Sarah讨论预算', ('Sarah Chen',)),  # a spaced-script name inside unspaced text
    ],
)
def test_names_in_unspaced_scripts_already_name_the_person(title, people):
    from utils.llm.meeting_notes_validation import lead_title_with_people

    assert lead_title_with_people(title, people) == (title, False)


def test_unspaced_script_names_still_need_a_real_match():
    from utils.llm.meeting_notes_validation import lead_title_with_people

    assert lead_title_with_people('王小明讨论预算', ('王伟',)) == ('王伟: 王小明讨论预算', True)
    # A one-character token (a common family name) is not a mention on its own.
    assert lead_title_with_people('王小明讨论预算', ('王 伟',)) == ('王 伟: 王小明讨论预算', True)


def test_title_lead_repair_is_counted_as_a_static_presentation_repair(monkeypatch):
    from utils.llm import meeting_notes_presentation

    recorded: list = []
    monkeypatch.setattr(
        meeting_notes_presentation,
        '_record_contract',
        lambda *, outcome, reasons: recorded.append((outcome, sorted(reasons))),
    )
    prefix = _prefix_for(_three_party_conversation(), monkeypatch)

    _notes(prefix, monkeypatch, title='Q2 Budget Cuts and Offsite Move')

    assert ('static_repair', ['title_people_lead']) in recorded


def test_rich_meeting_notes_titles_are_left_to_the_roster_rules(monkeypatch):
    from utils.conversations.meeting_participants import MeetingRoster, RosterEntry
    from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix

    roster = MeetingRoster(
        entries=(
            RosterEntry(display_name='David', email=None, organization=None, kind='owner', source='calendar'),
            RosterEntry(display_name='Sarah Chen', email=None, organization=None, kind='human', source='calendar'),
        ),
        display_title='Budget sync',
        title_is_window_title=False,
    )
    prefix = ConversationPromptPrefix(
        conversation_id='conv-rich',
        context='CONVERSATION METADATA\n- Captured at: now (UTC)\n\nFULL TRANSCRIPT\n[s1 0] budget talk',
        transcript_segment_ids=frozenset({'s1'}),
        title_people=('Sarah Chen',),
        owner_names=('David',),
    )

    structured, messages = _notes(prefix, monkeypatch, title='Budget Sync', rich=True, roster=roster)

    assert structured.title == 'Budget Sync'
    assert 'PEOPLE IN THIS CONVERSATION' not in _text(messages[1])
