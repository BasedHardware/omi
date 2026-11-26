"""Experiment ``end_open_conversation``: End cuts the v3 conversation at the instant it was pressed.

Off (the default) End records nothing and the builder reads nothing, so the
ordinary v3 suites assert production's behaviour unchanged. On, an owner-level
cut ends the open stretch and later speech starts a new one, even when one
uploaded recording carries the speech on both sides of the cut.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from config import reliability_experiments
from utils.conversations.v3 import manual_cuts, outline

EXPERIMENT = 'end_open_conversation'
NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def recording(cid='r', at=NOW, segments=None, **extra):
    return {
        'id': cid,
        'started_at': at,
        'source': 'omi',
        'recording': True,
        'transcript_segments': segments or [{'text': 'hello world', 'start': 0, 'end': 10, 'is_user': True}],
        **extra,
    }


def spoken(*spans):
    return [{'text': f'line {index}', 'start': start, 'end': end} for index, (start, end) in enumerate(spans)]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)


def test_registered():
    assert EXPERIMENT in reliability_experiments.EXPERIMENTS


def test_one_uploaded_recording_is_cut_where_end_was_pressed():
    # Speech at 0-10 s and 60-70 s in the same recording: one stretch without a cut (gap under 5 min).
    row = recording(segments=spoken((0, 10), (60, 70)))
    now = NOW + timedelta(seconds=80)
    assert len(outline.stretches([row], now)) == 1

    first, second = outline.stretches([row], now, manual_cuts=[NOW + timedelta(seconds=30)])
    assert [line['text'] for line in first['lines']] == ['line 0']
    assert first['manual_end'] and first['locked'] and first['finished']
    assert [line['text'] for line in second['lines']] == ['line 1']
    assert not second['manual_end'] and not second['finished']


def test_end_with_no_later_speech_closes_the_open_stretch_at_once():
    row = recording()
    now = NOW + timedelta(seconds=40)
    assert not outline.stretches([row], now)[0]['finished']
    (group,) = outline.stretches([row], now, manual_cuts=[NOW + timedelta(seconds=30)])
    assert group['manual_end'] and group['finished']


def test_cut_in_the_future_or_before_any_speech_changes_nothing():
    row = recording()
    now = NOW + timedelta(seconds=40)
    for cut in (now + timedelta(seconds=1), NOW - timedelta(seconds=5)):
        (group,) = outline.stretches([row], now, manual_cuts=[cut])
        assert not group['manual_end'] and not group['finished']


def test_cut_after_the_silence_boundary_does_not_mark_the_ended_stretch():
    # The stretch ended by silence at 10 s; End arrives 6 minutes later with nothing recorded since.
    row = recording()
    cut = NOW + timedelta(minutes=6)
    (group,) = outline.stretches([row], cut + timedelta(seconds=1), manual_cuts=[cut])
    assert group['finished'] and not group['manual_end']

    # Same when speech resumes after that late cut: the silence boundary splits, nobody is marked.
    resumed = recording(segments=spoken((0, 10), (400, 410)))
    first, second = outline.stretches([resumed], NOW + timedelta(seconds=420), manual_cuts=[cut])
    assert not first['manual_end'] and not second['manual_end']


def test_late_speech_from_before_the_cut_joins_the_ended_stretch():
    cut = NOW + timedelta(seconds=30)
    early = recording('a', segments=spoken((0, 10)))
    late = recording('b', at=NOW + timedelta(seconds=15), segments=spoken((0, 5)))
    after = recording('c', at=NOW + timedelta(seconds=45), segments=spoken((0, 5)))
    first, second = outline.stretches([early, after, late], NOW + timedelta(seconds=60), manual_cuts=[cut])
    assert {line['conversation_id'] for line in first['lines']} == {'a', 'b'}
    assert first['manual_end']
    assert {line['conversation_id'] for line in second['lines']} == {'c'}


def test_a_recordings_own_manual_end_still_cuts_beside_an_owner_cut():
    ended = recording('a', finished_at=NOW + timedelta(seconds=10), v3_manual_end=True)
    later = recording('b', at=NOW + timedelta(seconds=20))
    without = outline.stretches([ended, later], NOW + timedelta(seconds=40))
    with_cut = outline.stretches([ended, later], NOW + timedelta(seconds=40), manual_cuts=[NOW + timedelta(seconds=12)])
    assert [len(g['lines']) for g in without] == [len(g['lines']) for g in with_cut] == [1, 1]
    assert without[0]['manual_end'] and with_cut[0]['manual_end']


def test_off_request_end_writes_nothing(off, monkeypatch):
    record, enqueue = Mock(), Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', record)
    monkeypatch.setattr(manual_cuts.triggers, 'enqueue', enqueue)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)
    assert manual_cuts.request_end('u') is False
    record.assert_not_called()
    enqueue.assert_not_called()


def test_off_load_reads_nothing(off, monkeypatch):
    load = Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'load', load)
    assert manual_cuts.load('u', [recording()]) == []
    load.assert_not_called()


def test_on_request_end_records_the_instant_and_wakes_the_builder(on, monkeypatch):
    record, enqueue = Mock(return_value='cut-1'), Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', record)
    monkeypatch.setattr(manual_cuts.triggers, 'enqueue', enqueue)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)
    assert manual_cuts.request_end('u', now=NOW) is True
    record.assert_called_once_with('u', NOW)
    enqueue.assert_called_once_with('u', manual_end_id='cut-1')


def test_on_request_end_skips_an_owner_outside_v3(on, monkeypatch):
    record = Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', record)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: False)
    assert manual_cuts.request_end('u') is False
    record.assert_not_called()


def test_on_request_end_never_raises(on, monkeypatch):
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', Mock(side_effect=RuntimeError('store down')))
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)
    assert manual_cuts.request_end('u') is False


def test_on_load_asks_from_the_earliest_loaded_recording(on, monkeypatch):
    load = Mock(return_value=[NOW])
    monkeypatch.setattr(manual_cuts.cuts_db, 'load', load)
    rows = [recording('a', at=NOW + timedelta(minutes=3)), recording('b', at=NOW - timedelta(minutes=2))]
    assert manual_cuts.load('u', rows) == [NOW]
    load.assert_called_once_with('u', NOW - timedelta(minutes=2))
    assert manual_cuts.load('u', []) == []


# --- The End time from the phone, and held audio joining the conversation it was recorded in ---

from utils.conversations.v3 import planner  # noqa: E402


@pytest.mark.parametrize(
    'ended_at, expected',
    [
        (None, NOW),
        ('not a time', NOW),
        (NOW - timedelta(seconds=3), NOW - timedelta(seconds=3)),
        (NOW + timedelta(seconds=4), NOW + timedelta(seconds=4)),  # small clock skew ahead
        (NOW + timedelta(seconds=30), NOW),  # a phone clock ahead of the server
        (NOW - timedelta(minutes=11), NOW),  # a stale or badly retried request
        ((NOW - timedelta(seconds=3)).replace(tzinfo=None), NOW - timedelta(seconds=3)),  # naive means UTC
    ],
)
def test_cut_instant_uses_the_phones_end_time_only_when_plausible(ended_at, expected):
    assert manual_cuts.cut_instant(ended_at, NOW) == expected


@pytest.mark.parametrize(
    'header, expected',
    [
        (None, None),
        ('', None),
        ('soon', None),
        ('1e400', None),
        (str(NOW.timestamp()), NOW),
        (f'{NOW.timestamp() + 0.25:.3f}', NOW + timedelta(milliseconds=250)),
    ],
)
def test_parse_ended_at_reads_epoch_seconds_and_ignores_anything_else(header, expected):
    assert manual_cuts.parse_ended_at(header) == expected


def test_on_request_end_records_the_phones_end_time(on, monkeypatch):
    record, enqueue = Mock(return_value='cut-1'), Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', record)
    monkeypatch.setattr(manual_cuts.triggers, 'enqueue', enqueue)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)
    pressed = NOW - timedelta(seconds=2)
    assert manual_cuts.request_end('u', ended_at=pressed, now=NOW) is True
    record.assert_called_once_with('u', pressed)
    # The builder is woken at once whatever the listening session's recording is doing.
    enqueue.assert_called_once_with('u', manual_end_id='cut-1')


def test_ending_cut_is_the_first_cut_after_the_last_speech_while_the_stretch_is_open():
    gap = timedelta(minutes=5)
    last = NOW
    assert planner.ending_cut(last, [], gap) is None
    assert planner.ending_cut(last, [NOW - timedelta(minutes=1)], gap) is None, 'a cut before the last speech'
    assert planner.ending_cut(last, [NOW + timedelta(minutes=6)], gap) is None, 'silence had already ended it'
    first, second = NOW + timedelta(seconds=40), NOW + timedelta(minutes=2)
    assert planner.ending_cut(last, [second, first], gap) == first


def ended_row(cid='ended', *, start=NOW, seconds=60, cut=None, **extra):
    """A conversation the person ended: locked, with its last published line ``seconds`` after its start."""
    return {
        'id': cid,
        'status': 'completed',
        'manual_end': True,
        'started_at': start,
        'finished_at': start + timedelta(seconds=seconds),
        'v3_recording_ids': ['landed'],
        'transcript_segments': [{'id': 's1', 'text': 'already there', 'start': 0.0, 'end': float(seconds)}],
        **({planner.CUT_FIELD: cut} if cut is not None else {}),
        **extra,
    }


def line(at, seconds=5, *, recording='held', sid='late'):
    start = NOW + timedelta(seconds=at)
    return {
        'start': start,
        'end': start + timedelta(seconds=seconds),
        'text': 'late words',
        'speaker': 'ME',
        'conversation_id': recording,
        'segment': {'id': sid, 'text': 'late words', 'start': 0.0, 'end': float(seconds)},
    }


def test_held_audio_from_before_the_end_belongs_to_the_ended_conversation():
    cut = NOW + timedelta(seconds=100)
    owners = planner.Ownership({'ended': ended_row(cut=cut)}, {'landed': {}, 'held': {}})
    assert owners.owner_of(line(70))['id'] == 'ended', 'after its last line, before the End'
    assert owners.owner_of(line(98))['id'] == 'ended', 'a line belongs to the side on which it starts'
    assert owners.owner_of(line(100)) is None, 'speech from the End on starts the next conversation'
    assert owners.owner_of(line(130)) is None


def test_without_the_stored_cut_late_audio_stays_outside_as_today():
    owners = planner.Ownership({'ended': ended_row()}, {'landed': {}, 'held': {}})
    assert owners.owner_of(line(70)) is None
    # A conversation that ended by silence carries no cut even if the field were present by mistake.
    quiet = ended_row(cut=NOW + timedelta(seconds=100), manual_end=False)
    assert planner.Ownership({'ended': quiet}, {'held': {}}).owner_of(line(70)) is None
    # A conversation still open is not a finished owner.
    still_open = ended_row(cut=NOW + timedelta(seconds=100), status='in_progress')
    assert planner.Ownership({'ended': still_open}, {'held': {}}).owner_of(line(70)) is None


def test_the_reach_stops_at_the_next_conversation_and_never_takes_claimed_speech():
    cut = NOW + timedelta(seconds=100)
    following = ended_row('next', start=NOW + timedelta(seconds=80), seconds=10, manual_end=False)
    owners = planner.Ownership({'ended': ended_row(cut=cut), 'next': following}, {'landed': {}, 'held': {}})
    assert owners.owner_of(line(70))['id'] == 'ended'
    assert owners.owner_of(line(81, 4))['id'] == 'next', 'inside the next conversation'
    assert owners.owner_of(line(95)) is None, 'after the next conversation began'
    # Speech another conversation already claimed on its recording is not pulled back.
    claimed = {
        'held': {'claims': [{'conversation_id': 'elsewhere', 'start': NOW, 'end': NOW + timedelta(seconds=200)}]}
    }
    assert planner.Ownership({'ended': ended_row(cut=cut)}, claimed).owner_of(line(70)) is None


def planned(*lines, manual_end=False):
    return {
        'lines': list(lines),
        'finished': True,
        'manual_end': manual_end,
        'title': 'Planned',
        'kind': 'conversation',
        'emoji': '💬',
    }


def published():
    """The line the ended conversation already shows, as the planner sees it again on a later pass."""
    return {
        'start': NOW,
        'end': NOW + timedelta(seconds=60),
        'text': 'already there',
        'speaker': 'ME',
        'conversation_id': 'landed',
        'segment': {'id': 's1', 'text': 'already there', 'start': 0.0, 'end': 60.0},
    }


def test_late_audio_joins_the_ended_conversation_instead_of_becoming_a_fragment():
    cut = NOW + timedelta(seconds=100)
    existing = {'ended': ended_row(cut=cut)}
    recordings = {'landed': {}, 'held': {}}
    old, late, after = published(), line(70), line(110, sid='after')
    # The upstream finish path cuts at the last landed recording, so the planner proposes the late line
    # as its own window; a third window is speech from after the End.
    windows = planner.preserve_finished_windows(
        [planned(old, manual_end=True), planned(late, manual_end=True), planned(after)], existing, recordings
    )
    assert [(w.get('existing_id'), [l['segment']['id'] for l in w['lines']]) for w in windows] == [
        ('ended', ['s1', 'late']),
        (None, ['after']),
    ]

    # Baseline (no stored cut): the late line is its own fragment.
    windows = planner.preserve_finished_windows(
        [planned(old, manual_end=True), planned(late, manual_end=True)], {'ended': ended_row()}, recordings
    )
    assert [(w.get('existing_id'), [l['segment']['id'] for l in w['lines']]) for w in windows] == [
        ('ended', ['s1']),
        (None, ['late']),
    ]


def test_record_end_stores_without_waking_and_wake_is_separate(on, monkeypatch):
    record, enqueue = Mock(return_value='cut-1'), Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', record)
    monkeypatch.setattr(manual_cuts.triggers, 'enqueue', enqueue)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)
    assert manual_cuts.record_end('u', ended_at=NOW - timedelta(seconds=1), now=NOW) == 'cut-1'
    record.assert_called_once_with('u', NOW - timedelta(seconds=1))
    enqueue.assert_not_called()

    assert manual_cuts.wake('u', 'cut-1') is True
    enqueue.assert_called_once_with('u', manual_end_id='cut-1')
    # Nothing stored (off, not admitted, a fault): nothing to wake for.
    assert manual_cuts.wake('u', None) is False
    assert enqueue.call_count == 1
    enqueue.side_effect = RuntimeError('queue down')
    assert manual_cuts.wake('u', 'cut-2') is False, 'never raises into End'


def test_off_record_end_and_wake_do_nothing(off, monkeypatch):
    record, enqueue = Mock(), Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', record)
    monkeypatch.setattr(manual_cuts.triggers, 'enqueue', enqueue)
    assert manual_cuts.record_end('u', now=NOW) is None
    assert manual_cuts.wake('u', None) is False
    record.assert_not_called()
    enqueue.assert_not_called()


def test_end_route_wakes_once_per_end(monkeypatch):
    """One builder wake per End: the baseline finish wakes for a cut window, the experiment for the rest."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from routers import conversations

    woken = []
    monkeypatch.setattr(conversations.v3_manual_cuts, 'record_end', lambda uid, ended_at=None: 'cut-1')
    monkeypatch.setattr(conversations.v3_manual_cuts, 'wake', lambda uid, cut_id: woken.append(cut_id))
    monkeypatch.setattr(conversations, 'retrieve_in_progress_conversation', lambda uid: None)

    def answer(tile):
        return SimpleNamespace(conversation=SimpleNamespace(tile_state=tile))

    # No recording in progress, window cut by the baseline finish (it woke the builder): no second wake.
    monkeypatch.setattr(conversations, 'finish_live_window', lambda uid, window_id=None, **kw: answer('writing'))
    conversations.process_in_progress_conversation(None, 'u', None)
    assert woken == []

    # The baseline finish is still waiting for audio and woke nobody: the experiment wakes.
    monkeypatch.setattr(conversations, 'finish_live_window', lambda uid, window_id=None, **kw: answer('transcribing'))
    conversations.process_in_progress_conversation(None, 'u', None)
    assert woken == ['cut-1']

    # Nothing open at all: the cut is stored for audio still to land, and the builder is woken.
    monkeypatch.setattr(conversations, 'finish_live_window', lambda uid, window_id=None, **kw: None)
    with pytest.raises(HTTPException) as missing:
        conversations.process_in_progress_conversation(None, 'u', None)
    assert missing.value.status_code == 404 and woken == ['cut-1', 'cut-1']

    # A recording in progress (the listening session's): the experiment wakes at once, then the baseline path runs.
    monkeypatch.setattr(conversations, 'retrieve_in_progress_conversation', lambda uid: {'id': 'session-recording'})
    monkeypatch.setattr(conversations, 'is_listen_finalization_dispatch_enabled', lambda: True)
    monkeypatch.setattr(conversations.byok, 'has_byok_keys', lambda: False)
    monkeypatch.setattr(conversations, 'finalize_conversation', lambda cid, request=None, uid=None: f'finalized {cid}')
    assert conversations.process_in_progress_conversation(None, 'u', None) == 'finalized session-recording'
    assert woken == ['cut-1', 'cut-1', 'cut-1']


