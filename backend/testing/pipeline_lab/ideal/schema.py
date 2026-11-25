"""The ideal file format, and its validator.

    python -m testing.pipeline_lab.ideal.schema --packet DIR IDEAL.json

An ideal is one JSON object::

    {
      "day": "2026-11-18",
      "author": "fable",                 # who drafted it: a model name, "merged" or "reviewed"
      "spec_version": 1,                 # the SPEC.md version it follows
      "cards": [
        {
          "id": "c001",
          "lines": ["L0001-L0012", "L0015"],   # inclusive ranges and single ids from lines.jsonl
          "kind": "conversation",              # conversation | voice_work | media | background | noise
          "home": true,                        # shown on Home in the ideal
          "hidden_reason": null,               # when home is false: too_short | media | background | noise | other
          "title": "Product reliability and fundraising",
          "people": [],
          "key_points": ["...", "..."],        # what the card must convey (1-6 when on Home)
          "tasks": ["..."],                    # tasks the wearer would want created, may be []
          "confidence": "high",                # high | medium | low
          "why": "One or two sentences on the boundary and Home call."
        }
      ]
    }

Rules the validator enforces: every line that is not a duplicate (``dup_of``) belongs to exactly
one card, duplicates belong to none, ranges name real lines in order, and the per-field rules above.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence

KINDS = ('conversation', 'voice_work', 'media', 'background', 'noise')
HIDDEN_REASONS = ('too_short', 'media', 'background', 'noise', 'other')
CONFIDENCE = ('high', 'medium', 'low')
_LINE = re.compile(r'^L(\d{4,})$')
_RANGE = re.compile(r'^L(\d{4,})\s*-\s*L(\d{4,})$')
MAX_ERRORS = 60


def load_lines(packet: Path) -> list[dict[str, Any]]:
    return [json.loads(row) for row in (Path(packet) / 'lines.jsonl').read_text(encoding='utf-8').splitlines() if row]


def expand(ref: str, width: int = 4) -> list[str]:
    """``"L0003-L0005"`` -> ``["L0003", "L0004", "L0005"]``; a single id -> itself. Raises ValueError."""
    ref = str(ref).strip()
    single = _LINE.match(ref)
    if single:
        return [ref]
    span = _RANGE.match(ref)
    if not span:
        raise ValueError(f'not a line id or range: {ref!r}')
    first, last = int(span.group(1)), int(span.group(2))
    if last < first:
        raise ValueError(f'range runs backwards: {ref!r}')
    width = max(width, len(span.group(1)))
    return [f'L{n:0{width}d}' for n in range(first, last + 1)]


def card_lines(card: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for ref in card.get('lines') or []:
        out.extend(expand(ref))
    return out


def validate(ideal: Mapping[str, Any], lines: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    known = {str(line['line']): line for line in lines}
    duplicates = {lid for lid, line in known.items() if line.get('dup_of')}
    owner: dict[str, str] = {}
    cards = ideal.get('cards')
    if not isinstance(cards, list) or not cards:
        return ['"cards" must be a non-empty list']
    seen_ids: set[str] = set()
    for index, card in enumerate(cards):
        cid = str(card.get('id') or f'#{index}')
        where = f'card {cid}'
        if cid in seen_ids:
            errors.append(f'{where}: duplicate id')
        seen_ids.add(cid)
        try:
            ids = card_lines(card)
        except ValueError as error:
            errors.append(f'{where}: {error}')
            continue
        if not ids:
            errors.append(f'{where}: no lines')
        for lid in ids:
            if lid not in known:
                errors.append(f'{where}: unknown line {lid}')
            elif lid in duplicates:
                errors.append(f'{where}: {lid} is a duplicate of {known[lid]["dup_of"]}; leave it out')
            elif lid in owner:
                errors.append(f'{where}: {lid} is already in card {owner[lid]}')
            else:
                owner[lid] = cid
        kind = card.get('kind')
        if kind not in KINDS:
            errors.append(f'{where}: kind {kind!r} not in {KINDS}')
        home = card.get('home')
        if not isinstance(home, bool):
            errors.append(f'{where}: home must be true or false')
        elif home:
            if card.get('hidden_reason') not in (None, ''):
                errors.append(f'{where}: on Home, so hidden_reason must be null')
            if not str(card.get('title') or '').strip():
                errors.append(f'{where}: on Home, so it needs a title')
            points = card.get('key_points')
            if not isinstance(points, list) or not 1 <= len(points) <= 6:
                errors.append(f'{where}: on Home, so it needs 1-6 key_points')
        elif card.get('hidden_reason') not in HIDDEN_REASONS:
            errors.append(f'{where}: hidden, so hidden_reason must be one of {HIDDEN_REASONS}')
        for name in ('key_points', 'tasks', 'people'):
            value = card.get(name, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f'{where}: {name} must be a list of strings')
        if card.get('confidence') not in CONFIDENCE:
            errors.append(f'{where}: confidence must be one of {CONFIDENCE}')
        if not str(card.get('why') or '').strip():
            errors.append(f'{where}: why is empty')
    missing = [lid for lid in known if lid not in owner and lid not in duplicates]
    if missing:
        errors.append(f'{len(missing)} line(s) in no card, e.g. {", ".join(_runs(missing)[:8])}')
    return errors


def _runs(ids: Iterable[str]) -> list[str]:
    """Compress sorted line ids into ``L0001-L0004`` runs for messages."""
    numbers = sorted(int(lid[1:]) for lid in ids)
    out: list[str] = []
    start = prev = None
    for n in numbers:
        if prev is not None and n == prev + 1:
            prev = n
            continue
        if start is not None:
            out.append(f'L{start:04d}' if start == prev else f'L{start:04d}-L{prev:04d}')
        start = prev = n
    if start is not None:
        out.append(f'L{start:04d}' if start == prev else f'L{start:04d}-L{prev:04d}')
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.schema')
    parser.add_argument('--packet', required=True)
    parser.add_argument('ideal')
    args = parser.parse_args(argv)
    try:
        ideal = json.loads(Path(args.ideal).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        print(f'cannot read {args.ideal}: {error}', file=sys.stderr)
        return 1
    errors = validate(ideal, load_lines(Path(args.packet)))
    if errors:
        for line in errors[:MAX_ERRORS]:
            print(line)
        if len(errors) > MAX_ERRORS:
            print(f'... and {len(errors) - MAX_ERRORS} more')
        print(f'INVALID: {len(errors)} error(s)')
        return 1
    cards = ideal['cards']
    print(f'VALID: {len(cards)} cards, {sum(1 for c in cards if c.get("home"))} on Home')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
