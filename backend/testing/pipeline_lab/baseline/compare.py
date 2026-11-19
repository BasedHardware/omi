"""Baseline normalization, matching, change classification and the day digest. Pure functions over contract JSON.

**Production view.** ``corpus/<day>/baseline/{conversations,memories,action_items}.jsonl``
hold production rows (snapshot shape). They go through the same
:func:`chain.export.normalize_conversation` as the replay, with tasks and memories
grouped by ``conversation_id``, so both sides have one shape.

**Matching (pairs).** Id first (M1 replays production's own capture ids; v3 sets ``baseline_id`` to
the production conversation sharing the most recordings). The rest pair by time overlap: greedy on
intersection-over-union of ``[started_at, finished_at]``, highest first, above ``min_iou`` (default 0.3).

**Groups (the pairing units the inspector shows).** Pairs plus the strong ``baseline_ids`` links (a
replay conversation sharing recordings with several production conversations; :func:`strong_links`)
are joined into connected components. A group is ``1:1`` (``same`` / ``cosmetic`` / ``content``), ``merge`` (N production -> 1
replay), ``split`` (1 -> N), ``regroup`` (N -> M, both above one), ``new`` (replay only) or ``missing``
(production only). Every count the inspector shows is a count of groups carrying a tag
(:data:`TAGS`), so a filter chip and the list it filters can never disagree.

**Fields.** Each 1:1 group classifies ``home, discarded, boundary, title, overview, emoji, category,
events, tasks, memories, pushes, transcript`` (plus ``home_reason``). Text is compared after
:func:`loose_text` (casefold, NFKC, every punctuation run and whitespace run collapsed), so a
whitespace- or punctuation-only edit is ``cosmetic``; ``emoji``, ``category`` and the hidden reason of a
conversation hidden on both sides are always cosmetic. Title and overview record an edit size
(``words_changed``, ``edit_ratio`` = 1 - word-sequence similarity). Groups of more than one
conversation compare Home, tasks, memories and pushes over the union of each side; their summaries
are not compared (the regrouping is the change).

**Home.** A conversation is on Home when its ``v3.visible`` is true; a classic row (no ``v3`` block)
is on Home when it is not discarded.

Every difference is a production comparison (``vs production``), never a regression verdict.
This is the one pairing and status implementation (RULINGS 10); the inspector reads
``baseline.json`` (``version`` 2) or calls :func:`baseline_view` itself for runs written without it.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from testing.pipeline_lab.chain.export import normalize_conversation
from testing.pipeline_lab.stack.io import parse_time

VERSION = 2
BOUNDARY_TOLERANCE_S = 30.0
NEAR_MATCH = 0.45  # word Jaccard at which two items are one item edited, not one removed and one added
LINK_COVER = 0.5  # a weak shared-recording link joins a group only above this cover (see strong_links)
REWRITE_RATIO = 0.5  # edit_ratio at or above which a title/overview is "rewritten" rather than "edited"

FIELDS = (
    'home',
    'discarded',
    'boundary',
    'title',
    'overview',
    'emoji',
    'category',
    'home_reason',
    'events',
    'tasks',
    'memories',
    'pushes',
    'transcript',
)
ALWAYS_COSMETIC = frozenset({'emoji', 'category', 'home_reason'})
COMPARED_FIELDS = FIELDS  # name kept for older readers

GROUP_KINDS = ('same', 'cosmetic', 'content', 'merge', 'split', 'regroup', 'new', 'missing')
MARKERS = {
    'same': '=',
    'cosmetic': '~',
    'content': '≠',
    'merge': '⇉',
    'split': '⇇',
    'regroup': '⇄',
    'new': '+',
    'missing': '−',
}
GROUPING_KINDS = frozenset({'merge', 'split', 'regroup', 'new', 'missing'})
# Every tag a group can carry; the digest counts groups per tag.
TAGS = (
    'worth',
    'home_dropped',
    'home_added',
    'home_both',
    'merge',
    'split',
    'regroup',
    'new',
    'missing',
    'boundary',
    'summary',
    'events',
    'tasks',
    'memories',
    'pushes',
    'transcript',
    'discard',
    'cosmetic',
    'same',
)


# ---- production view ------------------------------------------------------------------------


def production_view(
    conversations: Iterable[Mapping[str, Any]],
    *,
    memories: Iterable[Mapping[str, Any]] = (),
    action_items: Iterable[Mapping[str, Any]] = (),
    notifications: Iterable[Mapping[str, Any]] = (),
    people: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    by_conv: dict[str, dict[str, list]] = {}
    for kind, rows in (('memories', memories), ('action_items', action_items), ('notifications', notifications)):
        for row in rows:
            cid = row.get('conversation_id') or (row.get('memory_id') if kind == 'memories' else None)
            if cid:
                by_conv.setdefault(str(cid), {}).setdefault(kind, []).append(row)
    out = []
    for row in conversations:
        cid = str(row.get('id'))
        grouped = by_conv.get(cid, {})
        normalized = normalize_conversation(
            row,
            action_items=grouped.get('action_items', []),
            memories=grouped.get('memories', []),
            notifications=grouped.get('notifications', []),
            lane=row.get('record_lane_owner') or 'unknown',
            baseline_id=cid,
            people=people,
            evaluable={'boundaries': True, 'reason': 'production'},
        )
        out.append(normalized)
    out.sort(key=lambda c: (c.get('started_at') or '', c['id']))
    return out


# ---- matching -------------------------------------------------------------------------------


def _span(conversation: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
    start = parse_time(conversation.get('started_at'))
    end = parse_time(conversation.get('finished_at')) or start
    if start is None or end is None:
        return None
    return (start, end) if end >= start else (end, start)


def iou(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    sa, sb = _span(a), _span(b)
    if sa is None or sb is None:
        return 0.0
    inter = (min(sa[1], sb[1]) - max(sa[0], sb[0])).total_seconds()
    if inter <= 0:
        return 0.0
    union = (max(sa[1], sb[1]) - min(sa[0], sb[0])).total_seconds()
    return inter / union if union > 0 else 1.0


@dataclass(frozen=True)
class Match:
    replay_id: str | None
    baseline_id: str | None
    method: str  # id | overlap | unmatched
    iou: float


def match_conversations(
    replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]], *, min_iou: float = 0.3
) -> list[Match]:
    prod_by_id = {str(p['id']): p for p in production}
    matches: list[Match] = []
    used_prod: set[str] = set()
    pending_replay = []
    for r in replay:
        rid = str(r['id'])
        candidate = r.get('baseline_id') or rid
        if candidate in prod_by_id and candidate not in used_prod:
            matches.append(Match(rid, candidate, 'id', round(iou(r, prod_by_id[candidate]), 4)))
            used_prod.add(candidate)
        else:
            pending_replay.append(r)
    remaining_prod = [p for p in production if str(p['id']) not in used_prod]
    scored = sorted(
        ((iou(r, p), str(r['id']), str(p['id'])) for r in pending_replay for p in remaining_prod),
        key=lambda row: (-row[0], row[1], row[2]),
    )
    used_replay: set[str] = set()
    for score, rid, pid in scored:
        if score < min_iou:
            break
        if rid in used_replay or pid in used_prod:
            continue
        matches.append(Match(rid, pid, 'overlap', round(score, 4)))
        used_replay.add(rid)
        used_prod.add(pid)
    for r in pending_replay:
        if str(r['id']) not in used_replay:
            matches.append(Match(str(r['id']), None, 'unmatched', 0.0))
    for p in production:
        if str(p['id']) not in used_prod:
            matches.append(Match(None, str(p['id']), 'unmatched', 0.0))
    return matches


# ---- text and items -------------------------------------------------------------------------

_NON_WORD = re.compile(r'[\W_]+', re.UNICODE)


def loose_text(text: Any) -> str:
    """Text with case, width, whitespace and punctuation removed from the comparison.

    Every run of punctuation or whitespace becomes one space, so "3.5" ("3 5") and "35" stay apart.
    """
    folded = unicodedata.normalize('NFKC', str(text or '')).casefold()
    return _NON_WORD.sub(' ', folded).strip()


def edit_size(replay: Any, production: Any) -> dict[str, Any]:
    """Word-level edit measure between two texts, after :func:`loose_text`."""
    a, b = loose_text(production).split(), loose_text(replay).split()
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in matcher.get_opcodes() if op != 'equal')
    ratio = round(1.0 - matcher.ratio(), 4) if (a or b) else 0.0
    return {'words_changed': changed, 'edit_ratio': ratio, 'words': {'replay': len(b), 'production': len(a)}}


def _words(text: str) -> set[str]:
    return set(loose_text(text).split())


def _jaccard(a: str, b: str) -> float:
    left, right = _words(a), _words(b)
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _task_text(item: Mapping[str, Any]) -> str:
    return str(item.get('description') or '')


def _memory_text(item: Mapping[str, Any]) -> str:
    return str(item.get('content') or '')


def _push_text(item: Mapping[str, Any]) -> str:
    return f"{item.get('title') or ''} {item.get('body') or ''}"


ITEM_FIELDS = {
    'tasks': ('action_items', _task_text),
    'memories': ('memories', _memory_text),
    'pushes': ('notifications', _push_text),
}


def item_diff(replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]], text_of) -> dict[str, Any]:
    """Counts of items added, removed and edited (near match), with cosmetic-only edits counted apart."""
    left = [loose_text(text_of(i)) for i in replay or []]
    right = [loose_text(text_of(i)) for i in production or []]
    pool = list(right)
    unmatched_left = []
    cosmetic = 0
    for text in left:
        if text in pool:
            pool.remove(text)
        else:
            unmatched_left.append(text)
    raw_left = sorted(text_of(i) for i in replay or [])
    raw_right = sorted(text_of(i) for i in production or [])
    if not unmatched_left and not pool and raw_left != raw_right:
        cosmetic = 1
    edited = 0
    remaining = list(pool)
    for text in list(unmatched_left):
        best = max(remaining, key=lambda other: _jaccard(text, other), default=None)
        if best is not None and _jaccard(text, best) >= NEAR_MATCH:
            remaining.remove(best)
            unmatched_left.remove(text)
            edited += 1
    return {
        'replay': len(left),
        'production': len(right),
        'added': len(unmatched_left),
        'removed': len(remaining),
        'edited': edited,
        'cosmetic': cosmetic,
    }


def _events(structured: Mapping[str, Any]) -> list[tuple[str, str]]:
    out = []
    for event in structured.get('events') or []:
        if isinstance(event, Mapping):
            out.append((loose_text(event.get('title') or ''), str(event.get('start') or event.get('starts_at') or '')))
        else:
            out.append((loose_text(event), ''))
    return sorted(out)


# ---- per-conversation facts -----------------------------------------------------------------


def on_home(conversation: Mapping[str, Any]) -> bool:
    block = conversation.get('v3')
    if isinstance(block, Mapping):
        return bool(block.get('visible', True))
    return not conversation.get('discarded')


def home_reason(conversation: Mapping[str, Any]) -> str:
    """Why a conversation is off Home ('' when it is on Home)."""
    if on_home(conversation):
        return ''
    block = conversation.get('v3')
    if isinstance(block, Mapping):
        return str(block.get('home_hidden_reason') or block.get('kind') or 'hidden')
    return str(conversation.get('discard_reason') or 'discarded')


def transcript_of(conversation: Mapping[str, Any]) -> str:
    return ' '.join((seg.get('text') or '').strip() for seg in conversation.get('segments') or [])


def comparable(conversation: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The raw values of every compared field (the inspector shows these side by side)."""
    if conversation is None:
        return None
    s = conversation.get('structured') or {}
    return {
        'home': on_home(conversation),
        'home_reason': home_reason(conversation),
        'discarded': bool(conversation.get('discarded')),
        'boundary': [conversation.get('started_at'), conversation.get('finished_at')],
        'title': s.get('title') or '',
        'overview': s.get('overview') or '',
        'emoji': s.get('emoji') or '',
        'category': s.get('category') or '',
        'events': len(s.get('events') or []),
        'tasks': len(conversation.get('action_items') or []),
        'memories': len(conversation.get('memories') or []),
        'pushes': len(conversation.get('notifications') or []),
        'transcript': len(loose_text(transcript_of(conversation)).split()),
    }


