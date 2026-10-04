"""Transcript-file import: SRT, WebVTT and plain-text transcripts from other tools.

People switching from other recorders and meeting tools can bring their history:
export transcripts as ``.srt``, ``.vtt`` or ``.txt`` (alone or zipped) and each file
becomes a completed Omi conversation. Like the Limitless importer this is a light
import — parse and store the transcript, no AI processing — so it is fast, cheap,
and idempotent (a file's content decides its conversation ID).
"""

from __future__ import annotations

import hashlib
import html
import logging
import os
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Callable, Dict, Iterator, List, Mapping, Optional, Sequence
from zipfile import BadZipFile, ZipFile, ZipInfo, is_zipfile
from zoneinfo import ZoneInfo

import database.import_jobs as import_jobs_db
import database.users as users_db
from database.auth import get_user_name
from database.document_ids import document_id_from_seed
from models.conversation import Conversation
from models.conversation_enums import CategoryEnum, ConversationSource, ConversationStatus
from models.import_job import ImportJob, ImportJobStatus, ImportSourceType
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
from models.transcript_segment import TranscriptSegment
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.projection_payload import omit_null_processing_state
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
MAX_TRANSCRIPT_FILE_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_TRANSCRIPT_BYTES = 200 * 1024 * 1024
# Untimed text gets estimated times so turns keep their order and the
# conversation a plausible duration (about 150 spoken words per minute).
ESTIMATED_WORDS_PER_SECOND = 2.5
DEFAULT_TITLE = 'Imported transcript'
# Never change: baked into the ID of every conversation already imported.
TRANSCRIPT_IMPORT_ID_NAMESPACE = 'transcript-file'
# A file counts as speaker-labeled when most cues open with "Name: ".
LABELED_FILE_MIN_SHARE = 0.6


class TranscriptImportError(Exception):
    """An upload the importer refuses as a whole, with a user-facing reason."""


@dataclass(frozen=True)
class TranscriptCue:
    text: str
    speaker: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None


@dataclass(frozen=True)
class ParsedTranscript:
    title: str
    started_at: Optional[datetime]
    cues: tuple[TranscriptCue, ...]


# --------------------------------------------------------------------------- parsing

_TIMESTAMP = r'(?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?'
_TIMESTAMP_RE = re.compile(r'(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?')
_CUE_TIMING_RE = re.compile(rf'^\s*({_TIMESTAMP})\s*-->\s*({_TIMESTAMP})')
_LABEL_RE = re.compile(r"^(?P<label>[^\W\d_][^:\n]{0,39}?)\s*:\s+(?P<rest>\S.*)$")
_SPEAKER_N_RE = re.compile(r'^(?:speaker|participant|person|spk)\s*\d+$', re.IGNORECASE)
_VOICE_RE = re.compile(r'<v(?:\.[\w.-]+)?\s+([^>]+)>')
_TAG_RE = re.compile(r'<[^>]*>')
_HEADER_NAME_FIRST_RE = re.compile(rf'^(?P<name>\S.*?)\s{{2,}}\(?(?P<ts>{_TIMESTAMP})\)?\s*$')
_HEADER_TIME_FIRST_RE = re.compile(rf"^\[?(?P<ts>{_TIMESTAMP})\]?\s+(?P<name>[^\W\d_][\w .'-]{{0,39}})$")
_INLINE_TIMED_RE = re.compile(rf'^\[?(?P<ts>{_TIMESTAMP})\]?\s*(?:-\s*)?(?P<rest>\S.*)$')


def _seconds(value: str) -> Optional[float]:
    match = _TIMESTAMP_RE.fullmatch(value.strip())
    if not match:
        return None
    hours, minutes, seconds, fraction = match.groups()
    if int(seconds) >= 60 or (hours is not None and int(minutes) >= 60):
        return None
    total = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
    if fraction:
        total += int(fraction.ljust(3, '0')) / 1000
    return float(total)


def _normalize(text: str) -> str:
    return text.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')


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
    otherwise unlabeled file stays text.
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
        if label and (mostly_labeled or _SPEAKER_N_RE.match(label[0]) or counts[label[0].casefold()] > 1):
            result.append(TranscriptCue(text=label[1], speaker=label[0], start=cue.start, end=cue.end))
        else:
            result.append(cue)
    return result


