#!/usr/bin/env python3
"""Plan, apply or detect drift between contracts/analytics/posthog.json and PostHog.

  plan   print the differences; exit 0
  drift  print the differences; exit 1 when there are any (run daily)
  apply  write the live before-state to --snapshot-dir, then PATCH only the
         differing hog function inputs and names and warehouse should_sync;
         enabled, execution_order and untracked functions are reported and
         leave apply exiting 1

Stdlib only. The key comes from POSTHOG_PERSONAL_API_KEY and is never printed.
Hog function inputs are read from the detail endpoint; the list endpoint omits them.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'contracts/analytics/posthog.json'
DEFAULT_HOST = 'https://us.posthog.com'


class Client:
    def __init__(self, host, key, project):
        self.host, self.key, self.project = host.rstrip('/'), key, project

    def request(self, method, path, body=None):
        url = path if path.startswith('http') else f'{self.host}{path}'
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read() or b'null')
        except urllib.error.HTTPError as error:
            # The body names the failing field; it never echoes the bearer key.
            raise SystemExit(f'PostHog {method} {path}: HTTP {error.code} {error.read()[:300]!r}') from None

    def get(self, path):
        return self.request('GET', path)

    def patch(self, path, body):
        return self.request('PATCH', path, body)

    def paged(self, path):
        out, page = [], self.get(path)
        while True:
            out += page.get('results', [])
            if not page.get('next'):
                return out
            page = self.get(page['next'])


def names(value):
    if isinstance(value, list):
        return sorted(str(v).strip() for v in value if str(v).strip())
    return sorted(n.strip() for n in str(value or '').split(',') if n.strip())


def desired_inputs(fn):
    if fn['kind'] == 'keep_list':
        return {'keep': names(fn['events']), 'percentage': fn['pct']}
    return {'percentage': fn['pct'], 'triggeringEvents': names(fn['events'])}


def live_value(live, key):
    value = ((live.get('inputs') or {}).get(key) or {}).get('value')
    return names(value) if key in ('keep', 'triggeringEvents') else value


def same_number(a, b):
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a == b


def diff(config, live_functions, live_list, live_schemas):
    """Return [{target, field, live, desired}] between config and fetched live state."""
    changes = []
    managed = {f['id'] for f in config['functions']}
    for fn in config['functions']:
        if fn['kind'] == 'unmanaged':
            continue
        live = live_functions.get(fn['id'])
        if live is None:
            changes.append({'target': fn['id'], 'field': 'exists', 'live': None, 'desired': fn['name']})
            continue
        if live.get('name') != fn['name']:
            changes.append({'target': fn['id'], 'field': 'name', 'live': live.get('name'), 'desired': fn['name']})
        # Reported, never PATCHed: apply changes only inputs, names and should_sync.
        for field in ('enabled', 'execution_order'):
            if field in fn and field in live and live[field] != fn[field]:
                changes.append({'target': fn['id'], 'field': field, 'live': live[field], 'desired': fn[field]})
        for key, want in desired_inputs(fn).items():
            have = live_value(live, key)
            equal = same_number(have, want) if key == 'percentage' else have == want
            if not equal:
                changes.append({'target': fn['id'], 'field': f'inputs.{key}', 'live': have, 'desired': want})
    for live in live_list:
        if live.get('type', 'transformation') == 'transformation' and live['id'] not in managed and not live.get('deleted'):
            changes.append({'target': live['id'], 'field': 'untracked', 'live': live.get('name'), 'desired': None})
    for schema in config['warehouse']['schemas']:
        if not schema.get('schema_id'):
            continue
        live = live_schemas.get(schema['schema_id'])
        if live is None:
            changes.append({'target': schema['name'], 'field': 'exists', 'live': None, 'desired': schema['schema_id']})
        elif bool(live.get('should_sync')) != bool(schema['should_sync']):
            changes.append({'target': schema['schema_id'], 'field': 'should_sync', 'live': live.get('should_sync'), 'desired': schema['should_sync']})
    return changes


def describe(change):
    live, want = change['live'], change['desired']
    if isinstance(live, list) and isinstance(want, list):
        removed = sorted(set(live) - set(want))
        added = sorted(set(want) - set(live))
        return f"{change['target']} {change['field']}: -{len(removed)} {removed} +{len(added)} {added}"
    if change['field'] == 'untracked':
        return f"{change['target']} untracked live transformation {live!r}: add it to posthog.json or delete it"
    return f"{change['target']} {change['field']}: {live!r} -> {want!r}"


def fetch(client, config):
    project = config['project_id']
    live_functions = {}
    for fn in config['functions']:
        if fn['kind'] != 'unmanaged':
            try:
                live_functions[fn['id']] = client.get(f"/api/projects/{project}/hog_functions/{fn['id']}/")
            except SystemExit as error:
                if 'HTTP 404' not in str(error):
                    raise
    live_list = client.paged(f'/api/projects/{project}/hog_functions/?type=transformation&limit=200')
    sources = client.paged(f'/api/projects/{project}/external_data_sources/?limit=200')
    live_schemas = {s['id']: dict(s, source_id=src['id']) for src in sources for s in src.get('schemas', [])}
    return live_functions, live_list, live_schemas


def patch_bodies(config, live_functions, changes):
    """Group changes into one PATCH per target, sending only names and changed inputs."""
    bodies = {}
    functions = {f['id']: f for f in config['functions']}
    for change in changes:
        target, field = change['target'], change['field']
        if target in functions and field == 'name':
            bodies.setdefault(('fn', target), {})['name'] = change['desired']
        elif target in functions and field.startswith('inputs.'):
            key = field.split('.', 1)[1]
            want = change['desired']
            if key == 'triggeringEvents':
                want = ','.join(want)
            # PostHog replaces the inputs object, so carry the unchanged inputs along whole.
            # A changed input keeps its order but drops compiled bytecode; the server recompiles it.
            body = bodies.setdefault(('fn', target), {})
            live_inputs = live_functions[target].get('inputs') or {}
            inputs = body.setdefault('inputs', {k: dict(v) for k, v in live_inputs.items()})
            kept = {k: v for k, v in (live_inputs.get(key) or {}).items() if k not in ('value', 'bytecode', 'bytecode_contract')}
            inputs[key] = dict(kept, value=want)
        elif field == 'should_sync':
            bodies.setdefault(('schema', target), {})['should_sync'] = change['desired']
    return bodies


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('plan', 'apply', 'drift'))
    parser.add_argument('--config', default=str(SOURCE))
    parser.add_argument('--snapshot-dir', help='required for apply: where the live before-state is written')
    args = parser.parse_args(argv)
    key = os.environ.get('POSTHOG_PERSONAL_API_KEY')
    if not key:
        print('POSTHOG_PERSONAL_API_KEY is not set', file=sys.stderr)
        return 2
    if args.mode == 'apply' and not args.snapshot_dir:
        print('apply needs --snapshot-dir', file=sys.stderr)
        return 2
    config = json.loads(Path(args.config).read_text())
    client = Client(os.environ.get('POSTHOG_HOST', DEFAULT_HOST), key, config['project_id'])
    live_functions, live_list, live_schemas = fetch(client, config)
    changes = diff(config, live_functions, live_list, live_schemas)
    for change in changes:
        print(describe(change))
    print(f'{len(changes)} difference(s) between {Path(args.config).name} and PostHog project {config["project_id"]}')
    for schema in config['warehouse']['schemas']:
        if not schema.get('schema_id'):
            print(f"note: warehouse {schema['name']} is {schema.get('status', 'pending')}; not applied")
    if args.mode == 'drift':
        return 1 if changes else 0
    if args.mode == 'plan' or not changes:
        return 0
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    snap = Path(args.snapshot_dir) / f'posthog-before-{stamp}'
    snap.mkdir(parents=True, exist_ok=False)
    for fid, live in live_functions.items():
        (snap / f'hog_function-{fid}.json').write_text(json.dumps(live, indent=1) + '\n')
    (snap / 'warehouse-schemas.json').write_text(json.dumps(live_schemas, indent=1) + '\n')
    print(f'before-state written to {snap}')
    project = config['project_id']
    for (kind, target), body in patch_bodies(config, live_functions, changes).items():
        if kind == 'fn':
            path = f'/api/projects/{project}/hog_functions/{target}/'
        else:
            path = f'/api/projects/{project}/external_data_schemas/{target}/'
        client.patch(path, body)
        print(f'patched {kind} {target}: {sorted(body)}')
    after = diff(config, *fetch(client, config))
    print(f'{len(after)} difference(s) remain after apply')
    for change in after:
        if change['field'] in ('enabled', 'execution_order', 'untracked', 'exists'):
            print(f'not applied by this tool, fix in PostHog or in the file: {describe(change)}')
    return 1 if after else 0


if __name__ == '__main__':
    raise SystemExit(main())
