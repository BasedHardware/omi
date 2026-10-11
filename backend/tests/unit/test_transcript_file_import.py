"""Transcript-file import: bring conversations recorded elsewhere into Omi.

Exports from other recorders and meeting tools arrive as SRT, WebVTT or plain
text transcripts, alone or zipped. Like the Limitless importer this is a light
import: parse, store the transcript as a completed conversation, no AI. These
tests pin the parsers, speaker and people mapping, deterministic idempotent IDs,
upload limits, and the job lifecycle.
"""

import asyncio
import codecs
import inspect
import io
import re
import struct
import threading
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_LZMA, ZIP_STORED, ZipFile

import pytest

import database.auth as auth_db
import database.conversations as conversations_db
from models.conversation_enums import ConversationSource
from models.import_job import ImportJobStatus, ImportSourceType
from utils.imports import transcript_files as tf
from utils.notification_dispatch import NotificationDispatchOutcome, NotificationDispatchStatus

UID = 'user-abc'

SRT = (
    '﻿1\r\n'
    '00:00:01,000 --> 00:00:04,500\r\n'
    'Jane Doe: Morning, did the vendor send the quote?\r\n'
    '\r\n'
    '2\r\n'
    '00:00:05,000 --> 00:00:09,000\r\n'
    'Sam: Yes, it came in at twelve thousand\r\n'
    'for the whole year.\r\n'
    '\r\n'
    '3\r\n'
    '00:00:09,500 --> 00:00:12,000\r\n'
    'Jane Doe: Then we sign it this week.\r\n'
    '\r\n'
    '4\r\n'
    '00:00:12,000 --> 00:00:13,000\r\n'
    'Sam: Agreed.\r\n'
)

VTT = (
    'WEBVTT\n'
    '\n'
    'NOTE exported by a meeting tool\n'
    '\n'
    'cue-1\n'
    '00:01.000 --> 00:03.250\n'
    '<v Jane Doe>Let us start with the roadmap.</v>\n'
    '\n'
    '00:00:03.500 --> 00:00:06.000 align:start\n'
    '<v.loud Sam>The <c.yellow>beta</c> ships on Monday.\n'
)

OTTER_STYLE_TXT = (
    'Jane Doe  0:03\n'
    'Morning everyone, quick sync on hiring.\n'
    '\n'
    'Speaker 2  0:15\n'
    'We have two finalists for the design role.\n'
    'Both interviews are done.\n'
    '\n'
    'Jane Doe  1:02:05\n'
    'Great, let us decide by Friday.\n'
)

INLINE_TXT = (
    '[00:00:02] Jane Doe: Did you book the venue?\n'
    '[00:00:06] Sam: Booked it for the twelfth.\n'
    '[00:00:09] Jane Doe: Perfect, thanks.\n'
)

PARAGRAPHS_TXT = 'Picked up groceries and called the bank.\n\nNeed to renew the car insurance before March.\n'


# --------------------------------------------------------------------------- parsers


def test_srt_parses_times_multiline_text_and_recurring_speakers():
    cues = tf.parse_srt(SRT)

    assert [(c.speaker, c.start, c.end) for c in cues] == [
        ('Jane Doe', 1.0, 4.5),
        ('Sam', 5.0, 9.0),
        ('Jane Doe', 9.5, 12.0),
        ('Sam', 12.0, 13.0),
    ]
    assert cues[1].text == 'Yes, it came in at twelve thousand for the whole year.'


@pytest.mark.parametrize('extension', ['.srt', '.txt'])
@pytest.mark.parametrize(
    'srt',
    [
        pytest.param(
            '1\n00:00:01,000 --> 00:00:02,000\n<i>Alice: Hello\nthere</i>\n\n'
            '2\n00:00:02,000 --> 00:00:03,000\n<font color="#ffff00">Bob: Hi</font>\n\n'
            '3\n00:00:03,000 --> 00:00:04,000\n<b>Alice:</b> Ok &amp; thanks\n',
            id='text-below-timing',
        ),
        pytest.param(
            '00:00:01,000 --> 00:00:02,000 <i>Alice: Hello there</i>\n'
            '00:00:02,000 --> 00:00:03,000 <font color="#ffff00">Bob: Hi</font>\n'
            '00:00:03,000 --> 00:00:04,000 <b>Alice:</b> Ok &amp; thanks\n',
            id='one-line-cues',
        ),
    ],
)
def test_srt_formatting_tags_are_removed_before_speaker_labels_are_read(srt, extension):
    """SRT allows <i>, <b>, <u> and <font> around cue text; they are markup, never words or names."""
    parsed = tf.parse_transcript_file(f'call{extension}', srt.encode('utf-8'))

    assert parsed is not None
    assert [(cue.speaker, cue.text) for cue in parsed.cues] == [
        ('Alice', 'Hello there'),
        ('Bob', 'Hi'),
        ('Alice', 'Ok & thanks'),
    ]


@pytest.mark.parametrize('extension', ['.srt', '.txt'])
def test_srt_angle_brackets_and_ampersands_that_are_not_markup_stay_words(extension):
    """Only SRT's own tags (<i>, <b>, <u>, <s>, <font>) are markup; "x < 10" and "<-" are words."""
    srt = (
        '1\n00:00:01,000 --> 00:00:02,000\nAlice: if x < 10 and y > 5 we ship\n\n'
        '2\n00:00:02,000 --> 00:00:03,000\nBob: the arrow <- goes\nback -> here\n\n'
        '3\n00:00:03,000 --> 00:00:04,000\nAlice: meeting&notes, R&amp;D and &amp;lt;b&amp;gt;\n'
    )

    parsed = tf.parse_transcript_file(f'call{extension}', srt.encode('utf-8'))

    assert parsed is not None
    assert [(cue.speaker, cue.text) for cue in parsed.cues] == [
        ('Alice', 'if x < 10 and y > 5 we ship'),
        ('Bob', 'the arrow <- goes back -> here'),
        # An entity needs its ';' ("&not" is not one here), and text is unescaped exactly once.
        ('Alice', 'meeting&notes, R&D and &lt;b&gt;'),
    ]


def test_a_vtt_voice_name_is_unescaped_so_it_can_bind():
    vtt = 'WEBVTT\n\n00:01.000 --> 00:02.000\n<v Tom &amp; Jerry>hello</v>\n'

    cues = tf.parse_vtt(vtt)
    segments = tf.segments_from_cues(cues, owner_name=None, people={'tom & jerry': 'person-tj'})

    assert [cue.speaker for cue in cues] == ['Tom & Jerry']
    assert [(s.text, s.person_id) for s in segments] == [('hello', 'person-tj')]


@pytest.mark.parametrize('body', ['Alice: hello', 'alice: hello'])
def test_a_name_the_text_already_opens_with_is_not_repeated(body):
    """A voice-tagged cue may also write its speaker's label; the unbound name is kept once."""
    vtt = f'WEBVTT\n\n00:01.000 --> 00:02.000\n<v Alice>{body}</v>\n'

    segments = tf.segments_from_cues(tf.parse_vtt(vtt), owner_name='Jane Doe', people={})

    assert [s.text for s in segments] == [body]


def test_one_off_label_in_unlabeled_file_is_text_but_speaker_n_is_a_speaker():
    srt = (
        '1\n00:00:00,000 --> 00:00:01,000\nLet us go over the plan.\n\n'
        '2\n00:00:01,000 --> 00:00:02,000\nNote: bring the contract\n\n'
        '3\n00:00:02,000 --> 00:00:03,000\nSpeaker 3: ok\n\n'
        '4\n00:00:03,000 --> 00:00:04,000\nSounds good.\n'
    )

    cues = tf.parse_srt(srt)

    assert (cues[1].speaker, cues[1].text) == (None, 'Note: bring the contract')
    assert (cues[2].speaker, cues[2].text) == ('Speaker 3', 'ok')
    assert cues[0].speaker is None and cues[3].speaker is None


def test_vtt_skips_header_notes_and_ids_and_reads_voice_tags():
    cues = tf.parse_vtt(VTT)

    assert [(c.speaker, c.start, c.end, c.text) for c in cues] == [
        ('Jane Doe', 1.0, 3.25, 'Let us start with the roadmap.'),
        ('Sam', 3.5, 6.0, 'The beta ships on Monday.'),
    ]


