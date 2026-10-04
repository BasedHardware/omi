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


def _seg(segment_id, text, *, speaker='SPEAKER_00', is_user=True, person_id=None):
    return TranscriptSegment(
        id=segment_id,
        text=text,
        speaker=speaker,
        is_user=is_user,
        person_id=person_id,
        start=0.0,
        end=2.0,
    )


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
    return [
        Person(id='p-sarah', name='Sarah Chen', created_at=STARTED_AT, updated_at=STARTED_AT),
        Person(id='p-lee', name='Lee', created_at=STARTED_AT, updated_at=STARTED_AT),
    ]


def _prefix_for(conversation, monkeypatch, *, owner_name='David'):
    from utils.conversations import transcript_for_llm
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: owner_name)
    transcript, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map(
        'uid-1', conversation, _people()
    )
    return build_conversation_prompt_prefix(
        conversation_id='conv-names',
        transcript=transcript,
        started_at=STARTED_AT,
        timezone_name='UTC',
        language_code='en',
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


def test_speaker_map_remembers_owner_clusters_and_words_spoken(monkeypatch):
    from utils.conversations import transcript_for_llm

    monkeypatch.setattr(transcript_for_llm, 'get_user_name', lambda *_a, **_k: 'David')
    _, speaker_map = transcript_for_llm.conversation_transcript_and_speaker_map(
        'uid-1', _three_party_conversation(), _people()
    )

    # Still the plain cluster -> name mapping every existing caller reads.
    assert speaker_map == {0: 'David', 1: 'Sarah Chen', 2: 'Lee'}
    assert speaker_map.owner_keys == frozenset({0})
    assert speaker_map.word_counts == {0: 14, 1: 38, 2: 1}


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
    from utils.llm.meeting_notes_validation import MAX_LED_TITLE_CHARACTERS, lead_title_with_people

    title = 'Quarterly Vendor Spend Review and Offsite Rescheduling'
    led, changed = lead_title_with_people(title, ('Sarah Chen', 'Johnathan Park'))

    assert changed
    assert led == f'Sarah Chen: {title}'
    assert len(f'Sarah Chen & Johnathan Park: {title}') > MAX_LED_TITLE_CHARACTERS


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

    assert title_names_any_person("Catch-up with O'Neil", ("Pat O'Neil",)) is False
    assert title_names_any_person("Pat O'Neil Reviews Launch", ("Pat O'Neil",)) is True
    assert title_names_any_person('Sarahville Trip Planning', ('Sarah Chen',)) is False
    assert title_names_any_person('Al.Ex Sync', ('Al.Ex',)) is True


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
