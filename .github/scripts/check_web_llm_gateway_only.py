#!/usr/bin/env python3
"""Reject direct LLM provider access from production web code."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SOURCE_SUFFIXES = {'.js', '.jsx', '.mjs', '.ts', '.tsx'}
SKIPPED_PARTS = {
    '.next',
    '__tests__',
    'coverage',
    'node_modules',
    'test',
    'tests',
}
FORBIDDEN_SOURCE_PATTERNS = {
    # SCA-118 covers inference traffic. The providers' organization namespaces
    # (api.anthropic.com/v1/organizations/*, api.openai.com/v1/organization/*)
    # serve only org-admin reporting — no model traffic exists there — and the
    # admin dashboard's cost legs (web/admin/lib/services/provider-costs.ts)
    # read spend from them with dedicated cost-report keys.
    'direct provider URL': re.compile(
        r'api\.anthropic\.com(?!/v1/organizations/)'
        r'|api\.openai\.com(?!/v1/organization/)'
        r'|openrouter\.ai',
        re.I,
    ),
    'direct provider credential': re.compile(
        r'\b(?:ANTHROPIC|CLAUDE|OPENAI|OPENROUTER)_API_KEY\b'
    ),
    'Anthropic browser/server SDK': re.compile(r'@anthropic-ai/sdk'),
    'OpenAI browser/server SDK': re.compile(
        r'(?:from\s+[\'"]openai[\'"]|require\(\s*[\'"]openai[\'"]\s*\))'
    ),
}
FORBIDDEN_DEPENDENCIES = {'@anthropic-ai/sdk', 'openai'}


def find_violations(root: Path) -> list[str]:
    web_root = root / 'web'
    violations: list[str] = []
    if not web_root.is_dir():
        return [f'{web_root}: web source directory is missing']

    for path in sorted(web_root.rglob('*')):
        if not path.is_file() or any(part in SKIPPED_PARTS for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        if path.name == 'package.json':
            violations.extend(_package_violations(path, relative))
            continue
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        source = path.read_text(encoding='utf-8')
        for description, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
            if pattern.search(source):
                violations.append(f'{relative}: {description}')
    return violations


def _package_violations(path: Path, relative: str) -> list[str]:
    manifest = json.loads(path.read_text(encoding='utf-8'))
    violations = []
    for section in ('dependencies', 'devDependencies', 'optionalDependencies'):
        dependencies = manifest.get(section, {})
        if not isinstance(dependencies, dict):
            continue
        for name in sorted(FORBIDDEN_DEPENDENCIES & dependencies.keys()):
            violations.append(f'{relative}: direct provider dependency {name!r} in {section}')
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    violations = find_violations(args.root.resolve())
    if violations:
        print('Web LLM requests must use the authenticated Omi gateway:')
        for violation in violations:
            print(f'- {violation}')
        return 1
    print('web LLM gateway-only guard passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
