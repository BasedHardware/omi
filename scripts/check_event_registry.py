#!/usr/bin/env python3
"""C7 source/generation/consumer check; stdlib only, no telemetry access."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'contracts/analytics/events.json'
DART = 'app/lib/utils/analytics/registry/events.g.dart'
PLAN = 'contracts/analytics/TRACKING_PLAN.md'
BRIDGE = 'app/lib/utils/analytics/registry/typed_events.dart'
RAW = re.compile(r'\b(?:AnalyticsManager\s*\(\s*\)|Posthog\s*\(\s*\)|analytics|posthog)\s*\.\s*(?:track|trackEvent|capture)\s*\(')
MANAGER_CALL = re.compile(r'\bAnalyticsManager\s*\(\s*\)\s*\.\s*track\s*\(')
IDENT = re.compile(r'^[a-z][A-Za-z0-9]*$')


def git(ref, path):
    result = subprocess.run(['git', 'show', f'{ref}:{path}'], cwd=ROOT, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def validate(doc, root=ROOT, prior=None):
    errors = []
    events = doc['events']
    ids = {e['id'] for e in events}
    if len(ids) != len(events) or len({e['wire_name'] for e in events}) != len(events):
        errors.append('event ids and wire names must be unique')
    if prior:
        old = {e['id']: e for e in prior['events']}
        now = {e['id']: e for e in events}
        for key, value in old.items():
            if key not in now or any(now[key][field] != value[field] for field in ('wire_name', 'properties', 'phase', 'intent', 'correlation')):
                errors.append(f'{key}: released wire identity is immutable; retain old event and add a new id')
        if not set(prior['adopted_files']) <= set(doc['adopted_files']):
            errors.append('adoption cannot be removed')
    for event in events:
        label = event['id']
        if not IDENT.fullmatch(label) or not event['wire_name'].strip():
            errors.append(f'{label}: invalid id/name')
        if event['status'] not in ('active', 'deprecated') or (event['replaced_by'] is not None and event['replaced_by'] not in ids):
            errors.append(f'{label}: invalid lifecycle/replacement')
        # F1 owns the intent vocabulary and correlated payload encoding; C7 reserves the fields.
        if event['phase'] != 'point' or event['intent'] is not None or event['correlation'] is not None:
            errors.append(f'{label}: attempt/outcome requires the F1 contract before emission')
        for key, spec in event['properties'].items():
            if (not IDENT.fullmatch(key) or set(spec) != {'type', 'wire_name'} or
                spec['type'] != 'bool' or not isinstance(spec['wire_name'], str) or not spec['wire_name'] or
                spec['wire_name'] in {'git_sha', 'build_number', 'app_platform', 'app_version', 'app_build'}):
                errors.append(f'{label}.{key}: only boolean examples admitted; extend closed enum/count types with privacy tests, never free String/Map')
        if len({p.get('wire_name') for p in event['properties'].values()}) != len(event['properties']):
            errors.append(f'{label}: property wire names must be unique')
        if not event['consumers']:
            errors.append(f'{label}: no consumer; add a checked-in question and executable query under contracts/analytics/consumers')
        for consumer in event['consumers']:
            if not re.fullmatch(r'[a-z0-9-]+', consumer):
                errors.append(f'{label}: invalid consumer id')
                continue
            path = root / 'contracts/analytics/consumers' / f'{consumer}.json'
            try:
                record = json.loads(path.read_text())
                query_path = record['query']
                if not query_path.startswith('contracts/analytics/consumers/') or '..' in Path(query_path).parts:
                    raise ValueError('query outside consumer directory')
                query = (root / query_path).read_text()
                if record['kind'] != 'question' and not re.fullmatch(r'https://[^ ]+', record.get('artifact_url', '')):
                    raise ValueError('deployed consumers need their real artifact_url')
                if (record['id'] != consumer or label not in record['events'] or
                    not all(record.get(k) for k in ('owner', 'question', 'zero_policy')) or
                    record['namespace_property'] != '$app_namespace' or record['kind'] not in ('question', 'dashboard', 'alert', 'experiment')):
                    raise ValueError('consumer metadata incomplete')
                # Execute, not substring-match: positive signal and wrong cohort/build negatives.
                with sqlite3.connect(':memory:') as db:
                    db.execute('CREATE TABLE events(event TEXT, app_namespace TEXT, build_number TEXT)')
                    db.executemany('INSERT INTO events VALUES (?, ?, ?)', [(event['wire_name'], 'mobile-test', '1'), (event['wire_name'], 'desktop-test', '1'), (event['wire_name'], 'mobile-test', '2'), ('unrelated', 'mobile-test', '1')])
                    rows = db.execute(query, {'app_namespace': 'mobile-test', 'build_number': '1'}).fetchall()
                    if rows != [(event['wire_name'], 1)]:
                        raise ValueError('query must select the event only in the specified namespace/build')
                    db.execute('DELETE FROM events')
                    if db.execute(query, {'app_namespace': 'mobile-test', 'build_number': '1'}).fetchall():
                        raise ValueError('query manufactures presence on empty input')
            except (OSError, KeyError, ValueError, sqlite3.Error) as exc:
                errors.append(f'{label}: unusable consumer {consumer}: {exc}')
    return errors


def dart_string(value):
    return json.dumps(value).replace("$", "\\$")


def render(doc):
    dart = ["// GENERATED by scripts/check_event_registry.py --write; do not edit.", "sealed class RegisteredEvent {", "  const RegisteredEvent();", "  String get wireName;", "  Map<String, Object> get properties;", "}"]
    plan = ['# Mobile tracking plan (generated)', '', 'Source: events.json. Presence is not task success. Existing SDK provenance/identity is unchanged.', '', '| API | Wire name | Properties | Status | Consumers |', '| --- | --- | --- | --- | --- |']
    for e in doc['events']:
        cls = e['id'][0].upper() + e['id'][1:]
        fields = e['properties']
        args = ', '.join('required this.'+key for key in fields)
        dart += ['', f'final class {cls} extends RegisteredEvent {{', f"  const {cls}({('{' + args + '}') if args else ''});"]
        dart += [f'  final bool {key};' for key in fields]
        dart += ['  @override', f'  String get wireName => {dart_string(e["wire_name"])};', '  @override', '  Map<String, Object> get properties => {' + ', '.join(dart_string(fields[k]['wire_name'])+': '+k for k in fields) + '};', '}']
        plan.append(f"| {e['id']} | {e['wire_name']} | {', '.join(p['wire_name'] for p in fields.values()) or 'none'} | {e['status']} | {', '.join(e['consumers'])} |")
    return '\n'.join(dart)+'\n', '\n'.join(plan)+'\n'


def raw_violations(path, source, _prior, adopted):
    if not path.startswith('app/lib/') or not path.endswith('.dart') or (path not in adopted and path != BRIDGE):
        return []
    # Constrained lexical tripwire: known analytics receivers only, not camera.capture
    # or unrelated counters. Aliased/dynamic dispatch needs the behavioral batch test.
    trivia = r"//[^\n]*|/\*.*?\*/|r?'(?:\\.|[^'\\])*'|r?\"(?:\\.|[^\"\\])*\""
    source = re.sub(trivia, '', source, flags=re.S)
    calls = list(RAW.finditer(source))
    if path == BRIDGE and len(calls) <= 1 and all(MANAGER_CALL.fullmatch(c.group()) for c in calls):
        return []
    return [f'{path}: raw analytics call; use registry/typed_events.dart and events.json. Only TypedEvents.emit may bridge once to AnalyticsManager.track.'] if calls else []



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--base', default='origin/main')
    args = parser.parse_args()
    doc = json.loads((ROOT / SOURCE).read_text())
    old = git(args.base, SOURCE)
    errors = validate(doc, prior=json.loads(old) if old else None)
    generated = render(doc)
    for path, content in zip((DART, PLAN), generated):
        if args.write and not errors:
            (ROOT / path).write_text(content)
        elif not (ROOT / path).exists() or (ROOT / path).read_text() != content:
            errors.append(f'{path}: stale generated output; run python3 scripts/check_event_registry.py --write')
    changed = subprocess.check_output(['git', 'diff', '--name-only', args.base, '--', 'app/lib'], cwd=ROOT, text=True).splitlines()
    changed += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', 'app/lib'], cwd=ROOT, text=True).splitlines()
    for path in set(changed) | set(doc['adopted_files']):
        if (ROOT / path).is_file():
            errors += raw_violations(path, (ROOT / path).read_text(), git(args.base, path), doc['adopted_files'])
    for error in errors:
        print(error)
    if not errors:
        print(f"C7: {len(doc['events'])} registered events, executable consumers, generated output current")
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
