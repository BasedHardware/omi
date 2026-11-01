"""Slice A contracts for all-vendor batch routing: schema, ladder, paid-once bounds, holds, names."""

import copy
import math

import re

import pytest

from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    STTServingSurface,
    provider_is_enabled,
)
from utils.batch_pipeline import vendor_route_contracts as c
from utils.batch_pipeline import vendor_route_metrics as m
from utils.batch_pipeline.provider_stt import PARAKEET_MODEL, resolve_route
from utils.observability.reasons import (
    VendorAttemptOutcome as Outcome,
    VendorHealthReason,
    VendorHoldReason,
    VendorRouteTableOutcome,
)


def _route(price, *, cap=None, budget=None, failover_only=False):
    return {
        'price_usd_per_audio_hour': price,
        'daily_audio_hours_cap': cap,
        'monthly_budget_usd': budget,
        'failover_only': failover_only,
        'speaker_turns': 'discard',
    }


def _option(route, tier='accepted', source='legacy_parity'):
    return {'route': route, 'quality_tier': tier, 'quality_source': source}


def _table():
    return {
        'schema_version': 1,
        'table_version': '2026-11-01a',
        'selection': 'cheapest',
        'gpu_floor_percent': 12.5,
        'routes': {
            'gpu': _route(0.0711),
            'modulate': _route(0.03, cap=3300.0),
            'soniox': _route(0.10, cap=200.0, budget=500.0, failover_only=True),
        },
        'rows': [
            {'language_class': 'gpu_supported', 'options': [_option('gpu'), _option('modulate'), _option('soniox')]},
            {'language_class': 'gpu_unsupported', 'options': [_option('modulate'), _option('soniox', 'unproven', 'x')]},
            {'language_class': 'en', 'options': [_option('modulate'), _option('gpu')]},
            {'language_class': '*', 'options': [_option('modulate')]},
        ],
    }


# --- builtin rung is today's routing ---------------------------------------------------------------

_LANGUAGES = sorted(
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL] | MODULATE_SUPPORTED_LANGUAGES | {'xx', 'zh-TW', 'pt_BR'}
)


@pytest.mark.parametrize('language', [None, '', *_LANGUAGES])
def test_builtin_table_first_capable_route_equals_resolve_route(language):
    route = resolve_route(language)
    expected = 'gpu' if route.stt_route == 'parakeet' else route.provider_service
    assert c.capable_options(c.BUILTIN_TABLE, language)[0].route == expected


def test_builtin_table_is_ordered_unpriced_and_floorless():
    assert c.BUILTIN_TABLE.selection == 'ordered'
    assert c.BUILTIN_TABLE.gpu_floor_percent == 0.0
    assert set(c.BUILTIN_TABLE.routes) == {'gpu', 'modulate'}


def test_vendor_capability_is_code_owned_policy_admission():
    for service in c.VENDOR_SERVICES:
        assert c.route_capable(service, 'en') == provider_is_enabled(service, STTServingSurface.PRERECORDED)
    assert not c.route_capable('deepgram', 'en')
    # Pinned on purpose: Soniox failover needs slice D's reviewed prerecorded admission, not a table edit.
    assert not c.route_capable('soniox', 'en')
    assert c.route_capable('gpu', None)  # unknown is multi, which Parakeet serves
    assert not c.route_capable('gpu', 'ja')


# --- schema ----------------------------------------------------------------------------------------


def test_valid_table_parses_and_rows_resolve_exact_then_class_then_default():
    table = c.RouteTable.from_dict(_table())
    assert table.table_version == '2026-11-01a' and table.gpu_floor_percent == 12.5
    assert table.routes['soniox'].failover_only and table.routes['modulate'].daily_audio_hours_cap == 3300.0
    assert table.row_for('en-US').language_class == 'en'
    assert table.row_for('de').language_class == 'gpu_supported'
    assert table.row_for('ja').language_class == 'gpu_unsupported'
    assert table.row_for(None).language_class == 'gpu_supported'


def test_capable_options_never_include_a_route_policy_does_not_admit():
    table = c.RouteTable.from_dict(_table())
    for language in ('de', 'ja', 'en'):
        assert all(c.route_capable(option.route, language) for option in c.capable_options(table, language))
    assert 'gpu' not in {option.route for option in c.capable_options(table, 'ja')}


def _mutate(path, value):
    def apply(raw):
        target = raw
        for key in path[:-1]:
            target = target[key]
        if value is _DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value

    return apply


_DELETE = object()

