"""Export runtime-recorded Firestore query shapes and index-service verdicts.

Runs every registered query driver against the in-memory recording fake, then
emits a deterministic JSON artifact: schema version, driver summary, and one
entry per recorded terminal shape with its candidate/required index spec,
service verdict, uncertainty flag, and originating driver/combo metadata.

The same module provides ``evaluate_shapes``/``format_guard_failure``, the
zero-serving-debt guard core used by
``tests/unit/test_firestore_query_shapes.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.support.firestore_index_rules import (
    IndexSpec,
    is_served,
    required_index,
    resolved_candidate_index,
)
from tests.support.firestore_query_driver_registry import COVERED_BY, DRIVERS, SKIPS
from tests.support.firestore_query_drivers import DriverResult, calling_key, run_all_drivers, shape_id
from tests.support.firestore_shape_recorder import QueryShape, _encode_value

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / 'firestore.indexes.json'


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text())


def run_drivers() -> dict[str, DriverResult]:
    """Execute the whole registry once and return per-function results."""
    return run_all_drivers(DRIVERS)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def shape_verdict(shape: QueryShape, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the export verdict for one recorded shape."""
    spec = resolved_candidate_index(shape, manifest)
    required = required_index(shape)
    encoded = shape.to_dict()
    return {
        'id': shape_id(shape),
        'signature': json.loads(shape.signature()),
        'shape': encoded,
        'calling_function': shape.calling_function,
        'driver_function': shape.driver_function,
        'parameter_combo': encoded['parameter_combo'],
        'candidate_index': spec.to_dict(),
        'required_index': required.to_dict() if required is not None else None,
        'served': is_served(shape, manifest),
        'serving': shape.serving,
        'uncertain': spec.uncertain,
        'reason': spec.reason,
    }


def build_export(results: Mapping[str, DriverResult], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Assemble the deterministic export payload."""
    entries: list[dict[str, Any]] = []
    driver_summary: list[dict[str, Any]] = []
    for key in sorted(results):
        result = results[key]
        driver_summary.append(
            {
                'function': key,
                'shapes': len(result.shapes),
                'profiles': sorted(
                    {
                        shape.parameter_combo['caller_profile']
                        for shape in result.shapes
                        if 'caller_profile' in shape.parameter_combo
                    }
                ),
                'errors': [
                    {'combo': {name: _encode_value(value) for name, value in e.combo.items()}, 'error': e.error}
                    for e in result.errors
                ],
            }
        )
        for shape in result.shapes:
            entries.append(shape_verdict(shape, manifest))
    entries.sort(key=_canonical)
    unique = {entry['id'] for entry in entries}
    return {
        'schema_version': SCHEMA_VERSION,
        'counts': {
            'drivers': len(results),
            'covered_by': len(COVERED_BY),
            'skips': len(SKIPS),
            'shapes': len(entries),
            'unique_shapes': len(unique),
            'unserved_certain': sum(1 for e in entries if e['serving'] and not e['served'] and not e['uncertain']),
            'unserved_uncertain': sum(1 for e in entries if e['serving'] and not e['served'] and e['uncertain']),
            'unserved_nonserving': sum(1 for e in entries if not e['serving'] and not e['served']),
        },
        'drivers': driver_summary,
        'shapes': entries,
    }


def ledger_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Ledger row: stable id, signature, and the index that would serve the shape."""
    spec: IndexSpec | None = None
    required = entry.get('required_index')
    spec_dict = required if required is not None else entry['candidate_index']
    row = {
        'id': entry['id'],
        'shape': entry['signature'],
        'required_index': spec_dict,
    }
    if entry.get('uncertain'):
        row['reason'] = entry.get('reason', '')
    return row


def evaluate_shapes(entries: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Compute the zero-serving-debt verdict from exported shape entries.

    Returns ``{'known_gaps': {id: row}, 'uncertain': {id: row},
    'nonserving': {id: row}}``. Only unserved shapes appear. Entries recorded
    under a ``serving=False`` caller profile never count as debt — they are
    reported separately so an explicitly non-serving row is still visible. A
    serving entry always wins over a non-serving entry sharing its stable id,
    and a certain serving gap wins over an uncertain one.
    """
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for entry in entries:
        if entry['served']:
            continue
        groups.setdefault(entry['id'], []).append(entry)
    known_gaps: dict[str, dict[str, Any]] = {}
    uncertain: dict[str, dict[str, Any]] = {}
    nonserving: dict[str, dict[str, Any]] = {}
    for entry_id, members in groups.items():
        serving = [member for member in members if member.get('serving', True)]
        if not serving:
            nonserving[entry_id] = ledger_entry(members[0])
            continue
        representative = next((member for member in serving if not member['uncertain']), serving[0])
        row = ledger_entry(representative)
        if representative['uncertain']:
            uncertain[entry_id] = row
        else:
            known_gaps[entry_id] = row
    return {'known_gaps': known_gaps, 'uncertain': uncertain, 'nonserving': nonserving}


def _signature_id(signature: Any) -> str:
    return hashlib.sha256(json.dumps(signature, sort_keys=True).encode('utf-8')).hexdigest()[:16]


def format_guard_failure(computed: Mapping[str, dict[str, Any]]) -> str:
    """Render the zero-serving-debt verdict; empty string means no debt.

    Every serving unserved row and every serving unresolved-uncertain row is a
    failure with its full row metadata. Explicitly non-serving unserved rows
    are not debt — ``format_nonserving_rows`` reports them separately; there is
    no allowlist or debt baseline.
    """
    parts = []
    if computed['known_gaps']:
        parts.append('UNSERVED serving shapes (declare an index or remove the query):')
        parts.extend(
            f'  {gap_id}: {json.dumps(row, sort_keys=True)}' for gap_id, row in sorted(computed['known_gaps'].items())
        )
    if computed['uncertain']:
        parts.append('UNRESOLVED uncertain serving shapes (resolve the index story — may require oracle evidence):')
        parts.extend(
            f'  {gap_id}: {json.dumps(row, sort_keys=True)}' for gap_id, row in sorted(computed['uncertain'].items())
        )
    return '\n'.join(parts)


def format_nonserving_rows(computed: Mapping[str, dict[str, Any]]) -> str:
    """Informational listing of explicitly non-serving unserved rows."""
    return '\n'.join(
        f'  {gap_id}: {json.dumps(row, sort_keys=True)}' for gap_id, row in sorted(computed['nonserving'].items())
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, help='write the full export JSON to this path')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    results = run_drivers()
    errors = [f'{key}: {e.error}' for key, res in results.items() for e in res.errors]
    if errors:
        for line in errors[:20]:
            print(f'driver error: {line}', file=sys.stderr)
        return 2

    payload = build_export(results, manifest)
    text = json.dumps(payload, indent=2, sort_keys=True) + '\n'
    if args.export:
        args.export.write_text(text)
        print(f'wrote {args.export} ({payload["counts"]["shapes"]} shapes)')
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
