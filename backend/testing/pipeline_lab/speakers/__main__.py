"""``python -m testing.pipeline_lab.speakers <command>``: the speaker lab's commands."""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    commands = {
        'bench': 'testing.pipeline_lab.speakers.bench',
        'export-owner': 'testing.pipeline_lab.speakers.owner_export',
        'silver': 'testing.pipeline_lab.speakers.silver',
    }
    if not argv or argv[0] not in commands:
        print('usage: python -m testing.pipeline_lab.speakers {' + '|'.join(commands) + '} ...', file=sys.stderr)
        return 2
    import importlib

    return importlib.import_module(commands[argv[0]]).main(argv[1:])


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
