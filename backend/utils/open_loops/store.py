"""Open-loop store domain logic: identity, expiry, dedupe, cooldown, ranking.

Pure functions over plain loop dicts — no I/O, so every rule here is testable
without Firestore. ``database/open_loops.py`` owns persistence; the daily pass
(``utils/open_loops/daily.py``) composes these rules.

A loop is one checkable follow-up the owner may later be asked about. Kinds:
``owed_to_user`` (delegated, or another's commitment to the owner),
``own_commitment`` (the owner's own task going stale), ``issue_or_blocker``
(work defect to file / blocked dated errand). Statuses: ``opened``,
``progressing``, ``stale``, ``due_soon`` are open; ``resolved``, ``dropped``,
``expired`` are terminal and never surface again.

Task-aware dedupe: a loop that matches an open task is *linked*
(``linked_task_id``), never dropped — the card then asks about the task
("Did you send Tyler the Stably bullets?") instead of duplicating it. Links
come in two strengths: ``task_link='model'`` (the model asserted the task as
the loop's origin via ``from_task_id`` — a strong link; the card renders the
task's own description, and Done completes the task) and ``task_link=
'heuristic'`` (``find_task_match`` token overlap — ask-only; Done resolves
the loop but never completes the task). ``find_task_match`` is the documented
seam a Jev-based matcher replaces later without touching any caller.

Terminal loops (resolved/dropped/expired) never come back: they are excluded
from update matching and merging, and the same follow-up can open a NEW loop
only after ``REMENTION_COOLDOWN_DAYS`` without signal.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

LOOP_KINDS = ('owed_to_user', 'own_commitment', 'issue_or_blocker')
OPEN_STATUSES = frozenset({'opened', 'progressing', 'stale', 'due_soon'})
TERMINAL_STATUSES = frozenset({'resolved', 'dropped', 'expired'})

# Days without any signal before a loop expires, by kind. own_commitment gets
# longer because the owner's own tracked work has its own queue; owed_to_user
# gets the longest because someone else's deliverable can resurface after a
# quiet stretch and the answer is still valuable.
DEFAULT_EXPIRY_DAYS = 7
EXPIRY_DAYS_BY_KIND = {
    'own_commitment': 10,
    'owed_to_user': 14,
    'issue_or_blocker': DEFAULT_EXPIRY_DAYS,
}
# Terminal docs are kept this long (negative examples / audit), then deleted so
# the per-user store stays bounded no matter how many loops accumulate.
TERMINAL_RETENTION_DAYS = 14
# Hard cap on open loops per user. Beyond it the least recently active open
# loops expire first; with expiry and retention the store never grows past
# OPEN_LOOP_STORE_CAP open docs plus a bounded terminal tail.
OPEN_LOOP_STORE_CAP = 60

# The daily pass carries at most this many most-relevant open loops in the
# prompt, and considers at most this many open tasks.
CARRIED_LOOPS_PROMPT_CAP = 20
OPEN_TASKS_PROMPT_CAP = 40

# Re-ask cooldown: a loop surfaced within the last two days is not surfaced
# again unless it became due_soon. "Remind me later" snoozes two days.
SURFACE_COOLDOWN_DAYS = 2
SNOOZE_DAYS = 2

# Daily Review slots: at most three cards, only value >= 3.
DAILY_CARD_SLOTS = 3
MIN_SURFACE_VALUE = 3

# Token-overlap thresholds. Both parts (Jaccard AND containment) must pass —
# max() alone let "Tyler send deck" match "send deck to investors" (shared
# short wording inside a different task) and wrongly complete that task.
# Task matching is the looser pair: the loop is asking about the same work.
TASK_MATCH_JACCARD_MIN = 0.6
TASK_MATCH_CONTAINMENT_MIN = 0.8
# Loop-to-loop merging is stricter still: merging rewrites the loop store, so
# "Tyler send deck" and "Tyler send invoice" (two thirds shared) stay two loops.
LOOP_MERGE_JACCARD_MIN = 0.7
LOOP_MERGE_CONTAINMENT_MIN = 0.8

# A terminal loop's follow-up can open a NEW loop only this many days after
# the terminal day; within the window a re-mention is ignored (never revived).
# The sweep deletes terminal docs after TERMINAL_RETENTION_DAYS, so in the
# daily-pass flow the cool-off and the doc's lifetime end together.
REMENTION_COOLDOWN_DAYS = 14

# Defensive caps on the daily pass's model output (the prompt asks for far
# less): a runaway response cannot flood the store or the cards document.
MODEL_LOOPS_CAP = 40
LOOP_TEXT_MAX_CHARS = 160
DUE_MAX_CHARS = 40

_WORD_RE = re.compile(r'[a-z0-9]+')
_FUNCTION_WORDS = frozenset(
    {
        'the',
        'a',
        'an',
        'and',
        'or',
        'to',
        'of',
        'for',
        'on',
        'in',
        'with',
        'at',
        'by',
        'is',
        'are',
        'it',
        'this',
        'that',
    }
)

# History entries keep the shape card.py's why-now reader expects
# (history[-1]['date']); last_activity_at moves only on real signal, never on
# surfacing, so "no follow-up since Tuesday" stays honest.


def normalize_text(value: Any) -> str:
    """Lowercased word tokens joined by one space; punctuation dropped."""
    return ' '.join(_WORD_RE.findall(str(value or '').lower()))


def stable_key(kind: Any, who: Any, what: Any) -> str:
    """The upsert identity of a loop: its kind plus normalized who+what.

    Two extractions of the same promise land on the same key even when the
    wording differs in case or punctuation.
    """
    payload = '|'.join((str(kind or ''), normalize_text(who), normalize_text(what)))
    return 'ol-' + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def significant_tokens(*values: Any) -> frozenset[str]:
    tokens = normalize_text(' '.join(str(v or '') for v in values)).split()
    return frozenset(t for t in tokens if len(t) > 2 and t not in _FUNCTION_WORDS)


def similarity_parts(a: frozenset[str], b: frozenset[str]) -> tuple[float, float]:
    """``(jaccard, containment)`` over significant tokens.

    Containment matters because a loop's "send the vendor write-up" is often a
    short restatement of a longer task title; Jaccard alone would miss it.
    Callers combine the two parts with the AND rules the threshold constants
    document — a single loose max() is what let the wrong task complete.
    """
    if not a or not b:
        return 0.0, 0.0
    shared = len(a & b)
    return shared / len(a | b), shared / min(len(a), len(b))


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_open(loop: Mapping[str, Any]) -> bool:
    return loop.get('status') in OPEN_STATUSES


def days_since(value: Any, today: date) -> Optional[int]:
    moment = _as_date(value)
    return (today - moment).days if moment is not None else None


def last_activity_day(loop: Mapping[str, Any]) -> Optional[date]:
    return _as_date(loop.get('last_activity_at') or loop.get('created_at'))


def append_history(loop: Mapping[str, Any], day: date, status: str, evidence: str) -> dict[str, Any]:
    """Return a copy of ``loop`` with one status entry appended (last ten kept)."""
    entry = {'date': day.isoformat(), 'status': status, 'evidence': str(evidence or '')[:200]}
    history = [dict(item) for item in (loop.get('history') or []) if isinstance(item, Mapping)]
    return {**loop, 'status': status, 'history': (history + [entry])[-10:]}


def expiry_days(loop: Mapping[str, Any]) -> int:
    return EXPIRY_DAYS_BY_KIND.get(str(loop.get('kind')), DEFAULT_EXPIRY_DAYS)


def expiry_due(loop: Mapping[str, Any], today: date) -> bool:
    """True when an open loop has had no signal for its kind's expiry window."""
    if not is_open(loop):
        return False
    last = last_activity_day(loop)
    if last is None:
        return False
    return (today - last).days >= expiry_days(loop)


