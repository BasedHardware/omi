"""The checked-in prod route table soniox-unsupported-1127 (David 2026-11-27, from en-overflow-1116).

GPU first everywhere Parakeet serves; fresh English overflows to Modulate past the GPU SLO; other
GPU-capable languages stay on GPU. Languages Parakeet cannot serve start on Soniox, with Modulate as
failover (David 2026-11-27, after a public eval where Soniox beat Velma on every language but English).
Modulate keeps its daily cap (5000 audio-h, David 2026-11-16) and $0.06 list price. Soniox has no daily
cap: a paging alert on its daily audio hours replaces it, so growth never holds units on a cap. Runs the real parser and the real
selection over the file the runtime overlay serves as BATCH_VENDOR_ROUTE_TABLE. Hermetic.
"""

import json
from pathlib import Path

import pytest
import yaml

from utils.batch_pipeline import route_selection as rs
from utils.batch_pipeline import vendor_route_contracts as c
from utils.batch_pipeline.provider_stt_admission import resolve_route
from utils.observability.reasons import VendorHealthReason, VendorRouteReason as Reason

BACKEND = Path(__file__).resolve().parents[2]
TABLE_PATH = BACKEND / 'deploy' / 'batch-pipeline' / 'vendor_route_table.prod.json'
OVERLAY_PATH = BACKEND / 'deploy' / 'runtime_env' / 'prod.overlay.yaml'
INTEGRATION_TABLE_PATH = TABLE_PATH.with_name('vendor_route_table.en-overflow-1116.json')
SYNC_SERVICES = ('backend-sync', 'backend-sync-backfill', 'backend-integration')
SUPPORTED = 'en'  # deployed Parakeet serves it, and it is the one overflow language
OTHER_SUPPORTED = 'de'  # Parakeet serves it; English-only overflow keeps it on GPU
UNSUPPORTED = 'ja'  # deployed Parakeet cannot; Modulate can
LANGUAGES = ('en', 'de', 'ja', 'zh-TW', 'yue', 'xx', 'multi', 'und', '', None, 'pt-BR', 'EN', 'ar')
UID = 'synthetic-owner-1'


class Health:
    def __init__(self, down=()):
        self.down = set(down)

    def allows(self, service):
        if service in self.down:
            return False, VendorHealthReason.BREAKER_OPEN
        return True, VendorHealthReason.HEALTHY


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in c.FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(rs, '_tables', rs._TableCache())
    monkeypatch.setattr(rs, '_health', c.AlwaysHealthy())


@pytest.fixture
def table():
    return c.RouteTable.from_dict(json.loads(TABLE_PATH.read_text()))


def _decide(table, language, *, down=(), saturated=False):
    rs.configure_health(Health(down=down))
    return rs.decide(table, language, byok=False, uid=UID, gpu_saturated=lambda: saturated)


def test_the_file_is_the_standing_english_overflow_table(table):
    assert table.table_version == 'soniox-unsupported-1127'
    assert table.selection == 'ordered'
    assert table.gpu_floor_percent == 0.0
    assert not table.routes['soniox'].failover_only and not table.routes['modulate'].failover_only
    assert [option.route for option in table.row_for('en').options] == ['gpu', 'modulate', 'soniox']
    assert [option.route for option in table.row_for(OTHER_SUPPORTED).options] == ['gpu']
    assert [option.route for option in table.row_for(UNSUPPORTED).options] == ['soniox', 'modulate']


def test_modulate_spend_is_bounded_per_day_and_priced_at_list(table):
    # lead2 2026-11-04 (Luna P1 on #24637): a runaway-only bound. gpu_unsupported needs ~900
    # audio-h/day; David 2026-11-16 raised 3000 -> 5000 when RECENT English joined overflow during
    # the L4 stockout, leaving ~4000 audio-h/day of overflow before anything holds (~$300/day
    # worst case). A trip holds units with their audio; it never drops them. $ is table-driven at
    # the $0.06/audio-h list rate; the $50/day overflow-spend alert is the episode bound.
    modulate = table.routes['modulate']
    assert modulate.daily_audio_hours_cap == 5000.0
    assert modulate.price_usd_per_audio_hour == 0.06
    assert modulate.monthly_budget_usd is None
    assert table.routes['gpu'].daily_audio_hours_cap is None
    # Soniox starts unsupported-language units with no cap (David 2026-11-27): a paging alert on its daily
    # audio hours (omi-batch-soniox-daily-hours) is the bound, so user growth never holds units on a cap.
    soniox = table.routes['soniox']
    assert soniox.daily_audio_hours_cap is None and soniox.monthly_budget_usd is None
    assert soniox.price_usd_per_audio_hour == 0.12


