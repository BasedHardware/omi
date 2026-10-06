#!/usr/bin/env python3
"""Index one user's existing transcripts into the transcript-chunk namespace.

Chat and conversation search always query transcript-chunk vectors, but chunks
are written only when ``TRANSCRIPT_CHUNK_INDEXING_ENABLED`` was on while a
conversation finished processing. It is closed by default, so stored history has
no chunks and a detail spoken only in a transcript stays unfindable (#20629).

This writes the same chunks the processing path writes, built exactly as the
search readers rebuild them (``started_at`` or ``created_at``), so every indexed
chunk index hydrates back to the same verbatim text. Vector IDs are
deterministic, so a rerun overwrites instead of duplicating. Chunk text is
embedded but never stored in vector metadata.

Only completed, visible (not discarded or deleted) conversations are indexed.
Output is counts only: no conversation IDs or transcript text.

Dry-run is the default: it reads Firestore and counts the chunks it would embed,
with no embedding or vector writes. ``--apply`` embeds and upserts; it needs
explicit approval before it is pointed at production.

Usage:
    python scripts/backfill_transcript_chunk_vectors.py --uid <uid>
    python scripts/backfill_transcript_chunk_vectors.py --uid <uid> --apply
    python scripts/backfill_transcript_chunk_vectors.py --uid <uid> --apply --limit 50
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from utils.conversations.transcript_chunks import build_transcript_chunks

logger = logging.getLogger(__name__)


def _value(value: Any) -> Any:
    return getattr(value, 'value', value)


def chunks_for(conversation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The chunks to index for this row, or [] when it is not eligible."""
    if conversation.get('discarded') or conversation.get('deleted'):
        return []
    if _value(conversation.get('status')) != 'completed':
        return []
    segments = conversation.get('transcript_segments') or []
    if not isinstance(segments, list):
        return []
    # Same start time hydrate_chunk_texts uses, so chunk_index maps back to identical text.
    return build_transcript_chunks(segments, conversation.get('started_at') or conversation.get('created_at'))


@dataclass
class Summary:
    apply: bool
    scanned: int = 0
    eligible: int = 0
    chunks: int = 0
    upserted: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            'apply': self.apply,
            'scanned_conversations': self.scanned,
            'conversations_with_chunks': self.eligible,
            'chunks': self.chunks,
            'upserted_vectors': self.upserted,
            'failed_conversations': self.failed,
        }


def backfill_user(
    uid: str,
    conversations: Iterable[Mapping[str, Any]],
    *,
    apply: bool,
    upsert: Callable[[str, str, list[dict[str, Any]]], int],
    limit: Optional[int] = None,
) -> Summary:
    summary = Summary(apply=apply)
    for conversation in conversations:
        if limit is not None and summary.eligible >= limit:
            break
        summary.scanned += 1
        chunks = chunks_for(conversation)
        if not chunks:
            continue
        summary.eligible += 1
        summary.chunks += len(chunks)
        if not apply:
            continue
        try:
            summary.upserted += upsert(uid, str(conversation['id']), chunks)
        except Exception as error:
            # Keep going; a rerun overwrites by deterministic ID, so failures are safe to retry.
            summary.failed += 1
            logger.warning('transcript chunk backfill upsert failed: %s', type(error).__name__)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uid', required=True, help='The one user whose history to index.')
    parser.add_argument('--apply', action='store_true', help='Embed and upsert. Default is a read-only dry run.')
    parser.add_argument('--limit', type=int, default=None, help='Max conversations to index, newest first.')
    args = parser.parse_args()

    from database import conversations as conversations_db
    from database.vector_db import upsert_transcript_chunk_vectors

    summary = backfill_user(
        args.uid,
        conversations_db.iter_all_conversations(args.uid, include_discarded=False),
        apply=args.apply,
        upsert=upsert_transcript_chunk_vectors,
        limit=args.limit,
    )
    print(json.dumps(summary.as_dict()))
    return 1 if summary.failed else 0


if __name__ == '__main__':
    sys.exit(main())