def _edge_shift(a: Any, b: Any) -> float | None:
    left, right = parse_time(a), parse_time(b)
    if left is None or right is None:
        return None if (left is None) != (right is None) else 0.0
    return (left - right).total_seconds()


def boundary_moved(replay: Mapping[str, Any], production: Mapping[str, Any], method: str = 'id') -> bool:
    if method == 'overlap':
        return True
    for name in ('started_at', 'finished_at'):
        shift = _edge_shift(replay.get(name), production.get(name))
        if shift is None or abs(shift) > BOUNDARY_TOLERANCE_S:
            return True
    return False


def _text_field(replay: str, production: str) -> dict[str, Any] | None:
    if replay == production:
        return None
    if loose_text(replay) == loose_text(production):
        return {'class': 'cosmetic', 'what': 'format'}
    size = edit_size(replay, production)
    return {'class': 'substantive', 'what': 'rewritten' if size['edit_ratio'] >= REWRITE_RATIO else 'edited', **size}


def classify_pair(
    replay: Mapping[str, Any], production: Mapping[str, Any], *, method: str = 'id'
) -> dict[str, dict[str, Any]]:
    """``{field: {class, ...}}`` for every field that differs between a 1:1 pair."""
    out: dict[str, dict[str, Any]] = {}
    r_home, p_home = on_home(replay), on_home(production)
    if r_home != p_home:
        out['home'] = {'class': 'substantive', 'what': 'added' if r_home else 'dropped'}
    elif not r_home and home_reason(replay) != home_reason(production):
        out['home_reason'] = {'class': 'cosmetic'}
    if bool(replay.get('discarded')) != bool(production.get('discarded')):
        out['discarded'] = {'class': 'substantive'}
    if boundary_moved(replay, production, method):
        out['boundary'] = {
            'class': 'substantive',
            'start_shift_s': _edge_shift(replay.get('started_at'), production.get('started_at')),
            'end_shift_s': _edge_shift(replay.get('finished_at'), production.get('finished_at')),
        }
    rs, ps = replay.get('structured') or {}, production.get('structured') or {}
    for name in ('title', 'overview'):
        found = _text_field(str(rs.get(name) or ''), str(ps.get(name) or ''))
        if found:
            out[name] = found
    for name in ('emoji', 'category'):
        if str(rs.get(name) or '') != str(ps.get(name) or ''):
            out[name] = {'class': 'cosmetic'}
    if _events(rs) != _events(ps):
        out['events'] = {
            'class': 'substantive',
            'replay': len(rs.get('events') or []),
            'production': len(ps.get('events') or []),
        }
    elif rs.get('events') != ps.get('events') and (rs.get('events') or ps.get('events')):
        out['events'] = {'class': 'cosmetic'}
    for name, (field, text_of) in ITEM_FIELDS.items():
        found = item_diff(replay.get(field) or [], production.get(field) or [], text_of)
        if found['added'] or found['removed'] or found['edited']:
            out[name] = {'class': 'substantive', **found}
        elif found['cosmetic']:
            out[name] = {'class': 'cosmetic', **found}
    r_text, p_text = transcript_of(replay), transcript_of(production)
    if r_text != p_text:
        if loose_text(r_text) == loose_text(p_text):
            out['transcript'] = {'class': 'cosmetic'}
        else:
            out['transcript'] = {'class': 'substantive', **edit_size(r_text, p_text)}
    return {name: out[name] for name in FIELDS if name in out}


