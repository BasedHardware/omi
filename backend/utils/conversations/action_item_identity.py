"""Keep a conversation's task identity across the reprocess replace.

``process_conversation._write_action_items`` replaces every task a conversation wrote
before with the new extraction. It used to recreate all of them under fresh ids, which
dropped the ``exported`` marker that task-app delivery keys on, so every reprocess
(smart-merge survivor refresh, user reprocess, sync update, server recovery) offered
unchanged tasks to the user's Todoist/Asana/ClickUp/Google Tasks again.

Apple Reminders is deliberately NOT covered: a reprocess still gives an Apple-linked or pending
task a fresh id and pushes a second reminder, as before. Its client sync is
last-writer-wins on Omi ``updated_at`` vs the reminder's ``lastModifiedDate``
(``app/lib/services/integrations/apple_reminders_sync_service.dart:163-191``); the
replaced row has no ``updated_at`` edit history, so keeping the link would let the
extraction overwrite a title/due edit the user made in Reminders. A duplicate keeps
that edited copy; a kept link could silently lose it.

Identity rule. A new item is the same task as a prior row only when both belong to the
same conversation, the prior row is not Apple-linked, and their ``identity_key`` values
are equal and non-empty. The key is
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

An unexpected planner exception falls back to the kill-switch plan (fresh ids, every
row delivered, today's order), so the planner can never cost a conversation its tasks.

Anchor shadow (measurement only). The log line also counts how many prior rows the exact
rule left unmatched could be paired with an unmatched new item by stored structural
provenance: the transcript segment ids each row cites for THIS conversation
(``provenance[].transcript_segment_ids``, written by ``conversation_capture``). A pair
needs at least ``ANCHOR_MIN_SHARED_SEGMENTS`` shared segment ids and must be one-to-one:
the old row overlaps exactly one unmatched new item and that item overlaps exactly one
unmatched old row. Every other overlap is ambiguous and never a pair. This compares
record provenance, not task text, and its result is only logged: the plan, writes,
deletions, deliveries and reminders are computed before it and never read it. Any
exception in it is logged as ``shadow=error`` and swallowed; its kill switch is
``ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENABLED``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, cast

from config.action_item_identity_key import identity_key
from config.action_item_identity import (
    action_item_identity_anchor_shadow_enabled,
    action_item_identity_preserve_enabled,
)
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.metrics import OMI_ACTION_ITEM_IDENTITY_TOTAL
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# The cloud export marker written by task delivery (utils/task_sync.py). Nothing else
# on the prior row is carried forward; Apple-linked rows are never matched (_apple_linked).
CARRIED_FIELDS = ('exported', 'export_platform', 'export_date')

REUSED = 'reused_identity'
NEW = 'new'
SKIPPED_EXPORTED = 'skipped_already_exported'
DISABLED = 'disabled'
OUTCOMES = (REUSED, NEW, SKIPPED_EXPORTED, DISABLED)

# Anchor shadow: shared transcript segment ids an (old row, new item) pair needs. One is
# the simplest structural rule; the one-to-one requirement, not a threshold, rejects splits.
ANCHOR_MIN_SHARED_SEGMENTS = 1
# The one field the shadow adds to the prior-row read (same query, no extra document).
ANCHOR_READ_FIELDS = ('provenance',)
SHADOW_FIELDS = (
    'unmatched_prior',
    'unmatched_prior_exported',
    'unmatched_prior_ineligible',
    'prior_without_anchor',
    'unmatched_new',
    'new_without_anchor',
    'anchor_pairs',
    'anchor_ambiguous',
)
_SHADOW_FORMAT = ' '.join(f'{name}=%d' for name in SHADOW_FIELDS)
SHADOW_STATES = {True: 'ok', False: 'disabled'}  # plus 'error'
# Reject an oversized measurement rather than sampling and reporting false pairs.
ANCHOR_MAX_ROWS = 512
ANCHOR_MAX_COMPARISONS = 65_536
ANCHOR_MAX_PROVENANCE_ENTRIES = 64
ANCHOR_MAX_SEGMENTS_PER_ROW = 512
ANCHOR_MAX_TOTAL_SEGMENTS = 65_536
ANCHOR_MAX_SEGMENT_ID_LENGTH = 256
_MAX_LOG_COUNT = 2**31 - 1
_SHADOW_ERROR_NAMES = frozenset({'RuntimeError', 'TypeError', 'ValueError', 'AssertionError', 'KeyError'})


class AnchorShadowLimitExceeded(Exception):
    """Measurement exceeded its work budget; the completed write plan is still valid."""


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


def _eligible(row: Mapping[str, Any], conversation_id: str) -> bool:
    """A prior row the identity rule may ever lend its id: this conversation's, id-bearing, not Apple-linked."""
    row_id = row.get('id')
    return (
        isinstance(row_id, str)
        and bool(row_id)
        and row.get('conversation_id') == conversation_id
        and not _apple_linked(row)
    )


