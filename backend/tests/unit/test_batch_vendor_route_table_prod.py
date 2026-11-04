"""The checked-in prod route table en-overflow-1104 (lead2 863cd6, David 49b7e4: English-only overflow).

GPU first everywhere Parakeet serves; fresh English overflows to Modulate past the GPU SLO; other
GPU-capable languages stay on GPU; languages Parakeet cannot serve start on Modulate. Modulate carries a
runaway-only daily cap (3000 audio-h) and its $0.06 list price; no Soniox (not admitted on prerecorded
today, so route_capable never selects it). Runs the real parser and the real
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
    assert table.table_version == 'en-overflow-1104'
    assert table.selection == 'ordered'
    assert table.gpu_floor_percent == 0.0
    assert set(table.routes) == {'gpu', 'modulate'}  # Soniox is not admitted on prerecorded today
    assert [option.route for option in table.row_for('en').options] == ['gpu', 'modulate']
    assert [option.route for option in table.row_for(OTHER_SUPPORTED).options] == ['gpu']


def test_modulate_spend_is_bounded_per_day_and_priced_at_list(table):
    # lead2 2026-11-04 (Luna P1 on #24637): a runaway-only bound. gpu_unsupported needs ~900
    # audio-h/day, so 3000 leaves ~2100 audio-h/day of overflow before anything holds (~$180/day
    # worst case). A trip holds units with their audio; it never drops them. $ is table-driven at
    # the $0.06/audio-h list rate; the $50/day overflow-spend alert is the episode bound.
    modulate = table.routes['modulate']
    assert modulate.daily_audio_hours_cap == 3000.0
    assert modulate.price_usd_per_audio_hour == 0.06
    assert modulate.monthly_budget_usd is None
    assert table.routes['gpu'].daily_audio_hours_cap is None


@pytest.mark.parametrize('language', LANGUAGES)
def test_healthy_and_unsaturated_it_routes_exactly_as_today(table, language):
    # Serving the table changes nothing until the ring saturates: blank, 'multi' and unknown
    # languages keep today's route too, so arming it is not a silent move to Modulate.
    decision = _decide(table, language)
    assert decision.route == resolve_route(language, byok=False)


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


def test_overflow_waits_on_the_ring_when_modulate_is_down(table):
    decision = _decide(table, SUPPORTED, down={'modulate'}, saturated=True)
    assert (decision.selected, decision.reason) == ('gpu', Reason.ORDERED)


@pytest.mark.parametrize('language', [UNSUPPORTED, 'ca', 'gl', 'eu', 'cy', 'af', 'sq', 'bs', 'sw'])
def test_languages_parakeet_cannot_serve_start_on_modulate(table, language):
    assert table.row_for(language).language_class == c.GPU_UNSUPPORTED_CLASS
    decision = _decide(table, language)
    assert decision.selected == 'modulate'
    assert decision.route.stt_route == 'provider'
    assert decision.reason in {Reason.SOLE_CAPABLE, Reason.ORDERED}


def test_modulate_down_holds_unsupported_languages_on_modulate(table):
    # No second vendor in the table: the stage holds the audio until Modulate returns.
    decision = _decide(table, UNSUPPORTED, down={'modulate'})
    assert (decision.selected, decision.reason) == ('modulate', Reason.NO_HEALTHY_ROUTE)


def test_served_through_the_env_value(monkeypatch, table):
    monkeypatch.setenv('BATCH_VENDOR_ROUTE_TABLE', json.dumps(json.loads(TABLE_PATH.read_text())))
    served, outcome = rs.current_table()
    assert served == table
    assert outcome.value == 'configured'


@pytest.mark.parametrize('service', SYNC_SERVICES)
def test_the_runtime_overlay_serves_this_file_on_every_sync_service(service):
    # Durable: the backend train re-applies the overlay, so a deploy never drops the table.
    overlay = yaml.safe_load(OVERLAY_PATH.read_text())
    env = overlay['overlay']['cloud_run']['services'][service]['env']
    served = json.loads(env['BATCH_VENDOR_ROUTE_TABLE']['value'])
    assert served == json.loads(TABLE_PATH.read_text())
