"""Outage drills for armed batch vendor routing (testing/vendor_drill.py): vendors and GPUs fail
mid-batch and no recording is lost.

Each drill serves a configured route table (Modulate primary for languages Parakeet cannot serve,
Soniox failover-only), runs the real admission, slice C health, provider stage, GPU scheduler and
ordered merge on SimStore, and scripts the fake vendors' HTTP answers over drill time. Synthetic
owners and audio only; no vendor is called and nothing leaves the process.

Every drill checks the fixed requirements (``assert_invariants``): no unit lost or dropped, audio
kept until commit, no vendor billed twice for one unit, no transcript written twice, per-owner
capture order, privacy fenced before every vendor POST and the queue's concurrency cap.

Paid-once (vendor_route_contracts.check_new_attempt) still ends a unit terminal ``failed_held``
once every permitted vendor has billed it a failure: the units a vendor failed before its breaker
opened, and the unit each failed half-open probe carried. Those drills pin that loss (each such
unit billed exactly once per vendor) and bound it, pending a decision on the paid-once rule.
"""

import pytest

from database import sync_ledger  # noqa: F401  # warm legacy_dark's lazy ledger import outside the call budget
from testing.vendor_drill import DrillWorld, VendorScript, assert_invariants, route_table
from utils.batch_pipeline import admission  # noqa: F401  # warm its fair-use/backfill imports
from utils.batch_pipeline.vendor_route_contracts import VENDOR_HELD

OUTAGE = (300.0, 2100.0)  # 30 min, starting after the first units have committed
QUIET, BUSY = 3, 6  # owners: ~2 vs ~4 provider units a minute
# Units a vendor may bill a failure before slice C opens its breaker (five failures and no
# success in the error window), plus the calls already in flight when it opens.
TRIP_BOUND = 8
PROBE_INTERVAL = 30.0  # slice C: one fleet-wide half-open probe per interval while open


