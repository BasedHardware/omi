"""Process-local per-target connect-refusal backoff policy."""

from utils.stt.connect_backoff import ConnectRefusalBackoff


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(**overrides):
    clock = Clock()
    backoff = ConnectRefusalBackoff(clock=clock, **overrides)
    return clock, backoff


def test_isolated_refusal_does_not_hold_the_target_out():
    clock, backoff = make()
    backoff.acquire('soniox').finish(refused=True)
    assert backoff.acquire('soniox') is not None


def test_three_refusals_inside_the_window_open_the_gate():
    clock, backoff = make()
    events = []
    backoff.on_event = lambda provider, event: events.append(event)
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    assert backoff.acquire('soniox') is None
    assert backoff.acquire('soniox') is None
    assert events == ['opened', 'skipped', 'skipped']


def test_refusals_separated_beyond_the_window_do_not_open():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
        clock.now += 10.5
    assert backoff.acquire('soniox') is not None


def test_other_targets_and_providers_are_not_held_out():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    assert backoff.acquire('modulate-velma-2') is not None
    assert backoff.acquire('soniox-eu') is not None


def test_exactly_one_probe_is_admitted_after_cooldown():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    assert backoff.acquire('soniox') is None
    clock.now += 1.9
    assert backoff.acquire('soniox') is None
    clock.now += 0.1
    probe = backoff.acquire('soniox')
    assert probe is not None
    skipped = sum(backoff.acquire('soniox') is None for _ in range(39))
    assert skipped == 39
    probe.finish(success=True)
    assert backoff.acquire('soniox') is not None


def test_outstanding_normal_refusals_do_not_extend_or_escalate():
    clock, backoff = make()
    held = [backoff.acquire('soniox') for _ in range(5)]
    for lease in held[:3]:
        lease.finish(refused=True)
    opened_at = clock.now
    held[3].finish(refused=True)
    held[4].finish(refused=True)
    clock.now = opened_at + 2.0
    probe = backoff.acquire('soniox')
    assert probe is not None
    probe.finish(refused=True)
    clock.now += 3.9
    assert backoff.acquire('soniox') is None
    clock.now += 0.1
    assert backoff.acquire('soniox') is not None


def test_probe_refusals_double_the_cooldown_to_the_cap():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    wait = 2.0
    for _ in range(4):
        clock.now += wait - 0.1
        assert backoff.acquire('soniox') is None
        clock.now += 0.1
        backoff.acquire('soniox').finish(refused=True)
        wait = min(wait * 2, 10.0)
    clock.now += 9.9
    assert backoff.acquire('soniox') is None
    clock.now += 0.1
    assert backoff.acquire('soniox') is not None


def test_probe_success_resets_window_ladder_and_cooldown():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    clock.now += 2.0
    backoff.acquire('soniox').finish(success=True)
    lease = backoff.acquire('soniox')
    assert lease is not None
    lease.finish(refused=True)
    assert backoff.acquire('soniox') is not None


def test_inflight_normal_success_resets_an_open_gate():
    clock, backoff = make()
    held = [backoff.acquire('soniox') for _ in range(4)]
    for lease in held[:3]:
        lease.finish(refused=True)
    assert backoff.acquire('soniox') is None
    held[3].finish(success=True)
    assert backoff.acquire('soniox') is not None


def test_neutral_probe_finish_recools_without_immediate_second_probe():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    clock.now += 2.0
    backoff.acquire('soniox').finish()
    assert backoff.acquire('soniox') is None
    clock.now += 1.9
    assert backoff.acquire('soniox') is None
    clock.now += 0.1
    assert backoff.acquire('soniox') is not None


def test_stale_normal_leases_cannot_touch_a_probe_epoch():
    clock, backoff = make()
    stale_success = backoff.acquire('soniox')
    stale_failure = backoff.acquire('soniox')
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    clock.now += 2.0
    probe = backoff.acquire('soniox')
    stale_success.finish(success=True)
    stale_failure.finish(refused=True)
    assert backoff.acquire('soniox') is None
    probe.finish(refused=True)
    clock.now += 3.9
    assert backoff.acquire('soniox') is None
    clock.now += 0.1
    assert backoff.acquire('soniox') is not None


def test_stale_lease_results_cannot_reopen_or_reset_a_newer_epoch():
    clock, backoff = make()
    stale = backoff.acquire('soniox')
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    clock.now += 2.0
    probe = backoff.acquire('soniox')
    stale.finish(refused=True)
    assert backoff.acquire('soniox') is None
    probe.finish(refused=True)
    clock.now += 4.0
    stale.finish(refused=True)
    next_probe = backoff.acquire('soniox')
    assert next_probe is not None
    next_probe.finish(success=True)
    fresh = backoff.acquire('soniox')
    fresh.finish(refused=True)
    assert backoff.acquire('soniox') is not None