def compare_pair(
    replay: Mapping[str, Any] | None, production: Mapping[str, Any] | None, *, method: str = 'id'
) -> dict[str, Any]:
    """One matched pair: ``status`` (same / cosmetic / changed / discard flipped / new / missing) and fields."""
    if replay is None:
        return {'status': 'missing', 'changed_fields': [], 'fields': {}, 'diff': {}}
    if production is None:
        return {'status': 'new', 'changed_fields': [], 'fields': {}, 'diff': {}}
    fields = classify_pair(replay, production, method=method)
    left, right = comparable(replay), comparable(production)
    diff = {name: {'replay': left.get(name), 'production': right.get(name)} for name in fields}
    substantive = [n for n, f in fields.items() if f['class'] == 'substantive']
    if 'discarded' in fields:
        status = 'discard flipped'
    elif substantive:
        status = 'changed'
    elif fields:
        status = 'cosmetic'
    else:
        status = 'same'
    return {
        'status': status,
        'changed_fields': list(fields),
        'substantive_fields': substantive,
        'cosmetic_fields': [n for n in fields if n not in substantive],
        'fields': fields,
        'diff': diff,
        'label': 'vs production',
    }


# ---- groups ---------------------------------------------------------------------------------


def _seconds(span: tuple[datetime, datetime] | None) -> float:
    return max(1.0, (span[1] - span[0]).total_seconds()) if span else 1.0


