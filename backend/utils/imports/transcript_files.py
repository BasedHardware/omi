"""Transcript-file import: SRT, WebVTT and plain-text transcripts from other tools.

People switching from other recorders and meeting tools can bring their history:
export transcripts as ``.srt``, ``.vtt`` or ``.txt`` (alone or zipped) and each file
becomes a completed Omi conversation. Like the Limitless importer this is a light
import — parse and store the transcript, no AI processing — so it is fast, cheap,
and idempotent (a file's content decides its conversation ID).
"""

from __future__ import annotations

import asyncio
import codecs
import hashlib
import html
import logging
import os
import re
import struct
import threading
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo, is_zipfile
from zoneinfo import ZoneInfo

import database.conversations as conversations_db
import database.import_jobs as import_jobs_db
import database.import_quotas as import_quotas_db
import database.users as users_db
from database.auth import get_user_full_name
from database.document_ids import document_id_from_seed
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.import_job import ImportJob, ImportJobStatus, ImportSourceType
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
from models.transcript_segment import TranscriptSegment
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.projection_payload import omit_null_processing_state
from utils.executors import db_executor, run_blocking, storage_executor
from utils.notification_dispatch import (
    NotificationDispatchStatus,
    NotificationIntent,
    NotificationKind,
    dispatch_notification,
)

logger = logging.getLogger(__name__)

TRANSCRIPT_EXTENSIONS = ('.srt', '.vtt', '.txt')
UPLOAD_EXTENSIONS = ('.zip', *TRANSCRIPT_EXTENSIONS)
TRANSCRIPT_ORIGINS = {'plaud': ConversationSource.plaud, 'other': ConversationSource.unknown}
MAX_TRANSCRIPT_FILES = 1000
# Hostile text costs about 1 s of parsing per MiB; this keeps one import to minutes.
MAX_ARCHIVE_TRANSCRIPT_BYTES = 50 * 1024 * 1024
# Each file becomes one conversation document, which Firestore caps at 1 MiB. The
# transcript is stored as zlib(json), and 'enhanced' protection then stores that as
# hex -> AES -> base64 (about 2.67x), so 350 KB of zlib output is about 935 KB stored.
MAX_TRANSCRIPT_FILE_BYTES = 1024 * 1024
MAX_TRANSCRIPT_SEGMENTS = 5_000
MAX_COMPRESSED_TRANSCRIPT_BYTES = 350_000
# Opening a ZIP loads its whole central directory before any member limit applies,
# so the size the end record declares is checked first.
MAX_ZIP_DIRECTORY_ENTRIES = 20_000
# zipfile reads entries until the directory's declared bytes run out, whatever count
# it declares, so the byte cap is what bounds the work; 2 MiB is thousands of entries.
MAX_ZIP_DIRECTORY_BYTES = 2 * 1024 * 1024
# Deflate honors the per-read output cap; bzip2 and LZMA members decompress a
# whole input block regardless, so a tiny member can expand past every limit.
READABLE_ZIP_COMPRESSION = (ZIP_STORED, ZIP_DEFLATED)
# Untimed text gets estimated times so turns keep their order and the
# conversation a plausible duration (about 150 spoken words per minute).
ESTIMATED_WORDS_PER_SECOND = 2.5
DEFAULT_TITLE = 'Imported transcript'
MAX_TITLE_CHARS = 200
# Never change: baked into the ID of every conversation already imported.
TRANSCRIPT_IMPORT_ID_NAMESPACE = 'transcript-file'
# A file counts as speaker-labeled when most cues open with "Name: ".
LABELED_FILE_MIN_SHARE = 0.6
# Earlier file-name dates are an unset device clock or not a date at all.
MIN_FILENAME_YEAR = 1990


class TranscriptImportError(Exception):
    """An upload the importer refuses as a whole, with a user-facing reason."""


# Why one file was skipped, as shown to the user. Exception class names stay in logs.
MAX_REPLACEMENT_CHARACTER_SHARE = 0.02
MONTHLY_LIMIT_REACHED = 'monthly import limit reached'
NOT_A_TRANSCRIPT = 'not a readable transcript'
FILE_TOO_LARGE = 'file too large'
TRANSCRIPT_TOO_LONG = 'transcript too long'
FILE_DAMAGED = 'file is damaged'
NOT_SAVED = 'could not be saved'
UNEXPECTED_ERROR = 'unexpected error'
# Files already imported are skipped as duplicates on the retry this asks for.
INTERRUPTED_ERROR = 'The import was interrupted. Please try again.'
UNEXPECTED_IMPORT_ERROR = 'There was an error importing your transcripts. Please try again.'


