"""Original producer proof in off mode, plus the opt-in lease predicate matrix."""

from datetime import datetime, timezone
import json

import pytest

from utils.batch_pipeline import record_producer_proof as proof


def inventory(items):
    return {'kind': 'List', 'apiVersion': 'v1', 'metadata': {'resourceVersion': '1'}, 'items': items}


def pod(name, start, *, namespace='prod-omi-backend', extra_start=None):
    starts = [start] if extra_start is None else [start, extra_start]
    return {
        'metadata': {'name': name, 'namespace': namespace, 'labels': {'app.kubernetes.io/name': 'pusher'}},
        'status': {
            'containerStatuses': [
                {'state': {'running': {'startedAt': datetime.fromtimestamp(s, timezone.utc).isoformat()}}}
                for s in starts
            ]
        },
    }


@pytest.fixture
def load(tmp_path, monkeypatch):
    monkeypatch.setattr(proof.time, 'time', lambda: 1000)

    def read(items):
        path = tmp_path / 'pods.json'
        path.write_text(json.dumps(inventory(items)))
        return proof.load_pusher_pod_proof(path, datetime.fromtimestamp(999, timezone.utc).isoformat())

    return read


def test_absent_pod_and_later_container_start_prove_dead(load):
    token = {'t': {'pod': 'old', 'process_started_at': 900}}
    assert proof.producer_tokens_dead(token, load([]))
    assert proof.producer_tokens_dead(token, load([pod('old', 950)]))
    assert not proof.producer_tokens_dead(token, load([pod('old', 800)]))
    assert not proof.producer_tokens_dead(token, load([pod('old', 900)]))
    # btime integer seconds and start ticks can place the stored process epoch
    # before its live container's timestamp. That is not a restart proof.
    assert not proof.producer_tokens_dead(token, load([pod('old', 900.75)]))
    assert not proof.producer_tokens_dead(token, load([pod('old', 902)]))
    assert proof.producer_tokens_dead(token, load([pod('old', 902.01)]))
    assert not proof.producer_tokens_dead(token, load([pod('old', 950, extra_start=800)]))


def test_live_or_unknown_identity_never_uses_stoppage_fallback(load):
    current = load([pod('live', 800)])
    assert not proof.producer_tokens_dead(
        {'t': {'pod': 'live', 'process_started_at': 900}}, current, producers_stopped=True
    )
    for value in (
        {},
        False,
        'unknown',
        {'pod': '', 'process_started_at': 900},
        {'pod': 'old', 'process_started_at': float('nan')},
        {'pod': 'new', 'process_started_at': 1000},
    ):
        assert not proof.producer_tokens_dead({'t': value}, current, producers_stopped=True)
    assert not proof.producer_tokens_dead(
        {'t': {'pod': 'old', 'process_started_at': 900}}, None, producers_stopped=True
    )


def test_legacy_fallback_is_explicit_and_all_tokens_must_qualify(load):
    assert not proof.producer_tokens_dead({'old': True}, None)
    assert proof.producer_tokens_dead({'old': True}, None, producers_stopped=True)
    mixed = {'old': True, 'known': {'pod': 'live', 'process_started_at': 900}}
    assert not proof.producer_tokens_dead(mixed, load([pod('live', 800)]), producers_stopped=True)
    assert proof.producer_tokens_dead(mixed, load([]), producers_stopped=True)


def test_missing_or_unready_running_state_is_unknown(load):
    item = pod('old', 800)
    item['status'] = {}
    assert not proof.producer_tokens_dead({'t': {'pod': 'old', 'process_started_at': 900}}, load([item]))


