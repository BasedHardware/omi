#!/usr/bin/env python3
"""Read-only side-by-side for the notes-first episode composer (Fable LLM-efficiency #3).

Composes an owner's recent closed episodes twice -- once with today's full-transcript
prompt and once with the notes-first prompt plus the bounded transcript-excerpt tool --
and writes a private text diff. It never writes to Firestore, never schedules a compose
and never calls ``composer.compose``. It does spend two model calls per episode.

Run it only on an account whose owner approved this read (David approved his own
account for the 2026-11-10 ramp review). Do not run it on any other account.

    cd backend
    .venv/bin/python scripts/episode_composer_notes_first_diff.py --uid <uid> --limit 5

The output file is created with mode 0600 under ``~/.omi-private`` by default.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database._client import get_firestore_client  # noqa: E402
from utils.episodes import composer, home_read, service  # noqa: E402


def _render(updates: Mapping[str, Any]) -> str:
    """A stable text view of the composed page, for a human diff."""
    lines = [f"TITLE: {updates.get('title') or ''}", f"LEDE: {updates.get('lede') or ''}"]
    follow_ups = updates.get('follow_ups') or []
    if follow_ups:
        lines.append('FOLLOW-UPS:')
        lines.extend(f'  - {item}' for item in follow_ups)
    for moment in updates.get('moments') or []:
        lines.append(f"CHAPTER {moment.get('started_at')} - {moment.get('ended_at')}: {moment.get('heading') or ''}")
        for point in moment.get('points') or []:
            lines.append(f"  * {point.get('text') or ''}")
            for detail in point.get('details') or []:
                lines.append(f"      - {detail}")
    return '\n'.join(lines)


def _language(episode: Mapping[str, Any]) -> str:
    language = str(episode.get('output_language') or 'English')
    return {'en': 'English'}.get(language, language)


def _compose_full(uid: str, members: list[dict[str, Any]], *, owner: str, tz: ZoneInfo, language: str):
    messages = composer.build_messages(members, owner=owner, tz=tz, language=language)
    reply = composer.invoke_model(uid, messages)
    data = composer.parse(composer._content(reply))
    input_tokens, output_tokens = composer._usage(reply)
    return composer.to_updates(data, members, tz), input_tokens, output_tokens, 0


def _compose_notes_first(uid: str, members: list[dict[str, Any]], *, owner: str, tz: ZoneInfo, language: str):
    data, reply, input_tokens, output_tokens, tool_calls = composer._compose_notes_first(
        uid, members, owner=owner, tz=tz, language=language, invoke=composer.invoke_model
    )
    return composer.to_updates(data, members, tz), input_tokens, output_tokens, tool_calls


def _private_path(uid: str) -> Path:
    digest = hashlib.sha256(uid.encode()).hexdigest()[:12]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return Path.home() / '.omi-private' / f'episode-composer-notes-first-{digest}-{stamp}.txt'


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uid', required=True, help='Owner uid. Only run on an account whose owner approved the read.')
    parser.add_argument('--limit', type=int, default=5, help='Maximum closed episodes to compare (default 5).')
    parser.add_argument('--days', type=int, default=7, help='Look back this many days (default 7).')
    parser.add_argument('--out', type=Path, default=None, help='Private output path (default ~/.omi-private/...).')
    parser.add_argument('--plan', action='store_true', help='List the episodes that would be compared; no model calls.')
    args = parser.parse_args(argv)

    client = get_firestore_client()
    now = datetime.now(timezone.utc)
    rows, _ = home_read.list_episode_window(
        args.uid, now - timedelta(days=args.days), now, limit=max(args.limit * 4, 20), firestore_client=client
    )
    episodes = [row for row in rows if str(row.get('status') or '') == 'closed'][: args.limit]
    if not episodes:
        print('No closed episodes in the window.')
        return 0
    if args.plan:
        for episode in episodes:
            print(f"{episode.get('id')}  {episode.get('started_at')}  {episode.get('title') or ''}")
        return 0

    c = service.Collaborators(firestore_client=client)
    try:
        tz = ZoneInfo(service._tz(args.uid, c))
    except Exception:
        tz = ZoneInfo('UTC')
    owner = service._owner_name(args.uid, c)

    sections: list[str] = []
    totals = {'full': 0, 'notes_first': 0, 'tool_calls': 0}
    for episode in episodes:
        state, members = composer._members(args.uid, episode, c)
        if state != 'ok' or not members:
            sections.append(f"=== {episode.get('id')} skipped: members not ready ({state}) ===")
            continue
        language = _language(episode)
        full, full_in, full_out, _ = _compose_full(args.uid, members, owner=owner, tz=tz, language=language)
        notes, notes_in, notes_out, tool_calls = _compose_notes_first(
            args.uid, members, owner=owner, tz=tz, language=language
        )
        totals['full'] += full_in
        totals['notes_first'] += notes_in
        totals['tool_calls'] += tool_calls
        diff = difflib.unified_diff(
            _render(full).splitlines(),
            _render(notes).splitlines(),
            fromfile='full-transcript',
            tofile='notes-first',
            lineterm='',
        )
        sections.append(
            '\n'.join(
                [
                    f"=== {episode.get('id')}  {episode.get('started_at')}  {episode.get('title') or ''} ===",
                    f'members={len(members)}  input_tokens full={full_in} notes_first={notes_in}  '
                    f'output_tokens full={full_out} notes_first={notes_out}  tool_calls={tool_calls}',
                    '',
                    *diff,
                ]
            )
        )

    header = [
        'Episode composer notes-first side-by-side (read-only; no Firestore writes)',
        f"uid_sha256_12={hashlib.sha256(args.uid.encode()).hexdigest()[:12]}  episodes={len(episodes)}",
        f"input_tokens full={totals['full']} notes_first={totals['notes_first']}  "
        f"tool_calls={totals['tool_calls']}",
        '',
    ]
    out = args.out or _private_path(args.uid)
    _write_private(out, '\n'.join(header + sections) + '\n')
    print(f'Wrote {out} (mode 0600).')
    print(
        f"input_tokens full={totals['full']} notes_first={totals['notes_first']} " f"tool_calls={totals['tool_calls']}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
