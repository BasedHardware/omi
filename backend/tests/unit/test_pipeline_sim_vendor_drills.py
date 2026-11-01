"""Conformance-sim drills for the multi-vendor provider stage (slice D): each vendor down, all
down, and recovery, on the real admission, ProviderSttStage, OrderedMerge and projection.

Every drill admits Japanese uploads (Parakeet cannot serve them) with legacy sync draining, so each
unit takes the C8 provider route. Assertions are the lead's fixed requirements: no audio or unit
lost, no vendor paid twice for one unit, nothing terminal while a vendor is merely down, and the
held backlog drains after recovery.
"""

from dataclasses import replace

import pytest

from testing.pipeline_sim.clock import SIM_EPOCH
from testing.pipeline_sim.sim import Simulation
from testing.pipeline_sim.trace import GOLDEN_CONFIGS
from utils.batch_pipeline.vendor_route_contracts import VENDOR_HELD

OUTAGE_END = 1500.0  # every upload arrives inside [0, 1200)
TERMINAL_FAILURES = {'quarantined', 'privacy_blocked', 'provider_superseded', 'dead'}


def drill(**changes):
    changes.setdefault('vendor_routing_armed', True)
    sim = Simulation(replace(GOLDEN_CONFIGS['provider_stt_ja'](), **changes))
    result = sim.run()
    jobs = {key: row for (table, key), row in result.store.rows.items() if table == 'jobs'}
    assert jobs, 'the drill must admit provider units'
    assert all(row['stt_route']['stt_route'] == 'provider' for row in jobs.values())
    return sim, result, jobs


def calls(sim, service):
    return sum(count for (_, name), count in sim.vendor_calls.items() if name == service)


def assert_paid_once_per_vendor(sim):
    assert sim.vendor_calls, 'the drill must call a vendor'
    assert max(sim.vendor_calls.values()) == 1, 'a vendor was paid twice for one unit'


def assert_all_committed(jobs):
    states = {row['state'] for row in jobs.values()}
    assert states == {'committed'}, states
    assert not any(row.get('recovery_state') == 'failed_held' for row in jobs.values())


def test_baseline_without_outages_is_one_modulate_call_per_unit():
    sim, _, jobs = drill()
    assert_all_committed(jobs)
    assert_paid_once_per_vendor(sim)
    assert {service for _, service in sim.vendor_calls} == {'modulate'}


def test_modulate_down_with_soniox_in_the_table_fails_over_before_any_modulate_spend():
    sim, _, jobs = drill(vendor_outages=(('modulate', 0.0, OUTAGE_END),), vendor_failover_routes=('soniox',))
    assert_all_committed(jobs)
    assert_paid_once_per_vendor(sim)
    assert calls(sim, 'modulate') == 0  # health refused it: no failed POSTs
    assert calls(sim, 'soniox') == len(jobs)
    for row in jobs.values():
        attempts = row['provider_attempts']
        assert [(a['service'], a['outcome']) for a in attempts] == [('soniox', 'ok')]


def test_modulate_down_before_its_breaker_trips_costs_one_failed_call_then_soniox():
    sim, _, jobs = drill(
        vendor_outages=(('modulate', 0.0, OUTAGE_END),),
        vendor_failover_routes=('soniox',),
        vendor_health_aware=False,
    )
    assert_all_committed(jobs)
    assert_paid_once_per_vendor(sim)
    for row in jobs.values():
        outcomes = [(a['service'], a['outcome']) for a in row['provider_attempts']]
        assert outcomes == [('modulate', 'error_5xx'), ('soniox', 'ok')]


def test_modulate_down_without_a_failover_route_holds_then_drains_after_recovery():
    sim, result, jobs = drill(vendor_outages=(('modulate', 0.0, OUTAGE_END),))
    assert_all_committed(jobs)  # recovery drained every hold through Modulate
    assert_paid_once_per_vendor(sim)
    assert calls(sim, 'soniox') == 0
    for row in jobs.values():
        hold = row['vendor_hold']
        assert hold['reason'] == 'no_healthy_vendor' and hold['waiting_for'] == ['modulate']
        assert hold['redrives'] >= 1
        assert [(a['service'], a['outcome']) for a in row['provider_attempts']] == [('modulate', 'ok')]
    assert result.counters['provider_stt_deferred'] > 0


def test_all_vendors_down_holds_every_unit_with_custody_and_drains_after_recovery():
    sim, _, jobs = drill(
        vendor_outages=(('modulate', 0.0, OUTAGE_END), ('soniox', 0.0, OUTAGE_END)),
        vendor_failover_routes=('soniox',),
    )
    assert_all_committed(jobs)
    assert_paid_once_per_vendor(sim)
    for row in jobs.values():
        assert row['vendor_hold']['waiting_for'] == ['modulate', 'soniox']
        # Recovery returns to the admitted vendor first; Soniox stays failover capacity only.
        assert [(a['service'], a['outcome']) for a in row['provider_attempts']] == [('modulate', 'ok')]


def test_unarmed_modulate_outage_keeps_todays_terminal_failed_held():
    """No configured route table (dormant default): one Modulate call, then today's terminal
    failed_held for every unit, never a failover or a hold a pre-D worker could mishandle."""
    sim, _, jobs = drill(
        vendor_outages=(('modulate', 0.0, 7200.0),),
        vendor_failover_routes=('soniox',),
        vendor_health_aware=False,
        vendor_routing_armed=False,
    )
    assert_paid_once_per_vendor(sim)
    assert calls(sim, 'soniox') == 0
    for row in jobs.values():
        assert (row['state'], row['recovery_state']) == ('quarantined', 'failed_held')
        assert VENDOR_HELD != row['state'] and 'vendor_hold' not in row


def test_soniox_down_alone_changes_nothing():
    sim, _, jobs = drill(vendor_outages=(('soniox', 0.0, OUTAGE_END),), vendor_failover_routes=('soniox',))
    assert_all_committed(jobs)
    assert calls(sim, 'soniox') == 0
    assert calls(sim, 'modulate') == len(jobs)


def test_a_health_blind_total_outage_is_bounded_to_one_paid_call_per_vendor():
    """Without health (breakers never trip) both vendors fail every call: the paid-once bound ends
    each unit terminal after exactly one call per vendor, never a retry storm."""
    sim, _, jobs = drill(
        vendor_outages=(('modulate', 0.0, 7200.0), ('soniox', 0.0, 7200.0)),
        vendor_failover_routes=('soniox',),
        vendor_health_aware=False,
    )
    assert_paid_once_per_vendor(sim)
    for (segment, _), calls in sim.vendor_calls.items():
        assert calls == 1 and segment in jobs
    for row in jobs.values():
        assert (row['state'], row['recovery_state'], row['merge_pending']) == ('quarantined', 'failed_held', False)
        assert [a['outcome'] for a in row['provider_attempts']] == ['error_5xx', 'error_5xx']


@pytest.mark.parametrize('end', [OUTAGE_END, 3600.0])
def test_holds_never_outlive_the_outage_by_more_than_one_redrive(end):
    from config.batch_pipeline_vendor_failover import HELD_REDRIVE_SECONDS_DEFAULT

    sim, result, jobs = drill(vendor_outages=(('modulate', 0.0, end),))
    assert_all_committed(jobs)
    assert not any(row['state'] == VENDOR_HELD for row in jobs.values())
    # Each unit's one successful attempt started within a redrive interval of the recovery.
    for row in jobs.values():
        started = row['provider_attempts'][-1]['started_at'] - SIM_EPOCH
        assert end <= started <= end + HELD_REDRIVE_SECONDS_DEFAULT + 60.0
