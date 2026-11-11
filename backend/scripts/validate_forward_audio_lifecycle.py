"""Offline guard for new-bucket policies and their separation from prod stock; never mutates GCS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

if __package__:
    from .validate_storage_lifecycle import validate_desired_document
else:
    from validate_storage_lifecycle import validate_desired_document

RELEASE = '20261015-v1'
ROOT = Path(__file__).resolve().parents[1] / 'deploy' / 'storage-lifecycle'


def validate(document: dict[str, Any], *, canonical: bool) -> list[str]:
    errors = []
    for key, value in {
        'release': RELEASE,
        'newBucketOnly': True,
        'location': 'us-central1',
        'storageClass': 'STANDARD',
        'versioning': {'enabled': False},
        'softDeletePolicy': {'retentionDurationSeconds': '0'},
    }.items():
        if document.get(key) != value:
            errors.append(f'{key} does not match the new regional bucket contract')
    if canonical:
        expected = [
            {
                'action': {'type': 'SetStorageClass', 'storageClass': destination},
                'condition': {
                    'age': age,
                    'matchesPrefix': [f'canonical-packs-{RELEASE}/'],
                    'matchesStorageClass': [source],
                },
            }
            for age, source, destination in [(30, 'STANDARD', 'COLDLINE'), (120, 'COLDLINE', 'ARCHIVE')]
        ]
    else:
        expected = [
            {'action': {'type': 'Delete'}, 'condition': {'age': age, 'matchesPrefix': [f'{prefix}-{RELEASE}/']}}
            for prefix, age in [('staging', 1), ('merged', 3), ('playback', 30)]
        ]
    if document.get('lifecycle') != {'rule': expected}:
        errors.append('lifecycle rules must exactly match release-scoped forward policy')
    return errors


def main() -> int:
    errors = []
    for filename, canonical in [('canonical-forward.json', True), ('cache-forward.json', False)]:
        errors.extend(validate(json.loads((ROOT / filename).read_text()), canonical=canonical))
    # Forward Archive is for new empty regional buckets only. Also check the
    # existing-stock contract so this source gate cannot endorse a prod Archive
    # transition that David dropped on 2026-11-02.
    errors.extend(validate_desired_document(json.loads((ROOT / 'prod.json').read_text())))
    for error in errors:
        print(f'ERROR: {error}')
    if not errors:
        print('forward audio and prod lifecycle contracts passed (source only; forward requires new empty buckets)')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