def terminal_day(loop: Mapping[str, Any]) -> Optional[date]:
    """The day a terminal loop closed (last history entry), for retention."""
    if loop.get('status') not in TERMINAL_STATUSES:
        return None
    history = loop.get('history') or []
    for entry in reversed(history):
        if isinstance(entry, Mapping):
            return _as_date(entry.get('date'))
    return last_activity_day(loop)


def sweep(loops: Iterable[Mapping[str, Any]], today: date) -> tuple[list[dict[str, Any]], list[str]]:
    """One bounded-store maintenance pass. Returns ``(writes, deletes)``.

    - Open loops past their kind's no-signal window become ``expired``.
    - Terminal loops older than ``TERMINAL_RETENTION_DAYS`` are deleted.
    - When more than ``OPEN_LOOP_STORE_CAP`` open loops remain, the least
      recently active ones expire first.
    """
    writes: list[dict[str, Any]] = []
    deletes: list[str] = []
    kept_open: list[dict[str, Any]] = []
    for loop in loops:
        current = dict(loop)
        if current.get('status') in TERMINAL_STATUSES:
            ended = terminal_day(current)
            if ended is not None and (today - ended).days > TERMINAL_RETENTION_DAYS:
                deletes.append(str(current.get('id')))
            continue
        if expiry_due(current, today):
            writes.append(append_history(current, today, 'expired', 'no signal for the expiry window'))
            continue
        kept_open.append(current)
    if len(kept_open) > OPEN_LOOP_STORE_CAP:

        def staleness(loop: Mapping[str, Any]) -> tuple[int, str]:
            last = last_activity_day(loop)
            # most stale first: age descending, id only for determinism
            return (-(today - last).days if last is not None else 0), str(loop.get('id'))

        overflow = sorted(kept_open, key=staleness)[: len(kept_open) - OPEN_LOOP_STORE_CAP]
        overflow_ids = {str(loop.get('id')) for loop in overflow}
        kept_open = [loop for loop in kept_open if str(loop.get('id')) not in overflow_ids]
        writes.extend(append_history(loop, today, 'expired', 'store cap: least recently active') for loop in overflow)
    return writes, deletes


