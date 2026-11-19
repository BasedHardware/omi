"""Prototype: decide an hour's cards in one call, with the whole hour as context.

    python -m testing.pipeline_lab.ideal.hourpass --root ROOT --packet DIR --spec SPEC.md \\
        --upstream http://127.0.0.1:19083 --token-file FILE [--effort none] [--window-minutes 60] \\
        [--budget-usd 2] [--label NAME]

The question this answers: if, after an hour, one model call saw everything said in that hour and
decided the boundaries, Home calls, titles and key points together, how close would it get to the
reviewed ideal? It uses the production outline lane (``omi:auto:conversation-v3-outline``, the
model v3's outline uses), not a stronger model.

How it walks the day:

- A window holds every line from its start up to ``window`` later. The call sees the window's
  lines and the last few cards already decided (title, kind, Home, last lines).
- A card may say ``continues`` with an earlier card's id: its lines join that card. Earlier cards
  are only ever extended, never split (merge-only refinement).
- The window's last card is carried into the next window instead of being decided, when speech
  carries on within ``carry_gap`` of the window's end and the card is shorter than a window.
- An answer that breaks the format (a line in no card or in two, unknown ids) is sent back once
  with the validator's errors. A second failure is recorded and its uncovered lines become one
  hidden ``noise`` card, so the score shows the failure instead of hiding it.

Calls go through the lab LLM proxy: every request and response is recorded with its cost under a
run in the store, and a spend cap applies. The output is an ideal-format file the scorer reads.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any, Callable, Mapping, Sequence
import time
import urllib.error
import urllib.request

from testing.pipeline_lab.ideal.schema import CONFIDENCE, HIDDEN_REASONS, KINDS, card_lines, load_lines, validate

LANE = 'omi:auto:conversation-v3-outline'
FEATURE = 'conversation_v3_outline'
CONTEXT_CARDS = 3
CONTEXT_LINES = 4

SYSTEM = """You turn one stretch of a person's day, transcribed from an always-on wearable, into the cards their
Home screen should show. You see the whole stretch at once, plus the end of the cards decided just before it.

{spec}

## Input and output

The input is numbered transcript lines, `Lnnnn HH:MM:SS [recording] SPEAKER: text`. A line marked
"(duplicate of Lxxxx)" repeats another: leave it out of every card. EARLIER CARDS lists the most recent cards
already decided, with their last lines.

Return one JSON object, {{"cards": [...]}}, with the cards in time order. Each card has:
- "lines": the line ids it holds, as inclusive ranges and single ids, e.g. ["L0101-L0130", "L0134"]. Every
  line of this stretch that is not a duplicate belongs to exactly one card. A range must not span lines that
  belong to another card: list several ranges instead.
- "continues": the id of an EARLIER CARD this is the same sit-down as (its lines are added to that card), or null.
- "kind", "home", "hidden_reason" (null when home is true), "title", "key_points", "tasks", "people",
  "confidence" (high, medium or low) and "why" (one sentence), as the rules above describe.
