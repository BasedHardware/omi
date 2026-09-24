"""Flagged rich meeting notes: roster normalization, roster prompt path, and the
context pack. Flag-off behaviour is pinned byte-identical by construction — the
rich path only activates on explicit arguments, and every test here feeds them.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

import google.auth.credentials  # noqa: F401,E402

from testing.import_isolation import stub_modules  # noqa: E402
from models.calendar_context import CalendarMeetingContext, MeetingParticipant  # noqa: E402
from models.conversation_enums import ConversationSource  # noqa: E402
from models.transcript_segment import TranscriptSegment  # noqa: E402
from utils.conversations.meeting_context_pack import (  # noqa: E402
    MAX_CONTEXT_PACK_CHARACTERS,
    MeetingContextPack,
    PersonFact,
    PriorMeetingNote,
    render_meeting_context_pack,
    should_gather_meeting_context,
)
from utils.conversations.meeting_participants import (  # noqa: E402
    MeetingRoster,
    RosterEntry,
    clean_display_title,
    normalize_meeting_participants,
)

START = datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules({}):
        # Keep production-module import cost out of individual fast-unit timing.
        import utils.conversations.process_conversation  # noqa: F401
        import utils.llm.conversation_processing  # noqa: F401
        import utils.llm.conversation_prompt_prefix  # noqa: F401

        yield


def _context(participants, title='Scaling Forever sync', source='macos_calendar', platform='Zoom'):
    return CalendarMeetingContext(
        calendar_event_id='evt-1',
        title=title,
        participants=list(participants),
        platform=platform,
        start_time=START,
        duration_minutes=30,
        calendar_source=source,
    )


def _roster(entries):
    return MeetingRoster(entries=tuple(entries), display_title='Scaling Forever sync', title_is_window_title=False)


def _entry(name=None, email=None, org=None, kind='human', source='macos_calendar', person_id=None):
    return RosterEntry(display_name=name, email=email, organization=org, kind=kind, source=source, person_id=person_id)


class TestNormalizeMeetingParticipants:
    def test_owner_matched_by_any_owner_email_and_emitted_once(self):
        roster = normalize_meeting_participants(
            _context(
                [
                    MeetingParticipant(name='David Zheng', email='DAVID@acme.com'),
                    MeetingParticipant(name='Ash Kalb', email='ash@fulcra.com'),
                ]
            ),
            ConversationSource.desktop,
            owner_name='David Zheng',
            owner_emails=['david@acme.com', 'david@work.dev'],
            people=[],
        )
        owners = [entry for entry in roster.entries if entry.kind == 'owner']
        assert len(owners) == 1
        assert owners[0].display_name == 'David Zheng'
        assert {entry.display_name for entry in roster.entries if entry.kind == 'human'} == {'Ash Kalb'}

    def test_owner_emitted_even_when_absent_from_participants(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='Ash Kalb', email='ash@fulcra.com')]),
            ConversationSource.desktop,
            owner_name='David Zheng',
            owner_emails=['david@acme.com'],
            people=[],
        )
        assert [entry.kind for entry in roster.entries].count('owner') == 1
        assert roster.entries[0].display_name == 'David Zheng'

    def test_no_owner_identity_fabricates_nothing(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='Ash Kalb', email='ash@fulcra.com')]),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[],
        )
        assert all(entry.kind != 'owner' for entry in roster.entries)

    def test_email_local_part_owner_match_on_owned_domain(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name=None, email='dazheng@acme-corp.com')]),
            ConversationSource.desktop,
            owner_name='David',
            owner_emails=['dazheng@gmail.com'],
            people=[],
        )
        assert [entry.kind for entry in roster.entries].count('owner') == 1

    def test_freemail_local_part_matches_owner_across_domains(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name=None, email='dazheng@yahoo.com')]),
            ConversationSource.desktop,
            owner_name='David',
            owner_emails=['dazheng@gmail.com'],
            people=[],
        )
        # Local-part matching crosses domains, freemail included: the Yahoo
        # participant IS the owner, so exactly one owner is emitted.
        owners = [entry for entry in roster.entries if entry.kind == 'owner']
        assert len(owners) == 1
        assert owners[0].email == 'dazheng@yahoo.com'
        assert [entry for entry in roster.entries if entry.kind == 'human'] == []

    def test_duck_com_local_part_matches_owner_across_domains(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name=None, email='dazheng@duck.com')]),
            ConversationSource.desktop,
            owner_name='David',
            owner_emails=['dazheng@gmail.com'],
            people=[],
        )
        owners = [entry for entry in roster.entries if entry.kind == 'owner']
        assert len(owners) == 1
        assert owners[0].email == 'dazheng@duck.com'

    def test_surname_compatible_second_owner_entry_collapses(self):
        # "David Zing <david@acme.com>" proves the owner by email; the
        # OCR-truncated "David ZI" then collapses into the same owner rather
        # than becoming a second participant.
        roster = normalize_meeting_participants(
            _context(
                [
                    MeetingParticipant(name='David Zing', email='david@acme.com'),
                    MeetingParticipant(name='David ZI'),
                ]
            ),
            ConversationSource.desktop,
            owner_name='David Zing',
            owner_emails=['david@acme.com'],
            people=[],
        )
        owners = [entry for entry in roster.entries if entry.kind == 'owner']
        assert len(owners) == 1
        assert [entry for entry in roster.entries if entry.kind == 'human'] == []

    def test_email_proved_surname_anchor_collapses_ocr_repeat(self):
        # First-name-only auth plus an email-proved "David Zhang": the surname
        # anchor comes from the proved entry, so the OCR "David ZI" collapses
        # even though two participants share the first token — while the
        # unrelated same-first "David Smith" stays a human.
        roster = normalize_meeting_participants(
            _context(
                [
                    MeetingParticipant(name='David Zhang', email='david.one@gmail.com'),
                    MeetingParticipant(name='David ZI', email='david.other@gmail.com'),
                    MeetingParticipant(name='David Smith', email='dsmith@example.com'),
                ]
            ),
            ConversationSource.desktop,
            owner_name='David',
            owner_emails=['david.one@gmail.com'],
            people=[],
        )
        owners = [entry for entry in roster.entries if entry.kind == 'owner']
        assert len(owners) == 1
        # The merged owner prefers the canonical verified full name over OCR.
        assert owners[0].display_name == 'David Zhang'
        assert [entry.display_name for entry in roster.entries if entry.kind == 'human'] == ['David Smith']

    def test_surname_prefix_ocr_near_matches_owner(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='David ZI'), MeetingParticipant(name='Ash')]),
            ConversationSource.desktop,
            owner_name='David Zing',
            owner_emails=[],
            people=[],
        )
        owners = [entry for entry in roster.entries if entry.kind == 'owner']
        assert len(owners) == 1
        assert owners[0].display_name == 'David ZI'
        assert [entry.display_name for entry in roster.entries if entry.kind == 'human'] == ['Ash']

    def test_conflicting_surname_never_collapses_into_owner(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='David Smith')]),
            ConversationSource.desktop,
            owner_name='David Zing',
            owner_emails=[],
            people=[],
        )
        owners = [entry for entry in roster.entries if entry.kind == 'owner']
        assert len(owners) == 1  # the known owner is still emitted once
        assert owners[0].display_name == 'David Zing'
        assert [entry.display_name for entry in roster.entries if entry.kind == 'human'] == ['David Smith']

    def test_two_same_first_token_participants_leave_owner_ambiguous(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='David Zi'), MeetingParticipant(name='David Smith')]),
            ConversationSource.desktop,
            owner_name='David Zing',
            owner_emails=[],
            people=[],
        )
        humans = [entry.display_name for entry in roster.entries if entry.kind == 'human']
        assert sorted(humans) == ['David Smith', 'David Zi']

    @pytest.mark.parametrize(
        'name',
        [
            'Boardy',
            'Otter',
            'Otter.ai',
            'Fireflies',
            'Fred from Fireflies',
            'Read.ai',
            'Fathom',
            'tl;dv',
            'Notetaker',
            'Zoom AI Companion',
            'Gemini',
            'Omi Agent',
            'O. Omi Agent',
            'Acme Notetaker',
            'Boardy Boardman',
            'boardy',
            'Fireflies Bot',
            "David's Omi Agent",
        ],
    )
    def test_ai_agent_name_catalog(self, name):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name=name)]),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[],
        )
        assert roster.entries[0].kind == 'ai_agent'

    @pytest.mark.parametrize(
        'email',
        [
            'feed@otter.ai',
            'bot@fireflies.ai',
            'noreply@boardy.ai',
            'relay@read.ai',
            'notes@fathom.video',
            'rec@tldv.io',
            'bot@relay.local',
        ],
    )
    def test_ai_agent_domains(self, email):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='Notes', email=email)]),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[],
        )
        assert roster.entries[0].kind == 'ai_agent'

    @pytest.mark.parametrize(
        'name', ['Jamie', 'Granola Smith', 'Gong User', 'Copilot Fan', 'Ottery Lane', 'Fathoma Reyes', 'Agent Smith']
    )
    def test_human_names_are_not_misclassified_as_agents(self, name):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name=name)]),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[],
        )
        assert roster.entries[0].kind == 'human'

    def test_people_catalog_flags_and_enriches(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='Ash')]),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[
                {'id': 'p-ash', 'name': 'Ash Kalb', 'organization': 'Fulcra Dynamics', 'email': 'ash@fulcra.com'},
                {'id': 'p-ash2', 'name': 'Ash Doe', 'organization': 'Elsewhere'},
            ],
        )
        # Two catalog entries share the first token — no merge may pick one.
        assert roster.entries[0].person_id is None
        assert roster.entries[0].display_name == 'Ash'

    def test_single_catalog_candidate_resolves_and_supplies_metadata(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name='Ash', email='ash@fulcra.com')]),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[{'id': 'p-ash', 'name': 'Ash Kalb', 'organization': 'Fulcra Dynamics', 'email': 'ash@fulcra.com'}],
        )
        entry = roster.entries[0]
        assert entry.person_id == 'p-ash'
        assert entry.display_name == 'Ash Kalb'
        assert entry.organization == 'Fulcra Dynamics'

    def test_email_only_participant_resolves_through_person_aliases(self):
        roster = normalize_meeting_participants(
            _context([MeetingParticipant(name=None, email='akalb@fulcra.com')]),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[{'id': 'p-ash', 'name': 'Ash Kalb', 'aliases': ['akalb@fulcra.com']}],
        )
        assert roster.entries[0].display_name == 'Ash Kalb'
        assert roster.entries[0].person_id == 'p-ash'

    def test_same_email_aliases_dedupe_keeping_the_best_name(self):
        roster = normalize_meeting_participants(
            _context(
                [
                    MeetingParticipant(name='Ash', email='ash@fulcra.com'),
                    MeetingParticipant(name='Ash Kalb', email='ASH@fulcra.com'),
                ]
            ),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[],
        )
        assert len(roster.entries) == 1
        assert roster.entries[0].display_name == 'Ash Kalb'

    @pytest.mark.parametrize(
        ('title', 'platform', 'expected'),
        [
            (
                'Meet - dyo-jguo-jrw - Camera and microphone recording - Google Chrome - David (scalingforever.com)',
                'Meet',
                'Google Meet call',
            ),
            ('\u200e\u2068Release\u2069 – (68226)', 'Telegram', 'Telegram call: Release'),
            ('\u200e\u2068Metrics\u2069 – (77589)', 'Telegram', 'Telegram call: Metrics'),
            ('Zoom Meeting - Google Chrome - David', 'Zoom', 'Zoom call'),
            ('Microsoft Teams | Audio playing', 'Teams', 'Microsoft Teams call'),
            ('🔊 Meet - dyo-jguo-jrw', 'Meet', 'Google Meet call'),
        ],
    )
    def test_screen_titles_normalize_to_canonical_call_titles(self, title, platform, expected):
        assert clean_display_title(title, screen_derived=True, platform=platform) == expected

    def test_telegram_detection_requires_the_platform(self):
        # An arbitrary chat app with the same title shape is not a Telegram call.
        assert (
            clean_display_title('\u2068Release\u2069 – (68226)', screen_derived=True, platform='WhatsApp') == 'Release'
        )

    def test_screen_title_cleaning_and_calendar_title_passthrough(self):
        assert clean_display_title('\u202a(3) Alice Chen - Zoom\u202c', screen_derived=True) == 'Alice Chen'
        assert clean_display_title('meet - abc-defg-hij', screen_derived=True) == 'Google Meet call'
        assert clean_display_title('Zoom Meeting', screen_derived=True) == 'Zoom call'
        assert clean_display_title('Raw title — Google Meet', screen_derived=False) == 'Raw title — Google Meet'

    def test_screen_derived_context_marks_window_title(self):
        roster = normalize_meeting_participants(
            _context(
                [MeetingParticipant(name='Ash')], title='(2) Sprint review - Google Meet', source='screen_activity'
            ),
            ConversationSource.desktop,
            owner_name=None,
            owner_emails=[],
            people=[],
        )
        assert roster.title_is_window_title is True
        assert roster.display_title == 'Sprint review'
        assert roster.entries[0].source == 'screen_activity'


class TestRosterPromptPrefix:
    def _build(self, *, roster=None, speaker_map=None, calendar_context=None, desktop_capture=False):
        from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

        return build_conversation_prompt_prefix(
            conversation_id='conv-rich',
            transcript='[s1 0] hello everyone\n[s2 1] hi',
            started_at=START,
            timezone_name='UTC',
            language_code='en',
            calendar_context=calendar_context,
            speaker_map=speaker_map,
            roster=roster,
            desktop_meeting_capture=desktop_capture,
        )

    def test_roster_path_renders_participants_block(self):
        roster = _roster(
            [
                _entry('David Zheng', 'david@acme.com', 'Acme', kind='owner'),
                _entry('Ash Kalb', 'ash@fulcra.com', 'Fulcra Dynamics'),
            ]
        )
        prefix = self._build(roster=roster, speaker_map={0: 'David Zheng', 1: None})
        assert 'PARTICIPANTS\n- David Zheng | Acme | owner | via macos_calendar' in prefix.context
        assert '- Ash Kalb | Fulcra Dynamics | human | via macos_calendar' in prefix.context
        # One unresolved cluster + exactly one unbound named human → bound.
        assert 'spk 1 Ash Kalb' in prefix.context

    def test_strict_guard_leaves_cluster_unbound_when_ai_present(self):
        roster = _roster(
            [
                _entry('David', 'david@acme.com', kind='owner'),
                _entry('Ash Kalb', 'ash@fulcra.com'),
                _entry('Boardy', None, None, kind='ai_agent'),
            ]
        )
        prefix = self._build(roster=roster, speaker_map={0: 'David', 1: None})
        # One unresolved cluster and one unbound named human, but the AI agent
        # could be that cluster's true identity → never bind.
        assert 'spk 1 ?' in prefix.context
        assert 'spk 1 Ash Kalb' not in prefix.context
        assert '- Boardy | - | ai agent | via macos_calendar' in prefix.context

    def test_strict_guard_leaves_cluster_unbound_with_nameless_human(self):
        roster = _roster(
            [
                _entry('David', 'david@acme.com', kind='owner'),
                _entry('Ash Kalb', 'ash@fulcra.com'),
                _entry(None, 'plus-one@fulcra.com'),
            ]
        )
        prefix = self._build(roster=roster, speaker_map={0: 'David', 1: None})
        assert 'spk 1 ?' in prefix.context
        assert 'spk 1 Ash Kalb' not in prefix.context

    def test_desktop_remote_cluster_demoted_when_channel_is_mixed(self):
        roster = _roster(
            [
                _entry('David', 'david@acme.com', kind='owner'),
                _entry('Ash Kalb', 'ash@fulcra.com'),
                _entry('Priya Rao', 'priya@fulcra.com'),
            ]
        )
        prefix = self._build(
            roster=roster,
            speaker_map={0: 'David', 1: 'Ash Kalb'},
            desktop_capture=True,
        )
        assert 'spk 1 ?' in prefix.context
        assert 'remote audio channel' in prefix.context
        assert 'Priya Rao' in prefix.context

    def test_desktop_mixed_remote_never_binds_to_boardy(self):
        # Owner + nameless duck.com guest + Boardy: the remote channel could be
        # either remote party, so even a cluster pre-bound to Boardy demotes.
        roster = _roster(
            [
                _entry('David', 'david@acme.com', kind='owner'),
                _entry(None, 'guest@duck.com'),
                _entry('Boardy', None, None, kind='ai_agent'),
            ]
        )
        prefix = self._build(
            roster=roster,
            speaker_map={0: 'David', 1: 'Boardy'},
            desktop_capture=True,
        )
        assert 'spk 1 Boardy' not in prefix.context
        assert 'spk 1 ?' in prefix.context
        assert 'remote audio channel; may contain several people' in prefix.context

        # The same roster with the cluster left unresolved also cannot bind to
        # the only named remote (an AI agent and a nameless human both block).
        prefix = self._build(
            roster=roster,
            speaker_map={0: 'David', 1: None},
            desktop_capture=True,
        )
        assert 'spk 1 Boardy' not in prefix.context
        assert 'spk 1 ?' in prefix.context

    def test_flag_off_prefix_is_the_legacy_rendering(self):
        context = _context(
            [MeetingParticipant(name='David'), MeetingParticipant(name='Ash Kalb', email='ash@fulcra.com')]
        )
        prefix = self._build(calendar_context=context, speaker_map={0: 'David', 1: None})
        # Literal baseline of the legacy rendering: original metadata lines and
        # the transcript, byte-for-byte. The one-name guard still binds.
        assert prefix.context == (
            'CONVERSATION METADATA\n'
            '- Captured at: 2026-08-18T14:00:00 (UTC)\n'
            '- Meeting title: Scaling Forever sync\n'
            '- Participants: David, Ash Kalb <ash@fulcra.com>\n'
            '- Platform: Zoom\n'
            '- Meeting notes: Not specified\n'
            'spk 0 David\n'
            'spk 1 Ash Kalb\n'
            '\n'
            'FULL TRANSCRIPT\n'
            '[s1 0] hello everyone\n[s2 1] hi'
        )


class TestRichConversationNotes:
    def _call(self, monkeypatch, *, payload, meeting_context=None, roster=None, rich_enabled=True):
        from utils.llm import conversation_processing
        from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix

        captured: dict = {}

        class Model:
            def invoke(self, messages):
                captured['messages'] = messages
                return SimpleNamespace(content=json.dumps(payload))

        monkeypatch.setattr(conversation_processing, 'get_llm', lambda *_a, **_k: Model())
        monkeypatch.setattr(conversation_processing, 'shared_conversation_cache_supported', lambda: False)
        prefix = ConversationPromptPrefix(
            conversation_id='conv-rich',
            context='CONVERSATION METADATA\n- Captured at: now (UTC)\n\nFULL TRANSCRIPT\nAsh Kalb and Priya Rao met.',
        )
        structured = conversation_processing.get_conversation_notes(
            prefix,
            started_at=START,
            language_code='en',
            output_language_code='en',
            tz='UTC',
            task_intelligence_capture=True,
            meeting_context=meeting_context,
            rich_context_enabled=rich_enabled,
            roster=roster,
        )
        return structured, captured['messages'], prefix

    def _message_text(self, message) -> str:
        content = message.content if hasattr(message, 'content') else message['content']
        if isinstance(content, list):
            return ''.join(part.get('text', '') for part in content if isinstance(part, dict))
        return str(content)

    def test_rich_fields_parse_and_validate(self, monkeypatch):
        roster = _roster(
            [
                _entry('David', 'david@acme.com', kind='owner'),
                _entry('Ash Kalb', 'ash@fulcra.com'),
            ]
        )
        payload = {
            'title': 'Fulcra Sync',
            'overview': 'compat',
            'emoji': '🧠',
            'category': 'work',
            'sections': [
                {'heading': 'Plan', 'body_markdown': '- Decided the date', 'kind': 'main'},
                {'heading': 'Banter', 'body_markdown': '- Fantasy football tangent', 'kind': 'side_notes'},
            ],
            'action_items': [],
            'events': [],
            'meeting_type': 'one_on_one',
            'participants': [
                {'name': 'David', 'email': 'david@acme.com', 'source': 'roster'},
                {'name': 'Ash Kalb', 'email': 'ash@fulcra.com', 'source': 'roster'},
                {'name': 'Nobody Invented', 'source': 'transcript'},
                {'name': 'Priya Rao', 'source': 'transcript'},
            ],
            'insights': [{'text': 'Short insight', 'kind': 'prior_meeting'}],
        }
        structured, messages, prefix = self._call(
            monkeypatch,
            payload=payload,
            meeting_context='BACKGROUND CONTEXT (not part of this conversation)\n\nPRIOR MEETINGS\n- met before',
            roster=roster,
        )
        assert structured.meeting_type == 'one_on_one'
        # Owner dropped; uncorroborated name dropped; roster and transcript names kept.
        names = [p.name for p in structured.participants]
        assert names == ['Ash Kalb', 'Priya Rao']
        assert structured.insights[0].kind == 'prior_meeting'
        assert structured.sections[-1].kind == 'side_notes'
        assert structured.sections[-1].heading == 'Side notes'
        static_text = self._message_text(messages[0])
        volatile_text = self._message_text(messages[1])
        # The headed background block and its content live only in the volatile
        # suffix; the static rules describe it but never carry the payload.
        assert 'BACKGROUND CONTEXT (not part of this conversation)' in volatile_text
        assert 'PRIOR MEETINGS' not in static_text
        assert 'met before' not in static_text
        assert 'PRIOR MEETINGS' not in prefix.context
        assert 'meeting_type' in static_text  # rich schema ships in the format instructions

    def test_prompt_split_keeps_legacy_language_out_of_rich(self, monkeypatch):
        payload = {
            'title': 't',
            'overview': 'o',
            'emoji': '🧠',
            'category': 'work',
            'sections': [{'heading': 'h', 'body_markdown': '- b'}],
            'action_items': [],
            'events': [],
        }
        _, off_messages, _ = self._call(monkeypatch, payload=payload, rich_enabled=False)
        _, on_messages, prefix = self._call(
            monkeypatch,
            payload=payload,
            meeting_context='BACKGROUND CONTEXT (not part of this conversation)\n\nGOALS\n- ship',
            roster=_roster([_entry('Ash Kalb', 'ash@fulcra.com')]),
        )
        off_text = self._message_text(off_messages[0]) + '\n' + self._message_text(off_messages[1])
        on_text = self._message_text(on_messages[0]) + '\n' + self._message_text(on_messages[1])
        on_static = self._message_text(on_messages[0])
        on_volatile = self._message_text(on_messages[1])
        assert 'Prefer one or two substantial bullets per section' in off_text
        assert 'Omit repetition,\n  incidental tangents' in off_text
        assert 'Prefer one or two substantial bullets per section' not in on_text
        assert 'Omit repetition,\n  incidental tangents' not in on_text
        assert 'BACKGROUND CONTEXT (not part of this conversation)' in on_volatile
        assert 'PRIOR MEETINGS' not in on_static
        assert 'PRIOR MEETINGS' not in prefix.context

    def test_flag_off_structured_serialization_keeps_legacy_shape(self, monkeypatch):
        from models.structured import Section

        payload = {
            'title': 't',
            'overview': 'o',
            'emoji': '🧠',
            'category': 'work',
            'sections': [{'heading': 'h', 'body_markdown': '- b'}],
            'action_items': [],
            'events': [],
        }
        structured, _, _ = self._call(monkeypatch, payload=payload, rich_enabled=False)
        assert set(structured.model_dump()) == {
            'title',
            'overview',
            'emoji',
            'category',
            'sections',
            'action_items',
            'events',
        }
        assert set(Section(heading='h', body_markdown='- b').model_dump()) == {
            'heading',
            'body_markdown',
            'source_segment_ids',
        }

    def test_legacy_conversation_document_stamps_no_rich_keys(self):
        from models.conversation import Conversation
        from models.structured import Section, Structured

        conversation = Conversation(
            id='c1',
            created_at=START,
            started_at=START,
            finished_at=START + timedelta(minutes=30),
            structured=Structured(
                title='t',
                overview='o',
                sections=[Section(heading='h', body_markdown='- b')],
            ),
        )
        structured_dump = conversation.model_dump()['structured']
        assert 'meeting_type' not in structured_dump
        assert 'participants' not in structured_dump
        assert 'insights' not in structured_dump
        assert 'kind' not in structured_dump['sections'][0]

    def test_insights_empty_without_background_and_capped(self, monkeypatch):
        payload = {
            'title': 't',
            'overview': 'o',
            'emoji': '🧠',
            'category': 'work',
            'sections': [],
            'action_items': [],
            'events': [],
            'participants': [],
            'insights': [{'text': ' '.join(['word'] * 40), 'kind': 'memory'}] * 6,
        }
        structured, _, _ = self._call(monkeypatch, payload=payload, meeting_context=None, roster=_roster([]))
        assert structured.insights == []

        structured, _, _ = self._call(
            monkeypatch,
            payload=payload,
            meeting_context='BACKGROUND CONTEXT (not part of this conversation)\n\nGOALS\n- ship',
            roster=_roster([]),
        )
        assert len(structured.insights) == 4
        assert all(len(insight.text.split()) <= 30 for insight in structured.insights)

    def test_side_notes_sections_merge_into_one_last_section(self, monkeypatch):
        payload = {
            'title': 't',
            'overview': 'o',
            'emoji': '🧠',
            'category': 'work',
            'sections': [
                {'heading': 'Plan', 'body_markdown': '- Decided the date', 'kind': 'main'},
                {'heading': 'Aside', 'body_markdown': '- Keyboard tangent\n- Coffee rec', 'kind': 'side_notes'},
                {'heading': 'Work', 'body_markdown': '- Scope agreed', 'kind': 'main'},
                {
                    'heading': 'More aside',
                    'body_markdown': '- Book link\n- Keyboard tangent\n- Third\n- Fourth\n- Fifth extra',
                    'kind': 'side_notes',
                },
            ],
            'action_items': [],
            'events': [],
            'participants': [],
            'insights': [],
        }
        structured, _, _ = self._call(monkeypatch, payload=payload, roster=_roster([]))
        side = [s for s in structured.sections if s.kind == 'side_notes']
        assert len(side) == 1
        assert structured.sections[-1].kind == 'side_notes'
        assert structured.sections[-1].heading == 'Side notes'
        bullets = [line for line in structured.sections[-1].body_markdown.split('\n') if line.strip()]
        # Earlier tangents merge in, duplicates collapse, and the cap holds.
        assert len(bullets) == 4
        assert '- Coffee rec' in bullets
        assert '- Book link' in bullets
        assert bullets.count('- Keyboard tangent') == 1

    def test_render_sections_markdown_puts_side_notes_last(self):
        from models.structured import Section
        from utils.conversations.summary_selection import render_sections_markdown

        rendered = render_sections_markdown(
            [
                Section(heading='Side notes', body_markdown='- tangent', kind='side_notes'),
                Section(heading='Plan', body_markdown='- work'),
            ]
        )
        assert rendered.index('## Plan') < rendered.index('## Side notes')


class TestMeetingContextPack:
    def test_empty_pack_renders_nothing(self):
        assert render_meeting_context_pack(MeetingContextPack()) == ''
        assert render_meeting_context_pack(None) == ''

    def test_render_is_capped_and_headed(self):
        pack = MeetingContextPack(
            prior_meetings=tuple(
                PriorMeetingNote(title=f'Meeting {i}', date_label='2026-08-01', gist='x' * 400) for i in range(10)
            ),
            people_facts=(PersonFact(name='Ash Kalb', relationship='collaborator', notes='y' * 500),),
            goals=tuple('g' * 300 for _ in range(5)),
            memories=tuple('m' * 300 for _ in range(6)),
            screen_text='s' * 4000,
        )
        rendered = render_meeting_context_pack(pack)
        assert rendered.startswith('BACKGROUND CONTEXT (not part of this conversation)')
        assert len(rendered) <= MAX_CONTEXT_PACK_CHARACTERS
        assert 'PRIOR MEETINGS' in rendered
        assert 'SCREEN ACTIVITY' in rendered

    def test_oversized_item_truncates_instead_of_crowding_out_later_items(self):
        pack = MeetingContextPack(
            prior_meetings=(PriorMeetingNote(title='Sync', date_label='2026-08-01', gist='ok'),),
            people_facts=(
                PersonFact(name='A' * 400, relationship='x' * 900, notes='n' * 900),
                PersonFact(name='Bob', relationship='friend'),
            ),
        )
        rendered = render_meeting_context_pack(pack)
        # The oversized fact truncates to the part budget instead of dropping
        # the whole PEOPLE section; other parts still render.
        assert 'PRIOR MEETINGS' in rendered
        people_part = rendered.split('PEOPLE\n', 1)[1]
        assert len(people_part) <= 900
        assert people_part.endswith('…')
        # When the budget has room left, later small items still land.
        pack = MeetingContextPack(
            people_facts=(
                PersonFact(name='A' * 400, relationship='x' * 300),
                PersonFact(name='Bob', relationship='friend'),
            )
        )
        assert 'Bob (friend)' in render_meeting_context_pack(pack)

    def test_gather_skips_memory_read_without_identity_needles(self, monkeypatch):
        import utils.conversations.meeting_context_pack as pack_module

        calls = {'memories': 0, 'goals': 0}
        monkeypatch.setattr(
            pack_module.memories_db,
            'get_memories',
            lambda *a, **k: calls.__setitem__('memories', calls['memories'] + 1) or [],
        )
        monkeypatch.setattr(
            pack_module.goals_db,
            'get_user_goals',
            lambda *a, **k: calls.__setitem__('goals', calls['goals'] + 1) or [],
        )
        # Roster of only the owner + an AI agent: no human identity needle, so
        # the memories read is skipped entirely.
        roster = _roster(
            [
                _entry('David', 'david@acme.com', kind='owner'),
                _entry('Boardy', None, None, kind='ai_agent'),
            ]
        )
        conversation = SimpleNamespace(started_at=START, finished_at=START + timedelta(minutes=30), id='c1')
        pack_module.gather_meeting_context_pack('uid', conversation, roster, people=[], include_screen_text=False)
        assert calls['memories'] == 0

    def test_per_source_failures_degrade_independently(self, monkeypatch):
        import utils.conversations.meeting_context_pack as pack_module

        def boom(*a, **k):
            raise RuntimeError('sensitive pii payload should not be logged')

        monkeypatch.setattr(pack_module.calendar_db, 'list_meetings', boom)
        monkeypatch.setattr(pack_module.conversations_db, 'get_conversations_without_photos', boom)
        monkeypatch.setattr(pack_module.goals_db, 'get_user_goals', boom)
        monkeypatch.setattr(pack_module.memories_db, 'get_memories', boom)
        monkeypatch.setattr(pack_module.screen_activity_db, 'get_screen_activity', boom)
        roster = _roster([_entry('Ash Kalb', 'ash@fulcra.com')])
        conversation = SimpleNamespace(started_at=START, finished_at=START + timedelta(minutes=30), id='c1')
        pack = pack_module.gather_meeting_context_pack('uid', conversation, roster, people=[], include_screen_text=True)
        # Every source failed; the pack is empty but nothing raised.
        assert pack is None

    def test_gather_gate(self):
        segment = TranscriptSegment(
            id='s1', text='x', speaker='SPEAKER_00', speaker_id=0, is_user=True, start=0.0, end=400.0
        )
        segment_b = TranscriptSegment(
            id='s2', text='y', speaker='SPEAKER_01', speaker_id=1, is_user=False, start=400.0, end=800.0
        )
        conversation = SimpleNamespace(
            source=ConversationSource.omi,
            external_data={},
            transcript_segments=[segment, segment_b],
        )
        assert should_gather_meeting_context(conversation, None) is True

        quiet = SimpleNamespace(
            source=ConversationSource.omi,
            external_data={},
            transcript_segments=[
                TranscriptSegment(
                    id='s3', text='x', speaker='SPEAKER_00', speaker_id=0, is_user=True, start=0.0, end=10.0
                )
            ],
        )
        assert should_gather_meeting_context(quiet, None) is False
        assert should_gather_meeting_context(quiet, _context([MeetingParticipant(name='Ash')])) is True

        desktop_meeting = SimpleNamespace(
            source=ConversationSource.desktop,
            external_data={'conversation_role': 'meeting'},
            transcript_segments=[],
        )
        assert should_gather_meeting_context(desktop_meeting, None) is True

    def test_screen_text_lists_windows_first_and_strips_repeated_chrome(self, monkeypatch):
        import utils.conversations.meeting_context_pack as pack_module

        chrome = 'Ask Gemini • New Chrome available • nemotron-asr-streaming • Soniox Console'
        rows = [
            {
                'timestamp': '1',
                'windowTitle': 'Meet - dyo-jguo-jrw - Google Chrome - David (acme.com)',
                'appName': 'Google Chrome',
                'ocrText': f'{chrome} • Priya Raman • Boardy Boardman • David Zhang',
            },
            {
                'timestamp': '2',
                'windowTitle': '(7) Priya Raman | LinkedIn - High memory usage - 1.2 GB',
                'appName': 'Google Chrome',
                'ocrText': f'{chrome} • Founding Engineer @ Northwind AI',
            },
            {'timestamp': '3', 'windowTitle': 'x.com', 'appName': 'Google Chrome', 'ocrText': chrome},
            {
                'timestamp': '4',
                'windowTitle': '\u2068max carter\u2069 – (69165)',
                'appName': 'Telegram',
                'ocrText': 'max carter • i fell out of bed • private family thing',
            },
            {'timestamp': '5', 'windowTitle': 'Huge', 'appName': 'Google Chrome', 'ocrText': 'y' * 4000},
        ]
        monkeypatch.setattr(pack_module.screen_activity_db, 'get_screen_activity', lambda *a, **k: rows)
        conversation = SimpleNamespace(started_at=START, finished_at=START + timedelta(minutes=30))
        text = pack_module._gather_screen_text('uid', conversation)
        windows, _, on_screen = text.partition('On-screen text')
        # Distinct cleaned window titles come first; meeting codes and browser noise are gone.
        assert '- Google Chrome | Google Meet call' in windows
        assert '- Google Chrome | Priya Raman | LinkedIn' in windows
        assert 'dyo-jguo-jrw' not in windows and 'High memory usage' not in windows
        # Case-preserving residual OCR keeps names and products; chrome repeated across frames is stripped.
        assert 'Priya Raman' in on_screen and 'Northwind AI' in on_screen
        assert 'Soniox Console' not in on_screen
        # Private messaging OCR is never included, only the window title.
        assert 'fell out of bed' not in text
        assert 'Telegram | max carter' in windows
        assert len(text) <= pack_module.MAX_SCREEN_CHARACTERS

    def test_prior_meetings_person_id_match_and_query_bounds(self, monkeypatch):
        import utils.conversations.meeting_context_pack as pack_module

        calls = {}

        def fake_list_meetings(uid, **kwargs):
            calls['meetings'] = kwargs
            return []

        monkeypatch.setattr(pack_module.calendar_db, 'list_meetings', fake_list_meetings)
        records = [
            # Matches only via transcript-segment person_id — no names needed.
            {
                'id': 'old-1',
                'started_at': START - timedelta(days=10),
                'transcript_segments': [{'person_id': 'p-ash', 'text': 'x'}],
                'structured': {'title': 'Earlier sync', 'overview': 'roadmap talk'},
            },
            {'id': 'conv-x', 'transcript_segments': [{'person_id': 'p-ash'}]},  # current — excluded
            {'id': 'old-2', 'discarded': True, 'transcript_segments': [{'person_id': 'p-ash'}]},
            {'id': 'old-3', 'transcript_segments': [{'person_id': 'p-owner'}]},  # owner alone never matches
            {'id': 'old-4', 'transcript_segments': [{'person_id': 'p-other'}]},
        ]

        def fake_conversations(uid, **kwargs):
            calls['conversations'] = kwargs
            return records

        monkeypatch.setattr(pack_module.conversations_db, 'get_conversations_without_photos', fake_conversations)
        action_calls = []

        def fake_action_items(uid, **kwargs):
            action_calls.append(kwargs)
            return [{'description': f'item {i}'} for i in range(5)]

        monkeypatch.setattr(pack_module.action_items_db, 'get_action_items', fake_action_items)
        roster = _roster(
            [
                _entry('David', 'david@acme.com', kind='owner', person_id='p-owner'),
                _entry(None, None, person_id='p-ash'),
            ]
        )
        conversation = SimpleNamespace(started_at=START, id='conv-x')
        notes = pack_module._gather_prior_meetings('uid', conversation, roster, START, 'UTC')
        assert calls['meetings'] == {
            'start_date': START - timedelta(days=180),
            'end_date': START,
            'limit': 60,
        }
        assert calls['conversations'] == {
            'limit': 60,
            'start_date': START - timedelta(days=180),
            'end_date': START,
        }
        assert [note.title for note in notes] == ['Earlier sync']
        assert action_calls == [{'conversation_id': 'old-1', 'completed': False, 'limit': 3}]
        assert len(notes[0].open_items) == 3


class TestRichFailOpen:
    def test_normalizer_failure_returns_empty_roster_not_none(self, monkeypatch):
        import utils.conversations.meeting_notes_wiring as wiring

        def boom(*a, **k):
            raise ValueError('malformed people document with private details')

        monkeypatch.setattr(wiring, 'should_gather_meeting_context', lambda *a, **k: True)
        monkeypatch.setattr(wiring, 'load_people_documents', lambda uid: [])
        monkeypatch.setattr(wiring, 'resolve_owner_identity', lambda uid: ('David', ('david@acme.com',)))
        monkeypatch.setattr(wiring, 'normalize_meeting_participants', boom)
        conversation = SimpleNamespace(source=ConversationSource.omi, external_data={})
        roster, people_docs, desktop_capture = wiring._rich_meeting_roster('uid', conversation, None)
        # An empty roster — never None — keeps the strict rich speaker path.
        assert roster is not None
        assert roster.entries == ()
        assert people_docs == []
        assert desktop_capture is False

    def test_gather_gate_failure_preserves_desktop_capture(self, monkeypatch):
        import utils.conversations.meeting_notes_wiring as wiring

        def boom(*a, **k):
            raise RuntimeError('gate blew up')

        monkeypatch.setattr(wiring, 'should_gather_meeting_context', boom)
        conversation = SimpleNamespace(
            source=ConversationSource.desktop,
            external_data={'conversation_role': 'meeting'},
        )
        roster, _people_docs, desktop_capture = wiring._rich_meeting_roster('uid', conversation, None)
        assert roster is not None
        assert roster.entries == ()
        assert desktop_capture is True

    def test_context_block_failure_returns_none(self, monkeypatch):
        import utils.conversations.meeting_notes_wiring as wiring

        monkeypatch.setattr(
            wiring,
            'gather_meeting_context_pack',
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('pack exploded')),
        )
        roster = _roster([_entry('Ash Kalb', 'ash@fulcra.com')])
        assert (
            wiring._rich_meeting_context_block('uid', SimpleNamespace(), roster, [], 'UTC', include_screen_text=False)
            is None
        )
        monkeypatch.setattr(
            wiring,
            'gather_meeting_context_pack',
            lambda *a, **k: MeetingContextPack(goals=('g',)),
        )
        monkeypatch.setattr(
            wiring,
            'render_meeting_context_pack',
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('render exploded')),
        )
        assert (
            wiring._rich_meeting_context_block('uid', SimpleNamespace(), roster, [], 'UTC', include_screen_text=False)
            is None
        )

    def test_notes_call_path_survives_roster_and_pack_failures(self, monkeypatch):
        import contextlib

        import utils.conversations.meeting_notes_wiring as wiring
        import utils.conversations.process_conversation as pc
        from models.conversation_enums import ExternalIntegrationConversationSource
        from models.structured import Structured

        def boom(*a, **k):
            raise ValueError('malformed legacy data')

        monkeypatch.setattr(pc, '_conversation_notes_v2_enabled', lambda: True)
        monkeypatch.setattr(pc, '_meeting_notes_rich_context_enabled', lambda: True)
        monkeypatch.setattr(pc, '_meeting_notes_screen_text_context_enabled', lambda: False)
        monkeypatch.setattr(pc, '_proposes_task_candidates', lambda conversation: False)
        monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda uid: 'UTC')
        monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda uid: 'en')
        monkeypatch.setattr(pc, 'track_usage', lambda *a, **k: contextlib.nullcontext())
        monkeypatch.setattr(pc, '_fetch_dedup_candidates_for_query', lambda *a, **k: [])
        monkeypatch.setattr(pc, 'validate_structured_source_segment_ids', lambda *a, **k: None)
        monkeypatch.setattr(wiring, 'should_gather_meeting_context', lambda *a, **k: True)
        monkeypatch.setattr(wiring, 'load_people_documents', lambda uid: [])
        monkeypatch.setattr(wiring, 'resolve_owner_identity', lambda uid: ('David', ('david@acme.com',)))
        monkeypatch.setattr(wiring, 'normalize_meeting_participants', boom)
        monkeypatch.setattr(wiring, 'gather_meeting_context_pack', boom)

        captured = {}

        def fake_notes(prefix, **kwargs):
            captured['prefix'] = prefix
            captured['kwargs'] = kwargs
            return Structured()

        monkeypatch.setattr(pc, 'get_conversation_notes', fake_notes)
        conversation = SimpleNamespace(
            source=ConversationSource.external_integration,
            external_data={},
            text_source=ExternalIntegrationConversationSource.audio,
            text='[s1 0] hello everyone',
            started_at=START,
            id='conv-x',
            calendar_meeting_context=_context([MeetingParticipant(name='Ash Kalb', email='ash@fulcra.com')]),
        )
        structured, discarded = pc._get_structured('uid', 'en', conversation)
        assert structured is not None
        assert discarded is False
        kwargs = captured['kwargs']
        # get_conversation_notes still ran, with no background block and the
        # empty (strict) roster — rich mode stays on, unsafe legacy one-name
        # binding stays off.
        assert kwargs['meeting_context'] is None
        assert kwargs['rich_context_enabled'] is True
        roster = kwargs['roster']
        assert roster is not None
        assert roster.entries == ()
        assert '- Participants:' not in captured['prefix'].context
        assert 'PARTICIPANTS' not in captured['prefix'].context


def test_rich_prompt_anchors_still_match_legacy_wording():
    """The rich rewrite anchors on exact legacy text and only logs on drift; pin it here."""
    from utils.llm import meeting_notes_rich_prompts as rich
    from utils.llm.conversation_processing import _conversation_notes_static_instructions

    base = _conversation_notes_static_instructions('FORMAT')
    assert rich._LEGACY_NOTE_BODY_OPENING in base
    assert rich._LEGACY_SELECT_THREADS in base
    text = rich.rich_static_instructions('FORMAT', _conversation_notes_static_instructions)
    assert rich._RICH_NOTE_BODY_OPENING in text and rich._LEGACY_NOTE_BODY_OPENING not in text
    assert rich._RICH_SELECT_THREADS in text and rich._LEGACY_SELECT_THREADS not in text


def test_participant_names_corroborated_by_screen_background_are_kept():
    from models.structured import Participant, Structured
    from utils.llm.meeting_notes_validation import validate_rich_meeting_notes

    roster = normalize_meeting_participants(
        _context(
            [MeetingParticipant(email='someone@duck.com'), MeetingParticipant(name='Boardy Boardman')],
            title='Meet - abc-defg-hij',
            source='screen_activity',
            platform='Google Meet',
        ),
        ConversationSource.desktop,
        owner_name='David Zhang',
        owner_emails=['david@acme.com'],
        people=[],
    )
    structured = Structured(
        participants=[
            Participant(name='Priya Raman', role='Founding-engineer candidate', source='roster'),
            Participant(name='Invented Person', role='guess', source='transcript'),
        ]
    )
    background = 'BACKGROUND CONTEXT\nSCREEN ACTIVITY\nWindows open during the meeting:\n- Google Chrome | Priya Raman | LinkedIn'
    validated = validate_rich_meeting_notes(
        structured,
        transcript_body='hello there',
        roster=roster,
        has_background_context=True,
        background_body=background,
    )
    assert [p.name for p in validated.participants] == ['Priya Raman']