def test_each_voice_span_in_a_vtt_cue_keeps_its_own_speaker():
    """WebVTT scopes a voice to its span, so a two-voice cue is two turns, not one under the first voice."""
    data = (
        b'WEBVTT\n\n00:01.000 --> 00:05.000\n' b'<v Alice Doe>Can we ship?</v> <v Bob Smith>No, wait for review.</v>\n'
    )
    parsed = tf.parse_transcript_file('standup.vtt', data)
    assert parsed is not None

    conversation = tf.build_imported_conversation(
        UID,
        parsed,
        data,
        source=ConversationSource.unknown,
        language_code='en',
        owner_name='Alice Doe',
        people={'bob smith': 'person-bob'},
        fallback_started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    segments = conversation.transcript_segments
    assert [(s.text, s.is_user, s.person_id) for s in segments] == [
        ('Can we ship?', True, None),
        ('No, wait for review.', False, 'person-bob'),
    ]
    assert segments[0].speaker_id != segments[1].speaker_id
    # The cue's range is shared out by word count (3 of 7 words, then 4 of 7), in order.
    assert (segments[0].start, segments[1].end) == (1.0, 5.0)
    assert segments[0].end == segments[1].start == pytest.approx(1.0 + 4.0 * 3 / 7, abs=0.001)


@pytest.mark.parametrize(
    ('cue', 'expected'),
    [
        pytest.param(
            'So, <v Bob>hi there</v> and then <v Carol &amp; Co>bye</v>',
            [(None, 'So,'), ('Bob', 'hi there'), (None, 'and then'), ('Carol & Co', 'bye')],
            id='unvoiced-text-around-the-spans',
        ),
        pytest.param(
            '<v Alice>Hi <v Bob>Hello',
            [('Alice', 'Hi'), ('Bob', 'Hello')],
            id='unclosed-voices',
        ),
        pytest.param(
            '<v Alice>Hi <b>all</b></v> <v Alice>and welcome</v>',
            [('Alice', 'Hi all and welcome')],
            id='adjacent-spans-of-one-voice-merge',
        ),
        pytest.param(
            '<v Speaker 1>Hi</v><v.loud Bob>Alice: <i>hey</i></v>',
            [('Speaker 1', 'Hi'), ('Bob', 'Alice: hey')],
            id='classes-and-formatting-tags',
        ),
    ],
)
def test_vtt_voice_spans_split_a_cue_into_runs(cue, expected):
    cues = tf.parse_vtt(f'WEBVTT\n\n00:00:10.000 --> 00:00:20.000\n{cue}\n')

    assert [(c.speaker, c.text) for c in cues] == expected
    assert cues[0].start == 10.0 and cues[-1].end == 20.0
    assert all(a.end == b.start for a, b in zip(cues, cues[1:]))


def test_punctuation_between_voice_spans_is_not_a_speakerless_turn():
    """Exporters mark each voice with a dash; the dash is not a third, unnamed speaker."""
    vtt = 'WEBVTT\n\n00:00:10.000 --> 00:00:20.000\n- <v Alice>Hi there</v>\n- <v Bob>Yo</v>\n'

    cues = tf.parse_vtt(vtt)
    segments = tf.segments_from_cues(cues, owner_name='Alice', people={'bob': 'person-bob'})

    assert [(c.speaker, c.text) for c in cues] == [('Alice', 'Hi there'), ('Bob', 'Yo')]
    assert [(s.speaker_id, s.is_user, s.person_id) for s in segments] == [(0, True, None), (1, False, 'person-bob')]


def test_a_cue_with_no_words_at_all_keeps_its_text():
    cues = tf.parse_vtt('WEBVTT\n\n00:00:10.000 --> 00:00:20.000\n\u266a \u266a\n')

    assert [(c.speaker, c.text) for c in cues] == [(None, '\u266a \u266a')]


def test_a_cue_too_short_to_share_out_keeps_its_timing_on_each_run():
    """Millisecond slices would round to an empty run: no run is ever zero-length."""
    vtt = 'WEBVTT\n\n00:00:01.000 --> 00:00:01.002\n<v A>one</v> <v B>two</v> <v C>three</v>\n'

    cues = tf.parse_vtt(vtt)

    assert [c.speaker for c in cues] == ['A', 'B', 'C']
    assert all(c.end > c.start for c in cues)
    assert {(c.start, c.end) for c in cues} == {(1.0, 1.002)}


@pytest.mark.parametrize('cue_count', [1, 4], ids=['one-cue', 'across-cues'])
def test_splitting_voices_stops_once_the_file_is_over_the_segment_cap(monkeypatch, cue_count):
    monkeypatch.setattr(tf, 'MAX_TRANSCRIPT_SEGMENTS', 3)
    voices = ''.join(f'<v S{index}>w{index}</v>' for index in range(4 // cue_count))
    cue = f'00:00:01.000 --> 00:00:02.000\n{voices}\n'
    vtt = 'WEBVTT\n\n' + '\n'.join([cue] * cue_count)

    with pytest.raises(tf.TranscriptFileSkipped) as skipped:
        tf.parse_transcript_file('call.vtt', vtt.encode('utf-8'))

    assert skipped.value.reason == tf.TRANSCRIPT_TOO_LONG


def test_a_cue_of_many_voice_spans_is_refused_in_linear_time():
    vtt = 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n' + '<v A>x</v>-' * 200_000 + '\n'
    started = time.perf_counter()

    with pytest.raises(tf.TranscriptFileSkipped):
        tf.parse_transcript_file('call.vtt', vtt.encode('utf-8'))

    assert time.perf_counter() - started < 1.0


def test_a_voice_split_cue_without_a_usable_range_keeps_its_timing_on_each_run():
    cues = tf.parse_vtt('WEBVTT\n\n00:00:20.000 --> 00:00:10.000\n<v Alice>Hi</v> <v Bob>Hello</v>\n')

    assert [(c.speaker, c.start, c.end) for c in cues] == [('Alice', 20.0, 10.0), ('Bob', 20.0, 10.0)]


def test_otter_style_header_lines_start_timed_speaker_turns():
    cues = tf.parse_text_transcript(OTTER_STYLE_TXT)

    assert [(c.speaker, c.start) for c in cues] == [('Jane Doe', 3.0), ('Speaker 2', 15.0), ('Jane Doe', 3725.0)]
    assert cues[1].text == 'We have two finalists for the design role. Both interviews are done.'


def test_inline_timestamped_lines_carry_speaker_and_time():
    cues = tf.parse_text_transcript(INLINE_TXT)

    assert [(c.speaker, c.start, c.text) for c in cues] == [
        ('Jane Doe', 2.0, 'Did you book the venue?'),
        ('Sam', 6.0, 'Booked it for the twelfth.'),
        ('Jane Doe', 9.0, 'Perfect, thanks.'),
    ]


def test_inline_timestamped_text_lines_are_not_speaker_headers():
    """A time-first line names a speaker only when an untimed body line follows it."""
    cues = tf.parse_text_transcript('[00:01] Hello there\n[00:05] How are you doing\n[00:09] Fine thanks\n')

    assert [(c.speaker, c.start, c.text) for c in cues] == [
        (None, 1.0, 'Hello there'),
        (None, 5.0, 'How are you doing'),
        (None, 9.0, 'Fine thanks'),
    ]


def test_time_first_header_lines_start_turns_when_an_untimed_body_follows():
    cues = tf.parse_text_transcript('[00:01] Jane Doe\nMorning everyone.\n\n[00:05] Sam\nMorning.\n')

    assert [(c.speaker, c.start, c.text) for c in cues] == [
        ('Jane Doe', 1.0, 'Morning everyone.'),
        ('Sam', 5.0, 'Morning.'),
    ]


def test_mixed_inline_transcript_keeps_every_line():
    text = (
        '[00:01] Jane Doe: Did you book the venue?\n'
        '[00:05] Sounds good\n'
        '[00:09] Sam: Booked it for the twelfth.\n'
    )

    cues = tf.parse_text_transcript(text)

    assert [(c.speaker, c.start, c.text) for c in cues] == [
        ('Jane Doe', 1.0, 'Did you book the venue?'),
        (None, 5.0, 'Sounds good'),
        ('Sam', 9.0, 'Booked it for the twelfth.'),
    ]


def test_speaker_header_file_keeps_timed_body_lines_and_bodiless_headers():
    text = 'Jane Doe  0:03\nDoes Friday work?\n\nSam  0:10\n10:30 works for me\n\nJane Doe  0:15\n'

    cues = tf.parse_text_transcript(text)

    assert [(c.speaker, c.start, c.text) for c in cues] == [
        ('Jane Doe', 3.0, 'Does Friday work?'),
        ('Sam', 10.0, '10:30 works for me'),
        (None, 15.0, 'Jane Doe'),
    ]


def test_plain_paragraphs_become_untimed_cues_without_speakers():
    cues = tf.parse_text_transcript(PARAGRAPHS_TXT)

    assert [(c.speaker, c.start, c.text) for c in cues] == [
        (None, None, 'Picked up groceries and called the bank.'),
        (None, None, 'Need to renew the car insurance before March.'),
    ]


_VTT_CUE = 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n'


@pytest.mark.parametrize(
    ('filename', 'text'),
    [
        pytest.param('notes.txt', 'a' + ' ' * 200_000 + 'b', id='txt-header-whitespace-run'),
        pytest.param('notes.txt', 'Jane' + ' ' * 200_000 + '0:0', id='txt-header-almost-timestamp'),
        pytest.param('notes.txt', 'a:' + ' ' * 200_000, id='txt-label-whitespace-run'),
        pytest.param('call.vtt', _VTT_CUE + '<' * 200_000, id='vtt-unclosed-tags'),
        pytest.param('call.vtt', _VTT_CUE + '<v a' * 50_000, id='vtt-unclosed-voices'),
        pytest.param('call.vtt', _VTT_CUE + '<v' + ' ' * 200_000 + 'x', id='vtt-voice-whitespace-run'),
    ],
)
def test_pathological_lines_parse_in_linear_time(filename, text):
    """A crafted line must not pin the worker (and the GIL) in regex backtracking."""
    started = time.perf_counter()

    tf.parse_transcript_file(filename, text.encode('utf-8'))

    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize(
    ('filename', 'data'),
    [
        ('audio.mp3', b'ID3\x03\x00'),
        ('notes.srt', b'\x00\x01\x02binary'),
        ('truncated-utf16.srt', codecs.BOM_UTF16_LE + b'1'),
        ('binary-utf16.srt', codecs.BOM_UTF16_LE + b'\x00\x00\x01\x00'),
        ('empty.txt', b'   \n\n'),
    ],
)
def test_unsupported_binary_or_empty_files_are_not_transcripts(filename, data):
    assert tf.parse_transcript_file(filename, data) is None


@pytest.mark.parametrize(
    ('encoding', 'bom'),
    [('utf-16-le', codecs.BOM_UTF16_LE), ('utf-16-be', codecs.BOM_UTF16_BE)],
)
def test_utf16_transcripts_are_decoded_not_mistaken_for_binary(encoding, bom):
    """Windows tools export UTF-16, whose every ASCII character carries a NUL byte."""
    parsed = tf.parse_transcript_file('call.srt', bom + SRT.lstrip('\ufeff').encode(encoding))

    assert parsed is not None
    assert [(c.speaker, c.start) for c in parsed.cues] == [
        ('Jane Doe', 1.0),
        ('Sam', 5.0),
        ('Jane Doe', 9.5),
        ('Sam', 12.0),
    ]
    assert parsed.cues[0].text == 'Morning, did the vendor send the quote?'


def test_a_numbered_srt_saved_as_txt_is_read_as_srt():
    as_srt = tf.parse_transcript_file('call.srt', SRT.encode('utf-8'))
    as_txt = tf.parse_transcript_file('call.txt', SRT.encode('utf-8'))

    assert as_srt is not None and as_txt is not None
    assert as_txt.cues == as_srt.cues


@pytest.mark.parametrize(
    'text',
    [
        pytest.param(
            'Call with Acme, notes\n\n00:01:02,000 --> 00:01:09,000\nClip: customer said onboarding was confusing.\n\n'
            'Alice: we should simplify step two.\nBob: agreed, I will draft a proposal.\nAlice: great, review Friday.\n',
            id='notes-quoting-one-clip',
        ),
        pytest.param(
            'Weekly sync\nAgenda\n10:00 --> 10:15 Updates\n10:15 --> 10:30 Roadmap\n\n'
            'Alice: hi everyone.\nBob: morning.\nAlice: let us start.\n',
            id='agenda-with-times',
        ),
    ],
)
def test_a_txt_that_only_mentions_a_cue_timing_is_not_read_as_srt(text):
    """Only a file that opens like SRT is SRT; parsing other text as SRT would drop most of it."""
    parsed = tf.parse_transcript_file('notes.txt', text.encode('utf-8'))

    assert parsed is not None
    assert {'Alice', 'Bob'} <= {cue.speaker for cue in parsed.cues}


@pytest.mark.parametrize(
    'preface',
    ['Weekly sync transcript\n\n', 'SRT\n\n', 'Exported by Recorder\nDate: 2026-09-12\n\n', '\n\n  \n'],
    ids=['title', 'format-line', 'header-block', 'blank-lines'],
)
def test_an_srt_saved_as_txt_after_a_preface_is_still_read_as_srt(preface):
    """The cues keep their timings and speakers; a .txt never drops the preface's words."""
    srt = '1\n00:00:01,000 --> 00:00:04,000\nAlice: Hello there.\n\n2\n00:00:05,000 --> 00:00:08,000\nBob: Hi Alice.\n'

    as_txt = tf.parse_transcript_file('x.txt', (preface + srt).encode('utf-8'))

    assert as_txt is not None
    timed = [(cue.speaker, cue.start, cue.text) for cue in as_txt.cues if cue.start is not None]
    assert timed == [('Alice', 1.0, 'Hello there.'), ('Bob', 5.0, 'Hi Alice.')]
    untimed = [f'{cue.speaker}: {cue.text}' if cue.speaker else cue.text for cue in as_txt.cues if cue.start is None]
    assert ' '.join(untimed).split() == preface.split()


@pytest.mark.parametrize(
    'text',
    [
        pytest.param(
            '00:01:02,000 --> 00:01:09,000\nClip: customer said onboarding was confusing.\n\n'
            'Alice: we should simplify step two.\nBob: agreed, I will draft a proposal.\nAlice: great, review Friday.\n',
            id='clip-first',
        ),
        pytest.param(
            '10:00 --> 10:15 Updates\n10:15 --> 10:30 Roadmap\n\nAlice: hi everyone.\nBob: morning.\nAlice: let us start.\n',
            id='agenda-first',
        ),
    ],
)
def test_notes_that_open_with_a_quoted_timing_keep_every_turn(text):
    parsed = tf.parse_transcript_file('notes.txt', text.encode('utf-8'))

    assert parsed is not None
    assert {'Alice', 'Bob'} <= {cue.speaker for cue in parsed.cues}


@pytest.mark.parametrize(
    'text',
    [
        pytest.param(
            '00:00:01.000 --> 00:00:05.000 Hello there.\n\n00:00:05.000 --> 00:00:09.000 Hi Alice.\n',
            id='one-line-cues',
        ),
        pytest.param(
            '[00:00:01.000 --> 00:00:05.000]   Hello there.\n[00:00:05.000 --> 00:00:09.000]   Hi Alice.\n',
            id='whisper-cpp',
        ),
    ],
)
def test_one_line_timed_cues_keep_their_text_and_start(text):
    parsed = tf.parse_transcript_file('call.txt', text.encode('utf-8'))

    assert parsed is not None
    assert [(cue.text, cue.start) for cue in parsed.cues] == [('Hello there.', 1.0), ('Hi Alice.', 5.0)]


@pytest.mark.parametrize(
    'text',
    [
        pytest.param(
            'Interview notes\nAlice: we should simplify step two.\n\n00:01:02,000 --> 00:01:09,000\n'
            'customer said onboarding was confusing.\n\n00:03:10,000 --> 00:03:15,000\npricing page is unclear.\n',
            id='notes-then-two-clips',
        ),
        pytest.param(
            'Interview notes\n\n00:01:02,000 --> 00:01:09,000\nonboarding was confusing.\n\n'
            'Alice: we should simplify step two.\nBob: agreed.\n\n00:03:10,000 --> 00:03:15,000\n'
            'pricing page is unclear.\n\n00:05:00,000 --> 00:05:04,000\ncheckout is slow.\n',
            id='mostly-clips-with-a-discussion',
        ),
        pytest.param(
            'Clip\n00:24:21,000 --> 00:24:47,000\nshipping is on track\n\nQuote:\n00:28:22,000 --> 00:28:27,000\n\n'
            '00:31:00,000 --> 00:31:05,000\nhiring is paused\n',
            id='labels-above-timings',
        ),
    ],
)
def test_a_mostly_timed_txt_keeps_its_untimed_blocks(text):
    """However a .txt is routed, every word in it reaches the transcript."""
    parsed = tf.parse_transcript_file('notes.txt', text.encode('utf-8'))

    assert parsed is not None
    kept = ' '.join(f'{cue.speaker}: {cue.text}' if cue.speaker else cue.text for cue in parsed.cues).split()
    words = [word for word in text.split() if word != '-->' and not re.fullmatch(r'[\d:,]+', word)]
    assert sorted(kept) == sorted(words)


@pytest.mark.parametrize('extension', ['.txt', '.srt'])
def test_one_line_cues_without_blank_lines_each_become_a_cue(extension):
    text = '00:00:01.000 --> 00:00:05.000 Hello there.\n00:00:05.000 --> 00:00:09.000 Hi Alice.\n'

    parsed = tf.parse_transcript_file(f'call{extension}', text.encode('utf-8'))

    assert parsed is not None
    assert [(cue.text, cue.start, cue.end) for cue in parsed.cues] == [
        ('Hello there.', 1.0, 5.0),
        ('Hi Alice.', 5.0, 9.0),
    ]


@pytest.mark.parametrize(
    'line',
    ['00:00:01,000 --> 00:00:04,000', '[00:00:00.000 --> 00:00:05.000]'],
    ids=['srt-timing', 'whisper-empty-segment'],
)
def test_a_bare_cue_timing_line_never_becomes_a_fragment_of_its_end_time(line):
    match = tf._INLINE_TIMED_RE.match(line)

    assert match is None or match.group('rest') not in ('0', ']', '0]')


def test_empty_whisper_segments_add_nothing_to_the_cue_before_them():
    text = (
        '[00:00.000 --> 00:04.000]   thanks everyone\n\n[00:04.000 --> 00:08.000]   let us start\n\n'
        '[00:08.000 --> 00:12.000]\n\n[00:12.000 --> 00:16.000]\n'
    )

    parsed = tf.parse_transcript_file('whisper.txt', text.encode('utf-8'))

    assert parsed is not None
    assert [(cue.text, cue.start) for cue in parsed.cues] == [('thanks everyone', 0.0), ('let us start', 4.0)]


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        pytest.param(
            '[00:00:00.000 --> 00:00:04.000]\n[00:00:04.000 --> 00:00:08.000]  Hello there\n'
            '[00:00:08.000 --> 00:00:09.000]\n',
            [(None, 'Hello there', 4.0)],
            id='as-many-empty-segments-as-spoken',
        ),
        pytest.param(
            'Weekly sync\n[00:00:01.000 --> 00:00:02.000]  Alice: hi\n[00:00:02.000 --> 00:00:03.000]\n'
            '[00:00:03.000 --> 00:00:04.000]  Bob: hello\n[00:00:04.000 --> 00:00:05.000]\n',
            [(None, 'Weekly sync', None), ('Alice', 'hi', 1.0), ('Bob', 'hello', 3.0)],
            id='title-and-empty-segments',
        ),
        pytest.param(
            '[00:00:01.000 --> 00:00:04.000]\nHello there\n[00:00:04.000 --> 00:00:08.000]\nHi Alice\n',
            [(None, 'Hello there', 1.0), (None, 'Hi Alice', 4.0)],
            id='timing-lines-with-text-below',
        ),
        pytest.param(
            'Weekly sync\n2026-09-12\n[00:00:01] Alice: Hi all\n[00:00:05] Bob: Hello\n',
            [(None, 'Weekly sync 2026-09-12', None), ('Alice', 'Hi all', 1.0), ('Bob', 'Hello', 5.0)],
            id='title-above-inline-timestamps',
        ),
    ],
)
def test_inline_timed_text_keeps_its_timings_and_every_word(text, expected):
    parsed = tf.parse_transcript_file('call.txt', text.encode('utf-8'))

    assert parsed is not None
    assert [(cue.speaker, cue.text, cue.start) for cue in parsed.cues] == expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        pytest.param(
            '[00:01.000 --> 00:07.000] Alice: Hello\n',
            [(1.0, 7.0)],
            id='the-final-turn-keeps-its-end',
        ),
        pytest.param(
            '[00:00.000 --> 00:02.000] Alice: Hello\n[00:20.000 --> 00:27.500] Bob: Hi again\n',
            [(0.0, 2.0), (20.0, 27.5)],
            id='a-gap-between-turns-stays-a-gap',
        ),
        pytest.param(
            '[00:00:01.000 --> 00:00:04.000]\nHello there\n[00:00:10.000 --> 00:00:12.000]\nHi Alice\n',
            [(1.0, 4.0), (10.0, 12.0)],
            id='timing-lines-with-text-below',
        ),
        pytest.param(
            # An end at or before the start is not a usable end: the next turn closes the turn,
            # and the last turn gets its estimate, as for a timing without one.
            '[00:05.000 --> 00:03.000] Alice: Hello\n[00:09.000 --> 00:09.000] Bob: Hi\n',
            [(5.0, 9.0), (9.0, 10.0)],
            id='an-end-before-its-start-is-ignored',
        ),
        pytest.param(
            '[00:00:02] Alice: Hello\n[00:00:06] Bob: Hi\n',
            [(2.0, 6.0), (6.0, 7.0)],
            id='no-end-closes-at-the-next-turn',
        ),
    ],
)
def test_an_inline_timing_keeps_its_explicit_end(text, expected):
    """whisper.cpp writes "[start --> end]": the end is the source's, not an estimate."""
    parsed = tf.parse_transcript_file('whisper.txt', text.encode('utf-8'))

    assert parsed is not None
    segments = tf.segments_from_cues(parsed.cues, owner_name=None, people={})
    assert [(s.start, s.end) for s in segments] == expected