def strong_links(
    replay: Sequence[Mapping[str, Any]], prod_by_id: Mapping[str, Mapping[str, Any]]
) -> list[tuple[str, str]]:
    """The ``baseline_id`` / ``baseline_ids`` links that join a group.

    A v3 window shares recordings with every production window cut from the same recording, so
    joining on every link chains a whole afternoon into one group. A link joins when it is either
    conversation's largest overlap, or the overlap covers at least :data:`LINK_COVER` of the shorter
    of the two. Weaker links stay in the data (the conversation page still lists those twins).
    """
    links: list[tuple[str, str, float, float]] = []
    for r in replay:
        rid = str(r['id'])
        for bid in dict.fromkeys([r.get('baseline_id'), *(r.get('baseline_ids') or [])]):
            if not bid or str(bid) not in prod_by_id:
                continue
            p = prod_by_id[str(bid)]
            sa, sb = _span(r), _span(p)
            overlap = max(0.0, (min(sa[1], sb[1]) - max(sa[0], sb[0])).total_seconds()) if sa and sb else 0.0
            links.append((rid, str(bid), overlap, overlap / min(_seconds(sa), _seconds(sb))))
    best: dict[str, tuple[float, tuple[str, str]]] = {}
    for rid, pid, overlap, _cover in links:
        for node in ('r:' + rid, 'p:' + pid):
            if node not in best or overlap > best[node][0]:
                best[node] = (overlap, (rid, pid))
    keep = {edge for _overlap, edge in best.values()}
    keep.update((rid, pid) for rid, pid, _overlap, cover in links if cover >= LINK_COVER)
    return sorted(keep)


