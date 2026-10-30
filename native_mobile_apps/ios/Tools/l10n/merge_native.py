#!/usr/bin/env python3
"""Merge per-locale translations into native.json: merge_native.py out_ar.json out_bg.json ...

Each file is {"key": "translation"} for one locale (the locale is the `_xx` suffix of its name), for
all native keys or just new ones. Refuses unknown keys and placeholders that differ from English;
`make strings` then reports any key still missing a locale.
"""
import json
import re
import sys
from pathlib import Path

NATIVE = Path(__file__).with_name('native.json')
PLACEHOLDER = re.compile(r'\{[A-Za-z_]+\}')


def main() -> int:
    native = json.loads(NATIVE.read_text(encoding='utf-8'))
    failed = False
    for name in sys.argv[1:]:
        locale = Path(name).stem.rsplit('_', 1)[-1]
        table = json.loads(Path(name).read_text(encoding='utf-8'))
        for key, value in table.items():
            entry = native.get(key)
            if entry is None:
                print(f'{locale}: unknown key {key}', file=sys.stderr)
                failed = True
            elif not isinstance(value, str) or not value.strip():
                print(f'{locale}: empty {key}', file=sys.stderr)
                failed = True
            elif sorted(PLACEHOLDER.findall(value)) != sorted(PLACEHOLDER.findall(entry['en'])):
                print(f'{locale}: placeholders differ in {key}: {value!r}', file=sys.stderr)
                failed = True
            else:
                entry[locale] = value
    NATIVE.write_text(json.dumps(native, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