# --- One End, one conversation: the finalized recording's own mark does not cut a second time ---


def test_end_cuts_once_when_the_listening_recording_spoke_earlier_than_the_files():
    """The first End on the phone (2026-11-24): one End produced two ended conversations.

    The listening recording had speech early on and was marked at its end; the later speech travelled
    as uploaded files; the End came six minutes after that mark, with speech in between.
    """
    listening = recording(
        'listening', segments=spoken((0, 20)), finished_at=NOW + timedelta(seconds=20), v3_manual_end=True
    )
    files = recording('files', at=NOW + timedelta(seconds=290), segments=spoken((0, 60)))
    pressed = NOW + timedelta(seconds=352)
    after = recording('after', at=NOW + timedelta(seconds=360), segments=spoken((0, 5)))
    now = NOW + timedelta(seconds=400)

    baseline = outline.stretches([listening, files, after], now)
    assert [(len(g['lines']), g['manual_end']) for g in baseline] == [(1, True), (2, False)], 'today: cut at the mark'

    groups = outline.stretches([listening, files, after], now, manual_cuts=[pressed])
    assert [(len(g['lines']), g['manual_end']) for g in groups] == [(2, True), (1, False)]
    assert groups[0]['end'] == NOW + timedelta(seconds=350)


def test_the_mark_still_cuts_when_the_stretch_did_not_go_on_to_the_end():
    marked = recording(
        'listening', segments=spoken((0, 20)), finished_at=NOW + timedelta(seconds=20), v3_manual_end=True
    )
    # Nothing was said between the mark and the End, ten minutes later: the End finds no open stretch,
    # and the conversation is still one the person ended.
    pressed = NOW + timedelta(minutes=10)
    groups = outline.stretches([marked], NOW + timedelta(minutes=11), manual_cuts=[pressed])
    assert [(len(g['lines']), g['manual_end']) for g in groups] == [(1, True)]

    # The next speech comes only after the End: the mark cuts, as it does today.
    after = recording('after', at=NOW + timedelta(minutes=10, seconds=30), segments=spoken((0, 5)))
    groups = outline.stretches([marked, after], NOW + timedelta(minutes=12), manual_cuts=[pressed])
    assert [(len(g['lines']), g['manual_end']) for g in groups] == [(1, True), (1, False)]

    # The next speech comes before the End but after five minutes of silence: a new stretch anyway.
    late = recording('late', at=NOW + timedelta(minutes=6), segments=spoken((0, 5)))
    groups = outline.stretches([marked, late], NOW + timedelta(minutes=11), manual_cuts=[pressed])
    assert [(len(g['lines']), g['manual_end']) for g in groups] == [(1, True), (1, True)]


