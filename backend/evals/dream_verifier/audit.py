"""Blind label reconciliation. Only aggregate disagreement counts leave CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.dream_verifier.contracts import digest


def read_labels(path: Path, expected: set[str]) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len({row['id'] for row in rows}) != len(rows) or {row['id'] for row in rows} != expected:
        raise ValueError('audit_ids_must_match_exactly_once')
    if any(row['label'] not in {'accept', 'reject', 'uncertain'} or not row.get('reason', '').strip() for row in rows):
        raise ValueError('audit_incomplete_labels_or_reasons')
    return {row['id']: row for row in rows}


def reconcile(items: list[dict[str, Any]], left: Path, right: Path, adjudication: Path | None = None) -> dict[str, Any]:
    expected = {item['id'] for item in items}
    a, b = read_labels(left, expected), read_labels(right, expected)
    disputed = {
        item['id']
        for item in items
        if a[item['id']]['label'] != b[item['id']]['label']
        or a[item['id']]['label'] == 'uncertain'
        or a[item['id']]['label'] != item['gold']
    }
    resolved = {}
    if adjudication:
        resolved = read_labels(adjudication, disputed)
        if any(row['label'] == 'uncertain' for row in resolved.values()):
            raise ValueError('david_adjudication_still_uncertain')
    # A change to gold requires a new dataset/manifest, not a silent overwrite.
    gold_changes = sum(
        resolved[key]['label'] != next(item['gold'] for item in items if item['id'] == key) for key in resolved
    )
    return {
        'dataset_sha256': digest(items),
        'items': len(items),
        'disagreements': len(disputed),
        'adjudicated': len(resolved),
        'gold_changes_required': gold_changes,
        'audit_complete': len(resolved) == len(disputed) and not gold_changes,
        'reviewers': ['luna', 'grok'],
        'adjudicator': 'David' if adjudication else None,
    }
