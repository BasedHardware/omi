from config.translation import (
    resolve_ondemand_config,
    resolve_translation_profile,
    viewed_translation_profile,
    TranslationProvider,
)
from utils.translation_demand import DemandPolicy, TranslationDemand


def test_defaults_ship_on_demand_on_with_kill_switches_to_legacy():
    # Owner decision 2026-09-29: default ON at merge; flags are kill switches.
    config = resolve_ondemand_config({})
    assert config.gate_enabled and config.onopen_enabled and config.gemini_enabled
    assert config.lease_v1_enabled and not config.shadow_enabled
    assert config.admits('any-uid') and config.spend_configured
    assert config.cohort_percent == 100
    assert config.uid_daily_chars > 0 and config.global_daily_chars > 0
    assert resolve_translation_profile({}).policy_version == 'legacy'
    assert viewed_translation_profile(resolve_translation_profile({}), config).providers == (
        TranslationProvider.gemini,
    )


def test_kill_switches_restore_exact_legacy_defaults():
    config = resolve_ondemand_config(
        {
            'TRANSLATION_DEMAND_GATE_ENABLED': 'false',
            'TRANSLATION_DEMAND_LEASE_V1_ENABLED': 'false',
            'TRANSLATION_ONDEMAND_GEMINI_ENABLED': 'false',
            'TRANSLATION_ONOPEN_ENABLED': 'false',
            'TRANSLATION_ONDEMAND_COHORT_PERCENT': '0',
        }
    )
    assert not config.gate_enabled and not config.onopen_enabled and not config.gemini_enabled
    assert not config.admits('any-uid')


def test_unversioned_state_stales_to_legacy_and_renewal_does_not_change_generation():
    now = [0.0]
    demand = TranslationDemand(lambda: now[0])
    assert demand.snapshot(lease_v1_enabled=True).policy == DemandPolicy.legacy_unknown
    report = {'foreground': True, 'transcript_visible': True}
    assert demand.observe(report, lease_v1_enabled=True)
    generation = demand.snapshot(lease_v1_enabled=True).generation
    now[0] = 20
    assert demand.observe(report, lease_v1_enabled=True)
    assert demand.snapshot(lease_v1_enabled=True).generation == generation
    now[0] = 80
    assert demand.snapshot(lease_v1_enabled=True).policy == DemandPolicy.legacy_stale


def test_lease_expiry_malformed_reports_and_lifetime_beyond_telemetry_cap():
    now = [0.0]
    demand = TranslationDemand(lambda: now[0])
    report = {'foreground': True, 'transcript_visible': False, 'translation_demand_version': 1}
    assert demand.observe(report, lease_v1_enabled=True)
    assert demand.snapshot(lease_v1_enabled=True).policy == DemandPolicy.hidden
    assert not demand.observe({**report, 'transcript_visible': 0}, lease_v1_enabled=True)
    assert not demand.observe({'foreground': True, 'transcript_visible': True}, lease_v1_enabled=True)
    for index in range(2100):
        now[0] += 1
        assert demand.observe(report, lease_v1_enabled=True)
    now[0] += 61
    assert demand.snapshot(lease_v1_enabled=True).policy == DemandPolicy.lease_expired
    demand.close()
    assert demand.snapshot(lease_v1_enabled=True).policy == DemandPolicy.closed


def test_unsupported_capability_does_not_silently_enter_unversioned_rollout():
    demand = TranslationDemand(lambda: 0)
    assert not demand.observe(
        {'foreground': True, 'transcript_visible': True, 'translation_demand_version': 2}, lease_v1_enabled=True
    )
    assert demand.snapshot(lease_v1_enabled=True).policy == DemandPolicy.legacy_unknown
