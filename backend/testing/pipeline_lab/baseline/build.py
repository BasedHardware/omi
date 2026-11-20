"""File-level entry: read a day's baseline and a run's conversations, write ``baseline.json``.

Reads ``$ROOT/corpus/<day_id>/baseline/*.jsonl`` and ``$ROOT/runs/<run_id>/conversations/*.json``
per the store contract. The normalized production conversations are also written to
``runs/<run_id>/baseline/conversations/<id>.json`` in the replay's own shape so the
inspector can diff two files of identical structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from testing.pipeline_lab.baseline.compare import baseline_view, production_view
from testing.pipeline_lab.stack.io import read_json, read_jsonl, write_json
from testing.pipeline_lab.store import safe_segment


def load_production(baseline_dir: Path, conversations_file: str = 'conversations.jsonl') -> list[dict[str, Any]]:
    """Production conversations in the replay's shape.

    ``corpus add-day`` writes ``conversations.jsonl`` already normalized (RULINGS 1) and the raw
    rows beside it; rows still in snapshot shape (``transcript_segments``) are normalized here.
    """
    baseline_dir = Path(baseline_dir)
    rows = list(read_jsonl(baseline_dir / conversations_file))
    if rows and all('segments' in row and 'transcript_segments' not in row for row in rows):
        return sorted(rows, key=lambda c: (c.get('started_at') or '', c['id']))
    return production_view(
        rows,
        memories=list(read_jsonl(baseline_dir / 'memories.jsonl')),
        action_items=list(read_jsonl(baseline_dir / 'action_items.jsonl')),
        notifications=list(read_jsonl(baseline_dir / 'notifications.jsonl')),
    )


def load_replay(run_dir: Path) -> list[dict[str, Any]]:
    return [read_json(path) for path in sorted((Path(run_dir) / 'conversations').glob('*.json'))]


def build_baseline(
    run_dir: Path, baseline_dir: Path, *, min_iou: float = 0.3, conversations_file: str = 'conversations.jsonl'
) -> dict[str, Any]:
    """``conversations_file``: ``v3_conversations.jsonl`` for a v3 run (production's v3 conversations)."""
    production = load_production(baseline_dir, conversations_file)
    replay = load_replay(run_dir)
    for conversation in production:
        name = safe_segment(str(conversation['id']), 'production conversation id')
        write_json(Path(run_dir) / 'baseline' / 'conversations' / f'{name}.json', conversation)
    view = baseline_view(replay, production, min_iou=min_iou)
    write_json(Path(run_dir) / 'baseline.json', view)
    return view