def parse_srt(text: str) -> List[TranscriptCue]:
    cues: List[TranscriptCue] = []
    for lines in _blocks(text):
        timing_index = next((index for index, line in enumerate(lines[:2]) if '-->' in line), None)
        if timing_index is None:
            continue
        timing = _CUE_TIMING_RE.match(lines[timing_index])
        body = ' '.join(lines[timing_index + 1 :]).strip()
        if not timing or not body:
            continue
        cues.append(TranscriptCue(text=body, start=_seconds(timing.group(1)), end=_seconds(timing.group(2))))
    return _assign_speakers(cues)


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
        raw = ' '.join(lines[timing_index + 1 :])
        voice = _VOICE_RE.search(raw)
        body = re.sub(r'\s+', ' ', html.unescape(_TAG_RE.sub('', raw))).strip()
        if not timing or not body:
            continue
        cues.append(
            TranscriptCue(
                text=body,
                speaker=voice.group(1).strip() if voice else None,
                start=_seconds(timing.group(1)),
                end=_seconds(timing.group(2)),
            )
        )
    return _assign_speakers(cues)


def _parse_header_turns(lines: List[str]) -> List[TranscriptCue]:
    cues: List[TranscriptCue] = []
    speaker: Optional[str] = None
    start: Optional[float] = None
    body: List[str] = []

    def close() -> None:
        if body:
            cues.append(TranscriptCue(text=' '.join(body), speaker=speaker, start=start))

    for line in lines:
        header = _HEADER_NAME_FIRST_RE.match(line) or _HEADER_TIME_FIRST_RE.match(line)
        if header and _is_name_label(header.group('name')):
            close()
            speaker, start, body = header.group('name').strip(), _seconds(header.group('ts')), []
        elif line:
            body.append(line)
    close()
    return cues


def parse_text_transcript(text: str) -> List[TranscriptCue]:
    lines = [line.strip() for line in _normalize(text).split('\n')]
    content = [line for line in lines if line]
    if not content:
        return []
    headers = sum(
        1
        for line in content
        if (match := (_HEADER_NAME_FIRST_RE.match(line) or _HEADER_TIME_FIRST_RE.match(line)))
        and _is_name_label(match.group('name'))
    )
    if headers:
        return _parse_header_turns(lines)
    timed = [_INLINE_TIMED_RE.match(line) for line in content]
    if sum(1 for match in timed if match) * 2 >= len(content):
        cues: List[TranscriptCue] = []
        for line, match in zip(content, timed):
            if match:
                cues.append(TranscriptCue(text=match.group('rest').strip(), start=_seconds(match.group('ts'))))
            elif cues:
                previous = cues[-1]
                cues[-1] = TranscriptCue(text=f'{previous.text} {line}', start=previous.start)
        return _assign_speakers(cues)
    cues = []
    for block in _blocks(text):
        if len(block) > 1 and all(_LABEL_RE.match(line) for line in block):
            cues.extend(TranscriptCue(text=line) for line in block)
        else:
            cues.append(TranscriptCue(text=' '.join(block)))
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
    except ValueError:
        return None
    return local.astimezone(timezone.utc)


def title_from_filename(filename: str) -> str:
    stem = PurePosixPath(filename).stem
    match = _filename_datetime_match(stem)
    if match:
        stem = stem[: match.start()] + ' ' + stem[match.end() :]
    title = re.sub(r'\s+', ' ', re.sub(r'[_]+|(?<=\w)-(?=\w)', ' ', stem)).strip(' -_.')
    return title if title and not title.replace(' ', '').isdigit() else DEFAULT_TITLE


def parse_transcript_file(filename: str, data: bytes, *, tz: Optional[str] = 'UTC') -> Optional[ParsedTranscript]:
    """Parse one transcript file, or ``None`` when it is not a usable transcript."""
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in TRANSCRIPT_EXTENSIONS or b'\x00' in data:
        return None
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('cp1252', errors='replace')
    head = _normalize(text).lstrip()
    if head.startswith('WEBVTT'):
        cues = parse_vtt(text)
    elif extension == '.srt' or (extension == '.txt' and _CUE_TIMING_RE.search(head[:500] or '')):
        cues = parse_srt(text)
    elif extension == '.vtt':
        cues = parse_vtt(text)
    else:
        cues = parse_text_transcript(text)
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


