#!/usr/bin/env python3
"""Would activating a feature work against this serving state? Pure: manifest + state JSON in, verdict out.

A feature activation manifest (``backend/deploy/activation/<feature>.yaml``) declares what a lever move
needs from live serving state: which services must serve a source tree that contains given commits, env
keys that must be set (and equal across runtimes), llm-gateway lanes, Cloud Tasks queues and scheduler
jobs, and the order the services must move in. ``activation_collect.py`` reads that state from prod
read-only; this module never touches the network, git or the environment, so it is unit-tested offline.

Every requirement resolves to one of:

- ``satisfied``: the state proves it;
- ``missing``: the state proves it is not met;
- ``unknown``: the state could not be read (never treated as satisfied);
- ``deferred``: it belongs to the service being moved at this step or a later one, so it is not yet due.

A requirement with ``controlled: false`` names something the activation does not own (another
gate or writer owns it). It is always reported, but never changes the exit code.

Verdict and exit code: ``BLOCKED`` (1) when a controlled requirement is missing; else ``UNKNOWN`` (2)
when a controlled requirement is unknown; else ``READY`` (0). A malformed manifest or state exits 3.

  python3 backend/scripts/activation_check.py --manifest backend/deploy/activation/conversations-v3.yaml \\
      --state state.json [--before pusher] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

SATISFIED, MISSING, UNKNOWN, DEFERRED = 'satisfied', 'missing', 'unknown', 'deferred'
READY, BLOCKED, UNDETERMINED = 'READY', 'BLOCKED', 'UNKNOWN'
EXIT = {READY: 0, BLOCKED: 1, UNDETERMINED: 2}
EXIT_INVALID = 3
ACTIVATE = 'activate'
SCHEMA_VERSION = 1
IDENTITY_FIELDS = ('project', 'environment', 'feature', 'region')


class InvalidInput(ValueError):
    """The manifest or the state does not follow the schema; no verdict is possible."""


@dataclass(frozen=True)
class Result:
    id: str
    kind: str
    status: str
    controlled: bool
    detail: str = ''
    why: str = ''


@dataclass
class Verdict:
    feature: str
    step: str
    verdict: str
    results: list[Result] = field(default_factory=list)
    collected_at: str = ''

    @property
    def exit_code(self) -> int:
        return EXIT[self.verdict]

    def counts(self) -> dict[str, int]:
        out = {SATISFIED: 0, MISSING: 0, UNKNOWN: 0, DEFERRED: 0}
        for result in self.results:
            out[result.status] += 1
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            'feature': self.feature,
            'step': self.step,
            'collected_at': self.collected_at,
            'verdict': self.verdict,
            'exit_code': self.exit_code,
            'counts': self.counts(),
            'results': [asdict(r) for r in self.results],
        }


# ---------------------------------------------------------------------------------------------- manifest


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidInput(message)


def _names(value: Any, what: str) -> list[str]:
    _require(
        isinstance(value, list) and value and all(isinstance(v, str) and v for v in value), f'{what}: non-empty list'
    )
    return list(value)


def _require_target_fields(data: dict[str, Any], label: str, fields: Iterable[str]) -> None:
    for field in fields:
        value = data.get(field)
        _require(
            isinstance(value, str) and bool(value) and value == value.strip(),
            f'{label}.{field}: non-empty string without surrounding whitespace',
        )


def validate_manifest(manifest: Any) -> dict[str, Any]:
    _require(isinstance(manifest, dict), 'manifest: mapping')
    _require(manifest.get('schema_version') == SCHEMA_VERSION, 'manifest.schema_version: 1')
    _require_target_fields(manifest, 'manifest', IDENTITY_FIELDS)
    services = manifest.get('services')
    _require(isinstance(services, dict) and services, 'manifest.services: mapping')
    for name, svc in services.items():
        _require(isinstance(svc, dict) and svc.get('kind') in ('cloud_run', 'gke'), f'services.{name}.kind')
        for commit in svc.get('contains', []):
            _require(
                isinstance(commit, dict) and re.fullmatch(r'[0-9a-f]{40}', str(commit.get('commit', ''))) is not None,
                f'services.{name}.contains: full 40-hex commit',
            )
    if any(svc['kind'] == 'gke' for svc in services.values()) or 'cluster' in manifest:
        _require_target_fields(manifest, 'manifest', ('cluster',))
    order = manifest.get('order')
    _require(isinstance(order, list) and order, 'manifest.order: list of steps')
    ordered: list[str] = []
    for step in order:
        ordered += _names(step, 'order step')
    _require(len(ordered) == len(set(ordered)), 'manifest.order: a service appears once')
    _require(all(s in services for s in ordered), 'manifest.order: unknown service')
    for req in manifest.get('env', []):
        _require(isinstance(req, dict) and isinstance(req.get('id'), str), 'env[].id')
        _require(bool(req.get('keys')) != bool(req.get('any_of')), f'env.{req["id"]}: exactly one of keys/any_of')
        _names(req.get('keys') or req.get('any_of'), f'env.{req["id"]} keys')
        _require(all(r in services for r in _names(req.get('runtimes'), f'env.{req["id"]}.runtimes')), 'env runtime')
        _require(not (req.get('any_of') and req.get('equal')), f'env.{req["id"]}: equal needs keys')
    lanes = manifest.get('gateway_lanes')
    if lanes is not None:
        _require(lanes.get('service') in services, 'gateway_lanes.service')
        _names(lanes.get('lanes'), 'gateway_lanes.lanes')
    for kind in ('queues', 'scheduler_jobs'):
        for item in manifest.get(kind, []):
            _require(isinstance(item, dict) and isinstance(item.get('name'), str), f'{kind}[].name')
            before = item.get('before')
            _require(before is None or before == ACTIVATE or before in ordered, f'{kind}.{item["name"]}.before')
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    import yaml  # PyYAML is in every backend environment; imported here so the pure checker loads without it

    with open(path, encoding='utf-8') as handle:
        try:
            data = yaml.safe_load(handle)
        except yaml.YAMLError as error:
            raise InvalidInput(f'manifest is not valid YAML: {type(error).__name__}') from error
    return validate_manifest(data)


# ---------------------------------------------------------------------------------------------- state


def validate_state(state: Any) -> dict[str, Any]:
    _require(isinstance(state, dict), 'state: mapping')
    _require(state.get('schema_version') == SCHEMA_VERSION, 'state.schema_version: 1')
    _require_target_fields(state, 'state', IDENTITY_FIELDS)
    _require('cluster' in state, 'state.cluster: required (null for a manifest without a cluster)')
    if state['cluster'] is not None:
        _require_target_fields(state, 'state', ('cluster',))
    for key in ('services', 'queues', 'scheduler_jobs', 'ancestry'):
        table = state.get(key, {})
        _require(isinstance(table, dict), f'state.{key}: mapping')
        for name, value in table.items():
            if key in ('queues', 'scheduler_jobs') and name == '_error':
                _require(isinstance(value, str), f'state.{key}._error: string')
                continue
            _require(isinstance(value, dict), f'state.{key}.{name}: mapping')
        if key == 'services':
            for name, value in table.items():
                serving = value.get('serving', [])
                _require(
                    isinstance(serving, list) and all(isinstance(u, dict) for u in serving),
                    f'state.services.{name}.serving: list of mappings',
                )
    return state


def _service(state: dict[str, Any], name: str) -> tuple[list[dict[str, Any]] | None, str]:
    """(serving units, reason). None when the service could not be read."""
    svc = state.get('services', {}).get(name)
    if svc is None:
        return None, 'not collected'
    if svc.get('error'):
        return None, str(svc['error'])
    units = svc.get('serving')
    if not isinstance(units, list) or not units:
        return None, 'no serving revisions in state'
    return units, ''


def _unit_label(unit: dict[str, Any]) -> str:
    percent = unit.get('percent')
    return f"{unit.get('name', '?')}" + (f'@{percent:g}%' if isinstance(percent, (int, float)) else '')


# ---------------------------------------------------------------------------------------------- evaluation


def _due_services(manifest: dict[str, Any], step: str) -> set[str]:
    """Services whose requirements are due before moving ``step`` (a service name, or ``activate``)."""
    order = manifest['order']
    if step == ACTIVATE:
        return {s for group in order for s in group}
    for index, group in enumerate(order):
        if step in group:
            return {s for earlier in order[:index] for s in earlier}
    raise InvalidInput(f'--before {step}: not a service in manifest.order (or "activate")')


def _infra_due(manifest: dict[str, Any], before: str | None, step: str) -> bool:
    """Queues and jobs depend on no service, so they are due at every step unless ``before`` names a later one:
    ``before: X`` makes the object due when X moves, at every later step, and at the lever move."""
    if before is None or step == ACTIVATE:
        return True
    if before == ACTIVATE:
        return False
    group_of = {s: i for i, g in enumerate(manifest['order']) for s in g}
    return group_of[before] <= group_of[step]


def _contains(manifest, state, name, due, out: list[Result]) -> None:
    svc = manifest['services'][name]
    for item in svc.get('contains', []):
        rid = f"service:{name}:contains:{item['commit'][:12]}"
        why = item.get('why', '')
        if name not in due:
            out.append(Result(rid, 'contains', DEFERRED, True, 'moves at or after this step', why))
            continue
        units, reason = _service(state, name)
        if units is None:
            out.append(Result(rid, 'contains', UNKNOWN, True, reason, why))
            continue
        lacking, unknown = [], []
        for unit in units:
            source = unit.get('source_sha')
            answer = state.get('ancestry', {}).get(source or '', {}).get(item['commit']) if source else None
            if answer is True:
                continue
            if answer is False:
                lacking.append(f'{_unit_label(unit)} source={str(source)[:12]}')
            else:
                unknown.append(
                    f"{_unit_label(unit)} source={str(source)[:12] if source else unit.get('source_error', 'unread')}"
                )
        if lacking:
            out.append(Result(rid, 'contains', MISSING, True, 'serving without it: ' + ', '.join(lacking), why))
        elif unknown:
            out.append(Result(rid, 'contains', UNKNOWN, True, 'ancestry unknown: ' + ', '.join(unknown), why))
        else:
            out.append(Result(rid, 'contains', SATISFIED, True, f'{len(units)} serving unit(s) contain it', why))


def _env_value(unit: dict[str, Any], key: str, default: str | None, unset: Iterable[str] = ()) -> tuple[str, Any]:
    """('set', comparable) | ('absent', None) | ('unknown', reason) for one serving unit.

    ``unset`` lists placeholder values that mean "not configured" (a deploy default such as
    ``http://127.0.0.1:9``); they count as absent. Only an absent key takes the code ``default``: an
    explicit empty value is compared as itself, because code may read '' differently from the default
    (``CONVERSATIONS_V3_STAGE=''`` falls through to the named cohort, not ``beta``)."""
    env = unit.get('env')
    if not isinstance(env, dict):
        return 'unknown', 'env not collected'
    entry = env.get(key)
    if entry is None:
        return ('set', default) if default is not None else ('absent', None)
    if not isinstance(entry, dict):
        return 'unknown', 'malformed env entry'
    if 'unknown' in entry:
        return 'unknown', str(entry['unknown'])
    if 'secret_ref' in entry:
        return 'set', 'secret:' + str(entry['secret_ref'])
    value = entry.get('value')
    if value is None or str(value) in set(unset) or (value == '' and default is None):
        return 'absent', None
    return 'set', str(value)


def _env(manifest, state, due, out: list[Result]) -> None:
    for req in manifest.get('env', []):
        controlled = req.get('controlled', True)
        why = req.get('why', '')
        default = req.get('default')
        keys = req.get('keys') or []
        any_of = req.get('any_of') or []
        observed: dict[str, dict[str, Any]] = {k: {} for k in keys}
        absent_on: dict[str, set[str]] = {k: set() for k in keys}
        unknown_on: dict[str, set[str]] = {k: set() for k in keys}
        for runtime in req['runtimes']:
            units, reason = _service(state, runtime) if runtime in due else (None, '')
            for key in keys or ['|'.join(any_of)]:
                rid = f"env:{req['id']}:{runtime}:{key}"
                if runtime not in due:
                    out.append(Result(rid, 'env', DEFERRED, controlled, 'moves at or after this step', why))
                    continue
                if units is None:
                    out.append(Result(rid, 'env', UNKNOWN, controlled, reason, why))
                    if keys:
                        unknown_on[key].add(runtime)
                    continue
                absent, unknown = [], []
                for unit in units:
                    candidates = [key] if keys else any_of
                    states = [_env_value(unit, k, default, req.get('unset_values', ())) for k in candidates]
                    hit = next((s for s in states if s[0] == 'set'), None)
                    if hit is not None:
                        expected = req.get('value')
                        if keys:
                            observed[key][f'{runtime}/{unit.get("name", "?")}'] = hit[1]
                        if expected is not None and hit[1] != str(expected):
                            absent.append(f'{_unit_label(unit)} (value differs from required)')
                        continue
                    if any(s[0] == 'unknown' for s in states):
                        unknown.append(_unit_label(unit))
                        if keys:
                            unknown_on[key].add(runtime)
                    else:
                        absent.append(_unit_label(unit))
                        if keys:
                            absent_on[key].add(runtime)
                if absent:
                    out.append(Result(rid, 'env', MISSING, controlled, 'not set on ' + ', '.join(absent), why))
                elif unknown:
                    out.append(Result(rid, 'env', UNKNOWN, controlled, 'unreadable on ' + ', '.join(unknown), why))
                else:
                    out.append(Result(rid, 'env', SATISFIED, controlled, f'set on {len(units)} unit(s)', why))
        if not req.get('equal'):
            continue
        for key in keys:
            rid = f"env-equal:{req['id']}:{key}"
            due_runtimes = [r for r in req['runtimes'] if r in due]
            if len(due_runtimes) < 2 and len(observed[key]) < 2:
                out.append(Result(rid, 'env_equal', DEFERRED, controlled, 'fewer than two due runtimes', why))
                continue
            # A runtime is unread when any of its serving units could not be read, even if another unit was.
            unread = [
                r
                for r in due_runtimes
                if r in unknown_on[key]
                or (r not in absent_on[key] and not any(k.startswith(r + '/') for k in observed[key]))
            ]
            groups: dict[str, set[str]] = {}
            for where, value in observed[key].items():
                groups.setdefault(json.dumps(value), set()).add(where.split('/')[0])
            if absent_on[key]:
                groups['absent'] = set(absent_on[key])
            if len(groups) > 1:
                # Names runtimes only; values never reach the report.
                detail = ' vs '.join('[' + ','.join(sorted(v)) + ']' for v in groups.values())
                out.append(Result(rid, 'env_equal', MISSING, controlled, 'values differ: ' + detail, why))
            elif unread:
                out.append(Result(rid, 'env_equal', UNKNOWN, controlled, 'no value from ' + ', '.join(unread), why))
            else:
                out.append(
                    Result(rid, 'env_equal', SATISFIED, controlled, f'equal on {len(due_runtimes)} runtimes', why)
                )


def _lanes(manifest, state, due, out: list[Result]) -> None:
    spec = manifest.get('gateway_lanes')
    if not spec:
        return
    name = spec['service']
    why = spec.get('why', '')
    units, reason = _service(state, name)
    for lane in spec['lanes']:
        rid = f'lane:{lane}'
        if name not in due:
            out.append(Result(rid, 'gateway_lane', DEFERRED, True, f'{name} moves at or after this step', why))
            continue
        if units is None:
            out.append(Result(rid, 'gateway_lane', UNKNOWN, True, reason, why))
            continue
        lacking, unknown = [], []
        for unit in units:
            served = unit.get('lanes')
            if not isinstance(served, list):
                unknown.append(f"{_unit_label(unit)} ({unit.get('lanes_error', 'lanes not collected')})")
            elif lane not in served:
                lacking.append(_unit_label(unit))
        if lacking:
            out.append(Result(rid, 'gateway_lane', MISSING, True, 'not served by ' + ', '.join(lacking), why))
        elif unknown:
            out.append(Result(rid, 'gateway_lane', UNKNOWN, True, 'unreadable: ' + ', '.join(unknown), why))
        else:
            out.append(Result(rid, 'gateway_lane', SATISFIED, True, f'served by {len(units)} unit(s)', why))


def _objects(manifest, state, step, kind: str, state_key: str, ready_states: Iterable[str], out: list[Result]):
    table = state.get(state_key, {})
    for item in manifest.get(kind, []):
        rid = f"{kind.rstrip('s').replace('_job', '-job')}:{item['name']}"
        controlled = item.get('controlled', True)
        why = item.get('why', '')
        if not _infra_due(manifest, item.get('before'), step):
            out.append(Result(rid, kind, DEFERRED, controlled, f"due before {item['before']}", why))
            continue
        if isinstance(table.get('_error'), str):
            out.append(Result(rid, kind, UNKNOWN, controlled, table['_error'], why))
            continue
        got = table.get(item['name'])
        if got is None:
            out.append(Result(rid, kind, UNKNOWN, controlled, 'not collected', why))
        elif got.get('error'):
            out.append(Result(rid, kind, UNKNOWN, controlled, str(got['error']), why))
        elif not got.get('exists'):
            out.append(Result(rid, kind, MISSING, controlled, 'does not exist', why))
        else:
            wanted = item.get('state') or None
            allowed = {wanted} if wanted else set(ready_states)
            if got.get('state') not in allowed:
                out.append(Result(rid, kind, MISSING, controlled, f"state {got.get('state')}", why))
            else:
                out.append(Result(rid, kind, SATISFIED, controlled, f"exists, {got.get('state')}", why))


def evaluate(manifest: dict[str, Any], state: dict[str, Any], step: str = ACTIVATE) -> Verdict:
    validate_manifest(manifest)
    validate_state(state)
    for field in (*IDENTITY_FIELDS, 'cluster'):
        _require(state[field] == manifest.get(field), f'state.{field}: does not match manifest.{field}')
    due = _due_services(manifest, step)
    results: list[Result] = []
    for group in manifest['order']:
        for name in group:
            _contains(manifest, state, name, due, results)
    _lanes(manifest, state, due, results)
    _env(manifest, state, due, results)
    _objects(manifest, state, step, 'queues', 'queues', ('RUNNING',), results)
    _objects(manifest, state, step, 'scheduler_jobs', 'scheduler_jobs', ('ENABLED',), results)
    for item in manifest.get('not_checked', []):
        results.append(
            Result(f"external:{item['id']}", 'external', UNKNOWN, False, item.get('owner', ''), item.get('why', ''))
        )
    controlled = [r for r in results if r.controlled]
    if any(r.status == MISSING for r in controlled):
        verdict = BLOCKED
    elif any(r.status == UNKNOWN for r in controlled):
        verdict = UNDETERMINED
    else:
        verdict = READY
    return Verdict(manifest['feature'], step, verdict, results, str(state.get('collected_at', '')))


# ---------------------------------------------------------------------------------------------- output


def render_text(verdict: Verdict) -> str:
    # The state is a snapshot; the caller judges whether collected_at is fresh enough for the move.
    lines = [
        f'ACTIVATION {verdict.feature} before={verdict.step} verdict={verdict.verdict} '
        f"state_collected_at={verdict.collected_at or 'unknown'}"
    ]
    order = {MISSING: 0, UNKNOWN: 1, SATISFIED: 2, DEFERRED: 3}
    for r in sorted(verdict.results, key=lambda r: (not r.controlled, order[r.status])):
        scope = '' if r.controlled else ' (not controlled by this activation; advisory)'
        lines.append(f'  {r.status.upper():9} {r.id}{scope}' + (f' -- {r.detail}' if r.detail else ''))
    c = verdict.counts()
    lines.append(
        f"SUMMARY satisfied={c[SATISFIED]} missing={c[MISSING]} unknown={c[UNKNOWN]} deferred={c[DEFERRED]} "
        f'exit={verdict.exit_code}'
    )
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--state', required=True, type=Path, help='state JSON from activation_collect.py')
    parser.add_argument('--before', default=ACTIVATE, help='service about to move, or "activate" (the lever move)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        state = json.loads(args.state.read_text(encoding='utf-8'))
        verdict = evaluate(manifest, state, args.before)
    except (InvalidInput, OSError, ValueError) as error:
        print(f'ACTIVATION invalid input: {error}', file=sys.stderr)
        return EXIT_INVALID
    print(json.dumps(verdict.to_json(), indent=2) if args.json else render_text(verdict))
    return verdict.exit_code


if __name__ == '__main__':
    sys.exit(main())
