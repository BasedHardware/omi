from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def report():
    """Load the script under test as a module, without leaking it into the process.

    The ``sys.modules`` registration is not optional: the script's dataclasses resolve their own
    module by name while executing, and ``exec_module`` fails without it. Doing it at import time
    would leave the entry behind for every later test in the run, which the repo's test-isolation
    rule bans (enforced by ``scripts/check_module_stub_pollution.py``), so it is scoped to the
    fixture and removed afterwards.
    """
    spec = importlib.util.spec_from_file_location(
        'chat_agent_cost_report', BACKEND_ROOT / 'scripts' / 'chat_agent_cost_report.py'
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        'date': '2026-07-30',
        'feature': 'chat_agent',
        'outcome': 'success',
        'cache_status': 'hit',
        'actual_model_version': 'claude-sonnet-5',
        'cached_input_tokens': 0,
        'uncached_input_tokens': 0,
        'cache_write_tokens': 0,
        'cache_write_ttl': None,
        'output_tokens': 0,
        'estimated_cost_micro_usd': 0,
    }
    row.update(overrides)
    return row


def test_attributes_spend_across_components_and_reports_write_read_ratio(report) -> None:
    """A cache-writing turn followed by cache-reading turns is split per component."""
    totals = report.build_totals(
        [
            # First turn of a session: writes the whole prefix at the 1h rate.
            _row(
                cache_write_tokens=20_000,
                cache_write_ttl='1h',
                uncached_input_tokens=500,
                output_tokens=400,
                cache_status='miss',
                estimated_cost_micro_usd=90_000,
            ),
            # Follow-up turns read that prefix back.
            _row(
                cached_input_tokens=20_000, uncached_input_tokens=200, output_tokens=300, estimated_cost_micro_usd=7_400
            ),
            _row(
                cached_input_tokens=20_000, uncached_input_tokens=200, output_tokens=300, estimated_cost_micro_usd=7_400
            ),
        ]
    )

    assert totals.attempts == 3
    assert totals.cached_input_tokens == 40_000
    assert totals.cache_write_1h_tokens == 20_000
    assert totals.attempts_with_cache_write == 1
    assert totals.attempts_with_cache_read == 2
    assert totals.cache_status['miss'] == 1
    assert totals.ledger_cost_micro_usd == 104_800

    # One prefix written per two reads.
    assert report.write_read_ratio(totals) == pytest.approx(0.5)

    rates = report.Rates(
        rate_card_id='test',
        input_micro_usd=2_000_000,
        cached_input_micro_usd=200_000,
        output_micro_usd=10_000_000,
        cache_write_micro_usd=2_500_000,
        cache_write_1h_micro_usd=4_000_000,
    )
    by_name = {component.name: component for component in report.cost_components(totals, rates)}
    assert by_name['cached input (read)'].cost_micro_usd == 8_000  # 40k @ 0.2 $/M
    assert by_name['uncached input'].cost_micro_usd == 1_800  # 900 @ 2 $/M
    assert by_name['cache write 1h'].cost_micro_usd == 80_000  # 20k @ 4 $/M
    assert by_name['output'].cost_micro_usd == 10_000  # 1k @ 10 $/M

    rendered = report.render(totals, rates, 'chat_agent')
    assert 'cache write 1h' in rendered
    assert 'write:read ratio: 0.50' in rendered


def test_untagged_cache_writes_are_reported_and_priced_at_the_one_hour_rate(report) -> None:
    """A 'mixed' TTL means the request's breakpoints disagree — surface it, don't drop it."""
    totals = report.build_totals([_row(cache_write_tokens=1_000, cache_write_ttl='mixed')])

    assert totals.cache_write_untagged_tokens == 1_000
    assert totals.cache_write_1h_tokens == 0

    rates = report.Rates(
        rate_card_id='test',
        input_micro_usd=2_000_000,
        cached_input_micro_usd=200_000,
        output_micro_usd=10_000_000,
        cache_write_micro_usd=2_500_000,
        cache_write_1h_micro_usd=4_000_000,
    )
    by_name = {component.name: component for component in report.cost_components(totals, rates)}
    assert by_name['cache write 1h'].tokens == 1_000
    assert "had no single TTL" in report.render(totals, rates, 'chat_agent')


def test_luna_30_minute_cache_writes_use_the_luna_write_rate(report) -> None:
    """The managed Luna route reports explicit 30-minute writes, not Anthropic TTLs."""
    totals = report.build_totals(
        [
            _row(
                actual_model_version='gpt-5.6-luna',
                cache_write_tokens=1_000_000,
                cache_write_ttl='30m',
                estimated_cost_micro_usd=250_000,
            )
        ]
    )

    assert totals.cache_write_30m_tokens == 1_000_000
    assert totals.cache_write_5m_tokens == 0
    assert totals.cache_write_1h_tokens == 0
    assert totals.cache_write_untagged_tokens == 0

    card_path = BACKEND_ROOT / 'llm_gateway' / 'config' / 'cost_rate_cards.yaml'
    rates = report.load_rates('gpt-5.6-luna', card_path)
    by_name = {component.name: component for component in report.cost_components(totals, rates)}

    assert rates.cache_write_micro_usd == 250_000
    assert by_name['cache write 30m'].cost_micro_usd == 250_000
    assert by_name['cache write 1h'].cost_micro_usd == 0
    assert 'cache write 30m' in report.render(totals, rates, 'chat_agent')


