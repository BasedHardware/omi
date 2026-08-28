"""Enforcement moves, server-side (contract §7).

These were client-side in the prototype and are now the server's job,
because the measured model violated each of them:

1. Cap is applied, not requested — at most max_persisted survive.
2. Only approved_clean persists. No exceptions (enforced upstream — nothing
   here is ever handed a rejected candidate to begin with).
3. The banner must be a frame that survived the cap: highest
   banner_suitability among survivors, only if >= 0.35.
4. Capture order, not model order — strip sorted by captured_at, rank 0..5.

ASSUMPTION (not specified by the contract): when the combined pool of
existing + newly-approved frames exceeds max_persisted, the OLDEST frames by
captured_at are evicted first, keeping the most recent max_persisted. The
contract states the cap and the banner/strip selection precisely but not the
eviction order; "most recent survives" is the simplest rule consistent with
a rolling meeting note and is flagged here for review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

import database.screen_frames as screen_frames_db
import utils.other.storage as storage
from models.screen_frame import ConversationScreenFrame, ConversationScreenFrameSet, ScreenFrameGround
from utils.screen_frames import store as screen_frame_store

logger = logging.getLogger(__name__)

BANNER_SUITABILITY_THRESHOLD = 0.35
STRIP_MAX = 6

_NEUTRAL_GROUND_FALLBACK = {"stops": ["#5A5D66", "#33363D"], "is_neutral": True}


@dataclass(frozen=True)
class NewPersistedFrame:
    """One frame the writer has already committed to GCS, awaiting a Firestore
    record and a role/rank from enforcement."""

    frame_id: str
    captured_at: datetime
    caption: str
    labels: List[str]
    source_badge: Optional[str]
    banner_suitability: float
    width: int
    height: int
    canonical_sha256: str
    ground: ScreenFrameGround


def _frame_doc(frame: NewPersistedFrame) -> Dict[str, Any]:
    return {
        'id': frame.frame_id,
        'captured_at': frame.captured_at,
        'caption': frame.caption,
        'labels': list(frame.labels),
        'source_badge': frame.source_badge,
        'banner_suitability': frame.banner_suitability,
        'focal_region': None,
        'width': frame.width,
        'height': frame.height,
        'canonical_sha256': frame.canonical_sha256,
        'ground': frame.ground.model_dump(),
        'created_at': datetime.now(timezone.utc),
    }


def _apply_cap_and_roles(
    existing: List[Dict[str, Any]], new_docs: List[Dict[str, Any]], max_persisted: int
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Merge existing + new by id, cap to max_persisted (oldest evicted
    first), pick the banner among survivors, assign role/rank.

    Returns (survivors, evicted); each survivor dict has 'role'/'rank' set
    in place.
    """
    by_id: Dict[str, Dict[str, Any]] = {}
    for doc in [*existing, *new_docs]:
        by_id[doc['id']] = doc
    pool = sorted(by_id.values(), key=lambda d: d['captured_at'])

    if len(pool) > max_persisted:
        evicted = pool[: len(pool) - max_persisted]
        survivors = pool[len(pool) - max_persisted :]
    else:
        evicted = []
        survivors = pool

    banner_id: Optional[str] = None
    best = BANNER_SUITABILITY_THRESHOLD
    for doc in survivors:
        suitability = float(doc.get('banner_suitability') or 0.0)
        if suitability >= best:
            banner_id = doc['id']
            best = suitability

    strip_candidates = sorted((d for d in survivors if d['id'] != banner_id), key=lambda d: d['captured_at'])
    strip_candidates = strip_candidates[:STRIP_MAX]
    strip_rank = {d['id']: rank for rank, d in enumerate(strip_candidates)}

    for doc in survivors:
        if doc['id'] == banner_id:
            doc['role'] = 'banner'
            doc['rank'] = 0
        elif doc['id'] in strip_rank:
            doc['role'] = 'strip'
            doc['rank'] = strip_rank[doc['id']]
        else:
            # Defensive only: with max_persisted == 1 banner + STRIP_MAX,
            # every non-banner survivor fits in strip_rank. Kept out of the
            # visible set rather than raising, since being over-cautious
            # here just means an extra frame doesn't render this round.
            doc['role'] = 'strip'
            doc['rank'] = STRIP_MAX

    return survivors, evicted


