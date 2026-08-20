"""Conferencing-OCR identity extraction, pinned to real captured OCR.

The first version of this extractor scanned every OCR line and accepted anything
shaped like a short capitalised phrase. Run against the real screenshots for
conversation ff8b9998 (2026-08-18 19:29-19:58 UTC, a Google Meet call in a Chrome
tab) it produced twelve "participants":

    EQ, Meet, Switch account, Omi Monitor, ANX, Spud, David Zhang,
    Coinflow Portal, Spud pay, Om, Manage access, Blocked users

Only `David Zhang` is a person; the rest is the browser tab strip. Injecting
phantom participants into the summarization prompt is worse than passing no
context at all, because the model then attributes statements to people who were
never in the room.

The real identity was in the same OCR the whole time, in the Meet pre-join card
and in email addresses. The fixtures below are copied verbatim from that store
(`screenshots.ocrText`); the tests never read the database.

Ground truth for this meeting, independently corroborated by Granola's own header
for the same call (`ash@fulcradynamics.com, Boardy`): Ash Kalb, Boardy Boardman,
and the user David Zhang.
"""

from datetime import datetime, timezone

import pytest

from utils.conversations.meeting_context import (
    context_from_screen_activity,
    participants_from_ocr,
)

CONVERSATION_START = datetime(2026, 8, 18, 19, 29, 39, tzinfo=timezone.utc)
CONVERSATION_END = datetime(2026, 8, 18, 19, 58, 23, tzinfo=timezone.utc)

# Verbatim OCR of the 19:30:04 screenshot: a full-desktop capture whose top half is
# the Chrome tab strip / bookmarks bar and whose bottom half is the Meet pre-join card.
PRE_JOIN_OCR = """EQ
→
meet.google.com/amc-iajq-asx?authuser=david%40scalingforever.com
*
New ® • | Ask Gemini
@ Work
%
Meet
david@scalingforever.com
Switch account
Omi Monitor
Dashboards - Grafana
MacOS • Dashboards • Post
Usage - OpenAl API
Cost | Claude Platform
Sign In | Sentry
Cursor - The best way to col
ANX
Spud
David Zhang
Keys & Tokens | Coolify
spudpay-dev-01 dev-box ge
Log in | Brale
Coinflow Portal
Spud pay
• Security Advisories • BasedHa
Om
omi main: Omi Summer - Airta
Pull requests • BasedHardware
WY LLC Registration - Google
Spud pay
* Mercury | Banking for Startups
• Manage access
• Blocked users
gcloud CLI Remote Login
Activation Rate YTD
Meet - amc-iaja-asx
Ready to join?
Ash Kalb and Boardy Boardman are in this call
This call is open to anyone
son now
Other ways to join v
• MacBook Air ....
4) MacBook Air ...
•i MacBook Air ... ~
* Backgrounds... -
Gemini will analyze your conversation via temporary access to meeting content. The meeting host can turn it
off. Learn more"""

# Verbatim fragments from later in-call frames: participant tiles with Meet's
# trailing decorations, the chat panel, and the roster panel's email addresses.
IN_CALL_OCR = """Meet with...
David Zhang + Ash Kalb - Al Conte:
Ash Kalb 3:44PM
Boardy Boardman
Ash Kalb (Presenting, annotating)
boardy@boardy.ai
(boardy@boardy.ai)
ash@fulcradynamics.com"""

# Every junk "participant" the previous extractor emitted for this window.
JUNK_NAMES = {
    'EQ',
    'Meet',
    'Switch account',
    'Omi Monitor',
    'ANX',
    'Spud',
    'Coinflow Portal',
    'Spud pay',
    'Om',
    'Manage access',
    'Blocked users',
}


def _rows(*texts: str) -> list[dict[str, str]]:
    return [{'appName': 'Google Chrome', 'windowTitle': 'Meet - amc-iajq-asx', 'ocrText': text} for text in texts]


