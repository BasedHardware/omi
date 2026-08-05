"""Behavioural cover for the edition engine.

These run the real functions. The two things worth guarding hardest are the
ones that fail invisibly: focus time that silently inflates, and the Gmail
exclusion list that silently lets a credential onto a printable page.
"""

from datetime import date

import pytest

from models.paper import (
    Claim,
    Edition,
    ForYou,
    Interest,
    InterestProfile,
    NewsletterStory,
    Photo,
    SourceRef,
    Yesterday,
)
from utils.paper.context import focus_blocks
from utils.paper.render import render_text
from utils.paper.sources.gmail_source import exclusion_reason

# ---------------------------------------------------------------------------
# Focus time — measured, not assumed
# ---------------------------------------------------------------------------


def _sample(stamp: str, app: str, title: str = ''):
    return {'timestamp': stamp, 'appName': app, 'windowTitle': title}


def test_focus_time_comes_from_real_gaps_between_samples():
    blocks = focus_blocks(
        [
            _sample('2026-08-04 09:00:00.000', 'Cursor'),
            _sample('2026-08-04 09:03:00.000', 'Cursor'),
            _sample('2026-08-04 09:06:00.000', 'Cursor'),
            _sample('2026-08-04 09:09:00.000', 'Cursor'),
        ]
    )
    assert [(b.label, b.minutes) for b in blocks] == [('Cursor', 9)]


def test_overnight_gap_cannot_inflate_focus_time():
    """A 14-hour gap between samples must contribute the cap, not 14 hours.

    This is the bug that makes a focus number untrustworthy: leave the machine
    on overnight and one app appears to have been used all night.
    """
    blocks = focus_blocks(
        [
            _sample('2026-08-04 09:00:00.000', 'Cursor'),
            _sample('2026-08-04 23:00:00.000', 'Cursor'),
            _sample('2026-08-04 23:06:00.000', 'Cursor'),
        ]
    )
    assert blocks[0].minutes == 10  # 5 (capped) + 5 (capped)


def test_apps_touched_briefly_are_not_focus():
    blocks = focus_blocks(
        [
            _sample('2026-08-04 09:00:00.000', 'Mail'),
            _sample('2026-08-04 09:01:00.000', 'Cursor'),
            _sample('2026-08-04 09:30:00.000', 'Cursor'),
        ]
    )
    assert [b.label for b in blocks] == ['Cursor']


def test_unparseable_timestamps_are_skipped_not_fatal():
    blocks = focus_blocks(
        [
            _sample('not-a-date', 'Cursor'),
            _sample('2026-08-04 09:00:00.000', 'Slack'),
            _sample('2026-08-04 09:20:00.000', 'Slack'),
        ]
    )
    assert [b.label for b in blocks] == ['Slack']


# ---------------------------------------------------------------------------
# Gmail exclusions — the security rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'subject',
    [
        'Your verification code is 448213',
        'Sign-in code for your account',
        'Reset your password',
        'Your receipt from Uber',
        'Payment failed for your subscription',
        'Your August account statement is ready',
        'Build failed on main',
        'Invitation: Standup @ Wed Aug 5',
    ],
)
def test_dangerous_and_useless_mail_never_reaches_the_page(subject):
    assert exclusion_reason({'subject': subject, 'from': 'x@example.com', 'body': ''})


def test_a_code_in_the_body_is_caught_even_with_an_innocent_subject():
    """The subject is attacker-controlled shape; the body is where the code is."""
    message = {
        'subject': 'Welcome aboard',
        'from': 'hello@startup.com',
        'body': 'Thanks for joining. Your code is 903114 and expires in 10 minutes.',
    }
    assert exclusion_reason(message) == 'contains what looks like a one-time code'


def test_automated_senders_are_excluded_by_address():
    assert exclusion_reason({'subject': 'Weekly digest', 'from': 'notifications@github.com', 'body': ''})


def test_a_real_newsletter_survives_the_filter():
    message = {
        'subject': 'The pace of memory research is picking up',
        'from': 'Import AI <jack@importai.net>',
        'body': 'This week: three papers on long-horizon retrieval and what they change.',
    }
    assert exclusion_reason(message) is None


# ---------------------------------------------------------------------------
# Grounding rules — nothing prints without something behind it
# ---------------------------------------------------------------------------


def test_a_newsletter_story_with_no_publication_is_not_printable():
    assert not NewsletterStory(summary='Something happened.').is_printable
    assert NewsletterStory(summary='Something happened.', sources=[SourceRef(name='Stratechery')]).is_printable


def test_a_photo_without_a_real_moment_behind_it_is_not_printable():
    """An image with no moment is decoration, and decoration presented as memory is a lie."""
    assert not Photo(image_b64='aGk=').is_printable
    assert not Photo(moment='walked to the river').is_printable
    assert Photo(moment='walked to the river', image_b64='aGk=').is_printable


def test_a_claim_with_no_source_is_not_printable():
    assert not Claim(text='Revenue tripled.').is_printable
    assert Claim(text='Revenue tripled.', sources=[SourceRef(name='The Information')]).is_printable


def test_a_profile_with_no_grounded_interests_is_unusable():
    """Callers must not rank against an empty rubric and call the result personal."""
    assert not InterestProfile(thesis='Building things').is_usable
    assert InterestProfile(interests=[Interest(topic='memory retrieval', evidence='asked about it 4 days')]).is_usable


# ---------------------------------------------------------------------------
# The page stays finite
# ---------------------------------------------------------------------------


def test_plaintext_never_exceeds_the_printer_column_width():
    """Including headers built from user data, which is where wrapping gets skipped."""
    edition = Edition(date='2026-08-05', issue_number=7)
    edition.yesterday = Yesterday(
        headline='A very long headline that would run past the column width of a receipt printer',
        story='S' * 400,
        decisions=['D' * 200],
    )
    edition.newsletters = [
        NewsletterStory(
            summary='N' * 300,
            sources=[SourceRef(name='A Publication With A Notably Long Name')],
        )
    ]
    text = render_text(edition, reader_name='Bartholomew Featherstonehaugh-Vansittart')
    assert text.splitlines()
    assert not [line for line in text.splitlines() if len(line) > 42]


def test_an_empty_edition_reports_itself_empty():
    assert Edition(date='2026-08-05').is_empty


def test_an_edition_with_only_a_photo_is_not_empty():
    edition = Edition(date='2026-08-05')
    edition.photo = Photo(moment='the walk home', image_b64='aGk=')
    assert not edition.is_empty


def test_degraded_sources_are_surfaced_not_swallowed():
    """A paper that has quietly had no Gmail for a fortnight must say so."""
    from models.paper import SourceHealth

    edition = Edition(date='2026-08-05')
    edition.source_health = [
        SourceHealth(source='gmail', ok=False, note='token expired'),
        SourceHealth(source='calendar', ok=True, kept=3),
    ]
    assert [health.source for health in edition.degraded_sources] == ['gmail']
    assert 'gmail unavailable' in render_text(edition)


def test_for_you_reports_empty_when_nothing_cleared_the_bar():
    assert ForYou().is_empty