class TranscriptFileSkipped(Exception):
    """One file the import skips, with the reason shown to the user; the others still import."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TranscriptCue:
    text: str
    # The speaker's name as the file wrote it (a "Name:" label, a <v Name> voice, a header).
    # ``text`` never repeats it; ``segments_from_cues`` decides whether the segment does.
    speaker: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None


@dataclass(frozen=True)
class ParsedTranscript:
    title: str
    started_at: Optional[datetime]
    cues: tuple[TranscriptCue, ...]


# --------------------------------------------------------------------------- parsing

# Hours are bounded so a cue claiming a 5,000-digit hour is not a timestamp at all.
_TIMESTAMP = r'(?:\d{1,3}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?'
_TIMESTAMP_RE = re.compile(r'(?:(\d{1,3}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?')
_CUE_TIMING_RE = re.compile(rf'^\s*({_TIMESTAMP})\s*-->\s*({_TIMESTAMP})')
_LABEL_RE = re.compile(r"^(?P<label>[^\W\d_][^:\n]{0,39}?)\s*:\s+(?P<rest>\S.*)$")
# A whole label that is a generic placeholder, not a name: "Speaker 2", "SPEAKER_01",
# "spk 3", "Participant 1", "Unknown Speaker". It is a speaker even as a one-off, and
# it names no one, so it never stays in the text. "Speakers" or "Speaker of the House" is not one.
_GENERIC_SPEAKER_RE = re.compile(
    r'^(?:(?:speaker|participant|person|spk)[\s_]*\d+|(?:unknown|unidentified)\s+(?:speaker|participant))$',
    re.IGNORECASE,
)
# These run on uploaded lines of up to a few MB while holding the GIL, so each
# must stay linear: no two adjacent unbounded runs that can trade characters
# (a tag or voice ends at the next '<', and a header name is capped).
_VOICE_RE = re.compile(r'<v(?:\.[\w.-]+)?\s+([^<>\s][^<>]*)>')
_VOICE_END_RE = re.compile(r'</v\s*>')
_WORD_RE = re.compile(r'\w')
# WebVTT escapes every literal '<', so any '<...>' in a cue is markup.
_TAG_RE = re.compile(r'<[^<>]*>')
# SRT does not escape: only its own formatting tags (<i>, <b>, <u>, <s>, <font ...>) are
# markup, and other angle brackets are words ("if x < 10 and y > 5", "<-").
_SRT_TAG_RE = re.compile(r'</?(?:[ibus]|font)\b[^<>]*>', re.IGNORECASE)
# A character reference ends with ';': "meeting&notes" is text, not "&not" + "es".
_ENTITY_RE = re.compile(r'&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});')
_HEADER_NAME_FIRST_RE = re.compile(rf'^(?P<name>\S(?:[^\n]{{0,58}}\S)?)\s{{2,}}\(?(?P<ts>{_TIMESTAMP})\)?$')
_HEADER_TIME_FIRST_RE = re.compile(rf"^\[?(?P<ts>{_TIMESTAMP})\]?\s+(?P<name>[^\W\d_][\w .'-]{{0,39}})$")
# An optional "--> end" (one-line cues, whisper.cpp's "[start --> end]") is consumed whole,
# so its dash is never taken for the "-" separator before the text, and kept as the turn's end.
_INLINE_TIMED_RE = re.compile(
    rf'^\[?(?P<ts>{_TIMESTAMP})(?![\d.,:])(?:\s*-->\s*(?P<end>{_TIMESTAMP})(?![\d.,:]))?+\]?+\s*(?:-\s*)?(?P<rest>\S.*)$'
)
# A line that is only a timing ("[00:32.000 --> 00:36.000]", an empty whisper.cpp
# segment): it carries no words.
_BARE_TIMING_RE = re.compile(rf'^\[?(?P<ts>{_TIMESTAMP})(?:\s*-->\s*(?P<end>{_TIMESTAMP}))?\]?$')
# What may follow an SRT timing line's end time: cue settings (SRT's "X1:40 Y1:20",
# WebVTT's "align:start position:10%"). Anything else is the text of a one-line cue.
_CUE_SETTINGS_RE = re.compile(r'(?:\s+(?:[XY][12]|align|position|line|size|vertical|region):\S+)*\s*', re.IGNORECASE)


def _seconds(value: str) -> Optional[float]:
    match = _TIMESTAMP_RE.fullmatch(value.strip())
    if not match:
        return None
    hours, minutes, seconds, fraction = match.groups()
    try:
        if int(seconds) >= 60 or (hours is not None and int(minutes) >= 60):
            return None
        total = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
        if fraction:
            total += int(fraction.ljust(3, '0')) / 1000
        return float(total)
    except (ValueError, OverflowError):
        # One unreadable timestamp leaves its cue untimed; it never fails the file.
        return None


def _normalize(text: str) -> str:
    return text.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')


def _unescape(text: str) -> str:
    """Decode each ``;``-terminated character reference once; a bare "&" stays text."""
    return _ENTITY_RE.sub(lambda entity: html.unescape(entity.group(0)), text)


def _plain_cue_text(raw: str, tags: re.Pattern[str]) -> str:
    """A cue's text without its markup: the ``tags`` its format uses, then character references."""
    return re.sub(r'\s+', ' ', _unescape(tags.sub('', raw))).strip()


def _blocks(text: str) -> List[List[str]]:
    blocks: List[List[str]] = []
    for raw in re.split(r'\n\s*\n', _normalize(text)):
        lines = [line.strip() for line in raw.split('\n') if line.strip()]
        if lines:
            blocks.append(lines)
    return blocks


def _is_name_label(label: str) -> bool:
    return 0 < len(label.split()) <= 4


def _assign_speakers(cues: Sequence[TranscriptCue]) -> List[TranscriptCue]:
    """Split "Name: text" prefixes into speakers without mistaking prose for names.

    A label is a speaker when the file is mostly speaker-labeled, when it is a
    generic ``Speaker N`` label, or when it recurs. A one-off "Note: ..." in an
    otherwise unlabeled file stays text. A name split off here is never lost:
    ``segments_from_cues`` puts it back in front of the text unless it names the
    owner or a known person, or is a generic placeholder that names no one.
    """
    labeled: List[Optional[tuple[str, str]]] = []
    for cue in cues:
        match = _LABEL_RE.match(cue.text) if cue.speaker is None else None
        if match and _is_name_label(match.group('label')):
            labeled.append((match.group('label').strip(), match.group('rest').strip()))
        else:
            labeled.append(None)
    candidates = sum(1 for cue, label in zip(cues, labeled) if label is not None or cue.speaker is not None)
    mostly_labeled = bool(cues) and candidates / len(cues) >= LABELED_FILE_MIN_SHARE
    counts: Dict[str, int] = {}
    for label in labeled:
        if label:
            counts[label[0].casefold()] = counts.get(label[0].casefold(), 0) + 1
    result: List[TranscriptCue] = []
    for cue, label in zip(cues, labeled):
        if label and (mostly_labeled or _GENERIC_SPEAKER_RE.match(label[0]) or counts[label[0].casefold()] > 1):
            result.append(TranscriptCue(text=label[1], speaker=label[0], start=cue.start, end=cue.end))
        else:
            result.append(cue)
    return result


def _srt_block_cues(lines: Sequence[str], *, keep_label: bool = False) -> Optional[List[TranscriptCue]]:
    """The cues in one SRT block, or None when neither of its first two lines is a cue timing.

    A timing line followed by its text on the next lines is one cue. A timing line
    that carries text itself ("00:00:01.000 --> 00:00:05.000 Hello") starts a run of
    one-line cues, one per timing line; other lines continue the cue above them.
    The line before a timing is the cue number; with ``keep_label`` (a .txt) a line
    there that is not a number (a title, "Clip", "Quote:") is kept as its own cue.
    SRT's formatting tags (``<i>``, ``<b>``, ``<u>``, ``<s>``, ``<font ...>``) are
    removed from cue text before any "Name: " label is looked for; other angle
    brackets are kept as words.
    """
    timing_index = next((index for index, line in enumerate(lines[:2]) if _CUE_TIMING_RE.match(line)), None)
    if timing_index is None:
        return None
    timing = _CUE_TIMING_RE.match(lines[timing_index])
    assert timing is not None
    label = lines[0] if keep_label and timing_index == 1 and not lines[0].isdigit() else ''
    labels = [TranscriptCue(text=label)] if label else []
    if _CUE_SETTINGS_RE.fullmatch(lines[timing_index], timing.end()):
        body = _plain_cue_text(' '.join(lines[timing_index + 1 :]), _SRT_TAG_RE)
        start, end = _seconds(timing.group(1)), _seconds(timing.group(2))
        return labels + ([TranscriptCue(text=body, start=start, end=end)] if body else [])
    runs: List[tuple[re.Match[str], List[str]]] = []
    for line in lines[timing_index:]:
        line_timing = _CUE_TIMING_RE.match(line)
        if line_timing:
            runs.append((line_timing, [line[line_timing.end() :].strip()]))
        else:
            runs[-1][1].append(line)
    cues: List[TranscriptCue] = labels
    for line_timing, parts in runs:
        body = _plain_cue_text(' '.join(parts), _SRT_TAG_RE)
        if body:
            cues.append(
                TranscriptCue(text=body, start=_seconds(line_timing.group(1)), end=_seconds(line_timing.group(2)))
            )
    return cues


