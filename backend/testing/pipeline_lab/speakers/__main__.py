"""``python -m testing.pipeline_lab.speakers <command>``: the speaker lab's commands."""

from __future__ import annotations

import sys
import importlib


def main(argv: list[str]) -> int:
    commands = {
        'bench': 'testing.pipeline_lab.speakers.bench',
        'words': 'testing.pipeline_lab.speakers.bench:words_main',
        'export-owner': 'testing.pipeline_lab.speakers.owner_export',
        'silver': 'testing.pipeline_lab.speakers.silver',
        'diagnose': 'testing.pipeline_lab.speakers.prod_diagnose',
    }
    if not argv or argv[0] not in commands:
        print('usage: python -m testing.pipeline_lab.speakers {' + '|'.join(commands) + '} ...', file=sys.stderr)
        return 2

    module, _, function = commands[argv[0]].partition(':')
    return getattr(importlib.import_module(module), function or 'main')(argv[1:])


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
