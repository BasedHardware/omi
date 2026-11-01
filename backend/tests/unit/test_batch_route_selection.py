"""Slice B of all-vendor routing: route table selection, cohort, kill switch, GPU floor."""

import copy
import json
import logging
from pathlib import Path

import pytest

from config.policy.batch import cohort_bucket
from database import rollout_cohorts as ramp_store
from utils.batch_pipeline import route_selection as rs
from utils.batch_pipeline import vendor_route_contracts as c
from utils.batch_pipeline import vendor_route_metrics as m
from utils.batch_pipeline.provider_stt import resolve_route
from utils.observability.reasons import VendorHealthReason, VendorRouteReason as Reason, VendorRouteTableOutcome
from utils.rollout import runtime_percent

SUPPORTED = 'en'  # deployed Parakeet serves it
UNSUPPORTED = 'ja'  # deployed Parakeet cannot; Modulate can
LANGUAGES = ('en', 'de', 'ja', 'zh-TW', 'yue', 'xx', 'multi', 'und', '', None, 'pt-BR', 'EN', 'ar')
UID = 'synthetic-owner-1'


def _route(price, *, failover_only=False):
    return {
        'price_usd_per_audio_hour': price,
        'daily_audio_hours_cap': None,
        'monthly_budget_usd': None,
        'failover_only': failover_only,
        'speaker_turns': 'discard',
    }


def _option(route):
    return {'route': route, 'quality_tier': 'accepted', 'quality_source': 'legacy_parity'}


TABLE = {
    'schema_version': 1,
    'table_version': 't1',
    'selection': 'cheapest',
    'gpu_floor_percent': 0.0,
    'routes': {
        'gpu': _route(0.07),
        'modulate': _route(0.043),
        'soniox': _route(0.10, failover_only=True),
    },
    'rows': [
        {'language_class': 'gpu_supported', 'options': [_option('gpu'), _option('modulate'), _option('soniox')]},
        {'language_class': '*', 'options': [_option('modulate'), _option('soniox')]},
    ],
}


class Health:
    def __init__(self, down=(), raises=False):
        self.down, self.raises, self.asked = set(down), raises, []

    def allows(self, service):
        self.asked.append(service)
        if self.raises:
            raise RuntimeError('boom')
        if service in self.down:
            return False, VendorHealthReason.BREAKER_OPEN
        return True, VendorHealthReason.HEALTHY


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in c.FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(rs, '_tables', rs._TableCache())
    monkeypatch.setattr(rs, '_health', c.AlwaysHealthy())


def _cohort(monkeypatch, table=TABLE, percent='100'):
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_PERCENT', percent)
    if table is not None:
        monkeypatch.setenv('BATCH_VENDOR_ROUTE_TABLE', table if isinstance(table, str) else json.dumps(table))


def _soniox_admitted(monkeypatch):
    real = c.provider_is_enabled
    monkeypatch.setattr(c, 'provider_is_enabled', lambda p, s: True if p == 'soniox' else real(p, s))


def _select(language, *, byok=False, uid=UID, batch_percent=100.0, eligible=True):
    return rs.select_route(language, byok=byok, uid=uid, batch_percent=batch_percent, vendor_eligible=eligible)


# --- dormant defaults: byte-identical to today ---------------------------------------------------


@pytest.mark.parametrize('language', LANGUAGES)
@pytest.mark.parametrize('byok', [False, True])
@pytest.mark.parametrize('eligible', [False, True])
def test_defaults_are_resolve_route_exactly(language, byok, eligible):
    decision = _select(language, byok=byok, eligible=eligible)
    assert decision.route == resolve_route(language, byok=byok)
    assert decision.reason is Reason.NOT_IN_COHORT
    assert decision.table_version == 'builtin'


@pytest.mark.parametrize('language', LANGUAGES)
def test_configured_table_outside_cohort_is_resolve_route(monkeypatch, language):
    _cohort(monkeypatch, percent='0')
    assert _select(language).route == resolve_route(language)


@pytest.mark.parametrize('language', LANGUAGES)
def test_cohort_without_table_serves_builtin(monkeypatch, language):
    _cohort(monkeypatch, table=None)
    decision = _select(language)
    assert decision.route == resolve_route(language)
    assert decision.reason is Reason.ORDERED


