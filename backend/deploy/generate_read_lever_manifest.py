#!/usr/bin/env python3
"""Record source-effective Firestore read levers; never choose rollout values."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterator

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from config.firestore_read_levers import DEFAULT_PERCENTAGES, ENV_KEY, KNOWN_LEVERS  # noqa: E402
from deploy import compose_runtime_env as composer  # noqa: E402
from scripts.runtime_env_validation.common import _literal_env_value  # noqa: E402

OUTPUT = BACKEND / 'deploy/firestore_read_levers_manifest.json'
POLICY_KEY = 'firestore_read_lever_policy'
CHARTS = ('batch-pipeline-worker', 'backend-listen', 'pusher')


def parse_levers(raw: str, surface: str) -> dict[str, int]:
    """Reject declarations the runtime would silently ignore or turn off."""
    values = json.loads(raw)
    if not isinstance(values, dict):
        raise ValueError(f'{surface}: {ENV_KEY} must be a JSON object')
    for lever, value in values.items():
        if lever not in KNOWN_LEVERS:
            raise ValueError(f'{surface}: unknown lever {lever}')
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(f'{surface}: invalid percentage for {lever}')
    return values


def effective_levers(explicit: dict[str, int]) -> dict[str, int]:
    return {lever: explicit.get(lever, DEFAULT_PERCENTAGES.get(lever, 0)) for lever in sorted(KNOWN_LEVERS)}


def literal_entries(doc: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[str, dict]]:
    """Walk all env blocks, including jobs and desktop, without another YAML parser."""
    if isinstance(doc, dict):
        if ENV_KEY in doc:
            yield '/'.join(path), doc[ENV_KEY]
        for key, value in doc.items():
            yield from literal_entries(value, (*path, str(key)))


def chart_literal(doc: Any) -> str:
    """Find either the worker string setting or the serving chart's env-list entry."""
    matches: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if 'firestoreReadLevers' in node:
                matches.append(node['firestoreReadLevers'])
            if node.get('name') == ENV_KEY:
                matches.append(_literal_env_value(node))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(doc)
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise ValueError('chart must declare exactly one string FIRESTORE_READ_LEVERS literal')
    return matches[0]


