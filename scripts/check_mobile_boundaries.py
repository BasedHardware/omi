#!/usr/bin/env python3
"""Diff-scoped lexical no-growth ratchets for mobile ownership boundaries."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# Strings/comments are ignored. This is not Dart name or type resolution.
TRIVIA = re.compile(r'''//[^\n]*|/\*[\s\S]*?\*/|r?(?:"""[\s\S]*?"""|''' + "'''[\\s\\S]*?'''" + r'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')


def counts(source, rules, path):
    source = TRIVIA.sub(' ', source)
    return {r['id']: len(re.findall(r['pattern'], source)) for r in rules
            if any(path.startswith(p) for p in r['paths']) and path not in r.get('except', [])}


def violations(path, source, prior_source, rules, baseline, adopted=()):
    current = counts(source, rules, path)
    previous = counts(prior_source, rules, path) if prior_source is not None else {}
    return [f'{path}: {key} grew to {count} (limit {min(baseline.get(key, 0), previous.get(key, 0))}); '
            + next(r['remedy'] for r in rules if r['id'] == key)
            for key, count in current.items()
            if (prior_source is None or key in adopted)
            and count > min(baseline.get(key, 0), previous.get(key, 0))]


def base_source(base, path):
    result = subprocess.run(['git', 'show', f'{base}:{path}'], cwd=ROOT, text=True, capture_output=True)
    return result.stdout if result.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--base', default='origin/main')
    parser.add_argument('--changed-files')
    args = parser.parse_args()
    config = json.loads((ROOT / args.config).read_text())
    baseline = config['baseline']
    base = subprocess.check_output(['git', 'merge-base', args.base, 'HEAD'], cwd=ROOT, text=True).strip()
    previous = base_source(base, args.config)
    errors = []
    if previous:
        previous = json.loads(previous)
        if config['rules'] != previous['rules']:
            errors.append(f'{args.config}: boundary rules are frozen; revise the spine contract, not the gate')
        for path, adopted in previous.get('adopted', {}).items():
            if not set(adopted) <= set(config.get('adopted', {}).get(path, [])):
                errors.append(f'{path}: adopted boundary rules cannot be removed')
        for path, values in baseline.items():
            for key, count in values.items():
                if key in config.get('adopted', {}).get(path, []) and count > previous['baseline'].get(path, {}).get(key, 0):
                    errors.append(f'{path}: {key} baseline cannot grow')
    if args.changed_files:
        changed = Path(args.changed_files).read_text().splitlines()
    else:
        changed = subprocess.check_output(['git', 'diff', '--name-only', base], cwd=ROOT, text=True).splitlines()
        changed += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    for path, adopted in config.get('adopted', {}).items():
        if any(baseline.get(path, {}).get(key, 0) != 0 for key in adopted):
            errors.append(f'{path}: adopted rules require a zero-debt baseline')
        available = set(counts('', config['rules'], path))
        if not set(adopted) <= available:
            errors.append(f'{path}: adopted contains an unknown or inapplicable rule')
    for path in set(changed):
        if path.endswith('.dart') and (ROOT / path).is_file():
            errors.extend(violations(path, (ROOT / path).read_text(), base_source(base, path),
                                     config['rules'], baseline.get(path, {}), config.get('adopted', {}).get(path, [])))
    for error in errors:
        print(error, file=sys.stderr)
    print(f'Mobile boundaries: {len(set(changed))} changed paths; {len(errors)} errors')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
