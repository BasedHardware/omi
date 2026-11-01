"""In-memory view of an owner snapshot directory (written outside Git by the prod exporter).

The snapshot holds private data: it must live outside any Git work tree with
owner-only file modes. Nothing here reads the network or a database.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORD = re.compile(r"[\w'’-]+")


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace('Z', '+00:00')
    if ' ' in text and 'T' not in text:
        text = text.replace(' ', 'T', 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def terms(text: str) -> set[str]:
    return {word.casefold() for word in WORD.findall(text or '') if len(word) > 2}


def score(query_terms: set[str], text: str) -> int:
    return len(query_terms & terms(text))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open() if line.strip()]


def _json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text()) if path.exists() else default


@dataclass
class Snapshot:
    root: Path
    profile: dict[str, Any]
    conversations: dict[str, dict[str, Any]]
    screen: list[dict[str, Any]]
    memories: list[dict[str, Any]]
    people: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    meetings: list[dict[str, Any]]
    _screen_times: list[datetime] = field(default_factory=list)

    @classmethod
    def load(cls, root: str | Path) -> 'Snapshot':
        root = Path(root)
        screen = _jsonl(root / 'screen_activity.jsonl')
        for row in screen:
            row['_at'] = parse_time(row.get('timestamp'))
        screen = sorted((row for row in screen if row['_at']), key=lambda row: row['_at'])
        snap = cls(
            root=root,
            profile=_json(root / 'profile.json', {}),
            conversations={row['id']: row for row in _jsonl(root / 'conversations.jsonl')},
            screen=screen,
            memories=[row for row in _jsonl(root / 'memories.jsonl') if not row.get('invalid_at')],
            people=[row for row in _json(root / 'people.json', []) if not row.get('is_dismissed')],
            tasks=_jsonl(root / 'action_items.jsonl'),
            meetings=_json(root / 'meetings.json', []),
        )
        snap._screen_times = [row['_at'] for row in screen]
        return snap

    @property
    def owner_name(self) -> str:
        profile_text = (self.profile.get('ai_user_profile') or {}).get('profile_text') or ''
        match = re.search(r'-\s*([A-Z][\w-]+(?:\s+[A-Z][\w-]+)+)', profile_text)
        return match.group(1) if match else 'the user'

    @property
    def profile_text(self) -> str:
        return (self.profile.get('ai_user_profile') or {}).get('profile_text') or ''

    def person_name(self, person_id: str | None) -> str | None:
        for person in self.people:
            if person.get('id') == person_id:
                return person.get('name')
        return None

    def screen_between(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        lo = bisect_left(self._screen_times, start)
        hi = bisect_right(self._screen_times, end)
        return self.screen[lo:hi]

    def frames(self, conversation_id: str) -> list[dict[str, Any]]:
        folder = self.root / 'screen_frames' / conversation_id
        frames = _json(folder / 'frames.json', [])
        for frame in frames:
            image = folder / f"{frame.get('id')}.jpg"
            frame['_image'] = str(image) if image.exists() else None
        return sorted(frames, key=lambda frame: str(frame.get('captured_at') or ''))

    def frame_image(self, frame_id: str) -> Path | None:
        for image in (self.root / 'screen_frames').glob(f'*/{frame_id}.jpg'):
            return image
        return None

    def window(self, conversation: dict[str, Any]) -> tuple[datetime, datetime]:
        start = parse_time(conversation.get('started_at')) or parse_time(conversation.get('created_at'))
        end = parse_time(conversation.get('finished_at')) or start
        return start, end
