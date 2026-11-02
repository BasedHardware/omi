"""Real per-attempt prices, the 1M continuation, and allowlist-only Dream visibility."""

from datetime import date, datetime, timezone
from fractions import Fraction
from types import SimpleNamespace

import pytest

from config.dream_agent import Caps, admission_for, dream_journal_key
from database import dream_store, review_changes, review_store
from llm_gateway.gateway.accounting import rate_card_for
from tests.unit.test_dream_harness_runtime import UID, runtime, store
from utils.dream_cost import (
    cached_input_price_ratio,
    estimate_tokens,
    price_attempt,
    price_weighted_tokens,
    unpriced_card,
    verification_reserve_tokens,
)
from utils.dream_harness_transport import attempt_room, turn_from_usage
from utils.llm.shaped_agent import Budget, Mount

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
OWNER = 'vi7SA9ckQCe4ccobWNxlbdcNdC23'


def test_heavy_pass_continues_after_about_45k_tokens():
    mount = Mount(budget=Budget(tokens=1000000, turns=64))
    messages = [{'role': 'user', 'content': 'stable seed'}, {'role': 'assistant', 'content': 'noted'}]
    estimate, completion = attempt_room(
        messages,
        mount,
        prior_prompt_tokens=45000,
        prior_message_count=1,
        completion_limit=4096,
    )
    assert completion >= 128
    assert estimate < 50000
    assert estimate + completion < 60000


def test_byte_heuristic_rounds_up_at_three_and_a_half_bytes_per_token():
    assert estimate_tokens(0) == 0
    assert estimate_tokens(1) == 1
    assert estimate_tokens(7) == 2


def test_cached_input_uses_the_cached_rate_and_3_8_is_priced():
    listed = date(2026, 10, 18)
    full, status = price_attempt(
        'gemini', 'gemini-2.5-flash', prompt_tokens=1000, cached_tokens=0, completion_tokens=100, at=listed
    )
    cached, cached_status = price_attempt(
        'gemini', 'gemini-2.5-flash', prompt_tokens=1000, cached_tokens=400, completion_tokens=100, at=listed
    )
    assert status == cached_status == 'priced'
    # 1000 * $0.30 + 100 * $2.50, and 600 * $0.30 + 400 * $0.03 + 100 * $2.50.
    assert full == 550
    assert cached == 442
    assert cached < full
    micro, flash_status = price_attempt(
        'gemini',
        'gemini-3.8-flash',
        prompt_tokens=1000,
        cached_tokens=400,
        completion_tokens=100,
        cache_storage_token_seconds=3600,
        at=listed,
    )
    # 600 * $0.75 + 400 * $0.075 + 100 * $3.75, plus 1 token-hour of storage.
    assert flash_status == 'priced' and micro == 856
    intro = rate_card_for('gemini', 'gemini-3.8-flash', at=listed)
    assert intro is not None and intro.rate_card_id == 'vertex.gemini-3.8-flash.intro.2026-10-15'
    assert intro.cache_storage_micro_usd_per_million_token_hours == 1000000
    assert intro.cache_write_micro_usd_per_million == intro.input_micro_usd_per_million
    assert unpriced_card('gemini', 'gemini-3.8-flash') is None
    lite = rate_card_for('gemini', 'gemini-3.1-flash-lite', at=listed)
    assert lite is not None
    assert lite.input_micro_usd_per_million == 250000
    assert lite.audio_input_micro_usd_per_million == 500000
    assert lite.cache_storage_micro_usd_per_million_token_hours == 1000000


def test_price_weighted_meter_uses_the_active_rate_card_and_unknown_cache_is_full_price():
    ratio = cached_input_price_ratio('gemini', 'gemini-3.8-flash', 1000)
    assert ratio == Fraction(1, 10)
    assert (
        price_weighted_tokens(
            'gemini',
            'gemini-3.8-flash',
            prompt_tokens=1000,
            cached_tokens=800,
            completion_tokens=100,
        )
        == 380
    )
    assert (
        price_weighted_tokens(
            'gemini',
            'gemini-3.8-flash',
            prompt_tokens=1000,
            cached_tokens=None,
            completion_tokens=100,
            cache_reported=False,
        )
        == 1100
    )
    assert (
        price_weighted_tokens(
            'gemini',
            'gemini-3.8-flash',
            prompt_tokens=1000,
            cached_tokens=800,
            completion_tokens=100,
            cache_reported=False,
        )
        == 1100
    )


def test_transport_counts_unreported_cache_at_full_price():
    turn, unknown = turn_from_usage(
        {
            'prompt_tokens': 1000,
            'completion_tokens': 100,
            'cached_tokens': 800,
            'cache_unreported_tokens': 200,
            'cache_usage_complete': False,
            'unknown_attempts': 0,
        },
        2000,
    )
    assert unknown == 0
    assert turn.tokens == turn.price_weighted_tokens == 1100