def segments_from_cues(
    cues: Sequence[TranscriptCue],
    *,
    owner_name: Optional[str],
    people: Mapping[str, str],
) -> List[TranscriptSegment]:
    """Number speakers by first appearance and bind the owner and known people by name.

    ``people`` maps casefolded person names to person IDs. Missing end times close
    at the next turn; untimed cues get ordered, estimated times.
    """
    owner = owner_name.casefold().strip() if owner_name else None
    speaker_ids: Dict[Optional[str], int] = {}
    segments: List[TranscriptSegment] = []
    cursor = 0.0
    for index, cue in enumerate(cues):
        key = cue.speaker.casefold() if cue.speaker else None
        speaker_id = speaker_ids.setdefault(key, len(speaker_ids))
        start = cue.start if cue.start is not None else cursor
        start = max(start, segments[-1].start if segments else 0.0)
        end = cue.end
        if end is None or end <= start:
            following = next((c.start for c in cues[index + 1 :] if c.start is not None), None)
            end = following if following is not None and following > start else start + _estimated_seconds(cue.text)
        is_user = bool(owner and key == owner)
        segments.append(
            TranscriptSegment(
                text=cue.text,
                speaker=f'SPEAKER_{speaker_id:02d}',
                speaker_id=speaker_id,
                is_user=is_user,
                person_id=None if is_user or key is None else people.get(key),
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
    """Casefolded person name -> person ID, so named speakers bind to known people."""
    try:
        people = users_db.get_people(uid)
    except Exception as exc:
        logger.warning('transcript import people lookup failed uid=%s error_class=%s', uid, type(exc).__name__)
        return {}
    names: Dict[str, str] = {}
    for person in people:
        name, person_id = (person.get('name') or '').strip(), person.get('id')
        if name and person_id:
            names.setdefault(name.casefold(), person_id)
    return names


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
            category=CategoryEnum.other,
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


class _TooLarge(Exception):
    pass


def _read_limited(open_member: Callable[[], object]) -> bytes:
    with open_member() as handle:  # type: ignore[attr-defined]
        data = handle.read(MAX_TRANSCRIPT_FILE_BYTES + 1)
    if len(data) > MAX_TRANSCRIPT_FILE_BYTES:
        raise _TooLarge()
    return data


def _is_transcript_member(info: ZipInfo) -> bool:
    path = PurePosixPath(info.filename)
    return (
        not info.is_dir()
        and '__MACOSX' not in path.parts
        and not path.name.startswith('.')
        and path.suffix.lower() in TRANSCRIPT_EXTENSIONS
    )


@contextmanager
def _upload_entries(upload_path: str, original_filename: str, tz: Optional[str]) -> Iterator[List[_Entry]]:
    if PurePosixPath(original_filename).suffix.lower() == '.zip' or is_zipfile(upload_path):
        try:
            archive = ZipFile(upload_path)
        except BadZipFile as exc:
            raise TranscriptImportError('The upload is not a valid ZIP archive.') from exc
        with archive:
            members = [info for info in archive.infolist() if _is_transcript_member(info)]
            if len(members) > MAX_TRANSCRIPT_FILES:
                raise TranscriptImportError(
                    f'An import can contain at most {MAX_TRANSCRIPT_FILES} transcript files; '
                    f'this archive has {len(members)}.'
                )
            if sum(info.file_size for info in members) > MAX_ARCHIVE_TRANSCRIPT_BYTES:
                raise TranscriptImportError('The transcripts in this archive are too large to import at once.')
            zone = _zone(tz)
            entries = []
            for info in members:
                try:
                    archived_at = datetime(*info.date_time, tzinfo=zone).astimezone(timezone.utc)
                except ValueError:
                    archived_at = None
                entries.append(
                    _Entry(
                        name=info.filename,
                        read=lambda info=info: _read_limited(lambda: archive.open(info)),
                        archived_at=archived_at,
                    )
                )
            yield entries
        return
    if PurePosixPath(original_filename).suffix.lower() not in TRANSCRIPT_EXTENSIONS:
        raise TranscriptImportError('Upload a .zip, .srt, .vtt or .txt file.')
    yield [
        _Entry(
            name=original_filename,
            read=lambda: _read_limited(lambda: open(upload_path, 'rb')),
            archived_at=None,
        )
    ]


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
    current = import_jobs_db.get_import_job(job_id)
    return bool(current and current.get('status') == ImportJobStatus.cancelled.value)


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
    import_jobs_db.update_import_job(
        job_id,
        {
            'status': ImportJobStatus.failed.value,
            'error': message,
            'completed_at': datetime.now(timezone.utc).isoformat(),
        },
    )
    _notify(uid, job_id, 'Transcript Import Failed', message, {'type': 'import_failed', 'job_id': job_id})


def process_transcript_import(
    job_id: str,
    uid: str,
    upload_path: str,
    *,
    original_filename: str,
    language_code: str = 'en',
    tz: Optional[str] = 'UTC',
    origin: str = 'other',
) -> None:
    """Background worker: turn every transcript in the upload into a conversation."""
    try:
        import_jobs_db.update_import_job(
            job_id,
            {'status': ImportJobStatus.processing.value, 'started_at': datetime.now(timezone.utc).isoformat()},
        )
        source = TRANSCRIPT_ORIGINS.get(origin, ConversationSource.unknown)
        owner_name = get_user_name(uid, use_default=False)
        people = load_people_names(uid)
        created = skipped = processed = 0
        errors: List[str] = []
        with _upload_entries(upload_path, original_filename, tz) as entries:
            total = len(entries)
            import_jobs_db.update_import_job(job_id, {'total_files': total})
            if total == 0:
                _fail(uid, job_id, 'No transcript files (.srt, .vtt or .txt) were found in the upload.')
                return
            for entry in entries:
                if processed and _job_cancelled(job_id):
                    logger.info('transcript import job %s cancelled after %s of %s files', job_id, processed, total)
                    return
                try:
                    data = entry.read()
                    parsed = parse_transcript_file(entry.name, data, tz=tz)
                    if parsed is None:
                        errors.append('not a readable transcript')
                    else:
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
                        if lifecycle_service.persist_imported_conversation(
                            uid, omit_null_processing_state(conversation.model_dump())
                        ):
                            created += 1
                        else:
                            skipped += 1
                except _TooLarge:
                    errors.append('file too large')
                except Exception as exc:
                    logger.warning('transcript import file failed job_id=%s error_class=%s', job_id, type(exc).__name__)
                    errors.append(type(exc).__name__)
                processed += 1
                if processed % 10 == 0 or processed == total:
                    import_jobs_db.update_import_job(
                        job_id,
                        {
                            'processed_files': processed,
                            'conversations_created': created,
                            'conversations_skipped': skipped,
                        },
                    )
        if _job_cancelled(job_id):
            return
        if errors and created == 0 and skipped == 0:
            _fail(uid, job_id, f'None of the {total} file(s) could be imported ({errors[0]}).')
            return
        import_jobs_db.update_import_job(
            job_id,
            {
                'status': ImportJobStatus.completed.value,
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'error': f'{len(errors)} file(s) could not be imported' if errors else None,
                'conversations_created': created,
                'conversations_skipped': skipped,
            },
        )
        body = f'Imported {created} conversation(s) from your transcripts.'
        if skipped:
            body += f' {skipped} were already imported.'
        if errors:
            body += f' {len(errors)} file(s) could not be imported.'
        _notify(
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
    except TranscriptImportError as exc:
        _fail(uid, job_id, str(exc))
    except Exception as exc:
        logger.error('transcript import job failed job_id=%s error_class=%s', job_id, type(exc).__name__)
        _fail(uid, job_id, 'There was an error importing your transcripts. Please try again.')
    finally:
        try:
            if os.path.exists(upload_path):
                os.remove(upload_path)
        except OSError as exc:
            logger.error('transcript import upload cleanup failed job_id=%s error_class=%s', job_id, type(exc).__name__)
