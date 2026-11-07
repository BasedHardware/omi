"""Home row contract: server-classified home_step on list reads (hermetic)."""

from datetime import datetime, timedelta, timezone

import pytest

from models.conversation import Conversation
from utils.conversations import home_step, home_titles

NOW = datetime.now(timezone.utc)


def row(**updates):
    base = {
        'id': 'a',
        'status': 'completed',
        'created_at': NOW - timedelta(hours=1),
        'started_at': NOW - timedelta(hours=1),
        'finished_at': NOW - timedelta(minutes=50),
        'structured': {'title': 'Lunch with the team', 'overview': 'We talked.'},
    }
    base.update(updates)
    return base


def minimum(title='Mm-hmm.', **updates):
    """A stand-in title on a row that still owes its summary."""
    updates.setdefault('summary_due_at', NOW.timestamp())
    return row(structured={'title': title, 'overview': '', 'title_provenance': 'server_minimum'}, **updates)


@pytest.mark.parametrize(
    'data,expected',
    [
        (row(), 'ready'),
        (minimum(), 'writing_notes'),
        (minimum('Recording · 9:38 AM'), 'writing_notes'),
        (minimum(summary_blocked_reason='content_below_floor'), 'noise'),
        (minimum(user_title='Mine'), 'ready'),
        (minimum(starred=True, summary_blocked_reason='content_below_floor'), 'ready'),
        (minimum(finalization_status='dead_letter'), 'failed'),
        (minimum(summary_retryable=True), 'failed'),
        (row(structured={'title': '', 'overview': ''}), 'transcribing'),
        (row(status='processing', structured={'title': '', 'overview': ''}), 'transcribing'),
        (row(status='processing'), 'writing_notes'),
        (row(status='in_progress'), None),
    ],
)
def test_classify(data, expected):
    assert home_step.classify(data) == expected


def test_restamped_finished_title_is_never_processing_forever():
    """GLM P1 on #24732: neutralize re-stamps server_minimum on read for finished rows."""
    settled = minimum('Thank you.', summary_due_at=None)
    assert home_step.classify(settled) == 'noise', 'a final stand-in title is noise, not Processing'
    delivered = minimum('Thank you.', summary_completed_at=NOW.timestamp())
    assert home_step.classify(delivered) == 'ready'
    output = minimum('Thank you.', summary_output_present=True)
    assert home_step.classify(output) == 'ready'
    projected = home_titles.neutralize_minimum_title(
        row(
            started_at=NOW - timedelta(seconds=40),
            finished_at=NOW,
            transcript_segments=[{'text': 'Thank you.'}],
            structured={'title': 'Thank you.', 'overview': 'A short thanks.'},
        )
    )
    assert projected['structured']['title_provenance'] == 'server_minimum'
    assert home_step.classify(projected) == 'noise'
    assert home_step.classify(dict(projected, summary_output_present=True)) == 'ready'


@pytest.mark.parametrize(
    'title,seconds',
    [('Yeah.', 0), ("We didn't Know.", 28 * 60), ('Recording · 3:37 PM', 58), ('Recording · 9:21 AM', 222)],
)
def test_davids_settled_junk_rows_are_noise(title, seconds):
    """2026-11-06 screenshots: after the drain these rows owe nothing, so they leave Home."""
    start = NOW - timedelta(hours=20)
    data = minimum(title, started_at=start, finished_at=start + timedelta(seconds=seconds), summary_due_at=None)
    assert home_step.classify(home_titles.neutralize_minimum_title(data)) == 'noise'


@pytest.mark.parametrize('age_hours,expected', [(1, 'transcribing'), (3, 'failed')])
def test_unstamped_empty_capture_cannot_stay_processing_forever(age_hours, expected):
    finished = NOW - timedelta(hours=age_hours)
    data = row(
        structured={'title': '', 'overview': ''}, started_at=finished - timedelta(seconds=11), finished_at=finished
    )
    assert home_step.classify(data) == expected


def test_empty_blocked_minimum_is_noise():
    from utils.conversations.summary_delivery import EMPTY_BLOCKED_REASONS

    reason = sorted(EMPTY_BLOCKED_REASONS)[0]
    assert home_step.classify(minimum('Recording · 9:38 AM', summary_blocked_reason=reason)) == 'noise'


@pytest.mark.parametrize('hours,expected', [(1, 'transcribing'), (-1, 'failed')])
def test_stamped_batch_capture_follows_its_deadline(hours, expected):
    data = row(
        structured={'title': '', 'overview': ''},
        record_lane_owner='batch_sync_v1',
        home_transcription_deadline_at=NOW + timedelta(hours=hours),
    )
    assert home_step.classify(data) == expected


@pytest.mark.parametrize('value', ['off', 'false', '0', 'no'])
def test_kill_switch_omits_the_field(monkeypatch, value):
    monkeypatch.setenv('HOME_STEP_PROJECTION', value)
    assert 'home_step' not in home_step.project(minimum())


def test_wire_carries_home_step_only_when_set():
    with_step = Conversation.model_validate(home_step.project(minimum()) | {'id': 'a'}).model_dump(mode='json')
    assert with_step['home_step'] == 'writing_notes'
    without = Conversation.model_validate(minimum() | {'id': 'a'}).model_dump(mode='json')
    assert 'home_step' not in without


def test_neutral_title_uses_the_users_zone_and_falls_back_to_utc():
    start = datetime(2026, 11, 5, 9, 38, tzinfo=timezone.utc)
    data = minimum('Yeah.', started_at=start, finished_at=start + timedelta(seconds=30))
    local = home_titles.neutralize_minimum_title(data, tz_name_provider=lambda: 'Asia/Ho_Chi_Minh')
    assert local['structured']['title'] == 'Recording · 4:38 PM'
    assert home_titles.neutralize_minimum_title(data)['structured']['title'] == 'Recording · 9:38 AM'

    def broken():
        raise RuntimeError('firestore down')

    assert home_titles.neutralize_minimum_title(data, tz_name_provider=broken)['structured']['title'] == (
        'Recording · 9:38 AM'
    )


def test_summary_owed_echo_titles_are_neutral_whatever_their_length():
    start = NOW - timedelta(hours=5)
    data = minimum(
        'Mm-hmm.', started_at=start, finished_at=start + timedelta(minutes=4), summary_due_at=NOW.timestamp()
    )
    assert home_titles.neutralize_minimum_title(data)['structured']['title'].startswith('Recording · ')
    settled = dict(data, summary_completed_at=NOW.timestamp())
    assert home_titles.neutralize_minimum_title(settled)['structured']['title'] == 'Mm-hmm.'
