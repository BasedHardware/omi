#!/usr/bin/env python3
"""Check CallKit stimulus metadata; never qualify microphone recovery from it."""
import argparse
import json
from pathlib import Path


def analyze(trace, build):
    if trace.get('schema') != 'omi-audio-interruption-driver/v1' or trace.get('mode') != 'local-call':
        raise ValueError('local-call driver trace required')
    if not build.get('inputs') or trace.get('build') != build:
        raise ValueError('driver build mismatch')
    if (trace.get('audio_retained') is not False or trace.get('external_call') is not False
            or trace.get('includes_calls_in_recents') is not False):
        raise ValueError('local-only metadata scope required')
    events = trace.get('events')
    if not isinstance(events, list) or not events:
        raise ValueError('missing driver events')
    previous = 0
    for e in events:
        if not isinstance(e, dict) or not isinstance(e.get('kind'), str):
            raise ValueError('malformed event')
        if type(e.get('elapsed_ms')) is not int or e['elapsed_ms'] < previous:
            raise ValueError('invalid event clock')
        previous = e['elapsed_ms']
    kinds = [e['kind'] for e in events]
    allowed = {'scene_active', 'provider_configured', 'provider_ready', 'pre_start_call_inventory', 'local_call_start_requested', 'start_transaction_accepted',
               'local_call_start_action', 'local_call_audio_configured', 'local_call_connected_reported',
               'callkit_audio_activated', 'local_call_end_requested', 'end_transaction_accepted',
               'local_call_end_action', 'local_call_end_fulfilled', 'callkit_audio_deactivated', 'completed'}
    errors = sorted(set(kinds) - allowed)
    required = ['scene_active', 'provider_configured', 'provider_ready', 'pre_start_call_inventory', 'local_call_start_requested', 'local_call_start_action',
                'local_call_audio_configured', 'local_call_connected_reported', 'callkit_audio_activated',
                'local_call_end_requested', 'local_call_end_action', 'local_call_end_fulfilled',
                'callkit_audio_deactivated', 'completed']
    complete = kinds.count('completed') == 1 and kinds[-1] == 'completed'
    valid = all(kinds.count(k) == 1 for k in required)
    dwell = None
    if valid:
        positions = [kinds.index(k) for k in required]
        valid = positions == sorted(positions)
        for kind in ('provider_configured', 'provider_ready'):
            config = events[kinds.index(kind)]
            valid = valid and (config.get('maximum_call_groups') == 1
                               and config.get('maximum_calls_per_group') == 1
                               and config.get('supports_generic_handle') is True)
        valid = valid and events[kinds.index('pre_start_call_inventory')].get('active_call_count') == 0
        activated = events[kinds.index('callkit_audio_activated')]['elapsed_ms']
        ended = events[kinds.index('local_call_end_requested')]['elapsed_ms']
        dwell = ended - activated
        valid = valid and 4900 <= dwell <= 10000 and events[-1]['elapsed_ms'] <= 11000
    status = 'passed' if valid and complete and not errors else 'failed' if complete else 'incomplete'
    return {'schema': 'omi-local-call-stimulus-analysis/v1', 'stimulus': status, 'errors': errors,
            'activation_dwell_ms': dwell, 'microphone_interruption_qualified': False,
            'scope': 'Local CallKit activation/deactivation only; analyze the independent microphone trace.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('--build', required=True, type=Path)
    a = p.parse_args()
    try:
        report = analyze(json.loads(a.trace.read_text()), json.loads(a.build.read_text()))
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
        print(json.dumps({'status': 'blocked', 'reason': str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return {'passed': 0, 'failed': 1, 'incomplete': 2}[report['stimulus']]


if __name__ == '__main__':
    raise SystemExit(main())