MALFORMED = {
    'unknown top-level key': _mutate(('extra',), 1),
    'missing top-level key': _mutate(('gpu_floor_percent',), _DELETE),
    'schema version 2': _mutate(('schema_version',), 2),
    'schema version bool': _mutate(('schema_version',), True),
    'schema version float': _mutate(('schema_version',), 1.0),
    'bad table version': _mutate(('table_version',), 'Has Spaces'),
    'open selection': _mutate(('selection',), 'fastest'),
    'floor above 100': _mutate(('gpu_floor_percent',), 101),
    'floor nan': _mutate(('gpu_floor_percent',), math.nan),
    'unknown route': _mutate(('routes', 'deepgram'), _route(0.01)),
    'missing route config key': _mutate(('routes', 'modulate', 'monthly_budget_usd'), _DELETE),
    'negative price': _mutate(('routes', 'modulate', 'price_usd_per_audio_hour'), -0.01),
    'price unit mistake': _mutate(('routes', 'modulate', 'price_usd_per_audio_hour'), 30),
    'infinite cap': _mutate(('routes', 'modulate', 'daily_audio_hours_cap'), math.inf),
    'bool price': _mutate(('routes', 'modulate', 'price_usd_per_audio_hour'), True),
    'gpu spend cap': _mutate(('routes', 'gpu', 'daily_audio_hours_cap'), 10.0),
    'gpu failover only': _mutate(('routes', 'gpu', 'failover_only'), True),
    'soniox chosen as primary': _mutate(('routes', 'soniox', 'failover_only'), False),
    'speaker turns kept': _mutate(('routes', 'modulate', 'speaker_turns'), 'keep'),
    'cheapest without price': _mutate(('routes', 'gpu', 'price_usd_per_audio_hour'), None),
    'no rows': _mutate(('rows',), []),
    'no default row': _mutate(('rows', 3, 'language_class'), 'fr'),
    'duplicate class': _mutate(('rows', 3, 'language_class'), 'en'),
    'bad class': _mutate(('rows', 3, 'language_class'), 'EN'),
    'empty options': _mutate(('rows', 3, 'options'), []),
    'duplicate option': _mutate(('rows', 3, 'options'), [_option('modulate'), _option('modulate')]),
    'open tier': _mutate(('rows', 3, 'options', 0, 'quality_tier'), 'great'),
    'free-text source': _mutate(('rows', 3, 'options', 0, 'quality_source'), 'see the doc'),
    'gpu on unsupported class': _mutate(('rows', 1, 'options', 0, 'route'), 'gpu'),
    'gpu on unsupported language': _mutate(('rows', 2, 'language_class'), 'ja'),
    'failover-only row': _mutate(('rows', 3, 'options'), [_option('soniox')]),
    'row route without config': _mutate(('routes', 'soniox'), _DELETE),
    'routes not a map': _mutate(('routes',), []),
}


@pytest.mark.parametrize('name', sorted(MALFORMED))
def test_malformed_tables_are_rejected(name):
    raw = copy.deepcopy(_table())
    MALFORMED[name](raw)
    with pytest.raises(c.RouteTableInvalid):
        c.RouteTable.from_dict(raw)


def test_rejection_messages_never_echo_config_content():
    raw = copy.deepcopy(_table())
    raw['table_version'] = 'secret-looking value'
    with pytest.raises(c.RouteTableInvalid) as error:
        c.RouteTable.from_dict(raw)
    assert 'secret' not in str(error.value)


# --- ladder ----------------------------------------------------------------------------------------


@pytest.mark.parametrize('junk', [{'bad': 1}, 'not a table', 7, [], {'rows': None}])
def test_malformed_with_no_last_valid_serves_builtin(junk):
    assert c.RouteTableLadder().resolve(junk) == (c.BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN)


def test_ladder_configured_then_last_valid_then_unset_is_builtin():
    ladder = c.RouteTableLadder()
    table, outcome = ladder.resolve(_table())
    assert outcome is VendorRouteTableOutcome.CONFIGURED and table.table_version == '2026-11-01a'
    broken = copy.deepcopy(_table())
    broken['routes']['soniox']['failover_only'] = False
    assert ladder.resolve(broken) == (table, VendorRouteTableOutcome.LAST_VALID)
    # Unset (or the kill switch) is deliberate: builtin, and last-valid survives for the next malformed read.
    assert ladder.resolve(None) == (c.BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN)
    assert ladder.resolve(broken) == (table, VendorRouteTableOutcome.LAST_VALID)


# --- health ----------------------------------------------------------------------------------------


def test_always_healthy_stub_satisfies_the_interface():
    health: c.VendorHealth = c.AlwaysHealthy()
    assert health.allows('modulate') == (True, VendorHealthReason.HEALTHY)


# --- paid-once attempt bounds ----------------------------------------------------------------------


