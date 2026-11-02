"""The checked-in prod route table: GPU-first, Modulate overflow, Soniox failover only (lead 7cb3fb).

Runs the real parser and the real selection over the file the lead sets as BATCH_VENDOR_ROUTE_TABLE,
under each vendor-health case the runbook names. Hermetic: health is injected, no network.
"""

import json
from pathlib import Path

import pytest

from utils.batch_pipeline import route_selection as rs
from utils.batch_pipeline import vendor_route_contracts as c
from utils.batch_pipeline.provider_stt import resolve_route
from utils.observability.reasons import VendorHealthReason, VendorRouteReason as Reason

TABLE_PATH = Path(__file__).resolve().parents[2] / 'deploy' / 'batch-pipeline' / 'vendor_route_table.prod.json'
SUPPORTED = 'en'  # deployed Parakeet serves it
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


def _soniox_admitted(monkeypatch, admitted=True):
    real = c.provider_is_enabled
    monkeypatch.setattr(c, 'provider_is_enabled', lambda p, s: admitted if p == 'soniox' else real(p, s))


def _decide(table, language, *, down=(), saturated=False):
    rs.configure_health(Health(down=down))
    return rs.decide(table, language, byok=False, uid=UID, gpu_saturated=lambda: saturated)


def test_the_file_is_one_valid_table_with_a_bounded_version(table):
    assert table.selection == 'ordered'
    assert table.gpu_floor_percent == 0.0  # ordered GPU-first already keeps every Parakeet unit on the floor
    assert table.routes['soniox'].failover_only and not table.routes['modulate'].failover_only
    assert table.table_version.startswith('prod-')


@pytest.mark.parametrize('language', LANGUAGES)
def test_healthy_and_unsaturated_it_routes_exactly_as_today(table, language):
    # Serving the table changes nothing until the ring saturates or a vendor fails: blank, 'multi' and
    # unknown languages keep today's route too, so arming it is not a silent move to Modulate.
    decision = _decide(table, language)
    assert decision.route == resolve_route(language, byok=False)


def test_parakeet_languages_stay_on_gpu_until_the_ring_is_saturated(table):
    decision = _decide(table, SUPPORTED)
    assert (decision.selected, decision.reason) == ('gpu', Reason.ORDERED)
    assert decision.route.stt_route == 'parakeet'


def test_a_saturated_ring_overflows_fresh_parakeet_units_to_modulate(table):
    decision = _decide(table, SUPPORTED, saturated=True)
    assert (decision.selected, decision.reason) == ('modulate', Reason.GPU_OVERFLOW)


def test_overflow_never_starts_on_soniox_and_waits_on_the_ring_when_modulate_is_down(table, monkeypatch):
    _soniox_admitted(monkeypatch)
    decision = _decide(table, SUPPORTED, down={'modulate'}, saturated=True)
    assert (decision.selected, decision.reason) == ('gpu', Reason.ORDERED)


def test_languages_parakeet_cannot_serve_start_on_modulate(table):
    decision = _decide(table, UNSUPPORTED)
    assert decision.selected == 'modulate'
    assert decision.route.stt_route == 'provider'
    assert decision.reason in {Reason.SOLE_CAPABLE, Reason.ORDERED}


def test_modulate_down_fails_unsupported_languages_over_to_soniox(table, monkeypatch):
    _soniox_admitted(monkeypatch)
    decision = _decide(table, UNSUPPORTED, down={'modulate'})
    assert (decision.selected, decision.reason) == ('soniox', Reason.FAILOVER)


def test_all_vendors_down_starts_on_modulate_so_the_stage_holds_the_audio(table, monkeypatch):
    _soniox_admitted(monkeypatch)
    decision = _decide(table, UNSUPPORTED, down={'modulate', 'soniox'})
    assert (decision.selected, decision.reason) == ('modulate', Reason.NO_HEALTHY_ROUTE)


def test_without_soniox_admission_a_modulate_outage_holds_instead_of_failing_over(table, monkeypatch):
    _soniox_admitted(monkeypatch, admitted=False)
    decision = _decide(table, UNSUPPORTED, down={'modulate'})
    assert (decision.selected, decision.reason) == ('modulate', Reason.NO_HEALTHY_ROUTE)


def test_vendor_spend_is_capped_per_day(table):
    # Soniox is failover-only at $0.10/h list. Its cap covers a mean full Modulate outage day of
    # unsupported-language STT (~900 audio-h/day, 7-day legacy meter) and bounds that day near $100;
    # past the cap units hold with their audio and redrive when Modulate returns.
    assert 900 <= table.routes['soniox'].daily_audio_hours_cap <= 1200
    # Modulate's cap is a durable daily budget about 2x the expected 100% batch load (unsupported-language
    # STT ~900 audio-h/day moved from legacy, plus peak overflow), never low enough to bind in normal days.
    assert 2000 <= table.routes['modulate'].daily_audio_hours_cap <= 4000


def test_served_through_the_env_value_the_runbook_sets(monkeypatch, table):
    # The runbook sets the compact JSON of this file; the ladder must serve it as CONFIGURED.
    monkeypatch.setenv('BATCH_VENDOR_ROUTE_TABLE', json.dumps(json.loads(TABLE_PATH.read_text())))
    served, outcome = rs.current_table()
    assert served == table
    assert outcome.value == 'configured'
