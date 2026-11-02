#!/usr/bin/env python3
"""Offline sanitized app telemetry replay plus explicitly proposed host policy."""
import argparse
import copy
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
from pathlib import Path


class UnsupportedTelemetrySchema(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def field(record, key):
    """Preserve missing, null and explicit zero as three distinct states."""
    if key not in record:
        return {'presence': 'absent'}
    return {'presence': 'null' if record[key] is None else 'value', 'value': copy.deepcopy(record[key])}


def validate_fixture(value):
    if value.get('schema_version') != 1 or value.get('provenance') != 'actual_sanitized_app_telemetry_excerpt':
        raise UnsupportedTelemetrySchema('unsupported fixture envelope/provenance')
    if value.get('metadata', {}).get('schema_version') != 2:
        raise UnsupportedTelemetrySchema('only exported telemetry schema 2 is supported; do not reinterpret unknown schema')
    ids = set()
    for scenario in value['scenarios']:
        if scenario['id'] in ids:
            raise ValueError('duplicate scenario ID')
        ids.add(scenario['id'])
        for item in scenario['evidence']:
            if item['source'] not in value['sources']:
                raise ValueError('unresolved source reference')
            if not item['json_pointer'].startswith('/') or not isinstance(item['record'], dict):
                raise ValueError('invalid evidence record')
            if 'schema_version' in item['record'] and item['record']['schema_version'] != 2:
                raise UnsupportedTelemetrySchema('unsupported per-record schema')
    return value


def load_verified(path, manifest):
    path, manifest = Path(path).resolve(), Path(manifest).resolve()
    attestation = json.loads(manifest.read_text())
    hashes = {x['snapshot']: x['sha256'] for x in attestation['local_files']}
    if hashes.get(path.name) != sha(path):
        raise ValueError('local sanitized fixture hash mismatch')
    return validate_fixture(json.loads(path.read_text()))


def merge_records(fixture):
    """Stable source pointer identity, limited to verified cumulative collections.

    Conflicting payloads are retained and flagged. Never collapse two records
    merely because they have the same timestamp or identical metrics.
    """
    validate_fixture(fixture)
    cumulative = set(fixture['cumulative_snapshot_contract']['collections_verified_identical'])
    rows, by_key, variants = [], {}, {}
    ingestion = 0
    for scenario in fixture['scenarios']:
        for item in scenario['evidence']:
            pointer = item['json_pointer']
            collection = pointer.split('/')[1] if pointer != '/' else 'snapshot'
            lineage = fixture['lineage'] if collection in cumulative else item['source']
            identity = (lineage, fixture['metadata']['schema_version'], pointer)
            content = hashlib.sha256(canonical(item['record']).encode()).hexdigest()
            key = (identity, content)
            ref = {'source': item['source'], 'json_pointer': pointer, 'scenario': scenario['id'], 'ingestion_index': ingestion}
            if key in by_key:
                by_key[key]['references'].append(ref)
            else:
                row = {'identity': list(identity), 'content_sha256': content,
                       'collection': collection, 'record': copy.deepcopy(item['record']),
                       'references': [ref], 'first_ingestion_index': ingestion, 'identity_conflict': False}
                rows.append(row)
                by_key[key] = row
                variants.setdefault(identity, []).append(row)
            ingestion += 1
    for group in variants.values():
        if len(group) > 1:
            for row in group:
                row['identity_conflict'] = True
    return rows


def epoch_ms(timestamp):
    value = dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('timestamp timezone is absent')
    delta = value - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


@dataclass(frozen=True)
class Policy:
    """Engineering proposals and synthetic test thresholds, not device facts."""
    progress_timeout_ms: int
    retry_base_ms: int
    retry_cap_ms: int
    retry_limit: int

    def __post_init__(self):
        if any(type(x) is not int or x <= 0 for x in (self.progress_timeout_ms, self.retry_base_ms, self.retry_cap_ms, self.retry_limit)):
            raise ValueError('policy limits must be positive integer milliseconds/counts')
        if self.retry_base_ms > self.retry_cap_ms or self.retry_limit > 100:
            raise ValueError('inconsistent/unbounded retry policy')


class ProposedMonitor:
    """Virtual-time host state model. No hardware I/O, reconnect or subscriptions.

    A policy concern cannot prove continuous packet absence, an app/firmware
    fault, physical proximity or the reason a process was restarted.
    """
    def __init__(self, policy):
        self.policy = policy
        self.link = 'unknown'
        self.service = 'unknown'
        self.subscriptions = 'unknown'
        self.audio = 'unknown'
        self.last_snapshot = None
        self.last_snapshot_at = None
        self.last_progress_at = None
        self.tracking_since = None
        self.last_clock = None
        self.disconnects = []
        self.lifecycle = []
        self.recovery_markers = []
        self.next_retry_at = None
        self.retry_attempts = 0
        self.backlog = {'presence': 'absent'}
        self.unread = {'presence': 'absent'}

    def clock(self, now):
        if type(now) is not int or now < 0 or (self.last_clock is not None and now < self.last_clock):
            raise ValueError('injected monotonic clock must be nonnegative and nondecreasing')
        self.last_clock = now

    def event(self, record, now):
        self.clock(now)
        name = record.get('event_type', record.get('event'))
        if name == 'disconnect':
            self.link = 'disconnected'
            self.subscriptions = 'unknown'
            self.audio = 'unknown'
            self.last_progress_at = None
            self.tracking_since = None
            self.last_snapshot = None
            self.disconnects.append(copy.deepcopy(record))
            if record.get('manual') is False and self.next_retry_at is None and self.retry_attempts < self.policy.retry_limit:
                delay = min(self.policy.retry_cap_ms, self.policy.retry_base_ms * 2 ** self.retry_attempts)
                self.next_retry_at = now + delay
        elif name == 'connected':
            self.link = 'connected'
            self.subscriptions = 'unknown'
            self.audio = 'unknown'
            self.last_progress_at = None
            self.tracking_since = now
            self.next_retry_at = None
            self.last_snapshot = None
        elif name in ('service_start', 'previous_run_unclean'):
            self.lifecycle.append(copy.deepcopy(record))
            self.service = 'started' if name == 'service_start' else 'previous_run_unclean'
            self.subscriptions = 'unknown'
            self.audio = 'unknown'
            self.last_progress_at = None
            self.last_snapshot = None
            self.tracking_since = now
        elif name == 'audio_recovered':
            self.recovery_markers.append(copy.deepcopy(record))
            # Marker alone, even with counters, is not measured restored progress.

    def confirm_subscriptions_for_test(self, now):
        self.clock(now)
        self.subscriptions = 'confirmed_by_injected_test_input'

    def snapshot(self, record, now):
        self.clock(now)
        keys = ('audio_packets_received_current', 'audio_packets_expected_current')
        previous = self.last_snapshot
        session = record.get('connected_at')
        same_session = previous is not None and session is not None and previous.get('connected_at') == session
        values = [record.get(key) for key in keys]
        valid = all(type(x) is int and x >= 0 for x in values)
        old = [previous.get(key) for key in keys] if previous else [None, None]
        old_valid = all(type(x) is int and x >= 0 for x in old)
        progress = valid and old_valid and same_session and values[0] > old[0] and values[1] >= old[1]
        if not same_session or (old_valid and valid and any(new < before for new, before in zip(values, old))):
            self.last_progress_at = None
            self.tracking_since = now
            self.audio = 'unknown'
        if self.tracking_since is None:
            self.tracking_since = now
        if progress:
            self.last_progress_at = now
            self.audio = 'sampled_counter_progress'  # No continuous-health claim.
            self.retry_attempts = 0
        elif not valid:
            self.audio = 'unknown'
        self.last_snapshot = copy.deepcopy(record)
        self.last_snapshot_at = now
        if 'offline_storage_backlog_bytes' in record:
            self.backlog = field(record, 'offline_storage_backlog_bytes')
        if 'offline_storage_unread_packets' in record:
            self.unread = field(record, 'offline_storage_unread_packets')
        return progress

    def take_retry_due(self, now):
        self.clock(now)
        if self.link != 'disconnected' or self.next_retry_at is None or now < self.next_retry_at:
            return False
        self.next_retry_at = None
        self.retry_attempts += 1
        return True  # Proposed intent only; no actual reconnection is performed.

    def status(self, now):
        self.clock(now)
        record = self.last_snapshot or {}
        counters_known = all(type(record.get(k)) is int and record[k] >= 0 for k in ('audio_packets_received_current', 'audio_packets_expected_current'))
        anchor = self.last_progress_at if self.last_progress_at is not None else self.tracking_since
        concern = counters_known and anchor is not None and now - anchor >= self.policy.progress_timeout_ms
        return {'provenance': 'engineering_proposal_not_observed_device_behavior',
                'link': self.link, 'service': self.service, 'subscriptions': self.subscriptions,
                'audio': self.audio, 'policy_progress_timeout_concern': concern,
                'continuous_outage_proven': False, 'root_cause': 'unresolved',
                'backlog': copy.deepcopy(self.backlog),
                'unread_packets': copy.deepcopy(self.unread),
                'backlog_scope': 'last observed snapshot; not continuous measurement',
                'telemetry_insufficient': not counters_known,
                'instrumentation_validity': 'unverified; known numeric values do not validate instrumentation',
                'retry_attempts': self.retry_attempts, 'next_retry_at': self.next_retry_at}


def report(fixture, policy_data):
    validate_fixture(fixture)
    policy = Policy(**{key: policy_data[key] for key in ('progress_timeout_ms', 'retry_base_ms', 'retry_cap_ms', 'retry_limit')})
    scenarios = {x['id']: x for x in fixture['scenarios']}
    observed = {}
    snapshots = [x['record'] for x in scenarios['connected_zero_progress_backlog']['evidence']]
    first, second = snapshots
    a = dt.datetime.fromisoformat(first['exported_at'].replace('Z', '+00:00'))
    b = dt.datetime.fromisoformat(second['exported_at'].replace('Z', '+00:00'))
    delta = round((b - a).total_seconds() * 1000)
    monitor = ProposedMonitor(policy)
    # Link is reported, not independently proved; this is a proposed state input.
    monitor.event({'event': 'connected'}, 0)
    monitor.snapshot(first, 0)
    monitor.snapshot(second, delta)
    observed['connected_zero_progress_backlog'] = {
        'snapshot_delta_ms_rounded': delta,
        'reported_connection_age_at_second_export_ms': epoch_ms(second['exported_at']) - second['connected_at'],
        'current_counters': {k: [field(x, k) for x in snapshots] for k in ('audio_packets_received_current', 'audio_packets_expected_current', 'offline_storage_backlog_bytes', 'offline_storage_unread_packets')},
        'proposed_policy_evaluation': monitor.status(delta)}
    remote = scenarios['foreground_code19_reconnect']['evidence'][0]['record']
    observed['foreground_code19_reconnect'] = {
        'disconnect_reason': field(remote, 'reason'), 'code': field(remote, 'code'),
        'last_rssi': field(remote, 'last_rssi'), 'last_rssi_age_ms': field(remote, 'last_rssi_age_ms'),
        'lost_audio_seconds_recorded': field(remote, 'lost_audio_seconds'),
        'received_recorded': field(remote, 'audio_packets_received'), 'expected_recorded': field(remote, 'audio_packets_expected'),
        'packet_loss_or_root_cause_derived': False}
    burst = [x['record'] for x in scenarios['weak_signal_timeout_burst']['evidence']]
    observed['weak_signal_timeout_burst'] = {'relative_event_ms': [x['ts'] - burst[0]['ts'] for x in burst], 'events': copy.deepcopy(burst), 'rssi_threshold_inferred': False}
    gap = [x['record'] for x in scenarios['low_level_connected_vs_recovery_gap']['evidence']]
    observed['low_level_connected_vs_recovery_gap'] = {
        'low_level_connected_delay_ms': gap[2]['ts'] - gap[0]['ts'],
        'recorded_reconnect_delay_ms': gap[0]['time_to_reconnect_ms'],
        'lifecycle_markers': [copy.deepcopy(x) for x in gap if x.get('event') in ('previous_run_unclean', 'service_start')],
        'continuous_outage_proven': False, 'manual_relaunch_or_battery_kill_proven': False}
    ordering = [x['record'] for x in scenarios['recovery_marker_ordering_and_schema']['evidence']]
    observed['recovery_marker_ordering_and_schema'] = {
        'ingestion_order': [x.get('event_type') for x in ordering],
        'timestamps_in_ingestion_order': [field(x, 'ts') for x in ordering],
        'audio_recovered_timestamp_minus_disconnect_ms': ordering[1]['ts'] - ordering[0]['ts'],
        'recovery_received_counter': field(ordering[1], 'audio_packets_received'),
        'recovery_expected_counter': field(ordering[1], 'audio_packets_expected'),
        'negative_outage_duration_inferred': False}
    rows = merge_records(fixture)
    return {'schema_version': 1, 'layer': 'offline sanitized host telemetry replay',
            'provenance': fixture['provenance'], 'root_cause': 'unresolved',
            'hardware_acceptance': 'not_measured', 'instruction_level_simulation': False,
            'excerpt_record_count_before_dedup': sum(len(x['evidence']) for x in fixture['scenarios']),
            'unique_excerpt_records': len(rows), 'dedup_conflicts': sum(x['identity_conflict'] for x in rows),
            'records_in_ingestion_order': rows, 'scenarios': observed,
            'ingestion_order_scope': 'supplied excerpt traversal order; JSON pointers retain original exported array positions; no original acquisition/ingestion timestamps reconstructed',
            'proposed_policy': copy.deepcopy(policy_data),
            'externally_verified_full_export_counts_not_recomputed_from_excerpt': fixture['externally_verified_full_export_counts_not_recomputed_from_excerpt'],
            'historical_firmware_assignment': 'unknown unless an event has contemporaneous version evidence',
            'not_proven_by_scenario': {name: x['not_proven'] for name, x in scenarios.items()},
            'source_limitations': copy.deepcopy(fixture['source_limitations'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=Path(__file__).parent / 'telemetry-fixtures/sanitized-telemetry.json')
    parser.add_argument('--manifest', type=Path, default=Path(__file__).parent / 'telemetry-fixtures/manifest.json')
    parser.add_argument('--policy', type=Path, default=Path(__file__).parent / 'telemetry-fixtures/proposed-policy.json')
    args = parser.parse_args()
    fixture = load_verified(args.fixture, args.manifest)
    policy_data = json.loads(args.policy.read_text())
    if policy_data.get('provenance') != 'engineering_proposal_not_observed_device_behavior':
        raise ValueError('policy must be labeled engineering proposal')
    print(json.dumps(report(fixture, policy_data), indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
