"""The compact episode state: what the cheap per-moment update reads and returns.

Pure: no I/O. The state is a few hundred tokens (topic, running bullets,
people, open questions, provisional items). The incremental update never sees
an earlier transcript, only this state plus the newest moment's text, so the
cost of a moment does not grow with the episode.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from config.episodes import (
    MAX_BULLETS,
    MAX_HEADING_CHARS,
    MAX_ITEM_CHARS,
    MAX_OPEN_QUESTIONS,
    MAX_PEOPLE,
    MAX_PROVISIONAL_ITEMS,
    MAX_STATE_CHARS,
    MAX_TOPIC_CHARS,
)

from utils.speakers.display import sanitize_speaker_text

ITEM_KINDS = frozenset({'task', 'reminder'})
_SPACE = re.compile(r'\s+')


def clean_text(value: Any, limit: int) -> str:
    """One line, trimmed, bounded. Non-strings become empty."""
    if not isinstance(value, str):
        return ''
    text = _SPACE.sub(' ', sanitize_speaker_text(value)).strip().strip('•-* ').strip()
    return text[:limit].rstrip()


def _clean_list(values: Any, *, limit: int, chars: int) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value, chars)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def new_item_id() -> str:
    return 'p' + uuid.uuid4().hex[:11]


def _parse_due(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass
class IncrementalUpdate:
    """A validated model answer for one moment."""

    title: str = ''
    moment_heading: str = ''
    bullets: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    new_items: list[dict[str, Any]] = field(default_factory=list)
    edits: dict[str, dict[str, Any]] = field(default_factory=dict)
    drop_ids: set[str] = field(default_factory=set)


class InvalidUpdate(ValueError):
    """The model answer is not the JSON object the prompt asked for."""


def parse_update(raw: str, *, known_item_ids: Sequence[str]) -> IncrementalUpdate:
    """Parse and bound the model's JSON. Unknown item ids are ignored, never invented."""
    text = str(raw)
    try:
        start, end = text.index('{'), text.rindex('}') + 1
        data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as error:
        raise InvalidUpdate('not a JSON object') from error
    if not isinstance(data, dict):
        raise InvalidUpdate('not a JSON object')
    known = set(known_item_ids)
    update = IncrementalUpdate(
        title=clean_text(data.get('title'), MAX_TOPIC_CHARS),
        moment_heading=clean_text(data.get('moment_heading'), MAX_HEADING_CHARS),
        bullets=_clean_list(data.get('bullets'), limit=MAX_BULLETS, chars=MAX_ITEM_CHARS),
        people=[name for name in _clean_list(data.get('people'), limit=MAX_PEOPLE, chars=60) if name != 'a speaker'],
        open_questions=_clean_list(data.get('open_questions'), limit=MAX_OPEN_QUESTIONS, chars=MAX_ITEM_CHARS),
    )
    drops = data.get('drop_ids')
    if isinstance(drops, list):
        update.drop_ids = {item for item in drops if isinstance(item, str) and item in known}
    items = data.get('items')
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        body = clean_text(item.get('text'), MAX_ITEM_CHARS)
        if not body:
            continue
        kind = item.get('kind') if item.get('kind') in ITEM_KINDS else 'task'
        parsed = {
            'text': body,
            'kind': kind,
            'explicit': item.get('explicit') is True,
            'due_at': _parse_due(item.get('due')),
        }
        item_id = item.get('id')
        if isinstance(item_id, str) and item_id in known:
            if item_id not in update.drop_ids:
                update.edits[item_id] = parsed
        elif not item_id:
            update.new_items.append(parsed)
    return update


def provisional_items(episode: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = episode.get('provisional_items')
    return [dict(item) for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []


def render_state(episode: Optional[Mapping[str, Any]]) -> str:
    """The compact state the model reads back. Volatile, so it goes after the fixed prefix."""
    if not episode:
        return '{}'
    open_items = [
        {'id': item['id'], 'text': clean_text(item.get('text', ''), MAX_ITEM_CHARS), 'kind': item.get('kind', 'task')}
        for item in provisional_items(episode)
        if item.get('status') == 'provisional' and isinstance(item.get('id'), str)
    ]
    state = {
        'topic': clean_text(episode.get('title'), MAX_TOPIC_CHARS),
        'bullets': _clean_list(episode.get('bullets'), limit=MAX_BULLETS, chars=MAX_ITEM_CHARS),
        'people': [
            name for name in _clean_list(episode.get('people'), limit=MAX_PEOPLE, chars=60) if name != 'a speaker'
        ],
        'open_questions': _clean_list(episode.get('open_questions'), limit=MAX_OPEN_QUESTIONS, chars=MAX_ITEM_CHARS),
        'items': open_items,
    }
    rendered = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
    # Bullets are the only part that can push past the budget; shed the oldest first.
    while len(rendered) > MAX_STATE_CHARS and state['bullets']:
        state['bullets'] = state['bullets'][1:]
        rendered = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
    return rendered[:MAX_STATE_CHARS]


def apply_update(
    episode: Mapping[str, Any],
    update: IncrementalUpdate,
    *,
    conversation_id: str,
    segment_offset: Optional[float],
    now: datetime,
) -> dict[str, Any]:
    """Fold one moment's answer into the stored state. Returns only the changed fields."""
    items = provisional_items(episode)
    for item in items:
        item_id = item.get('id')
        if item.get('status') != 'provisional':
            continue
        if item_id in update.drop_ids:
            item['status'] = 'dropped'
        elif item_id in update.edits:
            edit = update.edits[item_id]
            item.update({key: value for key, value in edit.items() if value is not None or key == 'due_at'})
    existing = {clean_text(item.get('text'), MAX_ITEM_CHARS).casefold() for item in items}
    for new in update.new_items:
        if len(items) >= MAX_PROVISIONAL_ITEMS:
            break
        if new['text'].casefold() in existing:
            continue
        existing.add(new['text'].casefold())
        items.append(
            {
                'id': new_item_id(),
                'status': 'provisional',
                'conversation_id': conversation_id,
                'segment_offset': segment_offset,
                'created_at': now,
                'action_item_id': None,
                **new,
            }
        )
    people = list(update.people)
    for name in episode.get('people') or []:
        if len(people) >= MAX_PEOPLE:
            break
        if isinstance(name, str) and name.casefold() not in {p.casefold() for p in people}:
            people.append(name)
    changed: dict[str, Any] = {
        'bullets': update.bullets or list(episode.get('bullets') or []),
        'people': people,
        'open_questions': update.open_questions,
        'provisional_items': items,
        'state_updated_at': now,
    }
    if update.title:
        changed['title'] = update.title
    return changed
