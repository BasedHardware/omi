"""Pure, bounded screen selection. Speech is never truncated or deduplicated."""

import json
import re
from typing import Any, Sequence

_WORDS = re.compile(r'[^\W\d_]{4,}', re.UNICODE)
_CALL = re.compile(r'\b(joined|joining|waiting|participant|microphone|muted|call ended|left the call)\b', re.I)
_STOP = {'this', 'that', 'with', 'from', 'have', 'will', 'what', 'your', 'they', 'there', 'about', 'would', 'could'}
_SCREEN = {'screen_frame', 'screen_ocr', 'message'}


def episode_words(text: str) -> set[str]:
    return set(_WORDS.findall(text.casefold())) - _STOP


def compact_episode_items(items: Sequence[Any]) -> list[Any]:
    """Prefer connected observations, preserving original IDs, times and attribution.

    A lexical match ranks retrieval, never proves a connection. The model still
    adjudicates it. Unknown/solo screens retain a small exploration allowance.
    New lines in successive OCR observations survive; only repeated lines go.
    """
    speech = ' '.join(item.content for item in items if item.source_kind == 'speech')
    words = episode_words(speech)
    people = {item.actor.casefold() for item in items if item.actor and item.source_kind in {'speech', 'roster'}}
    screens = [item for item in items if item.source_kind in _SCREEN]
    scored = []
    for index, item in enumerate(screens):
        folded = item.content.casefold()
        score = 3 * bool(_CALL.search(folded)) + 3 * any(
            re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', folded) for name in people
        )
        score += min(3, len(episode_words(item.content) & words))
        scored.append((score, index, item))
    # Bound overall screen volume, prioritizing connected surfaces over incidental
    # windows. Speech/context are retained independently of this allocation.
    selected = {}
    budget = 12000
    exploratory = 1200
    seen_lines: dict[str, set[str]] = {}
    for score, index, item in sorted(scored, key=lambda entry: (-entry[0], entry[1])):
        try:
            data = json.loads(item.content)
        except (TypeError, ValueError):
            data = None
        field = next(
            (key for key in ('ocr', 'ocrText', 'summary', 'text', 'content') if isinstance(data, dict) and key in data),
            None,
        )
        text = str(data[field]) if isinstance(data, dict) and field is not None else item.content
        # Scope chrome removal to the same window/app, never to other sources.
        surface = (
            str((data.get('app'), data.get('window'), data.get('visible_names'), data.get('role')))
            if isinstance(data, dict)
            else item.source_kind
        )
        lines = text.splitlines()
        previous = seen_lines.setdefault(surface, set())
        fresh = [line for line in lines if re.sub(r'\s+', ' ', line).strip().casefold() not in previous]
        normalized = {re.sub(r'\s+', ' ', line).strip().casefold() for line in lines if line.strip()}
        if normalized and not fresh:
            continue
        cap = min(budget, 3000 if score >= 2 else min(400, exploratory))
        if cap <= 0:
            continue
        body = '\n'.join(fresh)[:cap]
        if len(body) < len('\n'.join(fresh)):
            body += '\n[observation text truncated]'
        if isinstance(data, dict) and field is not None:
            data = dict(data)
            data[field] = body
            content = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        else:
            content = body
        if not content.strip():
            continue
        selected[item.id] = item.model_copy(update={'content': content})
        previous.update(normalized)
        budget -= len(content)
        if score < 2:
            exploratory -= len(content)
    # Preserve original chronology and alias stability for the retained evidence.
    return [
        selected[item.id] if item.id in selected else item
        for item in items
        if item.source_kind not in _SCREEN or item.id in selected
    ]


def compact_evidence_rows(items: Sequence[Any]) -> list[dict]:
    """Wire abbreviations only; durable evidence metadata stays unchanged."""
    keys = {
        'source_kind': 'k',
        'time': 'at',
        'actor': 'a',
        'diarization_key': 'd',
        'source_ref': 'r',
        'wake_word_invocation': 'w',
        'content': 'c',
    }
    rows = []
    for index, item in enumerate(items):
        data = item.model_dump(exclude_none=True)
        if not item.wake_word_invocation:
            data.pop('wake_word_invocation', None)
        if item.source_kind != 'speech':
            data.pop('source_ref', None)
        rows.append({'id': f'evidence:{index}', **{keys[key]: value for key, value in data.items() if key != 'id'}})
    return rows
