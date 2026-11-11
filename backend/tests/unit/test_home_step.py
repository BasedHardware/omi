"""Home row contract: server-classified home_step on list reads (hermetic)."""

from datetime import datetime, timedelta, timezone

import pytest

from models.conversation import Conversation
from utils.conversations import home_step, home_titles
from utils.conversations.summary_delivery import EMPTY_BLOCKED_REASONS

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


def test_row_level_projection_provenance_is_writing_notes_without_structured_provenance():
    stamped = row(
        structured={'title': '', 'overview': ''},
        summary_title_provenance='server_minimum',
        summary_due_at=NOW.timestamp(),
    )
    assert home_step.classify(stamped) == 'writing_notes'
    # No debt means no summary will ever replace the stand-in: hide it, do not
    # present Writing notes forever.
    assert home_step.classify({**stamped, 'summary_due_at': None}) == 'noise'


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


EMPTY_REASONS = sorted(EMPTY_BLOCKED_REASONS)


def empty_block(**updates):
    """A completed row with a terminal empty-output block and no summary body."""
    updates.setdefault('summary_blocked_reason', 'empty_output_exhausted')
    return row(structured={'title': 'Recording · 9:38 AM', 'overview': '', 'sections': []}, **updates)


@pytest.mark.parametrize('provenance', [None, 'server_minimum', 'llm', 'generated'])
def test_empty_blocked_stand_in_is_noise_whatever_title_provenance(provenance):
    for reason in EMPTY_REASONS:
        data = empty_block(summary_blocked_reason=reason)
        if provenance is not None:
            data['structured']['title_provenance'] = provenance
        assert home_step.classify(data) == 'noise'


@pytest.mark.parametrize('reason', EMPTY_REASONS)
@pytest.mark.parametrize(
    'structured',
    [
        {'title': 'Recording · 9:38 AM', 'overview': 'Actual notes.', 'sections': []},
        {
            'title': 'Recording · 9:38 AM',
            'overview': ' ',
            'sections': [{'heading': 'Notes', 'body_markdown': 'Actual notes.'}],
        },
    ],
)
def test_empty_block_with_summary_output_is_not_noise(structured, reason):
    assert home_step.classify(row(structured=structured, summary_blocked_reason=reason)) == 'ready'


@pytest.mark.parametrize('reason', EMPTY_REASONS)
@pytest.mark.parametrize('receipt', [{'summary_output_present': True}, {'summary_completed_at': NOW.timestamp()}])
def test_empty_block_with_banked_receipt_is_not_noise(receipt, reason):
    """A stale terminal reason must not hide a row whose summary already landed."""
    assert home_step.classify(empty_block(summary_blocked_reason=reason, **receipt)) == 'ready'


@pytest.mark.parametrize('reason', EMPTY_REASONS)
def test_empty_block_with_open_debt_is_not_noise(reason):
    """A live summary_due_at outranks a stale terminal reason."""
    provisional = minimum('Recording · 9:38 AM', summary_blocked_reason=reason)
    assert home_step.classify(provisional) == 'writing_notes'
    unprovenanced = empty_block(summary_blocked_reason=reason, summary_due_at=NOW.timestamp())
    assert home_step.classify(unprovenanced) == 'ready'


@pytest.mark.parametrize('reason', EMPTY_REASONS)
def test_late_revision_reopen_returns_to_writing_notes_or_ready(reason):
    """Clearing the reason on a re-arm must move the row back out of noise."""
    blocked = minimum('Recording · 9:38 AM', summary_blocked_reason=reason, summary_due_at=None)
    assert home_step.classify(blocked) == 'noise'
    reopened = dict(blocked, summary_blocked_reason=None, summary_due_at=NOW.timestamp())
    assert home_step.classify(reopened) == 'writing_notes'
    delivered = dict(blocked, summary_blocked_reason=None, summary_output_present=True)
    assert home_step.classify(delivered) == 'ready'


@pytest.mark.parametrize('reason', EMPTY_REASONS)
@pytest.mark.parametrize(
    'curation',
    [{'user_title': 'Mine'}, {'starred': True}, {'folder_user_set': True}, {'has_photos': True}],
)
def test_curated_row_outranks_empty_output_block(curation, reason):
    assert home_step.classify(empty_block(summary_blocked_reason=reason, **curation)) == 'ready'


@pytest.mark.parametrize('reason', EMPTY_REASONS)
@pytest.mark.parametrize('provenance,expected', [(None, 'ready'), ('server_minimum', 'noise')])
def test_empty_output_noise_kill_switch_restores_legacy_classification(monkeypatch, provenance, expected, reason):
    monkeypatch.setenv('HOME_EMPTY_OUTPUT_NOISE', 'false')
    data = empty_block(summary_blocked_reason=reason)
    data['structured']['title_provenance'] = provenance
    assert home_step.classify(data) == expected


@pytest.mark.parametrize('reason', EMPTY_REASONS)
def test_summary_output_stays_visible_with_kill_switch_off(monkeypatch, reason):
    monkeypatch.setenv('HOME_EMPTY_OUTPUT_NOISE', 'false')
    data = row(
        structured={'title': 'Recording · 9:38 AM', 'overview': 'Actual notes.', 'sections': []},
        summary_blocked_reason=reason,
    )
    assert home_step.classify(data) == 'ready'


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