def collect_sources(
    *,
    base_path: Path = composer.DEFAULT_BASE,
    runtime_env_dir: Path = composer.RUNTIME_ENV_DIR,
    runtime_path: Path = composer.DEFAULT_OUTPUT,
    charts_dir: Path = BACKEND / 'charts',
) -> tuple[dict, dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """Reuse compose's duplicate-key-safe loader and merge semantics for every source."""
    base = composer._load_yaml(base_path)
    composed = composer.compose_manifest(base_path=base_path, runtime_env_dir=runtime_env_dir)
    expected = {
        f'runtime/{path.removeprefix("environments/").removesuffix("/env")}': parse_levers(
            _literal_env_value(entry), path
        )
        for path, entry in literal_entries(composed)
    }
    sources: dict[str, dict[str, int]] = {'code/defaults': dict(DEFAULT_PERCENTAGES)}
    documents = {'base': base.get('environment_shared', {})}
    for env in composer.ENVIRONMENTS:
        documents[f'overlay/{env}'] = composer._load_yaml(runtime_env_dir / f'{env}.overlay.yaml').get('overlay', {})
    for prefix, doc in documents.items():
        for path, entry in literal_entries(doc):
            surface = f'{prefix}/{path.removesuffix("/env")}'
            sources[surface] = parse_levers(_literal_env_value(entry), surface)
    for path, entry in literal_entries(composer._load_yaml(runtime_path)):
        surface = f'runtime/{path.removeprefix("environments/").removesuffix("/env")}'
        sources[surface] = parse_levers(_literal_env_value(entry), surface)
    for chart in CHARTS:
        directory = charts_dir / chart
        defaults_path = directory / 'values.yaml'
        defaults = composer._load_yaml(defaults_path) if defaults_path.exists() else {}
        if chart == 'batch-pipeline-worker':
            sources[f'chart/default/{chart}'] = parse_levers(chart_literal(defaults), str(defaults_path))
        for env in composer.ENVIRONMENTS:
            stem = chart if chart == 'batch-pipeline-worker' else chart.replace('-', '_')
            path = directory / f'{env}_omi_{stem}_values.yaml'
            overlay = composer._load_yaml(path)
            # Serving chart env lists replace defaults, just as Helm does. Worker dev
            # omits the knob, so its effective value comes from values.yaml.
            merged = composer._deep_merge(defaults, overlay)
            surface = f'chart/{env}/{chart}'
            sources[surface] = parse_levers(chart_literal(merged), surface)
            # Validate overlay literals independently too (including any future knob).
            if chart != 'batch-pipeline-worker' or 'firestoreReadLevers' in overlay.get('worker', {}):
                parse_levers(chart_literal(overlay), f'{surface} overlay')
    return base[POLICY_KEY], sources, expected


def expiry_errors(sources: dict[str, dict[str, int]], expiry: dict, *, today: date) -> list[str]:
    errors = []
    if not isinstance(expiry, dict):
        return ['lever_expiry must be a surface -> lever -> {value, expires} map']
    for surface, entries in expiry.items():
        if not isinstance(entries, dict):
            errors.append(f'{surface}: lever_expiry must be a mapping')
            continue
        for lever in entries:
            if lever not in KNOWN_LEVERS:
                errors.append(f'{surface}: unknown expiry lever {lever}')
    if errors:
        return errors
    for surface, explicit in sources.items():
        # This also validates defaults separately, even when every surface overrides them.
        try:
            parse_levers(json.dumps(explicit), surface)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        values = (
            explicit
            if surface == 'code/defaults' or surface.startswith(('base/', 'overlay/'))
            else effective_levers(explicit)
        )
        for lever, value in values.items():
            if not 0 < value < 100:
                continue
            entry = expiry.get(surface, {}).get(lever)
            scope = f'{surface}/{lever}={value}'
            if not isinstance(entry, dict) or type(entry.get('value')) is not int or entry['value'] != value:
                errors.append(f'{scope}: missing matching lever_expiry')
                continue
            try:
                raw = entry['expires']
                expires = date.fromisoformat(raw) if isinstance(raw, str) else None
                if expires is None or expires.isoformat() != raw:
                    raise ValueError('expected YYYY-MM-DD string')
            except (KeyError, ValueError, TypeError):
                errors.append(f'{scope}: malformed expiry (expected YYYY-MM-DD)')
                continue
            if not today <= expires <= today + timedelta(days=7):
                errors.append(f'{scope}: expiry must be today through 7 days out (UTC)')
    return errors


def parity_errors(sources: dict[str, dict[str, int]], expected: dict[str, dict[str, int]], policy: dict) -> list[str]:
    errors = []
    actual_runtime = {key: value for key, value in sources.items() if key.startswith('runtime/')}
    if actual_runtime.keys() != expected.keys():
        errors.append('runtime surfaces differ from composed surfaces')
    for surface, explicit in actual_runtime.items():
        if surface in expected and effective_levers(explicit) != effective_levers(expected[surface]):
            errors.append(f'{surface}: effective levers differ from compose_manifest')
    allowlist = policy.get('reviewed_inheritance', {})
    empty_charts = {surface for surface, values in sources.items() if surface.startswith('chart/') and not values}
    if set(allowlist) != empty_charts:
        errors.append('reviewed inheritance allowlist must match empty chart surfaces exactly')
    for surface, explicit in sources.items():
        if not surface.startswith('chart/'):
            continue
        _, env, chart = surface.split('/')
        if not explicit:
            annotation = allowlist.get(surface, {})
            if (
                annotation.get('reason') != 'intentionally inherits code defaults'
                or annotation.get('status') != 'UNRESOLVED'
                or not annotation.get('reviewed_by')
                or 'batch_timeliness_leader' not in annotation.get('notes', '')
                or annotation.get('comparison_surface') not in expected
            ):
                errors.append(f'{surface}: missing reviewed UNRESOLVED inheritance annotation')
        else:
            target = f'runtime/{env}/gke/{chart}'
            if target not in expected or effective_levers(explicit) != effective_levers(expected[target]):
                errors.append(f'{surface}: effective levers differ from {target}')
    return errors


def build_manifest(*, today: date | None = None, **paths: Any) -> dict:
    policy, sources, expected = collect_sources(**paths)
    errors = expiry_errors(sources, policy.get('lever_expiry'), today=today or datetime.now(timezone.utc).date())
    errors += parity_errors(sources, expected, policy)
    if errors:
        raise ValueError('\n'.join(errors))
    surfaces = {}
    for surface, explicit in sources.items():
        if not surface.startswith(('runtime/', 'chart/')) and surface != 'code/defaults':
            continue
        surfaces[surface] = {
            'explicit': dict(sorted(explicit.items())),
            'inherited': sorted(KNOWN_LEVERS - explicit.keys()),
            'effective': effective_levers(explicit),
            'lever_expiry': policy['lever_expiry'].get(surface, {}),
        }
        if surface in policy.get('reviewed_inheritance', {}):
            annotation = policy['reviewed_inheritance'][surface]
            comparison = annotation['comparison_surface']
            surfaces[surface]['inheritance'] = annotation
            surfaces[surface]['unresolved_differences'] = {
                lever: {'surface': value, 'comparison_surface': effective_levers(expected[comparison])[lever]}
                for lever, value in effective_levers(explicit).items()
                if value != effective_levers(expected[comparison])[lever]
            }
    return {
        'schema_version': 1,
        'generated_by': 'python3 backend/deploy/generate_read_lever_manifest.py',
        'scope': 'Source-effective declarations only; not live state or rollout authority.',
        'notes': policy['unresolved_notes'],
        'surfaces': dict(sorted(surfaces.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        rendered = json.dumps(build_manifest(), indent=2, sort_keys=True) + '\n'
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.check:
        if not args.output.exists() or args.output.read_text() != rendered:
            print(f'{args.output} is out of date; run generate_read_lever_manifest.py', file=sys.stderr)
            return 1
        print(f'{args.output} is up to date')
    else:
        args.output.write_text(rendered)
        print(f'Wrote {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
