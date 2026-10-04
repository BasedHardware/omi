"""Transcript-file import: bring conversations recorded elsewhere into Omi.

Exports from other recorders and meeting tools arrive as SRT, WebVTT or plain
text transcripts, alone or zipped. Like the Limitless importer this is a light
import: parse, store the transcript as a completed conversation, no AI. These
tests pin the parsers, speaker and people mapping, deterministic idempotent IDs,
upload limits, and the job lifecycle.
"""

import codecs
import io
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZIP_LZMA, ZipFile

import pytest

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
        ('Opening turn.', 0, 1.0),
        ('Later turn.', 1, 5.0),
        ('Still Sam.', 1, segments[1].end),
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
    store = _Store()
    updates: list = []
    state = {'status': ImportJobStatus.pending.value}
    notifications: list = []
    reads: list = []

    def update(job_id, fields):
        updates.append(fields)
        state.update(fields)

    def get(job_id):
        reads.append(dict(state))
        return dict(state)

    monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', store.persist)
    monkeypatch.setattr(tf.import_jobs_db, 'update_import_job', update)
    monkeypatch.setattr(tf.import_jobs_db, 'get_import_job', get)
    monkeypatch.setattr(tf, 'get_user_name', lambda *_a, **_k: 'Jane Doe')
    monkeypatch.setattr(tf, 'load_people_names', lambda _uid: {'sam': 'person-sam'})

    def dispatch(intent):
        notifications.append(intent)
        return NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=1)

    monkeypatch.setattr(tf, 'dispatch_notification', dispatch)
    return SimpleJob(store, updates, state, notifications, reads)


class SimpleJob:
    def __init__(self, store, updates, state, notifications, reads):
        self.store = store
        self.updates = updates
        self.state = state
        self.notifications = notifications
        self.reads = reads

    def cancel(self):
        self.state['status'] = ImportJobStatus.cancelled.value

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
    tf.process_transcript_import('job-1', UID, str(path), original_filename=name, **kwargs)
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
    big = 'x' * 500
    _run(tmp_path, 'export.zip', _zip({'ok.srt': SRT[:150], 'huge.txt': big}))

    final = job.final()
    assert final['status'] == ImportJobStatus.completed.value
    assert final['conversations_created'] == 1
    assert final['error'] == '1 file(s) could not be imported'


def test_archive_over_member_or_size_budget_is_rejected_before_reading(tmp_path, job, monkeypatch):
    monkeypatch.setattr(tf, 'MAX_TRANSCRIPT_FILES', 2)
    _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.srt': SRT, 'c.srt': SRT}))

    final = job.final()
    assert final['status'] == ImportJobStatus.failed.value
    assert 'at most 2 transcript files' in final['error']
    assert job.store.docs == {}


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
    """A cancel is read at each progress update (every 10 files), like the Limitless importer."""
    created_before_cancel = []
    original = job.store.persist

    def persist_then_cancel(uid, data):
        created_before_cancel.append(data['id'])
        job.cancel()
        return original(uid, data)

    monkeypatch.setattr(tf.lifecycle_service, 'persist_imported_conversation', persist_then_cancel)

    _run(tmp_path, 'export.zip', _zip(_numbered_srts(25)))

    assert len(created_before_cancel) == 10
    assert job.final_status_writes() == []
    assert job.state['status'] == ImportJobStatus.cancelled.value


def test_cancel_is_read_per_progress_update_not_per_file(tmp_path, job):
    _run(tmp_path, 'export.zip', _zip(_numbered_srts(25)))

    # Before the processing write, before the first file, after files 10 and 20, before the final write.
    assert len(job.reads) == 5
    assert job.final()['status'] == ImportJobStatus.completed.value
    assert len(job.store.docs) == 25


def test_job_cancelled_before_it_starts_never_becomes_processing(tmp_path, job):
    job.cancel()

    upload = _run(tmp_path, 'export.zip', _zip({'a.srt': SRT, 'b.txt': INLINE_TXT}))

    assert job.state['status'] == ImportJobStatus.cancelled.value
    assert not [u for u in job.updates if 'status' in u]
    assert job.store.docs == {}
    assert job.notifications == []
    assert not upload.exists(), 'a cancelled upload is still cleaned up'


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

    def name_then_cancel(*_args, **_kwargs):
        job.cancel()
        return 'Jane Doe'

    monkeypatch.setattr(tf, 'get_user_name', name_then_cancel)

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


def test_job_uses_its_own_source_type(monkeypatch):
    created = MagicMock()
    monkeypatch.setattr(tf.import_jobs_db, 'create_import_job', created)

    job = tf.create_transcript_import_job(UID)

    assert job.source_type == ImportSourceType.transcript_files
    assert created.call_args.args[0]['source_type'] == 'transcript_files'
