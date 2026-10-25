"""The open-loops daily pass: one structured call per user per local day.

A sibling step of the daily recap job: when the recap cohort processes a
user's completed local day, this pass is dispatched after the recap's own
work is fully done — push, backfill and webhook — onto a dedicated executor
with its own deadline (see ``utils.other.notifications``), so a slow pass can
never spend recap budget, delay the webhook or defer another user's recap.
It renders the day with the recap's own deserializer, char budget and
renderer — the same *view* of the day, though not a byte-identical shared
prompt prefix (the recap's system prompt and eligibility filter differ, so
no prompt-cache prefix is actually shared) — then makes exactly one model
call (feature key ``open_loop_daily``, usage-tracked) that:

1. decides statuses for carried loops, open tasks and today's extractions —
   only loops with signal come back;
2. resolves loops the day's evidence shows are done;
3. proposes up to three ranked surface candidates with a 1–5 value score.

Deterministic post-processing owns everything the UI depends on: task-aware
dedupe (link, never drop; only a model-asserted ``from_task_id`` link is
strong enough for Done to complete a task), loop-to-loop dedupe (merge,
task-linked survivor wins), the two-day re-ask cooldown, snoozes, expiry and
the three-slot / value-≥3 ranking. Terminal loops never come back: they are
excluded from update matching and merging, and their follow-up can open a
NEW loop only after ``store.REMENTION_COOLDOWN_DAYS``. Cards render through
``utils.open_loops.card`` and persist per local day; nothing is served to
clients in this PR — PR 3 adds the Review source and the mobile UI through
``utils.open_loops.service``.

Fail-open contract: this pass may raise; the dispatcher catches every
failure, logs it and moves on. A day whose pass failed simply has no cards.

Cost guards: ``OPEN_LOOPS_ENABLED`` off skips the pass and writes nothing; a
user with no extractions and no open loops, or with no conversations and no
due-soon loop, skips the model call; an atomic per-day claim
(``database.open_loops.claim_daily_pass``) is taken **before** the model
call, so retried recap ticks, abandoned threads and the locked-retry path
never double-spend — and the per-day cards document still marks the day as
run.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from config.open_loops import open_loops_enabled
import database.action_items as action_items_db
import database.conversations as conversations_db
import database.daily_summaries as daily_summaries_db
import database.open_loops as open_loops_db
from utils.conversations.factory import deserialize_conversations
from utils.conversations.media_consumers import eligible_conversations
from utils.conversations.render import conversations_to_string
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
from utils.other.daily_summary_budget import DEFAULT_MAX_HISTORY_CHARS, select_conversations_within_budget
from utils.open_loops.card import build_review_card, llm_polisher
from utils.open_loops.prompts import OPEN_LOOPS_DAILY_RULES
from utils.open_loops import store

logger = logging.getLogger(__name__)

RAN = 'ran'
SKIPPED_DISABLED = 'skipped_disabled'
SKIPPED_ALREADY_RAN = 'skipped_already_ran'
SKIPPED_CLAIMED = 'skipped_claimed'
SKIPPED_NO_SIGNAL = 'skipped_no_signal'

# The model may decide exactly these statuses (the offline-validated set).
DECIDABLE_STATUSES = frozenset({'opened', 'progressing', 'stale', 'due_soon', 'resolved'})


def _zone(tz: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(tz) if tz else ZoneInfo('UTC')
    except Exception:
        return ZoneInfo('UTC')


def local_today(tz: Optional[str], now: Optional[datetime] = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(_zone(tz)).date()


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def parse_model_output(content: Any) -> Optional[dict[str, Any]]:
    """Lenient JSON parse of the daily pass output (code fences tolerated)."""
    text = str(getattr(content, 'content', content) or '').strip()
    if text.startswith('```'):
        text = text.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def eligible_day_rows(uid: str, rows: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """The day's conversation rows the pass may read.

    Merge donors (``sync_merged_into`` — their content lives in the merge
    target), locked and discarded rows, and content excluded from derived
    consumers (the recap's own eligibility rule) never contribute loops.
    """
    rows = [row for row in rows if not row.get('sync_merged_into')]
    rows = [row for row in rows if not row.get('is_locked') and not row.get('discarded')]
    return list(eligible_conversations(uid, rows))


def _row_title(row: Mapping[str, Any]) -> str:
    structured = row.get('structured')
    if isinstance(structured, Mapping):
        return str(structured.get('title') or '')
    return str(row.get('title') or '')


def day_extractions(uid: str, rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Per-conversation extraction entries for the prompt input."""
    entries: List[Dict[str, Any]] = []
    for row in rows:
        payload = conversations_db.get_open_loop_extractions(uid, dict(row))
        if not payload:
            continue
        entries.append(
            {
                'conversation_id': row.get('id'),
                'title': _row_title(row),
                'delegated_by_user': payload.get('delegated_by_user') or [],
                'commitments_by_others': payload.get('commitments_by_others') or [],
                'observed_issue_or_blocker': payload.get('observed_issue_or_blocker'),
            }
        )
    return entries


def render_day(rows: Sequence[Mapping[str, Any]]) -> str:
    """The day rendered as the recap renders it: same deserializer, the recap's
    own char budget over whole conversations, then the same renderer."""
    conversations = deserialize_conversations([dict(row) for row in rows])
    bounded = select_conversations_within_budget(conversations, DEFAULT_MAX_HISTORY_CHARS)
    return conversations_to_string(bounded.conversations)


def open_tasks_view(uid: str, today: date) -> List[Dict[str, Any]]:
    """The owner's open tasks with created/due dates and age, capped."""
    items = action_items_db.get_action_items(uid, completed=False) or []
    view: List[Dict[str, Any]] = []
    for item in items[: store.OPEN_TASKS_PROMPT_CAP]:
        created = item.get('created_at')
        created_day = created.date() if created is not None and hasattr(created, 'date') else today
        view.append(
            {
                'task_id': item.get('id'),
                'title': item.get('description') or item.get('title'),
                'created_at': _iso(created),
                'age_days': max(0, (today - created_day).days) if created else None,
                'due_at': _iso(item.get('due_at')),
            }
        )
    return view


def day_summary_view(uid: str, date_str: str) -> Optional[Dict[str, Any]]:
    summary = daily_summaries_db.get_daily_summary_by_date(uid, date_str)
    if not summary:
        return None
    return {'headline': summary.get('headline'), 'overview': str(summary.get('overview') or '')[:400] or None}


def _source_fields(
    entry: Mapping[str, Any], conversation_meta: Mapping[str, Mapping[str, Any]], target: Optional[Mapping[str, Any]]
) -> Dict[str, Any]:
    ids = [str(i) for i in (entry.get('source_conversation_ids') or []) if i]
    meta = next((conversation_meta[i] for i in ids if i in conversation_meta), None)
    merged_ids = list((target or {}).get('source_conversation_ids') or [])
    for loop_id in ids:
        if loop_id not in merged_ids:
            merged_ids.append(loop_id)
    return {
        'source_conversation_ids': merged_ids[:10],
        'source_title': (meta or {}).get('title') or (target or {}).get('source_title'),
        'source_started_at': (meta or {}).get('started_at') or (target or {}).get('source_started_at'),
    }


def ingest_model_loops(
    model_loops: Sequence[Any],
    existing: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
    *,
    today: date,
    conversation_meta: Mapping[str, Mapping[str, Any]],
    now: datetime,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str]]:
    """Apply the model's status decisions to the store.

    Returns ``(loop_writes, absorbed_ids, model_id_map)``. Deterministic rules,
    model proposals only:

    - Terminal loops (resolved/dropped/expired) are never update targets: a
      ``loop_id`` or similarity hit against one is ignored, and the same
      follow-up can open a NEW loop only after
      ``store.REMENTION_COOLDOWN_DAYS`` — a re-mentioned dropped item never
      revives the dropped loop.
    - A carried ``loop_id``, a stable-key hit, or a token-similarity duplicate
      updates or merges into one loop — never a second document.
    - A loop from an open task (``from_task_id``) keeps the ``task-<id>``
      identity the prompt defines; ``linked_task_id`` records the link and
      ``task_link='model'`` its strength (Done may complete the task).
    - A loop matching an open task is linked (``task_link='heuristic'``),
      never dropped (task-aware dedupe; see ``store.find_task_match`` for the
      documented Jev seam).
    - History and ``last_activity_at`` move only on a status decision, and
      only the decidable status vocabulary is accepted.
    - ``absorbed_ids`` are store documents a merge retired; the caller deletes
      them so the store never grows duplicates.
    """
    by_id = {str(loop.get('id')): dict(loop) for loop in existing if store.is_open(loop)}
    updates: Dict[str, Dict[str, Any]] = {}
    model_id_map: Dict[str, str] = {}

    for entry in model_loops[: store.MODEL_LOOPS_CAP]:
        if not isinstance(entry, Mapping):
            continue
        status = entry.get('status')
        if status not in DECIDABLE_STATUSES:
            continue
        task_id = str(entry.get('from_task_id') or '').strip() or None
        kind = entry.get('kind') if entry.get('kind') in store.LOOP_KINDS else None
        if kind is None:
            kind = 'own_commitment' if task_id else 'owed_to_user'
        who = str(entry.get('who') or '').strip()[: store.LOOP_TEXT_MAX_CHARS] or None
        what = str(entry.get('what') or '').strip()[: store.LOOP_TEXT_MAX_CHARS]
        if not what and not task_id:
            continue

        key = store.stable_key(kind, who, what)
        model_loop_id = str(entry.get('loop_id') or '').strip()
        target: Optional[Dict[str, Any]] = None
        if model_loop_id and model_loop_id in by_id:
            target = by_id[model_loop_id]
        elif task_id:
            target = by_id.get(f'task-{task_id}')
        else:
            for candidate in list(by_id.values()) + list(updates.values()):
                if (
                    str(
                        candidate.get('stable_key')
                        or store.stable_key(candidate.get('kind'), candidate.get('who'), candidate.get('what'))
                    )
                    == key
                ):
                    target = candidate
                    break
                if store.loops_match({'kind': kind, 'who': who, 'what': what}, candidate):
                    target = candidate
                    break

        if target is None:
            if store.remention_blocked(existing, kind=kind, who=who, what=what, today=today, linked_task_id=task_id):
                # The same follow-up a terminal loop closed too recently:
                # ignored, and the terminal loop is left exactly as it is.
                continue
            loop_id = f'task-{task_id}' if task_id else key
            target = {'id': loop_id, 'stable_key': key, 'created_at': _iso(now), 'times_surfaced': 0, 'history': []}
        else:
            target = dict(target)
            loop_id = str(target['id'])
        loop = dict(target)
        if what:
            loop['what'] = what
        if who:
            loop['who'] = who
        loop['kind'] = kind
        loop['stable_key'] = key
        if entry.get('due'):
            loop['by_when'] = str(entry.get('due'))[: store.DUE_MAX_CHARS]
        if entry.get('evidence'):
            loop['evidence'] = str(entry['evidence'])[:200]
        if entry.get('work_related') is not None:
            loop['work_related'] = bool(entry['work_related'])
        if task_id:
            loop['linked_task_id'] = task_id
            loop['task_link'] = 'model'
            task = next((t for t in tasks if str(t.get('task_id')) == task_id), None)
            if task is not None:
                loop['linked_task_title'] = str(task.get('title') or '')[: store.LOOP_TEXT_MAX_CHARS] or None
                loop['linked_task_created_at'] = _iso(task.get('created_at'))
        loop.update(_source_fields(entry, conversation_meta, target))
        if loop.get('status') != status:
            loop = store.append_history(loop, today, status, str(entry.get('evidence') or ''))
        loop['status'] = status
        loop['last_activity_at'] = _iso(now)
        by_id[loop_id] = loop
        updates[loop_id] = loop
        if model_loop_id:
            model_id_map[model_loop_id] = loop_id
        if task_id:
            model_id_map[f'task-{task_id}'] = loop_id

    merged = store.merge_duplicates(list(updates.values()))
    survivors = {str(loop['id']) for loop in merged}
    absorbed = [
        loop_id for loop_id in updates if loop_id not in survivors and loop_id in {str(e.get('id')) for e in existing}
    ]
    if len(merged) != len(updates):
        for model_id, target_id in list(model_id_map.items()):
            if target_id in survivors:
                continue
            absorbed_loop = updates.get(target_id)
            survivor = next(
                (l for l in merged if absorbed_loop is not None and store.loops_match(absorbed_loop, l)), None
            )
            if survivor is not None:
                model_id_map[model_id] = str(survivor['id'])
    return merged, absorbed, model_id_map


