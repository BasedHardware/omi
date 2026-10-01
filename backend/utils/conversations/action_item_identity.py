"""Keep a conversation's task identity across the reprocess replace.

``process_conversation._write_action_items`` replaces every task a conversation wrote
before with the new extraction. It used to recreate all of them under fresh ids, which
dropped the ``exported`` marker that task-app delivery keys on, so every reprocess
(smart-merge survivor refresh, user reprocess, sync update, server recovery) offered
unchanged tasks to the user's Todoist/Asana/ClickUp/Google Tasks again and pushed them
to Apple Reminders again.

Identity rule. A new item is the same task as a prior row only when both belong to the
same conversation and their ``identity_key`` values are equal and non-empty. The key is
an exact canonical form of the description: Unicode width/typography normalized,
ordinary text case-folded, zero-width space/BOM removed, sentence punctuation and
whitespace collapsed. Internal punctuation,
numeric signs and Unicode joiners are retained because they can change meaning. Numeric
compatibility symbols (e.g. exponents) and case in code-bearing descriptions are retained.
Nothing fuzzy: no embeddings, no similarity threshold, no cross-conversation lookup. Equal keys
pair one-to-one, so two identical tasks in one conversation keep two ids; a prior row
with the same due instant is preferred, then an exported row, then the oldest. A kept
row lends the new row its document id and its export marker (``CARRIED_FIELDS``);
every other field is the new extraction, exactly as before. A reworded task does not
match and is delivered as new. A prior row nothing matches is deleted, as before, and
its copy in the task app is left alone, as before.

Ordering. When prior rows exist, delivery is queued only after the task vectors are
written, so an attempt that fails there queues nothing for its retry to repeat.
This is best-effort export: overlapping deliveries and an unconfirmed provider create
still need provider-side idempotency. First processing keeps today's order and arguments.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from config.action_item_identity import action_item_identity_preserve_enabled
from utils.metrics import OMI_ACTION_ITEM_IDENTITY_TOTAL

logger = logging.getLogger(__name__)

# The export marker written by task delivery (utils/task_sync.py) and the Apple
# Reminders client callback. Nothing else on the prior row is carried forward.
CARRIED_FIELDS = ('exported', 'export_platform', 'export_date', 'apple_reminder_id')

REUSED = 'reused_identity'
NEW = 'new'
SKIPPED_EXPORTED = 'skipped_already_exported'
DISABLED = 'disabled'
OUTCOMES = (REUSED, NEW, SKIPPED_EXPORTED, DISABLED)


def identity_key(description: object) -> str:
    """Exact canonical form of a task description; empty means "never the same task"."""
    if not isinstance(description, str):
        return ''
    # NFKC turns x² into x2 and Ⅳ into IV. Keep numeric compatibility symbols;
    # width folding (including full-width digits) and composed accents are safe.
    normalized = unicodedata.normalize(
        'NFC',
        ''.join(
            char if unicodedata.category(char) in ('No', 'Nl') else unicodedata.normalize('NFKC', char)
            for char in description
        ),
    )
    words = normalized.split()
    code_bearing = any(
        word.casefold().strip('.,:;!?') in {'code', 'password', 'token', 'identifier', 'secret'} for word in words
    )
    code_bearing = code_bearing or any(
        any(char.isalpha() for char in word) and any(char.isnumeric() for char in word) for word in words
    )
    folded = unicodedata.normalize('NFC', normalized if code_bearing else normalized.casefold())
    chars: List[str] = []
    for index, char in enumerate(folded):
        category = unicodedata.category(char)
        if char in ('\u200b', '\ufeff'):
            continue
        # Curly apostrophes are typography; signs, decimal separators, identifiers
        # and emoji/script joiners are content. Never erase all Unicode punctuation.
        if char in ('\u2018', '\u2019'):
            char = "'"
        next_char = folded[index + 1 : index + 2]
        previous_char = folded[index - 1 : index] if index else ''
        sentence_separator = char in '.,!?;' and (not next_char or next_char.isspace() or next_char in '.,!?;')
        if sentence_separator and not previous_char.isdigit():
            char = ' '
        chars.append(' ' if category == 'Cc' else char)
    key = ' '.join(''.join(chars).split())
    return key if any(not unicodedata.category(char).startswith(('P', 'Z', 'C')) for char in key) else ''


def _instant(value: object) -> Optional[int]:
    """UTC microseconds for a datetime or ISO string; naive values are UTC, as on write."""
    if isinstance(value, str) and value:
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        return round(value.timestamp() * 1_000_000)
    except (OverflowError, OSError, ValueError):
        return None


def _preference(row: Mapping[str, Any]) -> tuple[bool, bool, int, str]:
    created = _instant(row.get('created_at'))
    return (not row.get('exported'), created is None, created or 0, str(row.get('id')))


@dataclass(frozen=True)
class ReplacementPlan:
    """What the replace writes, under which ids, and which rows it delivers."""

    items: List[Dict[str, Any]]
    document_ids: Optional[List[Optional[str]]]
    outcomes: List[str]
    # Kept prior id -> whether that prior row had a client reminder armed.
    kept_reminders: Dict[str, bool]
    deliver_after_persist: bool

    @property
    def reused_ids(self) -> frozenset[str]:
        return frozenset(self.kept_reminders)

    def create_kwargs(self) -> Dict[str, Any]:
        return {} if self.document_ids is None else {'document_ids': self.document_ids}

    def deliverable(self, created_items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Created rows minus those the user's task app already holds."""
        return [item for item, outcome in zip(created_items, self.outcomes) if outcome != SKIPPED_EXPORTED]

    def reconcile_kept_reminder(self, uid: str, task_id: str, action_item: Any, reconcile: Callable[..., Any]) -> bool:
        """Reschedule a kept id's reminder with one update message; True when ``task_id`` was kept.

        A kept id must not get the replaced-row cancel followed by a fresh schedule: FCM
        does not order the two, and a late cancel would silence the kept reminder. The
        update message cancels and reschedules on the client, in order.
        """
        if task_id not in self.kept_reminders:
            return False
        if action_item.due_at or self.kept_reminders[task_id]:
            try:
                reconcile(
                    user_id=uid,
                    action_item_id=task_id,
                    description=action_item.description,
                    completed=bool(action_item.completed),
                    due_at=action_item.due_at,
                )
            except Exception as error:
                # The rows are already written; a reminder send must never cost the extraction.
                logger.error('event=action_item_identity stage=reminder exception_type=%s', type(error).__name__)
        return True