def test_an_explicit_txt_end_sets_the_conversation_duration():
    data = b'[00:00.000 --> 00:02.000] Alice: Hello\n[00:20.000 --> 00:27.000] Bob: Hi again\n'
    parsed = tf.parse_transcript_file('whisper.txt', data)
    assert parsed is not None
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    conversation = tf.build_imported_conversation(
        UID,
        parsed,
        data,
        source=ConversationSource.unknown,
        language_code='en',
        owner_name=None,
        people={},
        fallback_started_at=started,
    )

    assert (conversation.finished_at - started).total_seconds() == 27.0


@pytest.mark.parametrize(
    'text',
    [
        pytest.param(
            'Alice: Hello there everyone\nand welcome to the call\nBob: Thanks for having me\nAlice: Let us start\n'
            'Bob: Sure thing\n',
            id='a-wrapped-turn',
        ),
        pytest.param(
            'Weekly sync\nAlice: Hello there everyone\nBob: Thanks for having me\nAlice: Let us start\n',
            id='a-title-above',
        ),
    ],
)
def test_a_labeled_transcript_keeps_its_speakers(text):
    parsed = tf.parse_transcript_file('call.txt', text.encode('utf-8'))

    assert parsed is not None
    assert {'Alice', 'Bob'} <= {cue.speaker for cue in parsed.cues}
    assert all(not (cue.speaker or '').startswith('Weekly') for cue in parsed.cues)


@pytest.mark.parametrize('body', ['Note:see you then', 'see http://x.io/a', 'B:c'])
def test_one_line_cue_text_that_looks_like_a_setting_is_kept(body):
    text = f'00:00:01,000 --> 00:00:04,000 {body}\n\n00:00:05,000 --> 00:00:06,000 bye\n'

    parsed = tf.parse_transcript_file('call.srt', text.encode('utf-8'))

    assert parsed is not None
    assert [cue.text for cue in parsed.cues] == [body, 'bye']


@pytest.mark.parametrize('settings', [' X1:100 X2:200 Y1:10 Y2:20', ' align:start position:10%', ''])
def test_real_cue_settings_are_not_cue_text(settings):
    text = f'1\n00:00:01,000 --> 00:00:04,000{settings}\nHello there\n'

    parsed = tf.parse_transcript_file('call.srt', text.encode('utf-8'))

    assert parsed is not None
    assert [(cue.text, cue.start) for cue in parsed.cues] == [('Hello there', 1.0)]


def test_a_bom_survives_neither_utf8_nor_the_cp1252_fallback():
    data = codecs.BOM_UTF8 + '00:00:01,000 --> 00:00:02,000\nJos\u00e9: hola.\n\n'.encode('cp1252')
    data += '00:00:03,000 --> 00:00:04,000\nAna: buenas.\n'.encode('cp1252')

    parsed = tf.parse_transcript_file('call.srt', data)

    assert parsed is not None
    assert [(cue.speaker, cue.text) for cue in parsed.cues] == [('Jos\u00e9', 'hola.'), ('Ana', 'buenas.')]


def test_a_txt_that_opens_like_srt_but_holds_no_cues_is_read_as_text():
    text = '00:00:01,000 --> 00:00:02,000\n\nAlice: hi there.\nBob: hello.\nAlice: shall we start?\n'

    parsed = tf.parse_transcript_file('notes.txt', text.encode('utf-8'))

    assert parsed is not None
    assert {'Alice', 'Bob'} <= {cue.speaker for cue in parsed.cues}


def test_file_dispatch_uses_extension_title_and_filename_date():
    parsed = tf.parse_transcript_file('2026-09-12 14_30_05 Vendor quote call.srt', SRT.encode('utf-8'), tz='UTC')

    assert parsed is not None
    assert parsed.title == 'Vendor quote call'
    assert parsed.started_at == datetime(2026, 9, 12, 14, 30, 5, tzinfo=timezone.utc)
    assert len(parsed.cues) == 4