def test_malformed_ledger_row_contributes_its_readable_fields(report) -> None:
    """Best-effort ledger writes can omit or corrupt a field; the report must not abort."""
    totals = report.build_totals(
        [_row(cached_input_tokens='not-a-number', uncached_input_tokens=-5, output_tokens=True, cache_write_tokens=700)]
    )

    assert totals.attempts == 1
    assert totals.cached_input_tokens == 0
    assert totals.uncached_input_tokens == 0
    assert totals.output_tokens == 0  # bool is not a token count
    assert totals.cache_write_untagged_tokens == 700


def test_no_attempts_reports_an_empty_range_instead_of_dividing_by_zero(report) -> None:
    totals = report.build_totals([])
    rates = report.Rates('test', 0, 0, 0, 0, 0)

    assert report.write_read_ratio(totals) is None
    assert 'No chat_agent attempts found' in report.render(totals, rates, 'chat_agent')


def test_no_attempts_report_keeps_uid_scope(report) -> None:
    totals = report.build_totals([])
    rates = report.Rates('test', 0, 0, 0, 0, 0)

    rendered = report.render(totals, rates, 'chat_agent', uid='u-1')

    assert rendered.splitlines() == [
        'scope: uid=u-1',
        'No chat_agent attempts found. Check the date range and that accounting is enabled.',
    ]


def test_rates_come_from_the_real_card_and_an_unknown_model_fails_loudly(report) -> None:
    """Pricing the report against a model with no card would silently understate spend."""
    card_path = BACKEND_ROOT / 'llm_gateway' / 'config' / 'cost_rate_cards.yaml'
    rates = report.load_rates('claude-sonnet-5', card_path)

    assert rates.cached_input_micro_usd < rates.input_micro_usd < rates.cache_write_1h_micro_usd

    with pytest.raises(LookupError):
        report.load_rates('claude-not-a-real-model', card_path)


def test_model_resolves_from_the_route_override_not_the_pre_override_profile(report) -> None:
    """model_config records the pre-override choice; the override is what actually bills.

    Asserted against the override file rather than a literal: `chat_agent` has already moved
    provider once (anthropic -> openai), and pinning the served model here would fail the next
    routing change without anything being wrong with the resolver.
    """
    overrides = yaml.safe_load(
        (BACKEND_ROOT / 'llm_gateway' / 'config' / 'generated_route_overrides.yaml').read_text(encoding='utf-8')
    )
    served = next(r['primary']['model'] for r in overrides['generated_route_overrides'] if r['feature'] == 'chat_agent')

    assert report.resolve_model(None, 'chat_agent') == served
    assert report.resolve_model('claude-haiku-4-5', 'chat_agent') == 'claude-haiku-4-5'

    with pytest.raises(LookupError):
        report.resolve_model(None, 'not-a-feature')


def test_a_range_spanning_a_routing_change_is_priced_per_model(report) -> None:
    """chat_agent has already moved provider once. Folding both models into one set of totals
    would price every pre-switch attempt at the current model's card."""
    grouped = report.build_totals_by_pricing_basis(
        [
            _row(actual_model_version='claude-sonnet-5', output_tokens=1_000, date='2026-08-01'),
            _row(actual_model_version='gpt-5.6-luna', output_tokens=400, date='2026-08-03'),
            _row(actual_model_version='gpt-5.6-luna', output_tokens=600, date='2026-08-04'),
        ]
    )

    assert {model for model, _card in grouped} == {'claude-sonnet-5', 'gpt-5.6-luna'}
    assert grouped[('claude-sonnet-5', '')].attempts == 1
    assert grouped[('gpt-5.6-luna', '')].attempts == 2
    assert grouped[('gpt-5.6-luna', '')].output_tokens == 1_000

    # Each group is priceable on its own card, which is the point of splitting them.
    card_path = BACKEND_ROOT / 'llm_gateway' / 'config' / 'cost_rate_cards.yaml'
    for model, _card in grouped:
        assert report.load_rates(model, card_path).output_micro_usd > 0


def test_one_model_priced_two_ways_is_split_by_the_card_it_was_billed_on(report) -> None:
    """A model name does not identify its rates: an intro price can expire while the name stays
    the same, so attempts either side of that must not be folded together."""
    grouped = report.build_totals_by_pricing_basis(
        [
            _row(rate_card_id='anthropic.claude-sonnet-5.intro.2026-07-17', output_tokens=100),
            _row(rate_card_id='anthropic.claude-sonnet-5.standard.2026-09-01', output_tokens=250),
        ]
    )

    assert len(grouped) == 2
    assert grouped[('claude-sonnet-5', 'anthropic.claude-sonnet-5.intro.2026-07-17')].output_tokens == 100
    assert grouped[('claude-sonnet-5', 'anthropic.claude-sonnet-5.standard.2026-09-01')].output_tokens == 250


