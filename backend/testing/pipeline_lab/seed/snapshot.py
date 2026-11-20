"""Read an owner snapshot directory in the ``fetch-owner-audio`` exporter format.

Layout (from the exporter's ``snapshot()``; values are decoded product reads, with
datetimes as ISO strings and bytes reduced to ``{"_bytes": n}`` markers):

    manifest.json          {uid_prefix, window:{start,end,days}, created_at, source_commit, counts}
    profile.json           users/{uid} root document
    conversations.jsonl    get_conversations(include_discarded=True) rows
    screen_activity.jsonl  screen activity rows
    memories.jsonl         MemoryService.iter_portability_export_memories rows
    people.json            get_people(include_dismissed=True)
    action_items.jsonl     iter_all_action_items rows
    goals.json             get_all_goals(include_inactive=True)
    daily_summaries.json   get_daily_summaries(window)
    meetings.json          list_meetings(window)
    screen_frames/<cid>/   optional frames metadata + JPGs (never read here)

This reader never prints or logs content. Missing optional files read as empty.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

JSONL_FILES = ('conversations', 'screen_activity', 'memories', 'action_items')
JSON_LIST_FILES = ('people', 'goals', 'daily_summaries', 'meetings')


class SnapshotError(ValueError):
    pass


class SnapshotReader:
    def __init__(self, root: Path):
        self.root = Path(root)
        if not (self.root / 'manifest.json').is_file():
            raise SnapshotError('snapshot directory has no manifest.json')

    def manifest(self) -> dict[str, Any]:
        return json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))

    def profile(self) -> dict[str, Any]:
        path = self.root / 'profile.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def _jsonl(self, name: str) -> Iterator[dict[str, Any]]:
        path = self.root / f'{name}.jsonl'
        if not path.exists():
            return
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)

    def _json_list(self, name: str) -> list[dict[str, Any]]:
        path = self.root / f'{name}.json'
        if not path.exists():
            return []
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, list):
            raise SnapshotError(f'{name}.json must hold a list')
        return value

    def conversations(self) -> Iterator[dict[str, Any]]:
        return self._jsonl('conversations')

    def memories(self) -> Iterator[dict[str, Any]]:
        return self._jsonl('memories')

    def action_items(self) -> Iterator[dict[str, Any]]:
        return self._jsonl('action_items')

    def screen_activity(self) -> Iterator[dict[str, Any]]:
        return self._jsonl('screen_activity')

    def people(self) -> list[dict[str, Any]]:
        return self._json_list('people')

    def goals(self) -> list[dict[str, Any]]:
        return self._json_list('goals')

    def daily_summaries(self) -> list[dict[str, Any]]:
        return self._json_list('daily_summaries')

    def meetings(self) -> list[dict[str, Any]]:
        return self._json_list('meetings')
