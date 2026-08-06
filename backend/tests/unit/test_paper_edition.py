"""Behavioural cover for the edition engine.

These run the real functions. The two things worth guarding hardest are the
ones that fail invisibly: focus time that silently inflates, and the Gmail
exclusion list that silently lets a credential onto a printable page.
"""

import json
import urllib.parse
from datetime import date, datetime, timezone

import pytest

from models.paper import (
    Claim,
    Edition,
    ForYou,
    Interest,
    InterestProfile,
    NewsletterStory,
    Photo,
    Provenance,
    SourceRef,
    Yesterday,
)
from utils.paper.context import focus_blocks, screen_day_window
from utils.paper.render import render_text
from utils.paper.sources import hackernews
from utils.paper.sources.gmail_source import _sender_name, exclusion_reason
from utils.paper.sources.hackernews import fetch_buzz

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


# ---------------------------------------------------------------------------
# Hacker News — the buzz source. Hermetic: the HTTP layer is faked, and a test
# that reaches the network is a bug in the test.
# ---------------------------------------------------------------------------

DAY = date(2026, 8, 5)


def _stamp(when: date, hour: int = 12) -> int:
    """Unix seconds for a wall time, built here rather than borrowed from the module."""
    return int(datetime(when.year, when.month, when.day, hour, tzinfo=timezone.utc).timestamp())


def _hit(object_id, title, points, when=DAY, url='https://example.com/story'):
    return {
        'objectID': object_id,
        'title': title,
        'points': points,
        'created_at_i': _stamp(when),
        'url': url,
    }


class _HNResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _fake_hn(monkeypatch, responder):
    """Fake the HTTP layer. `responder(params)` returns hits, or raises to fail a query."""
    calls = []

    def fake_urlopen(request, *_args, **_kwargs):
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(request.full_url).query))
        calls.append(params)
        return _HNResponse({'hits': responder(params)})

    monkeypatch.setattr(hackernews.urllib.request, 'urlopen', fake_urlopen)
    return calls


def _profile(*topics):
    return InterestProfile(interests=[Interest(topic=topic, evidence='worked on it') for topic in topics])


def _is_topic_query(params):
    return bool(params.get('query'))


def _is_front_page(params):
    return params.get('tags') == 'story' and not params.get('query')


def test_a_story_seen_twice_keeps_its_higher_scoring_copy(monkeypatch):
    """The same story comes back from several queries; the page must rank it once, at its real score.

    Keeping the first copy seen would file a 90-point story at the 10 points the
    narrow topic query happened to report, and bury it under smaller news.
    """

    def responder(params):
        if _is_topic_query(params):
            return [_hit('1', 'Memory retrieval at scale', points=10)]
        if _is_front_page(params):
            return [_hit('1', 'Memory retrieval at scale', points=90), _hit('2', 'A memory of Unix', points=50)]
        return []

    _fake_hn(monkeypatch, responder)
    lines, health = fetch_buzz(_profile('memory'), DAY)

    assert [line.claim.text for line in lines] == ['Memory retrieval at scale', 'A memory of Unix']
    assert health.kept == 2


@pytest.mark.parametrize(
    'case,when',
    [
        ('older than the window', date(2026, 7, 30)),
        ('the day the window opens minus one', date(2026, 8, 1)),
        ('filed after the edition day', date(2026, 8, 6)),
    ],
)
def test_a_story_outside_the_three_day_window_is_never_printed(monkeypatch, case, when):
    """Yesterday's paper printing last month's story is the failure that makes a brief worthless."""

    def responder(params):
        if _is_front_page(params):
            return [_hit('old', 'Stale news', points=400, when=when), _hit('new', 'Fresh news', points=60)]
        return []

    _fake_hn(monkeypatch, responder)
    lines, health = fetch_buzz(_profile('memory'), DAY)

    assert [line.claim.text for line in lines] == ['Fresh news'], case
    assert health.fetched == 2  # both were read; only one was kept


def test_the_window_comes_from_the_day_argument_not_the_clock(monkeypatch):
    """A run for a past date must fetch that date's buzz, or the source cannot be tested at all."""
    calls = _fake_hn(monkeypatch, lambda params: [])
    fetch_buzz(_profile('memory'), date(2021, 3, 15))

    floors = {int(params['numericFilters'].split('created_at_i>')[1]) for params in calls}
    assert floors == {_stamp(date(2021, 3, 12), hour=0)}


def test_every_query_failing_reports_the_source_as_down(monkeypatch):
    """An outage must not be printed as a quiet day — that is a false claim about the reader's field."""

    def responder(params):
        raise OSError('hn.algolia.com unreachable')

    _fake_hn(monkeypatch, responder)
    lines, health = fetch_buzz(_profile('memory', 'agents'), DAY)

    assert lines == []
    assert health.ok is False
    assert 'failed' in health.note


def test_a_quiet_day_is_reported_healthy_and_says_so(monkeypatch):
    """Nothing cleared the bar is a real answer, and must read differently from an outage."""
    _fake_hn(monkeypatch, lambda params: [])
    lines, health = fetch_buzz(_profile('memory'), DAY)

    assert lines == []
    assert health.ok is True
    assert health.note and 'failed' not in health.note


def test_one_failed_query_does_not_cost_the_others(monkeypatch):
    """A single flaky topic search must not blank the section."""

    def responder(params):
        if _is_topic_query(params):
            raise TimeoutError('slow')
        if _is_front_page(params):
            return [_hit('1', 'Something large happened', points=300)]
        return []

    _fake_hn(monkeypatch, responder)
    lines, health = fetch_buzz(_profile('memory'), DAY)

    assert [line.claim.text for line in lines] == ['Something large happened']
    assert health.ok is True
    assert health.note == '1/3 queries failed'