def test_evicted_identity_state_ignores_stale_lease_results():
    clock, backoff = make(max_identities=1)
    stale_failure = backoff.acquire('a')
    stale_success = backoff.acquire('a')
    stale_probe_success = backoff.acquire('a')
    backoff.acquire('b')
    for _ in range(3):
        backoff.acquire('a').finish(refused=True)
    stale_failure.finish(refused=True)
    clock.now += 1.9
    assert backoff.acquire('a') is None
    stale_success.finish(success=True)
    assert backoff.acquire('a') is None
    clock.now += 0.1
    probe = backoff.acquire('a')
    assert probe is not None
    stale_probe_success.finish(success=True)
    stale_failure.finish(refused=True)
    assert backoff.acquire('a') is None


def test_events_emit_the_bounded_provider_family_never_target_names():
    clock, backoff = make()
    events = []
    backoff.on_event = lambda provider, event: events.append(provider)
    for _ in range(3):
        backoff.acquire('east', provider='soniox').finish(refused=True)
    assert backoff.acquire('east', provider='soniox') is None
    for _ in range(3):
        backoff.acquire('west', provider='custom-vendor').finish(refused=True)
    assert backoff.acquire('west', provider='custom-vendor') is None
    assert events == ['soniox', 'soniox', 'unknown', 'unknown']
    assert all(provider != 'east' and provider != 'west' for provider in events)


def test_finish_is_idempotent():
    clock, backoff = make()
    lease = backoff.acquire('soniox')
    lease.finish(refused=True)
    lease.finish(success=True)
    lease.finish(refused=True)
    assert backoff.acquire('soniox') is not None


def test_forced_escape_is_a_non_probe_lease_whose_success_resets():
    clock, backoff = make()
    events = []
    backoff.on_event = lambda provider, event: events.append(event)
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    assert backoff.acquire('soniox') is None
    escape = backoff.acquire('soniox', force=True)
    assert escape is not None
    assert not escape.probe
    assert events == ['opened', 'skipped', 'escape']
    assert backoff.cooldown_until('soniox') == 2.0
    escape.finish(success=True)
    assert backoff.cooldown_until('soniox') == 0.0
    assert backoff.acquire('soniox') is not None


def test_forced_escape_refusal_and_neutral_finishes_cannot_extend_or_escalate():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    backoff.acquire('soniox', force=True).finish(refused=True)
    assert backoff.cooldown_until('soniox') == 2.0
    assert backoff._states['soniox'].cooldown_seconds == 2.0
    backoff.acquire('soniox', force=True).finish()
    assert backoff.cooldown_until('soniox') == 2.0
    clock.now += 1.9
    assert backoff.acquire('soniox') is None
    clock.now += 0.1
    probe = backoff.acquire('soniox', force=True)
    assert probe is not None and probe.probe


def test_escape_lease_refusal_leaves_a_held_probe_held():
    clock, backoff = make()
    for _ in range(3):
        backoff.acquire('soniox').finish(refused=True)
    clock.now += 2.0
    probe = backoff.acquire('soniox')
    assert probe is not None and probe.probe
    escape = backoff.acquire('soniox', force=True)
    assert escape is not None and not escape.probe
    escape.finish(refused=True)
    assert backoff.acquire('soniox') is None
    probe.finish(refused=True)
    clock.now += 3.9
    assert backoff.acquire('soniox') is None
    clock.now += 0.1
    assert backoff.acquire('soniox') is not None


def test_escape_events_emit_the_bounded_provider_family():
    clock, backoff = make()
    events = []
    backoff.on_event = lambda provider, event: events.append((provider, event))
    for _ in range(3):
        backoff.acquire('east', provider='soniox').finish(refused=True)
    backoff.acquire('east', provider='soniox', force=True)
    for _ in range(3):
        backoff.acquire('west', provider='custom-vendor').finish(refused=True)
    backoff.acquire('west', provider='custom-vendor', force=True)
    assert ('soniox', 'escape') in events
    assert ('unknown', 'escape') in events
    assert all(provider in ('soniox', 'unknown') for provider, _ in events)


def test_cooldown_until_never_creates_state():
    clock, backoff = make()
    assert backoff.cooldown_until('never-seen') == 0.0
    assert 'never-seen' not in backoff._states


def test_cache_is_bounded_and_evicts_the_oldest_identity():
    clock, backoff = make(max_identities=64)
    for index in range(65):
        backoff.acquire(f'target-{index}')
    for _ in range(3):
        backoff.acquire('target-64').finish(refused=True)
    assert backoff.acquire('target-64') is None
    assert len(backoff._states) == 64
    assert 'target-0' not in backoff._states
    assert backoff.acquire('target-0') is not None


def test_lru_touch_keeps_recently_used_identities():
    clock, backoff = make(max_identities=4)
    for identity in ('a', 'b', 'c', 'd'):
        backoff.acquire(identity)
    backoff.acquire('a')
    backoff.acquire('e')
    assert 'a' in backoff._states
    assert 'b' not in backoff._states