@pytest.mark.parametrize('kind', ['List', 'PodList'])
def test_authoritative_api_and_kubectl_list_forms_are_accepted(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(proof.time, 'time', lambda: 1000)
    raw = {**inventory([]), 'kind': kind}
    path = tmp_path / 'pods.json'
    path.write_text(json.dumps(raw))
    assert proof.load_pusher_pod_proof(path, datetime.fromtimestamp(999, timezone.utc).isoformat())['pods'] == {}
    with pytest.raises(ValueError):
        proof.load_pusher_pod_proof(path, datetime.fromtimestamp(999, timezone.utc).replace(tzinfo=None).isoformat())


def test_file_and_freshness_are_bound_and_wrong_scope_refuses(load, monkeypatch):
    first = load([])
    other = load([pod('other', 800)])
    assert first['file_sha256'] != other['file_sha256']
    with pytest.raises(ValueError):
        load([pod('old', 800, namespace='other')])
    monkeypatch.setattr(proof.time, 'time', lambda: 1400)
    assert not proof.producer_tokens_dead({'t': {'pod': 'old', 'process_started_at': 900}}, first)


def test_absence_inventory_must_postdate_process_start_uncertainty(load):
    assert not proof.producer_tokens_dead({'t': {'pod': 'new', 'process_started_at': 998}}, load([]))


def test_abandoned_token_is_dead_without_pod_proof_but_reconnect_is_live(load):
    abandoned = {'pod': 'live', 'process_started_at': 900, 'abandoned_at': 950}
    current = load([pod('live', 800)])
    assert proof.producer_tokens_dead({'old': abandoned}, current)
    assert proof.producer_tokens_dead({'old': abandoned}, None)
    assert proof.producer_tokens_dead({'old': abandoned}, {**current, 'captured_at': 1})
    assert not proof.producer_tokens_dead(
        {'old': abandoned, 'new': {'pod': 'live', 'process_started_at': 900}}, current
    )


@pytest.mark.parametrize('abandoned', [None, True, '950', float('nan'), float('inf'), 899])
def test_malformed_abandon_attestation_never_proves_dead(load, abandoned):
    token = {'t': {'pod': 'live', 'process_started_at': 900, 'abandoned_at': abandoned}}
    assert not proof.producer_tokens_dead(token, load([pod('live', 800)]))
    assert not proof.producer_tokens_dead(token, None)


@pytest.mark.parametrize('raw', [{}, {'kind': 'List', 'apiVersion': 'v1', 'items': []}])
def test_malformed_list_refuses(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(proof.time, 'time', lambda: 1000)
    path = tmp_path / 'pods.json'
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        proof.load_pusher_pod_proof(path, datetime.fromtimestamp(999, timezone.utc).isoformat())


@pytest.mark.parametrize(
    'expiry,signal,dead',
    [
        (999, 1, False),  # heartbeat still inside 3600s
        (999, -3000, False),  # invalid epoch
        (999, 500, False),
        (1000, 1, False),  # strict boundary
    ],
)
def test_lease_needs_both_deadlines_load_safe(load, monkeypatch, expiry, signal, dead):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    token = {
        't': {
            'pod': 'live',
            'process_started_at': 900,
            'last_signal_at': signal,
            'lease_expires_at': expiry,
            'signal_source': 'frames',
        }
    }
    assert proof.producer_tokens_dead(token, load([pod('live', 800)]), uid='synthetic') is dead


@pytest.mark.parametrize(
    'change',
    [
        {},
        {'lease_expires_at': 9999},
        {'last_signal_at': 9000},
        {'lease_expires_at': float('nan')},
        {'last_signal_at': True},
        {'lease_expires_at': 6401},
    ],
)
def test_three_quiet_clocks_and_malformed_fields(monkeypatch, change):
    monkeypatch.setattr(proof.time, 'time', lambda: 10000)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    value = {
        'pod': 'live',
        'process_started_at': 100,
        'last_signal_at': 1,
        'lease_expires_at': 3601,
        'signal_source': 'custody_append',
        **change,
    }
    expected = change in ({}, {'lease_expires_at': 9999}, {'lease_expires_at': 6401})
    assert proof.producer_tokens_dead({'s': value}, None, uid='synthetic') is expected