def test_gemini_3_8_price_switches_on_2027_01_01():
    before, before_status = price_attempt(
        'gemini',
        'gemini-3.8-flash',
        prompt_tokens=1_000_000,
        cached_tokens=0,
        completion_tokens=0,
        at=date(2026, 12, 31),
    )
    after, after_status = price_attempt(
        'gemini',
        'gemini-3.8-flash',
        prompt_tokens=1_000_000,
        cached_tokens=0,
        completion_tokens=0,
        at=date(2027, 1, 1),
    )
    assert before_status == after_status == 'priced'
    assert before == 750000
    assert after == 1500000
    intro = rate_card_for('gemini', 'gemini-3.8-flash', at=date(2026, 12, 31))
    standard = rate_card_for('gemini', 'gemini-3.8-flash', at=date(2027, 1, 1))
    assert intro is not None and intro.rate_card_id.endswith('intro.2026-10-15')
    assert standard is not None and standard.rate_card_id.endswith('2027-01-01')


def test_verification_reserve_is_zero_until_evidence_exists_and_floors_each_call():
    assert verification_reserve_tokens([], completion_tokens=256) == 0

    class Staged:
        refs = ()
        records = {}

        def payload(self):
            return {'operation': {'kind': 'rename', 'reason': 'because', 'why_it_matters': 'matters'}}

    assert verification_reserve_tokens([Staged()], completion_tokens=256) == 2048


def test_allowlist_on_demand_is_owner_scoped(monkeypatch):
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', OWNER)
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    assert admission_for(OWNER) == ('on_demand', True)
    assert admission_for('other-owner') == ('reserved', False)
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'false')
    assert admission_for(OWNER) == ('reserved', False)


def test_allowlist_gates_schedule_and_manual(runtime, store, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    assert dream_store.acquire(UID, Caps(tokens=96000), now=NOW) is not None
    runtime.rows[('users', 'other-owner')] = {}
    assert dream_store.acquire('other-owner', Caps(tokens=96000), now=NOW) is None
    with pytest.raises(dream_store.AdmissionDenied, match='dream_budget_unavailable'):
        dream_store.acquire('other-owner', Caps(tokens=96000), now=NOW, trigger='manual')


class _Doc:
    exists = False

    def get(self):
        return self

    def to_dict(self):
        return {}

    def collection(self, name):
        return self

    def document(self, name):
        return self


@pytest.fixture(scope='module')
def review_api():
    import database.task_intelligence_control  # noqa: F401
    import utils.task_intelligence.chat_first_eligibility  # noqa: F401

    from utils import review

    return review


def test_review_hides_dream_journal_and_proposals_from_ineligible_owners(monkeypatch, review_api):
    from models.dream_edit import Edit
    from models.review import AgentProposalItem, ReviewItemV2

    review = review_api

    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'allowlist')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', OWNER)
    item = ReviewItemV2(
        item_id='agent_proposal:toy',
        kind='agent_proposal',
        title='Close toy task?',
        created_at=NOW,
        agent_proposal=AgentProposalItem(
            edit=Edit(kind='close_task', target='action_items/toy', reason='Done', evidence=['conversations/toy'])
        ),
    )
    monkeypatch.setattr(review.store, 'user', lambda uid: _Doc())
    monkeypatch.setattr(
        review.store,
        'list_proposals',
        lambda uid: [{'item': item.model_dump(), 'source': {'edit_key': 'agent:close:toy'}, 'evidence_version': '1'}],
    )
    monkeypatch.setattr(review.store, 'remaining_today', lambda uid: 3)
    monkeypatch.setattr(review.store, 'offer_item', lambda *args: True)
    monkeypatch.setattr(review.speakers, 'get_prompts', lambda uid: SimpleNamespace(prompts=[]))
    monkeypatch.setattr(
        'database.task_intelligence_control.get_task_workflow_control',
        lambda uid: SimpleNamespace(workflow_mode='off', account_generation=0),
    )
    monkeypatch.setattr(
        'utils.task_intelligence.chat_first_eligibility.resolve_task_intelligence_for_user',
        lambda **kwargs: SimpleNamespace(intelligence_product_enabled=False),
    )
    hidden = review.get_items('other-owner', include_agent_proposals=True)
    assert hidden.items == []
    shown = review.get_items(OWNER, include_agent_proposals=True)
    assert [row.kind for row in shown.items] == ['agent_proposal']

    created = NOW
    rows = [
        {
            'phase': 'applied',
            'edit_key': 'agent:close:toy',
            'change': {'change_id': 'dream-change', 'kind': 'other', 'title': 'Dream', 'created_at': created},
        },
        {
            'phase': 'applied',
            'edit_key': 'user:transcript:toy',
            'change': {'change_id': 'user-change', 'kind': 'other', 'title': 'User', 'created_at': created},
        },
    ]

    class Query:
        def order_by(self, *args, **kwargs):
            return self

        def limit(self, count):
            return self

        def stream(self):
            return [SimpleNamespace(to_dict=lambda row=row: row) for row in rows]

    monkeypatch.setattr(
        review_changes.review_queries, 'CHANGES', SimpleNamespace(build=lambda *args, **kwargs: Query())
    )
    monkeypatch.setattr(review_store, 'user', lambda uid: _Doc())
    monkeypatch.setattr(review_store, 'require_doc', lambda uid, data: data)
    page = review_changes.list_changes('other-owner', now=NOW)
    assert [change.change_id for change in page.changes] == ['user-change']
    assert dream_journal_key('agent:close:toy') and dream_journal_key('dream:close:toy')
    assert not dream_journal_key('user:transcript:toy')