@pytest.mark.parametrize(
    ('filename', 'tz', 'expected'),
    [
        ('20260912_143005.txt', 'UTC', datetime(2026, 9, 12, 14, 30, 5, tzinfo=timezone.utc)),
        ('Sync 2026-09-12T09-15.vtt', 'America/New_York', datetime(2026, 9, 12, 13, 15, tzinfo=timezone.utc)),
        ('2026-02-30 10_00 bad date.txt', 'UTC', None),
        ('Weekly sync.txt', 'UTC', None),
        ('0001-01-01 00_00 call.txt', 'Asia/Tokyo', None),
        ('9999-12-31 23_59 call.txt', 'America/Adak', None),
        ('1970-01-01 00_00 unset clock.txt', 'UTC', None),
        ('19891231_235959.txt', 'UTC', None),
        ('19900101_000000.txt', 'UTC', datetime(1990, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_started_at_from_filename(filename, tz, expected):
    assert tf.started_at_from_filename(filename, tz) == expected


def test_out_of_range_filename_date_falls_back_instead_of_failing_the_file():
    parsed = tf.parse_transcript_file('0001-01-01 00_00 call.srt', SRT.encode('utf-8'), tz='Asia/Tokyo')

    assert parsed is not None
    assert parsed.started_at is None
    assert len(parsed.cues) == 4


@pytest.mark.parametrize(
    ('filename', 'title'),
    [
        ('2026-09-12 14_30_05 Vendor quote call.srt', 'Vendor quote call'),
        ('exports/team-standup_notes.vtt', 'team standup notes'),
        ('20260912_143005.txt', 'Imported transcript'),
    ],
)
def test_title_from_filename(filename, title):
    assert tf.title_from_filename(filename) == title


# --------------------------------------------------------------------------- segments


def test_segments_number_speakers_and_match_owner_and_people():
    cues = tf.parse_srt(SRT)

    segments = tf.segments_from_cues(cues, owner_name='jane doe', people={'sam': 'person-sam'})

    assert [(s.speaker_id, s.speaker, s.is_user, s.person_id) for s in segments] == [
        (0, 'SPEAKER_00', True, None),
        (1, 'SPEAKER_01', False, 'person-sam'),
        (0, 'SPEAKER_00', True, None),
        (1, 'SPEAKER_01', False, 'person-sam'),
    ]
    assert [(s.start, s.end) for s in segments] == [(1.0, 4.5), (5.0, 9.0), (9.5, 12.0), (12.0, 13.0)]


@pytest.mark.parametrize(
    ('owner_name', 'label', 'is_owner'),
    [
        pytest.param('Jane Doe', 'Jane Doe', True, id='full-name'),
        pytest.param('Jane  Doe ', 'jane doe', True, id='case-and-spacing'),
        pytest.param('Jane Doe', 'Jane   Doe', True, id='label-spacing'),
        pytest.param('Jane Doe', 'Jane', True, id='first-name-alone'),
        pytest.param('Jane Doe', 'Jane Smith', False, id='another-surname'),
        pytest.param('Jane Doe', 'Doe', False, id='surname-alone'),
        # Only one word is known: "Jane Doe" and "Jane Smith" cannot be told apart.
        pytest.param('Jane', 'Jane', True, id='first-name-only-known'),
        pytest.param('Jane', 'Jane Doe', False, id='full-label-first-name-only-known'),
        pytest.param(None, 'Jane', False, id='owner-unknown'),
    ],
)
def test_the_owner_is_the_whole_name_or_the_first_name_alone(owner_name, label, is_owner):
    cues = [tf.TranscriptCue(text='Hello.', speaker=label), tf.TranscriptCue(text='Hi.', speaker='Sam')]

    segments = tf.segments_from_cues(cues, owner_name=owner_name, people={'jane smith': 'person-jane-smith'})

    assert segments[0].is_user is is_owner
    assert segments[1].is_user is False
    if label == 'Jane Smith':
        assert segments[0].person_id == 'person-jane-smith'
    bound = is_owner or label == 'Jane Smith'
    assert segments[0].text == ('Hello.' if bound else f'{label}: Hello.')
    assert segments[1].text == 'Sam: Hi.'


@pytest.mark.parametrize('order', [1, -1], ids=['as-stored', 'reversed'])
def test_a_name_two_people_share_binds_neither_of_them(monkeypatch, order):
    """A "Sam:" label cannot say which Sam spoke, whichever one Firestore streams first."""
    people = [
        {'id': 'person-sam-1', 'name': 'Sam'},
        {'id': 'person-jo', 'name': 'Jo'},
        {'id': 'person-sam-2', 'name': ' sam '},
        {'id': 'person-nameless', 'name': ''},
    ]
    monkeypatch.setattr(tf.users_db, 'get_people', lambda uid: people[::order])

    names = tf.load_people_names(UID)

    assert names == {'jo': 'person-jo'}
    segments = tf.segments_from_cues(
        [tf.TranscriptCue(text='Hi.', speaker='Sam'), tf.TranscriptCue(text='Hey.', speaker='Jo')],
        owner_name=None,
        people=names,
    )
    assert [s.person_id for s in segments] == [None, 'person-jo']
    assert [s.text for s in segments] == ['Sam: Hi.', 'Hey.'], 'the unbound name stays readable in the text'


@pytest.mark.parametrize(
    ('filename', 'text'),
    [
        pytest.param(
            'call.srt',
            '1\n00:00:01,000 --> 00:00:02,000\nJane Doe: Morning.\n\n'
            '2\n00:00:02,000 --> 00:00:03,000\nSam: Hi.\n\n'
            '3\n00:00:03,000 --> 00:00:04,000\nAlice Chen: Hello.\n',
            id='srt-labels',
        ),
        pytest.param(
            'call.vtt',
            'WEBVTT\n\n00:01.000 --> 00:02.000\n<v Jane Doe>Morning.</v>\n\n'
            '00:02.000 --> 00:03.000\n<v Sam>Hi.</v>\n\n00:03.000 --> 00:04.000\n<v Alice Chen>Hello.</v>\n',
            id='vtt-voices',
        ),
        pytest.param(
            'call.txt',
            'Jane Doe  0:01\nMorning.\n\nSam  0:02\nHi.\n\nAlice Chen  0:03\nHello.\n',
            id='speaker-headers',
        ),
        pytest.param(
            'call.txt',
            '[00:01] Jane Doe: Morning.\n[00:02] Sam: Hi.\n[00:03] Alice Chen: Hello.\n',
            id='inline-timed-labels',
        ),
    ],
)
def test_a_name_leaves_the_text_only_when_it_binds_to_the_owner_or_a_person(filename, text):
    """A segment can name only the owner (is_user) or a person (person_id); any other name stays in its text."""
    parsed = tf.parse_transcript_file(filename, text.encode('utf-8'))
    assert parsed is not None

    segments = tf.segments_from_cues(parsed.cues, owner_name='Jane Doe', people={'sam': 'person-sam'})

    assert [(s.text, s.speaker_id, s.is_user, s.person_id) for s in segments] == [
        ('Morning.', 0, True, None),
        ('Hi.', 1, False, 'person-sam'),
        ('Alice Chen: Hello.', 2, False, None),
    ]


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        pytest.param(
            'Meeting notes for Tuesday.\n\nTODO: send the deck\n\nWe agreed on the scope.\n\nTODO: book the room\n',
            ['Meeting notes for Tuesday.', 'TODO: send the deck', 'We agreed on the scope.', 'TODO: book the room'],
            id='a-recurring-label',
        ),
        pytest.param(
            # Read as speaker headers; each heading's time becomes its turn's start.
            'Weekly sync\n9:00 Budget review\nWe went over the Q3 numbers.\n9:30 Hiring update\nTwo offers are out.\n',
            ['Weekly sync', 'Budget review: We went over the Q3 numbers.', 'Hiring update: Two offers are out.'],
            id='agenda-headings',
        ),
    ],
)
def test_a_label_that_is_not_a_name_never_costs_the_text_a_word(text, expected):
    parsed = tf.parse_transcript_file('notes.txt', text.encode('utf-8'))
    assert parsed is not None

    segments = tf.segments_from_cues(parsed.cues, owner_name='Jane Doe', people={'sam': 'person-sam'})

    assert [s.text for s in segments] == expected


@pytest.mark.parametrize(
    ('label', 'text'),
    [
        pytest.param('Speaker 2', 'hi', id='speaker-n'),
        pytest.param('Speaker 10', 'hi', id='two-digits'),
        pytest.param('SPEAKER_01', 'hi', id='diarization-token'),
        pytest.param('spk 3', 'hi', id='spk'),
        pytest.param('Participant 1', 'hi', id='participant-n'),
        pytest.param('unknown speaker', 'hi', id='unknown-speaker'),
        pytest.param('Speakers', 'Speakers: hi', id='plural-is-a-word'),
        pytest.param('Speaker of the House', 'Speaker of the House: hi', id='a-title'),
        pytest.param('Speaker 2 and Bob', 'Speaker 2 and Bob: hi', id='more-than-a-placeholder'),
        pytest.param('Unknown', 'Unknown: hi', id='unknown-alone'),
    ],
)
def test_a_generic_speaker_placeholder_is_not_kept_in_the_text(label, text):
    """A placeholder names no one: the segment's SPEAKER_NN already records the turn."""
    cues = [tf.TranscriptCue(text='hello', speaker='Alice Chen'), tf.TranscriptCue(text='hi', speaker=label)]

    segments = tf.segments_from_cues(cues, owner_name='Jane Doe', people={'sam': 'person-sam'})

    assert [(s.text, s.speaker_id, s.is_user, s.person_id) for s in segments] == [
        ('Alice Chen: hello', 0, False, None),
        (text, 1, False, None),
    ]


def test_a_placeholder_labeled_file_keeps_its_turns_apart_without_repeating_the_labels():
    text = 'Speaker 1: Morning everyone.\nSpeaker 2: Hi.\nSpeaker 1: Let us start.\n'

    parsed = tf.parse_transcript_file('call.txt', text.encode('utf-8'))
    assert parsed is not None
    segments = tf.segments_from_cues(parsed.cues, owner_name='Jane Doe', people={})

    assert [(s.text, s.speaker_id) for s in segments] == [('Morning everyone.', 0), ('Hi.', 1), ('Let us start.', 0)]


def test_untimed_cues_get_ordered_estimated_times():
    segments = tf.segments_from_cues(tf.parse_text_transcript(PARAGRAPHS_TXT), owner_name=None, people={})

    assert segments[0].start == 0.0
    assert 0.0 < segments[0].end <= segments[1].start < segments[1].end
    assert all(not s.is_user and s.speaker_id == 0 for s in segments)


def test_missing_end_times_close_at_next_turn():
    segments = tf.segments_from_cues(tf.parse_text_transcript(INLINE_TXT), owner_name=None, people={})

    assert [(s.start, s.end) for s in segments[:2]] == [(2.0, 6.0), (6.0, 9.0)]
    assert segments[2].end > segments[2].start


def test_out_of_order_timed_cues_are_sorted_not_clamped():
    srt = (
        '1\n00:00:05,000 --> 00:00:06,000\nSecond thing said.\n\n'
        '2\n00:00:01,000 --> 00:00:02,000\nFirst thing said.\n\n'
        '3\n00:00:07,000 --> 00:00:08,000\nThird thing said.\n'
    )

    segments = tf.segments_from_cues(tf.parse_srt(srt), owner_name=None, people={})

    assert [(s.text, s.start, s.end) for s in segments] == [
        ('First thing said.', 1.0, 2.0),
        ('Second thing said.', 5.0, 6.0),
        ('Third thing said.', 7.0, 8.0),
    ]


def test_sorting_keeps_untimed_cues_after_the_timed_cue_they_follow():
    cues = [
        tf.TranscriptCue(text='Later turn.', speaker='Sam', start=5.0),
        tf.TranscriptCue(text='Still Sam.', speaker='Sam'),
        tf.TranscriptCue(text='Opening turn.', speaker='Jane', start=1.0),
    ]

    segments = tf.segments_from_cues(cues, owner_name=None, people={})

    assert [(s.text, s.speaker_id, s.start) for s in segments] == [
        ('Jane: Opening turn.', 0, 1.0),
        ('Sam: Later turn.', 1, 5.0),
        ('Sam: Still Sam.', 1, segments[1].end),
    ]


def test_many_untimed_cues_build_segments_in_linear_time(monkeypatch):
    """Each untimed cue looks ahead for the next start; that must not rescan the rest.

    A plain record stands in for the segment model so the budget measures the
    look-ahead, not per-segment model validation.
    """
    monkeypatch.setattr(tf, 'TranscriptSegment', SimpleNamespace)
    cues = [tf.TranscriptCue(text='hello there')] * 20_000
    started = time.perf_counter()

    segments = tf.segments_from_cues(cues, owner_name=None, people={})

    assert time.perf_counter() - started < 1.0
    assert len(segments) == 20_000
    assert segments[-1].start >= segments[-2].end


def test_conversation_id_is_deterministic_per_user_and_content():
    first = tf.conversation_id_for_transcript(UID, b'same bytes')

    assert first == tf.conversation_id_for_transcript(UID, b'same bytes')
    assert first != tf.conversation_id_for_transcript('other-user', b'same bytes')
    assert first != tf.conversation_id_for_transcript(UID, b'other bytes')


# --------------------------------------------------------------------------- job


def _firebase_user(display_name):
    return SimpleNamespace(
        uid=UID,
        email=None,
        email_verified=False,
        phone_number=None,
        display_name=display_name,
        photo_url=None,
        disabled=False,
    )


class _Store:
    def __init__(self):
        self.docs = {}

    def persist(self, uid, data):
        if data['id'] in self.docs:
            return False
        self.docs[data['id']] = data
        return True


@pytest.fixture
def job(monkeypatch):
    monkeypatch.setattr(tf.import_quotas_db, 'reserve_import_quota', lambda *_args: 'reservation')
    monkeypatch.setattr(tf.import_quotas_db, 'release_import_quota', lambda *_args: None)
    store = _Store()
    updates: list = []
    state = {'status': ImportJobStatus.pending.value}
    notifications: list = []
    reads: list = []
    deleted: list = []

    def update(job_id, fields):
        updates.append(fields)
        state.update(fields)

    def get(job_id):
        reads.append(dict(state))
        return None if deleted else dict(state)

    def update_unless_cancelled(job_id, fields):
        """The Firestore transaction's read-check-write, atomic here as there."""
        reads.append(dict(state))
        if deleted or state.get('status') == ImportJobStatus.cancelled.value:
            return False
        tf.import_jobs_db.update_import_job(job_id, fields)
        return True

    def update_progress(job_id, fields):
        """Counters only, whatever the status, as the real write; a deleted job stays deleted."""
        assert set(fields) <= tf.import_jobs_db.IMPORT_JOB_PROGRESS_FIELDS
        reads.append(dict(state))
        if deleted:
            return False
        updates.append(fields)
        state.update(fields)
        return True

    monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', store.persist)
    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job', update)
    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job_unless_cancelled', update_unless_cancelled)
    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job_progress', update_progress)
    monkeypatch.setattr(tf.import_jobs_db, 'get_import_job', get)
    # The owner is resolved by the real identity lookup, from a Firebase display name.
    monkeypatch.setattr(auth_db, '_firebase_get_user', lambda uid: _firebase_user('Jane Doe'))
    monkeypatch.setattr(auth_db, 'cache_user_name', lambda *_a, **_k: None)
    monkeypatch.setattr(tf, 'load_people_names', lambda _uid: {'sam': 'person-sam'})

    def dispatch(intent):
        notifications.append(intent)
        return NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=1)

    monkeypatch.setattr(tf, 'dispatch_notification', dispatch)
    return SimpleJob(store, updates, state, notifications, reads, deleted)


class SimpleJob:
    def __init__(self, store, updates, state, notifications, reads, deleted):
        self.store = store
        self.updates = updates
        self.state = state
        self.notifications = notifications
        self.reads = reads
        self._deleted = deleted

    def cancel(self):
        self.state['status'] = ImportJobStatus.cancelled.value

    def delete(self):
        self._deleted.append(True)

    def final_status_writes(self):
        final = (ImportJobStatus.completed.value, ImportJobStatus.failed.value)
        return [u for u in self.updates if u.get('status') in final]

    def final(self):
        return [u for u in self.updates if 'completed_at' in u][-1]


def _zip(files: dict, compression: int = ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, 'w', compression=compression) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _run(tmp_path, name: str, data: bytes, **kwargs):
    path = tmp_path / name
    path.write_bytes(data)
    asyncio.run(tf.process_transcript_import('job-1', UID, str(path), original_filename=name, **kwargs))
    return path


def test_zip_import_creates_completed_light_conversations(tmp_path, job):
    data = _zip(
        {
            '2026-09-12 14_30_05 Vendor quote call.srt': SRT,
            'exports/Roadmap.vtt': VTT,
            'hiring.txt': OTTER_STYLE_TXT,
            'recording.mp3': b'ID3',
            '__MACOSX/._hiring.txt': b'\x00\x05\x16\x07',
        }
    )

    upload = _run(tmp_path, 'export.zip', data, language_code='en', tz='UTC')

    assert len(job.store.docs) == 3
    final = job.final()
    assert final['status'] == ImportJobStatus.completed.value
    assert (final['conversations_created'], final['conversations_skipped']) == (3, 0)
    assert final['error'] is None
    conversation = next(d for d in job.store.docs.values() if d['structured']['title'] == 'Vendor quote call')
    assert conversation['source'] == ConversationSource.unknown.value
    assert conversation['status'] == 'completed'
    assert conversation['language'] == 'en'
    assert conversation['started_at'] == datetime(2026, 9, 12, 14, 30, 5, tzinfo=timezone.utc)
    assert conversation['structured']['overview'].startswith('Morning, did the vendor send the quote?')
    assert conversation['transcript_segments'][0]['is_user'] is True
    assert conversation['transcript_segments'][1]['person_id'] == 'person-sam'
    assert job.notifications[-1].data['type'] == 'import_complete'
    assert not upload.exists(), 'the uploaded file is removed after processing'


def test_the_owner_is_found_by_full_name_and_another_jane_is_not_the_owner(tmp_path, job):
    """The owner's profile name is "Jane Doe"; "Jane" alone would also match "Jane Smith"."""
    srt = (
        '1\n00:00:01,000 --> 00:00:02,000\nJane Doe: Hello.\n\n'
        '2\n00:00:02,000 --> 00:00:03,000\nJane Smith: Hi.\n\n'
        '3\n00:00:03,000 --> 00:00:04,000\nJane Doe: Bye.\n'
    )

    _run(tmp_path, 'call.srt', srt.encode('utf-8'))

    (conversation,) = job.store.docs.values()
    assert [s['is_user'] for s in conversation['transcript_segments']] == [True, False, True]


def test_speakers_who_are_neither_the_owner_nor_in_people_keep_their_names(tmp_path, job):
    """Neither Alice nor Bob is the owner (Jane Doe) or in People: their names are stored with their words."""
    srt = (
        '1\n00:00:01,000 --> 00:00:02,000\nAlice Chen: The vendor quote came in.\n\n'
        '2\n00:00:02,000 --> 00:00:03,000\nBob Ortiz: Twelve thousand for the year.\n\n'
        '3\n00:00:03,000 --> 00:00:04,000\nAlice Chen: Then we sign it.\n'
    )

    _run(tmp_path, 'call.srt', srt.encode('utf-8'))

    (conversation,) = job.store.docs.values()
    assert [
        (s['text'], s['speaker_id'], s['is_user'], s['person_id']) for s in conversation['transcript_segments']
    ] == [
        ('Alice Chen: The vendor quote came in.', 0, False, None),
        ('Bob Ortiz: Twelve thousand for the year.', 1, False, None),
        ('Alice Chen: Then we sign it.', 0, False, None),
    ]
    assert conversation['structured']['overview'].startswith('Alice Chen: The vendor quote came in.')


def test_reimport_skips_conversations_already_imported(tmp_path, job):
    data = _zip({'a.srt': SRT, 'b.txt': INLINE_TXT})

    _run(tmp_path, 'first.zip', data)
    _run(tmp_path, 'second.zip', data)

    assert len(job.store.docs) == 2
    final = job.final()
    assert (final['status'], final['conversations_created'], final['conversations_skipped']) == (
        ImportJobStatus.completed.value,
        0,
        2,
    )


def test_single_file_upload_and_origin_mapping(tmp_path, job):
    _run(tmp_path, 'Standup.vtt', VTT.encode('utf-8'), origin='plaud')

    (conversation,) = job.store.docs.values()
    assert conversation['source'] == ConversationSource.plaud.value
    assert conversation['structured']['title'] == 'Standup'


def test_upload_without_transcripts_fails_with_a_clear_message(tmp_path, job):
    _run(tmp_path, 'export.zip', _zip({'recording.mp3': b'ID3', 'image.png': b'\x89PNG'}))

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert 'No transcript files' in final['error']
    assert job.notifications[-1].data['type'] == 'import_failed'


def test_oversized_member_is_reported_and_others_still_import(tmp_path, job, monkeypatch):
    monkeypatch.setattr(tf, 'MAX_TRANSCRIPT_FILE_BYTES', 200)
    small = '1\n00:00:01,000 --> 00:00:02,000\nJane Doe: Short call.\n\n2\n00:00:02,000 --> 00:00:03,000\nSam: Bye.\n'
    assert len(small.encode('utf-8')) <= 200
    big = 'x' * 500
    _run(tmp_path, 'export.zip', _zip({'ok.srt': small, 'huge.txt': big}))

    final = job.final()
    assert final['status'] == ImportJobStatus.completed.value
    assert final['conversations_created'] == 1
    assert final['error'] == '1 file(s) could not be imported'
    (conversation,) = job.store.docs.values()
    assert [s['text'] for s in conversation['transcript_segments']] == ['Short call.', 'Bye.']


def _spy_on_member_reads(monkeypatch) -> list:
    reads: list = []
    monkeypatch.setattr(tf, '_read_member', lambda archive, info: reads.append(info.filename) or b'')
    return reads


def test_archive_over_the_file_count_is_rejected_before_reading(tmp_path, job, monkeypatch):
    monkeypatch.setattr(tf, 'MAX_TRANSCRIPT_FILES', 2)
    reads = _spy_on_member_reads(monkeypatch)

    _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.srt': SRT, 'c.srt': SRT}))

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert 'at most 2 transcript files' in final['error']
    assert reads == []
    assert job.store.docs == {}


def test_archive_over_the_total_size_budget_is_rejected_before_reading(tmp_path, job, monkeypatch):
    monkeypatch.setattr(tf, 'MAX_ARCHIVE_TRANSCRIPT_BYTES', 2 * len(SRT.encode('utf-8')) - 1)
    reads = _spy_on_member_reads(monkeypatch)

    _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.srt': SRT}))

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert final['error'] == 'The transcripts in this archive are too large to import at once.'
    assert reads == []
    assert job.store.docs == {}


def _declare_member_size(archive: bytes, size: int) -> bytes:
    raw = bytearray(archive)
    struct.pack_into('<L', raw, raw.rfind(b'PK\x01\x02') + 24, size)
    return bytes(raw)


@pytest.mark.parametrize(('declared', 'accepted'), [(50 * 1024 * 1024, True), (50 * 1024 * 1024 + 1, False)])
def test_an_import_holds_at_most_50_mib_of_transcripts(tmp_path, job, monkeypatch, declared, accepted):
    """About 1 s of parsing per MiB: 50 MiB keeps one import's work to minutes, not tens of minutes."""
    reads = _spy_on_member_reads(monkeypatch)

    _run(tmp_path, 'export.zip', _declare_member_size(_zip({'a.srt': SRT}), declared))

    assert (reads == ['a.srt']) is accepted
    if not accepted:
        assert job.final()['error'] == 'The transcripts in this archive are too large to import at once.'


@pytest.mark.parametrize('compression', [ZIP_BZIP2, ZIP_LZMA], ids=['bzip2', 'lzma'])
def test_archive_with_unbounded_compression_is_rejected_before_reading(tmp_path, job, monkeypatch, compression):
    """bzip2/LZMA members decompress without honoring declared sizes.

    One tiny member can expand to gigabytes, so only stored and deflated members are read.
    """
    reads = []
    monkeypatch.setattr(tf, '_read_limited', lambda open_member: reads.append(open_member) or b'')

    _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.txt': INLINE_TXT}, compression))

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert 'Re-create the ZIP with standard compression' in final['error']
    assert reads == []
    assert job.store.docs == {}


def _numbered_srts(count: int) -> dict:
    return {f'{index:02d}.srt': f'1\n00:00:01,000 --> 00:00:02,000\nLine {index}\n' for index in range(count)}


def test_cancelled_job_stops_creating_conversations(tmp_path, job, monkeypatch):
    """A cancel is read before every file, so the import stops before the next one."""
    created_before_cancel = []
    original = job.store.persist

    def persist_then_cancel(uid, data):
        created_before_cancel.append(data['id'])
        job.cancel()
        return original(uid, data)

    monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', persist_then_cancel)

    _run(tmp_path, 'export.zip', _zip(_numbered_srts(25)))

    assert len(created_before_cancel) == 1
    assert job.final_status_writes() == []
    assert job.state['status'] == ImportJobStatus.cancelled.value
    assert job.notifications == []


@pytest.mark.parametrize('cancel_after', [1, 3, 9, 10], ids=lambda n: f'after-{n}')
def test_a_cancelled_import_records_the_counts_it_reached(tmp_path, job, monkeypatch, cancel_after):
    """Progress is written every 10 files; a cancel in between must not leave import history under-counted."""
    persist = job.store.persist

    def persist_then_cancel_at(uid, data):
        saved = persist(uid, data)
        if len(job.store.docs) == cancel_after:
            job.cancel()
        return saved

    monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', persist_then_cancel_at)

    _run(tmp_path, 'export.zip', _zip(_numbered_srts(25)))

    assert len(job.store.docs) == cancel_after
    assert job.state['status'] == ImportJobStatus.cancelled.value
    counts = [job.state.get(key) for key in ('processed_files', 'conversations_created', 'conversations_skipped')]
    assert counts == [cancel_after, cancel_after, 0]
    assert job.final_status_writes() == []
    assert job.notifications == []


def test_a_job_deleted_mid_import_gets_no_final_counts(tmp_path, job, monkeypatch):
    persist = job.store.persist

    def persist_then_delete(uid, data):
        saved = persist(uid, data)
        if len(job.store.docs) == 3:
            job.cancel()
            job.delete()
        return saved

    monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', persist_then_delete)

    _run(tmp_path, 'export.zip', _zip(_numbered_srts(25)))

    assert len(job.store.docs) == 3
    assert [u for u in job.updates if 'processed_files' in u] == []


def test_every_status_write_is_conditional_on_the_job_not_being_cancelled(tmp_path, job, monkeypatch):
    """The cancel route writes the job directly, so a read-then-write could overwrite it."""
    inside, bare = [False], []
    update, conditional = tf.import_jobs_db.update_import_job, tf.import_jobs_db.update_import_job_unless_cancelled

    def guarded(job_id, fields):
        inside[0] = True
        try:
            return conditional(job_id, fields)
        finally:
            inside[0] = False

    def watched(job_id, fields):
        if not inside[0]:
            bare.append(fields)
        update(job_id, fields)

    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job', watched)
    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job_unless_cancelled', guarded)

    _run(tmp_path, 'export.zip', _zip(_numbered_srts(12)))

    assert job.final()['status'] == ImportJobStatus.completed.value
    assert bare == []


def test_job_cancelled_before_it_starts_never_becomes_processing(tmp_path, job):
    job.cancel()

    upload = _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.txt': INLINE_TXT}))

    assert job.state['status'] == ImportJobStatus.cancelled.value
    assert not [u for u in job.updates if 'status' in u]
    assert job.store.docs == {}
    assert job.notifications == []
    assert not upload.exists(), 'a cancelled upload is still cleaned up'


def test_a_deleted_job_is_treated_as_cancelled(tmp_path, job):
    job.delete()

    upload = _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.txt': INLINE_TXT}))

    assert job.updates == []
    assert job.store.docs == {}
    assert job.notifications == []
    assert not upload.exists()


@pytest.mark.parametrize(
    'files',
    [
        pytest.param({'recording.mp3': b'ID3'}, id='no-transcripts'),
        pytest.param({'a.srt': SRT, 'b.srt': SRT, 'c.srt': SRT}, id='over-file-limit'),
        pytest.param({'a.srt': b'\x00binary'}, id='nothing-readable'),
        pytest.param({'a.srt': SRT}, id='importable'),
    ],
)
def test_cancel_while_processing_is_never_overwritten_by_a_final_status(tmp_path, job, monkeypatch, files):
    monkeypatch.setattr(tf, 'MAX_TRANSCRIPT_FILES', 2)

    def name_then_cancel(uid):
        job.cancel()
        return _firebase_user('Jane Doe')

    monkeypatch.setattr(auth_db, '_firebase_get_user', name_then_cancel)

    _run(tmp_path, 'export.zip', _zip(files))

    assert job.state['status'] == ImportJobStatus.cancelled.value
    assert job.final_status_writes() == []
    assert job.store.docs == {}
    assert job.notifications == []


@pytest.mark.parametrize(
    'files',
    [pytest.param({'a.srt': SRT}, id='would-complete'), pytest.param({'a.srt': b'\x00'}, id='would-fail')],
)
def test_cancel_observed_before_the_final_write_leaves_the_job_cancelled(tmp_path, job, monkeypatch, files):
    record_update = tf.import_jobs_db.update_import_job

    def update_then_cancel(job_id, fields):
        record_update(job_id, fields)
        if fields.get('processed_files') == 1:
            job.cancel()

    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job', update_then_cancel)

    _run(tmp_path, 'export.zip', _zip(files))

    assert job.state['status'] == ImportJobStatus.cancelled.value
    assert job.final_status_writes() == []
    assert job.notifications == []


def test_the_worker_holds_a_pool_slot_per_step_never_for_the_whole_import(tmp_path, job, monkeypatch):
    """backend/AGENTS.md: never hold a pool slot for more than 60 s. The import is an async
    coordinator; each file is its own short blocking step on the storage pool."""
    steps = []
    run_blocking = tf.run_blocking

    async def recording_run_blocking(executor, fn, *args, **kwargs):
        steps.append((executor, fn))
        return await run_blocking(executor, fn, *args, **kwargs)

    monkeypatch.setattr(tf, 'run_blocking', recording_run_blocking)

    _run(tmp_path, 'export.zip', _zip(_numbered_srts(12)))

    assert inspect.iscoroutinefunction(tf.process_transcript_import)
    assert [executor for executor, fn in steps if fn is tf._import_file] == [tf.storage_executor] * 12
    assert (tf.storage_executor, tf._open_upload) in steps
    job_writes = [executor for executor, fn in steps if fn in (tf._job_cancelled, tf.import_jobs_db.update_import_job)]
    assert len(job_writes) >= 4 and set(job_writes) == {tf.db_executor}
    assert job.final()['status'] == ImportJobStatus.completed.value
    assert len(job.store.docs) == 12


@pytest.mark.parametrize('at', ['the open', 'a file'])
def test_an_import_cancelled_at_shutdown_is_failed_not_left_processing(tmp_path, job, monkeypatch, at):
    """Shutdown cancels tracked background tasks (drain_background_tasks)."""
    run_blocking = tf.run_blocking
    interrupted = tf._open_upload if at == 'the open' else tf._import_file

    async def cancelled_at_step(executor, fn, *args, **kwargs):
        if fn is interrupted:
            raise asyncio.CancelledError
        return await run_blocking(executor, fn, *args, **kwargs)

    monkeypatch.setattr(tf, 'run_blocking', cancelled_at_step)

    with pytest.raises(asyncio.CancelledError):
        _run(tmp_path, 'export.zip', _zip({'a.srt': SRT}))

    assert job.final()['status'] == ImportJobStatus.failed.value
    assert job.final()['error'] == tf.INTERRUPTED_ERROR
    assert not (tmp_path / 'export.zip').exists()


def test_a_shutdown_after_the_import_completed_keeps_it_completed(tmp_path, job, monkeypatch):
    run_blocking = tf.run_blocking

    async def cancelled_at_notify(executor, fn, *args, **kwargs):
        if fn is tf._notify:
            raise asyncio.CancelledError
        return await run_blocking(executor, fn, *args, **kwargs)

    monkeypatch.setattr(tf, 'run_blocking', cancelled_at_notify)

    with pytest.raises(asyncio.CancelledError):
        _run(tmp_path, 'export.zip', _zip({'a.srt': SRT}))

    assert job.final()['status'] == ImportJobStatus.completed.value


def _cancel_while(tmp_path, data: bytes, blocked: threading.Event, release: threading.Event):
    """Run the import as a task and cancel it, as the shutdown drain does, while a step is blocked."""
    path = tmp_path / 'export.zip'
    path.write_bytes(data)

    async def main():
        task = asyncio.create_task(
            tf.process_transcript_import('job-1', UID, str(path), original_filename='export.zip')
        )
        while not blocked.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.05)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    return path