def plan_replacement(
    conversation_id: str,
    items: Sequence[Dict[str, Any]],
    prior_rows: Sequence[Mapping[str, Any]],
) -> ReplacementPlan:
    """Pair the new extraction with this conversation's prior rows (see module docstring)."""
    new_items = list(items)
    if not action_item_identity_preserve_enabled():
        return _emit(ReplacementPlan(new_items, None, [DISABLED] * len(new_items), {}, False), len(prior_rows))

    pools: Dict[str, List[Mapping[str, Any]]] = {}
    for row in prior_rows:
        row_id, key = row.get('id'), identity_key(row.get('description'))
        if key and isinstance(row_id, str) and row_id and row.get('conversation_id') == conversation_id:
            pools.setdefault(key, []).append(row)
    for pool in pools.values():
        pool.sort(key=_preference)

    keys = [identity_key(item.get('description')) for item in new_items]
    matches: List[Optional[Mapping[str, Any]]] = [None] * len(new_items)
    for same_due_only in (True, False):
        for index, (item, key) in enumerate(zip(new_items, keys)):
            if not key or matches[index] is not None:
                continue
            pool = pools.get(key, [])
            for position, row in enumerate(pool):
                if not same_due_only or _instant(row.get('due_at')) == _instant(item.get('due_at')):
                    matches[index] = pool.pop(position)
                    break

    planned: List[Dict[str, Any]] = []
    document_ids: List[Optional[str]] = []
    outcomes: List[str] = []
    kept: Dict[str, bool] = {}
    for item, row in zip(new_items, matches):
        if row is None:
            planned.append(item)
            document_ids.append(None)
            outcomes.append(NEW)
            continue
        row_id = str(row['id'])
        planned.append({**item, **{name: row[name] for name in CARRIED_FIELDS if row.get(name) is not None}})
        document_ids.append(row_id)
        kept[row_id] = bool(row.get('due_at')) and not row.get('completed')
        outcomes.append(SKIPPED_EXPORTED if row.get('exported') else REUSED)
    plan = ReplacementPlan(planned, document_ids if kept else None, outcomes, kept, bool(prior_rows))
    return _emit(plan, len(prior_rows))


def _emit(plan: ReplacementPlan, prior_rows: int) -> ReplacementPlan:
    """One bounded metric per outcome and one log line per replace; never ids or task text."""
    counts = {outcome: plan.outcomes.count(outcome) for outcome in OUTCOMES}
    for outcome, count in counts.items():
        if count:
            try:
                OMI_ACTION_ITEM_IDENTITY_TOTAL.labels(outcome=outcome).inc(count)
            except Exception:
                pass
    try:
        logger.info(
            'event=action_item_identity reused_identity=%d new=%d skipped_already_exported=%d disabled=%d '
            'prior_rows=%d deliver_after_persist=%s',
            counts[REUSED],
            counts[NEW],
            counts[SKIPPED_EXPORTED],
            counts[DISABLED],
            prior_rows,
            plan.deliver_after_persist,
        )
    except Exception:
        pass
    return plan
