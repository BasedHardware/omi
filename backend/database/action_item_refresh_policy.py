"""Pure add-only task reconciliation. Receipts remember exact identities after hard deletion.

No anchor matching. An edited task is never overwritten; its prior normalized key
remains an alias once enrolled. Missing receipt targets are deletion intent, not
permission to recreate. Pre-enrollment hard deletes/edits cannot be reconstructed.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from config.action_item_identity_key import identity_key

LIMIT = 200
RECEIPT = 'action_item_refresh'


def key(value: object) -> str:
    normalized = identity_key(value)
    return sha256(normalized.encode()).hexdigest() if normalized else ''


def enroll(ledger: dict[str, list[str]], rows: dict[str, dict]) -> None:
    for task_id, row in sorted(rows.items()):
        identity = key(row.get('description'))
        if identity and task_id not in ledger.setdefault(identity, []):
            ledger[identity].append(task_id)


def plan(
    conversation_id: str,
    rows: dict[str, dict],
    items: list[dict],
    receipt: dict,
    generation: int,
    *,
    donor_rows: dict[str, dict] | None = None,
    donor_receipt: dict | None = None,
) -> tuple[dict, dict[str, dict], dict[str, dict], dict[str, int]]:
    """Return receipt, creates, partial updates and bounded counters (all reads supplied)."""
    ledger = deepcopy(receipt.get('keys') or {}) if receipt.get('generation', generation) == generation else {}
    enroll(ledger, rows)
    counts = dict(kept_existing=len(rows), added_new=0, transferred_from_donor=0, skipped_duplicate=0, disabled=0)
    creates: dict[str, dict] = {}
    updates: dict[str, dict] = {}
    if donor_rows is not None:
        available = deepcopy(ledger)  # Includes edited aliases and structurally deleted target ids.
        donor_keys = deepcopy((donor_receipt or {}).get('keys') or {})
        enroll(donor_keys, donor_rows)
        # Preserve receipts for already deleted donors, too. They remain suppressors.
        for identity, task_ids in donor_keys.items():
            ledger.setdefault(identity, []).extend(i for i in task_ids if i not in ledger.get(identity, []))
        for task_id, row in sorted(donor_rows.items()):
            identity = key(row.get('description'))
            aliases = [identity, *(k for k, ids in donor_keys.items() if task_id in ids and k != identity)]
            matches = next((available[k] for k in aliases if available.get(k)), [])
            patch: dict[str, Any] = {'conversation_id': conversation_id}
            # Transfer is never a new-task delivery. Retire even a donor's
            # pre-claim retry marker before the survivor can observe it.
            if row.get('refresh_delivery') == 'pending':
                patch['refresh_delivery'] = 'transferred'
            # Retain original evidence and every user/external field on the donor.
            # Exact text does not prove two live rows have interchangeable user
            # state. Keep both visible; only user-deleted targets suppress a donor.
            if matches:
                target_id = matches[0]
                patch['refresh_duplicate_of'] = target_id
                if target_id not in rows or rows[target_id].get('deleted'):
                    patch['deleted'] = True
                for ids in available.values():
                    if target_id in ids:
                        ids.remove(target_id)
                counts['skipped_duplicate'] += 1
            updates[task_id] = patch
            counts['transferred_from_donor'] += 1
    else:
        occurrences: dict[str, int] = {}
        for item in items:
            identity = key(item.get('description'))
            if not identity:
                raise ValueError('refresh requires a nonempty exact task identity')
            ordinal = occurrences.get(identity, 0)
            occurrences[identity] = ordinal + 1
            slots = ledger.setdefault(identity, [])
            if ordinal < len(slots):
                counts['skipped_duplicate'] += 1
                continue
            task_id = 'refresh-' + sha256(f'{conversation_id}:{generation}:{identity}:{ordinal}'.encode()).hexdigest()
            slots.append(task_id)
            creates[task_id] = {**item, 'account_generation': generation, 'refresh_delivery': 'pending'}
            counts['added_new'] += 1
    if (
        len(ledger) > LIMIT
        or sum(map(len, ledger.values())) > LIMIT * 2
        or len(rows) + len(creates) + len(updates) > LIMIT
    ):
        raise ValueError('refresh task budget exceeded')
    return {'generation': generation, 'keys': ledger}, creates, updates, counts