def test_a_real_shutdown_cancel_mid_file_fails_the_job_and_writes_nothing_more(tmp_path, job, monkeypatch):
    blocked, release = threading.Event(), threading.Event()
    import_file = tf._import_file
    abandoned = {}

    def slow_import(*args, **kwargs):
        blocked.set()
        release.wait(5)
        try:
            return import_file(*args, **kwargs)
        except Exception as exc:
            abandoned['error'] = type(exc).__name__
            raise

    monkeypatch.setattr(tf, '_import_file', slow_import)

    path = _cancel_while(tmp_path, _zip({'a.srt': SRT}), blocked, release)
    time.sleep(0.2)  # let the abandoned file thread finish

    assert job.final()['status'] == ImportJobStatus.failed.value
    assert job.final()['error'] == tf.INTERRUPTED_ERROR
    assert not path.exists()
    # The released archive stops the abandoned thread before it stores anything.
    assert job.store.docs == {}


@pytest.mark.parametrize(
    ('files', 'final_status'),
    [
        pytest.param({'a.srt': SRT}, ImportJobStatus.completed.value, id='completed-write'),
        pytest.param({'recording.mp3': b'ID3'}, ImportJobStatus.failed.value, id='no-transcripts-write'),
        pytest.param({'a.srt': b'\x00binary'}, ImportJobStatus.failed.value, id='nothing-imported-write'),
    ],
)
def test_a_shutdown_during_the_final_write_never_overwrites_it(tmp_path, job, monkeypatch, files, final_status):
    blocked, release = threading.Event(), threading.Event()
    update = tf.import_jobs_db.update_import_job

    def slow_final_write(job_id, fields):
        if fields.get('status') == final_status:
            blocked.set()
            release.wait(5)
        update(job_id, fields)

    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job', slow_final_write)

    _cancel_while(tmp_path, _zip(files), blocked, release)
    time.sleep(0.2)  # let the final write land

    assert [write['status'] for write in job.final_status_writes()] == [final_status]
    assert job.final()['status'] == final_status
    assert all(tf.INTERRUPTED_ERROR not in str(n) for n in job.notifications)