Answer with the JSON object only."""


@dataclass
class Card:
    id: str
    lines: list[str]
    kind: str
    home: bool
    hidden_reason: str | None
    title: str
    key_points: list[str]
    tasks: list[str]
    people: list[str]
    confidence: str
    why: str

    def as_ideal(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'lines': _ranges(self.lines),
            'kind': self.kind,
            'home': self.home,
            'hidden_reason': None if self.home else self.hidden_reason,
            'title': self.title,
            'people': self.people,
            'key_points': self.key_points,
            'tasks': self.tasks,
            'confidence': self.confidence,
            'why': self.why,
        }


@dataclass
class WindowLog:
    window: int
    first: str
    last: str
    lines: int
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    fallback_lines: int = 0
    carried: str | None = None
    continued: list[str] = field(default_factory=list)
    normalized: int = 0
    usd: float = 0.0


def _ranges(ids: Sequence[str]) -> list[str]:
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


def render(lines: Sequence[Mapping[str, Any]]) -> str:
    return '\n'.join(
        f"{x['line']} {x['local']} [{x['recording']}] {x['speaker']}: {x['text']}"
        + (f" (duplicate of {x['dup_of']})" if x.get('dup_of') else '')
        for x in lines
    )


def context_block(cards: Sequence[Card], by_id: Mapping[str, Mapping[str, Any]]) -> str:
    if not cards:
        return 'EARLIER CARDS: none (start of the day).'
    parts = ['EARLIER CARDS:']
    for card in cards[-CONTEXT_CARDS:]:
        tail = [by_id[lid] for lid in sorted(card.lines)[-CONTEXT_LINES:]]
        where = 'on Home' if card.home else f'hidden ({card.hidden_reason})'
        parts.append(f'- id {card.id}: "{card.title}" [{card.kind}, {where}], last lines:')
        parts.extend('    ' + render([x]) for x in tail)
    return '\n'.join(parts)


def _strings(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def normalize(raw: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    """Fill fields a fast model tends to drop, counting each repair (the count is reported)."""
    fixes = 0
    card = dict(raw)
    if card.get('kind') not in KINDS:
        card['kind'] = 'conversation'
        fixes += 1
    if not isinstance(card.get('home'), bool):
        card['home'] = bool(card.get('home'))
        fixes += 1
    if card['home']:
        card['hidden_reason'] = None
        if not _strings(card.get('key_points')):
            card['key_points'] = [str(card.get('title') or 'Untitled')]
            fixes += 1
        card['key_points'] = _strings(card.get('key_points'))[:6]
        if not str(card.get('title') or '').strip():
            card['title'] = 'Untitled'
            fixes += 1
    elif card.get('hidden_reason') not in HIDDEN_REASONS:
        card['hidden_reason'] = {'media': 'media', 'background': 'background', 'noise': 'noise'}.get(
            card['kind'], 'other'
        )
        fixes += 1
    if card.get('confidence') not in CONFIDENCE:
        card['confidence'] = 'medium'
        fixes += 1
    if not str(card.get('why') or '').strip():
        card['why'] = '(no reason given)'
        fixes += 1
    for name in ('key_points', 'tasks', 'people'):
        card[name] = _strings(card.get(name))
    return card, fixes


def window_errors(cards: Sequence[Mapping[str, Any]], window: Sequence[Mapping[str, Any]]) -> list[str]:
    """The validator's errors for this window's answer (``continues`` is checked by the caller)."""
    probe = {'cards': [{**normalize(c)[0], 'id': f'w{i}'} for i, c in enumerate(cards)]}
    return validate(probe, window)


def gateway_call(proxy_url: str, messages: list[dict[str, str]], *, effort: str, tag: str) -> dict[str, Any]:
    body = {'model': LANE, 'messages': messages, 'response_format': {'type': 'json_object'}, 'stream': False}
    if effort:
        body['reasoning_effort'] = effort
    request = urllib.request.Request(
        proxy_url.rstrip('/') + '/v1/chat/completions',
        data=json.dumps(body).encode(),
        headers={
            'Content-Type': 'application/json',
            'X-Omi-Service-Caller': 'backend',
            'X-Omi-LLM-Feature': FEATURE,
            'X-Pipeline-Lab-Stage': 'hourpass',
            'X-Pipeline-Lab-Conversation': tag,
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(1, 4):
        try:
            with opener.open(request, timeout=300) as response:
                payload = json.loads(response.read())
            break
        except urllib.error.HTTPError as error:  # the proxy already retried transient answers; once more, slower
            if error.code < 500 or attempt == 3:
                raise
            time.sleep(10 * attempt)
    return json.loads(payload['choices'][0]['message']['content'] or '{}')


def run_day(
    lines: Sequence[Mapping[str, Any]],
    *,
    spec: str,
    context: Mapping[str, Any],
    ask: Callable[[list[dict[str, str]], str], dict[str, Any]],
    window: timedelta = timedelta(minutes=60),
    carry_gap: timedelta = timedelta(minutes=5),
) -> tuple[list[Card], list[WindowLog]]:
    by_id = {x['line']: x for x in lines}
    order = sorted(lines, key=lambda x: (x['at'], x['line']))
    at = {x['line']: datetime.fromisoformat(x['at']) for x in order}
    end_of = {x['line']: datetime.fromisoformat(x['end']) for x in order}
    system = SYSTEM.format(spec=spec.strip())
    people = ', '.join(context.get('known_people') or []) or 'none'
    cards: list[Card] = []
    logs: list[WindowLog] = []
    index = 0
    number = 0
    while index < len(order):
        number += 1
        start = at[order[index]['line']]
        stop = start + window
        chunk = [x for x in order[index:] if at[x['line']] < stop]
        rest = order[index + len(chunk) :]
        log = WindowLog(number, chunk[0]['line'], chunk[-1]['line'], len(chunk))
        prompt = (
            f"Day {context.get('day')}, timezone {context.get('timezone')}. People the app knows: {people}.\n\n"
            f'{context_block(cards, by_id)}\n\nTHIS STRETCH ({chunk[0]["local"]} to {chunk[-1]["local"]}):\n{render(chunk)}'
        )
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]
        answer: list[Mapping[str, Any]] = []
        known_ids = {c.id for c in cards[-CONTEXT_CARDS:]}
        for attempt in (1, 2):
            log.attempts = attempt
            raw = ask(messages, f'window-{number:02d}-a{attempt}')
            answer = [c for c in (raw.get('cards') or []) if isinstance(c, Mapping)]
            errors = window_errors(answer, chunk)
            errors += [
                f"card {i}: continues {c.get('continues')!r} is not an EARLIER CARD id"
                for i, c in enumerate(answer)
                if c.get('continues') not in (None, '') and c.get('continues') not in known_ids
            ]
            if not errors:
                break
            log.errors = errors[:20]
            messages = messages + [
                {'role': 'assistant', 'content': json.dumps(raw, ensure_ascii=False)},
                {
                    'role': 'user',
                    'content': 'That answer breaks the format:\n- '
                    + '\n- '.join(errors[:30])
                    + '\nReturn the corrected JSON object for the whole stretch.',
                },
            ]
        else:
            answer = _salvage(answer, chunk)
            log.fallback_lines = sum(len(c['lines']) for c in answer if c.get('_fallback'))
        decided: list[tuple[Card, str | None]] = []
        for raw_card in answer:
            fixed, fixes = normalize(raw_card)
            log.normalized += fixes
            ids = [lid for lid in _expand_all(fixed.get('lines')) if lid in by_id and not by_id[lid].get('dup_of')]
            if not ids:
                continue
            decided.append(
                (
                    Card(
                        id='',
                        lines=ids,
                        kind=fixed['kind'],
                        home=fixed['home'],
                        hidden_reason=fixed.get('hidden_reason'),
                        title=str(fixed.get('title') or ''),
                        key_points=fixed['key_points'],
                        tasks=fixed['tasks'],
                        people=fixed['people'],
                        confidence=fixed['confidence'],
                        why=str(fixed['why']),
                    ),
                    raw_card.get('continues') if raw_card.get('continues') in known_ids else None,
                )
            )
        decided.sort(key=lambda pair: min(pair[0].lines))
        carried: Card | None = None
        if decided and rest:
            last_card = max(decided, key=lambda pair: max(end_of[lid] for lid in pair[0].lines))[0]
            last_end = max(end_of[lid] for lid in last_card.lines)
            span = last_end - min(at[lid] for lid in last_card.lines)
            starts_window = min(last_card.lines, key=lambda lid: at[lid]) == chunk[0]['line']
            if at[rest[0]['line']] - last_end <= carry_gap and span < window and not starts_window:
                carried = last_card  # a card that starts the window is decided, so the walk always moves on
        for card, continues in decided:
            if card is carried:
                continue
            if continues:
                target = next(c for c in cards if c.id == continues)
                target.lines = sorted(set(target.lines) | set(card.lines))
                target.home = target.home or card.home
                target.key_points = (target.key_points + [p for p in card.key_points if p not in target.key_points])[:6]
                target.tasks += [t for t in card.tasks if t not in target.tasks]
                log.continued.append(continues)
                continue
            card.id = f'c{len(cards) + 1:03d}'
            cards.append(card)
        if carried is not None:
            log.carried = carried.title
            first = min(carried.lines, key=lambda lid: at[lid])
            index = next(i for i, x in enumerate(order) if x['line'] == first)
            # Lines of other cards inside the carried span are already decided; the next window repeats
            # them only as context, so they are dropped from it below.
            decided_ids = {lid for c in cards for lid in c.lines}
            order = order[:index] + [x for x in order[index:] if x['line'] not in decided_ids]
        else:
            index += len(chunk)
        logs.append(log)
    return cards, logs


def _expand_all(refs: Any) -> list[str]:
    out: list[str] = []
    for ref in refs if isinstance(refs, list) else []:
        try:
            out.extend(card_lines({'lines': [ref]}))
        except ValueError:
            continue
    return out


def _salvage(answer: Sequence[Mapping[str, Any]], chunk: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep each line's first valid owner; put uncovered lines in one hidden noise card."""
    allowed = {x['line'] for x in chunk if not x.get('dup_of')}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for card in answer:
        ids = [lid for lid in _expand_all(card.get('lines')) if lid in allowed and lid not in seen]
        seen.update(ids)
        if ids:
            out.append({**card, 'lines': ids, 'continues': None})
    missing = sorted(allowed - seen)
    if missing:
        out.append(
            {
                'lines': missing,
                'kind': 'noise',
                'home': False,
                'hidden_reason': 'other',
                'title': 'Unassigned after two invalid answers',
                'confidence': 'low',
                'why': 'fallback',
                '_fallback': True,
            }
        )
    return out


