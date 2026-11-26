"""Read-only export of one consenting owner's speaker evidence into a private speaker corpus.

What it reads (and nothing else): the owner's voiceprint (``users/{uid}.speaker_embedding``), the owner's
people (id, name and the voiceprint production would use, through ``usable_person_voiceprint``), and for
conversations in the window: the stored transcript segments with their speaker fields, the manual speaker
assignments, and the private-cloud-sync audio placed on the conversation's own clock.

    cd backend
    python -m testing.pipeline_lab.speakers.owner_export --guard <path to guard.py> \\
        --uid-file <0600 file> --secret-file <0600 file> --name <corpus name> --days 14 --limit 60

Output (``<lab root>/speakers/corpus/<name>/``, owner-only, refused inside a Git work tree):

- ``gallery.json``: ``{identity: vector}``, ``user`` for the owner and the person id for each person;
- ``people.json``: ``[{id, name}]`` (names stay private; reports print counts only);
- ``conversations/<key>/conversation.json``: segments (text, clocks, speaker fields), manual assignments;
- ``conversations/<key>/audio.wav``: 16 kHz mono PCM16 from ``audio_base`` (the first audio file's start);
- ``manifest.json``: counts and the window. Never the uid.

Safety is the v3 exporter's: the guard module is injected by path (it pins the owner and is never in this
repository), every Firestore, Storage and Redis write is refused for the whole process, and the uid is
never printed or written. Conversation keys are a salted hash of the production id, so a corpus never
names a production document.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from testing.pipeline_lab.v3.prod_export import _inside_git_worktree, load_guard, read_only_fence
from testing.pipeline_lab.store import atomic_write_bytes, atomic_write_json, ensure_private_dir
from testing.pipeline_lab.speakers.corpus import corpus_dir

SAMPLE_RATE = 16000
PAGE = 100
SEGMENT_FIELDS = (
    'id',
    'text',
    'start',
    'end',
    'speaker',
    'speaker_id',
    'is_user',
    'person_id',
    'speaker_label_source',
    'speaker_id_scope',
    'stt_provider',
    'speaker_identity_status',
    'speaker_match_source',
)


def _time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _plain(value: Any) -> Any:
    def default(item: Any) -> Any:
        if isinstance(item, datetime):
            return item.isoformat()
        if hasattr(item, 'model_dump'):
            return item.model_dump(mode='json')
        if isinstance(item, bytes):
            return {'_bytes': len(item)}
        return str(item)

    return json.loads(json.dumps(value, default=default))


def corpus_key(salt: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{salt}:{conversation_id}'.encode()).hexdigest()[:16]


def audio_base(conversation: dict) -> Optional[datetime]:
    starts = [_time(f.get('started_at')) for f in conversation.get('audio_files') or []]
    starts = [t for t in starts if t]
    return min(starts) if starts else _time(conversation.get('started_at'))


def conversation_pcm(uid: str, conversation: dict) -> Optional[bytes]:
    """PCM16 mono 16 kHz from :func:`audio_base`, each audio file at its own start (gaps silent)."""
    from utils.other import storage

    files = [f for f in conversation.get('audio_files') or [] if f.get('chunk_timestamps') and f.get('started_at')]
    base = audio_base(conversation)
    if not files or base is None:
        return None
    listings: dict[str, list] = {}
    timeline = bytearray()
    for item in sorted(files, key=lambda f: str(f['started_at'])):
        # A v3 conversation's audio files keep their chunks under the source recording's id.
        holder = str(item.get('recording_id') or item.get('conversation_id') or conversation['id'])
        if holder not in listings:
            try:
                listings[holder] = storage.list_audio_chunks(uid, holder)
            except Exception:
                listings[holder] = []
        if not listings[holder]:
            continue
        stamps = sorted(float(t) for t in item['chunk_timestamps'])
        try:
            pcm = storage.download_audio_chunks_and_merge(
                uid, holder, stamps, fill_gaps=True, sample_rate=SAMPLE_RATE, listed_chunks=listings[holder]
            )
        except (FileNotFoundError, ValueError):
            continue
        if not pcm:
            continue
        at = int(max(0.0, _time(item['started_at']).timestamp() - base.timestamp()) * SAMPLE_RATE) * 2
        if len(timeline) < at:
            timeline.extend(bytes(at - len(timeline)))
        timeline[at : at + len(pcm)] = pcm
    return bytes(timeline) or None


def wav_bytes(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _recorded_seconds(meta: dict) -> float:
    return sum(float(f.get('duration') or 0) for f in meta.get('audio_files') or [])


def _conversations(
    uid: str, start: datetime, end: datetime, *, min_seconds: float, max_seconds: float, v3_recent: bool = False
) -> Iterable[dict]:
    """Longest recordings first. Metadata pages (no decode) pick candidates; each is then read in full.
    The Home reader is not used: it pages visible rows only and stops early on hidden runs."""
    from database import conversations as conversations_db

    candidates, offset = [], 0
    if v3_recent:
        # The newest conversations-v3 rows with batch units (the shape the final pass serves), newest first.
        page = conversations_db.get_conversations(uid, limit=200, start_date=start, end_date=end, metadata_only=True)
        for meta in page:
            row = conversations_db.get_conversation(uid, meta['id']) or {}
            if row.get('discarded') or row.get('deleted') or not row.get('v3_recording_ids'):
                continue
            if any(
                (s.get('speaker_id_scope') or '').startswith('final:batch:')
                for s in row.get('transcript_segments') or []
            ):
                yield row
        return
    while True:
        page = conversations_db.get_conversations(
            uid, limit=PAGE, offset=offset, start_date=start, end_date=end, metadata_only=True
        )
        candidates.extend(
            m
            for m in page
            if not m.get('discarded') and not m.get('deleted') and min_seconds <= _recorded_seconds(m) <= max_seconds
        )
        if len(page) < PAGE:
            break
        offset += PAGE
    for meta in sorted(candidates, key=_recorded_seconds, reverse=True):
        row = conversations_db.get_conversation(uid, meta['id'])
        if row:
            yield row


def gallery(uid: str) -> tuple[dict[str, list[float]], list[dict[str, str]]]:
    """The voiceprints production would match against, and the people's ids and names."""
    from database import users as users_db
    from utils.stt.owner_profile import validated_embedding
    from utils.stt.voiceprints import usable_person_voiceprint

    prints: dict[str, list[float]] = {}
    owner = validated_embedding(users_db.get_user_speaker_embedding(uid))
    if owner is not None:
        prints['user'] = owner.reshape(-1).tolist()
    people = []
    for person in users_db.get_people(uid) or []:
        if not person.get('id'):
            continue
        people.append({'id': str(person['id']), 'name': str(person.get('name') or '')})
        vector = validated_embedding(usable_person_voiceprint(person))
        if vector is not None:
            prints[str(person['id'])] = vector.reshape(-1).tolist()
    return prints, people


