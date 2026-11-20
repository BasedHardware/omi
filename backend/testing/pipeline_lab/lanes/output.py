"""Ingest hand-off to the chain lane: one JSON file per conversation, no imports.

Path: ``$ROOT/runs/<run_id>/ingest/<conversation_id>.json`` plus
``ingest/index.json``. Field names follow the store contract's conversation
record (``segments``, ``evaluable``, ``started_at``/``finished_at``, ``lane``);
segment ``start``/``end`` are seconds from ``started_at``, as production stores
``transcript_segments``. ``driver.production`` and ``driver.simulated`` list,
per conversation, which steps ran product code and which the lab stood in for.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from testing.pipeline_lab.store import atomic_write_json, lab_root, safe_segment

SCHEMA = 'pipeline_lab.ingest/v1'


@dataclass
class IngestResult:
    id: str
    lane: str
    started_at: str | None
    finished_at: str | None
    outcome: str  # transcript | silence | failed
    segments: list[dict] = field(default_factory=list)
    language: str | None = None
    baseline_id: str | None = None
    boundaries: dict = field(default_factory=dict)
    evaluable: dict = field(default_factory=lambda: {'boundaries': False, 'reason': 'unknown'})
    stt: dict = field(default_factory=dict)
    driver: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def speakers(self) -> list[str]:
        return sorted({s['speaker'] for s in self.segments if s.get('speaker')})

    def to_json(self) -> dict:
        value = asdict(self)
        value['schema'] = SCHEMA
        value['speakers'] = self.speakers
        return value


def contract_segment(segment: Any, *, offset: float = 0.0) -> dict:
    """A product ``TranscriptSegment`` (or dict) -> store-contract segment."""
    get = (
        (lambda k, d=None: segment.get(k, d))
        if isinstance(segment, dict)
        else (lambda k, d=None: getattr(segment, k, d))
    )
    return {
        'start': round(float(get('start')) + offset, 3),
        'end': round(float(get('end')) + offset, 3),
        'speaker': get('speaker'),
        'speaker_name': get('speaker_name'),
        'is_user': bool(get('is_user', False)),
        'text': get('text') or '',
    }


def ingest_dir(run_id: str, root=None) -> Path:
    return lab_root(root) / 'runs' / safe_segment(run_id, 'run id') / 'ingest'


def write_results(run_id: str, results: list[IngestResult], root=None) -> Path:
    directory = ingest_dir(run_id, root)
    for result in results:
        atomic_write_json(directory / f"{safe_segment(result.id, 'conversation id')}.json", result.to_json())
    index = [
        {
            'id': r.id,
            'lane': r.lane,
            'outcome': r.outcome,
            'segments': len(r.segments),
            'driver': r.driver.get('name'),
            'stt_mode': r.stt.get('mode'),
        }
        for r in results
    ]
    return atomic_write_json(directory / 'index.json', {'schema': SCHEMA, 'conversations': index})
