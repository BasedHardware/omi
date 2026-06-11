"""Build verbatim transcript chunks for vector indexing.

Conversation vectors (ns1) embed only the structured summary, so specific details
(exact dates, names, numbers, one-off mentions) are unfindable semantically. These
chunks slice the raw transcript into overlapping windows, each prefixed with the
conversation date, so semantic search can land on the verbatim evidence.
"""

from datetime import datetime
from typing import List, Optional

import database.conversations as conversations_db

# ~8 segments per chunk with 2-segment overlap keeps chunks small enough to embed
# precisely while not splitting answers across a hard boundary.
CHUNK_WINDOW = 8
CHUNK_STRIDE = 6


def _speaker_label(seg: dict, people_by_id: Optional[dict] = None) -> str:
    if seg.get('is_user'):
        return 'User'
    person_id = seg.get('person_id')
    if person_id and people_by_id and person_id in people_by_id:
        return people_by_id[person_id]
    speaker_id = seg.get('speaker_id')
    return f"Speaker {speaker_id}" if speaker_id is not None else 'Speaker'


def build_transcript_chunks(
    segments: List[dict],
    started_at: Optional[datetime],
    window: int = CHUNK_WINDOW,
    stride: int = CHUNK_STRIDE,
    people_by_id: Optional[dict] = None,
) -> List[dict]:
    """segments: transcript_segment dicts ({'text','is_user','speaker_id','person_id',...}).

    Returns [{'text', 'created_at' (unix ts), 'chunk_index'}] ready for
    vector_db.upsert_transcript_chunk_vectors.
    """
    lines = []
    for seg in segments or []:
        text = (seg.get('text') or '').strip()
        if not text:
            continue
        lines.append(f"{_speaker_label(seg, people_by_id)}: {text}")
    if not lines:
        return []

    date_header = ''
    created_ts = 0
    if started_at is not None:
        date_header = f"[Conversation on {started_at.strftime('%d %b %Y, %H:%M')}]\n"
        created_ts = int(started_at.timestamp())

    chunks = []
    idx = 0
    pos = 0
    while pos < len(lines):
        piece = lines[pos : pos + window]
        chunks.append(
            {
                'text': date_header + "\n".join(piece),
                'created_at': created_ts,
                'chunk_index': idx,
            }
        )
        if pos + window >= len(lines):
            break
        pos += stride
        idx += 1
    return chunks


def hydrate_chunk_texts(uid: str, rows: List[dict]) -> List[dict]:
    """Attach verbatim text to chunk references returned by vector search.

    Re-reads the conversations from Firestore (decrypted by the db layer) and rebuilds
    the deterministic chunking, so transcript text never has to live in Pinecone.
    Rows whose conversation/chunk no longer exists are dropped.
    """
    conv_ids = list({r['conversation_id'] for r in rows if r.get('conversation_id')})
    if not conv_ids:
        return []
    conversations = conversations_db.get_conversations_by_id(uid, conv_ids)
    chunks_by_conv = {}
    for c in conversations:
        segs = c.get('transcript_segments') or []
        started = c.get('started_at') or c.get('created_at')
        chunks_by_conv[c['id']] = {ch['chunk_index']: ch['text'] for ch in build_transcript_chunks(segs, started)}

    hydrated = []
    for r in rows:
        text = chunks_by_conv.get(r.get('conversation_id'), {}).get(r.get('chunk_index'))
        if text:
            hydrated.append({**r, 'text': text})
    return hydrated