def _link_tasks(loops: List[Dict[str, Any]], tasks: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Task-aware dedupe: link matching open loops to their task, never drop.

    These links are heuristic (``find_task_match`` token overlap) — ask-only:
    the card keeps the loop's wording and a Done answer resolves the loop
    without completing the task.
    """
    for loop in loops:
        if loop.get('linked_task_id') or loop.get('status') in store.TERMINAL_STATUSES:
            continue
        match = store.find_task_match(loop, tasks)
        if match is not None:
            loop['linked_task_id'] = str(match.get('task_id'))
            loop['linked_task_title'] = match.get('title')
            loop['task_link'] = 'heuristic'
    return loops


def build_pass_input(
    *,
    date_str: str,
    tz: Optional[str],
    extraction_entries: Sequence[Mapping[str, Any]],
    carried: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
    day_summary: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        'date': date_str,
        'user_timezone': tz or 'UTC',
        'loop_extractions': list(extraction_entries),
        'carried_loops': list(carried),
        'open_tasks': list(tasks),
    }
    if day_summary:
        payload['day_summary'] = dict(day_summary)
    return payload


def run_daily_pass(
    uid: str,
    *,
    date_str: str,
    start_utc: Optional[Any] = None,
    end_utc: Optional[Any] = None,
    tz: Optional[str] = None,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
    llm: Optional[Any] = None,
    polisher: Optional[Callable] = None,
) -> str:
    """Run (or skip) one user's daily pass for one local day. Never serves cards.

    ``start_utc``/``end_utc`` are the local day's UTC bounds, as the recap
    computes them. Returns ``RAN`` or a ``SKIPPED_*`` reason; raises on
    infrastructure/model failure — the dispatching sibling step owns the
    fail-open catch, and a raised pass releases its claim so the day may
    retry exactly once.
    """
    if not open_loops_enabled():
        return SKIPPED_DISABLED
    now = now or store.now_utc()
    try:
        today = date.fromisoformat(date_str)
    except ValueError:
        today = local_today(tz, now)

    if open_loops_db.get_cards_doc(uid, date_str, firestore_client=firestore_client) is not None:
        return SKIPPED_ALREADY_RAN

    rows = (
        conversations_db.get_conversations(uid, start_date=start_utc, end_date=end_utc, date_field='started_at') or []
    )
    rows = eligible_day_rows(uid, rows)
    extraction_entries = day_extractions(uid, rows)

    loops = open_loops_db.get_loops(uid, firestore_client=firestore_client)
    expired_writes, deletes = store.sweep(loops, today)
    expired_by_id = {str(w['id']): w for w in expired_writes}
    for loop in expired_writes:
        open_loops_db.upsert_loop(uid, loop, firestore_client=firestore_client)
    if deletes:
        open_loops_db.delete_loops(uid, deletes, firestore_client=firestore_client)
    loops = [expired_by_id.get(str(loop.get('id')), loop) for loop in loops if str(loop.get('id')) not in set(deletes)]

    open_loops = [loop for loop in loops if store.is_open(loop)]
    due_soon_any = any(loop.get('status') == 'due_soon' for loop in open_loops)
    if not extraction_entries and not open_loops:
        return SKIPPED_NO_SIGNAL
    if not rows and not due_soon_any:
        # No conversations today and nothing due: don't pay the daily call
        # just to re-stale carried loops.
        return SKIPPED_NO_SIGNAL

    # The spend guard: atomically claim the day before the model call, so a
    # retried tick, an abandoned worker or the recap's locked-retry path can
    # never double-pay for this local day.
    if not open_loops_db.claim_daily_pass(uid, date_str, now=now, firestore_client=firestore_client):
        return SKIPPED_CLAIMED

    try:
        return _run_claimed_pass(
            uid,
            date_str=date_str,
            tz=tz,
            rows=rows,
            extraction_entries=extraction_entries,
            loops=loops,
            open_loops=open_loops,
            today=today,
            now=now,
            firestore_client=firestore_client,
            llm=llm,
            polisher=polisher,
        )
    except Exception:
        # Release for exactly one bounded retry (see claim_daily_pass); the
        # cards document stays absent, so the day is still marked unrun.
        open_loops_db.mark_daily_pass_failed(uid, date_str, firestore_client=firestore_client)
        raise


def _run_claimed_pass(
    uid: str,
    *,
    date_str: str,
    tz: Optional[str],
    rows: Sequence[Mapping[str, Any]],
    extraction_entries: List[Dict[str, Any]],
    loops: List[Dict[str, Any]],
    open_loops: List[Dict[str, Any]],
    today: date,
    now: datetime,
    firestore_client: Any,
    llm: Optional[Any],
    polisher: Optional[Callable],
) -> str:
    """The claimed (already paid-for-once) pass: prompt, one model call, writes."""
    carried = sorted(open_loops, key=store.carried_relevance)[: store.CARRIED_LOOPS_PROMPT_CAP]
    carried_views = [store.carried_view(loop, today) for loop in carried]
    tasks = open_tasks_view(uid, today)
    day_summary = day_summary_view(uid, date_str)

    conversation_meta = {
        str(row.get('id')): {
            'id': str(row.get('id')),
            'title': _row_title(row),
            'started_at': _iso(row.get('started_at')),
        }
        for row in rows
    }
    render = render_day(rows)
    user_content = f'{render}\n\nINPUT (JSON):\n' + json.dumps(
        build_pass_input(
            date_str=date_str,
            tz=tz,
            extraction_entries=extraction_entries,
            carried=carried_views,
            tasks=tasks,
            day_summary=day_summary,
        ),
        ensure_ascii=False,
        default=str,
    )

    model = llm if llm is not None else get_llm('open_loop_daily')
    with track_usage(uid, Features.OPEN_LOOP_DAILY):
        response = model.invoke(
            [
                {'role': 'system', 'content': OPEN_LOOPS_DAILY_RULES},
                {'role': 'user', 'content': user_content},
            ]
        )
    parsed = parse_model_output(response) or {}
    raw_loops = parsed.get('loops')
    model_loops: List[Any] = list(raw_loops) if isinstance(raw_loops, list) else []
    raw_surface = parsed.get('surface')
    surface_entries: List[Any] = list(raw_surface) if isinstance(raw_surface, list) else []
    # Defensive output caps: the prompt asks for ≤3 surface entries and a
    # short loop list; a runaway response cannot flood the store or cards.
    model_loops = model_loops[: store.MODEL_LOOPS_CAP]
    surface_entries = surface_entries[: store.DAILY_CARD_SLOTS]

    writes, absorbed, model_id_map = ingest_model_loops(
        model_loops,
        loops,
        tasks,
        today=today,
        conversation_meta=conversation_meta,
        now=now,
    )
    writes = _link_tasks(writes, tasks)

    loops_by_id = {str(loop['id']): loop for loop in [*loops, *writes]}
    candidates: List[Dict[str, Any]] = []
    for entry in surface_entries:
        if not isinstance(entry, Mapping):
            continue
        target_id = model_id_map.get(str(entry.get('loop_id')), str(entry.get('loop_id') or ''))
        loop = loops_by_id.get(target_id)
        if loop is None:
            continue
        try:
            value = int(entry.get('value') or 0)
        except (TypeError, ValueError):
            continue
        candidates.append({'loop': loop, 'value': value})

    selected = store.select_surface_cards(candidates, today)
    polisher = llm_polisher(uid) if polisher is None else polisher
    cards: List[Dict[str, Any]] = []
    surfaced_ids = set()
    for candidate in selected:
        loop = candidate['loop']
        card = build_review_card(store.card_view(loop), tz=tz, now=now, polisher=polisher)
        cards.append(
            {
                'id': str(loop['id']),
                'loop_id': str(loop['id']),
                **card.as_payload(),
                'value': int(candidate['value']),
                'state': 'pending',
                'actions': ['done', 'remind', 'drop'],
                'generated_at': _iso(now),
            }
        )
        surfaced_ids.add(str(loop['id']))

    for loop_id in absorbed:
        open_loops_db.delete_loops(uid, [loop_id], firestore_client=firestore_client)
    writes = [store.mark_surfaced(loop, today) if str(loop['id']) in surfaced_ids else loop for loop in writes]
    for loop in writes:
        open_loops_db.upsert_loop(uid, loop, firestore_client=firestore_client)
    open_loops_db.set_cards(uid, date_str, cards, firestore_client=firestore_client)
    open_loops_db.mark_daily_pass_ran(uid, date_str, firestore_client=firestore_client)
    logger.info(
        'open_loops_daily_pass uid=%s date=%s loops_written=%d cards=%d',
        uid,
        date_str,
        len(writes),
        len(cards),
    )
    return RAN
