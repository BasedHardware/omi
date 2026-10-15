from datetime import datetime, timezone

from utils.model_text import (
    DisplayClock,
    format_date,
    format_duration,
    format_elapsed,
    format_instant,
    format_span,
    to_datetime,
    truncation_note,
)

HCM = DisplayClock.from_name('Asia/Ho_Chi_Minh')
# The Grokbot event: 07:18 UTC is 14:18 in Ho Chi Minh, and ran 2h 12m.
START = datetime(2026, 9, 26, 7, 18, tzinfo=timezone.utc)
END = datetime(2026, 9, 26, 9, 30, tzinfo=timezone.utc)


def test_instant_is_local_and_labelled():
    assert format_instant(START, HCM) == 'Sat 26 Sep 2026, 14:18 Asia/Ho_Chi_Minh (UTC+07:00)'


def test_naive_datetime_is_utc_not_server_local():
    assert format_instant(START.replace(tzinfo=None), HCM) == format_instant(START, HCM)


def test_unix_seconds_and_iso_strings_are_accepted():
    assert format_instant(int(START.timestamp()), HCM) == format_instant(START, HCM)
    assert format_instant('2026-09-26T07:18:00Z', HCM) == format_instant(START, HCM)


def test_span_precomputes_end_and_duration():
    assert format_span(START, END, HCM) == 'Sat 26 Sep 2026, 14:18–16:30 Asia/Ho_Chi_Minh (UTC+07:00), 2h 12m'


def test_span_across_midnight_names_both_days():
    late = datetime(2026, 9, 26, 16, 0, tzinfo=timezone.utc)
    later = datetime(2026, 9, 26, 18, 15, tzinfo=timezone.utc)
    assert format_span(late, later, HCM) == (
        'Sat 26 Sep 2026, 23:00 – Sun 27 Sep 2026, 01:15 Asia/Ho_Chi_Minh (UTC+07:00), 2h 15m'
    )


def test_span_across_dst_labels_each_end():
    ny = DisplayClock.from_name('America/New_York')
    start = datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)  # 01:00 EDT
    end = datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)  # 02:00 EST
    rendered = format_span(start, end, ny)
    assert '(UTC-04:00)' in rendered and '(UTC-05:00)' in rendered and rendered.endswith('2h')


def test_span_without_end_is_the_start_instant():
    assert format_span(START, None, HCM) == format_instant(START, HCM)


def test_date_uses_the_users_calendar_day():
    evening_utc = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
    assert format_date(evening_utc, HCM) == 'Sun 27 Sep 2026'


def test_utc_clock_is_still_labelled():
    assert format_instant(START, DisplayClock.utc()) == 'Sat 26 Sep 2026, 07:18 UTC'


def test_invalid_zone_falls_back_to_labelled_utc():
    assert DisplayClock.from_name('Not/AZone') == DisplayClock.utc()


def test_for_turn_prefers_the_turn_zone_without_a_lookup(monkeypatch):
    def boom(_uid):
        raise AssertionError('must not read stored timezone when the turn carries one')

    monkeypatch.setattr(DisplayClock, 'for_uid', classmethod(lambda cls, uid: boom(uid)))
    assert DisplayClock.for_turn({'user_timezone': 'Asia/Ho_Chi_Minh'}, 'uid') == HCM


def test_for_turn_without_zone_or_uid_is_utc():
    assert DisplayClock.for_turn({}, None) == DisplayClock.utc()


def test_elapsed_is_marked_as_offset():
    assert format_elapsed(3900) == '+1:05:00'
    assert format_elapsed(5) == '+0:00:05'


def test_duration_forms():
    assert format_duration(7920) == '2h 12m'
    assert format_duration(7200) == '2h'
    assert format_duration(2700) == '45m'
    assert format_duration(30) == '30s'
    assert format_duration(-1) == 'unknown duration'


def test_truncation_note_says_omitted_not_absent():
    assert truncation_note(shown=5, total=5, unit='segments', how_to_get_more='') == ''
    note = truncation_note(shown=40, total=312, unit='transcript segments', how_to_get_more='Ask for a later range.')
    assert 'Showing 40 of 312 transcript segments' in note and 'omitted, not absent' in note


def test_to_datetime_rejects_garbage():
    assert to_datetime('not a date') is None
    assert to_datetime(None) is None
    assert to_datetime(True) is None
