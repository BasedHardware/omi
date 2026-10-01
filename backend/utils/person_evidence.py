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
    COUNTERS,
    COUNTED_KEYS_LIMIT,
    MANUAL_LABELS,
    SOURCE_CARD,
    WEIGHTS,
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


def reconcile_evidence(
    evidence: Optional[Mapping[str, Any]],
    ledger: Optional[Mapping[str, Any]],
    conversation_id: str,
    kind: Optional[str],
    still_labeled: bool,
    generation: int,
    now: datetime,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Reconcile one conversation's contribution, fenced by its assignment generation.

    The durable ledger lives in the encrypted manual-assignment receipt, not the
    person's bounded diagnostic key cache. One positive contribution per person
    per conversation uses the strongest observed source; it is retracted when
    no reviewed segment remains. Automatic corrections remain negative history.
    """
    current = dict(evidence) if isinstance(evidence, Mapping) else {}
    counted = [key for key in current.get('counted') or [] if isinstance(key, str)]
    previous = (
        set(ledger.get('kinds', [])) & set(COUNTERS)
        if ledger is not None
        else {key for key in COUNTERS if f'{key}:{conversation_id}' in counted}
    )
    if ledger and generation < ledger.get('generation', 0):
        return None, dict(ledger)
    following = previous & {AUTO_CORRECTED}
    if kind == AUTO_CORRECTED:
        following.add(kind)
    if still_labeled:
        positive = previous - {AUTO_CORRECTED}
        if kind and kind != AUTO_CORRECTED:
            positive.add(kind)
        if positive:
            following.add(max(positive, key=lambda key: WEIGHTS[key]))
    updated_ledger = {'kinds': sorted(following), 'generation': generation}
    if previous == following:
        return None, updated_ledger
    for key in previous - following:
        current[key] = max(0, evidence_count(current, key) - 1)
    for key in following - previous:
        current[key] = evidence_count(current, key) + 1
    keys = {f'{key}:{conversation_id}' for key in COUNTERS}
    current['counted'] = (
        [key for key in counted if key not in keys] + [f'{key}:{conversation_id}' for key in sorted(following)]
    )[-COUNTED_KEYS_LIMIT:]
    if following - previous - {AUTO_CORRECTED}:
        current['last_labeled_at'] = now
    return current, updated_ledger


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
    receipt: Dict[str, Any],
    after: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Every person-document write one manual assignment makes, and the sample paths it retires.

    ``people`` holds the documents read in the transaction (missing people map to None).
    A person who loses the relabeled segments has a speech profile taught from them
    fenced off; every person the assignment earns evidence for gets its new tally.
    """
    updates: Dict[str, Dict[str, Any]] = {}
    if len(people) > 499:
        raise ValueError('Assignment affects too many people for one transaction')
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
    earned = assignment_evidence(before, person_id=person_id, source=source)
    ledger = dict(receipt.get('label_evidence') or {})
    for pid, person in people.items():
        if not person:
            continue
        still_labeled = any(s.get('person_id') == pid and not _auto(s) and not s.get('is_user') for s in after)
        tally, contribution = reconcile_evidence(
            person.get('label_evidence'),
            ledger.get(pid),
            conversation_id,
            earned.get(pid),
            still_labeled,
            receipt.get('generation', 0),
            now,
        )
        ledger[pid] = contribution
        if tally is not None:
            updates.setdefault(pid, {})['label_evidence'] = tally
    receipt['label_evidence'] = ledger
    return updates, removed
