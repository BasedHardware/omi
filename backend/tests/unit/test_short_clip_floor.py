"""The short-clip floor on both measures: few words, or speech too brief to carry them.

A 2 s pendant clip packed with a dozen words must not reach Jev, the calendar
override or the notes model (2026-10-25: a 2 s clip kept by ``jev_keep`` with a
generated title, a 12 s clip kept by ``calendar_overlap``). Sub-floor captures
take the quiet minimum the word floor already routes to; the duration is
measured from the transcript's own segment spans, never the wall window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from utils.conversations import process_conversation as processing
from utils.conversations.duration import conversation_duration_seconds
from utils.conversations.relevance import decide_relevance
from utils.llm import notes_packet as packet
from utils.llm import notes_short_clip
from utils.llm.notes_short_clip import SHORT_CLIP_MAX_SPEECH_SECONDS, below_short_clip_floor, speech_seconds

START = datetime(2026, 10, 25, 6, 35, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_flags(monkeypatch):
    for flag in ('NOTES_PACKET_V2_MODE',):
        monkeypatch.delenv(flag, raising=False)
        monkeypatch.delenv(flag + '_SERVE_PERCENT', raising=False)
        monkeypatch.delenv(flag + '_SERVE_UID_SHA256S', raising=False)
    from database import users as users_db

    monkeypatch.setattr(users_db, 'get_user_language_preference', lambda *_args: 'en')


def _segments(words: int, *, start: float, end: float) -> list[SimpleNamespace]:
    text = ' '.join(f'word{index}' for index in range(words))
    return [SimpleNamespace(text=text, start=start, end=end)]


# --------------------------------------------------------------------------- the floor helpers


@pytest.mark.parametrize(
    'words,seconds,expected',
    [
        (11, None, True),  # word floor alone
        (12, None, False),
        (12, SHORT_CLIP_MAX_SPEECH_SECONDS, False),
        (25, 2.0, True),  # the 2 s clip with a dozen-plus words
        (25, 3.9, True),
        (25, 4.0, False),
        (14, 6.0, False),  # a short real command keeps its notes
        (25, 60.0, False),
        (12, -1.0, False),  # an invalid span is unknown, never sub-floor
    ],
)
def test_below_short_clip_floor_on_either_measure(words, seconds, expected):
    assert below_short_clip_floor(words=words, speech_seconds=seconds) is expected


def test_speech_seconds_skips_empty_text_and_unusable_spans():
    rows = [
        SimpleNamespace(text='real speech', start=0.0, end=4.0),
        SimpleNamespace(text='', start=10.0, end=20.0),  # silence band, not speech
        SimpleNamespace(text='broken', start=None, end=None),
    ]
    assert speech_seconds(rows) == 4.0
    assert speech_seconds([SimpleNamespace(text='no clocks')]) is None
    assert speech_seconds([]) is None


def test_quiet_minimum_takes_a_brief_speech_clip_with_many_words(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    conversation = SimpleNamespace(transcript_segments=_segments(25, start=0.0, end=2.0), photos=[])
    minimum = notes_short_clip.quiet_minimum('synthetic-account', conversation, tz='UTC')
    assert minimum is not None and minimum.title_provenance == 'server_minimum'


def test_quiet_minimum_leaves_real_speech_to_the_notes_model(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    conversation = SimpleNamespace(transcript_segments=_segments(25, start=0.0, end=60.0), photos=[])
    assert notes_short_clip.quiet_minimum('synthetic-account', conversation, tz='UTC') is None


# --------------------------------------------------------------------------- the relevance tiers


def _relevance(*, texts, speech_seconds, calendar=False, jev=None, model_discards=None):
    calls = {'jev': 0}

    def jev_probability():
        calls['jev'] += 1
        return jev()

    return (
        calls,
        decide_relevance(
            trigger=processing.ProcessingTrigger.SYNC_UPDATE,
            texts=texts,
            speech_seconds=speech_seconds,
            has_photos=False,
            user_kept=False,
            exempt=False,
            trusted_wake_word=False,
            model_discards=(lambda _on_error, _neighbor: model_discards) if model_discards is not None else None,
            calendar_retains=lambda: calendar,
            jev_discard_probability=jev_probability,
        ),
    )


# Content words keep the deterministic tier undecided so the paid arms decide.
AMBIGUOUS = ['firmware development and testing ' * 5]


def test_jev_is_never_asked_about_a_sub_floor_clip_and_cannot_keep_it():
    # Jev would keep (p_discard 0); the floor steps over it and nano decides.
    calls, decision = _relevance(texts=AMBIGUOUS, speech_seconds=2.0, jev=lambda: 0.0, model_discards=False)
    assert calls['jev'] == 0
    assert decision.verdict == 'keep' and decision.decided_by == 'model' and decision.reason == 'model_keep'

    # No paid arm at all: the withheld-model keep, never a Jev keep.
    calls, decision = _relevance(texts=AMBIGUOUS, speech_seconds=2.0, jev=lambda: 0.0)
    assert calls['jev'] == 0
    assert decision.verdict == 'keep' and decision.reason == 'model_withheld'


def test_a_calendar_overlap_still_rescues_a_sub_floor_clip_that_reaches_relevance():
    # Paths quiet_minimum does not cover (non-v2 cohort, rules-only desktop, recovery)
    # must not turn a short in-meeting fragment into a discard.
    calls, decision = _relevance(texts=AMBIGUOUS, speech_seconds=2.0, calendar=True, model_discards=True)
    assert decision.verdict == 'keep' and decision.reason == 'calendar_overlap'


def test_a_calendar_overlap_still_keeps_a_clip_that_meets_the_floor():
    calls, decision = _relevance(texts=AMBIGUOUS, speech_seconds=60.0, calendar=True, model_discards=True)
    assert decision.verdict == 'keep' and decision.decided_by == 'override' and decision.reason == 'calendar_overlap'


def test_jev_still_keeps_and_discards_clips_that_meet_the_floor():
    # The Jev tier runs only with the nano fallback behind it (the chain's contract).
    calls, decision = _relevance(texts=AMBIGUOUS, speech_seconds=60.0, jev=lambda: 0.05, model_discards=False)
    assert calls['jev'] == 1 and decision.verdict == 'keep' and decision.reason == 'jev_keep'
    calls, decision = _relevance(
        texts=AMBIGUOUS, speech_seconds=60.0, calendar=True, jev=lambda: 0.95, model_discards=False
    )
    assert decision.verdict == 'keep' and decision.reason == 'calendar_overlap'


def test_user_authority_still_outranks_the_floor():
    decision = decide_relevance(
        trigger=processing.ProcessingTrigger.SYNC_UPDATE,
        texts=['word ' * 25],
        speech_seconds=2.0,
        has_photos=False,
        user_kept=True,
        exempt=False,
        trusted_wake_word=False,
        model_discards=None,
        calendar_retains=lambda: False,
    )
    assert decision.verdict == 'keep' and decision.decided_by == 'user'


# --------------------------------------------------------------------------- the notes wiring


def test_a_two_second_clip_never_reaches_a_model_title_or_the_relevance_tiers(monkeypatch):
    monkeypatch.setenv(packet.FLAG, 'serve')
    monkeypatch.setattr(processing.notification_db, 'get_user_time_zone', lambda *_args: 'UTC')
    monkeypatch.setattr(processing, 'get_conversation_notes', lambda *_args, **_kwargs: pytest.fail('paid notes'))
    monkeypatch.setattr(
        processing, 'should_discard_conversation', lambda *_args, **_kwargs: pytest.fail('paid discard')
    )
    monkeypatch.setattr(
        processing, '_calendar_overlap_retains_conversation', lambda *_args, **_kwargs: pytest.fail('calendar read')
    )
    conversation = SimpleNamespace(
        transcript_segments=_segments(15, start=0.0, end=2.0),
        started_at=START,
        finished_at=START + timedelta(seconds=2),
        photos=[],
        source='omi',
    )
    decisions: list[Any] = []
    structured, discarded = processing._get_structured(
        'synthetic-account',
        'en',
        conversation,
        trigger=processing.ProcessingTrigger.SYNC_UPDATE,
        relevance_observer=decisions.append,
    )
    assert not discarded and structured.title_provenance == 'server_minimum'
    assert [d.reason for d in decisions] == ['content_below_floor']


# ------------------------------------------------------- the duration source (sync intake)


def test_sync_intake_wall_window_equals_the_transcript_span_and_the_floor_uses_the_span():
    """The WAL intake clocks cannot collapse: the wall window is the transcript span.

    ``process_segment`` times lines from the first word (``speech_offset`` into
    the VAD file), derives ``finished_at`` from the same offset, then shifts the
    segments onto the file clock. Replayed here with the real helpers, the row's
    ``finished_at - started_at`` equals its transcript span, and the floor is
    decided by that span — never by a wall window a collapsed row could shrink.
    """
    from utils.stt.pre_recorded import postprocess_words
    from utils.sync.word_timing import first_word_offset, shift_to_vad_file_clock

    vad_lead, speech = 30.0, 12.0  # the file opens well before the first word
    words = [
        {
            'timestamp': [vad_lead + speech * index / 6, vad_lead + speech * (index + 1) / 6],
            'speaker': None,
            'text': f'word{index}',
        }
        for index in range(6)
    ]
    offset = first_word_offset(words)
    assert offset == vad_lead
    segments = postprocess_words(words, 0)
    timestamp = START.timestamp()
    segment_end_timestamp = timestamp + offset + max(segment.end for segment in segments)
    shift_to_vad_file_clock(segments, offset)

    row = {
        'transcript_segments': [{'text': s.text, 'start': s.start, 'end': s.end} for s in segments],
        'started_at': datetime.fromtimestamp(timestamp, tz=timezone.utc),
        'finished_at': datetime.fromtimestamp(segment_end_timestamp, tz=timezone.utc),
    }
    wall = (row['finished_at'] - row['started_at']).total_seconds()
    span = conversation_duration_seconds(row)
    assert wall == pytest.approx(vad_lead + speech) and span == pytest.approx(wall)
    # Twelve words spread over that span meet the floor on neither measure...
    assert not below_short_clip_floor(words=12, speech_seconds=span)

    # ...while a genuinely 2-second clip is sub-floor even when the recognizer
    # packed a dozen words into it, and even if its wall window collapses.
    assert below_short_clip_floor(words=12, speech_seconds=2.0)
    assert below_short_clip_floor(words=12, speech_seconds=speech_seconds(_segments(12, start=0.0, end=2.0)))
