"""Condense screen-activity rows from a meeting window into prompt-sized evidence.

Pure: no I/O. Real OCR from a browser session is dominated by chrome that repeats
on every frame (the tab strip, bookmarks, "Ask Gemini"), so a naive first-N-chars
render spends the whole budget on text that identifies nothing. The useful signal
is usually the set of distinct windows (a LinkedIn profile opened from the invite,
a shared doc) plus the OCR fragments that are NOT repeated across frames.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Optional

from utils.conversations.meeting_participants import clean_display_title

MAX_TITLES = 20
MAX_TITLE_CHARACTERS = 1_000
_FRAGMENT_SPLIT = re.compile(r'\s*(?:[•·|\n]|\s{2,}| - | — )\s*')
_TITLE_NOISE = (
    re.compile(r'\s*-\s*High memory usage\s*-\s*[\d.]+\s*[KMG]B', re.IGNORECASE),
    re.compile(r'^\(\d+\)\s*'),
)
_MIN_FRAGMENT = 3
# Private chat OCR is almost never meeting content and is the most sensitive text
# on screen; keep only these apps' window titles.
_MESSAGING_APPS = frozenset(
    {'telegram', 'slack', 'discord', 'whatsapp', 'messages', 'signal', 'wechat', 'messenger', 'line', 'mail'}
)
_CALL_TITLES = ('Google Meet call', 'Zoom call', 'Microsoft Teams call')


def _clean_title(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    text = str(title)
    for pattern in _TITLE_NOISE:
        text = pattern.sub('', text)
    return clean_display_title(text, screen_derived=True)


def _fragments(ocr: str) -> list[str]:
    return [part.strip() for part in _FRAGMENT_SPLIT.split(ocr) if len(part.strip()) >= _MIN_FRAGMENT]


def digest_screen_rows(rows: Iterable[Any], budget: int) -> str:
    """Return distinct window titles first, then OCR with frame-repeated chrome removed."""
    materialized = [row for row in rows if isinstance(row, Mapping)]
    if not materialized or budget <= 0:
        return ''

    titles: list[str] = []
    seen_titles: set[str] = set()
    for row in materialized:
        app = str(row.get('appName') or '').strip()
        title = _clean_title(row.get('windowTitle'))
        label = ' | '.join(part for part in (app, title) if part)
        key = label.casefold()
        if not title or key in seen_titles:
            continue
        seen_titles.add(key)
        titles.append(label)
        if len(titles) >= MAX_TITLES:
            break

    per_row = [_fragments(re.sub(r'[ \t]+', ' ', str(row.get('ocrText') or ''))) for row in materialized]
    frequency: dict[str, int] = {}
    for fragments in per_row:
        for fragment in set(fragment.casefold() for fragment in fragments):
            frequency[fragment] = frequency.get(fragment, 0) + 1
    # Chrome repeats on most frames; keep anything seen in fewer than ~40% of them.
    threshold = max(3, int(len(materialized) * 0.4))

    residuals: list[tuple[int, str, str]] = []
    kept: list[str] = []
    for row, fragments in zip(materialized, per_row):
        app_name = str(row.get('appName') or '').strip()
        clean_title = _clean_title(row.get('windowTitle')) or ''
        is_call = any(clean_title.startswith(call) for call in _CALL_TITLES)
        if app_name.casefold() in _MESSAGING_APPS and not is_call:
            continue
        residual = ' · '.join(f for f in fragments if frequency.get(f.casefold(), 0) < threshold)
        if len(residual) < 12:
            continue
        key = residual.casefold()[:400]
        if any(SequenceMatcher(None, key, prior).ratio() > 0.85 for prior in kept):
            continue
        kept.append(key)
        header = ' | '.join(part for part in (app_name, clean_title) if part)
        residuals.append((0 if is_call else 1, header, residual))
    residuals.sort(key=lambda item: (item[0], -len(item[2])))

    parts: list[str] = []
    used = 0
    if titles:
        block = 'Windows open during the meeting:\n' + '\n'.join(f'- {title}' for title in titles)
        block = block[:MAX_TITLE_CHARACTERS]
        parts.append(block)
        used += len(block) + 2
    snippets: list[str] = []
    for _, header, residual in residuals:
        chunk = f'[{header}] {residual[:500]}' if header else residual[:500]
        if used + len(chunk) + 1 > budget:
            continue
        snippets.append(chunk)
        used += len(chunk) + 1
    if snippets:
        parts.append('On-screen text (repeated browser chrome removed):\n' + '\n'.join(snippets))
    return '\n\n'.join(parts)[:budget]
