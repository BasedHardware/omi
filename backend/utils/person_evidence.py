"""How one manual assignment changes people's ``label_evidence`` tallies (pure, no IO).

Used inside the manual-assignment transaction and by the receipt backfill. Counter
names, weights and the band mapping live in ``models.person_confidence``.
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from models.person_confidence import (
    AUTO_CONFIRMED,
    AUTO_CORRECTED,
    CARD_CONFIRMS,
    CARD_PICKS,
    COUNTED_KEYS_LIMIT,
    MANUAL_LABELS,
    SOURCE_CARD,
    evidence_count,
)


def _auto(segment: Mapping[str, Any]) -> bool:
    return bool(segment.get('speaker_match_source'))


def assignment_evidence(
    before: Sequence[Mapping[str, Any]],
    *,
    person_id: Optional[str],
    source: str,
) -> Dict[str, str]:
    """person_id -> counter key that one manual assignment earns, from the segments it relabeled.

    ``before`` are the relabeled segments as they were before the assignment. The
    target gains one event; a person whose automatic match was moved away gains a
    correction. Segments already labeled by hand to the target earn nothing.
    """
    earned: Dict[str, str] = {}
    if person_id:
        auto_same = any(s.get('person_id') == person_id and _auto(s) for s in before)
        unchanged = before and all(s.get('person_id') == person_id and not _auto(s) for s in before)
        if not unchanged:
            if source == SOURCE_CARD:
                earned[person_id] = CARD_CONFIRMS if auto_same else CARD_PICKS
            else:
                earned[person_id] = AUTO_CONFIRMED if auto_same else MANUAL_LABELS
    for segment in before:
        previous = segment.get('person_id')
        if previous and previous != person_id and _auto(segment):
            earned.setdefault(previous, AUTO_CORRECTED)
    return earned


def apply_evidence(
    evidence: Optional[Mapping[str, Any]],
    kind: str,
    conversation_id: str,
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """The updated tally, or None when this conversation already counted for ``kind`` (idempotent)."""
    current = dict(evidence) if isinstance(evidence, Mapping) else {}
    counted = [key for key in current.get('counted') or [] if isinstance(key, str)]
    key = f'{kind}:{conversation_id}'
    if key in counted:
        return None
    counted.append(key)
    current['counted'] = counted[-COUNTED_KEYS_LIMIT:]
    current[kind] = evidence_count(current, kind) + 1
    if kind != AUTO_CORRECTED:
        current['last_labeled_at'] = now
    return current


def merge_backfill(
    evidence: Optional[Mapping[str, Any]],
    conversation_ids: Iterable[str],
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """Add one hand label per receipt conversation not yet counted. None when nothing changes."""
    current: Optional[Dict[str, Any]] = dict(evidence) if isinstance(evidence, Mapping) else {}
    changed = False
    for conversation_id in conversation_ids:
        updated = apply_evidence(current, MANUAL_LABELS, conversation_id, now)
        if updated is not None:
            current, changed = updated, True
    if not changed:
        return None
    # A backfill does not know when the user labeled; keep any real timestamp.
    if evidence and evidence.get('last_labeled_at'):
        current['last_labeled_at'] = evidence['last_labeled_at']
    else:
        current.pop('last_labeled_at', None)
    return current


def receipt_person_ids(receipt: Optional[Mapping[str, Any]]) -> List[str]:
    """People named by explicit decisions in one conversation's manual-assignment receipt."""
    if not isinstance(receipt, Mapping):
        return []
    found: List[str] = []
    for group in ('speakers', 'segments'):
        entries = receipt.get(group)
        if not isinstance(entries, Mapping):
            continue
        for entry in entries.values():
            if not isinstance(entry, Mapping) or entry.get('is_user'):
                continue
            person_id = entry.get('person_id')
            if isinstance(person_id, str) and person_id and person_id not in found:
                found.append(person_id)
    return found


def person_updates_for_assignment(
    people: Mapping[str, Optional[Mapping[str, Any]]],
    previous: Iterable[str],
    person_id: Optional[str],
    before: Sequence[Mapping[str, Any]],
    source: str,
    conversation_id: str,
    resolved: Sequence[str],
    now: datetime,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Every person-document write one manual assignment makes, and the sample paths it retires.

    ``people`` holds the documents read in the transaction (missing people map to None).
    A person who loses the relabeled segments has a speech profile taught from them
    fenced off; every person the assignment earns evidence for gets its new tally.
    """
    updates: Dict[str, Dict[str, Any]] = {}
    removed: List[str] = []
    for pid in previous:
        person = people.get(pid)
        if not person:
            continue
        update: Dict[str, Any] = {'updated_at': now}
        taught = person.get('speech_sample_source') or {}
        if taught.get('conversation_id') == conversation_id and set(taught.get('segment_ids', [])) & set(resolved):
            removed.extend(person.get('speech_samples', []))
            update.update(
                speech_samples=[], speech_sample_transcripts=[], speaker_embedding=None, speech_sample_source=None
            )
        updates[pid] = update
    for pid, kind in assignment_evidence(before, person_id=person_id, source=source).items():
        person = people.get(pid)
        if not person:
            continue
        tally = apply_evidence(person.get('label_evidence'), kind, conversation_id, now)
        if tally is not None:
            updates.setdefault(pid, {})['label_evidence'] = tally
    return updates, removed
