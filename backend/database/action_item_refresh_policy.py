"""Pure add-only task reconciliation. Receipts remember exact identities after hard deletion.

Unique segment anchors can suppress reworded generated tasks. An edited task is
never overwritten; its prior normalized key remains an alias once enrolled.
Missing receipt targets are deletion intent, not
permission to recreate. Pre-enrollment hard deletes/edits cannot be reconstructed.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from config.action_item_identity_key import identity_key
from config.action_item_similarity import guarded_tokens_match, near_duplicate_tokens, substitution_tokens_match, tokens

LIMIT = 200
RECEIPT = 'action_item_refresh'


def key(value: object) -> str:
    normalized = identity_key(value)
    return sha256(normalized.encode()).hexdigest() if normalized else ''


def _segment_ids(row: dict) -> frozenset[str]:
    for ref in row.get('provenance') or []:
        if ref.get('kind') == 'conversation':
            return frozenset(s for s in ref.get('transcript_segment_ids') or [] if isinstance(s, str) and s)
    return frozenset()


def enroll(ledger: dict[str, list[str]], rows: dict[str, dict]) -> None:
    for task_id, row in sorted(rows.items()):
        identity = key(row.get('description'))
        if identity and task_id not in ledger.setdefault(identity, []):
            ledger[identity].append(task_id)


def protected_donor(row: dict, aliases: list[str]) -> bool:
    """Keep manual, edited, linked or curated rows. Uncertain historical edits stay kept."""
    if row.get('source') not in (None, 'legacy', 'conversation') or len(aliases) > 1:
        return True
    if any(
        row.get(field)
        for field in (
            'folder_id',
            'manual_assignment',
            'apple_reminder_id',
            'external_task_id',
            'goal_id',
            'workstream_id',
            'recurrence_rule',
            'priority',
        )
    ):
        return True
    created, updated = row.get('created_at'), row.get('updated_at')
    # All user updates stamp updated_at, including pre-receipt edits. Export and
    # completion updates can also do so: retain these ambiguous rows conservatively.
    return not created or not updated or updated != created


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
    counts = dict(
        kept_existing=len(rows),
        added_new=0,
        transferred_from_donor=0,
        skipped_duplicate=0,
        disabled=0,
        skipped_anchor_duplicate=0,
    )
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
            # Only ordinary unedited generated duplicates can be hidden. Never
            # delete a user-created/edited task or discard a separate external link.
            if matches:
                target_id = matches[0]
                patch['refresh_duplicate_of'] = target_id
                target = rows.get(target_id) or donor_rows.get(target_id) or {}
                if not protected_donor(row, aliases):
                    patch['deleted'] = True
                if (
                    (row.get('completed') or row.get('status') == 'completed')
                    and target
                    and key(target.get('description')) == identity
                    and not (
                        target.get('deleted')
                        or target.get('status') in ('cancelled', 'superseded')
                        or target.get('completed')
                        or target.get('status') == 'completed'
                    )
                ):
                    updates.setdefault(target_id, {}).update(
                        completed=True, status='completed', completed_at=row.get('completed_at')
                    )
                counts['skipped_duplicate'] += 1
            else:
                enroll(available, {task_id: row})
            updates.setdefault(task_id, {}).update(patch)
            counts['transferred_from_donor'] += 1
    else:
        existing_tokens = {task_id: tokens(row.get('description')) for task_id, row in rows.items()}
        # Reserve text matches across the whole extraction before trying anchors,
        # including items later in the list. One row must not absorb two tasks.
        matched = set()
        for item in items:
            identity = key(item.get('description'))
            if ledger.get(identity):
                matched.update(ledger[identity])
            else:
                words = tokens(item.get('description'))
                matched.update(tid for tid, prior in existing_tokens.items() if near_duplicate_tokens(words, prior))
        segments = {
            task_id: _segment_ids(row)
            for task_id, row in rows.items()
            if not row.get('deleted') and not protected_donor(row, [])
        }
        for item in items:
            identity = key(item.get('description'))
            if not identity:
                raise ValueError('refresh requires a nonempty exact task identity')
            if ledger.get(identity):
                counts['skipped_duplicate'] += 1
                continue
            candidate_tokens = tokens(item.get('description'))
            match = next(
                (
                    task_id
                    for task_id, words in existing_tokens.items()
                    if near_duplicate_tokens(candidate_tokens, words)
                ),
                None,
            )
            if match is not None:
                ledger[identity] = [match]  # Enroll this rewording as an edit/delete suppressor.
                matched.add(match)
                counts['skipped_duplicate'] += 1
                continue
            candidate_segments = _segment_ids(item)
            anchors = [
                task_id
                for task_id, prior_segments in segments.items()
                if task_id not in matched
                and candidate_segments & prior_segments
                and len(candidate_tokens & existing_tokens[task_id]) >= 3
                and guarded_tokens_match(candidate_tokens, existing_tokens[task_id])
                and substitution_tokens_match(candidate_tokens, existing_tokens[task_id])
            ]
            if len(anchors) == 1:
                ledger[identity] = anchors  # Retain the original wording and remember this alias.
                matched.add(anchors[0])
                counts['skipped_duplicate'] += 1
                counts['skipped_anchor_duplicate'] += 1
                continue
            ordinal = 0
            task_id = 'refresh-' + sha256(f'{conversation_id}:{generation}:{identity}:{ordinal}'.encode()).hexdigest()
            ledger[identity] = [task_id]
            creates[task_id] = {**item, 'account_generation': generation, 'refresh_delivery': 'pending'}
            existing_tokens[task_id] = candidate_tokens
            counts['added_new'] += 1
    if (
        len(ledger) > LIMIT
        or sum(map(len, ledger.values())) > LIMIT * 2
        or len(rows.keys() | creates.keys() | updates.keys()) > LIMIT
    ):
        raise ValueError('refresh task budget exceeded')
    return {'generation': generation, 'keys': ledger}, creates, updates, counts
