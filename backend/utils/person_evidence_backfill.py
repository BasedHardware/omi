"""Seed ``people/{id}.label_evidence`` from existing manual-assignment receipts.

Receipts do not record whether a decision came from the transcript tag sheet or a
suggestion card, so every receipt conversation counts as one hand label. Counting is
keyed per conversation (``manual_labels:<conversation_id>``), so re-running, resuming,
or overlapping with live labels never counts a conversation twice.
"""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from google.cloud import firestore

from database._client import run_transactional
from models.person_confidence import AUTO_CORRECTED, MANUAL_LABELS
from utils.manual_speaker_assignments import apply_manual_assignments
from utils.person_evidence import reconcile_evidence, receipt_person_ids

DecodeReceipt = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def receipt_conversations_by_person(
    conversations: Iterable[Tuple[str, Mapping[str, Any]]], decode: DecodeReceipt
) -> Dict[str, List[str]]:
    """person_id -> conversation ids whose receipt names them. Skips deleted and merged-away rows."""
    found: Dict[str, List[str]] = {}
    for conversation_id, data in conversations:
        if data.get('deleted') or not data.get('manual_speaker_assignments'):
            continue
        for person_id in receipt_person_ids(decode(data)):
            found.setdefault(person_id, []).append(conversation_id)
    return found


def backfill_person(
    client: Any,
    uid: str,
    person_id: str,
    conversation_ids: List[str],
    now: datetime,
    *,
    apply: bool,
) -> Optional[Dict[str, Any]]:
    """Merge one person's receipt conversations into their tally. Returns the new tally, or None when unchanged."""
    ref = client.collection('users').document(uid).collection('people').document(person_id)

    # One conversation per transaction bounds reads/writes independently of page size.
    # Re-read the receipt here: a scan can race with a relabel, deletion or merge.
    from database import conversations as conversations_db

    preview = None
    changed = None
    for conversation_id in dict.fromkeys(conversation_ids):
        conversation_ref = (
            client.collection('users')
            .document(uid)
            .collection(conversations_db.conversations_collection)
            .document(conversation_id)
        )

        @firestore.transactional
        def merge(transaction: Any) -> Optional[Dict[str, Any]]:
            snapshot = ref.get(transaction=transaction)
            raw = conversation_ref.get(transaction=transaction).to_dict() or {}
            if not snapshot.exists or not raw or raw.get('deleted'):
                return None
            person = snapshot.to_dict() or {}
            evidence = preview if not apply and preview is not None else person.get('label_evidence')
            receipt = conversations_db.decode_manual_speaker_assignments(
                uid, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
            )
            segments = conversations_db.decode_transcript_segments_verified(
                uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
            )
            # Only receipt-covered segments prove a manual label. A historical
            # text match with no provenance must not turn into positive evidence.
            covered = [
                s
                for s in segments
                if s.get('id') in (receipt.get('segments') or {})
                or str(s.get('speaker_id')) in (receipt.get('speakers') or {})
            ]
            reviewed = apply_manual_assignments(covered, receipt)
            if not any(
                s.get('person_id') == person_id and not s.get('is_user') and not s.get('speaker_match_source')
                for s in reviewed
            ):
                return None
            ledger = dict(receipt.get('label_evidence') or {})
            prior = ledger.get(person_id)
            kind = None if prior and set(prior.get('kinds', [])) - {AUTO_CORRECTED} else MANUAL_LABELS
            tally, contribution = reconcile_evidence(
                evidence, prior, conversation_id, kind, True, receipt.get('generation', 0), now
            )
            if tally is not None:
                # Receipts have no label timestamp. Preserve the live timestamp, if any.
                tally.pop('last_labeled_at', None)
                if evidence and evidence.get('last_labeled_at'):
                    tally['last_labeled_at'] = evidence['last_labeled_at']
            if apply and contribution != prior:
                ledger[person_id] = contribution
                receipt['label_evidence'] = ledger
                transaction.update(
                    conversation_ref,
                    conversations_db.encode_conversation_for_write(
                        uid, {'manual_speaker_assignments': receipt}, raw.get('data_protection_level', 'standard')
                    ),
                )
            if tally is not None and apply:
                transaction.update(ref, {'label_evidence': tally})
            return tally

        tally = run_transactional(client, merge)
        if tally is not None:
            preview = changed = tally
    return changed
