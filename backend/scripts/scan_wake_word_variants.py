#!/usr/bin/env python3
"""Discover wake-word spellings from real transcript segments without printing transcript text.

The scanner deliberately does not start from a guessed phonetic class. It inventories:
1. one- and two-token sequences immediately following the exact token ``hey``;
2. suffixes welded to a token beginning with ``hey``; and
3. observed words beginning with the known product spellings ``omi``/``omni``.

Input may be a local JSON/JSONL export, the macOS app's read-only SQLite cache,
or a read-only Firestore scan selected by ``--uid``/``--email``. Default output
contains normalized tokens, aggregate counts, and hashed document references
only; raw transcript text is never emitted.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any
import unicodedata
import zlib

import firebase_admin
from firebase_admin import auth as firebase_auth
from google.cloud import firestore

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


_WORD_RE = re.compile(r'[^\W_]+', re.UNICODE)


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize('NFKC', text).casefold()
    return [match.group(0) for match in _WORD_RE.finditer(normalized)]


def _hashed_ref(value: Any) -> str:
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:12]


def _segments(conversation: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = conversation.get('transcript_segments', conversation.get('segments', []))
    if not isinstance(raw, list):
        return []
    return [segment for segment in raw if isinstance(segment, Mapping)]


def _record_example(
    examples: dict[str, list[dict[str, Any]]],
    key: str,
    conversation_id: Any,
    segment_ids: Iterable[Any],
    *,
    max_examples: int,
) -> None:
    bucket = examples[key]
    if len(bucket) >= max_examples:
        return
    reference = {
        'conversation_ref': _hashed_ref(conversation_id),
        'segment_refs': list(dict.fromkeys(_hashed_ref(segment_id) for segment_id in segment_ids if segment_id)),
    }
    if reference not in bucket:
        bucket.append(reference)


def _ranked(
    counts: Counter[str],
    examples: dict[str, list[dict[str, Any]]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    return [
        {'tokens': key, 'count': count, 'example_refs': examples.get(key, [])}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def scan_conversations(
    conversations: Iterable[Mapping[str, Any]],
    *,
    max_examples: int = 3,
    result_limit: int = 100,
) -> dict[str, Any]:
    """Return privacy-preserving token inventories from conversation segments."""

    follower_counts: Counter[str] = Counter()
    follower_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cross_segment_followers: Counter[str] = Counter()
    welded_counts: Counter[str] = Counter()
    welded_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    product_prefix_counts: Counter[str] = Counter()
    product_prefix_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    conversation_count = 0
    segment_count = 0

    for conversation_index, conversation in enumerate(conversations):
        conversation_count += 1
        conversation_id = conversation.get('id', conversation.get('conversation_id', f'row-{conversation_index}'))
        flattened: list[tuple[str, int, Any]] = []
        for segment_index, segment in enumerate(_segments(conversation)):
            segment_count += 1
            text = segment.get('text')
            if not isinstance(text, str):
                continue
            segment_id = segment.get('id', f'{conversation_id}:{segment_index}')
            for token in _tokens(text):
                flattened.append((token, segment_index, segment_id))
                if token.startswith(('omi', 'omni')):
                    product_prefix_counts[token] += 1
                    _record_example(
                        product_prefix_examples,
                        token,
                        conversation_id,
                        [segment_id],
                        max_examples=max_examples,
                    )

        for token_index, (token, segment_index, segment_id) in enumerate(flattened):
            if token == 'hey':
                following = flattened[token_index + 1 : token_index + 3]
                for width in (1, 2):
                    candidate = following[:width]
                    if len(candidate) != width:
                        continue
                    key = ' '.join(value for value, _, _ in candidate)
                    follower_counts[key] += 1
                    if any(candidate_segment != segment_index for _, candidate_segment, _ in candidate):
                        cross_segment_followers[key] += 1
                    _record_example(
                        follower_examples,
                        key,
                        conversation_id,
                        [segment_id, *(candidate_segment_id for _, _, candidate_segment_id in candidate)],
                        max_examples=max_examples,
                    )
            elif token.startswith('hey') and len(token) > 3:
                suffix = token[3:]
                welded_counts[suffix] += 1
                _record_example(
                    welded_examples,
                    suffix,
                    conversation_id,
                    [segment_id],
                    max_examples=max_examples,
                )

    followers = _ranked(follower_counts, follower_examples, limit=result_limit)
    for item in followers:
        item['cross_segment_count'] = cross_segment_followers[item['tokens']]
    return {
        'schema_version': 1,
        'conversations_scanned': conversation_count,
        'segments_scanned': segment_count,
        'hey_followers': followers,
        'welded_hey_suffixes': _ranked(welded_counts, welded_examples, limit=result_limit),
        'omi_prefixed_tokens': _ranked(product_prefix_counts, product_prefix_examples, limit=result_limit),
    }


def _payload_conversations(payload: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(payload, list):
        if payload and all(isinstance(item, Mapping) and 'text' in item for item in payload):
            yield {'id': 'local-segments', 'transcript_segments': payload}
            return
        for item in payload:
            if isinstance(item, Mapping):
                yield item
        return
    if not isinstance(payload, Mapping):
        raise ValueError('input must contain a conversation object or list')
    for key in ('conversations', 'data', 'items'):
        nested = payload.get(key)
        if isinstance(nested, list):
            yield from _payload_conversations(nested)
            return
    yield payload


def load_local_conversations(path: Path) -> Iterator[Mapping[str, Any]]:
    """Load JSON, JSONL, or NDJSON without assuming one export envelope."""

    if path.suffix.casefold() in {'.jsonl', '.ndjson'}:
        with path.open(encoding='utf-8') as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield from _payload_conversations(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f'invalid JSON on line {line_number}') from error
        return
    with path.open(encoding='utf-8') as handle:
        yield from _payload_conversations(json.load(handle))


def load_sqlite_conversations(path: Path) -> Iterator[Mapping[str, Any]]:
    """Read transcript sessions from a macOS Omi cache without mutating it."""

    database_uri = f'{path.resolve().as_uri()}?mode=ro'
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only = ON')
        rows = connection.execute('''
            SELECT
                sessions.id AS session_id,
                COALESCE(sessions.backendId, sessions.clientConversationId, CAST(sessions.id AS TEXT))
                    AS conversation_id,
                segments.segmentId AS segment_id,
                segments.text AS text,
                segments.startTime AS start_time,
                segments.endTime AS end_time
            FROM transcription_sessions AS sessions
            JOIN transcription_segments AS segments ON segments.sessionId = sessions.id
            WHERE COALESCE(sessions.deleted, 0) = 0
            ORDER BY sessions.id, segments.segmentOrder, segments.id
            ''')
        current_session_id: int | None = None
        current_conversation_id: str | None = None
        current_segments: list[dict[str, Any]] = []
        for row in rows:
            if current_session_id is not None and row['session_id'] != current_session_id:
                yield {'id': current_conversation_id, 'transcript_segments': current_segments}
                current_segments = []
            current_session_id = row['session_id']
            current_conversation_id = row['conversation_id']
            current_segments.append(
                {
                    'id': row['segment_id'] or f"{row['session_id']}:{len(current_segments)}",
                    'text': row['text'],
                    'start': row['start_time'],
                    'end': row['end_time'],
                }
            )
        if current_session_id is not None:
            yield {'id': current_conversation_id, 'transcript_segments': current_segments}
    finally:
        connection.close()


def decode_firestore_segments(raw: Mapping[str, Any], uid: str) -> list[Mapping[str, Any]]:
    """Decode the selected transcript fields without importing the full database layer."""

    stored_segments = raw.get('transcript_segments')
    if isinstance(stored_segments, list):
        decoded_segments = stored_segments
    elif raw.get('transcript_segments_compressed') is True:
        if isinstance(stored_segments, bytes):
            compressed = stored_segments
        elif isinstance(stored_segments, str):
            raise RuntimeError(
                'enhanced transcript storage is not decoded by this read-only scanner; '
                'scan a decrypted local export with --input'
            )
        else:
            return []
        decoded_segments = json.loads(zlib.decompress(compressed).decode('utf-8'))
    elif isinstance(stored_segments, str):
        raise RuntimeError(
            'encrypted transcript storage is not decoded by this read-only scanner; '
            'scan a decrypted local export with --input'
        )
    else:
        return []
    if not isinstance(decoded_segments, list):
        return []
    return [segment for segment in decoded_segments if isinstance(segment, Mapping)]


def load_firestore_conversations(
    *,
    uid: str | None,
    email: str | None,
    project_id: str,
    limit: int | None,
) -> Iterator[Mapping[str, Any]]:
    """Stream only transcript storage fields from Firestore; never mutate state."""

    if not firebase_admin._apps:  # type: ignore[attr-defined]
        firebase_admin.initialize_app(options={'projectId': project_id})
    resolved_uid = uid
    if not resolved_uid:
        if not email:
            raise ValueError('Firestore mode requires --uid or --email')
        resolved_uid = firebase_auth.get_user_by_email(email).uid

    client = firestore.Client(project=project_id)
    query = (
        client.collection('users')
        .document(resolved_uid)
        .collection('conversations')
        .select(
            [
                'data_protection_level',
                'transcript_segments',
                'transcript_segments_compressed',
            ]
        )
    )
    if limit is not None:
        query = query.limit(limit)
    for snapshot in query.stream():
        raw = snapshot.to_dict() or {}
        yield {'id': snapshot.id, 'transcript_segments': decode_firestore_segments(raw, resolved_uid)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--input', type=Path, help='Local JSON/JSONL conversation export.')
    source.add_argument('--sqlite', type=Path, help='Read-only macOS Omi cache database (omi.db).')
    source.add_argument('--uid', help='Read this account from Firestore using ADC.')
    source.add_argument('--email', help='Resolve this Firebase Auth email, then read Firestore using ADC.')
    parser.add_argument('--project-id', help='Required with --uid/--email; for example based-hardware.')
    parser.add_argument('--limit', type=int, help='Maximum Firestore conversations to scan.')
    parser.add_argument('--max-examples', type=int, default=3, help='Hashed references retained per token form.')
    parser.add_argument('--result-limit', type=int, default=100, help='Maximum rows emitted per inventory.')
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.input:
        conversations = load_local_conversations(args.input)
    elif args.sqlite:
        conversations = load_sqlite_conversations(args.sqlite)
    else:
        if not args.project_id:
            raise SystemExit('error: --project-id is required with --uid/--email')
        conversations = load_firestore_conversations(
            uid=args.uid,
            email=args.email,
            project_id=args.project_id,
            limit=args.limit,
        )
    result = scan_conversations(
        conversations,
        max_examples=max(0, args.max_examples),
        result_limit=max(1, args.result_limit),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
