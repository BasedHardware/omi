#!/usr/bin/env python3
"""Bring conversations stored before the relevance step onto the stored-flag contract.

Two kinds of row are visible only because they predate the relevance step:

1. Legacy sync review rows (``sync_relevance='review'``) written with
   ``discarded=False``. Readers used to hide them with a read-time projection;
   readers now trust the stored ``discarded`` flag alone, so these rows must be
   stamped before that reader change is deployed.
2. Conversations never assessed at all (no ``relevance_decision``): offline
   sync, client finalize, and desktop captures from before the relevance step.
   Only audio-transcript sources are eligible, and an empty transcript is never
   a discard here. The deterministic rules (no model, no cost) run over the
   transcript; only a rule discard is written. What they cannot settle is left
   alone.

A row a user curated (starred, renamed, restored, shared, foldered, photos) or
one with stored calendar-meeting evidence is never touched. Every write goes
through ``lifecycle.discard_by_relevance``, which re-reads the row in a
transaction and refuses deleted, hidden, or restored rows. Discard stays
recoverable (Show discarded, restore).

Dry-run is the default and reads only. ``--apply`` writes; it needs explicit
approval before it is pointed at production.

Usage:
    python scripts/conversation_relevance_backfill.py --uid <uid>
    python scripts/conversation_relevance_backfill.py --limit 50
    python scripts/conversation_relevance_backfill.py --apply --start-after <uid>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from utils.conversations.fragment_visibility import is_low_signal_sync_fragment, is_user_curated
from utils.conversations.relevance_rules import RULES_VERSION, deterministic_relevance
from utils.conversations.wake_word import find_wake_word_matches

BACKFILL_TRIGGER = 'backfill'

# Only conversations whose content is an audio transcript. App/workflow imports
# (external_integration, workflow), camera captures (openglass), screen capture,
# onboarding, and rows with no recorded source keep their content elsewhere, so
# the transcript rules cannot see it: the first production run hid ~49k of them.
AUDIO_TRANSCRIPT_SOURCES = frozenset(
    {
        'friend',
        'omi',
        'fieldy',
        'bee',
        'plaud',
        'frame',
        'friend_com',
        'apple_watch',
        'phone',
        'phone_call',
        'desktop',
        'sdcard',
        'limitless',
        'rayban_meta',
    }
)
_DEFAULT_PAGE_SIZE = 200


def _value(value: Any) -> Any:
    return getattr(value, 'value', value)


def _has_calendar_evidence(conversation: Mapping[str, Any]) -> bool:
    external = conversation.get('external_data')
    return bool(
        conversation.get('calendar_event')
        or (isinstance(external, Mapping) and external.get('calendar_meeting_context'))
    )


def verdict_for(conversation: Mapping[str, Any]) -> Optional[str]:
    """The rule that settles this row as discarded, or None to leave it alone."""
    if conversation.get('discarded') or conversation.get('deleted'):
        return None
    if _value(conversation.get('status')) != 'completed':
        return None
    if is_low_signal_sync_fragment(conversation):
        return 'legacy_review'
    if conversation.get('relevance_decision') or is_user_curated(conversation):
        return None
    if _has_calendar_evidence(conversation):
        return None
    if str(_value(conversation.get('source')) or '') not in AUDIO_TRANSCRIPT_SOURCES:
        return None
    segments = conversation.get('transcript_segments') or []
    if not isinstance(segments, list):
        return None
    if find_wake_word_matches(segments):
        return None
    texts = [str(segment.get('text') or '') for segment in segments if isinstance(segment, Mapping)]
    verdict, rule = deterministic_relevance(texts, None)
    # After the fact, no transcript is unknown content (stored elsewhere, or not
    # decoded), never evidence of filler; only the live step may discard it.
    if rule == 'empty_transcript':
        return None
    return rule if verdict == 'discard' else None


def decision_record(rule: str) -> dict[str, Any]:
    return {
        'verdict': 'discard',
        'decided_by': 'rule',
        'reason': rule,
        'trigger': BACKFILL_TRIGGER,
        'rules_version': RULES_VERSION,
    }


@dataclass
class Summary:
    apply: bool
    scanned_users: int = 0
    scanned_conversations: int = 0
    discards: Counter = field(default_factory=Counter)
    written: int = 0
    refused: int = 0
    last_uid: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            'apply': self.apply,
            'scanned_users': self.scanned_users,
            'scanned_conversations': self.scanned_conversations,
            'discards_by_rule': dict(self.discards),
            'written': self.written,
            'refused_at_write': self.refused,
            'last_uid': self.last_uid,
        }


def backfill_user(
    uid: str,
    conversations: Iterable[Mapping[str, Any]],
    *,
    apply: bool,
    discard: Callable[[str, str, dict[str, Any]], bool],
    summary: Summary,
) -> None:
    summary.scanned_users += 1
    summary.last_uid = uid
    for conversation in conversations:
        summary.scanned_conversations += 1
        rule = verdict_for(conversation)
        if rule is None:
            continue
        summary.discards[rule] += 1
        if not apply:
            continue
        if discard(uid, str(conversation.get('id')), decision_record(rule)):
            summary.written += 1
        else:
            summary.refused += 1


def _user_ids(client: Any, *, page_size: int, start_after: Optional[str], limit: Optional[int]) -> Iterable[str]:
    page_size = min(max(int(page_size), 1), _DEFAULT_PAGE_SIZE)
    remaining = None if limit is None or limit <= 0 else int(limit)
    cursor: Any = {'__name__': start_after} if start_after else None
    while remaining is None or remaining > 0:
        take = page_size if remaining is None else min(page_size, remaining)
        query = client.collection('users').select([]).order_by('__name__').limit(take)
        if cursor is not None:
            query = query.start_after(cursor)
        page = list(query.stream())
        for snapshot in page:
            yield str(snapshot.id)
        if remaining is not None:
            remaining -= len(page)
        if len(page) < take:
            return
        cursor = page[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='Write discards. Default is a read-only dry run.')
    parser.add_argument('--uid', default=None, help='Run for one user only.')
    parser.add_argument('--page-size', type=int, default=_DEFAULT_PAGE_SIZE, help='Users per page.')
    parser.add_argument('--start-after', default=None, metavar='UID', help='Resume after this user id.')
    parser.add_argument('--limit', type=int, default=None, help='Max users to scan (smoke runs).')
    args = parser.parse_args()

    from database import conversations as conversations_db
    from database._client import get_firestore_client
    from utils.conversations import lifecycle

    summary = Summary(apply=args.apply)
    uids: Iterable[str] = (
        [args.uid]
        if args.uid
        else _user_ids(get_firestore_client(), page_size=args.page_size, start_after=args.start_after, limit=args.limit)
    )
    for uid in uids:
        backfill_user(
            uid,
            conversations_db.iter_all_conversations(uid, include_discarded=False),
            apply=args.apply,
            discard=lifecycle.discard_by_relevance,
            summary=summary,
        )
    print(json.dumps(summary.as_dict()))


if __name__ == '__main__':
    main()
