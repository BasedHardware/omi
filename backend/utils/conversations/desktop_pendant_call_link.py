"""Bounded deterministic pair selection, independent of transcript contents."""

from __future__ import annotations

import logging
from typing import Mapping, Any

from config.desktop_pendant_call_link import (
    CALL_GROUP_KIND,
    call_link_mode,
    call_pair,
    capture_windows,
    desktop_meeting,
)
from database import capture_groups as groups_db
from database import conversations as conversations_db

logger = logging.getLogger(__name__)


def select_pairs(rows: list[Mapping[str, Any]]) -> list[tuple[str, str, dict]]:
    """Greedy total ordering of all observed edges: each endpoint is used once.

    A persisted pair is reserved; a late candidate cannot steal an endpoint or
    transitively bridge it. Query saturation is handled by the caller.
    """
    edges = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            evidence = call_pair(a, b)
            if evidence is None:
                continue
            ids = {a['id'], b['id']}
            if any(set(r.get('capture_group_exclusions') or ()) & ids for r in (a, b)):
                continue
            groups = [r.get('capture_group') or {} for r in (a, b)]
            if any(g.get('id') and {m['id'] for m in g.get('members', [])} != ids for g in groups):
                continue
            if len({g['id'] for g in groups if g.get('id')}) > 1:
                continue
            desktop, pendant = (a, b) if desktop_meeting(a) else (b, a)
            reserved = any(g.get('id') for g in groups)
            rank = (
                not reserved,
                -evidence['overlap_seconds'],
                -evidence['overlap_ratio'],
                desktop['id'],
                pendant['id'],
            )
            edges.append((rank, desktop['id'], pendant['id'], evidence))
    used = set()
    pairs = []
    for _, desktop_id, pendant_id, evidence in sorted(edges):
        if desktop_id in used or pendant_id in used:
            continue
        used.update((desktop_id, pendant_id))
        pairs.append((desktop_id, pendant_id, evidence))
    return pairs


def link_call_pair(uid: str, conversation_id: str, rows: list[dict], *, saturated: bool) -> None:
    mode = call_link_mode(uid)
    if mode == 'off':
        return
    # Refresh the arriving row; finalizer models can predate group/unlink writes.
    own, _ = conversations_db.get_conversation_for_capture_check(uid, conversation_id)
    if not own:
        return
    own = dict(own, id=conversation_id)
    by_id = {r['id']: r for r in rows}
    by_id[conversation_id] = own
    candidates = sum(call_pair(own, other) is not None for other in by_id.values())
    selected = next((p for p in select_pairs(list(by_id.values())) if conversation_id in p[:2]), None)
    evidence = selected[2] if selected else {}
    reason = 'page_saturated' if saturated else ('best_pair' if selected else 'no_available_pair')
    decision = 'keep'
    if selected and not saturated:
        decision = 'would_link'
        if mode == 'on':
            desktop_id, pendant_id, evidence = selected
            expected_windows = capture_windows(by_id[desktop_id], by_id[pendant_id])
            if expected_windows is None:
                return
            group_id = groups_db.join_capture_group(
                uid,
                desktop_id,
                pendant_id,
                evidence,
                expected_windows=expected_windows,
                call_primary_id=desktop_id,
            )
            decision = 'linked' if group_id else 'keep'
            reason = 'best_pair' if group_id else 'conflict'
    logger.info(
        'event=desktop_pendant_call_link role=%s overlap_seconds=%.1f overlap_ratio=%.3f candidate_count=%d decision=%s reason=%s',
        'meeting' if desktop_meeting(own) else 'omi' if own.get('source') == 'omi' else 'other',
        evidence.get('overlap_seconds', 0),
        evidence.get('overlap_ratio', 0),
        candidates,
        decision,
        reason,
    )


def reserved_for_call(row: Mapping[str, Any]) -> bool:
    return (row.get('capture_group') or {}).get('kind') == CALL_GROUP_KIND