@pytest.mark.parametrize(
    'files',
    [
        pytest.param({'a.srt': SRT}, id='completed-write'),
        pytest.param({'a.srt': b'\x00binary'}, id='nothing-imported-write'),
    ],
)
def test_a_shutdown_while_the_final_write_is_still_queued_fails_the_job(tmp_path, job, monkeypatch, files):
    """A saturated db pool holds the final write in its queue; cancelling the task cancels it there.

    That write never runs, so the interruption must still be recorded rather than leave
    the job processing with no worker behind it.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(tf, 'db_executor', pool)
    occupied, release = threading.Event(), threading.Event()
    update_unless_cancelled = tf.import_jobs_db.update_import_job_unless_cancelled

    def last_progress_write(job_id, fields):
        if fields.get('processed_files') == len(files):
            # Another request takes the pool's only thread right after this write.
            pool.submit(lambda: (occupied.set(), release.wait(5)))
        return update_unless_cancelled(job_id, fields)

    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job_unless_cancelled', last_progress_write)
    path = tmp_path / 'export.zip'
    path.write_bytes(_zip(files))

    async def main():
        task = asyncio.create_task(
            tf.process_transcript_import('job-1', UID, str(path), original_filename='export.zip')
        )
        # The final write is queued behind the occupied thread.
        while not (occupied.is_set() and pool._work_queue.qsize() == 1):
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.05)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(main())
    finally:
        release.set()
        pool.shutdown(wait=True)

    assert job.final_status_writes() == [job.final()], 'one final status, never the queued one as well'
    assert job.final()['status'] == ImportJobStatus.failed.value
    assert job.final()['error'] == tf.INTERRUPTED_ERROR
    assert not path.exists(), 'the staged upload is removed once the job has its final status'


@pytest.mark.parametrize(
    ('failure', 'message'),
    [
        pytest.param(None, 'The upload is not a valid ZIP archive.', id='refused-upload'),
        pytest.param(RuntimeError('boom'), tf.UNEXPECTED_IMPORT_ERROR, id='unexpected-error'),
    ],
)
def test_a_shutdown_while_a_failure_write_is_still_queued_still_fails_the_job(
    tmp_path, job, monkeypatch, failure, message
):
    """A cancel raised while an except clause awaits its failure write skips the CancelledError clause.

    The queued failure write must still land, rather than leave the job processing.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(tf, 'db_executor', pool)
    occupied, release = threading.Event(), threading.Event()
    open_upload = tf._open_upload

    def occupied_then_open(*args, **kwargs):
        # Another request takes the pool's only thread before the failure write is queued.
        pool.submit(lambda: (occupied.set(), release.wait(5)))
        occupied.wait(5)
        if failure is not None:
            raise failure
        return open_upload(*args, **kwargs)

    monkeypatch.setattr(tf, '_open_upload', occupied_then_open)
    path = tmp_path / 'export.zip'
    path.write_bytes(b'not a zip at all')

    async def main():
        task = asyncio.create_task(
            tf.process_transcript_import('job-1', UID, str(path), original_filename='export.zip')
        )
        while not (occupied.is_set() and pool._work_queue.qsize() == 1):
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.05)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(main())
    finally:
        release.set()
        pool.shutdown(wait=True)

    assert job.final_status_writes() == [job.final()]
    assert (job.final()['status'], job.final()['error']) == (ImportJobStatus.failed.value, message)
    assert not path.exists()


def test_a_final_write_that_raises_is_still_followed_by_a_failure(tmp_path, job, monkeypatch):
    """A raising write settled nothing: the generic failure after it is still recorded."""
    update_unless_cancelled = tf.import_jobs_db.update_import_job_unless_cancelled

    def completed_write_fails(job_id, fields):
        if fields.get('status') == ImportJobStatus.completed.value:
            raise RuntimeError('firestore down')
        return update_unless_cancelled(job_id, fields)

    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job_unless_cancelled', completed_write_fails)

    _run(tmp_path, 'export.zip', _zip({'a.srt': SRT}))

    assert (job.final()['status'], job.final()['error']) == (ImportJobStatus.failed.value, tf.UNEXPECTED_IMPORT_ERROR)


def test_the_final_write_and_the_interruption_claim_the_settlement_once():
    """Whichever begins first in its pool thread writes; the other does nothing."""
    settlement = tf._Settlement()
    calls = []

    assert settlement.run(calls.append, 'final') is None
    assert settlement.run(calls.append, 'interrupted') is None

    assert calls == ['final']


class _FakeTransaction:
    def __init__(self):
        self.updates = []

    def update(self, ref, fields):
        self.updates.append((ref, fields))


class _FakeJobRef:
    def __init__(self, doc):
        self.doc = doc
        self.read_in = []

    def get(self, transaction=None):
        self.read_in.append(transaction)
        return SimpleNamespace(exists=self.doc is not None, to_dict=lambda: self.doc)


@pytest.mark.parametrize(
    ('doc', 'applied'),
    [
        pytest.param({'status': 'processing'}, True, id='running'),
        pytest.param({'status': 'cancelled'}, False, id='cancelled'),
        pytest.param(None, False, id='deleted'),
    ],
)
def test_the_conditional_job_update_reads_and_writes_in_one_transaction(monkeypatch, doc, applied):
    import database.import_jobs as import_jobs

    ref, transaction = _FakeJobRef(doc), _FakeTransaction()
    client = SimpleNamespace(
        collection=lambda name: SimpleNamespace(document=lambda job_id: ref), transaction=lambda: transaction
    )
    monkeypatch.setattr(import_jobs, 'db', client)
    monkeypatch.setattr(import_jobs.firestore, 'transactional', lambda fn: fn)

    result = import_jobs.update_import_job_unless_cancelled('job-1', {'status': 'completed'})

    assert result is applied
    assert ref.read_in == [transaction], 'the status is read inside the transaction'
    assert transaction.updates == ([(ref, {'status': 'completed'})] if applied else [])


@pytest.mark.parametrize(
    ('doc', 'applied'),
    [
        pytest.param({'status': 'cancelled'}, True, id='cancelled'),
        pytest.param({'status': 'processing'}, True, id='running'),
        pytest.param(None, False, id='deleted'),
    ],
)
def test_a_progress_write_touches_only_the_counters_of_a_job_that_exists(monkeypatch, doc, applied):
    """A cancelled job still gets the counts its worker reached; its status is never written."""
    import database.import_jobs as import_jobs

    ref, transaction = _FakeJobRef(doc), _FakeTransaction()
    client = SimpleNamespace(
        collection=lambda name: SimpleNamespace(document=lambda job_id: ref), transaction=lambda: transaction
    )
    monkeypatch.setattr(import_jobs, 'db', client)
    monkeypatch.setattr(import_jobs.firestore, 'transactional', lambda fn: fn)
    progress = {'processed_files': 3, 'conversations_created': 2, 'conversations_skipped': 1}

    assert import_jobs.update_import_job_progress('job-1', progress) is applied
    assert ref.read_in == [transaction]
    assert transaction.updates == ([(ref, progress)] if applied else [])


@pytest.mark.parametrize('fields', [{'status': 'completed'}, {'processed_files': 1, 'error': None}])
def test_a_progress_write_refuses_anything_but_the_counters(monkeypatch, fields):
    import database.import_jobs as import_jobs

    monkeypatch.setattr(import_jobs, 'db', None)

    with pytest.raises(ValueError):
        import_jobs.update_import_job_progress('job-1', fields)


def test_job_uses_its_own_source_type(monkeypatch):
    created = MagicMock()
    monkeypatch.setattr(tf.import_jobs_db, 'create_import_job', created)

    job = tf.create_transcript_import_job(UID)

    assert job.source_type == ImportSourceType.transcript_files
    assert created.call_args.args[0]['source_type'] == 'transcript_files'


# --------------------------------------------------------------------------- parse limits


def test_absurd_cue_hours_do_not_fail_the_file():
    """A timestamp's hours are bounded, so one absurd cue is dropped instead of raising."""
    srt = (
        '1\n' + '9' * 5000 + ':00:00,000 --> 00:00:02,000\nNever spoken.\n\n'
        '2\n99999999:00:00,000 --> 99999999:00:02,000\nAlso never spoken.\n\n'
        '3\n00:00:03,000 --> 00:00:04,000\nHello there.\n'
    )

    parsed = tf.parse_transcript_file('call.srt', srt.encode('utf-8'))

    assert parsed is not None
    assert [(c.text, c.start) for c in parsed.cues] == [('Hello there.', 3.0)]
    assert tf._seconds('99999999:00:00') is None
    assert tf._seconds('100:00:00') == 360000.0


def test_inline_continuation_lines_build_each_cue_once(monkeypatch):
    """Continuation lines are joined once, not re-copied into a new cue per line."""
    built = []
    cue = tf.TranscriptCue

    def counting_cue(*args, **kwargs):
        built.append(1)
        return cue(*args, **kwargs)

    monkeypatch.setattr(tf, 'TranscriptCue', counting_cue)
    timed_lines = 200

    cues = tf.parse_text_transcript('0:00 Okay, noted\n' * timed_lines + 'b\n' * timed_lines)

    assert len(cues) == timed_lines
    assert cues[-1].text == 'Okay, noted' + ' b' * timed_lines
    assert len(built) <= timed_lines


def test_future_filename_dates_are_clamped_to_now():
    before = datetime.now(timezone.utc)

    started_at = tf.started_at_from_filename('2999-01-01 10_00 call.txt', 'UTC')

    assert started_at is not None
    assert before <= started_at <= datetime.now(timezone.utc)


@pytest.mark.parametrize(
    ('filename', 'expected'),
    [
        pytest.param(' '.join(['meeting'] * 60) + '.txt', ' '.join(['meeting'] * 25), id='cut-at-word-boundary'),
        pytest.param('x' * 300 + '.srt', 'x' * 200, id='one-long-word'),
        pytest.param('Q3 ' + 'x' * 300 + '.vtt', 'Q3 ' + 'x' * 197, id='early-space-is-not-a-cut-point'),
    ],
)
def test_long_titles_are_capped(filename, expected):
    title = tf.title_from_filename(filename)

    assert title == expected
    assert len(title) <= 200


# --------------------------------------------------------------------------- storage limits


def test_file_over_the_segment_cap_is_skipped_before_segments_are_built(tmp_path, job, monkeypatch):
    monkeypatch.setattr(tf, 'MAX_TRANSCRIPT_SEGMENTS', 3)
    built = []
    segments_from_cues = tf.segments_from_cues
    monkeypatch.setattr(
        tf, 'segments_from_cues', lambda cues, **kw: built.append(cues) or segments_from_cues(cues, **kw)
    )

    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert final['error'] == 'None of the 1 file(s) could be imported (transcript too long).'
    assert built == []
    assert job.store.docs == {}


@pytest.mark.parametrize(('budget', 'imported'), [(1000, True), (999, False)], ids=['at-budget', 'one-byte-over'])
def test_stored_transcript_must_fit_the_document_budget(tmp_path, job, monkeypatch, budget, imported):
    """The budget is measured on the blob the conversation write path itself encodes."""
    encoded = []

    def encode(uid, conversation_data, level='standard'):
        encoded.append(conversation_data['transcript_segments'])
        return {'transcript_segments': b'z' * 1000}

    monkeypatch.setattr(tf.conversations_db, 'encode_conversation_for_write', encode)
    monkeypatch.setattr(tf, 'MAX_COMPRESSED_TRANSCRIPT_BYTES', budget)

    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))

    assert [segment['text'] for segment in encoded[0]][-1] == 'Agreed.'
    final = job.final()
    if imported:
        assert final['status'] == ImportJobStatus.completed.value
        assert len(job.store.docs) == 1
    else:
        assert final['error'] == 'None of the 1 file(s) could be imported (transcript too long).'
        assert job.store.docs == {}