def _apple_linked(row: Mapping[str, Any]) -> bool:
    """An Apple link or pending push whose delayed callback must not link a replacement row."""
    return (
        bool(row.get('apple_reminder_id'))
        or row.get('export_platform') == 'apple_reminders'
        or bool(row.get('sync_requested'))
    )


def _unchanged(items: Sequence[Dict[str, Any]]) -> ReplacementPlan:
    """The kill-switch plan: today's replace, fresh ids, every row delivered before the vectors."""
    return ReplacementPlan(list(items), None, [DISABLED] * len(items), {}, False)


def prior_read_kwargs() -> Dict[str, Any]:
    """Extra keyword arguments for the prior-row read: the anchor field, only while the shadow runs."""
    try:
        return {'extra_fields': ANCHOR_READ_FIELDS} if action_item_identity_anchor_shadow_enabled() else {}
    except Exception:
        return {}  # fail-open: the read stays exactly today's, and _shadow logs the error


def plan_replacement(
    conversation_id: str,
    items: Sequence[Dict[str, Any]],
    prior_rows: Sequence[Mapping[str, Any]],
    trigger: object = None,
) -> ReplacementPlan:
    """Pair the new extraction with this conversation's prior rows (see module docstring).

    Runs on every task write, first processing included, so it never raises: an
    unexpected error falls back to the kill-switch plan. ``trigger`` is only logged.
    """
    try:
        return _plan(conversation_id, items, prior_rows, trigger)
    except Exception as error:
        try:
            logger.error('event=action_item_identity outcome=planner_error cause=%s', type(error).__name__)
            record_fallback(
                component='other', from_mode='identity_preserve', to_mode='recreate', reason='other', outcome='degraded'
            )
        except Exception:
            pass
        return _unchanged(items)


def _plan(
    conversation_id: str,
    items: Sequence[Dict[str, Any]],
    prior_rows: Sequence[Mapping[str, Any]],
    trigger: object = None,
) -> ReplacementPlan:
    new_items = list(items)
    if not action_item_identity_preserve_enabled():
        plan = _unchanged(new_items)
        return _emit(plan, len(prior_rows), _shadow(conversation_id, new_items, prior_rows, plan, trigger))

    pools: Dict[str, List[Mapping[str, Any]]] = {}
    for row in prior_rows:
        key = identity_key(row.get('description'))
        # Apple-linked rows keep today's fresh id + second push: the Reminders sync is
        # last-writer-wins on updated_at (apple_reminders_sync_service.dart:163-191), so a
        # kept link would let this extraction overwrite the user's edit made in Reminders.
        if key and _eligible(row, conversation_id):
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
    return _emit(plan, len(prior_rows), _shadow(conversation_id, new_items, prior_rows, plan, trigger))


def _segment_anchor(row: Mapping[str, Any], conversation_id: str) -> frozenset[str]:
    """Transcript segment ids this row's provenance cites for this conversation; empty means no anchor."""
    anchor: set[str] = set()
    provenance = row.get('provenance')
    if not isinstance(provenance, (list, tuple)):
        return frozenset()
    if len(provenance) > ANCHOR_MAX_PROVENANCE_ENTRIES:
        raise AnchorShadowLimitExceeded()
    segment_count = 0
    for entry in provenance:
        evidence: Mapping[str, Any] = cast(Mapping[str, Any], entry) if isinstance(entry, Mapping) else {}
        if evidence.get('kind') == 'conversation' and evidence.get('id') == conversation_id:
            segments = evidence.get('transcript_segment_ids')
            if not isinstance(segments, (list, tuple)):
                continue
            segment_count += len(segments)
            if segment_count > ANCHOR_MAX_SEGMENTS_PER_ROW:
                raise AnchorShadowLimitExceeded()
            if any(isinstance(seg, str) and len(seg) > ANCHOR_MAX_SEGMENT_ID_LENGTH for seg in segments):
                raise AnchorShadowLimitExceeded()
            anchor.update(seg for seg in segments if isinstance(seg, str) and seg)
    return frozenset(anchor)