def _paragraph_cues(block: Sequence[str]) -> List[TranscriptCue]:
    """An untimed block: one cue per "Name: text" turn when it holds several, else one cue.

    A line that is not a label continues the turn above it (a wrapped turn), or
    stands as its own cue before the first label (a title).
    """
    labeled = [_LABEL_RE.match(line) is not None for line in block]
    if sum(labeled) < 2:
        return [TranscriptCue(text=' '.join(block))]
    turns: List[List[str]] = []
    for line, is_label in zip(block, labeled):
        if is_label or not turns:
            turns.append([line])
        else:
            turns[-1].append(line)
    return [TranscriptCue(text=' '.join(turn)) for turn in turns]


def parse_srt(text: str) -> List[TranscriptCue]:
    cues: List[TranscriptCue] = []
    for lines in _blocks(text):
        cues.extend(_srt_block_cues(lines) or [])
    return _assign_speakers(cues)


def _voice_runs(raw: str) -> List[tuple[Optional[str], str]]:
    """A WebVTT cue's text as (voice, plain text) runs, in order.

    A voice annotates only its own span (WebVTT 4.2.2), so ``<v Alice>Ship it?</v>
    <v Bob>Not yet.</v>`` is two runs, and text outside every span is a run with no
    voice. As in the WebVTT parser, ``<v>`` opens a span inside any still open, ``</v>``
    closes the innermost, and an unclosed span runs to the end of the cue; text goes to
    the innermost open voice. Other tags are formatting and are dropped.

    A run with no word characters (the space or the "- " dash between two spans) is
    dropped when the cue has words elsewhere, so it never becomes a turn of its own;
    then adjacent runs of one voice merge. Raises ``TranscriptFileSkipped`` once the cue
    holds more spans than a conversation can hold segments.
    """
    pieces: List[tuple[Optional[str], List[str]]] = [(None, [])]
    voices: List[str] = []
    position = 0
    for tag in _TAG_RE.finditer(raw):
        pieces[-1][1].append(raw[position : tag.start()])
        position = tag.end()
        voice = _VOICE_RE.fullmatch(tag.group(0))
        if voice:
            voices.append(_unescape(voice.group(1)).strip())
        elif _VOICE_END_RE.fullmatch(tag.group(0)):
            if voices:
                voices.pop()
        else:
            continue
        # Spans alternate with the text between them: past twice the cap, the runs are too.
        if len(pieces) > 2 * MAX_TRANSCRIPT_SEGMENTS:
            raise TranscriptFileSkipped(TRANSCRIPT_TOO_LONG)
        pieces.append((voices[-1] if voices else None, []))
    pieces[-1][1].append(raw[position:])
    bodies = [(speaker, _plain_cue_text(''.join(parts), _TAG_RE)) for speaker, parts in pieces]
    bodies = [(speaker, body) for speaker, body in bodies if body]
    if any(_WORD_RE.search(body) for _, body in bodies):
        bodies = [(speaker, body) for speaker, body in bodies if _WORD_RE.search(body)]
    merged: List[tuple[Optional[str], List[str]]] = []
    for speaker, body in bodies:
        if merged and merged[-1][0] == speaker:
            merged[-1][1].append(body)
        else:
            merged.append((speaker, [body]))
    return [(speaker, ' '.join(parts)) for speaker, parts in merged]


def _voice_run_cues(
    runs: Sequence[tuple[Optional[str], str]], start: Optional[float], end: Optional[float]
) -> List[TranscriptCue]:
    """One cue per voice run, sharing out the cue's time range by word count.

    A cue gives no timing finer than its own range, so each run gets a consecutive
    slice of it in proportion to its words, the first starting at the cue's start and
    the last ending at its end (rounded to the millisecond); the runs stay in order
    and do not overlap. A cue whose range is too short to give every run a slice of at
    least a millisecond, or that has no usable range (a missing time, or an end not
    after the start), leaves every run with the cue's own timing, for
    ``segments_from_cues`` to settle; those runs share that range.
    """
    unsplit = [TranscriptCue(text=text, speaker=speaker, start=start, end=end) for speaker, text in runs]
    if start is None or end is None or end <= start or len(runs) == 1:
        return unsplit
    words = [max(1, len(text.split())) for _, text in runs]
    total = sum(words)
    cues: List[TranscriptCue] = []
    spoken = 0
    run_start = start
    for (speaker, text), count in zip(runs, words):
        spoken += count
        run_end = end if spoken == total else round(start + (end - start) * spoken / total, 3)
        if run_end <= run_start:
            return unsplit
        cues.append(TranscriptCue(text=text, speaker=speaker, start=run_start, end=run_end))
        run_start = run_end
    return cues


def parse_vtt(text: str) -> List[TranscriptCue]:
    cues: List[TranscriptCue] = []
    for lines in _blocks(text):
        first = lines[0]
        if first.startswith('WEBVTT') or first.split(' ', 1)[0] in ('NOTE', 'STYLE', 'REGION'):
            continue
        timing_index = next((index for index, line in enumerate(lines[:2]) if '-->' in line), None)
        if timing_index is None:
            continue
        timing = _CUE_TIMING_RE.match(lines[timing_index])
        runs = _voice_runs(' '.join(lines[timing_index + 1 :]))
        if not timing or not runs:
            continue
        cues.extend(_voice_run_cues(runs, _seconds(timing.group(1)), _seconds(timing.group(2))))
        if len(cues) > MAX_TRANSCRIPT_SEGMENTS:
            # More turns than one conversation holds: stop rather than split the rest.
            raise TranscriptFileSkipped(TRANSCRIPT_TOO_LONG)
    return _assign_speakers(cues)


def _labeled(match: Optional[re.Match[str]]) -> Optional[re.Match[str]]:
    return match if match and _is_name_label(match.group('name')) else None


def _header_lines(content: Sequence[str]) -> List[Optional[re.Match[str]]]:
    """Per non-empty line, the speaker header that opens a turn there, if any.

    "Name  0:03" headers win when a file has them, so a body line such as
    "10:30 works for me" stays text. Otherwise "[00:01] Name" opens a turn only
    when an untimed body line follows it: "[00:01] Hello there" followed by
    another timed line is an inline-timestamped transcript, not a speaker.
    """
    name_first = [_labeled(_HEADER_NAME_FIRST_RE.match(line)) for line in content]
    if any(name_first):
        return name_first
    headers: List[Optional[re.Match[str]]] = []
    for index, line in enumerate(content):
        following = content[index + 1] if index + 1 < len(content) else None
        if following is None or _INLINE_TIMED_RE.match(following):
            headers.append(None)
        else:
            headers.append(_labeled(_HEADER_TIME_FIRST_RE.match(line)))
    return headers


def _parse_header_turns(content: Sequence[str], headers: Sequence[Optional[re.Match[str]]]) -> List[TranscriptCue]:
    turns: List[tuple[Optional[re.Match[str]], List[str]]] = [(None, [])]
    for line, header in zip(content, headers):
        if header:
            turns.append((header, []))
        else:
            turns[-1][1].append(line)
    cues: List[TranscriptCue] = []
    for header, body in turns:
        if header is None:
            if body:
                cues.append(TranscriptCue(text=' '.join(body)))
            continue
        name, start = header.group('name').strip(), _seconds(header.group('ts'))
        if body:
            cues.append(TranscriptCue(text=' '.join(body), speaker=name, start=start))
        else:
            # Nothing under it: keep the line's words as text rather than drop them.
            cues.append(TranscriptCue(text=name, start=start))
    return cues


