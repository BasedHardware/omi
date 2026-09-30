"""Export runtime-recorded Firestore query shapes and index-service verdicts.

Runs every registered query driver against the in-memory recording fake, then
emits a deterministic JSON artifact: schema version, driver summary, and one
entry per recorded terminal shape with its candidate/required index spec,
service verdict, uncertainty flag, and originating driver/combo metadata.

The same module provides ``evaluate_shapes``/``compare_ledgers``, the guard
core used by ``tests/unit/test_firestore_query_shapes.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.support.firestore_index_rules import IndexSpec, candidate_index, is_served, required_index
from tests.support.firestore_query_driver_registry import COVERED_BY, DRIVERS, SKIPS
from tests.support.firestore_query_drivers import DriverResult, calling_key, run_all_drivers, shape_id
from tests.support.firestore_shape_recorder import QueryShape, _encode_value

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / 'firestore.indexes.json'
DEFAULT_LEDGER = Path(__file__).resolve().parent.parent / 'tests' / 'support' / 'firestore_query_known_gaps.json'


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    return json.loads(path.read_text())


def run_drivers() -> dict[str, DriverResult]:
    """Execute the whole registry once and return per-function results."""
    return run_all_drivers(DRIVERS)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def shape_verdict(shape: QueryShape, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the export verdict for one recorded shape."""
    spec = candidate_index(shape)
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
            'unserved_certain': sum(1 for e in entries if not e['served'] and not e['uncertain']),
            'unserved_uncertain': sum(1 for e in entries if not e['served'] and e['uncertain']),
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
    """Compute the unresolved-gap ledgers from exported shape entries.

    Returns ``{'known_gaps': {id: row}, 'uncertain': {id: row}}`` — only
    unserved shapes appear, and uncertain shapes appear only while their
    uncertainty is unresolved by a declared index.
    """
    known_gaps: dict[str, dict[str, Any]] = {}
    uncertain: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for entry in entries:
        entry_id = entry['id']
        if entry_id in seen:
            continue
        seen.add(entry_id)
        if entry['served']:
            continue
        row = ledger_entry(entry)
        if entry['uncertain']:
            uncertain[entry_id] = row
        else:
            known_gaps[entry_id] = row
    return {'known_gaps': known_gaps, 'uncertain': uncertain}


def _signature_id(signature: Any) -> str:
    return hashlib.sha256(json.dumps(signature, sort_keys=True).encode('utf-8')).hexdigest()[:16]


def _validate_ledger_row(row: Any, section: str, problems: list[str]) -> None:
    if not isinstance(row, Mapping):
        problems.append(f'{section}: non-object row {row!r}')
        return
    row_id = row.get('id')
    if not isinstance(row_id, str) or not row_id:
        problems.append(f'{section}: row missing id')
        return
    signature = row.get('shape')
    if not isinstance(signature, (dict, list)):
        problems.append(f'{section}:{row_id}: stored shape is not a canonical signature object')
    elif _signature_id(signature) != row_id:
        problems.append(f'{section}:{row_id}: id does not match the canonical signature hash')
    if 'required_index' not in row:
        problems.append(f'{section}:{row_id}: missing required_index spec')
    if section == 'uncertain' and not str(row.get('reason', '')).strip():
        problems.append(f'{section}:{row_id}: missing uncertainty reason')


def compare_ledgers(
    computed: Mapping[str, dict[str, Any]],
    ledger: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Diff the recorded-shape ledgers against the checked-in ledger.

    Full row metadata is compared in both sections: the canonical signature,
    the index spec that would serve it, and the uncertainty reason. Each
    failure class is its own section so the guard message states exactly which
    maintenance action is required; there are no broad waivers.
    """
    sections: dict[str, list[str]] = {
        'invalid_ledger': [],
        'new_gaps': [],
        'stale_gaps': [],
        'changed_required': [],
        'changed_shape': [],
        'new_uncertain': [],
        'stale_uncertain': [],
        'changed_uncertain': [],
    }
    if ledger.get('schema_version') != SCHEMA_VERSION:
        sections['invalid_ledger'].append(f'schema_version {ledger.get("schema_version")!r} != {SCHEMA_VERSION}')

    ledger_gaps: dict[str, Any] = {}
    ledger_uncertain: dict[str, Any] = {}
    for section_name, target in (('known_gaps', ledger_gaps), ('uncertain', ledger_uncertain)):
        for row in ledger.get(section_name, ()) or ():
            _validate_ledger_row(row, section_name, sections['invalid_ledger'])
            if isinstance(row, Mapping):
                row_id = row.get('id')
                if row_id in target:
                    sections['invalid_ledger'].append(f'{section_name}: duplicate id {row_id}')
                else:
                    target[row_id] = row
    for gap_id in ledger_gaps.keys() & ledger_uncertain.keys():
        sections['invalid_ledger'].append(f'id {gap_id} present in both ledger sections')

    computed_gaps = computed['known_gaps']
    computed_uncertain = computed['uncertain']
    for gap_id, row in computed_gaps.items():
        stored = ledger_gaps.get(gap_id)
        if stored is None:
            sections['new_gaps'].append(gap_id)
            continue
        if stored.get('shape') != row.get('shape'):
            sections['changed_shape'].append(gap_id)
        elif stored.get('required_index') != row.get('required_index'):
            sections['changed_required'].append(gap_id)
    for gap_id in ledger_gaps:
        if gap_id not in computed_gaps:
            sections['stale_gaps'].append(gap_id)
    for gap_id, row in computed_uncertain.items():
        stored = ledger_uncertain.get(gap_id)
        if stored is None:
            sections['new_uncertain'].append(gap_id)
            continue
        if stored.get('shape') != row.get('shape'):
            sections['changed_shape'].append(gap_id)
        elif stored.get('required_index') != row.get('required_index'):
            sections['changed_required'].append(gap_id)
        elif stored.get('reason', '') != row.get('reason', ''):
            sections['changed_uncertain'].append(gap_id)
    for gap_id in ledger_uncertain:
        if gap_id not in computed_uncertain:
            sections['stale_uncertain'].append(gap_id)
    return sections


def format_guard_failure(sections: Mapping[str, list[str]]) -> str:
    labels = {
        'invalid_ledger': 'INVALID ledger rows (fix the checked-in ledger by hand; ids must match canonical signature hashes)',
        'new_gaps': 'NEW unserved shapes (declare a composite index — new queries cannot be added to the existing debt)',
        'stale_gaps': 'STALE ledger gaps (now served or no longer recorded — prune the ledger row)',
        'changed_required': 'CHANGED required index for an existing ledger id (declare the new index or review the shape change)',
        'changed_shape': 'CHANGED shape under an existing ledger id (review the query change; the recorded shape no longer matches the stored row)',
        'new_uncertain': 'NEW unresolved uncertainty (resolve the index story — may require oracle evidence — then ledger it)',
        'stale_uncertain': 'RESOLVED uncertainties still in the ledger (declare verified, then prune the row)',
        'changed_uncertain': 'CHANGED uncertainty metadata under an existing id (review the flag/reason change)',
    }
    parts = []
    for key, ids in sections.items():
        if ids:
            parts.append(f'{labels[key]}: {sorted(ids)}')
    return '\n'.join(parts)


def build_ledger(computed: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        'schema_version': SCHEMA_VERSION,
        'known_gaps': [computed['known_gaps'][k] for k in sorted(computed['known_gaps'])],
        'uncertain': [computed['uncertain'][k] for k in sorted(computed['uncertain'])],
    }


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