def test_an_earlier_end_keeps_its_own_cut_beside_a_later_one():
    # Two Ends, each with its recording mark and its owner cut: the first conversation stays ended where
    # its End was, the second runs to the second End.
    first = recording('a', segments=spoken((0, 20)), finished_at=NOW + timedelta(seconds=20), v3_manual_end=True)
    between = recording('b', at=NOW + timedelta(seconds=30), segments=spoken((0, 10)))
    second = recording(
        'c',
        at=NOW + timedelta(seconds=60),
        segments=spoken((0, 20)),
        finished_at=NOW + timedelta(seconds=80),
        v3_manual_end=True,
    )
    tail = recording('d', at=NOW + timedelta(seconds=90), segments=spoken((0, 10)))
    cuts = [NOW + timedelta(seconds=45), NOW + timedelta(seconds=105)]
    groups = outline.stretches([first, between, second, tail], NOW + timedelta(seconds=200), manual_cuts=cuts)
    assert [(len(g['lines']), g['manual_end']) for g in groups] == [(2, True), (2, True)]
    assert [g['end'] for g in groups] == [NOW + timedelta(seconds=40), NOW + timedelta(seconds=100)]


def test_a_mark_stamped_a_few_seconds_after_the_end_is_the_same_end():
    # The server stamped the recording's end slightly after the phone's End time.
    spoke = recording('files', segments=spoken((0, 30)))
    listening = recording(
        'listening',
        at=NOW + timedelta(seconds=5),
        segments=[{'text': 'heard on the listening session', 'start': 0, 'end': 10}],
        finished_at=NOW + timedelta(seconds=44),
        v3_manual_end=True,
    )
    after = recording(
        'after', at=NOW + timedelta(seconds=42), segments=[{'text': 'said after the end', 'start': 0, 'end': 5}]
    )
    groups = outline.stretches(
        [spoke, listening, after], NOW + timedelta(seconds=100), manual_cuts=[NOW + timedelta(seconds=40)]
    )
    assert [(len(g['lines']), g['manual_end']) for g in groups] == [(2, True), (1, False)]


