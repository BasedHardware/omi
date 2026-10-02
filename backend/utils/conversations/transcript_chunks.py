"""Build verbatim transcript chunks for vector indexing.

These chunks slice the raw transcript into overlapping windows prefixed with the
conversation date, so semantic search can land on verbatim evidence.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import database.conversations as conversations_db
from database.firestore_read_metrics import FirestoreReadSite

# ~8 segments per chunk with 2-segment overlap keeps chunks small enough to embed precisely.
CHUNK_WINDOW = 8
CHUNK_STRIDE = 6


def _speaker_label(seg: Dict[str, Any], people_by_id: Optional[Dict[str, str]] = None) -> str:
    if seg.get('is_user'):
        return 'User'
    if (pid := seg.get('person_id')) and people_by_id and pid in people_by_id:
        return people_by_id[pid]
    return f"Speaker {sid}" if (sid := seg.get('speaker_id')) is not None else 'Speaker'


def _coerce_started_at(raw: Any) -> Optional[datetime]:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    if isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def build_transcript_chunks(
    segments: List[Dict[str, Any]],
    started_at: Optional[Any],
    window: int = CHUNK_WINDOW,
    stride: int = CHUNK_STRIDE,
    people_by_id: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Return [{'text', 'created_at' (unix ts), 'chunk_index'}] for vector_db upsert."""
    lines: List[str] = []
    for seg in segments or []:
        text = (seg.get('text') or '').strip()
        if not text:
            continue
        lines.append(f"{_speaker_label(seg, people_by_id)}: {text}")
    if not lines:
        return []

    date_header = ''
    created_ts = 0
    dt = _coerce_started_at(started_at)
    if dt is not None:
        date_header = f"[Conversation on {dt.strftime('%d %b %Y, %H:%M')}]\n"
        created_ts = int(dt.timestamp())

    chunks: List[Dict[str, Any]] = []
    idx, pos = 0, 0
    while pos < len(lines):
        chunks.append(
            {
                'text': date_header + "\n".join(lines[pos : pos + window]),
                'created_at': created_ts,
                'chunk_index': idx,
            }
        )
        if pos + window >= len(lines):
            break
        pos += stride
        idx += 1
    return chunks


def hydrate_chunk_texts(uid: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach verbatim text to chunk references returned by vector search."""
    if not (conv_ids := list({r['conversation_id'] for r in rows if r.get('conversation_id')})):
        return []
    conversations = conversations_db.get_conversations_by_id(
        uid, conv_ids, read_site=FirestoreReadSite.TRANSCRIPT_CHUNK_HYDRATION
    )
    chunks_by_conv: Dict[str, Dict[int, str]] = {}
    meta_by_conv: Dict[str, Dict[str, Any]] = {}
    for c in conversations:
        segs: List[Dict[str, Any]] = c.get('transcript_segments') or []
        started = c.get('started_at') or c.get('created_at')
        chunks_by_conv[c['id']] = {ch['chunk_index']: ch['text'] for ch in build_transcript_chunks(segs, started)}
        structured = c.get('structured')
        title = structured.get('title') if isinstance(structured, dict) else None
        meta_by_conv[c['id']] = {'conversation_title': title, 'conversation_started_at': started}

    hydrated: List[Dict[str, Any]] = []
    for r in rows:
        conv_id, chunk_idx = r.get('conversation_id'), r.get('chunk_index')
        conv_chunks = chunks_by_conv.get(conv_id) if conv_id else None
        text = conv_chunks.get(chunk_idx) if (conv_chunks is not None and chunk_idx is not None) else None
        if text and conv_id:
            hydrated.append({**r, 'text': text, **meta_by_conv.get(conv_id, {})})
    return hydrated
