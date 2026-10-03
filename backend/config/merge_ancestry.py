"""Bounded ancestry handling for flattening sync-bridge tombstones one hop up.

A smart merge that absorbs a donor which already absorbed sync bridge sources
must not leave a two-hop redirect chain (ancestor -> donor -> survivor): every
existing redirect reader follows exactly one level of ``sync_merged_into``. The
helpers here plan that flatten purely: they take rows already read inside the
transaction and return the union ancestor list plus the per-ancestor re-point
patches, or a bounded rejection reason.

An inherited ancestor is safe to re-point only when it is a plain sync bridge
tombstone: deleted and discarded, redirecting exactly at the donor that
declared it, carrying a positive integer ``sync_content_revision``, holding no
``smart_merge`` state, and passing the same user-managed guards the pair check
applies. Anything else rejects the whole absorb; validation happens before any
write, so a rejection commits nothing.

Pure module: no I/O, no env reads.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from config.conversation_smart_merge import MAX_FRAGMENTS

INVALID = 'flatten_ancestor_invalid'
USER_MANAGED = 'flatten_ancestor_user_managed'
CAP = 'flatten_ancestor_cap'

_MAX_ID_CHARS = 128
MAX_UNION_ANCESTORS = MAX_FRAGMENTS - 1


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= _MAX_ID_CHARS and '/' not in value


def _smart_state(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get('smart_merge')
    return value if isinstance(value, Mapping) else {}


def ancestry_ids(row: Mapping[str, Any]) -> tuple[Optional[str], list[str]]:
    """``(reason, ids)`` for a row's declared ancestry; a reason rejects the merge.

    The list must contain only nonempty, slash-free, bounded ids and at most
    ``MAX_FRAGMENTS - 1`` raw entries — duplicates cannot inflate the union past
    the physical-row cap. A list past the cap returns ``CAP`` before any
    descendant row is examined; malformed shape returns ``INVALID``. Missing or
    empty is not an error: ``(None, [])``.
    """
    raw = row.get('sync_merged_from')
    if raw is None:
        return None, []
    if not isinstance(raw, list):
        return INVALID, []
    if len(raw) > MAX_UNION_ANCESTORS:
        return CAP, []
    if not all(_valid_id(item) for item in raw):
        return INVALID, []
    return None, sorted(set(raw))


def _positive_revision(row: Mapping[str, Any]) -> bool:
    revision = row.get('sync_content_revision')
    return isinstance(revision, int) and not isinstance(revision, bool) and revision > 0


def _plain_tombstone(row: Mapping[str, Any], merged_into: str) -> bool:
    return (
        row.get('deleted') is True
        and row.get('discarded') is True
        and row.get('sync_merged_into') == merged_into
        and _positive_revision(row)
    )


def _declared_cycle(edges: Mapping[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visited:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        cyclic = any(visit(next_id) for next_id in edges.get(node, ()))
        visiting.discard(node)
        visited.add(node)
        return cyclic

    return any(visit(node) for node in edges)


def ancestry_union(
    survivor: Mapping[str, Any],
    donors: Mapping[str, Mapping[str, Any]],
) -> tuple[Optional[str], list[str]]:
    """``(reason, union_ids)`` for the flattened ancestry; validates before reads.

    The union is the survivor's declared ancestry plus every direct donor id
    and every id the donors declare. Direct donor ids must be bounded valid
    strings, their ``smart_merge`` state absent, their ancestry lists well
    shaped, and no ancestor may collide with the survivor's ancestry, a direct
    donor id, or an ancestor declared by a different donor. A union past
    ``MAX_UNION_ANCESTORS`` returns ``CAP`` — all before any descendant row is
    read, so a transaction may call this first and only fetch the returned ids.
    """
    survivor_id = str(survivor.get('id'))
    reason, survivor_ids = ancestry_ids(survivor)
    if reason is not None:
        return reason, []
    survivor_set = set(survivor_ids)
    donor_ancestry: dict[str, list[str]] = {}
    donor_id_of: dict[str, str] = {}
    for donor_id, donor in donors.items():
        if not _valid_id(donor_id) or _smart_state(donor):
            return INVALID, []
        reason, ids = ancestry_ids(donor)
        if reason is not None:
            return reason, []
        donor_ancestry[donor_id] = ids
        for ancestor_id in ids:
            if ancestor_id in survivor_set or ancestor_id in donor_id_of:
                return INVALID, []
            donor_id_of[ancestor_id] = donor_id
    union = survivor_set | set(donor_ancestry) | set(donor_id_of)
    if len(union) > MAX_UNION_ANCESTORS:
        return CAP, []
    if survivor_id in union or set(donor_ancestry) & (survivor_set | set(donor_id_of)):
        return INVALID, []
    return None, sorted(union)


def flatten_updates(
    survivor: Mapping[str, Any],
    donors: Mapping[str, Mapping[str, Any]],
    ancestor_rows: Mapping[str, Optional[Mapping[str, Any]]],
    *,
    user_managed: Callable[[Mapping[str, Any]], bool],
) -> tuple[Optional[str], list[str], dict[str, dict[str, Any]]]:
    """Plan the ancestor flatten for one absorb.

    ``survivor`` and ``donors`` are the direct rows; ``ancestor_rows`` maps every
    id in the union minus the direct donors — the survivor's existing ancestry
    and each donor's declared ancestry — to its row (``None`` when the document
    is missing). Returns ``(reason, union_ids, updates)`` where ``union_ids`` is
    the sorted full ancestry the survivor should store and ``updates`` maps each
    newly inherited ancestor id to its re-point patch. A reason rejects
    everything; existing survivor ancestors are validated but never rewritten.
    """
    survivor_id = str(survivor.get('id'))
    reason, union = ancestry_union(survivor, donors)
    if reason is not None:
        return reason, [], {}
    survivor_set = set(ancestry_ids(survivor)[1])
    donor_ancestry = {donor_id: ancestry_ids(donor)[1] for donor_id, donor in donors.items()}
    donor_id_of = {aid: donor_id for donor_id, ids in donor_ancestry.items() for aid in ids}
    updates: dict[str, dict[str, Any]] = {}
    declared: dict[str, list[str]] = {}
    for ancestor_id in sorted(set(union) - set(donor_ancestry)):
        row = ancestor_rows.get(ancestor_id)
        if row is None:
            return INVALID, [], {}
        if ancestor_id in survivor_set:
            # Already the survivor's own tombstone: keep it untouched, but a
            # foreign or malformed row must not ride the union invisibly.
            state = _smart_state(row)
            if not _plain_tombstone(row, survivor_id):
                return INVALID, [], {}
            if state and (state.get('role') != 'donor' or state.get('survivor_id') != survivor_id):
                return INVALID, [], {}
            reason, nested = ancestry_ids(row)
            if reason is not None or any(
                nested_id not in survivor_set
                or (ancestor_rows.get(nested_id) or {}).get('sync_merged_into') != survivor_id
                for nested_id in nested
            ):
                return INVALID, [], {}
            if nested:
                declared[ancestor_id] = nested
            continue
        declared_by = donor_id_of[ancestor_id]
        if not _plain_tombstone(row, declared_by) or _smart_state(row):
            return INVALID, [], {}
        reason, nested = ancestry_ids(row)
        if reason is not None or any(
            nested_id not in donor_ancestry[declared_by]
            or (ancestor_rows.get(nested_id) or {}).get('sync_merged_into') != declared_by
            for nested_id in nested
        ):
            return INVALID, [], {}
        if nested:
            declared[ancestor_id] = nested
        if user_managed(row):
            return USER_MANAGED, [], {}
        revision = int(row['sync_content_revision'])
        patch: dict[str, Any] = {
            'sync_merged_into': survivor_id,
            'sync_content_revision': revision + 1,
        }
        if row.get('sync_bridge_cleaned_revision') == revision:
            patch['sync_bridge_cleaned_revision'] = revision + 1
        updates[ancestor_id] = patch
    if _declared_cycle(declared):
        return INVALID, [], {}
    return None, sorted(union), updates