def _to_api_frame(uid: str, conversation_id: str, doc: Dict[str, Any]) -> ConversationScreenFrame:
    frame_id = doc['id']
    content_url = storage.get_screen_frame_signed_url(uid, conversation_id, frame_id)
    thumbnail_url = storage.get_screen_frame_thumbnail_signed_url(uid, conversation_id, frame_id)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=storage.SCREEN_FRAME_SIGNED_URL_MINUTES)
    ground_data = doc.get('ground') or _NEUTRAL_GROUND_FALLBACK
    return ConversationScreenFrame(
        id=frame_id,
        captured_at=doc['captured_at'],
        role=doc.get('role') or 'strip',
        rank=int(doc.get('rank') or 0),
        caption=doc.get('caption') or '',
        labels=list(doc.get('labels') or []),
        source_badge=doc.get('source_badge'),
        focal_region=None,
        width=int(doc.get('width') or 0),
        height=int(doc.get('height') or 0),
        content_url=content_url,
        thumbnail_url=thumbnail_url,
        url_expires_at=expires_at,
        ground=ScreenFrameGround.model_validate(ground_data),
    )


def build_frame_set_response(uid: str, conversation_id: str) -> ConversationScreenFrameSet:
    """Read the currently-persisted survivor set and build the wire shape,
    with freshly-generated signed URLs. Never recomputes role/rank/ground —
    those are only touched by enforcement / the palette module respectively.
    """
    frames = screen_frames_db.get_conversation_screen_frames(uid, conversation_id)
    revision = screen_frames_db.get_conversation_screen_frames_revision(uid, conversation_id)

    banner: Optional[ConversationScreenFrame] = None
    strip: List[ConversationScreenFrame] = []
    for doc in frames:
        try:
            api_frame = _to_api_frame(uid, conversation_id, doc)
        except ValidationError:
            # One unrepresentable stored frame must cost that frame, not the note.
            # ConversationScreenFrame still enforces the wire contract (caption
            # length, label count, two gradient stops), and a doc that violates it
            # — legacy data, a hand edit, a future write path that skips
            # ScreenFrameJudgement — used to raise straight out of this loop and
            # 500 the whole read. The user's other screenshots are fine; serve them.
            logger.warning(
                "screen_frame skipping unrepresentable stored frame uid=%s conversation_id=%s frame_id=%s",
                uid,
                conversation_id,
                doc.get('id'),
            )
            continue
        if api_frame.role == 'banner':
            banner = api_frame
        else:
            strip.append(api_frame)
    strip.sort(key=lambda f: f.captured_at)
    adjudicated_at = screen_frames_db.get_conversation_screen_frames_adjudicated_at(uid, conversation_id)
    return ConversationScreenFrameSet(
        revision=revision,
        banner=banner,
        strip=strip[:STRIP_MAX],
        adjudicated_at=adjudicated_at,
    )


def enforce_and_persist(
    uid: str,
    conversation_id: str,
    max_persisted: int,
    new_frames: List[NewPersistedFrame],
) -> tuple[ConversationScreenFrameSet, bool]:
    """Merge newly-written frames into the conversation's persisted set,
    apply the cap, (re)assign banner/strip roles, and persist the result.

    Returns (frame_set, committed) where committed is True iff at least one
    of `new_frames` survived into the persisted set (i.e. wasn't immediately
    evicted by the cap) — this drives the adjudication response's "outcome".
    """
    existing = screen_frames_db.get_conversation_screen_frames(uid, conversation_id)
    new_docs = [_frame_doc(f) for f in new_frames]
    new_ids = {f.frame_id for f in new_frames}

    survivors, evicted = _apply_cap_and_roles(existing, new_docs, max_persisted)

    if survivors:
        screen_frame_store.persist_screen_frame_docs(uid, conversation_id, survivors)
    for doc in evicted:
        screen_frame_store.delete_screen_frame(uid, conversation_id, doc['id'])

    if new_docs:
        screen_frames_db.bump_conversation_screen_frames_revision(uid, conversation_id)

    committed = any(doc['id'] in new_ids for doc in survivors)
    return build_frame_set_response(uid, conversation_id), committed


def promote_banner_after_deletion(uid: str, conversation_id: str) -> ConversationScreenFrameSet:
    """After a per-frame delete, re-derive banner/strip roles over whatever
    is left. Contract §8: deleting the banner may promote only another
    already-approved, already-persisted frame; otherwise banner becomes
    None. Since every remaining doc is already an approved, persisted
    survivor, this is exactly _apply_cap_and_roles run again over the
    smaller remaining pool with no new candidates and no cap in play (the
    pool already shrank, never grew).
    """
    remaining = screen_frames_db.get_conversation_screen_frames(uid, conversation_id)
    if remaining:
        survivors, _evicted = _apply_cap_and_roles(remaining, [], max_persisted=len(remaining))
        screen_frame_store.persist_screen_frame_docs(uid, conversation_id, survivors)
    screen_frames_db.bump_conversation_screen_frames_revision(uid, conversation_id)
    return build_frame_set_response(uid, conversation_id)