def paid_once_bound(down_seconds: float, vendors: int = 1) -> int:
    """Terminal units a ``down_seconds`` outage of ``vendors`` vendors may cost under paid-once:
    the trip, then one probe-carrying unit per probe interval."""
    return vendors * (TRIP_BOUND + int(down_seconds // PROBE_INTERVAL) + 1)


def assert_paid_once_losses(world, bound: int) -> None:
    """Every vendor-cause failed_held unit was billed exactly once by each vendor it tried, and
    only failures: paid-once consumed it, nothing else did."""
    summary = assert_invariants(world, all_committed=False, allow_failed_held=bound)
    for segment_id in summary['failed_held_vendor']:
        tried = [
            service
            for service, outcome in attempts(world, segment_id)
            if outcome not in {'rate_limited', 'credit_refusal'}
        ]
        assert tried and len(tried) == len(set(tried)), tried
        assert not {outcome for _, outcome in attempts(world, segment_id)} & {'ok', 'silence'}
    assert set(summary['states']) <= {'committed', 'quarantined'}, summary


def populate(world, *, owners=QUIET, until=1200.0, every=40.0, languages=('ja', 'en'), duration=30.0):
    """Each owner uploads a unit every ``every`` seconds, alternating languages, until ``until``."""
    names = [f'owner-{index:02d}' for index in range(owners)]
    for owner in names:
        world.add_owner(owner)
    t, index = 0.0, 0
    while t < until:
        for offset, owner in enumerate(names):
            world.upload(owner, languages[(index + offset) % len(languages)], t + offset * 0.5, duration=duration)
        t += every
        index += 1
    return world


def calls(world, service, *, mode=None):
    return sum(1 for post in world.posts if post.service == service and (mode is None or post.mode == mode))


def attempts(world, segment_id):
    return [(a['service'], a['outcome']) for a in world.job(segment_id).get('provider_attempts', [])]


# --- baseline --------------------------------------------------------------------------------------


def test_baseline_every_unit_commits_once_on_its_selected_route(monkeypatch):
    world = populate(DrillWorld(monkeypatch)).run(3600)
    summary = assert_invariants(world)
    assert calls(world, 'soniox') == 0
    assert set(world.billed_posts().values()) == {1}
    assert {world.units[s].route for s in world.provider_units()} == {'modulate'}
    assert world.gpu_completions == len(world.units) - len(world.provider_units())
    assert not summary['breaker_open_at']


# --- Modulate --------------------------------------------------------------------------------------


@pytest.mark.parametrize('mode', ['5xx', 'hang', 'garbage', 'empty', '429', '402'])
def test_modulate_failure_mid_batch_fails_over_to_soniox_and_commits_everything(monkeypatch, mode):
    world = populate(DrillWorld(monkeypatch, modulate=VendorScript([(*OUTAGE, mode)])), owners=BUSY)
    summary = assert_invariants(world.run(4 * 3600))
    assert calls(world, 'soniox', mode='ok') > 0
    for segment_id in world.provider_units():
        billed = [
            service
            for service, outcome in attempts(world, segment_id)
            if outcome not in {'rate_limited', 'credit_refusal'}
        ]
        assert billed in (['modulate'], ['modulate', 'soniox'], ['soniox']), billed
    if mode != 'empty':  # validated-empty degrades, it does not open
        assert 'modulate' in summary['breaker_open_at']


@pytest.mark.parametrize('mode', ['5xx', 'hang'])
@pytest.mark.parametrize('owners', [QUIET, BUSY])
def test_modulate_outage_without_a_second_vendor_holds_and_pins_paid_once_losses(monkeypatch, mode, owners):
    """Modulate-only table: the breaker opens at any volume, units wait in vendor_held with their
    audio and commit once Modulate is back. Units Modulate billed a failure (before the trip, or
    carrying a half-open probe) end failed_held under paid-once."""
    world = DrillWorld(monkeypatch, table=route_table(soniox=False), modulate=VendorScript([(*OUTAGE, mode)]))
    populate(world, owners=owners).run(4 * 3600)
    assert_paid_once_losses(world, paid_once_bound(OUTAGE[1] - OUTAGE[0]))
    assert calls(world, 'soniox') == 0 and 'modulate' in world.breaker_open_seen
    assert world.breaker_open_seen['modulate'] - OUTAGE[0] <= 600


@pytest.mark.parametrize('mode', ['429', '402'])
@pytest.mark.parametrize('owners', [QUIET, BUSY])
def test_modulate_refusals_without_a_second_vendor_lose_nothing(monkeypatch, mode, owners):
    """429s and credits exhausted are unbilled: however long they last, no unit exhausts its
    attempt records, the breaker opens, and every hold drains after recovery."""
    world = DrillWorld(monkeypatch, table=route_table(soniox=False), modulate=VendorScript([(300.0, 7500.0, mode)]))
    summary = assert_invariants(populate(world, owners=owners).run(5 * 3600))
    assert 'modulate' in summary['breaker_open_at']
    # The trip, then one fleet-wide half-open probe per interval: refusals never fan out.
    assert calls(world, 'modulate', mode=mode) <= TRIP_BOUND + 7200.0 / PROBE_INTERVAL + 1


def test_modulate_slow_recovery_and_flapping(monkeypatch):
    script = VendorScript.flapping(300.0, 2100.0, 60.0)
    script.windows += [(2100.0, 3300.0, 'slow')]
    world = DrillWorld(monkeypatch, modulate=script)
    assert_invariants(populate(world, owners=BUSY, until=3000.0).run(5 * 3600))


def test_modulate_flapping_without_a_second_vendor(monkeypatch):
    world = DrillWorld(
        monkeypatch, table=route_table(soniox=False), modulate=VendorScript.flapping(300.0, 2100.0, 60.0)
    )
    populate(world, owners=BUSY).run(4 * 3600)
    assert_paid_once_losses(world, paid_once_bound(OUTAGE[1] - OUTAGE[0]))


# --- Soniox ----------------------------------------------------------------------------------------


@pytest.mark.parametrize('mode', ['5xx', 'hang', 'garbage', '429', '402'])
def test_soniox_failing_while_modulate_is_down(monkeypatch, mode):
    world = DrillWorld(monkeypatch, modulate=VendorScript([(*OUTAGE, '5xx')]), soniox=VendorScript([(*OUTAGE, mode)]))
    populate(world, owners=BUSY).run(4 * 3600)
    if mode in {'429', '402'}:
        assert_invariants(world)  # Soniox refusals are unbilled: units wait, none is lost
    else:
        assert_paid_once_losses(world, paid_once_bound(OUTAGE[1] - OUTAGE[0], vendors=2))


def test_soniox_down_alone_changes_nothing(monkeypatch):
    world = DrillWorld(monkeypatch, soniox=VendorScript([(0.0, 4 * 3600.0, '5xx')]))
    assert_invariants(populate(world, owners=BUSY).run(3600))
    assert calls(world, 'soniox') == 0


def test_both_vendors_down_for_an_hour_holds_with_custody_and_drains(monkeypatch):
    world = DrillWorld(
        monkeypatch,
        modulate=VendorScript([(300.0, 3900.0, '5xx')]),
        soniox=VendorScript([(300.0, 3900.0, '5xx')]),
    )
    populate(world, owners=BUSY).run(1800)
    assert any(world.job(s)['state'] == VENDOR_HELD for s in world.units)
    assert_paid_once_losses(world.run(4 * 3600), paid_once_bound(3600.0, vendors=2))


# --- GPUs ------------------------------------------------------------------------------------------


def test_l4_stockout_below_floor_keeps_every_unit_and_drains_when_capacity_returns(monkeypatch):
    world = DrillWorld(monkeypatch, gpu_workers=1, gpu_seconds_per_audio_second=0.5)
    populate(world, owners=BUSY, languages=('en', 'en', 'ja'))
    world.at(1800.0, lambda w: w.set_gpu_workers(4))
    assert_invariants(world.run(3 * 3600))


def test_gpu_workers_evicted_mid_unit_are_released_by_lease_expiry(monkeypatch):
    world = DrillWorld(monkeypatch, gpu_seconds_per_audio_second=2.0)
    populate(world, languages=('en',))
    for at in (200.0, 500.0, 800.0):
        world.at(at, lambda w: w.set_gpu_workers(4, evict=True))
    assert_invariants(world.run(2 * 3600))


def test_zero_gpu_workers_with_healthy_vendors_waits_for_capacity(monkeypatch):
    """No GPU worker for an hour while both vendors are healthy: GPU-routed units wait with
    custody (selection treats GPU as always healthy, nothing spills them to a vendor) and commit
    once workers return; vendor-routed units are unaffected."""
    world = DrillWorld(monkeypatch, gpu_workers=0)
    populate(world, languages=('en', 'ja'))
    world.at(3600.0, lambda w: w.set_gpu_workers(4))
    assert_invariants(world.run(3 * 3600))
    gpu_commits = [at for at, s in world.commits if world.units[s].route == 'gpu']
    assert min(gpu_commits) >= world.clock.now - 2 * 3600  # nothing on GPU committed before capacity returned
    assert {world.units[s].route for s in world.units if world.units[s].language == 'en'} == {'gpu'}


# --- worker restarts, duplicates, late results -----------------------------------------------------


def test_worker_restart_mid_vendor_call_reconciles_then_fails_over(monkeypatch):
    world = populate(DrillWorld(monkeypatch), until=200.0)
    world.crash_first_calls()
    assert_invariants(world.run(3 * 3600))
    for segment_id in world.provider_units():
        assert attempts(world, segment_id) == [('modulate', 'abandoned'), ('soniox', 'ok')]


def test_worker_restart_mid_vendor_call_without_a_second_vendor_is_terminal(monkeypatch):
    """Paid-once: an abandoned call is presumed billed, so with no second vendor the unit ends
    failed_held. Pinned until the paid-once rule for abandoned calls is decided."""
    world = populate(DrillWorld(monkeypatch, table=route_table(soniox=False)), until=200.0)
    world.crash_first_calls()
    summary = assert_invariants(world.run(3 * 3600), all_committed=False, allow_failed_held=len(world.units))
    assert sorted(summary['failed_held_vendor']) == sorted(world.provider_units())


def test_duplicate_delivery_outside_the_outbox_fence_calls_the_vendor_once(monkeypatch):
    world = populate(DrillWorld(monkeypatch), until=200.0)
    world.duplicate_first_deliveries()
    assert_invariants(world.run(3600))
    assert set(world.billed_posts().values()) == {1}


def test_a_late_result_after_the_unit_moved_on_is_never_written(monkeypatch):
    """The first call outlives the outbox lease; the watchdog's redelivery abandons it and fails the
    unit over to Soniox, which commits; the late Modulate answer then settles as superseded."""
    world = DrillWorld(monkeypatch, modulate=VendorScript([(0.0, 400.0, 'slow')], slow_seconds=2000.0))
    world.add_owner('owner-a')
    world.upload('owner-a', 'ja', 10.0)
    assert_invariants(world.run(3 * 3600))
    (segment_id,) = world.units
    assert attempts(world, segment_id) == [('modulate', 'abandoned'), ('soniox', 'ok')]
    assert 'soniox' in world.job(segment_id)['result']['result_uri'] or world.artifacts.writes[segment_id] == 2
    assert world.stale_settles == 1


# --- kill switches ---------------------------------------------------------------------------------


@pytest.mark.parametrize('flag', ['BATCH_VENDOR_FAILOVER_ENABLED', 'BATCH_VENDOR_HELD_REDRIVE_ENABLED'])
def test_kill_switch_flipped_off_and_on_mid_outage(monkeypatch, flag):
    world = DrillWorld(monkeypatch, modulate=VendorScript([(*OUTAGE, '5xx')]))
    populate(world, owners=BUSY)
    world.at(900.0, lambda w: w.set_env(flag, 'false'))
    world.at(1500.0, lambda w: w.set_env(flag, 'true'))
    assert_paid_once_losses(world.run(4 * 3600), paid_once_bound(OUTAGE[1] - OUTAGE[0]))


def test_routing_kill_switch_off_during_an_outage_returns_new_units_to_todays_terminal_failure(monkeypatch):
    """Off serves the builtin table, unarmed: no health gate, no failover, no hold (pre-D, as
    production runs today). Every unit Modulate fails while it is off ends failed_held; holds made
    while armed still keep their custody and drain."""
    world = DrillWorld(monkeypatch, modulate=VendorScript([(*OUTAGE, '5xx')]))
    populate(world, owners=BUSY)
    world.at(900.0, lambda w: w.set_env('BATCH_VENDOR_ROUTING_ENABLED', 'false'))
    world.at(1500.0, lambda w: w.set_env('BATCH_VENDOR_ROUTING_ENABLED', 'true'))
    world.run(4 * 3600)
    off = {s for s, u in world.provider_units_admitted_between(900.0, 1500.0)}
    lost = set(world.vendor_cause_failed_held())
    assert lost & off and {attempts(world, s)[0] for s in lost & off} == {('modulate', 'error_5xx')}
    assert_paid_once_losses(world, paid_once_bound(OUTAGE[1] - OUTAGE[0]) + len(off))


# --- languages -------------------------------------------------------------------------------------


def test_languages_route_by_capability(monkeypatch):
    world = DrillWorld(monkeypatch)
    world.add_owner('owner-a')
    for index, language in enumerate(['en', 'de', 'ja', 'zh-TW', 'yo', 'xx', 'multi', '']):
        world.upload('owner-a', language, float(index))
    assert_invariants(world.run(1800))
    routes = {world.units[s].language: world.units[s].route for s in world.units}
    assert routes['en'] == routes['de'] == 'gpu'
    assert routes['ja'] == routes['zh-TW'] == routes['yo'] == 'modulate'


def test_a_language_modulate_returns_empty_for_goes_to_soniox(monkeypatch):
    world = DrillWorld(monkeypatch, modulate=VendorScript([(0.0, 7200.0, 'empty')]))
    world.add_owner('owner-a')
    world.upload('owner-a', 'yo', 0.0)
    assert_invariants(world.run(1800))
    (segment_id,) = world.units
    assert attempts(world, segment_id) == [('modulate', 'empty_validated'), ('soniox', 'ok')]


# --- privacy and caps ------------------------------------------------------------------------------


def test_a_conversation_deleted_while_held_is_never_uploaded(monkeypatch):
    world = DrillWorld(monkeypatch, table=route_table(soniox=False), modulate=VendorScript([(0.0, 1800.0, '429')]))
    world.add_owner('owner-a')
    for index in range(10):
        world.upload('owner-a', 'ja', float(index))
    world.run(600)
    held = [s for s in world.units if world.job(s)['state'] == VENDOR_HELD]
    assert held
    world.customer.delete_conversation('owner-a', world.job(held[0])['conversation_id'])
    deleted_at = world.clock.now
    assert_invariants(world.run(3 * 3600), all_committed=False)
    assert world.job(held[0])['state'] == 'privacy_blocked'
    assert not [p for p in world.posts if p.segment_id == held[0] and p.at >= deleted_at]


def test_private_cloud_sync_off_on_a_live_recording_refuses_custody_and_upload(monkeypatch):
    world = DrillWorld(monkeypatch)
    world.add_owner('owner-a', private_cloud_sync_enabled=False)
    world.upload('owner-a', 'ja', 0.0, live=True)
    world.run(1800)
    assert world.refused_admissions == [('owner-a', 'recording_privacy_changed')]
    assert not world.units and not world.posts


def test_private_cloud_sync_off_does_not_gate_an_upload(monkeypatch):
    """Today's rule: the opt-out gates live-recorded custody only. An uploaded recording is
    transcribed by the vendor as legacy sync does, with no audio retained beyond the unit."""
    world = DrillWorld(monkeypatch)
    world.add_owner('owner-a', private_cloud_sync_enabled=False)
    world.upload('owner-a', 'ja', 0.0)
    assert_invariants(world.run(1800))
    assert calls(world, 'modulate', mode='ok') == 1


def test_daily_caps_are_never_exceeded(monkeypatch):
    world = DrillWorld(
        monkeypatch,
        table=route_table(modulate_daily_hours=0.1, soniox_daily_hours=0.05),
        modulate=VendorScript([(600.0, 1200.0, '5xx')]),
    )
    populate(world, owners=BUSY, languages=('ja',)).run(3600)
    assert_invariants(world, all_committed=False, allow_failed_held=TRIP_BOUND)
    billed = {'modulate': 0.0, 'soniox': 0.0}
    for post in world.posts:
        if post.billed:
            billed[post.service] += world.units[post.segment_id].duration
    assert billed['modulate'] <= 0.1 * 3600 and billed['soniox'] <= 0.05 * 3600
    assert any(world.job(s)['state'] == VENDOR_HELD for s in world.units)  # capped units wait, not drop
