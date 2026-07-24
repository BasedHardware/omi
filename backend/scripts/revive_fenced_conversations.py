"""Admin entrypoint: revive conversations stranded behind the discard fence (single uid).

A conversation discarded while it looked empty, then filled with real speech by a
later offline sync, cannot recover on its own. The lifecycle guard refuses every
write to a discarded conversation, so the reprocess that would restore the summary
is fenced and the record is left at ``processing`` holding a full transcript, an
empty title, and no way for its owner to see it.

Clearing the flag first is what makes the reprocess land: reprocessing a
conversation that is still discarded is fenced exactly like the sync-initiated one
was, and would leave the record no better off.

A revived conversation becomes visible to its owner, so ``--min-words`` keeps
fragments out of their list rather than reviving everything indiscernibly.

Usage:
    cd backend
    python scripts/revive_fenced_conversations.py --uid UID --dry-run
    python scripts/revive_fenced_conversations.py --uid UID
    python scripts/revive_fenced_conversations.py --uid UID --min-words 200 --limit 25
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud.firestore_v1 import FieldFilter

import database.conversations as conversations_db
from database._client import db
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation

CHECKPOINT_DIR = Path('/tmp/revive_fenced_conversations')


def _checkpoint_path(uid: str) -> Path:
    return CHECKPOINT_DIR / f'{uid}.json'


def _load_done(uid: str) -> set[str]:
    path = _checkpoint_path(uid)
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()).get('done', []))
    except (json.JSONDecodeError, OSError):
        return set()


def _record_done(uid: str, done: set[str]) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    _checkpoint_path(uid).write_text(json.dumps({'uid': uid, 'done': sorted(done)}))


def find_stranded(uid: str) -> List[str]:
    """Conversation ids holding a transcript that no write can complete.

    ``discarded`` with a non-terminal ``processing`` status is the signature the
    fence leaves behind: a terminal discard would have settled the status too.
    """
    query = (
        db.collection('users')
        .document(uid)
        .collection(conversations_db.conversations_collection)
        .where(filter=FieldFilter('discarded', '==', True))
        .where(filter=FieldFilter('status', '==', 'processing'))
    )
    return [doc.id for doc in query.stream()]


def _word_count(conversation: Dict[str, Any]) -> int:
    segments = conversation.get('transcript_segments') or []
    return sum(len(str(segment.get('text', '')).split()) for segment in segments)


def _classify(uid: str, conversation_ids: List[str], min_words: int) -> Tuple[List[Tuple[str, int]], int]:
    eligible: List[Tuple[str, int]] = []
    skipped = 0
    for conversation_id in conversation_ids:
        conversation = conversations_db.get_conversation(uid, conversation_id)
        if not conversation:
            skipped += 1
            continue
        if conversations_db.is_soft_deleted(conversation):
            # A tombstone is invisible on purpose. Reviving it would resurrect
            # content its owner deleted, the same contract reprocess enforces.
            skipped += 1
            continue
        words = _word_count(conversation)
        if words < min_words:
            skipped += 1
            continue
        eligible.append((conversation_id, words))
    return eligible, skipped


def revive_one(uid: str, conversation_id: str, language: Optional[str]) -> bool:
    """Clear the flag, then reprocess. Returns whether the result persisted."""
    conversations_db.restore_conversation_from_discarded(uid, conversation_id)

    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        return False

    persisted: List[bool] = []
    process_conversation(
        uid,
        language or conversation.get('language') or 'en',
        deserialize_conversation(conversation),
        force_process=True,
        is_reprocess=True,
        persistence_observer=persisted.append,
    )
    return bool(persisted) and persisted[-1]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Revive conversations stranded behind the discard fence')
    parser.add_argument('--uid', required=True, help='Firebase uid to repair')
    parser.add_argument('--dry-run', action='store_true', help='Report what would be revived without writing')
    parser.add_argument(
        '--min-words',
        type=int,
        default=20,
        help='Skip conversations whose transcript is shorter than this (default: 20)',
    )
    parser.add_argument('--limit', type=int, help='Revive at most this many in one run')
    parser.add_argument('--language', help='Override the language passed to reprocessing')
    parser.add_argument('--no-resume', action='store_true', help='Ignore the checkpoint and reconsider every id')
    parser.add_argument(
        '--sleep',
        type=float,
        default=1.0,
        help='Seconds between reprocess calls, to pace transcription and LLM load (default: 1.0)',
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    uid = args.uid

    stranded = find_stranded(uid)
    print(f'stranded conversations (discarded, still processing): {len(stranded)}')
    if not stranded:
        return 0

    done = set() if args.no_resume else _load_done(uid)
    pending = [c for c in stranded if c not in done]
    if done:
        print(f'already revived in a previous run: {len(done)}')

    eligible, skipped = _classify(uid, pending, args.min_words)
    eligible.sort(key=lambda item: item[1], reverse=True)
    print(f'eligible (>= {args.min_words} words): {len(eligible)}   skipped: {skipped}')
    if eligible:
        total_words = sum(words for _, words in eligible)
        print(f'transcript words to be restored: {total_words:,}')

    if args.limit:
        eligible = eligible[: args.limit]
        print(f'limited to: {len(eligible)}')

    if args.dry_run:
        for conversation_id, words in eligible[:20]:
            print(f'  would revive {conversation_id}  ({words} words)')
        if len(eligible) > 20:
            print(f'  ... and {len(eligible) - 20} more')
        return 0

    revived = 0
    fenced = 0
    failed = 0
    for index, (conversation_id, words) in enumerate(eligible, start=1):
        try:
            if revive_one(uid, conversation_id, args.language):
                revived += 1
                done.add(conversation_id)
            else:
                fenced += 1
                print(f'  still fenced after clearing the flag: {conversation_id}')
        except Exception as error:  # noqa: BLE001 - one failure must not strand the rest
            failed += 1
            print(f'  failed {conversation_id}: {type(error).__name__}: {error}')
        _record_done(uid, done)
        if index % 10 == 0:
            print(f'  progress: {index}/{len(eligible)}  revived={revived} fenced={fenced} failed={failed}')
        if args.sleep:
            time.sleep(args.sleep)

    print(f'revived: {revived}   still fenced: {fenced}   failed: {failed}')
    return 0 if failed == 0 and fenced == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
