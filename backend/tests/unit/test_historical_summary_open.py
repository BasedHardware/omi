"""POST /v1/conversations/{id}/summary/open and the guards around historical-tier rows."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import routers.conversations as conv_router
from config import historical_tier
from config.episodes import HOME_STEP_PROJECTION_ENV as home_step_env
from models.structured import Structured
from utils.conversations import historical_summary as hs
from utils.conversations import home_step, summary_delivery
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.v3 import summary as v3_summary

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def _row(**updates):
    row = {
        'id': 'c1',
        'status': 'completed',
        'processing_tier': 'historical',
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW,
        'language': 'en',
        'structured': {'title': 'We talked about the garden', 'overview': ''},
        'transcript_segments': [{'text': 'We talked about the garden', 'start': 0.0, 'end': 1.0}],
    }
    row.update(updates)
    return row


class Gates:
    """Every gate open; each test closes one."""

    def __init__(self, monkeypatch, row):
        self.row = row
        self.reserved: list[tuple[str, str]] = []
        self.released: list[tuple[str, str]] = []
        self.limits: dict[str, bool] = {}
        self.finished: list[str] = []
        self.processed = SimpleNamespace(id='c1', structured=Structured(title='T', overview='A real summary'))
        self.process = MagicMock(side_effect=lambda *a, **k: self.processed)
        self.rate_limited: set[str] = set()
        monkeypatch.delenv(historical_tier.OPEN_ENABLED_ENV, raising=False)
        monkeypatch.delenv(historical_tier.GLOBAL_DAILY_LIMIT_ENV, raising=False)
        monkeypatch.setattr(hs.conversations_db, 'get_conversation', lambda *a, **k: self.row)
        monkeypatch.setattr(hs.conversations_db, 'is_soft_deleted', lambda row: bool(row.get('deleted')))
        monkeypatch.setattr(hs, 'check_rate_limit_inline', self._rate)
        monkeypatch.setattr(hs.redis_db, 'reserve_rate_limit', self._reserve)
        monkeypatch.setattr(hs.redis_db, 'release_rate_limit', lambda key, policy: self.released.append((key, policy)))
        monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: False)
        monkeypatch.setattr(hs.byok, 'has_validated_byok_keys', lambda: False)
        self.compute = MagicMock()
        monkeypatch.setattr(hs, 'require_generated_compute', self.compute)
        self.claim = MagicMock(return_value=({'conversation_id': 'c1'}, True))
        monkeypatch.setattr(hs.attention_db, 'claim', self.claim)
        monkeypatch.setattr(hs.attention_db, 'owns_live_claim', lambda *a: True)
        monkeypatch.setattr(hs.attention_db, 'finish', lambda uid, op, state: self.finished.append(state))
        monkeypatch.setattr(hs, 'process_conversation', self.process)
        monkeypatch.setattr(hs, 'deserialize_conversation', lambda row: SimpleNamespace(language='en', id='c1'))
        self.submitted = MagicMock()
        monkeypatch.setattr(hs, 'submit_with_context', self.submitted)

    def _rate(self, key, policy):
        if policy in self.rate_limited:
            raise HTTPException(status_code=429, detail='Rate limit exceeded', headers={'Retry-After': '60'})

    def _reserve(self, key, policy, limit, window):
        if self.limits.get(policy) is None:
            self.reserved.append((key, policy))
            return True, limit - 1, window
        if isinstance(self.limits[policy], Exception):
            raise self.limits[policy]
        return False, 0, 1234


def _refusal():
    with pytest.raises(HTTPException) as caught:
        hs.open_summary('u1', 'c1')
    return caught.value


def test_generates_once_summary_only_and_indexes_the_summary(monkeypatch):
    gates = Gates(monkeypatch, _row())
    body, outcome = hs.open_summary('u1', 'c1')
    assert outcome == 'generated' and body is gates.processed
    kwargs = gates.process.call_args.kwargs
    assert kwargs == {'trigger': ProcessingTrigger.HISTORICAL_OPEN, 'first_party_only': True}
    assert gates.finished == ['succeeded']
    gates.compute.assert_called_once_with('u1', 'historical_summary_open')
    assert gates.submitted.call_args.args[1:] == (hs.save_structured_vector, 'u1', gates.processed)
    assert ('global', hs.GLOBAL_POLICY) in gates.reserved and ('u1:c1', hs.ATTEMPTS_POLICY) in gates.reserved


def test_vector_sub_flag_off_skips_the_index(monkeypatch):
    gates = Gates(monkeypatch, _row())
    monkeypatch.setenv(historical_tier.VECTOR_ENABLED_ENV, 'false')
    hs.open_summary('u1', 'c1')
    gates.submitted.assert_not_called()


def test_an_existing_summary_answers_without_a_model_or_any_gate(monkeypatch):
    gates = Gates(monkeypatch, _row(structured={'title': 'T', 'overview': 'Already summarized'}))
    monkeypatch.setenv(historical_tier.OPEN_ENABLED_ENV, 'false')
    gates.rate_limited = {hs.HOURLY_POLICY}
    body, outcome = hs.open_summary('u1', 'c1')
    assert outcome == 'existing' and body['structured']['overview'] == 'Already summarized'
    gates.process.assert_not_called()
    assert not gates.reserved and not gates.finished


@pytest.mark.parametrize(
    ('updates', 'status', 'code'),
    [
        ({'deleted': True}, 404, 'not_found'),
        ({'recording': True}, 404, 'not_found'),
        ({'is_locked': True}, 409, 'conversation_locked'),
        ({'discarded': True}, 409, 'conversation_discarded'),
        ({'processing_tier': None}, 409, 'not_historical'),
    ],
)
def test_row_refusals_precede_every_gate(monkeypatch, updates, status, code):
    gates = Gates(monkeypatch, _row(**updates))
    error = _refusal()
    assert error.status_code == status and error.detail['code'] == code
    gates.process.assert_not_called()
    assert not gates.reserved


def test_missing_row_is_404(monkeypatch):
    gates = Gates(monkeypatch, None)
    assert _refusal().status_code == 404
    gates.process.assert_not_called()


def test_kill_switch_off_is_503_and_stops_advertising(monkeypatch):
    gates = Gates(monkeypatch, _row())
    assert hs.summary_on_open(gates.row)
    monkeypatch.setenv(historical_tier.OPEN_ENABLED_ENV, 'false')
    error = _refusal()
    assert error.status_code == 503 and error.detail['code'] == 'historical_summary_disabled'
    assert not hs.summary_on_open(gates.row)
    gates.process.assert_not_called()


@pytest.mark.parametrize('policy', [hs.HOURLY_POLICY, hs.DAILY_POLICY])
def test_per_user_hourly_and_daily_caps_answer_429(monkeypatch, policy):
    gates = Gates(monkeypatch, _row())
    gates.rate_limited = {policy}
    error = _refusal()
    assert error.status_code == 429 and error.headers['Retry-After'] == '60'
    gates.process.assert_not_called()


def test_global_daily_cap_answers_429_with_retry_after(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.limits[hs.GLOBAL_POLICY] = False
    error = _refusal()
    assert error.status_code == 429 and error.detail['code'] == 'historical_summary_global_limit'
    assert error.headers['Retry-After'] == '1234'
    gates.process.assert_not_called()


def test_global_cap_fails_open_when_redis_is_down(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.limits[hs.GLOBAL_POLICY] = ConnectionError('redis down')
    gates.limits[hs.ATTEMPTS_POLICY] = ConnectionError('redis down')
    _, outcome = hs.open_summary('u1', 'c1')
    assert outcome == 'generated'


def test_global_cap_zero_disables_the_counter(monkeypatch):
    gates = Gates(monkeypatch, _row())
    monkeypatch.setenv(historical_tier.GLOBAL_DAILY_LIMIT_ENV, '0')
    hs.open_summary('u1', 'c1')
    assert ('global', hs.GLOBAL_POLICY) not in gates.reserved


def test_budget_denial_is_402_and_releases_the_global_slot(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.compute.side_effect = HTTPException(status_code=402, detail={'error': 'usage_budget_exhausted'})
    assert _refusal().status_code == 402
    assert gates.released == [('global', hs.GLOBAL_POLICY)]
    gates.process.assert_not_called()


def test_byok_account_without_request_keys_is_409(monkeypatch):
    gates = Gates(monkeypatch, _row())
    monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: True)
    error = _refusal()
    assert error.status_code == 409 and error.detail['code'] == 'byok_keys_required'
    gates.process.assert_not_called()


def test_byok_account_with_validated_keys_proceeds(monkeypatch):
    gates = Gates(monkeypatch, _row())
    monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: True)
    monkeypatch.setattr(hs.byok, 'has_validated_byok_keys', lambda: True)
    assert hs.open_summary('u1', 'c1')[1] == 'generated'


def test_row_attempts_per_day_are_capped(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.limits[hs.ATTEMPTS_POLICY] = False
    error = _refusal()
    assert error.status_code == 429 and error.detail['code'] == 'historical_summary_attempts_exhausted'
    assert ('global', hs.GLOBAL_POLICY) in gates.released
    gates.process.assert_not_called()


@pytest.mark.parametrize('owned', [False, 'stale'])
def test_concurrent_writer_is_409_and_returns_the_slots(monkeypatch, owned):
    gates = Gates(monkeypatch, _row())
    if owned == 'stale':
        monkeypatch.setattr(hs.attention_db, 'owns_live_claim', lambda *a: False)
    else:
        gates.claim.return_value = ({'conversation_id': 'c1'}, False)
    error = _refusal()
    assert error.status_code == 409 and error.detail['code'] == 'conversation_processing_in_progress'
    assert set(gates.released) == {('global', hs.GLOBAL_POLICY), ('u1:c1', hs.ATTEMPTS_POLICY)}
    gates.process.assert_not_called()


def test_empty_output_is_502(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.processed = SimpleNamespace(id='c1', structured=Structured(title='T'))
    error = _refusal()
    assert error.status_code == 502 and error.detail['code'] == 'summary_unavailable'
    assert gates.finished == ['failed']
    gates.submitted.assert_not_called()


def test_transient_failure_is_a_typed_retryable_503(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.process.side_effect = TimeoutError('provider timeout')
    error = _refusal()
    assert error.status_code == 503 and error.detail['code'] == 'historical_summary_retry'
    assert error.headers['Retry-After'] == str(hs.TRANSIENT_RETRY_AFTER_SECONDS)
    assert gates.finished == ['failed']


def test_route_sets_the_outcome_header(monkeypatch):
    monkeypatch.setattr(conv_router.historical_summary, 'open_summary', lambda uid, cid: ({'id': cid}, 'existing'))
    response = SimpleNamespace(headers={})
    assert conv_router.open_historical_summary('c1', response=response, uid='u1') == {'id': 'c1'}
    assert response.headers['X-Omi-Summary-Outcome'] == 'existing'


def test_projection_advertises_only_open_unsummarized_historical_rows(monkeypatch):
    monkeypatch.delenv(historical_tier.OPEN_ENABLED_ENV, raising=False)
    assert hs.project(_row())['summary_on_open'] is True
    for updates in (
        {'processing_tier': None},
        {'structured': {'title': 'T', 'overview': 'done'}},
        {'is_locked': True},
        {'discarded': True},
    ):
        assert 'summary_on_open' not in hs.project(_row(**updates))


def test_reprocess_of_a_historical_row_is_summary_only(monkeypatch):
    processed = SimpleNamespace(
        id='c1', discarded=False, processing_tier='historical', structured=Structured(title='T', overview='Notes')
    )
    monkeypatch.setattr(conv_router, 'process_conversation', lambda *a, **k: processed)
    learning = MagicMock(side_effect=AssertionError('no speaker learning for a historical row'))
    monkeypatch.setattr(conv_router, 'schedule_reprocessed_learning', learning)
    submitted = MagicMock()
    monkeypatch.setattr(hs, 'submit_with_context', submitted)
    result = conv_router.execute_reprocess('u1', 'c1', SimpleNamespace(), 'en', None, None, False, None, None)
    assert result is processed
    assert submitted.call_args.args[1:] == (hs.save_structured_vector, 'u1', processed)


def test_summary_stream_never_generates_for_a_historical_row():
    row = _row(transcript_segments=[{'text': 'word ' * 400}])
    assert not v3_summary.summary_eligible(row)
    assert v3_summary.summary_eligible({**row, 'processing_tier': None})


def test_historical_minimum_is_a_ready_home_row_with_no_summary_debt(monkeypatch):
    monkeypatch.delenv(home_step_env, raising=False)
    conversation = SimpleNamespace(transcript_segments=[SimpleNamespace(text='We planned the garden beds today.')])
    structured = build_deterministic_minimum_structured(conversation, uid='u1', provenance=False).model_dump()
    write = {
        **_row(structured=structured),
        'terminal_no_derived_effects': True,
        'summary_blocked_reason': 'historical_on_open',
    }
    summary_delivery.prepare(write, 'u1', now=NOW.timestamp())
    assert 'summary_due_at' not in write and write['summary_output_present'] is False
    assert summary_delivery.refusal(write) == 'local_only'
    assert home_step.classify(write) == 'ready'


def test_an_empty_open_time_run_never_arms_automatic_summary_debt():
    # The notes pipeline can return its provenance-stamped minimum for a short or empty
    # transcript; the historical row must still owe nothing the age gate will park.
    write = {
        **_row(structured={'title': 'Recording', 'title_provenance': 'server_minimum', 'overview': ''}),
        'terminal_no_derived_effects': True,
    }
    summary_delivery.prepare(write, 'u1', now=NOW.timestamp())
    assert write['summary_due_at'] is None
    assert summary_delivery.refusal(write) == 'local_only'