def test_compressed_transcript_size_is_the_write_path_blob():
    segments = [{'id': 's1', 'text': 'hello there', 'speaker': 'SPEAKER_00', 'start': 0.0, 'end': 1.0}]

    size = tf._compressed_transcript_bytes(UID, segments)

    assert size == len(
        conversations_db.encode_conversation_for_write(UID, {'transcript_segments': segments})['transcript_segments']
    )
    assert segments[0]['text'] == 'hello there', 'measuring never mutates the payload'


@pytest.mark.parametrize(('size', 'imported'), [(1024 * 1024, True), (1024 * 1024 + 1, False)], ids=['1MiB', 'over'])
def test_transcript_files_are_capped_at_one_mebibyte(tmp_path, job, size, imported):
    _run(tmp_path, 'notes.txt', b'x' * size)

    final = job.final()
    if imported:
        assert final['status'] == ImportJobStatus.completed.value
    else:
        assert final['error'] == 'None of the 1 file(s) could be imported (file too large).'
        assert job.store.docs == {}


# --------------------------------------------------------------------------- archive limits


def _end_of_directory(entries: int, directory_bytes: int, offset: int = 0) -> bytes:
    return struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, entries, entries, directory_bytes, offset, 0)


def _zip64_end_of_directory(entries: int, directory_bytes: int) -> bytes:
    record = struct.pack('<4sQ2H2L4Q', b'PK\x06\x06', 44, 45, 45, 0, 0, entries, entries, directory_bytes, 0)
    locator = struct.pack('<4sLQL', b'PK\x06\x07', 0, 0, 1)
    return record + locator + _end_of_directory(0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF)


def _directory_entries(count: int) -> bytes:
    """Central-directory records with no file data behind them (the cheap way to list many files)."""
    entry = struct.pack('<4s4B4HL2L5H2L', b'PK\x01\x02', 20, 3, 20, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0)
    return (entry + b'a.srt') * count


@pytest.mark.parametrize(
    'archive',
    [
        pytest.param(_directory_entries(25_000) + _end_of_directory(25_000, 50 * 25_000), id='many-real-entries'),
        pytest.param(_end_of_directory(30_000, 0), id='many-declared-entries'),
        pytest.param(_end_of_directory(10, 9 * 1024 * 1024), id='oversized-directory'),
        pytest.param(
            # zipfile reads entries until the directory bytes run out, whatever the count says.
            _directory_entries(42_000) + _end_of_directory(1, 51 * 42_000),
            id='count-lies-about-a-2MiB-directory',
        ),
        pytest.param(_zip64_end_of_directory(100_000, 0), id='zip64-many-entries'),
        pytest.param(_zip64_end_of_directory(10, 2**40), id='zip64-oversized-directory'),
    ],
)
def test_archive_with_an_oversized_directory_is_rejected_before_it_is_opened(tmp_path, job, monkeypatch, archive):
    """Opening a ZIP loads its whole central directory, so its declared size is checked first."""
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))

    _run(tmp_path, 'export.zip', archive)

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert final['error'] == 'This ZIP lists too many files to import. Split it into smaller ZIPs and try again.'
    assert opened == []


_LOCAL_HEADER = struct.Struct('<4s5H3L2H')
_CENTRAL_HEADER = struct.Struct('<4s6H3L5H2L')
_ZIP64_RECORD = struct.Struct('<4sQ2H2L4Q')


def _handmade_zip(
    members: dict,
    *,
    filler: int = 0,
    zip64: bool = False,
    extensible: bytes = b'',
    classic: tuple = (),
    comment: bytes = b'',
    prefix: bytes = b'',
) -> bytes:
    """A stored ZIP built byte by byte, so its end records can say what a test needs.

    ``filler`` adds directory entries for a non-transcript file; ``classic`` overrides
    the (entries, directory bytes) written to the classic end record; ``prefix`` is
    prepended without adjusting any offset (as a self-extractor stub is).
    """
    out = bytearray()
    directory = bytearray()
    for name, text in members.items():
        data, raw_name, offset = text.encode('utf-8'), name.encode(), len(out)
        crc = zlib.crc32(data)
        out += _LOCAL_HEADER.pack(b'PK\x03\x04', 20, 0, 0, 0, 0, crc, len(data), len(data), len(raw_name), 0)
        out += raw_name + data
        directory += _CENTRAL_HEADER.pack(
            b'PK\x01\x02', 20, 20, 0, 0, 0, 0, crc, len(data), len(data), len(raw_name), 0, 0, 0, 0, 0, offset
        )
        directory += raw_name
    directory += (_CENTRAL_HEADER.pack(b'PK\x01\x02', 20, 20, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0) + b'x') * filler
    entries, start = len(members) + filler, len(out)
    out += directory
    if zip64:
        record_at = len(out)
        size = _ZIP64_RECORD.size - 12 + len(extensible)
        out += _ZIP64_RECORD.pack(b'PK\x06\x06', size, 45, 45, 0, 0, entries, entries, len(directory), start)
        out += extensible
        out += struct.pack('<4sLQL', b'PK\x06\x07', 0, record_at, 1)
    count, size = classic or (entries, len(directory))
    out += struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, count, count, size, start, len(comment)) + comment
    return prefix + bytes(out)


def _decoy_zip64_record() -> bytes:
    """zip64 extensible data ending in a record that claims a one-entry directory."""
    return b'\0' * 144 + _ZIP64_RECORD.pack(b'PK\x06\x06', 44, 45, 45, 0, 0, 1, 1, 51, 0)


def test_a_decoy_zip64_record_cannot_hide_a_large_directory(tmp_path, job, monkeypatch):
    """zipfile reads the zip64 record the locator points at; a decoy just before the
    locator must not be the only one checked."""
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))
    archive = _handmade_zip(
        {'a.srt': SRT}, filler=25_000, zip64=True, extensible=_decoy_zip64_record(), classic=(1, 51)
    )

    _run(tmp_path, 'export.zip', archive)

    assert job.final()['error'] == 'This ZIP lists too many files to import. Split it into smaller ZIPs and try again.'
    assert opened == []


def test_the_zip64_record_before_the_locator_is_checked_too(tmp_path, job, monkeypatch):
    """With prepended data the locator's offset misses, and zipfile falls back to the
    record just before the locator (older CPython reads only that one)."""
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))
    archive = _handmade_zip({'a.srt': SRT}, filler=25_000, zip64=True, classic=(1, 51), prefix=b'MZ' + b'\0' * 4096)

    _run(tmp_path, 'export.zip', archive)

    assert job.final()['error'] == 'This ZIP lists too many files to import. Split it into smaller ZIPs and try again.'
    assert opened == []


def test_a_transcript_is_read_with_a_bounded_request():
    """The cap bounds memory only if no more than one byte past it is ever requested."""
    requested = []

    class Handle(io.BytesIO):
        def read(self, size=-1):
            requested.append(size)
            return super().read(size)

    data = tf._read_limited(lambda: Handle(b'x' * 10))

    assert data == b'x' * 10
    assert requested == [tf.MAX_TRANSCRIPT_FILE_BYTES + 1]


@pytest.mark.parametrize(
    'extensible', [pytest.param(b'\0' * 200, id='extensible-data'), pytest.param(b'', id='no-extensible-data')]
)
def test_zip64_archive_with_extensible_data_imports(tmp_path, job, extensible):
    """Writers that need zip64 put 0xFFFF markers in the classic record; the zip64 values count."""
    archive = _handmade_zip({'a.srt': SRT}, zip64=True, extensible=extensible, classic=(0xFFFF, 0xFFFFFFFF))

    _run(tmp_path, 'export.zip', archive)

    assert job.final()['status'] == ImportJobStatus.completed.value
    assert len(job.store.docs) == 1


def test_the_last_end_record_in_the_tail_is_the_one_checked(tmp_path, job, monkeypatch):
    """Like zipfile, the last end-of-directory signature wins, even inside the comment."""
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))
    later_record = struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, 60_000, 60_000, 99_000_000, 0, 0)

    # Bytes after it keep zipfile off its no-comment fast path, so the search decides.
    _run(tmp_path, 'export.zip', _handmade_zip({'a.srt': SRT}, comment=b'xx' + later_record + b'yy'))

    assert job.final()['error'] == 'This ZIP lists too many files to import. Split it into smaller ZIPs and try again.'
    assert opened == []


def test_an_end_signature_without_a_whole_record_after_it_is_not_a_zip(tmp_path, job):
    """zipfile gives up when the last signature has no complete record behind it, and so do we."""
    _run(tmp_path, 'export.zip', _handmade_zip({'a.srt': SRT}, comment=b'PK\x05\x06' + b'z' * 10))

    assert job.final()['error'] == 'The upload is not a valid ZIP archive.'


def test_a_zip_without_a_comment_is_read_from_its_final_22_bytes(tmp_path, job, monkeypatch):
    """zipfile's no-comment fast path: the signature bytes inside the final record's own
    directory-size field are not a later record."""
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))
    signature_as_size = struct.unpack('<L', b'PK\x05\x06')[0]

    _run(tmp_path, 'export.zip', _handmade_zip({'a.srt': SRT}, classic=(1, signature_as_size)))

    assert job.final()['error'] == 'This ZIP lists too many files to import. Split it into smaller ZIPs and try again.'
    assert opened == []


def test_an_end_record_at_the_far_edge_of_the_search_window_is_checked(tmp_path, job, monkeypatch):
    """zipfile searches the last 64 KiB + 22 bytes; a record at its very first byte still counts."""
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))

    _run(tmp_path, 'export.zip', _end_of_directory(30_000, 9 * 1024 * 1024) + b'\0' * (1 << 16))

    assert job.final()['error'] == 'This ZIP lists too many files to import. Split it into smaller ZIPs and try again.'
    assert opened == []


@pytest.mark.parametrize(
    'data',
    [
        pytest.param(b'not a zip archive' * 10, id='no-end-record'),
        pytest.param(b'PK\x05\x06\0\0', id='shorter-than-an-end-record'),
    ],
)
def test_a_zip_whose_end_record_cannot_be_read_is_refused_before_it_is_opened(tmp_path, job, monkeypatch, data):
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))

    _run(tmp_path, 'export.zip', data)

    assert job.final()['error'] == 'The upload is not a valid ZIP archive.'
    assert opened == []


@pytest.mark.parametrize(
    ('entries', 'directory_bytes', 'accepted'),
    [
        pytest.param(tf.MAX_ZIP_DIRECTORY_ENTRIES, 0, True, id='entries-at-limit'),
        pytest.param(tf.MAX_ZIP_DIRECTORY_ENTRIES + 1, 0, False, id='entries-over'),
        pytest.param(1, tf.MAX_ZIP_DIRECTORY_BYTES, True, id='directory-at-limit'),
        pytest.param(1, tf.MAX_ZIP_DIRECTORY_BYTES + 1, False, id='directory-over'),
    ],
)
def test_the_directory_caps_are_inclusive(tmp_path, job, monkeypatch, entries, directory_bytes, accepted):
    opened = []
    monkeypatch.setattr(tf, 'ZipFile', lambda *args, **kwargs: opened.append(args))

    _run(tmp_path, 'export.zip', _end_of_directory(entries, directory_bytes))

    assert bool(opened) is accepted


def test_a_future_zip_entry_date_is_clamped_to_now(tmp_path, job):
    buf = io.BytesIO()
    with ZipFile(buf, 'w') as zf:
        zf.writestr(zipfile.ZipInfo('call.srt', date_time=(2099, 1, 1, 0, 0, 0)), SRT)
    before = datetime.now(timezone.utc)

    _run(tmp_path, 'export.zip', buf.getvalue())

    (stored,) = job.store.docs.values()
    assert before <= stored['started_at'] <= datetime.now(timezone.utc)


def _zip64_archive(monkeypatch) -> bytearray:
    with monkeypatch.context() as patched:
        patched.setattr(zipfile, 'ZIP_FILECOUNT_LIMIT', 0)  # force zipfile to write the zip64 records
        return bytearray(_zip({'a.srt': SRT}))


@pytest.mark.parametrize('pointer', [2**64 - 1, 2**62 + 12345], ids=['max', 'past-seekable'])
def test_a_zip64_locator_pointing_past_the_file_is_refused_as_invalid(tmp_path, job, monkeypatch, pointer):
    """zipfile refuses a locator that points past its own position; the gate must not crash on it."""
    raw = _zip64_archive(monkeypatch)
    struct.pack_into('<Q', raw, raw.rfind(b'PK\x06\x07') + 8, pointer)

    _run(tmp_path, 'export.zip', bytes(raw))

    assert job.final()['error'] == 'The upload is not a valid ZIP archive.'


@pytest.mark.parametrize(
    'patch',
    [
        # Version needed to extract above what zipfile supports: NotImplementedError.
        pytest.param(lambda raw, at: struct.pack_into('<B', raw, at + 6, 64), id='future-version'),
        # The UTF-8 name flag on bytes that are not UTF-8: UnicodeDecodeError.
        pytest.param(
            lambda raw, at: (
                struct.pack_into('<H', raw, at + 8, struct.unpack_from('<H', raw, at + 8)[0] | 0x800),
                raw.__setitem__(slice(at + 46, at + 47), b'\xff'),
            ),
            id='bad-utf8-name',
        ),
    ],
)
def test_an_archive_zipfile_cannot_read_is_refused_as_invalid(tmp_path, job, patch):
    raw = bytearray(_zip({'a.srt': SRT}))
    patch(raw, raw.rfind(b'PK\x01\x02'))

    _run(tmp_path, 'export.zip', bytes(raw))

    assert job.final()['error'] == 'The upload is not a valid ZIP archive.'