def conversation_record(row: dict, key: str) -> dict:
    segments = []
    for segment in row.get('transcript_segments') or []:
        segment = _plain(segment)
        segments.append({field: segment.get(field) for field in SEGMENT_FIELDS})
    base = audio_base(row)
    started = _time(row.get('started_at'))
    return {
        'key': key,
        'source': row.get('source'),
        'language': row.get('language'),
        'started_at': started.isoformat() if started else None,
        'audio_base': base.isoformat() if base else None,
        # Stored segment clocks are seconds from started_at; audio is from audio_base.
        'segment_clock_offset': (base - started).total_seconds() if base and started else None,
        'segments': segments,
        'manual_speaker_assignments': _plain(row.get('manual_speaker_assignments')),
        'excluded_speakers': _plain(row.get('excluded_speakers')),
        # Production's own account of its speaker work on this conversation (statuses and counts, no vectors).
        'speaker_resolution': _plain(row.get('speaker_resolution')),
        'owner_recognition_diagnostics': _plain(row.get('owner_recognition_diagnostics')),
        'private_cloud_sync_enabled': row.get('private_cloud_sync_enabled'),
        'uses_custom_stt': row.get('uses_custom_stt'),
    }


def export(
    uid: str,
    out: Path,
    *,
    days: int,
    limit: int,
    min_seconds: float,
    salt: str,
    min_segments: int = 1,
    max_seconds: float = 1800.0,
    refresh: bool = False,
    v3_recent: bool = False,
) -> dict:

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    prints, people = gallery(uid)
    atomic_write_json(out / 'gallery.json', prints)
    atomic_write_json(out / 'people.json', people)
    counts = {'listed': 0, 'no_audio': 0, 'short': 0, 'no_segments': 0, 'exported': 0, 'existing': 0}
    conversations = ensure_private_dir(out / 'conversations')
    for row in _conversations(uid, start, end, min_seconds=min_seconds, max_seconds=max_seconds, v3_recent=v3_recent):
        if counts['exported'] + counts['existing'] >= limit:
            break
        counts['listed'] += 1
        if len(row.get('transcript_segments') or []) < max(1, min_segments):
            counts['no_segments'] += 1
            continue
        key = corpus_key(salt, str(row['id']))
        target = conversations / key
        if (target / 'audio.wav').is_file():
            counts['existing'] += 1
            if refresh:
                atomic_write_json(target / 'conversation.json', conversation_record(row, key))
            continue
        pcm = conversation_pcm(uid, row)
        if not pcm:
            counts['no_audio'] += 1
            continue
        if len(pcm) / (2 * SAMPLE_RATE) < min_seconds:
            counts['short'] += 1
            continue
        ensure_private_dir(target)
        atomic_write_json(target / 'conversation.json', conversation_record(row, key))
        atomic_write_bytes(target / 'audio.wav', wav_bytes(pcm))
        counts['exported'] += 1
        print(f'exported {counts["exported"]}: {len(pcm) / 32000:.0f}s', file=sys.stderr)
    manifest = {
        'kind': 'owner',
        'window': {'start': start.isoformat(), 'end': end.isoformat(), 'days': days},
        'created_at': end.isoformat(),
        'counts': {**counts, 'gallery': len(prints), 'people': len(people)},
    }
    atomic_write_json(out / 'manifest.json', manifest)
    return manifest


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--guard', required=True, help='owner guard module (outside this repository)')
    parser.add_argument('--uid-file', required=True)
    parser.add_argument('--secret-file', required=True)
    parser.add_argument('--name', required=True, help='corpus name under <lab root>/speakers/corpus/')
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--limit', type=int, default=60)
    parser.add_argument('--min-seconds', type=float, default=60.0)
    parser.add_argument('--max-seconds', type=float, default=1800.0, help='skip recordings longer than this')
    parser.add_argument('--v3-recent', action='store_true', help='newest conversations-v3 rows with batch units')
    parser.add_argument('--refresh', action='store_true', help='rewrite conversation.json of exported conversations')
    parser.add_argument('--min-segments', type=int, default=1, help='skip conversations with fewer stored segments')
    args = parser.parse_args(argv)

    guard = load_guard(args.guard)
    uid = guard.owner_uid(args.uid_file)
    guard.load_secret(args.secret_file)
    os.umask(0o077)
    out = corpus_dir(args.name, create=True)
    if _inside_git_worktree(out):
        raise SystemExit('refusing: the corpus is inside a Git work tree')
    salt_file = out / 'salt'
    if not salt_file.exists():
        salt_file.write_text(os.urandom(16).hex())
        salt_file.chmod(0o600)
    with read_only_fence():
        manifest = export(
            uid,
            out,
            days=args.days,
            limit=args.limit,
            min_seconds=args.min_seconds,
            salt=salt_file.read_text(),
            min_segments=args.min_segments,
            max_seconds=args.max_seconds,
            refresh=args.refresh,
            v3_recent=args.v3_recent,
        )
    print(json.dumps(manifest['counts']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
