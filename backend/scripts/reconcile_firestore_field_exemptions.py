#!/usr/bin/env python3
"""Detect or explicitly apply generated Firestore single-field index exemptions."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.reconcile_firestore_indexes import DEFAULT_DATABASE, verify_manifest_source  # noqa: E402

APPLY_CONFIRMATION = 'APPLY_FIRESTORE_FIELD_EXEMPTIONS'
CommandRunner = Callable[..., Any]


@dataclass(frozen=True, order=True)
class FieldExemption:
    collection_group: str
    field_path: str


def expected_field_exemptions(manifest: Mapping[str, Any]) -> tuple[FieldExemption, ...]:
    """Return the narrow exemption shape this destructive tool is allowed to apply."""

    overrides = manifest.get('fieldOverrides')
    if not isinstance(overrides, list):
        raise ValueError('Firestore manifest must contain a fieldOverrides list')

    exemptions: list[FieldExemption] = []
    for position, override in enumerate(overrides):
        if not isinstance(override, Mapping):
            raise ValueError(f'Firestore field override {position} must be an object')
        collection_group = override.get('collectionGroup')
        field_path = override.get('fieldPath')
        indexes = override.get('indexes')
        ttl = override.get('ttl', False)
        if not isinstance(collection_group, str) or not collection_group:
            raise ValueError(f'Firestore field override {position} must contain collectionGroup')
        if not isinstance(field_path, str) or not field_path:
            raise ValueError(f'Firestore field override {position} must contain fieldPath')
        if indexes != [] or ttl is not False:
            raise ValueError(
                'Field-exemption reconciliation only supports ttl=false with indexes=[]; '
                f'unsupported override at {collection_group}.{field_path}'
            )
        exemptions.append(FieldExemption(collection_group, field_path))

    if len(set(exemptions)) != len(exemptions):
        raise ValueError('Firestore manifest contains duplicate fieldOverrides')
    return tuple(sorted(exemptions))


def gcloud_describe_command(*, project: str, database: str, exemption: FieldExemption) -> list[str]:
    return [
        'gcloud',
        'firestore',
        'indexes',
        'fields',
        'describe',
        exemption.field_path,
        f'--project={project}',
        f'--database={database}',
        f'--collection-group={exemption.collection_group}',
        '--format=json',
    ]


def gcloud_disable_command(*, project: str, database: str, exemption: FieldExemption) -> list[str]:
    return [
        'gcloud',
        'firestore',
        'indexes',
        'fields',
        'update',
        exemption.field_path,
        f'--project={project}',
        f'--database={database}',
        f'--collection-group={exemption.collection_group}',
        '--disable-indexes',
        '--quiet',
    ]


def describe_field_exemption(
    *,
    project: str,
    database: str,
    exemption: FieldExemption,
    runner: CommandRunner = subprocess.run,
) -> Mapping[str, Any]:
    result = runner(
        gcloud_describe_command(project=project, database=database, exemption=exemption),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f'Firestore field-config lookup failed for {exemption.collection_group}.{exemption.field_path}'
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f'Firestore field-config lookup returned invalid JSON for '
            f'{exemption.collection_group}.{exemption.field_path}'
        ) from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError(
            f'Firestore field-config lookup returned a non-object for '
            f'{exemption.collection_group}.{exemption.field_path}'
        )
    return payload


def field_indexes_are_disabled(field: Mapping[str, Any]) -> bool:
    """Recognize an explicit empty index config, including protobuf-elided empty lists."""

    config = field.get('indexConfig')
    if not isinstance(config, Mapping):
        return False
    indexes = config.get('indexes', [])
    return (
        indexes == [] and config.get('usesAncestorConfig', False) is False and config.get('reverting', False) is False
    )


def find_missing_exemptions(
    *,
    project: str,
    database: str,
    exemptions: tuple[FieldExemption, ...],
    runner: CommandRunner = subprocess.run,
) -> list[FieldExemption]:
    return [
        exemption
        for exemption in exemptions
        if not field_indexes_are_disabled(
            describe_field_exemption(
                project=project,
                database=database,
                exemption=exemption,
                runner=runner,
            )
        )
    ]


def apply_field_exemptions(
    *,
    project: str,
    database: str,
    exemptions: tuple[FieldExemption, ...],
    runner: CommandRunner = subprocess.run,
) -> None:
    missing = find_missing_exemptions(
        project=project,
        database=database,
        exemptions=exemptions,
        runner=runner,
    )
    for exemption in missing:
        result = runner(
            gcloud_disable_command(project=project, database=database, exemption=exemption),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f'Firestore field exemption failed for {exemption.collection_group}.{exemption.field_path}'
            )

    remaining = find_missing_exemptions(
        project=project,
        database=database,
        exemptions=exemptions,
        runner=runner,
    )
    if remaining:
        formatted = ', '.join(f'{item.collection_group}.{item.field_path}' for item in remaining)
        raise RuntimeError(f'Firestore field exemptions did not converge: {formatted}')


def reconcile(
    *,
    project: str,
    database: str,
    manifest_path: Path,
    check_only: bool = False,
    dry_run: bool = False,
    apply: bool = False,
    confirmation: str | None = None,
    runner: CommandRunner = subprocess.run,
) -> None:
    modes = sum((check_only, dry_run, apply))
    if modes != 1:
        raise ValueError('choose exactly one of --check-only, --dry-run, or --apply')
    if apply and confirmation != APPLY_CONFIRMATION:
        raise ValueError(f'--apply requires --confirmation {APPLY_CONFIRMATION}')

    manifest = verify_manifest_source(manifest_path)
    exemptions = expected_field_exemptions(manifest)
    missing = find_missing_exemptions(
        project=project,
        database=database,
        exemptions=exemptions,
        runner=runner,
    )

    if dry_run:
        for exemption in missing:
            print(
                'Firestore field-exemption dry run: would disable automatic indexes for '
                f'{exemption.collection_group}.{exemption.field_path}'
            )
        if not missing:
            print('Firestore field-exemption dry run: all declared exemptions are already applied')
        return

    if check_only:
        if missing:
            for exemption in missing:
                print(
                    '::error title=Unapplied Firestore field exemption::'
                    f'{exemption.collection_group}.{exemption.field_path} remains automatically indexed'
                )
            raise RuntimeError(
                'Declared Firestore field exemptions are not serving; dispatch gcp_firestore_indexes.yml '
                f'with operation=field-exemptions and confirmation={APPLY_CONFIRMATION}'
            )
        print('All declared Firestore field exemptions are applied')
        return

    apply_field_exemptions(
        project=project,
        database=database,
        exemptions=exemptions,
        runner=runner,
    )
    print('All declared Firestore field exemptions are applied')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--database', default=DEFAULT_DATABASE)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'firestore.indexes.json')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--confirmation')
    args = parser.parse_args()
    try:
        reconcile(
            project=args.project,
            database=args.database,
            manifest_path=args.manifest.resolve(),
            check_only=args.check_only,
            dry_run=args.dry_run,
            apply=args.apply,
            confirmation=args.confirmation,
        )
    except (RuntimeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