def _anchor_counts(
    conversation_id: str,
    items: Sequence[Mapping[str, Any]],
    prior_rows: Sequence[Mapping[str, Any]],
    plan: ReplacementPlan,
    enabled: bool,
) -> Dict[str, int]:
    """Shadow counts over the rows the exact rule left unmatched. Reads its inputs; writes nothing."""
    if enabled and max(len(prior_rows), len(items)) > ANCHOR_MAX_ROWS:
        raise AnchorShadowLimitExceeded()
    reused_ids = plan.reused_ids
    unmatched_prior = [row for row in prior_rows if row.get('id') not in reused_ids]
    exact = (REUSED, SKIPPED_EXPORTED)
    unmatched_new = [item for item, outcome in zip(items, plan.outcomes) if outcome not in exact]
    eligible = [row for row in unmatched_prior if _eligible(row, conversation_id)]
    counts: Dict[str, int] = dict.fromkeys(SHADOW_FIELDS, 0)
    counts.update(
        unmatched_prior=len(unmatched_prior),
        unmatched_prior_exported=sum(1 for row in unmatched_prior if row.get('exported')),
        unmatched_prior_ineligible=len(unmatched_prior) - len(eligible),
        unmatched_new=len(unmatched_new),
    )
    if not enabled:
        return {name: min(value, _MAX_LOG_COUNT) for name, value in counts.items()}
    if len(eligible) * len(unmatched_new) > ANCHOR_MAX_COMPARISONS:
        raise AnchorShadowLimitExceeded()
    old = [_segment_anchor(row, conversation_id) for row in eligible]
    new = [_segment_anchor(item, conversation_id) for item in unmatched_new]
    if sum(map(len, old)) + sum(map(len, new)) > ANCHOR_MAX_TOTAL_SEGMENTS:
        raise AnchorShadowLimitExceeded()
    # Degree counts avoid storing the graph and the former cubic dense-graph scan.
    old_degree, new_degree = [0] * len(old), [0] * len(new)
    sole_new = [0] * len(old)
    for i, a in enumerate(old):
        for j, b in enumerate(new):
            if a and b and len(a & b) >= ANCHOR_MIN_SHARED_SEGMENTS:
                old_degree[i] += 1
                new_degree[j] += 1
                sole_new[i] = j
    pairs = sum(1 for i, degree in enumerate(old_degree) if degree == 1 and new_degree[sole_new[i]] == 1)
    counts.update(
        prior_without_anchor=sum(1 for a in old if not a),
        new_without_anchor=sum(1 for b in new if not b),
        anchor_pairs=pairs,
        anchor_ambiguous=sum(1 for degree in old_degree if degree) - pairs,
    )
    return counts


def _shadow(
    conversation_id: str,
    items: Sequence[Mapping[str, Any]],
    prior_rows: Sequence[Mapping[str, Any]],
    plan: ReplacementPlan,
    trigger: object,
) -> Dict[str, Any]:
    """Bounded shadow log fields; fail-open, so the shadow can never touch the write path."""
    fields: Dict[str, Any] = {'trigger': 'unknown', 'shadow': 'error', 'shadow_error': 'none'}
    try:
        if isinstance(trigger, ProcessingTrigger):
            fields['trigger'] = trigger.value
        enabled = action_item_identity_anchor_shadow_enabled()
        fields.update(_anchor_counts(conversation_id, items, prior_rows, plan, enabled), shadow=SHADOW_STATES[enabled])
    except Exception as error:
        name = type(error).__name__
        error_label = (
            'budget_exceeded'
            if isinstance(error, AnchorShadowLimitExceeded)
            else (name if name in _SHADOW_ERROR_NAMES else 'Exception')
        )
        fields.update(dict.fromkeys(SHADOW_FIELDS, 0), shadow='error', shadow_error=error_label)
    return fields


def _emit(plan: ReplacementPlan, prior_rows: int, shadow: Mapping[str, Any]) -> ReplacementPlan:
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
            'prior_rows=%d deliver_after_persist=%s trigger=%s shadow=%s shadow_error=%s ' + _SHADOW_FORMAT,
            counts[REUSED],
            counts[NEW],
            counts[SKIPPED_EXPORTED],
            counts[DISABLED],
            prior_rows,
            plan.deliver_after_persist,
            shadow['trigger'],
            shadow['shadow'],
            shadow['shadow_error'],
            *(shadow[name] for name in SHADOW_FIELDS),
        )
    except Exception:
        pass
    return plan