def test_every_buzz_line_is_printable_and_keeps_its_title_verbatim(monkeypatch):
    """No source, no print. The permalink is also what makes the title checkable."""

    def responder(params):
        if _is_front_page(params):
            return [
                _hit(
                    '49199308',
                    'A handful of cities have replaced Flock with Axon',
                    points=91,
                    url='https://www.404media.co/cities-are-ditching-flock/',
                )
            ]
        return []

    _fake_hn(monkeypatch, responder)
    lines, _ = fetch_buzz(_profile('surveillance'), DAY)

    (line,) = lines
    assert line.claim.is_printable
    assert line.claim.text == 'A handful of cities have replaced Flock with Axon'
    assert line.claim.provenance is Provenance.REPORTED
    assert line.category == 'front page'
    assert [(source.name, source.url) for source in line.claim.sources] == [
        ('Hacker News', 'https://news.ycombinator.com/item?id=49199308'),
        ('404media.co', 'https://www.404media.co/cities-are-ditching-flock/'),
    ]


def test_a_text_post_with_no_link_still_carries_its_source(monkeypatch):
    """Ask HN and Tell HN stories come back with `url: null`; they still have a permalink."""

    def responder(params):
        if _is_front_page(params):
            return [dict(_hit('49200389', 'Tell HN: Lost over 20yrs of Yahoo Emails', points=120), url=None)]
        return []

    _fake_hn(monkeypatch, responder)
    lines, _ = fetch_buzz(_profile('email'), DAY)

    (line,) = lines
    assert line.claim.is_printable
    assert [source.name for source in line.claim.sources] == ['Hacker News']


def test_a_fuzzy_search_hit_is_not_filed_under_an_interest(monkeypatch):
    """Algolia is typo-tolerant, so `query=rust` really does return "AI **Just** Created Viruses".

    Observed against the live API. Printing that under the reader's rust interest
    claims a connection to their work that is not there.
    """

    def responder(params):
        if params.get('query') == 'rust':
            return [
                _hit('1', 'AI Just Created Viruses Not Found in Nature', points=14),
                _hit('2', 'Rust 2.0 lands with a new borrow checker', points=8),
            ]
        return []

    _fake_hn(monkeypatch, responder)
    lines, _ = fetch_buzz(_profile('rust'), DAY)

    assert [(line.category, line.claim.text) for line in lines] == [
        ('rust', 'Rust 2.0 lands with a new borrow checker')
    ]


def test_the_section_stays_bounded(monkeypatch):
    """A newspaper page is finite; the highest-scoring stories are the ones that fit."""

    def responder(params):
        if _is_front_page(params):
            return [_hit(str(n), f'Story {n}', points=n) for n in range(1, 31)]
        return []

    _fake_hn(monkeypatch, responder)
    lines, health = fetch_buzz(_profile('memory'), DAY, limit=3)

    assert [line.claim.text for line in lines] == ['Story 30', 'Story 29', 'Story 28']
    assert health.kept == 3


def test_a_reader_with_no_learned_interests_still_gets_the_general_buzz(monkeypatch):
    """The general and Show HN queries need no profile, so a new account is not a blank page."""

    def responder(params):
        if params.get('tags') == 'show_hn':
            return [_hit('1', 'Show HN: A tool for reading papers', points=40)]
        return []

    calls = _fake_hn(monkeypatch, responder)
    lines, health = fetch_buzz(InterestProfile(), DAY)

    assert len(calls) == 2  # show_hn + front page, no topic searches
    assert [(line.category, line.claim.text) for line in lines] == [('show hn', 'Show HN: A tool for reading papers')]
    assert health.ok is True


# ---------------------------------------------------------------------------
# The timeline — a position on it is a claim about when
# ---------------------------------------------------------------------------


def _conversation(title, started, finished=''):
    return {'structured': {'title': title}, 'started_at': started, 'finished_at': finished}


def test_a_session_that_never_closed_is_not_counted_as_its_length():
    """A real day held one 12h56m "conversation" running 05:38 to 18:35.

    It was 67% of the day's recorded total, so the headline figure read 19h and
    every genuine session was buried under it. It keeps its place on the day,
    because it really did start then, but its length is not a measurement.
    """
    from utils.paper.context import build_timeline

    entries = build_timeline(
        [
            _conversation('Left running', '2026-08-05T05:38:00Z', '2026-08-05T18:35:00Z'),
            _conversation('A real talk', '2026-08-05T00:11:00Z', '2026-08-05T01:35:00Z'),
        ]
    )
    left_open = next(e for e in entries if e.label == 'Left running')
    real = next(e for e in entries if e.label == 'A real talk')

    assert left_open.unbounded and left_open.minutes == 0
    assert not real.unbounded and real.minutes == 84
    assert left_open.start_minute == 5 * 60 + 38  # still placed on the day


def test_the_recorded_total_excludes_unclosed_sessions():
    from models.paper import TimelineEntry, Yesterday

    yesterday = Yesterday(
        timeline=[
            TimelineEntry(label='real', start='2026-08-05T09:00:00Z', minutes=84),
            TimelineEntry(label='open', start='2026-08-05T05:38:00Z', minutes=0, unbounded=True),
        ]
    )
    assert yesterday.recorded_minutes == 84
    assert yesterday.unbounded_sessions == 1


def test_a_conversation_with_no_usable_start_is_left_off_the_timeline():
    """Better absent than placed somewhere plausible."""
    from utils.paper.context import build_timeline

    entries = build_timeline([_conversation('No stamp', ''), _conversation('Real', '2026-08-05T09:00:00Z')])
    assert [e.label for e in entries] == ['Real']
