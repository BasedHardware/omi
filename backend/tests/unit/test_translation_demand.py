from config.translation import (
    resolve_ondemand_config,
    resolve_translation_profile,
    viewed_translation_profile,
    TranslationProvider,
)
from utils.translation_demand import DemandPolicy, TranslationDemand


def test_defaults_ship_on_demand_on_with_stop_switches():
    config = resolve_ondemand_config({})
    assert config.gate_enabled and config.onopen_enabled and config.spend_configured
    assert config.uid_daily_chars > 0 and config.global_daily_chars > 0
    assert resolve_translation_profile({}).policy_version == 'legacy'
    viewed = viewed_translation_profile(resolve_translation_profile({}), config)
    assert viewed.providers == (TranslationProvider.gemini,)
    assert viewed.policy_version == 'viewed_v1'


def test_live_and_onopen_stop_switches():
    config = resolve_ondemand_config(
        {
            'TRANSLATION_DEMAND_GATE_ENABLED': 'false',
            'TRANSLATION_ONOPEN_ENABLED': 'false',
        }
    )
    assert not config.gate_enabled and not config.onopen_enabled


def test_unversioned_state_stales_to_legacy_and_renewal_does_not_change_generation():
    now = [0.0]
    demand = TranslationDemand(lambda: now[0])
    assert demand.snapshot().policy == DemandPolicy.legacy_unknown
    report = {'foreground': True, 'transcript_visible': True}
    assert demand.observe(report)
    generation = demand.snapshot().generation
    now[0] = 20
    assert demand.observe(report)
    assert demand.snapshot().generation == generation
    now[0] = 80
    assert demand.snapshot().policy == DemandPolicy.legacy_stale


def test_lease_expiry_malformed_reports_and_lifetime_beyond_telemetry_cap():
    now = [0.0]
    demand = TranslationDemand(lambda: now[0])
    report = {'foreground': True, 'transcript_visible': False, 'translation_demand_version': 1}
    assert demand.observe(report)
    assert demand.snapshot().policy == DemandPolicy.hidden
    assert not demand.observe({**report, 'transcript_visible': 0})
    assert not demand.observe({'foreground': True, 'transcript_visible': True})
    for index in range(2100):
        now[0] += 1
        assert demand.observe(report)
    now[0] += 61
    assert demand.snapshot().policy == DemandPolicy.lease_expired
    demand.close()
    assert demand.snapshot().policy == DemandPolicy.closed


def test_unsupported_capability_does_not_silently_enter_unversioned_rollout():
    demand = TranslationDemand(lambda: 0)
    assert not demand.observe({'foreground': True, 'transcript_visible': True, 'translation_demand_version': 2})
    assert demand.snapshot().policy == DemandPolicy.legacy_unknown