def parse_text_transcript(text: str, *, blocks: Optional[Sequence[Sequence[str]]] = None) -> List[TranscriptCue]:
    """Speaker-header, inline-timestamped or paragraph text. ``blocks`` reuses ``_blocks(text)``."""
    content = [line.strip() for line in _normalize(text).split('\n') if line.strip()]
    if not content:
        return []
    headers = _header_lines(content)
    if any(headers):
        return _parse_header_turns(content, headers)
    timed = [_INLINE_TIMED_RE.match(line) or _BARE_TIMING_RE.match(line) for line in content]
    if sum(1 for match in timed if match) * 2 >= len(content):
        # A timed line opens a turn; a timing alone on its line (an empty whisper.cpp
        # segment, or a timing with its text below) opens one with no text yet, and
        # turns that stay empty are dropped. Lines before the first timing keep their
        # words as an untimed cue. Each turn is joined once (per-line rebuilds were quadratic).
        # A "[start --> end]" timing keeps its end; segments_from_cues estimates one only
        # when it is missing or not after the start.
        lead: List[str] = []
        turns: List[tuple[Optional[float], Optional[float], List[str]]] = []
        for line, match in zip(content, timed):
            if match:
                rest = match.groupdict().get('rest')
                end = match.group('end')
                turns.append(
                    (_seconds(match.group('ts')), _seconds(end) if end else None, [rest.strip()] if rest else [])
                )
            elif turns:
                turns[-1][2].append(line)
            else:
                lead.append(line)
        cues = [TranscriptCue(text=' '.join(lead))] if lead else []
        cues.extend(TranscriptCue(text=' '.join(parts), start=start, end=end) for start, end, parts in turns if parts)
        return _assign_speakers(cues)
    cues: List[TranscriptCue] = []
    for block in _blocks(text) if blocks is None else blocks:
        cues.extend(_paragraph_cues(block))
    return _assign_speakers(cues)


_FILENAME_DATETIME_RES = (
    re.compile(
        r'(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})[ T_]+(?P<h>\d{2})[:_.h-](?P<mi>\d{2})(?:[:_.m-](?P<s>\d{2}))?'
    ),
    re.compile(r'(?<!\d)(?P<y>\d{4})(?P<mo>\d{2})(?P<d>\d{2})[_T -]?(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})?(?!\d)'),
)


def _filename_datetime_match(stem: str) -> Optional[re.Match[str]]:
    for pattern in _FILENAME_DATETIME_RES:
        match = pattern.search(stem)
        if match:
            return match
    return None


