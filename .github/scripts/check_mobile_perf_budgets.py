#!/usr/bin/env python3
"""INV-PERF-1/#23400: count/share admission caps can only ratchet downward."""
import argparse
import json
import math
from pathlib import Path
import subprocess

BUDGETS = 'app/integration_test/perf/budgets.json'


def leaves(value, prefix=''):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(leaves(child, f'{prefix}.{key}' if prefix else key))
        return result
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{prefix}: expected finite nonnegative numeric cap')
    return {prefix: value}


def violations(before, after):
    old = leaves(before.get('_gate', {}))
    new = leaves(after['_gate'])
    errors = []
    if not new:
        errors.append('empty mobile perf admission budgets')
    for key, cap in old.items():
        if key not in new or new[key] > cap:
            errors.append(f'{key}: {cap} → {new.get(key, "missing")}; restore the cap and fix the regression, never weaken admission')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    args = parser.parse_args()
    # Require Git evidence; shallow/missing refs are errors, not a silent bypass.
    base = subprocess.check_output(['git', 'merge-base', args.base, 'HEAD'], text=True).strip()
    before = json.loads(subprocess.check_output(['git', 'show', f'{base}:{BUDGETS}'], text=True))
    after = json.loads(Path(BUDGETS).read_text())
    errors = violations(before, after)
    for error in errors:
        print(f'PERF RED: {error}')
    if not errors:
        print('Mobile perf budget ratchet: PASS')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