def _attempt(n, service, outcome, *, audio=30.0):
    return c.VendorAttempt(
        attempt=n,
        service=service,
        token=f't{n}',
        privacy_generation=1,
        started_at=100.0 + n,
        table_version='builtin',
        outcome=outcome,
        settled_at=None if outcome is Outcome.RUNNING else 200.0 + n,
        audio_seconds=audio,
    )


def test_first_attempt_is_one_and_gpu_is_never_a_vendor_attempt():
    assert c.check_new_attempt([], 'modulate') == 1
    with pytest.raises(c.AttemptRefused):
        c.check_new_attempt([], 'gpu')


@pytest.mark.parametrize(
    'prior, service, allowed',
    [
        ([(Outcome.ERROR_5XX, 'modulate')], 'soniox', 2),
        ([(Outcome.ERROR_5XX, 'modulate')], 'modulate', None),  # paid once per vendor
        ([(Outcome.TIMEOUT, 'modulate')], 'modulate', None),
        ([(Outcome.EMPTY_VALIDATED, 'modulate')], 'soniox', 2),  # the Soniox second-chance precedent
        ([(Outcome.CREDIT_REFUSAL, 'modulate')], 'modulate', 2),  # unbilled refusal does not spend the vendor
        ([(Outcome.RATE_LIMITED, 'modulate'), (Outcome.RATE_LIMITED, 'modulate')], 'modulate', 3),
        ([(Outcome.ERROR_5XX, 'modulate'), (Outcome.TIMEOUT, 'soniox')], 'modulate', None),  # two billable
        ([(Outcome.RUNNING, 'modulate')], 'soniox', None),  # one live intent at a time
        ([(Outcome.OK, 'modulate')], 'soniox', None),
        ([(Outcome.SILENCE, 'modulate')], 'soniox', None),
        ([(Outcome.SUPERSEDED, 'modulate')], 'soniox', None),  # our-side terminal, never fails over
        ([(Outcome.RATE_LIMITED, 'modulate')] * 4, 'soniox', None),  # record bound
    ],
)
def test_check_new_attempt_bounds(prior, service, allowed):
    attempts = [_attempt(i + 1, svc, outcome) for i, (outcome, svc) in enumerate(prior)]
    if allowed is None:
        with pytest.raises(c.AttemptRefused):
            c.check_new_attempt(attempts, service)
    else:
        assert c.check_new_attempt(attempts, service) == allowed


def test_silence_is_unbilled_only_when_no_audio_was_sent():
    assert not _attempt(1, 'modulate', Outcome.SILENCE, audio=0.0).billable
    assert _attempt(1, 'soniox', Outcome.SILENCE, audio=30.0).billable
    assert not _attempt(1, 'modulate', Outcome.CREDIT_REFUSAL).billable
    assert _attempt(1, 'modulate', Outcome.EMPTY_VALIDATED).billable


def test_non_contiguous_attempts_are_refused():
    with pytest.raises(c.AttemptRefused):
        c.check_new_attempt([_attempt(2, 'modulate', Outcome.ERROR_5XX)], 'soniox')


def test_billable_bound_holds_for_every_sequence():
    """Exhaustive over short histories: no unit ever records more than two billable attempts or a vendor twice."""
    outcomes = sorted(c.FAILOVER_OUTCOMES)
    frontier = [[]]
    while frontier:
        attempts = frontier.pop()
        billable = [attempt for attempt in attempts if attempt.billable]
        assert len(billable) <= c.MAX_BILLABLE_ATTEMPTS
        assert len({attempt.service for attempt in billable}) == len(billable)
        for service in sorted(c.VENDOR_SERVICES):
            try:
                number = c.check_new_attempt(attempts, service)
            except c.AttemptRefused:
                continue
            for outcome in outcomes:
                frontier.append([*attempts, _attempt(number, service, outcome)])


def test_attempt_round_trips_and_rejects_inconsistent_records():
    attempt = _attempt(1, 'modulate', Outcome.ERROR_5XX)
    assert c.VendorAttempt.from_dict(attempt.to_dict()) == attempt
    bad = {**attempt.to_dict(), 'settled_at': None}
    with pytest.raises(ValueError):
        c.VendorAttempt.from_dict(bad)
    with pytest.raises(ValueError):
        c.VendorAttempt.from_dict({**attempt.to_dict(), 'service': 'gpu'})
    with pytest.raises(ValueError):
        c.VendorAttempt.from_dict({**attempt.to_dict(), 'outcome': 'whatever'})


# --- vendor_held -----------------------------------------------------------------------------------


def _held(redrive_at=500.0, **hold):
    return {
        'state': c.VENDOR_HELD,
        c.HOLD_FIELD: {
            'reason': 'no_healthy_vendor',
            'held_at': 100.0,
            'redrive_at': redrive_at,
            'redrives': 0,
            'waiting_for': ['modulate'],
            **hold,
        },
    }