@pytest.mark.parametrize('status', ['processing', 'merging'])
@pytest.mark.parametrize('title', ['', 'Notes have a title'])
@pytest.mark.parametrize('age_hours', [5, 7])
def test_processing_wait_is_bounded(status, title, age_hours):
    data = row(
        status=status,
        structured={'title': title},
        finished_at=NOW - timedelta(hours=age_hours),
        # Both are renewed during healthy processing and must not reset the bound.
        processing_admitted_at=NOW,
        updated_at=NOW,
    )
    before = dict(data)
    expected = 'failed' if age_hours == 7 else ('writing_notes' if title else 'transcribing')
    assert home_step.project(data)['home_step'] == expected
    assert data == before


@pytest.mark.parametrize('status', ['processing', 'merging'])
@pytest.mark.parametrize('field', ['finished_at', 'created_at'])
@pytest.mark.parametrize('title', ['', 'Notes have a title'])
@pytest.mark.parametrize('offset_microseconds', [-1, 0, 1])
def test_processing_age_limit_exact_boundary(monkeypatch, status, field, title, offset_microseconds):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 7, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(home_step, 'datetime', FrozenDatetime)
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'on')
    monkeypatch.setenv('HOME_PROCESSING_MAX_AGE_SECONDS', '21600')
    data = row(status=status, structured={'title': title}, finished_at=None, created_at=None)
    data[field] = FrozenDatetime.now() - timedelta(hours=6, microseconds=offset_microseconds)
    before = dict(data)
    expected = 'failed' if offset_microseconds >= 0 else ('writing_notes' if title else 'transcribing')
    metric = home_step.PROCESSING_AGE_TOTAL.labels(reason=home_step.HomeProcessingAgeReason.EXPIRED)
    counted = metric._value.get()
    assert home_step.project(data)['home_step'] == expected
    assert metric._value.get() == counted + (offset_microseconds >= 0)
    assert data == before


@pytest.mark.parametrize('raw', ['', 'bad', '0', '-1', '1.5'])
def test_invalid_processing_limit_uses_default_and_counts(monkeypatch, raw):
    monkeypatch.setenv('HOME_PROCESSING_MAX_AGE_SECONDS', raw)
    metric = home_step.PROCESSING_AGE_TOTAL.labels(reason=home_step.HomeProcessingAgeReason.INVALID_CONFIG)
    before = metric._value.get()
    assert home_step.classify(row(status='processing', finished_at=NOW - timedelta(hours=5))) == 'writing_notes'
    assert home_step.classify(row(status='processing', finished_at=NOW - timedelta(hours=7))) == 'failed'
    assert metric._value.get() == before + 2


def test_processing_limit_is_read_at_call_time(monkeypatch):
    data = row(status='processing', finished_at=NOW - timedelta(hours=1))
    monkeypatch.setenv('HOME_PROCESSING_MAX_AGE_SECONDS', '7200')
    assert home_step.classify(data) == 'writing_notes'
    monkeypatch.setenv('HOME_PROCESSING_MAX_AGE_SECONDS', '1800')
    assert home_step.classify(data) == 'failed'


@pytest.mark.parametrize('finished', [None, 'bad', 0])
def test_processing_falls_back_to_created_at(finished):
    assert (
        home_step.classify(row(status='processing', finished_at=finished, created_at=NOW - timedelta(hours=7)))
        == 'failed'
    )


def test_recent_capture_end_wins_over_old_recording_start_and_creation():
    assert (
        home_step.classify(
            row(status='processing', started_at=NOW - timedelta(days=1), created_at=NOW - timedelta(days=1))
        )
        == 'writing_notes'
    )


@pytest.mark.parametrize('title,expected', [('', 'transcribing'), ('Notes title', 'writing_notes')])
def test_unknown_processing_age_is_unchanged_and_counted(title, expected):
    data = row(status='processing', structured={'title': title}, finished_at='bad', created_at=None)
    metric = home_step.PROCESSING_AGE_TOTAL.labels(reason=home_step.HomeProcessingAgeReason.MISSING_TIMESTAMP)
    before = metric._value.get()
    assert home_step.classify(data) == expected
    assert metric._value.get() == before + 1


@pytest.mark.parametrize('field', ['finished_at', 'created_at'])
def test_naive_processing_clock_is_utc(field):
    data = row(status='merging', finished_at=None, created_at=None)
    data[field] = (NOW - timedelta(hours=7)).replace(tzinfo=None)
    assert home_step.classify(data) == 'failed'


@pytest.mark.parametrize(
    'curation',
    [{'user_title': 'Mine'}, {'starred': True}, {'folder_user_set': True}, {'has_photos': True}, {'photos': [{}]}],
)
def test_curation_preserves_completed_rows_but_cannot_extend_processing(curation):
    data = minimum(finished_at=NOW - timedelta(hours=7), summary_blocked_reason='content_below_floor', **curation)
    assert home_step.classify(data) == 'ready'
    assert home_step.classify(dict(data, status='processing')) == 'failed'


def test_processing_kill_switch_omits_field_and_does_not_count(monkeypatch):
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'off')
    monkeypatch.setenv('HOME_PROCESSING_MAX_AGE_SECONDS', 'bad')
    metric = home_step.PROCESSING_AGE_TOTAL.labels(reason=home_step.HomeProcessingAgeReason.INVALID_CONFIG)
    before = metric._value.get()
    assert 'home_step' not in home_step.project(row(status='processing', finished_at=NOW - timedelta(days=1)))
    assert metric._value.get() == before
