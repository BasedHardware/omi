#!/usr/bin/env python3
"""Generate Localizable.xcstrings from the Flutter app's ARB files.

Only keys the native code uses are emitted (scanned from `L("key"` calls), so the catalog
stays small. Native-only keys (not yet in the ARB files) come from native.json in this folder:
{"key": {"en": "...", "de": "..."}}. A native key that later lands in the ARB files is taken
from ARB, so upstreaming a string is just adding it there.

Placeholders: ARB `{name}` becomes `%N$@` in order of first appearance; callers pass Strings.
A message that is one ICU `select` is used per case: `L("chatStarterPrompt.goal")` is the `goal`
branch of `chatStarterPrompt`. Other ICU plural/select messages are not converted yet and are reported.

Usage: arb2xcstrings.py --arb-dir <omi>/app/lib/l10n --sources <dir>... --out <xcstrings>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KEY_USE = re.compile(r'\bL\(\s*"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?)"')
# Keys picked at runtime (`L(key)`) are listed as plain literals; native keys are recognizable.
NATIVE_LITERAL = re.compile(r'"(native[A-Z][A-Za-z0-9_]*)"')
PLACEHOLDER = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')
ICU = re.compile(r'\{[A-Za-z_][A-Za-z0-9_]*\s*,\s*(plural|select)')


def used_keys(sources: list[Path]) -> set[str]:
    keys: set[str] = set()
    for root in sources:
        for path in root.rglob('*.swift'):
            if '/Tests/' in path.as_posix():
                continue
            text = path.read_text(encoding='utf-8')
            keys.update(KEY_USE.findall(text))
            keys.update(NATIVE_LITERAL.findall(text))
    return keys


def select_case(message: str, case: str) -> str | None:
    """The `case` branch of a message that is exactly one `{var, select, ...}`."""
    head = re.match(r'\{\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*select\s*,', message.strip())
    if not head:
        return None
    body, i = message.strip(), head.end()
    while i < len(body):
        name = re.match(r'\s*([A-Za-z0-9_]+)\s*\{', body[i:])
        if not name:
            return None
        start = i + name.end()
        depth, j = 1, start
        while j < len(body) and depth:
            depth += {'{': 1, '}': -1}.get(body[j], 0)
            j += 1
        if name.group(1) == case:
            return body[start:j - 1]
        i = j
    return None


def load_arbs(arb_dir: Path) -> dict[str, dict[str, str]]:
    locales: dict[str, dict[str, str]] = {}
    for path in sorted(arb_dir.glob('app_*.arb')):
        data = json.loads(path.read_text(encoding='utf-8'))
        locale = data.get('@@locale') or path.stem.removeprefix('app_')
        locales[locale] = {k: v for k, v in data.items() if not k.startswith('@') and isinstance(v, str)}
    return locales


def convert(value: str) -> str:
    order: list[str] = []

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in order:
            order.append(name)
        return f'%{order.index(name) + 1}$@'

    return PLACEHOLDER.sub(repl, value.replace('%', '%%'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--arb-dir', type=Path, required=True)
    parser.add_argument('--sources', type=Path, nargs='+', required=True)
    parser.add_argument('--native', type=Path, default=Path(__file__).with_name('native.json'))
    parser.add_argument('--out', type=Path, required=True)
    # A key added to native.json carries en + de; upstream's other locales follow later, so a
    # staleness gate (`make strings-check`) must not fail on them. Keys absent everywhere
    # ("MISSING") still fail.
    parser.add_argument('--allow-untranslated', action='store_true')
    args = parser.parse_args()

    keys = used_keys(args.sources)
    arbs = load_arbs(args.arb_dir)
    native = json.loads(args.native.read_text(encoding='utf-8')) if args.native.exists() else {}

    strings: dict[str, dict] = {}
    missing: list[str] = []
    untranslated: dict[str, list[str]] = {}
    icu: list[str] = []
    for key in sorted(keys):
        per_locale = {loc: table[key] for loc, table in arbs.items() if key in table}
        if '.' in key:
            base, case = key.split('.', 1)
            per_locale = {
                loc: value for loc, table in arbs.items()
                if base in table and (value := select_case(table[base], case))
            }
        if 'en' not in per_locale:
            per_locale = native.get(key, {})
            # Same rule as upstream `app/scripts/l10n.py`: a new key ships in every locale.
            gaps = sorted(set(arbs) - set(per_locale))
            if 'en' in per_locale and gaps:
                untranslated[key] = gaps
        if 'en' not in per_locale:
            missing.append(key)
            continue
        if any(ICU.search(v) for v in per_locale.values()):
            icu.append(key)
            continue
        strings[key] = {
            'extractionState': 'manual',
            'localizations': {
                loc: {'stringUnit': {'state': 'translated', 'value': convert(value)}}
                for loc, value in sorted(per_locale.items())
            },
        }

    catalog = {'sourceLanguage': 'en', 'strings': strings, 'version': '1.0'}
    args.out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    locales = {loc for entry in strings.values() for loc in entry['localizations']}
    print(f'wrote {len(strings)} keys in {len(locales)} locales to {args.out}')
    for key in missing:
        print(f'MISSING (add to ARB or native.json): {key}', file=sys.stderr)
    for key, gaps in sorted(untranslated.items()):
        print(f'UNTRANSLATED native key {key}: missing {", ".join(gaps)}', file=sys.stderr)
    if untranslated:
        note = ' (not a failure with --allow-untranslated)' if args.allow_untranslated else ''
        print(f'{len(untranslated)} native keys wait for upstream translations{note}', file=sys.stderr)
    for key in icu:
        print(f'SKIPPED ICU plural/select (not converted yet): {key}', file=sys.stderr)
    if missing:
        return 1
    if untranslated and not args.allow_untranslated:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