def test_a_zip_entry_at_the_dos_epoch_is_dated_by_the_upload_instead(tmp_path, job):
    """1980-01-01 is the ZIP format's zero date (ZipInfo's default), not a recording time."""
    buf = io.BytesIO()
    with ZipFile(buf, 'w') as zf:
        zf.writestr(zipfile.ZipInfo('call.srt'), SRT)
    before = datetime.now(timezone.utc)

    _run(tmp_path, 'export.zip', buf.getvalue())

    (stored,) = job.store.docs.values()
    assert before <= stored['started_at'] <= datetime.now(timezone.utc)


def _central_flag(raw: bytearray, bit: int) -> bytearray:
    at = raw.rfind(b'PK\x01\x02')
    struct.pack_into('<H', raw, at + 8, struct.unpack_from('<H', raw, at + 8)[0] | bit)
    return raw


def _local_utf8_flag_on_a_cp437_name(raw: bytearray) -> bytearray:
    at = raw.find(b'PK\x03\x04')
    struct.pack_into('<H', raw, at + 6, struct.unpack_from('<H', raw, at + 6)[0] | 0x800)
    raw[at + 30] = 0xFF
    return raw


def _directory_offset_past_its_start(raw: bytearray) -> bytearray:
    struct.pack_into('<L', raw, raw.rfind(b'PK\x05\x06') + 16, raw.rfind(b'PK\x01\x02') + 1000)
    return raw


@pytest.mark.parametrize(
    'damage',
    [
        pytest.param(lambda raw: _central_flag(raw, 0x20), id='patched-data-flag'),
        pytest.param(lambda raw: _central_flag(raw, 0x40), id='strong-encryption-flag'),
        pytest.param(_local_utf8_flag_on_a_cp437_name, id='local-utf8-name'),
        pytest.param(_directory_offset_past_its_start, id='negative-header-offset'),
    ],
)
def test_a_member_zipfile_cannot_read_is_reported_as_damaged(tmp_path, job, damage):
    _run(tmp_path, 'export.zip', bytes(damage(bytearray(_zip({'a.srt': SRT})))))

    assert job.final()['error'] == f'None of the 1 file(s) could be imported ({tf.FILE_DAMAGED}).'


def _zip_with_header_offset(offset: int) -> bytes:
    """A member whose central header defers its local-header offset to a zip64 extra field."""
    buf = io.BytesIO()
    info = zipfile.ZipInfo('a.srt')
    info.extra = b'\x99\x99\x08\x00' + b'\0' * 8
    with ZipFile(buf, 'w') as zf:
        zf.writestr(info, SRT)
    raw = bytearray(buf.getvalue())
    central = raw.rfind(b'PK\x01\x02')
    struct.pack_into('<L', raw, central + 42, 0xFFFFFFFF)
    extra = raw.find(b'\x99\x99\x08\x00', central)
    raw[extra : extra + 12] = b'\x01\x00\x08\x00' + struct.pack('<Q', offset)
    return bytes(raw)


@pytest.mark.parametrize('offset', [2**64 - 1, 2**63, 2**62, 2**50, 2**40], ids=['max', '2^63', '2^62', '2^50', '2^40'])
def test_a_member_offset_beyond_the_archive_is_reported_as_damaged(tmp_path, job, offset):
    _run(tmp_path, 'export.zip', _zip_with_header_offset(offset))

    assert job.final()['error'] == f'None of the 1 file(s) could be imported ({tf.FILE_DAMAGED}).'


@pytest.mark.parametrize(
    ('date_time', 'tz', 'kept'),
    [
        pytest.param((1990, 1, 1, 0, 30, 0), 'Europe/Berlin', True, id='first-local-day-of-1990'),
        pytest.param((1989, 12, 31, 23, 30, 0), 'America/Los_Angeles', False, id='last-local-day-of-1989'),
    ],
)
def test_the_zip_date_floor_reads_the_local_year(tmp_path, job, date_time, tz, kept):
    """The same floor as a date in a file name, which is read in the user's timezone."""
    buf = io.BytesIO()
    with ZipFile(buf, 'w') as zf:
        zf.writestr(zipfile.ZipInfo('call.srt', date_time=date_time), SRT)

    _run(tmp_path, 'export.zip', buf.getvalue(), tz=tz)

    (stored,) = job.store.docs.values()
    assert (stored['started_at'].year < 2000) is kept


def test_an_upload_that_breaks_zip_detection_is_read_by_its_extension(tmp_path, job, monkeypatch):
    """Older zipfile versions raise from is_zipfile on some locators instead of answering False."""

    def is_zipfile_raises(path):
        raise zipfile.BadZipFile('zipfiles that span multiple disks are not supported')

    monkeypatch.setattr(tf, 'is_zipfile', is_zipfile_raises)

    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))

    assert job.final()['status'] == ImportJobStatus.completed.value


def test_zip64_archive_with_few_entries_still_imports(tmp_path, job, monkeypatch):
    """A real zip64 end record (classic fields 0xFFFF) is read for its true counts."""
    with monkeypatch.context() as patched:
        patched.setattr(zipfile, 'ZIP_FILECOUNT_LIMIT', 0)  # force zipfile to write the zip64 records
        raw = bytearray(_zip({'a.srt': SRT, 'b.txt': INLINE_TXT}))
    assert b'PK\x06\x06' in raw and b'PK\x06\x07' in raw
    # Some writers always defer to the zip64 record: the classic counts become markers.
    end = raw.rfind(b'PK\x05\x06')
    struct.pack_into('<2H', raw, end + 8, 0xFFFF, 0xFFFF)
    archive = bytes(raw)

    _run(tmp_path, 'export.zip', archive)

    assert job.final()['status'] == ImportJobStatus.completed.value
    assert len(job.store.docs) == 2


def _flag_members_encrypted(archive: bytes) -> bytes:
    raw = bytearray(archive)
    for signature, flags_at in ((b'PK\x01\x02', 8), (b'PK\x03\x04', 6)):
        index = raw.find(signature)
        while index >= 0:
            struct.pack_into('<H', raw, index + flags_at, 1)
            index = raw.find(signature, index + 1)
    return bytes(raw)


def test_password_protected_archive_is_rejected_with_a_plain_message(tmp_path, job):
    _run(tmp_path, 'export.zip', _flag_members_encrypted(_zip({'a.srt': SRT, 'b.txt': INLINE_TXT})))

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert final['error'] == "Password-protected ZIP files aren't supported."
    assert job.store.docs == {}


def _corrupt_stored_member(archive: bytes) -> bytes:
    raw = bytearray(archive)
    data_start = raw.find(b'PK\x03\x04') + 30 + len('a.srt')
    raw[data_start] ^= 0xFF
    return bytes(raw)


class InvalidArgument(Exception):
    """Stands in for the Firestore error a too-large document raises."""


@pytest.mark.parametrize(
    ('case', 'reason'),
    [
        ('damaged-member', 'file is damaged'),
        ('store-rejects', 'could not be saved'),
        ('unexpected', 'unexpected error'),
    ],
)
def test_per_file_failures_reach_users_as_plain_reasons(tmp_path, job, monkeypatch, caplog, case, reason):
    archive = _zip({'a.srt': SRT})
    if case == 'damaged-member':
        archive = _corrupt_stored_member(_zip({'a.srt': SRT}, ZIP_STORED))
    elif case == 'store-rejects':

        def reject(uid, data):
            raise InvalidArgument('document too large')

        monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', reject)
    else:

        def explode(*_args, **_kwargs):
            raise KeyError('speaker')

        monkeypatch.setattr(tf, 'parse_transcript_file', explode)

    with caplog.at_level('WARNING', logger=tf.logger.name):
        _run(tmp_path, 'export.zip', archive)

    final = job.final()
    assert final['error'] == f'None of the 1 file(s) could be imported ({reason}).'
    assert not any(name in final['error'] for name in ('BadZipFile', 'InvalidArgument', 'KeyError', 'Error'))
    assert 'error_class=' in caplog.text, 'the exception class is still logged'


@pytest.mark.parametrize('data', [b'hello\x81\x8d\x8f', ('hello' + '\ufffd' * 3).encode('utf-8')])
def test_replacement_heavy_text_is_not_a_transcript(data):
    assert tf._decode_transcript(data) is None
    assert tf.parse_transcript_file('renamed.txt', data) is None


def test_windows_text_with_a_rare_replacement_is_still_readable():
    data = b'Windows meeting transcript with caf\xe9 and useful notes. ' * 2 + b'\x81'
    assert tf._decode_transcript(data) is not None


def test_byte_quota_charges_only_new_conversations(tmp_path, job, monkeypatch):
    reserve, release = MagicMock(return_value='bytes-1'), MagicMock()
    monkeypatch.setattr(tf.import_quotas_db, 'reserve_import_quota', reserve)
    monkeypatch.setattr(tf.import_quotas_db, 'release_import_quota', release)

    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))
    reserve.assert_called_once_with(UID, 'byte', len(SRT.encode('utf-8')))
    release.assert_not_called()
    reserve.reset_mock()
    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))
    reserve.assert_called_once_with(UID, 'byte', len(SRT.encode('utf-8')))
    release.assert_called_once_with(UID, 'byte', 'bytes-1')
    assert len(job.store.docs) == 1


def test_failed_create_releases_the_byte_reservation(tmp_path, job, monkeypatch):
    release = MagicMock()
    monkeypatch.setattr(tf.import_quotas_db, 'release_import_quota', release)
    monkeypatch.setattr(
        tf.lifecycle_service, 'persist_imported_conversation', MagicMock(side_effect=RuntimeError('down'))
    )

    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))

    release.assert_called_once_with(UID, 'byte', 'reservation')
    assert not job.store.docs


def test_duplicate_stays_skipped_when_releasing_its_byte_reservation_fails(tmp_path, job, monkeypatch):
    monkeypatch.setattr(tf.import_quotas_db, 'release_import_quota', MagicMock(side_effect=RuntimeError('redis down')))

    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))
    _run(tmp_path, 'call.srt', SRT.encode('utf-8'))

    assert job.final()['status'] == 'completed'
    assert job.final()['conversations_skipped'] == 1
    assert len(job.store.docs) == 1


@pytest.mark.parametrize('allow_first', [True, False])
def test_worker_finishes_with_monthly_limit_reason_and_skips_remaining_files(tmp_path, job, monkeypatch, allow_first):
    reserve = MagicMock(side_effect=['bytes-1', None] if allow_first else [None])
    monkeypatch.setattr(tf.import_quotas_db, 'reserve_import_quota', reserve)

    _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.vtt': VTT, 'c.txt': OTTER_STYLE_TXT}))

    assert job.final()['status'] == 'completed'
    assert job.final()['conversations_created'] == int(allow_first)
    assert 'monthly import limit reached' in job.final()['error']
    assert job.state['processed_files'] == 3
    assert reserve.call_count == (2 if allow_first else 1)


@pytest.mark.parametrize('status', ['pending', 'processing', 'completed', 'failed', 'cancelled', None])
def test_cancel_transaction_only_applies_to_active_jobs(status):
    client = StrictFirestore()
    ref = client.collection('import_jobs').document('job-1')
    if status is not None:
        ref.create({'status': status})

    applied = tf.import_jobs_db.cancel_import_job_if_active('job-1', firestore_client=client)

    assert applied == (status in ('pending', 'processing'))
    assert ref.get().to_dict() == (
        {'status': 'cancelled', 'error': 'Cancelled by user'} if applied else {'status': status} if status else None
    )


def test_a_shutdown_while_a_file_is_queued_reserves_no_bytes(tmp_path, job, monkeypatch):
    """Cancelled before its file thread starts, an import never reserves quota for that file."""
    reserve, release = MagicMock(return_value='bytes-1'), MagicMock()
    monkeypatch.setattr(tf.import_quotas_db, 'reserve_import_quota', reserve)
    monkeypatch.setattr(tf.import_quotas_db, 'release_import_quota', release)
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(tf, 'storage_executor', pool)
    occupied, release_pool = threading.Event(), threading.Event()
    job_cancelled = tf._job_cancelled

    def before_the_file(job_id):
        # Another request takes the storage pool's only thread before the file is queued.
        pool.submit(lambda: (occupied.set(), release_pool.wait(5)))
        return job_cancelled(job_id)

    monkeypatch.setattr(tf, '_job_cancelled', before_the_file)
    path = tmp_path / 'export.zip'
    path.write_bytes(_zip({'a.srt': SRT}))

    async def main():
        task = asyncio.create_task(
            tf.process_transcript_import('job-1', UID, str(path), original_filename='export.zip')
        )
        while not (occupied.is_set() and pool._work_queue.qsize() == 1):
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.05)
        release_pool.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(main())
    finally:
        release_pool.set()
        pool.shutdown(wait=True)

    reserve.assert_not_called()
    release.assert_not_called()
    assert job.store.docs == {}
    assert job.final()['error'] == tf.INTERRUPTED_ERROR


def test_a_shutdown_during_a_failing_save_still_releases_its_bytes(tmp_path, job, monkeypatch):
    """The file thread outlives the cancelled task; a save that then fails gives the bytes back."""
    release = MagicMock()
    monkeypatch.setattr(tf.import_quotas_db, 'release_import_quota', release)
    blocked, unblock = threading.Event(), threading.Event()

    def slow_failing_save(uid, payload):
        blocked.set()
        unblock.wait(5)
        raise RuntimeError('firestore down')

    monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', slow_failing_save)

    _cancel_while(tmp_path, _zip({'a.srt': SRT}), blocked, unblock)
    deadline = time.monotonic() + 5
    while not release.called and time.monotonic() < deadline:
        time.sleep(0.01)

    release.assert_called_once_with(UID, 'byte', 'reservation')
    assert job.store.docs == {}