def test_rates_load_from_the_recorded_card_id_ahead_of_the_model_name(report) -> None:
    """The ledger records which card priced each attempt; that beats guessing from the name."""
    card_path = BACKEND_ROOT / 'llm_gateway' / 'config' / 'cost_rate_cards.yaml'

    by_id = report.load_rates('ignored-name', card_path, rate_card_id='anthropic.claude-sonnet-5.intro.2026-07-17')
    assert by_id.rate_card_id == 'anthropic.claude-sonnet-5.intro.2026-07-17'

    # An id that no longer exists in the card file must fail loudly rather than fall back to the
    # model name and silently price the range at today's rates.
    with pytest.raises(LookupError):
        report.load_rates('claude-sonnet-5', card_path, rate_card_id='anthropic.claude-sonnet-5.retired')


def test_a_row_with_no_model_is_grouped_rather_than_dropped(report) -> None:
    """A best-effort ledger write can omit the model; its tokens still cost money."""
    grouped = report.build_totals_by_pricing_basis([_row(actual_model_version=None, output_tokens=50)])

    assert grouped[('unknown', '')].output_tokens == 50


def test_the_default_window_ends_on_the_utc_day(report, monkeypatch) -> None:
    """The ledger's date field is UTC. A local today() east or west of UTC asks for a day the
    range was never meant to cover."""
    captured: dict[str, Any] = {}

    def fake_fetch(_client, feature, days, **_kwargs):
        captured['days'] = days
        return []

    monkeypatch.setattr(report, 'fetch_rows', fake_fetch)
    report.main(['--days', '1'], get_client=lambda: object())

    from datetime import datetime, timezone

    assert captured['days'] == [datetime.now(timezone.utc).date().isoformat()]


def test_date_range_is_inclusive_and_ordered(report) -> None:
    from datetime import date

    assert report.date_range(date(2026, 7, 30), 3) == ['2026-07-28', '2026-07-29', '2026-07-30']

    with pytest.raises(ValueError):
        report.date_range(date(2026, 7, 30), 0)


class _Snapshot:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return self._data


class _RecordingQuery:
    def __init__(self, snapshots: list[Any] | None = None) -> None:
        self.filters: list[Any] = []
        self._snapshots = snapshots or []

    def where(self, *, filter: Any) -> _RecordingQuery:
        self.filters.append(filter)
        return self

    def stream(self):
        return iter(self._snapshots)


class _FakeClient:
    def __init__(self, query: _RecordingQuery) -> None:
        self.query = query

    def collection(self, _name: str) -> _RecordingQuery:
        return self.query


def _filter_triples(filters: list[Any]) -> list[tuple[Any, Any, Any]]:
    return [(item.field_path, item.op_string, item.value) for item in filters]


def test_fetch_rows_with_uid_adds_a_user_uid_equality_filter(report) -> None:
    query = _RecordingQuery(snapshots=[_Snapshot({'feature': 'chat_agent', 'date': '2026-07-30'})])
    rows = list(report.fetch_rows(_FakeClient(query), 'chat_agent', ['2026-07-30'], uid='u-1'))

    assert _filter_triples(query.filters) == [
        ('feature', '==', 'chat_agent'),
        ('date', '==', '2026-07-30'),
        ('user_uid', '==', 'u-1'),
    ]
    assert len(rows) == 1


def test_fetch_rows_without_uid_adds_no_user_uid_filter(report) -> None:
    query = _RecordingQuery(snapshots=[_Snapshot({'feature': 'chat_agent', 'date': '2026-07-30'})])
    list(report.fetch_rows(_FakeClient(query), 'chat_agent', ['2026-07-30']))

    assert _filter_triples(query.filters) == [
        ('feature', '==', 'chat_agent'),
        ('date', '==', '2026-07-30'),
    ]
    assert all(item.field_path != 'user_uid' for item in query.filters)


def test_parse_args_accepts_an_optional_uid(report) -> None:
    assert report.parse_args(['--uid', 'u-1']).uid == 'u-1'
    assert report.parse_args([]).uid is None


def test_render_includes_a_uid_scope_line_only_when_set(report) -> None:
    totals = report.build_totals([_row(output_tokens=1)])
    rates = report.Rates('test', 0, 0, 0, 0, 0)
    without = report.render(totals, rates, 'chat_agent')
    with_none = report.render(totals, rates, 'chat_agent', uid=None)
    with_uid = report.render(totals, rates, 'chat_agent', uid='u-1')

    assert without == with_none
    without_lines = without.split('\n')
    with_uid_lines = with_uid.split('\n')
    assert with_uid_lines[0] == without_lines[0]
    assert with_uid_lines[1] == 'scope: uid=u-1'
    assert with_uid_lines[2:] == without_lines[1:]


def test_main_passes_uid_to_fetch_rows(report, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_fetch(_client, feature, days, *, uid=None):
        captured['uid'] = uid
        return []

    monkeypatch.setattr(report, 'fetch_rows', fake_fetch)
    report.main(['--uid', 'u-1', '--days', '1'], get_client=lambda: object())

    assert captured['uid'] == 'u-1'