def _components(
    replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]], matches: Sequence[Match]
) -> list[tuple[list[str], list[str]]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    prod_by_id = {str(p['id']): p for p in production}
    for r in replay:
        find('r:' + str(r['id']))
    for p in production:
        find('p:' + str(p['id']))
    for m in matches:
        if m.replay_id and m.baseline_id:
            union('r:' + m.replay_id, 'p:' + m.baseline_id)
    for rid, pid in strong_links(replay, prod_by_id):
        union('r:' + rid, 'p:' + pid)
    members: dict[str, tuple[list[str], list[str]]] = {}
    for node in list(parent):
        prods, reps = members.setdefault(find(node), ([], []))
        (prods if node.startswith('p:') else reps).append(node[2:])
    return list(members.values())


def _kind_of(n_prod: int, n_replay: int, pair: Mapping[str, Any] | None) -> str:
    if n_prod == 0:
        return 'new'
    if n_replay == 0:
        return 'missing'
    if n_prod == 1 and n_replay == 1:
        status = (pair or {}).get('status')
        if status == 'same':
            return 'same'
        if status == 'cosmetic':
            return 'cosmetic'
        return 'content'
    if n_replay == 1:
        return 'merge'
    if n_prod == 1:
        return 'split'
    return 'regroup'


def _shift_words(seconds: float | None) -> str:
    if seconds is None:
        return '?'
    sign = '+' if seconds > 0 else '−'
    value = abs(seconds)
    if value >= 90:
        return f'{sign}{round(value / 60)}m'
    return f'{sign}{round(value)}s'


def _items_words(name: str, found: Mapping[str, Any]) -> list[str]:
    noun = {'tasks': 'task', 'memories': 'memory', 'pushes': 'push'}[name]
    plural = {'task': 'tasks', 'memory': 'memories', 'push': 'pushes'}

    def n(count: int) -> str:
        return noun if count == 1 else plural[noun]

    out = []
    if found.get('added'):
        out.append(f"+{found['added']} {n(found['added'])}")
    if found.get('removed'):
        out.append(f"−{found['removed']} {n(found['removed'])}")
    if found.get('edited'):
        out.append(f"{found['edited']} {n(found['edited'])} reworded")
    return out


COSMETIC_WORDS = {
    'emoji': 'emoji',
    'category': 'category',
    'home_reason': 'hidden reason',
    'title': 'title punctuation',
    'overview': 'overview punctuation',
    'events': 'event wording',
    'tasks': 'task punctuation',
    'memories': 'memory punctuation',
    'pushes': 'push punctuation',
    'transcript': 'transcript punctuation',
}


def change_line(kind: str, fields: Mapping[str, Mapping[str, Any]], n_prod: int, n_replay: int) -> str:
    """One line saying exactly what changed, for the list under the replay cell."""
    parts: list[str] = []
    home = fields.get('home')
    if home:
        parts.append('now on Home' if home.get('what') == 'added' else 'dropped off Home')
    if kind == 'new':
        parts.insert(0, 'only in replay')
    elif kind == 'missing':
        parts.insert(0, 'not in replay')
    elif kind in ('merge', 'split', 'regroup'):
        verb = {'merge': 'merged', 'split': 'split', 'regroup': 'regrouped'}[kind]
        parts.insert(0, f'{n_prod} → {n_replay} {verb}')
    if 'discarded' in fields:
        parts.append('discard flipped')
    boundary = fields.get('boundary')
    if boundary:
        edges = [
            f'{edge} {_shift_words(boundary.get(f"{edge}_shift_s"))}'
            for edge in ('start', 'end')
            if boundary.get(f'{edge}_shift_s') is None or abs(boundary[f'{edge}_shift_s']) > BOUNDARY_TOLERANCE_S
        ]
        parts.append('edges moved: ' + ', '.join(edges) if edges else 'paired by overlap')
    for name in ('title', 'overview'):
        found = fields.get(name)
        if found and found['class'] == 'substantive':
            if found['what'] == 'rewritten':
                parts.append(f'{name} rewritten')
            else:
                words = found.get('words_changed') or 0
                parts.append(f"{name} edited ({words} word{'s' if words != 1 else ''})")
    events = fields.get('events')
    if events and events['class'] == 'substantive':
        parts.append('events differ')
    for name in ('tasks', 'memories', 'pushes'):
        found = fields.get(name)
        if found and found['class'] == 'substantive':
            parts.extend(_items_words(name, found))
    transcript = fields.get('transcript')
    if transcript and transcript['class'] == 'substantive' and not boundary:
        parts.append('transcript differs')
    if parts:
        return ' · '.join(parts)
    cosmetic = [COSMETIC_WORDS.get(n, n) for n, f in fields.items() if f['class'] == 'cosmetic']
    if cosmetic:
        return ' + '.join(cosmetic) + ' only'
    return 'identical'


def _score(kind: str, fields: Mapping[str, Mapping[str, Any]], n_prod: int, n_replay: int) -> float:
    """ "Most different": Home flip > grouping > content edit size > counts. Higher is more different."""
    score = 0.0
    if 'home' in fields:
        score += 1000
    if kind in GROUPING_KINDS:
        score += 300 + 10 * min(abs(n_prod - n_replay) + min(n_prod, n_replay), 20)
    if 'discarded' in fields:
        score += 200
    if 'boundary' in fields:
        score += 100
    for name, weight in (('title', 40), ('overview', 60)):
        found = fields.get(name)
        if found and found['class'] == 'substantive':
            score += 20 + weight * float(found.get('edit_ratio') or 0)
    events = fields.get('events')
    if events and events['class'] == 'substantive':
        score += 15
    for name in ('tasks', 'memories', 'pushes'):
        found = fields.get(name)
        if found and found['class'] == 'substantive':
            score += 5 * (found.get('added', 0) + found.get('removed', 0) + found.get('edited', 0))
    transcript = fields.get('transcript')
    if transcript and transcript['class'] == 'substantive':
        score += 5 * float(transcript.get('edit_ratio') or 0)
    if score == 0 and fields:
        score = 0.5  # cosmetic only
    return round(score, 3)


def _tags(kind: str, fields: Mapping[str, Mapping[str, Any]], home: Mapping[str, int]) -> list[str]:
    tags: list[str] = []
    if home['production'] and not home['replay']:
        tags.append('home_dropped')
    elif home['replay'] and not home['production']:
        tags.append('home_added')
    elif home['replay'] and home['production']:
        tags.append('home_both')
    if kind in GROUPING_KINDS:
        tags.append(kind)
    substantive = {n for n, f in fields.items() if f['class'] == 'substantive'}
    if 'boundary' in substantive:
        tags.append('boundary')
    if substantive & {'title', 'overview'}:
        tags.append('summary')
    for name in ('events', 'tasks', 'memories', 'pushes'):
        if name in substantive:
            tags.append(name)
    if 'transcript' in substantive and 'boundary' not in substantive:
        tags.append('transcript')
    if 'discarded' in substantive:
        tags.append('discard')
    if kind == 'cosmetic':
        tags.append('cosmetic')
    if kind == 'same':
        tags.append('same')
    # Worth a look = what can change what the owner sees: a Home flip; tasks, memories, pushes or
    # events (they surface outside Home); or a regrouping / content change on a conversation that is
    # on Home on either side. Regrouping and rewrites that stay hidden on both sides are reachable
    # under "Everything" (on the first real day they were 60+ of 76 groups).
    on_home = bool(home['production'] or home['replay'])
    worth = (
        bool({'home_dropped', 'home_added'} & set(tags))
        or bool(substantive & {'events', 'tasks', 'memories', 'pushes', 'discarded'})
        or (on_home and (kind in GROUPING_KINDS or bool(substantive)))
    )
    if worth:
        tags.insert(0, 'worth')
    return tags


def _group_fields(
    replays: Sequence[Mapping[str, Any]], prods: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Fields compared across a merge / split / regroup: Home and the union of each side's items."""
    out: dict[str, dict[str, Any]] = {}
    r_home = any(on_home(c) for c in replays)
    p_home = any(on_home(c) for c in prods)
    if r_home != p_home and replays and prods:
        out['home'] = {'class': 'substantive', 'what': 'added' if r_home else 'dropped'}
    for name, (field, text_of) in ITEM_FIELDS.items():
        found = item_diff(
            [i for c in replays for i in c.get(field) or []], [i for c in prods for i in c.get(field) or []], text_of
        )
        if found['added'] or found['removed'] or found['edited']:
            out[name] = {'class': 'substantive', **found}
    return out


def _new_or_missing_fields(conversations: Sequence[Mapping[str, Any]], side: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if any(on_home(c) for c in conversations):
        out['home'] = {'class': 'substantive', 'what': 'added' if side == 'replay' else 'dropped'}
    for name, (field, _text_of) in ITEM_FIELDS.items():
        count = sum(len(c.get(field) or []) for c in conversations)
        if count:
            out[name] = {
                'class': 'substantive',
                'replay': count if side == 'replay' else 0,
                'production': count if side == 'production' else 0,
                'added': count if side == 'replay' else 0,
                'removed': count if side == 'production' else 0,
                'edited': 0,
                'cosmetic': 0,
            }
    return out


def _start_key(conv: Mapping[str, Any]) -> tuple[str, str]:
    return (conv.get('started_at') or '', str(conv.get('id')))


def build_groups(
    replay: Sequence[Mapping[str, Any]],
    production: Sequence[Mapping[str, Any]],
    matches: Sequence[Match],
    pairs: Mapping[tuple[str | None, str | None], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    replay_by_id = {str(r['id']): r for r in replay}
    prod_by_id = {str(p['id']): p for p in production}
    groups = []
    for prod_ids, replay_ids in _components(replay, production, matches):
        prods = sorted((prod_by_id[i] for i in prod_ids), key=_start_key)
        reps = sorted((replay_by_id[i] for i in replay_ids), key=_start_key)
        pair = None
        if len(prods) == 1 and len(reps) == 1:
            pair = pairs.get((str(reps[0]['id']), str(prods[0]['id'])))
            if pair is None:  # linked only through baseline_ids: classify the two directly
                pair = compare_pair(reps[0], prods[0], method='overlap')
        kind = _kind_of(len(prods), len(reps), pair)
        if pair is not None:
            fields = dict(pair.get('fields') or {})
        elif kind == 'new':
            fields = _new_or_missing_fields(reps, 'replay')
        elif kind == 'missing':
            fields = _new_or_missing_fields(prods, 'production')
        else:
            fields = _group_fields(reps, prods)
        home = {'production': sum(on_home(c) for c in prods), 'replay': sum(on_home(c) for c in reps)}
        spans = [s for s in (_span(c) for c in [*prods, *reps]) if s]
        groups.append(
            {
                'kind': kind,
                'marker': MARKERS[kind],
                'production': [str(c['id']) for c in prods],
                'replay': [str(c['id']) for c in reps],
                'started_at': min(spans)[0].isoformat() if spans else None,
                'finished_at': max(s[1] for s in spans).isoformat() if spans else None,
                'home': home,
                'fields': fields,
                'substantive': [n for n, f in fields.items() if f['class'] == 'substantive'],
                'cosmetic': [n for n, f in fields.items() if f['class'] == 'cosmetic'],
                'change': change_line(kind, fields, len(prods), len(reps)),
                'score': _score(kind, fields, len(prods), len(reps)),
                'tags': _tags(kind, fields, home),
            }
        )
    groups.sort(key=lambda g: (g['started_at'] or '', (g['replay'] or g['production'])[0]))
    for index, group in enumerate(groups):
        group['id'] = f'g{index + 1:03d}'
    return groups


def digest(
    groups: Sequence[Mapping[str, Any]], replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The "What changed" panel. Every number under ``tags`` is a count of groups carrying that tag."""
    tags = {tag: 0 for tag in TAGS}
    kinds = {kind: 0 for kind in GROUP_KINDS}
    for group in groups:
        kinds[group['kind']] += 1
        for tag in group['tags']:
            tags[tag] += 1
    return {
        'groups': len(groups),
        'tags': tags,
        'kinds': kinds,
        'home': {
            'production': sum(on_home(c) for c in production),
            'replay': sum(on_home(c) for c in replay),
        },
        'conversations': {'production': len(production), 'replay': len(replay)},
    }


def baseline_view(
    replay: Sequence[Mapping[str, Any]], production: Sequence[Mapping[str, Any]], *, min_iou: float = 0.3
) -> dict[str, Any]:
    """``runs/<run_id>/baseline.json``: pairs (``conversations``), groups and the digest.

    ``conversations`` / ``counts`` are the pair-level view kept for older readers; ``groups`` and
    ``digest`` are what the inspector shows.
    """
    replay_by_id = {str(r['id']): r for r in replay}
    prod_by_id = {str(p['id']): p for p in production}
    listed_by: dict[str, str] = {}
    for r in replay:
        for bid in r.get('baseline_ids') or []:
            listed_by.setdefault(str(bid), str(r['id']))
    matches = match_conversations(replay, production, min_iou=min_iou)
    rows = []
    pairs: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for match in matches:
        r = replay_by_id.get(match.replay_id) if match.replay_id else None
        p = prod_by_id.get(match.baseline_id) if match.baseline_id else None
        compared = compare_pair(r, p, method=match.method)
        pairs[(match.replay_id, match.baseline_id)] = compared
        row = {
            'replay_id': match.replay_id,
            'baseline_id': match.baseline_id,
            'match': match.method,
            'iou': match.iou,
            'started_at': (r or p or {}).get('started_at'),
            **compared,
        }
        if r is None and match.baseline_id in listed_by:
            row.update(status='merged', merged_into=listed_by[match.baseline_id])
        rows.append(row)
    groups = build_groups(replay, production, matches, pairs)
    group_of = {('r', i): g['id'] for g in groups for i in g['replay']}
    group_of.update({('p', i): g['id'] for g in groups for i in g['production']})
    for row in rows:
        row['group'] = group_of.get(('r', row['replay_id'])) or group_of.get(('p', row['baseline_id']))
    rows.sort(key=lambda row: (row.get('started_at') or '', row.get('replay_id') or row.get('baseline_id') or ''))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    return {
        'version': VERSION,
        'fields_compared': list(FIELDS),
        'counts': counts,
        'conversations': rows,
        'groups': groups,
        'digest': digest(groups, replay, production),
    }