@pytest.mark.parametrize('language', LANGUAGES)
def test_kill_switch_returns_todays_routing(monkeypatch, language):
    _cohort(monkeypatch)
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_ENABLED', 'false')
    decision = _select(language)
    assert decision.route == resolve_route(language)
    assert decision.reason is Reason.KILL_SWITCH
    assert rs.current_table() == (c.BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN)


@pytest.mark.parametrize('value', ['true', 'TRUE', '', 'yes', '0'])
def test_kill_switch_only_false_disables(monkeypatch, value):
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_ENABLED', value)
    _cohort(monkeypatch)
    assert _select(SUPPORTED).reason is Reason.CHEAPEST


def test_legacy_on_owner_keeps_todays_routing(monkeypatch):
    _cohort(monkeypatch)
    decision = _select(SUPPORTED, eligible=False)
    assert decision.route == resolve_route(SUPPORTED)
    assert decision.reason is Reason.NOT_IN_COHORT


# --- cohort ----------------------------------------------------------------------------------------


def test_vendor_cohort_nests_in_batch_percent(monkeypatch):
    _cohort(monkeypatch, percent='100')
    assert _select(SUPPORTED, batch_percent=0.0).reason is Reason.NOT_IN_COHORT
    uids = [f'synthetic-owner-{i}' for i in range(400)]
    _cohort(monkeypatch, percent='30')
    routed = {uid for uid in uids if _select(SUPPORTED, uid=uid, batch_percent=50.0).reason is Reason.CHEAPEST}
    batch = {uid for uid in uids if cohort_bucket(uid, '') < 50.0}
    assert routed == {uid for uid in uids if cohort_bucket(uid, '') < 30.0}
    assert routed <= batch and 0 < len(routed) < len(batch)


def test_runtime_ramp_percent_wins_over_env(monkeypatch):
    _cohort(monkeypatch, percent='0')
    monkeypatch.setattr('config.batch_pipeline_vendor_routing.runtime_percent', lambda name, env_default: 100.0)
    assert _select(SUPPORTED).reason is Reason.CHEAPEST
    assert _select(SUPPORTED, batch_percent=0.0).reason is Reason.NOT_IN_COHORT  # still clamped


def test_allowlisted_owner_is_routed_at_zero_percent(monkeypatch):
    _cohort(monkeypatch, percent='0')
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_UID_ALLOWLIST', f' synthetic-owner-9, {UID} ,')
    assert _select(SUPPORTED).reason is Reason.CHEAPEST
    assert _select(SUPPORTED, uid='').reason is Reason.NOT_IN_COHORT
    assert _select(SUPPORTED, uid='synthetic-owner-2').reason is Reason.NOT_IN_COHORT
    assert _select(SUPPORTED, eligible=False).reason is Reason.NOT_IN_COHORT


def test_ramp_name_is_batch_nested():
    assert c.VENDOR_ROUTING_COHORT in ramp_store.RAMP_NAMES
    assert c.VENDOR_ROUTING_COHORT in ramp_store.BATCH_NESTED_RAMP_NAMES
    assert runtime_percent.clamp_nesting({'batch-pipeline': 5.0, c.VENDOR_ROUTING_COHORT: 25.0}) == {
        'batch-pipeline': 5.0,
        c.VENDOR_ROUTING_COHORT: 5.0,
    }
    env = {**ramp_store.empty_ramp_env(), 'percents': {'batch-pipeline': 5.0}}
    with pytest.raises(ramp_store.RampDocumentError, match='batch-vendor-routing exceeds'):
        ramp_store.apply_ramp_change(env, {'percents': {c.VENDOR_ROUTING_COHORT: 6.0}})
    after = ramp_store.apply_ramp_change(env, {'percents': {c.VENDOR_ROUTING_COHORT: 5.0}})
    assert after['percents'][c.VENDOR_ROUTING_COHORT] == 5.0
    with pytest.raises(ramp_store.RampDocumentError, match='batch-live-stt-retire exceeds'):
        ramp_store.apply_ramp_change(env, {'percents': {'batch-live-stt-retire': 6.0}})


# --- selection -------------------------------------------------------------------------------------


def test_cheapest_supported_language_takes_cheapest_vendor(monkeypatch):
    _cohort(monkeypatch)
    decision = _select(SUPPORTED)
    assert (decision.selected, decision.reason, decision.table_version) == ('modulate', Reason.CHEAPEST, 't1')
    assert decision.route.stt_route == 'provider'
    assert decision.route.provider_service == 'modulate'
    assert decision.route.provider_reason == 'none'
    assert decision.route.language == 'en'


