#!/usr/bin/env python3
"""omi-flags: the only writer of the Omi feature-flag store.

    python scripts/omi_flags.py list
    python scripts/omi_flags.py show KEY
    python scripts/omi_flags.py set KEY --rollout 25 --reason "ramp to 25%"
    python scripts/omi_flags.py set KEY --inactive --reason "kill"
    python scripts/omi_flags.py delete KEY --reason "hand back to PostHog"
    python scripts/omi_flags.py history KEY
    python scripts/omi_flags.py import-posthog [--keys a,b] [--apply]

Target: ``--project``/``--database`` or ``OMI_FLAGS_FIRESTORE_PROJECT``/``OMI_FLAGS_FIRESTORE_DATABASE``.
Writes need the flag project's writer identity (``prod-operator`` tier for prod).
Only ``kind: posthog`` registry keys can be written; registry ``surfaces`` are
copied onto the rule. ``experiment`` rows stay on PostHog. ``--mirror-posthog``
also patches the matching PostHog row (single unconditioned group only) so
released clients that still read PostHog agree. Runbook:
``backend/docs/runbooks/omi-flags.md``.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from database import omi_flags as store  # noqa: E402
from posthog_flag_sync import list_feature_flags  # noqa: E402

REGISTRY_PATH = ROOT / 'config' / 'feature-flags.yaml'
POSTHOG_HOST = 'https://us.posthog.com'
POSTHOG_PROJECT = '302298'
RULE_FIELDS = ('active', 'rollout_percentage', 'variant', 'payload', 'allow_uids', 'deny_uids', 'surfaces')


class FlagCliError(RuntimeError):
    pass


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    return {row['key']: row for row in data.get('flags', []) if row.get('kind') == 'posthog'}


def registry_entry(registry: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    entry = registry.get(key)
    if entry is None:
        raise FlagCliError(f'{key}: not a kind: posthog flag in config/feature-flags.yaml')
    if entry.get('lifecycle') == 'experiment':
        raise FlagCliError(f'{key}: experiments stay on PostHog until they conclude')
    return entry


def merge_rule(current: dict[str, Any] | None, entry: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    rule = {field: (current or {}).get(field) for field in RULE_FIELDS}
    rule.update({k: v for k, v in changes.items() if v is not None})
    rule['active'] = rule.get('active') is True
    pct = float(rule.get('rollout_percentage') or 0)
    if not 0 <= pct <= 100:
        raise FlagCliError('--rollout must be within 0..100')
    rule['rollout_percentage'] = pct
    payload = rule.get('payload')
    if payload is not None:
        json.loads(payload)  # must be valid JSON text
    rule['allow_uids'] = sorted(set(rule.get('allow_uids') or ()))
    rule['deny_uids'] = sorted(set(rule.get('deny_uids') or ()))
    rule['surfaces'] = list(entry['surfaces'])
    return rule


def rule_from_posthog_row(row: dict[str, Any], entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """A rule equivalent to a simple PostHog row, or (None, why it needs a human)."""
    if entry.get('lifecycle') == 'experiment':
        return None, 'experiment stays on PostHog'
    if row.get('active') is not True:
        return None, 'inactive row reads as unknown, not false; leave it on PostHog'
    filters = row.get('filters') or {}
    groups = filters.get('groups') or []
    if len(groups) != 1 or (groups[0] or {}).get('properties'):
        return None, 'targeting conditions need a manual rule'
    if (filters.get('multivariate') or {}).get('variants'):
        return None, 'multivariate row needs a manual rule'
    if groups[0].get('variant'):
        return None, 'group variant override needs a manual rule'
    pct = groups[0].get('rollout_percentage')
    payload = (filters.get('payloads') or {}).get('true')
    if payload is not None and not isinstance(payload, str):
        payload = json.dumps(payload)
    rule = {
        'active': True,
        'rollout_percentage': 100.0 if pct is None else float(pct),
        'variant': None,
        'payload': payload,
        'allow_uids': [],
        'deny_uids': [],
        'surfaces': list(entry['surfaces']),
    }
    return rule, 'ok'


def posthog_mirror_body(row: dict[str, Any], rule: dict[str, Any] | None) -> dict[str, Any]:
    """PATCH body that makes a simple PostHog row serve ``rule``; refuses anything it cannot express."""
    filters = dict(row.get('filters') or {})
    groups = filters.get('groups') or []
    if len(groups) != 1 or (groups[0] or {}).get('properties') or (filters.get('multivariate') or {}).get('variants'):
        raise FlagCliError(f"{row.get('key')}: PostHog row is not a single unconditioned group; mirror by hand")
    if rule is None:
        raise FlagCliError('delete hands the key back to PostHog; there is nothing to mirror')
    if rule['allow_uids'] or rule['deny_uids'] or rule['variant']:
        raise FlagCliError('allow/deny lists and variants cannot be mirrored to PostHog')
    filters['groups'] = [{**groups[0], 'properties': [], 'rollout_percentage': rule['rollout_percentage']}]
    payloads = {k: v for k, v in (filters.get('payloads') or {}).items() if k != 'true'}
    if rule.get('payload') is not None:
        payloads['true'] = rule['payload']
    filters['payloads'] = payloads
    # A kill row stays an active 0% group: an inactive PostHog row reads unknown on released clients.
    if not rule['active']:
        filters['groups'][0]['rollout_percentage'] = 0
    return {'active': True, 'filters': filters}


def _posthog_request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    token = os.getenv('POSTHOG_PERSONAL_API_KEY', '').strip()
    if not token:
        raise FlagCliError('POSTHOG_PERSONAL_API_KEY is required for PostHog reads/mirrors')
    request = urllib.request.Request(
        f'{POSTHOG_HOST}/api/projects/{POSTHOG_PROJECT}/{path}',
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def posthog_rows() -> dict[str, dict[str, Any]]:
    token = os.getenv('POSTHOG_PERSONAL_API_KEY', '').strip()
    if not token:
        raise FlagCliError('POSTHOG_PERSONAL_API_KEY is required for PostHog reads/mirrors')
    return {row['key']: row for row in list_feature_flags(POSTHOG_HOST, POSTHOG_PROJECT, token)}


def _client(args: argparse.Namespace) -> Any:
    if args.project:
        os.environ['OMI_FLAGS_FIRESTORE_PROJECT'] = args.project
    if args.database:
        os.environ['OMI_FLAGS_FIRESTORE_DATABASE'] = args.database
    client = store.flags_client()
    if client is None:
        raise FlagCliError('set --project or OMI_FLAGS_FIRESTORE_PROJECT')
    return client


def _actor() -> str:
    return os.getenv('OMI_FLAGS_ACTOR') or f'{getpass.getuser()}@{socket.gethostname()}'


def _write(client: Any, key: str, rule: dict[str, Any] | None, reason: str) -> None:
    version = store.write_rule(client, key, rule, actor=_actor(), reason=reason)
    published = store.publish_redis_version(version)
    print(f'{key}: version {version}' + ('' if published else ' (Redis not updated; pods pick it up within 60 s)'))


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def cmd_set(args: argparse.Namespace) -> None:
    entry = registry_entry(load_registry(), args.key)
    client = _client(args)
    _, docs = store.read_all(client)
    current = docs.get(args.key)
    changes: dict[str, Any] = {
        'active': True if args.active else (False if args.inactive else None),
        'rollout_percentage': args.rollout,
        'payload': args.payload,
    }
    if args.boolean:
        changes['variant'] = ''
    elif args.variant is not None:
        changes['variant'] = args.variant
    rule = merge_rule(current, entry, changes)
    rule['variant'] = rule.get('variant') or None
    if args.no_payload:
        rule['payload'] = None
    rule['allow_uids'] = sorted((set(rule['allow_uids']) | set(args.allow or ())) - set(args.unallow or ()))
    rule['deny_uids'] = sorted((set(rule['deny_uids']) | set(args.deny or ())) - set(args.undeny or ()))
    _print({'before': current, 'after': rule})
    mirror = None
    if args.mirror_posthog:
        row = posthog_rows().get(args.key)
        if row is None:
            raise FlagCliError(f'{args.key}: no PostHog row to mirror')
        mirror = (row['id'], posthog_mirror_body(row, rule))
        _print({'posthog_patch': mirror[1]})
    if not args.yes and input('write? [y/N] ').strip().lower() != 'y':
        print('aborted')
        return
    _write(client, args.key, rule, args.reason)
    if mirror is not None:
        _posthog_request('PATCH', f'feature_flags/{mirror[0]}/', mirror[1])
        print(f'{args.key}: PostHog row mirrored')


def cmd_delete(args: argparse.Namespace) -> None:
    client = _client(args)
    _, docs = store.read_all(client)
    if args.key not in docs:
        raise FlagCliError(f'{args.key}: no rule in the Omi store')
    _print({'before': docs[args.key], 'after': None})
    if not args.yes and input('delete (key returns to PostHog)? [y/N] ').strip().lower() != 'y':
        print('aborted')
        return
    _write(client, args.key, None, args.reason)


def cmd_import(args: argparse.Namespace) -> None:
    registry = load_registry()
    rows = posthog_rows()
    keys = args.keys.split(',') if args.keys else sorted(set(rows) & set(registry))
    client = _client(args)
    _, docs = store.read_all(client)
    planned = []
    for key in keys:
        if key not in registry or key not in rows:
            print(f'skip {key}: needs a registry kind: posthog row and a PostHog row')
            continue
        if key in docs:
            print(f'skip {key}: already in the Omi store')
            continue
        rule, why = rule_from_posthog_row(rows[key], registry[key])
        if rule is None:
            print(f'skip {key}: {why}')
            continue
        planned.append((key, rule))
        print(f"import {key}: active={rule['active']} rollout={rule['rollout_percentage']}")
    if not args.apply:
        print(f'dry run: {len(planned)} rule(s); pass --apply to write')
        return
    for key, rule in planned:
        _write(client, key, rule, args.reason or 'import from PostHog')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project')
    parser.add_argument('--database')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    for name in ('show', 'history'):
        sub.add_parser(name).add_argument('key')
    p_set = sub.add_parser('set')
    p_set.add_argument('key')
    state = p_set.add_mutually_exclusive_group()
    state.add_argument('--active', action='store_true')
    state.add_argument('--inactive', action='store_true')
    p_set.add_argument('--rollout', type=float)
    variant = p_set.add_mutually_exclusive_group()
    variant.add_argument('--variant')
    variant.add_argument('--boolean', action='store_true')
    payload = p_set.add_mutually_exclusive_group()
    payload.add_argument('--payload', help='JSON text served with the flag when it is on')
    payload.add_argument('--no-payload', action='store_true')
    for name in ('allow', 'unallow', 'deny', 'undeny'):
        p_set.add_argument(f'--{name}', nargs='+', metavar='UID')
    p_set.add_argument('--mirror-posthog', action='store_true')
    p_set.add_argument('--reason', required=True)
    p_set.add_argument('--yes', action='store_true')
    p_del = sub.add_parser('delete')
    p_del.add_argument('key')
    p_del.add_argument('--reason', required=True)
    p_del.add_argument('--yes', action='store_true')
    p_imp = sub.add_parser('import-posthog')
    p_imp.add_argument('--keys')
    p_imp.add_argument('--apply', action='store_true')
    p_imp.add_argument('--reason')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            _print(store.read_all(_client(args)))
        elif args.command == 'show':
            _print(store.read_all(_client(args))[1].get(args.key))
        elif args.command == 'history':
            _print(store.read_audit(_client(args), args.key))
        elif args.command == 'set':
            cmd_set(args)
        elif args.command == 'delete':
            cmd_delete(args)
        else:
            cmd_import(args)
    except FlagCliError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