def main(argv: Sequence[str] | None = None) -> int:
    from testing.pipeline_lab import contracts as c
    from testing.pipeline_lab.ledger import SpendLedger
    from testing.pipeline_lab.llm_proxy.server import LlmProxy, ProxyConfig
    from testing.pipeline_lab.store import Store, atomic_write_json, ensure_private_dir

    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.ideal.hourpass')
    parser.add_argument('--root', required=True)
    parser.add_argument('--packet', required=True)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--token-file', required=True)
    parser.add_argument('--effort', default='none')
    parser.add_argument('--window-minutes', type=float, default=60)
    parser.add_argument('--budget-usd', type=float, default=2.0)
    parser.add_argument('--label', default='luna')
    args = parser.parse_args(argv)

    packet = Path(args.packet)
    lines = load_lines(packet)
    context = json.loads((packet / 'context.json').read_text(encoding='utf-8'))
    token = Path(args.token_file).read_text(encoding='utf-8').strip()
    store = Store(root=ensure_private_dir(Path(args.root)), verdicts_root=Path(os.devnull))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = f'{stamp}-hourpass-{context.get("day")}-{args.label}-{secrets.token_hex(3)}'
    store.create_run(c.RunRecord(run_id=run_id, day_id=str(context.get('day')), ref=f'hourpass:{LANE}'))
    ledger = SpendLedger(store.ledger_path(run_id), budget_usd=args.budget_usd)
    config = ProxyConfig(upstream=args.upstream, mode='record', run_id=run_id, upstream_token=token)
    effort_fallbacks: list[str] = []
    with LlmProxy(config, store=store, ledger=ledger) as proxy:

        def ask(messages: list[dict[str, str]], tag: str) -> dict[str, Any]:
            try:
                return gateway_call(proxy.url, messages, effort=args.effort, tag=tag)
            except urllib.error.HTTPError as error:
                # A gateway that keeps failing one request at this effort gets it once at low effort;
                # the window is reported, so a run never hides which effort decided what.
                if error.code < 500 or args.effort in ('', 'none', 'low'):
                    raise
                effort_fallbacks.append(tag)
                return gateway_call(proxy.url, messages, effort='low', tag=tag + '-low')

        cards, logs = run_day(
            lines,
            spec=Path(args.spec).read_text(encoding='utf-8'),
            context=context,
            ask=ask,
            window=timedelta(minutes=args.window_minutes),
        )
    run_dir = store.run_dir(run_id)
    ideal = {
        'day': context.get('day'),
        'author': f'hourpass:{LANE}:effort={args.effort}:window={args.window_minutes:g}m',
        'spec_version': 2,
        'cards': [card.as_ideal() for card in cards],
    }
    atomic_write_json(run_dir / 'hourpass.json', ideal)
    atomic_write_json(run_dir / 'hourpass_windows.json', [log.__dict__ for log in logs])
    errors = validate(ideal, lines)
    spend = ledger.snapshot()
    summary = {
        'run_id': run_id,
        'cards': len(cards),
        'home': sum(1 for card in cards if card.home),
        'windows': len(logs),
        'retried_windows': sum(1 for log in logs if log.attempts > 1),
        'fallback_lines': sum(log.fallback_lines for log in logs),
        'continued': sum(len(log.continued) for log in logs),
        'carried': sum(1 for log in logs if log.carried),
        'normalized_fields': sum(log.normalized for log in logs),
        'effort_fallbacks': effort_fallbacks,
        'valid': not errors,
        'errors': errors[:10],
        'usd': spend.get('committed_usd'),
        'out': str(run_dir / 'hourpass.json'),
    }
    print(json.dumps(summary, indent=1))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
