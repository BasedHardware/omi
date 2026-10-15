#!/usr/bin/env python3
"""Generate the public beacon schema from the reviewed fleet registry."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'telemetry'


def schema(registry):
    def obj(properties, **extra):
        return dict(
            type='object', properties=properties, required=list(properties), additionalProperties=False, **extra
        )

    count = dict(type='integer', minimum=0, maximum=1_000_000)
    counter = dict(
        oneOf=[
            obj({'event': {'const': event}, 'outcome': {'enum': outcomes}, 'count': count})
            for event, outcomes in registry['events'].items()
        ]
    )
    histogram = dict(
        oneOf=[
            obj(
                {
                    'name': {'const': name},
                    'buckets': dict(
                        type='array',
                        prefixItems=[obj({'le': {'const': edge}, 'count': count}) for edge in spec['buckets']],
                        items=False,
                        minItems=len(spec['buckets']),
                        maxItems=len(spec['buckets']),
                    ),
                }
            )
            for name, spec in registry['histograms'].items()
        ]
    )
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        'title': 'Omi fleet telemetry v1',
        'allOf': [
            {
                'if': {'properties': {'histograms': {'contains': {'properties': {'name': {'const': name}}}}}},
                'then': {'properties': {'counters': {'contains': {'properties': {'event': {'const': spec['event']}}}}}},
            }
            for name, spec in registry['histograms'].items()
        ],
        **obj(
            {
                'schema_version': {'type': 'integer', 'const': 1},
                'platform': {'enum': registry['platforms']},
                'build_channel': {'enum': registry['build_channels']},
                'app_version': {'type': 'string', 'minLength': 1, 'maxLength': 64},
                'window_start': {'type': 'string', 'format': 'date-time'},
                'window_end': {'type': 'string', 'format': 'date-time'},
                'counters': dict(type='array', items=counter, maxItems=100),
                'histograms': dict(type='array', items=histogram, maxItems=len(registry['histograms'])),
            }
        ),
    }


def inventory_client_events(source):
    section = source.split('### Ops-to-metrics mapping')[1].split('### Reader and source conflicts')[0]
    return {
        columns[0].strip('`')
        for line in section.splitlines()
        if len(columns := [part.strip() for part in line.strip('|').split('|')]) >= 7
        and columns[1].startswith('client;')
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--inventory', type=Path, help='Verify event coverage against the fetched KB inventory')
    args = parser.parse_args()
    registry = json.loads((ROOT / 'fleet_registry.json').read_text())
    if args.inventory:
        expected = inventory_client_events(args.inventory.read_text()) - set(registry['server_observed_events'])
        if expected != set(registry['events']):
            raise SystemExit('fleet registry differs from inventory client events')
    rendered = json.dumps(schema(registry), indent=2) + '\n'
    target = ROOT / 'fleet_schema.json'
    if args.check:
        if not target.exists() or target.read_text() != rendered:
            raise SystemExit('fleet schema is stale; run backend/scripts/generate_fleet_schema.py')
    else:
        target.write_text(rendered)


if __name__ == '__main__':
    main()
