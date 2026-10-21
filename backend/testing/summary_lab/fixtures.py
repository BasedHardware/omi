"""Synthetic conversation fixtures. No customer transcripts, no PII."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures'


@dataclass(frozen=True)
class Fixture:
    id: str
    kind: str
    started_at: str
    timezone: str
    language: str
    transcript: str
    expected_facts: tuple[str, ...]
    must_not_contain: tuple[str, ...]
    owner_threads: tuple[str, ...]
    recorded: dict[str, dict[str, Any]]
    token_estimate: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'kind': self.kind,
            'started_at': self.started_at,
            'timezone': self.timezone,
            'language': self.language,
            'transcript': self.transcript,
            'expected_facts': list(self.expected_facts),
            'must_not_contain': list(self.must_not_contain),
            'owner_threads': list(self.owner_threads),
            'recorded': self.recorded,
            'token_estimate': dict(self.token_estimate),
        }


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def load_fixture(path: Path) -> Fixture:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not payload.get('id'):
        raise ValueError(f'invalid fixture: {path}')
    recorded = payload.get('recorded') or {}
    if not isinstance(recorded, dict):
        raise ValueError(f'invalid recorded map: {path}')
    token_estimate = payload.get('token_estimate') or {'input': 0, 'output': 0}
    if not isinstance(token_estimate, dict):
        raise ValueError(f'invalid token_estimate: {path}')
    return Fixture(
        id=str(payload['id']),
        kind=str(payload.get('kind') or 'conversation'),
        started_at=str(payload.get('started_at') or ''),
        timezone=str(payload.get('timezone') or 'UTC'),
        language=str(payload.get('language') or 'en'),
        transcript=str(payload.get('transcript') or ''),
        expected_facts=_as_str_tuple(payload.get('expected_facts')),
        must_not_contain=_as_str_tuple(payload.get('must_not_contain')),
        owner_threads=_as_str_tuple(payload.get('owner_threads')),
        recorded={str(key): value for key, value in recorded.items() if isinstance(value, dict)},
        token_estimate={
            'input': int(token_estimate.get('input') or 0),
            'output': int(token_estimate.get('output') or 0),
        },
    )


def load_synthetic_fixtures(directory: Path | None = None) -> tuple[Fixture, ...]:
    root = directory or FIXTURE_DIR
    paths = sorted(root.glob('*.json'))
    if not paths:
        raise FileNotFoundError(f'no synthetic fixtures in {root}')
    return tuple(load_fixture(path) for path in paths)