def test_hold_round_trips():
    hold = c.VendorHold(VendorHoldReason.FUNDS_REFUSAL, 1.0, 2.0, 3, ('modulate', 'soniox'))
    assert c.VendorHold.from_dict(hold.to_dict()) == hold


def _policy_hold(job, now):
    return c.is_vendor_policy_hold(job, now, redrive_seconds=300.0, stale_grace_seconds=60.0)


def test_live_hold_is_a_policy_hold_and_a_stale_one_is_measured():
    assert _policy_hold(_held(), now=400.0)
    assert _policy_hold(_held(), now=560.0)
    assert not _policy_hold(_held(), now=561.0)


def test_far_future_redrive_is_not_trusted():
    assert _policy_hold(_held(redrive_at=500.0), now=200.0)  # exactly one interval out
    assert not _policy_hold(_held(redrive_at=10_000.0), now=200.0)


def test_held_unit_with_a_running_attempt_is_measured_as_a_wedge():
    settled = {**_held(), c.ATTEMPTS_FIELD: [_attempt(1, 'modulate', Outcome.ERROR_5XX).to_dict()]}
    assert _policy_hold(settled, now=400.0)
    running = {**_held(), c.ATTEMPTS_FIELD: [_attempt(1, 'modulate', Outcome.RUNNING).to_dict()]}
    assert not _policy_hold(running, now=400.0)
    malformed = {**_held(), c.ATTEMPTS_FIELD: [{'attempt': 1}]}
    assert not _policy_hold(malformed, now=400.0)


@pytest.mark.parametrize('outcome', [Outcome.OK, Outcome.SILENCE])
def test_held_unit_that_already_has_a_result_is_measured(outcome):
    job = {**_held(), c.ATTEMPTS_FIELD: [_attempt(1, 'modulate', outcome).to_dict()]}
    assert not _policy_hold(job, now=400.0)


@pytest.mark.parametrize('attempts', [{}, None, 'x', ()])
def test_non_list_attempts_are_malformed(attempts):
    assert not _policy_hold({**_held(), c.ATTEMPTS_FIELD: attempts}, now=400.0)


@pytest.mark.parametrize(
    'job',
    [
        {'state': 'provider_pending'},
        {'state': c.VENDOR_HELD},
        _held(redrive_at=50.0),  # redrive before the hold
        _held(waiting_for=[]),
        _held(waiting_for=['gpu']),
        _held(reason='mystery'),
        _held(redrives=-1),
    ],
)
def test_malformed_or_other_states_are_not_policy_holds(job):
    assert not _policy_hold(job, now=200.0)


# --- frozen names ----------------------------------------------------------------------------------


def test_flag_names_are_owned_by_one_slice():
    # Registry rows are each slice's job (the registry checker enforces them once a slice reads a flag).
    assert {owner for owner, _ in c.FLAGS.values()} <= {'B', 'C', 'D', 'E'}
    assert all(re.fullmatch(r'BATCH_VENDOR_[A-Z0-9_]+', name) for name in c.FLAGS)


def test_metric_names_are_frozen_kept_and_backed_by_collectors():
    names = {value for key, value in vars(c).items() if key.startswith('METRIC_')}
    assert len(names) == 15
    assert all(name.startswith('omi_batch_pipeline_vendor_') for name in names)
    collected = {collector._name for collector in m.COLLECTORS}
    assert {name.removesuffix('_total') for name in names} == collected


def test_metric_helpers_fold_open_values_and_never_raise():
    before = m.ATTEMPTS.labels(provider='unknown', outcome='unknown')._value.get()
    m.attempt('deepgram', 'ConnectionError: private', 12.0)
    assert m.ATTEMPTS.labels(provider='unknown', outcome='unknown')._value.get() == before + 1
    m.route_decision('nope', 'nope')
    m.table_load(object())
    m.failover('gpu', 'soniox')
    m.late_result('soniox', 'merged')
    m.paid_intent_violation('modulate')
    m.hold_transition('held')
    m.held_units({VendorHoldReason.CAP_REACHED: 3}, -5.0)
    assert m.HELD_UNITS.labels(reason='cap_reached')._value.get() == 3
    assert m.HELD_UNITS.labels(reason='funds_refusal')._value.get() == 0
    m.health_decision('modulate', VendorHealthReason.BREAKER_OPEN)
    m.breaker_state('modulate', 'open')
    assert m.BREAKER_STATE.labels(provider='modulate', state='open')._value.get() == 1
    assert m.BREAKER_STATE.labels(provider='modulate', state='closed')._value.get() == 0
    m.audio_hours('soniox', 1.5, None)
    m.cap_hit('modulate', 'daily_cap_reached')
