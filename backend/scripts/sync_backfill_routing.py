#!/usr/bin/env python3
"""Compose the three control-owned routing values into exact deploy expectations."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

ROUTING_KEYS = frozenset(
    {
        'SYNC_BACKFILL_TASKS_QUEUE',
        'SYNC_BACKFILL_TASKS_HANDLER_URL',
        'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE',
    }
)


def read_routing(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition('=')
        if not sep or key not in ROUTING_KEYS or key in values or not value:
            raise ValueError('invalid sync routing overlay')
        values[key] = value
    if set(values) != ROUTING_KEYS:
        raise ValueError('incomplete sync routing overlay')
    handler = urlsplit(values['SYNC_BACKFILL_TASKS_HANDLER_URL'])
    if (
        handler.scheme != 'https'
        or not handler.hostname
        or handler.username
        or handler.password
        or handler.path != '/v2/sync-jobs/run'
        or handler.query
        or handler.fragment
        or values['SYNC_BACKFILL_TASKS_OIDC_AUDIENCE'] != values['SYNC_BACKFILL_TASKS_HANDLER_URL']
    ):
        raise ValueError('invalid sync routing handler/audience')
    return values


def compose_expected_routing(config: dict, routing: dict[str, str]) -> dict:
    result = deepcopy(config)
    env = result['cloud_run']['services']['backend-sync']['env']
    for key, value in routing.items():
        env[key] = {'value': value}
    return result


def compose_rendered_routing(state: dict, routing: dict[str, str]) -> dict:
    result = deepcopy(state)
    env = result['services']['backend-sync']['env']
    names = [entry['name'] for entry in env]
    if len(names) != len(set(names)):
        raise ValueError('duplicate rendered environment binding')
    result['services']['backend-sync']['env'] = [entry for entry in env if entry['name'] not in routing]
    result['services']['backend-sync']['env'].extend({'name': key, 'value': value} for key, value in routing.items())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--routing-env', required=True, type=Path)
    args = parser.parse_args()
    updated = compose_rendered_routing(json.loads(args.state.read_text()), read_routing(args.routing_env))
    fd, name = tempfile.mkstemp(prefix='.routing-state-', dir=args.state.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(updated, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, args.state)
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == '__main__':
    main()