@pytest.mark.parametrize('language', LANGUAGES)
def test_healthy_and_unsaturated_only_unsupported_languages_move(table, language):
    # Blank, 'multi', unknown and GPU languages keep today's route until the ring saturates. Only languages
    # Parakeet cannot serve change: the same provider route, served by Soniox instead of Modulate.
    decision = _decide(table, language)
    today = resolve_route(language, byok=False)
    if table.row_for(language).language_class == c.GPU_UNSUPPORTED_CLASS:
        assert (decision.selected, decision.route.stt_route) == ('soniox', 'provider')
        assert (today.stt_route, today.provider_service) == ('provider', 'modulate')
    else:
        assert decision.route == today


def test_english_stays_on_gpu_until_the_ring_is_saturated(table):
    decision = _decide(table, SUPPORTED)
    assert (decision.selected, decision.reason) == ('gpu', Reason.ORDERED)
    assert decision.route.stt_route == 'parakeet'


def test_a_saturated_ring_overflows_fresh_english_to_modulate(table):
    decision = _decide(table, SUPPORTED, saturated=True)
    assert (decision.selected, decision.reason) == ('modulate', Reason.GPU_OVERFLOW)
    assert decision.route.stt_route == 'provider'


@pytest.mark.parametrize('language', [OTHER_SUPPORTED, 'pt-BR', 'multi'])
def test_a_saturated_ring_keeps_other_gpu_languages_on_gpu(table, language):
    decision = _decide(table, language, saturated=True)
    assert decision.selected == 'gpu'
    assert decision.route == resolve_route(language, byok=False)


def test_overflow_takes_soniox_when_modulate_is_down(table):
    # Soniox is now a primary in the English row too, so a saturated ring with Modulate down keeps fresh
    # English moving on Soniox instead of waiting (needs both outages at once; the Soniox alert bounds it).
    decision = _decide(table, SUPPORTED, down={'modulate'}, saturated=True)
    assert (decision.selected, decision.reason) == ('soniox', Reason.GPU_OVERFLOW)


@pytest.mark.parametrize('language', [UNSUPPORTED, 'ca', 'gl', 'eu', 'cy', 'af', 'sq', 'bs', 'sw'])
def test_languages_parakeet_cannot_serve_start_on_soniox(table, language):
    assert table.row_for(language).language_class == c.GPU_UNSUPPORTED_CLASS
    decision = _decide(table, language)
    assert decision.selected == 'soniox' and decision.failover == ('modulate',)
    assert decision.route.stt_route == 'provider'
    assert decision.reason in {Reason.SOLE_CAPABLE, Reason.ORDERED}


def _soniox_admitted(monkeypatch, admitted=True):
    real = c.provider_is_enabled
    monkeypatch.setattr(c, 'provider_is_enabled', lambda p, s: admitted if p == 'soniox' else real(p, s))


def test_soniox_down_starts_unsupported_languages_on_modulate(table, monkeypatch):
    _soniox_admitted(monkeypatch)
    decision = _decide(table, UNSUPPORTED, down={'soniox'})
    assert (decision.selected, decision.reason) == ('modulate', Reason.ORDERED)


def test_overflow_prefers_modulate_over_soniox(table, monkeypatch):
    _soniox_admitted(monkeypatch)
    decision = _decide(table, SUPPORTED, saturated=True)
    assert (decision.selected, decision.reason) == ('modulate', Reason.GPU_OVERFLOW)
    assert decision.failover == ('soniox',)


def test_all_vendors_down_starts_on_soniox_so_the_stage_holds_the_audio(table, monkeypatch):
    _soniox_admitted(monkeypatch)
    decision = _decide(table, UNSUPPORTED, down={'modulate', 'soniox'})
    assert (decision.selected, decision.reason) == ('soniox', Reason.NO_HEALTHY_ROUTE)


def test_served_through_the_env_value(monkeypatch, table):
    monkeypatch.setenv('BATCH_VENDOR_ROUTE_TABLE', json.dumps(json.loads(TABLE_PATH.read_text())))
    served, outcome = rs.current_table()
    assert served == table
    assert outcome.value == 'configured'


@pytest.mark.parametrize('service', SYNC_SERVICES)
def test_the_runtime_overlay_pins_the_expected_table_on_each_sync_service(service):
    # Durable: the backend train re-applies the overlay, so a deploy never drops the table.
    overlay = yaml.safe_load(OVERLAY_PATH.read_text())
    env = overlay['overlay']['cloud_run']['services'][service]['env']
    served = json.loads(env['BATCH_VENDOR_ROUTE_TABLE']['value'])
    expected = INTEGRATION_TABLE_PATH if service == 'backend-integration' else TABLE_PATH
    assert served == json.loads(expected.read_text())