def test_cheapest_picks_gpu_when_gpu_is_cheaper(monkeypatch):
    table = copy.deepcopy(TABLE)
    table['routes']['gpu']['price_usd_per_audio_hour'] = 0.02
    _cohort(monkeypatch, table)
    decision = _select(SUPPORTED)
    assert (decision.selected, decision.reason) == ('gpu', Reason.CHEAPEST)
    assert decision.route == resolve_route(SUPPORTED)


def test_price_tie_breaks_on_row_order(monkeypatch):
    table = copy.deepcopy(TABLE)
    table['routes']['gpu']['price_usd_per_audio_hour'] = 0.043
    _cohort(monkeypatch, table)
    assert _select(SUPPORTED).selected == 'gpu'


def test_unsupported_language_is_sole_capable_vendor(monkeypatch):
    _cohort(monkeypatch)
    decision = _select(UNSUPPORTED)
    assert (decision.selected, decision.reason) == ('modulate', Reason.SOLE_CAPABLE)
    assert decision.route == resolve_route(UNSUPPORTED)


def test_ordered_table_takes_first_healthy(monkeypatch):
    table = {**copy.deepcopy(TABLE), 'selection': 'ordered'}
    _cohort(monkeypatch, table)
    assert (_select(SUPPORTED).selected, _select(SUPPORTED).reason) == ('gpu', Reason.ORDERED)


def test_byok_reason_is_kept(monkeypatch):
    _cohort(monkeypatch)
    assert _select(SUPPORTED, byok=True).route.provider_reason == 'byok'
    assert _select(UNSUPPORTED, byok=True).route.provider_reason == 'byok'


def test_soniox_is_never_selected_while_policy_does_not_admit_it(monkeypatch):
    _cohort(monkeypatch)
    monkeypatch.setattr(rs, '_health', Health(down={'modulate'}))
    decision = _select(UNSUPPORTED)
    assert decision.selected == 'modulate' and decision.reason is Reason.NO_HEALTHY_ROUTE
    assert 'soniox' not in decision.failover


def test_soniox_is_failover_only(monkeypatch):
    _soniox_admitted(monkeypatch)
    table = copy.deepcopy(TABLE)
    table['routes']['soniox']['price_usd_per_audio_hour'] = 0.001  # cheapest, still never primary
    _cohort(monkeypatch, table)
    decision = _select(UNSUPPORTED)
    assert decision.selected == 'modulate' and decision.failover == ('soniox',)


# --- health ----------------------------------------------------------------------------------------


def test_unhealthy_vendor_falls_to_gpu_where_capable(monkeypatch):
    _cohort(monkeypatch)
    health = Health(down={'modulate'})
    monkeypatch.setattr(rs, '_health', health)
    decision = _select(SUPPORTED)
    assert (decision.selected, decision.reason) == ('gpu', Reason.CHEAPEST)
    assert 'gpu' not in health.asked  # GPU is never a health question


def test_unhealthy_vendor_fails_over_to_admitted_failover_capacity(monkeypatch):
    _soniox_admitted(monkeypatch)
    _cohort(monkeypatch)
    monkeypatch.setattr(rs, '_health', Health(down={'modulate'}))
    decision = _select(UNSUPPORTED)
    assert (decision.selected, decision.reason) == ('soniox', Reason.FAILOVER)
    assert decision.route.provider_service == 'soniox'
    assert decision.route.provider_reason == 'unsupported_language'


def test_all_vendors_down_still_routes_to_first_vendor(monkeypatch):
    _soniox_admitted(monkeypatch)
    _cohort(monkeypatch)
    monkeypatch.setattr(rs, '_health', Health(down={'modulate', 'soniox'}))
    decision = _select(UNSUPPORTED)
    assert (decision.selected, decision.reason) == ('modulate', Reason.NO_HEALTHY_ROUTE)
    assert decision.failover == ()
    assert decision.route.stt_route == 'provider'  # admitted; the stage holds it with its audio


def test_raising_health_is_unhealthy(monkeypatch):
    _cohort(monkeypatch)
    monkeypatch.setattr(rs, '_health', Health(raises=True))
    assert _select(SUPPORTED).selected == 'gpu'