class TestRealCaptureFf8b9998:
    def test_pre_join_roster_yields_the_actual_participants(self):
        participants = participants_from_ocr([PRE_JOIN_OCR])
        names = [p.name for p in participants if p.name]

        assert 'Ash Kalb' in names
        assert 'Boardy Boardman' in names

    def test_no_tab_strip_text_is_ever_emitted_as_a_participant(self):
        participants = participants_from_ocr([PRE_JOIN_OCR, IN_CALL_OCR])
        names = {p.name for p in participants if p.name}

        assert not (names & JUNK_NAMES), f'tab-strip text leaked into participants: {sorted(names & JUNK_NAMES)}'

    def test_full_window_produces_names_with_their_email_addresses(self):
        context = context_from_screen_activity(
            _rows(PRE_JOIN_OCR, IN_CALL_OCR),
            started_at=CONVERSATION_START,
            finished_at=CONVERSATION_END,
        )

        assert context is not None
        by_name = {p.name: p.email for p in context.participants if p.name}
        assert by_name.get('Ash Kalb') == 'ash@fulcradynamics.com'
        assert by_name.get('Boardy Boardman') == 'boardy@boardy.ai'
        # The user himself is corroborated by his own signed-in address.
        assert by_name.get('David Zhang') == 'david@scalingforever.com'
        assert not (set(by_name) & JUNK_NAMES)
        assert context.calendar_source == 'screen_activity'
        assert context.platform == 'Google Chrome'

    def test_the_roster_frame_is_reached_even_when_it_is_not_first(self):
        # The 12k character budget used to be spent on whichever full-desktop frames
        # came first chronologically, so the pre-join card could fall outside it.
        filler = _rows(*(['meet.google.com/amc-iajq-asx\nDashboards - Grafana\n' + 'x' * 4000] * 8))
        context = context_from_screen_activity(
            filler + _rows(PRE_JOIN_OCR),
            started_at=CONVERSATION_START,
            finished_at=CONVERSATION_END,
        )

        assert context is not None
        assert 'Ash Kalb' in {p.name for p in context.participants}


class TestRosterPatterns:
    @pytest.mark.parametrize(
        'line,expected',
        [
            ('Ash Kalb and Boardy Boardman are in this call', ['Ash Kalb', 'Boardy Boardman']),
            ('Ash Kalb is in this call', ['Ash Kalb']),
            (
                'Ash Kalb, Boardy Boardman and David Zhang are in this call',
                ['Ash Kalb', 'Boardy Boardman', 'David Zhang'],
            ),
            ('Meet with Ash Kalb', ['Ash Kalb']),
            ('Boardy Boardman has joined', ['Boardy Boardman']),
            ('In call with Ash Kalb', ['Ash Kalb']),
        ],
    )
    def test_known_conferencing_sentences_are_parsed(self, line, expected):
        assert [p.name for p in participants_from_ocr([line])] == expected

    def test_roster_sentence_does_not_absorb_ui_words(self):
        # "This call is open to anyone" sits directly under the roster line.
        names = [p.name for p in participants_from_ocr(['This call is open to anyone']) if p.name]
        assert names == []


class TestPrecisionFirst:
    def test_a_bare_capitalised_line_is_not_a_participant(self):
        # This is exactly the shape that produced "Coinflow Portal" and "Blocked users".
        assert participants_from_ocr(['Coinflow Portal\nBlocked users\nOmi Monitor\nSpud pay']) == []

    def test_a_name_line_is_accepted_once_an_email_corroborates_it(self):
        participants = participants_from_ocr(['Boardy Boardman\nCoinflow Portal\nboardy@boardy.ai'])
        assert [(p.name, p.email) for p in participants] == [('Boardy Boardman', 'boardy@boardy.ai')]

    def test_a_dotted_local_part_corroborates_either_name_token(self):
        participants = participants_from_ocr(['Ash Kalb\nash.kalb@fulcradynamics.com'])
        assert [(p.name, p.email) for p in participants] == [('Ash Kalb', 'ash.kalb@fulcradynamics.com')]

    def test_an_uncorroborated_email_is_still_emitted_without_a_name(self):
        participants = participants_from_ocr(['someone@example.com'])
        assert [(p.name, p.email) for p in participants] == [(None, 'someone@example.com')]

    def test_tile_decorations_are_stripped_before_corroboration(self):
        participants = participants_from_ocr(
            ['Ash Kalb 3:44PM\nAsh Kalb (Presenting, annotating)\nash@fulcradynamics.com']
        )
        assert [p.name for p in participants] == ['Ash Kalb']

    def test_nothing_corroborated_means_no_context_rather_than_a_bare_title(self):
        context = context_from_screen_activity(
            _rows('Dashboards - Grafana\nCoinflow Portal\nBlocked users'),
            started_at=CONVERSATION_START,
            finished_at=CONVERSATION_END,
        )
        assert context is None

    def test_no_conferencing_rows_means_no_context(self):
        context = context_from_screen_activity(
            [{'appName': 'Cursor', 'windowTitle': 'notes.py', 'ocrText': 'Ash Kalb is in this call'}],
            started_at=CONVERSATION_START,
            finished_at=CONVERSATION_END,
        )
        assert context is None

    def test_participants_are_capped(self):
        roster = ', '.join(f'Person Number{index}' for index in range(20)) + ' are in this call'
        assert len(participants_from_ocr([roster])) <= 12