# --- with main's Finish wait (CONVERSATIONS_V3_CAPTURE_CONTINUITY) ----------------------------------------
#
# Main holds a recording's manual-end cut, up to policy.FINISH_WAIT, while a transcript that would join it
# has not landed. An End that stored an owner-level cut is not held: the cut applies at the End time at
# once and the late speech joins the ended conversation afterwards. Every other End keeps main's wait.


def test_an_end_with_its_owner_cut_does_not_wait_for_its_own_transcript():
    from tests.unit.test_conversations_v3_finish_late_predecessor import T0, finish, recording as sealed

    def scene():
        # The listening recording's own transcript has not landed; an earlier fragment has.
        return (
            sealed('f', T0 + timedelta(seconds=1.6), 1.2, origin='device-sync'),
            {**finish(T0 + timedelta(seconds=128), 22), 'transcript_segments': []},
        )

    fragment, ended = scene()
    now = ended['finished_at'] + timedelta(seconds=10)
    (group,) = outline.stretches([fragment, ended], now, continuity=True)
    assert not group['manual_end'] and 'finish_held_until' in group, 'main alone: the cut waits'

    fragment, ended = scene()
    pressed = ended['finished_at'] + timedelta(seconds=3)
    (group,) = outline.stretches([fragment, ended], now, continuity=True, manual_cuts=[pressed])
    assert group['manual_end'] and group['locked'] and 'finish_held_until' not in group
    assert outline.HOLD_UNTIL not in ended and outline.HOLD_UNTIL not in fragment