def test_configure_health_binds(monkeypatch):
    _cohort(monkeypatch)
    rs.configure_health(Health(down={'modulate'}))
    assert _select(SUPPORTED).selected == 'gpu'


def test_failover_hint_lists_other_healthy_vendors(monkeypatch):
    _soniox_admitted(monkeypatch)
    _cohort(monkeypatch)
    assert _select(SUPPORTED).failover == ('soniox',)
    assert _select(UNSUPPORTED).failover == ('soniox',)


def test_failover_vendors_for_the_stage(monkeypatch):
    _soniox_admitted(monkeypatch)
    _cohort(monkeypatch)
    assert rs.failover_vendors(UNSUPPORTED) == ('modulate', 'soniox')
    assert rs.failover_vendors(UNSUPPORTED, {'modulate'}) == ('soniox',)
    monkeypatch.setattr(rs, '_health', Health(down={'soniox'}))
    assert rs.failover_vendors(UNSUPPORTED, {'modulate'}) == ()
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_ENABLED', 'false')
    monkeypatch.setattr(rs, '_health', c.AlwaysHealthy())
    assert rs.failover_vendors(UNSUPPORTED) == ('modulate',)  # builtin table: no Soniox row
    monkeypatch.setattr(rs, 'current_table', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    assert rs.failover_vendors(UNSUPPORTED) == ()


# --- GPU floor -------------------------------------------------------------------------------------


def test_gpu_floor_share_takes_gpu_regardless_of_price(monkeypatch):
    table = {**copy.deepcopy(TABLE), 'gpu_floor_percent': 100.0}
    _cohort(monkeypatch, table)
    decision = _select(SUPPORTED)
    assert (decision.selected, decision.reason) == ('gpu', Reason.GPU_FLOOR)
    assert decision.route == resolve_route(SUPPORTED)
    assert _select(UNSUPPORTED).selected == 'modulate'  # the floor never routes an unsafe language


def test_gpu_floor_holds_when_the_row_omits_gpu(monkeypatch):
    table = {**copy.deepcopy(TABLE), 'gpu_floor_percent': 100.0}
    table['rows'] = [{'language_class': '*', 'options': [_option('modulate')]}]
    _cohort(monkeypatch, table)
    decision = _select(SUPPORTED)
    assert (decision.selected, decision.reason) == ('gpu', Reason.GPU_FLOOR)
    assert decision.route == resolve_route(SUPPORTED)
    assert _select(UNSUPPORTED).selected == 'modulate'


def test_gpu_floor_is_a_stable_bucket_independent_of_the_ramp(monkeypatch):
    table = {**copy.deepcopy(TABLE), 'gpu_floor_percent': 20.0}
    _cohort(monkeypatch, table)
    uids = [f'synthetic-owner-{i}' for i in range(500)]
    floor = {uid for uid in uids if _select(SUPPORTED, uid=uid).reason is Reason.GPU_FLOOR}
    assert floor == {uid for uid in uids if cohort_bucket(uid, c.GPU_FLOOR_COHORT_SALT) < 20.0}
    assert 50 < len(floor) < 150
    low_ramp = {uid for uid in uids if cohort_bucket(uid, '') < 20.0}
    assert floor != low_ramp


# --- table ladder ----------------------------------------------------------------------------------


def test_malformed_table_serves_last_valid_then_builtin(monkeypatch):
    _cohort(monkeypatch)
    assert rs.current_table()[1] is VendorRouteTableOutcome.CONFIGURED
    _cohort(monkeypatch, '{"schema_version": 1')  # not JSON
    table, outcome = rs.current_table()
    assert outcome is VendorRouteTableOutcome.LAST_VALID and table.table_version == 't1'
    assert _select(SUPPORTED).selected == 'modulate'
    monkeypatch.setattr(rs, '_tables', rs._TableCache())  # a fresh process has no last valid
    assert rs.current_table() == (c.BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN)
    assert _select(SUPPORTED).route == resolve_route(SUPPORTED)


def test_invalid_schema_is_rejected_without_logging_content(monkeypatch, caplog):
    bad = {**copy.deepcopy(TABLE), 'routes': {**TABLE['routes'], 'soniox': _route(0.10)}}  # not failover-only
    _cohort(monkeypatch, bad)
    with caplog.at_level(logging.WARNING):
        assert rs.current_table() == (c.BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN)
    assert 'outcome=rejected served=builtin' in caplog.text
    assert '0.1' not in caplog.text and 'soniox' not in caplog.text


@pytest.mark.parametrize('payload', ['null', ' null ', '[]', '"t1"'])
def test_json_null_or_non_table_after_valid_serves_last_valid(monkeypatch, payload):
    _cohort(monkeypatch)
    rs.current_table()
    _cohort(monkeypatch, payload)
    table, outcome = rs.current_table()
    assert outcome is VendorRouteTableOutcome.LAST_VALID and table.table_version == 't1'


def test_unset_table_after_valid_serves_builtin(monkeypatch):
    _cohort(monkeypatch)
    rs.current_table()
    monkeypatch.delenv('BATCH_VENDOR_ROUTE_TABLE')
    assert rs.current_table() == (c.BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN)


def test_table_without_capable_route_serves_todays_routing(monkeypatch):
    real = c.provider_is_enabled
    monkeypatch.setattr(c, 'provider_is_enabled', lambda p, s: False if p == 'modulate' else real(p, s))
    _cohort(monkeypatch)
    decision = _select(UNSUPPORTED)
    assert decision.route == resolve_route(UNSUPPORTED) and decision.reason is Reason.ORDERED


def test_exact_language_row_wins(monkeypatch):
    table = copy.deepcopy(TABLE)
    table['rows'].insert(0, {'language_class': 'de', 'options': [_option('gpu')]})
    _cohort(monkeypatch, table)
    assert _select('de').selected == 'gpu'
    assert _select('en').selected == 'modulate'


def test_selection_error_serves_todays_routing(monkeypatch, caplog):
    _cohort(monkeypatch)
    monkeypatch.setattr(rs, 'current_table', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    with caplog.at_level(logging.ERROR):
        decision = _select(SUPPORTED)
    assert decision.route == resolve_route(SUPPORTED) and decision.reason is Reason.UNKNOWN
    assert 'exception_type=RuntimeError' in caplog.text


# --- shadow and metrics ----------------------------------------------------------------------------


def test_shadow_logs_decision_and_serves_builtin(monkeypatch, caplog):
    _cohort(monkeypatch, percent='0')
    monkeypatch.setenv('BATCH_VENDOR_ROUTING_SHADOW_PERCENT', '100')
    with caplog.at_level(logging.INFO):
        decision = _select(SUPPORTED)
    assert decision.route == resolve_route(SUPPORTED) and decision.reason is Reason.NOT_IN_COHORT
    assert 'event=batch_vendor_route_shadow route=modulate reason=cheapest served=gpu table=t1' in caplog.text
    assert UID not in caplog.text
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _select(SUPPORTED, eligible=False)
    assert 'batch_vendor_route_shadow' not in caplog.text


def _sample(collector, **labels):
    for metric in collector.collect():
        for sample in metric.samples:
            if sample.name.endswith('_total') and all(sample.labels.get(k) == v for k, v in labels.items()):
                return sample.value
    return 0.0


def test_decisions_and_table_loads_are_counted(monkeypatch):
    _cohort(monkeypatch)
    decisions = _sample(m.ROUTE_DECISIONS, route='modulate', reason='cheapest')
    loads = _sample(m.TABLE_LOADS, outcome='configured')
    _select(SUPPORTED)
    assert _sample(m.ROUTE_DECISIONS, route='modulate', reason='cheapest') == decisions + 1
    assert _sample(m.TABLE_LOADS, outcome='configured') == loads + 1
    not_in_cohort = _sample(m.ROUTE_DECISIONS, route='gpu', reason='not_in_cohort')
    _select(SUPPORTED, eligible=False)
    assert _sample(m.ROUTE_DECISIONS, route='gpu', reason='not_in_cohort') == not_in_cohort + 1


def test_documented_example_table_is_valid(monkeypatch):
    doc = (Path(__file__).resolve().parents[2] / 'docs' / 'batch-pipeline-serving.md').read_text(encoding='utf-8')
    section = doc.split('## All-vendor route selection (dormant)', 1)[1].split('\n## ', 1)[0]
    example = section.split('```json\n', 1)[1].split('```', 1)[0]
    table = c.RouteTable.from_dict(json.loads(example))
    assert all(
        'gpu' in {option.route for option in row.options} for row in table.rows if row.language_class == 'gpu_supported'
    )
    _cohort(monkeypatch, example)
    assert _select(SUPPORTED).selected in {'modulate', 'gpu'}
