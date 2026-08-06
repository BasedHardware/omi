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
from utils.paper.context import focus_blocks, screen_day_window
from utils.paper.render import render_text
from utils.paper.sources.gmail_source import _sender_name, exclusion_reason

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


@pytest.mark.parametrize(
    'stored',
    [
        '2026-08-02T02:32:46Z',  # the format the live account actually stores
        '2026-08-02T23:59:00Z',
        '2026-08-02 02:32:46.000',  # the format the db docstring claims
        '2026-08-02 23:59:59.999',
    ],
)
def test_the_screen_day_window_selects_real_stored_timestamps(stored):
    """Screen rows are filtered by string comparison, so the bounds must sort correctly.

    Formatting a day as `2026-08-02 23:59:59.999` puts the end bound *below*
    every `2026-08-02T...Z` row, because 'T' > ' '. A single-day query then
    returns nothing and the focus section looks like a day with no capture.
    Caught by running against the real account, where the day had 5,000 rows.
    """
    start, end = screen_day_window(date(2026, 8, 2))
    assert start <= stored <= end


@pytest.mark.parametrize('stored', ['2026-08-03T00:00:01Z', '2026-08-01T23:59:59Z', '2026-08-03 00:00:01.000'])
def test_the_screen_day_window_excludes_adjacent_days(stored):
    start, end = screen_day_window(date(2026, 8, 2))
    assert not (start <= stored <= end)


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
    assert exclusion_reason(message) == 'contains what looks like a one-time code or sign-in link'


# Real provider message shapes. Every one of these reached the model before the
# filter was rewritten: the credential check read `body`, but `parse_gmail_message`
# leaves `body` empty for HTML-only and multipart/related mail — the dominant
# transactional shapes — while the clustering prompt is handed `snippet`.
@pytest.mark.parametrize(
    'case,sender,subject,body,snippet',
    [
        ('code in snippet, innocent subject', 'hello@startup.com', 'Welcome aboard', '', '483920 Your login code.'),
        ('hyphenated code', 'feedback@slack.com', 'Slack confirmation code: 034-928', '', ''),
        ('code on its own line', 'a@microsoft.com', 'Your single-use code', 'Security code:\n\n7391042', ''),
        ('spaced code', 'noreply@email.apple.com', 'Notice', 'Your code is 483 920', ''),
        ('google G- code', 'no-reply@accounts.google.com', 'Notice', 'G-123 456 is your code', ''),
        ('brand between your and code', 'noreply@uber.com', "Here's your Uber code", '', ''),
        ('apple id code', 'noreply@email.apple.com', 'Your Apple ID code', '', ''),
        ('magic link', 'no-reply@substack.com', 'Sign in', 'https://x.co/sign-in?token=eyJhbGciOi', ''),
        ('login link subject', 'team@makenotion.com', 'Your Notion login link', '', ''),
        ('unusual sign-in', 'no-reply@accounts.google.com', 'Action required: unusual sign-in attempt', '', ''),
        ('confirm identity', 'no-reply@coinbase.com', "Confirm it's you", '', ''),
        ('reset instructions', 'no-reply@figma.com', 'Reset instructions', '', ''),
        ('recovery link', 'no-reply@vercel.com', 'Recovery link for your account', '', ''),
        ('bank sending subdomain', 'x@ealerts.bankofamerica.com', 'A notice', '', ''),
        ('wells fargo subdomain', 'alerts@notify.wellsfargo.com', 'Your available funds', '', ''),
        (
            'account ending + amount',
            'x@b.com',
            'A deposit',
            'A deposit of $4,812.55 to your account ending in 4021.',
            '',
        ),
        ('card ending', 'x@b.com', 'Purchase approved', '$529.99 charged to card ending in 8817', ''),
        ('routing number', 'billing@acme.com', 'Invoice INV-00421', 'routing 021000021 account 8829104471', ''),
        ('money sent', 'x@b.com', 'You sent $1,200.00 to Jane Doe', '', ''),
        ('card declined', 'info@mailer.netflix.com', "We couldn't process your card", '', ''),
    ],
)
def test_credentials_and_account_detail_never_reach_the_page(case, sender, subject, body, snippet):
    assert exclusion_reason({'from': sender, 'subject': subject, 'body': body, 'snippet': snippet}), case


def test_the_filter_reads_every_field_the_model_is_shown():
    """`body` alone was a no-op on the mail that matters.

    HTML-only and multipart/related messages parse to an empty body, so the
    credential check scanned nothing while the prompt received the snippet that
    carried the code.
    """
    from utils.paper.sources.gmail_source import scanned_text

    scanned = scanned_text({'subject': 'Hi', 'snippet': 'code 123456', 'body': ''})
    assert 'code 123456' in scanned


def test_automated_senders_are_excluded_by_address():
    assert exclusion_reason({'subject': 'Weekly digest', 'from': 'notifications@github.com', 'body': ''})


@pytest.mark.parametrize(
    'sender,subject',
    [
        # Every one of these was wrongly cut by a `noreply@` sender rule when the
        # filter was first run against a real inbox. Publications overwhelmingly
        # send bulk mail from unmonitored addresses; it is not a danger signal.
        ('noreply@news.bloomberg.com', 'Money Stuff: SpaceX Unlocks Tomorrow'),
        ('noreply@news.bloomberg.com', 'Gold is waking up to the Warsh Fed'),
        ('no-reply@m.higgsfield.ai', 'Higgsfield Global Film Festival'),
        ('access@interactive.wsj.com', 'Takeaways From the Big Election Night'),
        ('team@info.digitalocean.com', 'Open-weight models ramp up performance'),
        ('billg@gatesnotes.com', 'Proof of progress'),
    ],
)
def test_publications_sending_from_noreply_are_not_cut(sender, subject):
    assert exclusion_reason({'from': sender, 'subject': subject, 'body': ''}) is None


@pytest.mark.parametrize(
    'sender,expected',
    [
        ('noreply@news.bloomberg.com', 'Bloomberg'),
        ('access@interactive.wsj.com', 'WSJ'),
        ('team@info.digitalocean.com', 'DigitalOcean'),
        ('investors@ycombinator.com', 'Y Combinator'),
        ('billg@gatesnotes.com', 'Gates Notes'),
        ('no-reply@m.higgsfield.ai', 'Higgsfield'),
        ('newsletter@tesla.com', 'Tesla'),
        ('The Browser <hi@thebrowser.com>', 'The Browser'),
    ],
)
def test_a_publication_is_named_by_its_domain_not_its_mailbox(sender, expected):
    """`noreply@news.bloomberg.com` is Bloomberg, not "noreply".

    The sources line is what lets a reader check a story, so a story credited to
    "noreply" or "team" is unverifiable in exactly the way the model forbids.
    """
    assert _sender_name(sender) == expected


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