def test_an_end_with_its_owner_cut_does_not_wait_for_a_reconnected_predecessor():
    from tests.unit.test_conversations_v3_finish_late_predecessor import T0, awaiting, finish

    def scene():
        # The stream dropped and reconnected: the first recording's batch transcript is still to land.
        return awaiting('a', T0, 60, sealed_at=T0 + timedelta(seconds=61)), finish(T0 + timedelta(seconds=400), 20)

    earlier, ended = scene()
    now = ended['finished_at'] + timedelta(seconds=10)
    (group,) = outline.stretches([earlier, ended], now, continuity=True)
    assert not group['manual_end'] and ended[outline.HOLD_UNTIL] is not None, 'main alone: the cut waits'

    earlier, ended = scene()
    pressed = ended['finished_at'] + timedelta(seconds=2)
    (group,) = outline.stretches([earlier, ended], now, continuity=True, manual_cuts=[pressed])
    assert group['manual_end'] and group['locked'] and 'finish_held_until' not in group
    assert outline.HOLD_UNTIL not in ended and outline.HOLD_UNTIL not in earlier


def test_an_end_without_an_owner_cut_of_its_own_still_waits():
    from tests.unit.test_conversations_v3_finish_late_predecessor import T0, awaiting, finish

    earlier = awaiting('a', T0, 60, sealed_at=T0 + timedelta(seconds=61))
    ended = finish(T0 + timedelta(seconds=400), 20)
    now = ended['finished_at'] + timedelta(seconds=10)
    # The only owner-level cut belongs to an End an hour earlier: it answers nothing here.
    (group,) = outline.stretches([earlier, ended], now, continuity=True, manual_cuts=[T0 - timedelta(hours=1)])
    assert not group['manual_end'] and group['finish_held_until'] == ended[outline.HOLD_UNTIL]