def merge_loop(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    """Merge a duplicate into the surviving loop.

    Identity, counters and history survive from ``existing``; wording prefers
    the fresher ``incoming`` when it carries a value. Source conversations
    accumulate so the card can still name where it came from.
    """
    merged = dict(existing)
    for field in ('kind', 'who', 'what', 'by_when', 'evidence', 'work_related', 'source_title', 'source_started_at'):
        if incoming.get(field):
            merged[field] = incoming[field]
    ids: list[str] = []
    for value in list(existing.get('source_conversation_ids') or []) + list(
        incoming.get('source_conversation_ids') or []
    ):
        text = str(value)
        if text and text not in ids:
            ids.append(text)
    merged['source_conversation_ids'] = ids[:10]
    if incoming.get('linked_task_id'):
        merged['linked_task_id'] = incoming['linked_task_id']
        # Strength travels with the link: a model-asserted task link keeps
        # task_link='model' (and its render fields) across the merge.
        for field in ('task_link', 'linked_task_title', 'linked_task_created_at'):
            if incoming.get(field):
                merged[field] = incoming[field]
    incoming_history = [e for e in (incoming.get('history') or []) if isinstance(e, Mapping)]
    merged['history'] = (list(existing.get('history') or []) + incoming_history)[-10:]
    return merged


def find_task_match(loop: Mapping[str, Any], tasks: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The open task this loop is asking about, or None.

    First-version heuristic (documented seam — the single function a Jev-based
    matcher replaces): significant-token overlap of the loop's who+what against
    each task title, requiring **both** Jaccard ≥ ``TASK_MATCH_JACCARD_MIN``
    and containment ≥ ``TASK_MATCH_CONTAINMENT_MIN``; the best task wins. When
    both sides name a ``who`` it must be the same person: "Tyler: send deck"
    never links to "send deck to investors" — that false link is what completed
    the wrong task in review.
    """
    loop_tokens = significant_tokens(loop.get('who'), loop.get('what'))
    if not loop_tokens:
        return None
    loop_who = normalize_text(loop.get('who'))
    best: Optional[Mapping[str, Any]] = None
    best_key: tuple[float, float] = (0.0, 0.0)
    for task in tasks:
        task_who = normalize_text(task.get('who'))
        if loop_who and task_who and loop_who != task_who:
            continue
        jaccard, containment = similarity_parts(
            loop_tokens, significant_tokens(task.get('title') or task.get('description'))
        )
        if jaccard < TASK_MATCH_JACCARD_MIN or containment < TASK_MATCH_CONTAINMENT_MIN:
            continue
        if (jaccard, containment) > best_key:
            best, best_key = task, (jaccard, containment)
    return best


def text_names_task(text: Any, title: Any) -> bool:
    """Whether a rendered card's text names the task by its significant tokens.

    The Done-completion gate: only an answer to a card that actually carried
    the task's own description may complete that task.
    """
    title_tokens = significant_tokens(title)
    if not title_tokens:
        return False
    text_tokens = significant_tokens(text)
    return len(title_tokens & text_tokens) / len(title_tokens) >= TASK_MATCH_CONTAINMENT_MIN


def _same_or_absent_who(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    who_a = normalize_text(a.get('who'))
    who_b = normalize_text(b.get('who'))
    return not who_a or not who_b or who_a == who_b


def loops_match(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Whether two loops are the same follow-up in different wording.

    Same normalized ``who`` is required whenever both name one (a deliverable
    from Tyler is not a deliverable from Ann), and the token overlap must pass
    both merge thresholds — stricter than the task-match pair because a merge
    rewrites the store while a task link only annotates a card.
    """
    if a.get('stable_key') and a.get('stable_key') == b.get('stable_key'):
        return True
    if not _same_or_absent_who(a, b):
        return False
    jaccard, containment = similarity_parts(
        significant_tokens(a.get('who'), a.get('what')), significant_tokens(b.get('who'), b.get('what'))
    )
    return jaccard >= LOOP_MERGE_JACCARD_MIN and containment >= LOOP_MERGE_CONTAINMENT_MIN


def remention_blocked(
    existing: Iterable[Mapping[str, Any]],
    *,
    kind: Any,
    who: Any,
    what: Any,
    today: date,
    linked_task_id: Any = None,
) -> bool:
    """Whether a terminal loop closed this same follow-up too recently.

    A dropped/resolved/expired loop is never revived. Within
    ``REMENTION_COOLDOWN_DAYS`` of its terminal day, a re-mention of the same
    follow-up (same stable identity, same task link, or a ``loops_match`` hit)
    opens nothing at all; after the cool-off it may open a NEW loop with fresh
    history (by then the sweep has deleted the terminal document).
    """
    key = stable_key(kind, who, what)
    task_loop_id = f'task-{linked_task_id}' if linked_task_id else None
    candidate = {'kind': kind, 'who': who, 'what': what}
    for loop in existing:
        if loop.get('status') not in TERMINAL_STATUSES:
            continue
        same = (
            str(loop.get('id')) == key
            or (task_loop_id is not None and str(loop.get('id')) == task_loop_id)
            or str(loop.get('stable_key') or '') == key
            or loops_match(candidate, loop)
        )
        if not same:
            continue
        ended = terminal_day(loop)
        if ended is not None and (today - ended).days < REMENTION_COOLDOWN_DAYS:
            return True
    return False


def merge_duplicates(loops: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate loops; a task-linked survivor beats a plain one.

    Blind-label evidence (KB D31): a stand-in dedupe that dropped wanted cards
    whenever a matching task existed was wrong 7/12 times — so here the match
    *merges* and the task link always survives.

    A terminal loop never merges with anything: merging would pull it back
    into a survivor that can still surface, and a closed loop must stay closed.
    """
    survivors: list[dict[str, Any]] = []
    for loop in loops:
        duplicate = next((s for s in survivors if s.get('id') != loop.get('id') and loops_match(s, loop)), None)
        if duplicate is None or duplicate.get('status') in TERMINAL_STATUSES or loop.get('status') in TERMINAL_STATUSES:
            survivors.append(dict(loop))
            continue
        if loop.get('linked_task_id') and not duplicate.get('linked_task_id'):
            survivors[survivors.index(duplicate)] = merge_loop(loop, duplicate)
        else:
            survivors[survivors.index(duplicate)] = merge_loop(duplicate, loop)
    return survivors


def surfaced_recently(loop: Mapping[str, Any], today: date) -> bool:
    last = _as_date(loop.get('last_surfaced_at'))
    return last is not None and (today - last).days < SURFACE_COOLDOWN_DAYS


def snoozed(loop: Mapping[str, Any], today: date) -> bool:
    until = _as_date(loop.get('snoozed_until'))
    return until is not None and until >= today


def surfaceable(loop: Mapping[str, Any], today: date) -> bool:
    """Cooldown + snooze + terminal gate for one surfaced card.

    - Terminal (resolved/dropped/expired) loops never surface.
    - A loop surfaced in the last two days is not re-asked unless it is now
      due_soon (status change re-arms the question).
    - A snoozed loop stays quiet until its snooze passes.
    """
    if not is_open(loop):
        return False
    if snoozed(loop, today):
        return False
    if surfaced_recently(loop, today) and loop.get('status') != 'due_soon':
        return False
    return True


def select_surface_cards(
    candidates: Sequence[Mapping[str, Any]], today: date, *, slots: int = DAILY_CARD_SLOTS
) -> list[Mapping[str, Any]]:
    """Deterministic slot fill: value >= 3, due_soon first, work first, cap 3.

    ``candidates`` items carry ``loop`` and ``value`` (the pass's 1–5 score).
    The model proposes; this filter decides — a coherent ranking the UI can
    trust without re-scoring.
    """
    eligible = [
        c for c in candidates if int(c.get('value') or 0) >= MIN_SURFACE_VALUE and surfaceable(c['loop'], today)
    ]
    eligible.sort(
        key=lambda c: (
            0 if c['loop'].get('status') == 'due_soon' else 1,
            0 if c['loop'].get('work_related') else 1,
            -int(c.get('value') or 0),
            str(c['loop'].get('id')),
        )
    )
    return eligible[:slots]


_STATUS_PRIORITY = {'due_soon': 0, 'stale': 1, 'progressing': 2, 'opened': 3}


def carried_relevance(loop: Mapping[str, Any]) -> tuple[int, int]:
    """Ordering for the ~20 most relevant open loops carried in the prompt."""
    last = last_activity_day(loop)
    age = (datetime.now(timezone.utc).date() - last).days if last is not None else 0
    return _STATUS_PRIORITY.get(str(loop.get('status')), 9), -age


def carried_view(loop: Mapping[str, Any], today: date) -> dict[str, Any]:
    """The compact prompt projection of one open loop."""
    last = last_activity_day(loop)
    history = [
        {'date': e.get('date'), 'status': e.get('status'), 'evidence': e.get('evidence')}
        for e in (loop.get('history') or [])[-5:]
        if isinstance(e, Mapping)
    ]
    opened = _as_date(loop.get('created_at'))
    return {
        'loop_id': loop.get('id'),
        'kind': loop.get('kind'),
        'who': loop.get('who'),
        'what': loop.get('what'),
        'due': loop.get('by_when'),
        'opened_on': opened.isoformat() if opened is not None else None,
        'age_days': (today - last).days if last is not None else None,
        'times_surfaced': loop.get('times_surfaced') or 0,
        'status': loop.get('status'),
        'history': history,
    }


def mark_surfaced(loop: Mapping[str, Any], day: date) -> dict[str, Any]:
    """Count one surfacing. History/last_activity stay untouched on purpose:
    surfacing is our action, not the owner's follow-up."""
    return {
        **loop,
        'times_surfaced': int(loop.get('times_surfaced') or 0) + 1,
        'last_surfaced_at': day.isoformat(),
    }


def card_view(loop: Mapping[str, Any]) -> dict[str, Any]:
    """The field names ``utils.open_loops.card.build_card`` renders from.

    A strong (model-asserted) task link renders the task's own description in
    the card — "Did you send Tyler the bullets for the Stably write-up? (your
    task from Thu)" — so a Done answer is evidence about the task itself. A
    heuristic-only link stays ask-only: the card keeps the loop's wording and
    Done resolves the loop without completing the task.
    """
    view = dict(loop)
    view['due'] = loop.get('by_when')
    view['title'] = loop.get('source_title') or 'conversation'
    if loop.get('source_started_at'):
        view['started_at'] = loop.get('source_started_at')
    task_title = loop.get('linked_task_title')
    if loop.get('linked_task_id') and task_title:
        if loop.get('task_link') == 'model':
            view['what'] = task_title
            view['related_task'] = {'title': task_title, 'opened_on': loop.get('linked_task_created_at')}
        elif not view.get('what'):
            view['related_task'] = {'title': task_title}
    return view