def _zone(tz: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(tz or 'UTC')
    except Exception:
        return ZoneInfo('UTC')


def started_at_from_filename(filename: str, tz: Optional[str] = 'UTC') -> Optional[datetime]:
    """Recording start from a date-time in the file name, read in the user's timezone."""
    match = _filename_datetime_match(PurePosixPath(filename).stem)
    if not match:
        return None
    parts = match.groupdict()
    if int(parts['y']) < MIN_FILENAME_YEAR:
        return None
    try:
        local = datetime(
            int(parts['y']),
            int(parts['mo']),
            int(parts['d']),
            int(parts['h']),
            int(parts['mi']),
            int(parts['s'] or 0),
            tzinfo=_zone(tz),
        )
        # A date in the future is a wrong device clock; it would sort above every real conversation.
        return min(local.astimezone(timezone.utc), datetime.now(timezone.utc))
    except (ValueError, OverflowError):
        # Not a real date (or past datetime's range in UTC): the caller falls back.
        return None


def title_from_filename(filename: str) -> str:
    stem = PurePosixPath(filename).stem
    match = _filename_datetime_match(stem)
    if match:
        stem = stem[: match.start()] + ' ' + stem[match.end() :]
    title = re.sub(r'\s+', ' ', re.sub(r'[_]+|(?<=\w)-(?=\w)', ' ', stem)).strip(' -_.')
    if len(title) > MAX_TITLE_CHARS:
        cut = title[: MAX_TITLE_CHARS + 1]
        space = cut.rfind(' ')
        # End on the last whole word that fits, unless that would drop most of the title.
        title = (cut[:space] if space > MAX_TITLE_CHARS // 2 else cut[:MAX_TITLE_CHARS]).strip(' -_.')
    return title if title and not title.replace(' ', '').isdigit() else DEFAULT_TITLE


def _decode_transcript(data: bytes) -> Optional[str]:
    """Text of a transcript file, or ``None`` when the bytes are binary."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        # UTF-16 puts a NUL in every ASCII character, so decode before the binary check.
        try:
            text = data.decode('utf-16')
        except UnicodeDecodeError:
            return None
        if '\x00' in text:
            return None
    else:
        if b'\x00' in data:
            return None
        data = data.removeprefix(codecs.BOM_UTF8)
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('cp1252', errors='replace')
    if text and text.count('\ufffd') / len(text) > MAX_REPLACEMENT_CHARACTER_SHARE:
        return None
    return text


def _txt_srt_cues(blocks: Sequence[Sequence[str]]) -> Optional[List[TranscriptCue]]:
    """A .txt read as SRT when most of its blocks are cues, else None.

    Unlike a .srt, whose untimed blocks are not part of the format, a .txt keeps
    them (a title, notes between quoted clips) as untimed text: reading it as SRT
    only adds the timings and speakers, it never drops words.
    """
    per_block = [_srt_block_cues(lines, keep_label=True) for lines in blocks]
    if sum(1 for cues in per_block if cues is not None) * 2 <= len(blocks):
        return None
    cues: List[TranscriptCue] = []
    for lines, block_cues in zip(blocks, per_block):
        cues.extend(_paragraph_cues(lines) if block_cues is None else block_cues)
    return _assign_speakers(cues)


def parse_transcript_file(filename: str, data: bytes, *, tz: Optional[str] = 'UTC') -> Optional[ParsedTranscript]:
    """Parse one transcript file, or ``None`` when it is not a usable transcript."""
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in TRANSCRIPT_EXTENSIONS:
        return None
    text = _decode_transcript(data)
    if text is None:
        return None
    head = _normalize(text).lstrip()
    if head.startswith('WEBVTT'):
        cues = parse_vtt(text)
    elif extension == '.srt':
        cues = parse_srt(text)
    elif extension == '.vtt':
        cues = parse_vtt(text)
    else:
        blocks = _blocks(text)
        # Every cue timing holds "-->": text without one skips the SRT check.
        srt_cues = _txt_srt_cues(blocks) if '-->' in text else None
        cues = parse_text_transcript(text, blocks=blocks) if srt_cues is None else srt_cues
    cues = [cue for cue in cues if cue.text.strip()]
    if not cues:
        return None
    return ParsedTranscript(
        title=title_from_filename(filename),
        started_at=started_at_from_filename(filename, tz),
        cues=tuple(cues),
    )


# --------------------------------------------------------------------------- conversation


def _estimated_seconds(text: str) -> float:
    return max(1.0, len(text.split()) / ESTIMATED_WORDS_PER_SECOND)


def _in_time_order(cues: Sequence[TranscriptCue]) -> Sequence[TranscriptCue]:
    """Cues sorted by start when the timed ones are out of order (stable).

    An untimed cue keeps the start of the timed cue before it, so a continuation
    stays with its turn.
    """
    starts = [cue.start for cue in cues if cue.start is not None]
    if all(earlier <= later for earlier, later in zip(starts, starts[1:])):
        return cues
    keys: List[float] = []
    current = float('-inf')
    for cue in cues:
        if cue.start is not None:
            current = cue.start
        keys.append(current)
    return [cues[index] for index in sorted(range(len(cues)), key=keys.__getitem__)]


def _next_starts(cues: Sequence[TranscriptCue]) -> List[Optional[float]]:
    """For each cue, the start of the next cue that has one, in one reverse pass."""
    following: List[Optional[float]] = [None] * len(cues)
    upcoming: Optional[float] = None
    for index in range(len(cues) - 1, -1, -1):
        following[index] = upcoming
        if cues[index].start is not None:
            upcoming = cues[index].start
    return following


def _name_key(name: str) -> str:
    """How speaker labels, the owner's name and People names compare: case and spacing aside."""
    return ' '.join(name.split()).casefold()


def _owner_keys(owner_name: Optional[str]) -> frozenset[str]:
    """The labels that name the owner: the whole name, or the first name alone.

    A first name with another surname is someone else: with "Jane Doe" known, "Jane
    Smith" is not the owner. When only one word of the name is known, a longer label
    ("Jane Doe") cannot be told apart from another person with that first name, so
    only the word itself matches.
    """
    full = _name_key(owner_name or '')
    return frozenset({full, full.split(' ')[0]}) if full else frozenset()


def _segment_text(cue: TranscriptCue, *, bound: bool) -> str:
    """The cue's words, led by "Name: " when its speaker's name binds to no one.

    A segment can only name its speaker through ``is_user`` or ``person_id``, so any
    other name ("Alice Chen", or a label that was never a name, such as a recurring
    "TODO" or an agenda heading) stays in the text rather than vanish. A generic
    placeholder ("Speaker 2") names no one: the segment's ``SPEAKER_NN`` already
    records the turn, and repeating it would only duplicate the app's own label.
    Nor is a name added to text that already opens with it (``<v Alice>Alice: hi``).
    """
    if bound or not cue.speaker or _GENERIC_SPEAKER_RE.match(cue.speaker):
        return cue.text
    if cue.text.casefold().startswith(f'{cue.speaker}:'.casefold()):
        return cue.text
    return f'{cue.speaker}: {cue.text}'


def segments_from_cues(
    cues: Sequence[TranscriptCue],
    *,
    owner_name: Optional[str],
    people: Mapping[str, str],
) -> List[TranscriptSegment]:
    """Number speakers by first appearance and bind the owner and known people by name.

    ``owner_name`` is the owner's whole name when known (``get_user_full_name``).
    ``people`` maps name keys (``_name_key``) to person IDs. A speaker name that
    binds to neither stays at the front of its text (``_segment_text``). Timed cues
    are put in time order. Missing end times close at the next turn; untimed cues get
    ordered, estimated times.
    """
    cues = _in_time_order(cues)
    owner_keys = _owner_keys(owner_name)
    speaker_ids: Dict[Optional[str], int] = {}
    segments: List[TranscriptSegment] = []
    next_starts = _next_starts(cues)
    cursor = 0.0
    for cue, following in zip(cues, next_starts):
        key = _name_key(cue.speaker) if cue.speaker else None
        speaker_id = speaker_ids.setdefault(key, len(speaker_ids))
        start = cue.start if cue.start is not None else cursor
        start = max(start, segments[-1].start if segments else 0.0)
        end = cue.end
        if end is None or end <= start:
            end = following if following is not None and following > start else start + _estimated_seconds(cue.text)
        is_user = key in owner_keys
        person_id = None if is_user or key is None else people.get(key)
        segments.append(
            TranscriptSegment(
                text=_segment_text(cue, bound=is_user or person_id is not None),
                speaker=f'SPEAKER_{speaker_id:02d}',
                speaker_id=speaker_id,
                is_user=is_user,
                person_id=person_id,
                start=start,
                end=end,
            )
        )
        cursor = end
    return segments


def conversation_id_for_transcript(uid: str, data: bytes) -> str:
    """Deterministic ID: re-importing the same file finds the same conversation."""
    digest = hashlib.sha256(data).hexdigest()
    return document_id_from_seed(f'{TRANSCRIPT_IMPORT_ID_NAMESPACE}:{uid}:{digest}')


def _overview(segments: Sequence[TranscriptSegment], max_chars: int = 500) -> str:
    texts: List[str] = []
    total = 0
    for segment in segments:
        if total + len(segment.text) > max_chars:
            break
        texts.append(segment.text)
        total += len(segment.text) + 1
    return ' '.join(texts) or (segments[0].text[: max_chars - 3] + '...' if segments else DEFAULT_TITLE)


def load_people_names(uid: str) -> Dict[str, str]:
    """Person name key (``_name_key``) -> person ID, so named speakers bind to known people.

    A name two people share is left out: the label cannot say which of them spoke.
    """
    try:
        people = users_db.get_people(uid)
    except Exception as exc:
        logger.warning('transcript import people lookup failed uid=%s error_class=%s', uid, type(exc).__name__)
        return {}
    ids_by_name: Dict[str, set[str]] = {}
    for person in people:
        name, person_id = (person.get('name') or '').strip(), person.get('id')
        if name and person_id:
            ids_by_name.setdefault(_name_key(name), set()).add(person_id)
    return {name: next(iter(ids)) for name, ids in ids_by_name.items() if len(ids) == 1}


def build_imported_conversation(
    uid: str,
    parsed: ParsedTranscript,
    data: bytes,
    *,
    source: ConversationSource,
    language_code: str,
    owner_name: Optional[str],
    people: Mapping[str, str],
    fallback_started_at: datetime,
) -> Conversation:
    """The completed conversation for one parsed file.

    Raises ``TranscriptFileSkipped`` before building any segment when the file has
    more turns than one conversation document can hold; segments cost far more
    memory than cues.
    """
    if len(parsed.cues) > MAX_TRANSCRIPT_SEGMENTS:
        raise TranscriptFileSkipped(TRANSCRIPT_TOO_LONG)
    segments = segments_from_cues(parsed.cues, owner_name=owner_name, people=people)
    started_at = parsed.started_at or fallback_started_at
    finished_at = started_at + timedelta(seconds=max((segment.end for segment in segments), default=0.0))
    return Conversation(
        id=conversation_id_for_transcript(uid, data),
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        source=source,
        language=language_code,
        structured=Structured(
            title=parsed.title,
            overview=_overview(segments),
            emoji='💬',
            action_items=[],
            events=[],
        ),
        transcript_segments=segments,
        status=ConversationStatus.completed,
        discarded=False,
        imported=True,
    )


# --------------------------------------------------------------------------- upload


@dataclass(frozen=True)
class _Entry:
    name: str
    read: Callable[[], bytes]
    archived_at: Optional[datetime]


def _read_limited(open_member: Callable[[], object]) -> bytes:
    with open_member() as handle:  # type: ignore[attr-defined]
        data = handle.read(MAX_TRANSCRIPT_FILE_BYTES + 1)
    if len(data) > MAX_TRANSCRIPT_FILE_BYTES:
        raise TranscriptFileSkipped(FILE_TOO_LARGE)
    return data


def _read_member(archive: ZipFile, info: ZipInfo) -> bytes:
    if not 0 <= info.header_offset < archive.start_dir:
        # A local header lies before the central directory; an offset outside that
        # (a misplaced directory, a hostile zip64 extra) cannot be read, or even seeked to.
        raise TranscriptFileSkipped(FILE_DAMAGED)
    try:
        return _read_limited(lambda: archive.open(info))
    except (BadZipFile, zlib.error, EOFError, NotImplementedError, UnicodeDecodeError) as exc:
        # A bad CRC, corrupt deflate stream or truncated member; a feature zipfile does
        # not support (patched data, strong encryption); a local name that is not UTF-8.
        logger.warning('transcript import member unreadable error_class=%s', type(exc).__name__)
        raise TranscriptFileSkipped(FILE_DAMAGED) from exc


_END_OF_DIRECTORY = struct.Struct('<4s4H2LH')
_ZIP64_LOCATOR = struct.Struct('<4sLQL')
_ZIP64_END_OF_DIRECTORY = struct.Struct('<4sQ2H2L4Q')


_END_OF_DIRECTORY_SIGNATURE = b'PK\x05\x06'
_ZIP64_LOCATOR_SIGNATURE = b'PK\x06\x07'
_ZIP64_END_OF_DIRECTORY_SIGNATURE = b'PK\x06\x06'


def _end_of_directory_at(tail: bytes) -> Optional[int]:
    """Where in the file's tail ``zipfile`` takes the classic end record from, or None.

    The final 22 bytes when they hold a record with no comment; otherwise the last
    signature, which must have a whole record behind it.
    """
    record_size = _END_OF_DIRECTORY.size
    if len(tail) < record_size:
        return None
    if tail[-record_size:].startswith(_END_OF_DIRECTORY_SIGNATURE) and tail.endswith(b'\0\0'):
        return len(tail) - record_size
    index = tail.rfind(_END_OF_DIRECTORY_SIGNATURE)
    return index if 0 <= index <= len(tail) - record_size else None


def _declared_zip_directory(path: str) -> Optional[tuple[int, int]]:
    """The largest (entries, central-directory bytes) the end records zipfile reads could declare.

    CPython versions differ in which zip64 record they read: the one the locator
    points at, or the one just before the locator. Both are read, and each field
    takes the largest value of the classic record and every zip64 record found; the
    classic 0xFFFF / 0xFFFFFFFF markers only count when no zip64 record exists.
    """
    zip64_records: List[tuple[Any, ...]] = []
    with open(path, 'rb') as handle:
        size = handle.seek(0, os.SEEK_END)
        # zipfile's search window: the longest comment (64 KiB) plus the record itself.
        tail_start = max(0, size - _END_OF_DIRECTORY.size - (1 << 16))
        handle.seek(tail_start)
        tail = handle.read()
        index = _end_of_directory_at(tail)
        if index is None:
            return None
        classic = _END_OF_DIRECTORY.unpack_from(tail, index)
        locator_at = tail_start + index - _ZIP64_LOCATOR.size
        if locator_at >= 0:
            handle.seek(locator_at)
            locator = handle.read(_ZIP64_LOCATOR.size)
            if locator.startswith(_ZIP64_LOCATOR_SIGNATURE):
                pointed_at = int(_ZIP64_LOCATOR.unpack(locator)[2])
                last_record_at = locator_at - _ZIP64_END_OF_DIRECTORY.size
                for record_at in {pointed_at, last_record_at}:
                    # zipfile never reads a record past the one just before the locator:
                    # a pointer beyond it is refused as corrupt (or ignored by older versions).
                    if not 0 <= record_at <= last_record_at:
                        continue
                    handle.seek(record_at)
                    record = handle.read(_ZIP64_END_OF_DIRECTORY.size)
                    if len(record) == _ZIP64_END_OF_DIRECTORY.size and record.startswith(
                        _ZIP64_END_OF_DIRECTORY_SIGNATURE
                    ):
                        zip64_records.append(_ZIP64_END_OF_DIRECTORY.unpack(record))
    entries = [int(classic[3]), int(classic[4])]
    directory_bytes = [int(classic[5])]
    if zip64_records:
        entries = [count for count in entries if count != 0xFFFF]
        directory_bytes = [count for count in directory_bytes if count != 0xFFFFFFFF]
        for record in zip64_records:
            entries += [int(record[6]), int(record[7])]
            directory_bytes.append(int(record[8]))
    return max(entries), max(directory_bytes)


def _is_transcript_member(info: ZipInfo) -> bool:
    path = PurePosixPath(info.filename)
    return (
        not info.is_dir()
        and '__MACOSX' not in path.parts
        and not path.name.startswith('.')
        and path.suffix.lower() in TRANSCRIPT_EXTENSIONS
    )


@dataclass(frozen=True)
class _Upload:
    entries: List[_Entry]
    archive: Optional[ZipFile] = None


def _looks_like_zip(path: str) -> bool:
    """is_zipfile, which older 3.11 releases let raise on a multi-disk zip64 locator."""
    try:
        return is_zipfile(path)
    except BadZipFile:
        return False


def _open_upload(upload_path: str, original_filename: str, tz: Optional[str]) -> _Upload:
    """The upload's transcript files, after every archive-wide limit is checked.

    One bounded blocking step: it reads the end records and a capped central
    directory, never a member's data.
    """
    if PurePosixPath(original_filename).suffix.lower() == '.zip' or _looks_like_zip(upload_path):
        declared = _declared_zip_directory(upload_path)
        # Fail closed: zipfile cannot open a file whose end record this cannot find either.
        if declared is None:
            raise TranscriptImportError('The upload is not a valid ZIP archive.')
        if declared[0] > MAX_ZIP_DIRECTORY_ENTRIES or declared[1] > MAX_ZIP_DIRECTORY_BYTES:
            raise TranscriptImportError(
                'This ZIP lists too many files to import. Split it into smaller ZIPs and try again.'
            )
        try:
            archive = ZipFile(upload_path)
        # zipfile also raises these for archives it cannot read: a UTF-8 name flag on
        # bytes that are not UTF-8, or a newer format version than it supports.
        except (BadZipFile, UnicodeDecodeError, NotImplementedError) as exc:
            raise TranscriptImportError('The upload is not a valid ZIP archive.') from exc
        try:
            return _Upload(entries=_archive_entries(archive, tz), archive=archive)
        except BaseException:
            archive.close()
            raise
    if PurePosixPath(original_filename).suffix.lower() not in TRANSCRIPT_EXTENSIONS:
        raise TranscriptImportError('Upload a .zip, .srt, .vtt or .txt file.')
    return _Upload(
        entries=[
            _Entry(
                name=original_filename,
                read=lambda: _read_limited(lambda: open(upload_path, 'rb')),
                archived_at=None,
            )
        ]
    )


def _archive_entries(archive: ZipFile, tz: Optional[str]) -> List[_Entry]:
    members = [info for info in archive.infolist() if _is_transcript_member(info)]
    if len(members) > MAX_TRANSCRIPT_FILES:
        raise TranscriptImportError(
            f'An import can contain at most {MAX_TRANSCRIPT_FILES} transcript files; '
            f'this archive has {len(members)}.'
        )
    if sum(info.file_size for info in members) > MAX_ARCHIVE_TRANSCRIPT_BYTES:
        raise TranscriptImportError('The transcripts in this archive are too large to import at once.')
    if any(info.flag_bits & 0x1 for info in members):
        raise TranscriptImportError("Password-protected ZIP files aren't supported.")
    if any(info.compress_type not in READABLE_ZIP_COMPRESSION for info in members):
        raise TranscriptImportError(
            'This archive uses an unsupported compression method. '
            'Re-create the ZIP with standard compression and try again.'
        )
    zone = _zone(tz)
    entries: List[_Entry] = []
    for info in members:
        try:
            # A future date (a wrong device clock) would pin the conversation atop the history.
            archived_at = min(
                datetime(*info.date_time, tzinfo=zone).astimezone(timezone.utc), datetime.now(timezone.utc)
            )
        except ValueError:
            archived_at = None
        # Years before MIN_FILENAME_YEAR (local, as for file-name dates) are not recording
        # times: they include the ZIP zero date, 1980-01-01, that ZipInfo writes by default.
        if info.date_time[0] < MIN_FILENAME_YEAR:
            archived_at = None
        entries.append(
            _Entry(
                name=info.filename,
                read=lambda info=info: _read_member(archive, info),
                archived_at=archived_at,
            )
        )
    return entries


def _release_upload(job_id: str, upload_path: str, upload: Optional[_Upload]) -> None:
    """Close the archive and delete the staged upload; the worker's last step, whatever happened."""
    try:
        if upload is not None and upload.archive is not None:
            upload.archive.close()
    finally:
        try:
            if os.path.exists(upload_path):
                os.remove(upload_path)
        except OSError as exc:
            logger.error('transcript import upload cleanup failed job_id=%s error_class=%s', job_id, type(exc).__name__)


# --------------------------------------------------------------------------- job


def create_transcript_import_job(uid: str) -> ImportJob:
    job = ImportJob(
        id=str(uuid.uuid4()),
        uid=uid,
        status=ImportJobStatus.pending,
        source_type=ImportSourceType.transcript_files,
    )
    import_jobs_db.create_import_job(job.model_dump())
    return job


def _job_cancelled(job_id: str) -> bool:
    """Whether the user cancelled (or deleted) the job; a cancel is final.

    Read before each file. Every status write the worker makes is also conditional
    on it (``update_import_job_unless_cancelled``), so a cancel that lands between
    this read and a write is never overwritten.
    """
    current = import_jobs_db.get_import_job(job_id)
    # A deleted job has no one waiting on it: stop quietly, as for a cancel.
    return current is None or current.get('status') == ImportJobStatus.cancelled.value


def _record_cancelled_counts(job_id: str, processed: int, created: int, skipped: int) -> None:
    """The counts a cancelled import reached, so its history matches the conversations it left.

    Progress is otherwise written only every 10 files. This writes the counters alone
    (``update_import_job_progress``), never ``status``, so the cancel stands; a deleted
    job is not recreated. Best effort: the import has already stopped.
    """
    if not processed:
        return
    progress = {'processed_files': processed, 'conversations_created': created, 'conversations_skipped': skipped}
    try:
        import_jobs_db.update_import_job_progress(job_id, progress)
    except Exception as exc:
        logger.warning(
            'transcript import cancel counts not recorded job_id=%s error_class=%s', job_id, type(exc).__name__
        )


def _notify(uid: str, job_id: str, title: str, body: str, data: Dict[str, str]) -> None:
    """Push is best effort; delivery cannot change a committed import status."""
    try:
        outcome = dispatch_notification(
            NotificationIntent(
                user_id=uid,
                title=title,
                body=body,
                source='transcript_import',
                kind=NotificationKind.IMPORT_JOB,
                data=data,
            )
        )
    except Exception as exc:
        logger.error('transcript import notification failed job_id=%s error_class=%s', job_id, type(exc).__name__)
        return
    if outcome.status != NotificationDispatchStatus.DISPATCHED or outcome.delivered == 0:
        logger.warning('transcript import notification not delivered job_id=%s status=%s', job_id, outcome.status.value)


def _fail(uid: str, job_id: str, message: str) -> None:
    failed = {
        'status': ImportJobStatus.failed.value,
        'error': message,
        'completed_at': datetime.now(timezone.utc).isoformat(),
    }
    if not import_jobs_db.update_import_job_unless_cancelled(job_id, failed):
        logger.info('transcript import job %s was cancelled; not recording its failure', job_id)
        return
    _notify(uid, job_id, 'Transcript Import Failed', message, {'type': 'import_failed', 'job_id': job_id})


class _Settlement:
    """Which final status write an import makes: its own outcome, or a shutdown's interruption.

    The final write is queued on the db pool, and a shutdown cancel can cancel it there
    before it starts, when nothing else would ever record the job's end. So each side
    claims the settlement inside its pool thread, as its write begins, and only the first
    claim writes: a final write that began is never overwritten by "interrupted", and one
    cancelled while still queued leaves the claim to the interruption. A write that raises
    settled nothing, so it gives the claim back for the failure that follows it.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._claimed = False

    def run(self, write: Callable[..., Any], *args: Any) -> Any:
        """``write(*args)`` when this is the first claim, else nothing (None)."""
        with self._lock:
            if self._claimed:
                return None
            self._claimed = True
        try:
            return write(*args)
        except BaseException:
            with self._lock:
                self._claimed = False
            raise


async def _settle_failure(settlement: _Settlement, uid: str, job_id: str, message: str) -> None:
    """Record the import's failure, even when a shutdown cancels the task while that write is queued.

    The cancel can remove the queued write from the db pool before it begins; it is then
    queued again, once, before the cancel goes on. A write that already began owns the
    settlement, so the second attempt writes nothing.
    """
    try:
        await run_blocking(db_executor, settlement.run, _fail, uid, job_id, message)
    except asyncio.CancelledError:
        await run_blocking(db_executor, settlement.run, _fail, uid, job_id, message)
        raise


def _compressed_transcript_bytes(uid: str, segments: List[Any]) -> int:
    """Size of the transcript blob the conversation write path stores, before any encryption."""
    encoded = conversations_db.encode_conversation_for_write(uid, {'transcript_segments': segments})
    return len(encoded['transcript_segments'])


def _import_file(
    job_id: str,
    uid: str,
    entry: _Entry,
    *,
    tz: Optional[str],
    source: ConversationSource,
    language_code: str,
    owner_name: Optional[str],
    people: Mapping[str, str],
) -> bool:
    """Store one transcript file as a conversation; False when it was already imported.

    Raises ``TranscriptFileSkipped`` with the user-facing reason when the file cannot be imported.
    """
    data = entry.read()
    parsed = parse_transcript_file(entry.name, data, tz=tz)
    if parsed is None:
        raise TranscriptFileSkipped(NOT_A_TRANSCRIPT)
    conversation = build_imported_conversation(
        uid,
        parsed,
        data,
        source=source,
        language_code=language_code,
        owner_name=owner_name,
        people=people,
        fallback_started_at=entry.archived_at or datetime.now(timezone.utc),
    )
    payload = omit_null_processing_state(conversation.model_dump())
    if _compressed_transcript_bytes(uid, payload['transcript_segments']) > MAX_COMPRESSED_TRANSCRIPT_BYTES:
        raise TranscriptFileSkipped(TRANSCRIPT_TOO_LONG)
    reservation = import_quotas_db.reserve_import_quota(uid, 'byte', len(data))
    if reservation is None:
        raise TranscriptFileSkipped(MONTHLY_LIMIT_REACHED)
    created = False
    try:
        created = lifecycle_service.persist_imported_conversation(uid, payload)
        return created
    except Exception as exc:
        logger.warning('transcript import save failed job_id=%s error_class=%s', job_id, type(exc).__name__)
        raise TranscriptFileSkipped(NOT_SAVED) from exc
    finally:
        if not created:
            # A release error must not replace a duplicate skip or a save failure:
            # the conversation was not counted, and masking that turns the job failed.
            try:
                import_quotas_db.release_import_quota(uid, 'byte', reservation)
            except Exception as release_exc:
                logger.warning(
                    'transcript import byte quota release failed job_id=%s error_class=%s',
                    job_id,
                    type(release_exc).__name__,
                )


async def process_transcript_import(
    job_id: str,
    uid: str,
    upload_path: str,
    *,
    original_filename: str,
    language_code: str = 'en',
    tz: Optional[str] = 'UTC',
    origin: str = 'other',
) -> None:
    """Background coordinator: turn every transcript in the upload into a conversation.

    Runs as an async task. Each blocking step (a job read or write, opening the
    archive, importing one file) borrows a pool thread only for that step, so no
    slot is held for the whole import (backend/AGENTS.md, lane 2).
    """
    upload: Optional[_Upload] = None
    # The final status write and a shutdown's "interrupted" failure each claim this as
    # they begin in a pool thread; only the first writes (_Settlement).
    settlement = _Settlement()
    try:
        started = {'status': ImportJobStatus.processing.value, 'started_at': datetime.now(timezone.utc).isoformat()}
        if not await run_blocking(db_executor, import_jobs_db.update_import_job_unless_cancelled, job_id, started):
            logger.info('transcript import job %s was cancelled before it started', job_id)
            return
        source = TRANSCRIPT_ORIGINS.get(origin, ConversationSource.unknown)
        owner_name = await run_blocking(db_executor, get_user_full_name, uid)
        people = await run_blocking(db_executor, load_people_names, uid)
        created = skipped = processed = 0
        errors: List[str] = []
        upload = await run_blocking(storage_executor, _open_upload, upload_path, original_filename, tz)
        total = len(upload.entries)
        if not await run_blocking(
            db_executor, import_jobs_db.update_import_job_unless_cancelled, job_id, {'total_files': total}
        ):
            logger.info('transcript import job %s was cancelled before its first file', job_id)
            return
        if total == 0:
            await run_blocking(
                db_executor,
                settlement.run,
                _fail,
                uid,
                job_id,
                'No transcript files (.srt, .vtt or .txt) were found in the upload.',
            )
            return
        monthly_limit_reached = False
        for entry in upload.entries:
            if await run_blocking(db_executor, _job_cancelled, job_id):
                await run_blocking(db_executor, _record_cancelled_counts, job_id, processed, created, skipped)
                logger.info('transcript import job %s cancelled after %s of %s files', job_id, processed, total)
                return
            try:
                if monthly_limit_reached:
                    raise TranscriptFileSkipped(MONTHLY_LIMIT_REACHED)
                if await run_blocking(
                    storage_executor,
                    _import_file,
                    job_id,
                    uid,
                    entry,
                    tz=tz,
                    source=source,
                    language_code=language_code,
                    owner_name=owner_name,
                    people=people,
                ):
                    created += 1
                else:
                    skipped += 1
            except TranscriptFileSkipped as skip:
                monthly_limit_reached = monthly_limit_reached or skip.reason == MONTHLY_LIMIT_REACHED
                errors.append(skip.reason)
            except Exception as exc:
                logger.warning('transcript import file failed job_id=%s error_class=%s', job_id, type(exc).__name__)
                errors.append(UNEXPECTED_ERROR)
            processed += 1
            if processed % 10 == 0 or processed == total:
                progress = {
                    'processed_files': processed,
                    'conversations_created': created,
                    'conversations_skipped': skipped,
                }
                if not await run_blocking(
                    db_executor, import_jobs_db.update_import_job_unless_cancelled, job_id, progress
                ):
                    await run_blocking(db_executor, _record_cancelled_counts, job_id, processed, created, skipped)
                    logger.info('transcript import job %s cancelled after %s of %s files', job_id, processed, total)
                    return
        if errors and created == 0 and skipped == 0 and not monthly_limit_reached:
            await run_blocking(
                db_executor,
                settlement.run,
                _fail,
                uid,
                job_id,
                f'None of the {total} file(s) could be imported ({errors[0]}).',
            )
            return
        completed = {
            'status': ImportJobStatus.completed.value,
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'error': (
                f'{len(errors)} file(s) could not be imported'
                + (f' ({MONTHLY_LIMIT_REACHED})' if monthly_limit_reached else '')
                if errors
                else None
            ),
            'conversations_created': created,
            'conversations_skipped': skipped,
        }
        if not await run_blocking(
            db_executor, settlement.run, import_jobs_db.update_import_job_unless_cancelled, job_id, completed
        ):
            logger.info('transcript import job %s was cancelled; not recording its completion', job_id)
            return
        body = f'Imported {created} conversation(s) from your transcripts.'
        if skipped:
            body += f' {skipped} were already imported.'
        if errors:
            body += f' {len(errors)} file(s) could not be imported.'
        await run_blocking(
            db_executor,
            _notify,
            uid,
            job_id,
            'Transcript Import Complete',
            body,
            {
                'type': 'import_complete',
                'job_id': job_id,
                'conversations_created': str(created),
                'conversations_skipped': str(skipped),
            },
        )
    except asyncio.CancelledError:
        # Shutdown cancels tracked background tasks (drain_background_tasks): record the
        # interruption rather than leave the job processing with no worker behind it. A
        # final write that already began owns the settlement, so this then writes nothing;
        # one the cancel removed from the pool's queue never claimed it, so this does.
        await run_blocking(db_executor, settlement.run, _fail, uid, job_id, INTERRUPTED_ERROR)
        raise
    # A cancel while these failures are written is not caught by the CancelledError
    # handler above (it is raised inside a sibling clause); _settle_failure covers it.
    except TranscriptImportError as exc:
        await _settle_failure(settlement, uid, job_id, str(exc))
    except Exception as exc:
        logger.error('transcript import job failed job_id=%s error_class=%s', job_id, type(exc).__name__)
        await _settle_failure(settlement, uid, job_id, UNEXPECTED_IMPORT_ERROR)
    finally:
        await run_blocking(storage_executor, _release_upload, job_id, upload_path, upload)
