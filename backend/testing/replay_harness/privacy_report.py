"""Identifier-free privacy qualification counters and expiry-boundary margins."""

from testing.replay_harness.gen_privacy_timeline import FAULTS, KINDS
from testing.replay_harness.privacy_faults import not_applicable_reason

OFFSETS = (0, 1, 59, 60, 61, 300)


def summary(bound_s=60.0, ttl_override_s=None, min_verified_transitions=1000):
    offsets = sorted(set((*OFFSETS, bound_s)))
    return {
        'scope': 'cache_staleness_only',
        'wall_clock_decisions_not_simulated': ['legal_hold_gate_age', 'byok_heartbeat_age'],
        'min_verified_transitions': min_verified_transitions,
        'qualification_minimum': 1000,
        'qualification_met': False,
        'verified_transitions': 0,
        'verified_baselines': 0,
        'not_applicable_transitions': 0,
        'unverified_transitions': 0,
        'transition_results': [],
        'fault_coverage': {
            family: {
                fault: {
                    'applicable': not not_applicable_reason(family, fault),
                    'not_applicable_reason': not_applicable_reason(family, fault),
                    'applied': 0,
                    'attempted': 0,
                    'completed': 0,
                    'verified': 0,
                    'baselines': 0,
                    'not_applicable': 0,
                    'unverified': 0,
                }
                for fault in FAULTS
            }
            for family in KINDS
        },
        'bound_s': bound_s,
        'bound_comparison': 'offset_s >= bound_s',
        'ttl_override_s': ttl_override_s,
        'attempted_transitions': 0,
        'transitions': 0,
        'completed_transitions': 0,
        'probes': 0,
        'mismatches': 0,
        'early_mismatches': 0,
        'unexpected_decisions': 0,
        'errors': [],
        'overlap_probes': 0,
        'bound_margin_s': None,
        'bound_margin_s_by_family': dict.fromkeys(KINDS),
        'expiry_samples_by_family': dict.fromkeys(KINDS, 0),
        'max_observed_staleness_seconds': dict.fromkeys(KINDS, 0),
        'families': dict.fromkeys(KINDS, 0),
        'faults': dict.fromkeys(FAULTS, 0),
        'cache_events': {},
        'redis_fault_calls': {},
        'by_family_fault_offset': {
            family: {
                fault: {
                    str(float(offset)): {'probes': 0, 'stale': 0, 'mismatches': 0, 'errors': 0} for offset in offsets
                }
                for fault in FAULTS
            }
            for family in KINDS
        },
    }


def observe_probe(details, row, offset, observed, expected, before):
    cell = details['by_family_fault_offset'][row['family']][row['fault']][str(float(offset))]
    cell['probes'] += 1
    details['probes'] += 1
    if observed == expected:
        return
    if observed != before:
        details['unexpected_decisions'] += 1
    cell['stale'] += 1
    family = row['family']
    details['max_observed_staleness_seconds'][family] = max(details['max_observed_staleness_seconds'][family], offset)
    if offset >= details['bound_s']:
        cell['mismatches'] += 1
        details['mismatches'] += 1
    else:
        details['early_mismatches'] += 1


def observe_expiry(details, family, now_s, expiry_ms):
    # PEXPIRETIME is the actual absolute expiry boundary of the published key,
    # not its requested/configured TTL. At a closed expiry boundary, zero
    # margin is NOT safe; the exact-bound probe decides qualification.
    margin = round(details['bound_s'] - (expiry_ms / 1000 - now_s), 6)
    details['expiry_samples_by_family'][family] += 1
    old = details['bound_margin_s_by_family'][family]
    details['bound_margin_s_by_family'][family] = margin if old is None else min(old, margin)
    old = details['bound_margin_s']
    details['bound_margin_s'] = margin if old is None else min(old, margin)


def table(details):
    """One row per family/fault, including explicit zeros; cells are stale/mismatch/probes."""
    offsets = (59, 60, 61, 300)
    lines = [
        '| family | fault | verified / completed | +59s | +60s | +61s | +300s | max stale s | margin s |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for family, faults in details['by_family_fault_offset'].items():
        for fault, cells in faults.items():
            coverage = details['fault_coverage'][family][fault]
            if not coverage['applicable']:
                lines.append(f'| {family} | {fault} | N/A | N/A | N/A | N/A | N/A | N/A | N/A |')
                continue
            counts = f"{coverage['verified']}/{coverage['completed']}"
            if fault == 'none':
                counts += ' (baseline)'
            values = []
            for offset in offsets:
                cell = cells[str(float(offset))]
                values.append(f"{cell['stale']}/{cell['mismatches']}/{cell['probes']}")
            maximum = details['max_observed_staleness_seconds'][family]
            margin = details['bound_margin_s_by_family'][family]
            lines.append(f'| {family} | {fault} | {counts} | ' + ' | '.join(values) + f' | {maximum} | {margin} |')
    return '\n'.join(lines)


def observe_transition(details, record):
    coverage = details['fault_coverage'][record['family']][record['fault']]
    coverage['attempted'] += 1
    coverage['completed'] += int(record['completed'])
    coverage['applied'] += int(record['fault_applied'])
    if not record['fault_applicable']:
        status, counter = 'not_applicable', 'not_applicable_transitions'
    elif record['completed'] and record['probe_errors'] == 0 and record['fault'] == 'none':
        status, counter = 'baseline', 'verified_baselines'
    elif record['completed'] and record['fault_applied'] and record['probe_errors'] == 0:
        status, counter = 'verified', 'verified_transitions'
    else:
        status, counter = 'unverified', 'unverified_transitions'
    record['verification'] = status
    record['gate_eligible'] = status == 'verified'
    details[counter] += 1
    cell_key = {
        'verified': 'verified',
        'baseline': 'baselines',
        'not_applicable': 'not_applicable',
        'unverified': 'unverified',
    }[status]
    coverage[cell_key] += 1
