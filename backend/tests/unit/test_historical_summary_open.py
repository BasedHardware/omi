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
from utils import byok as byok_module
from utils.conversations import historical_projection
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
        self.process = MagicMock(side_effect=self._process)
        self.reread: dict | None = None
        self.rate_limited: set[str] = set()
        monkeypatch.delenv(historical_tier.OPEN_ENABLED_ENV, raising=False)
        monkeypatch.delenv(historical_tier.GLOBAL_DAILY_LIMIT_ENV, raising=False)
        self.reads = 0
        monkeypatch.setattr(hs.conversations_db, 'get_conversation', self._read)
        monkeypatch.setattr(hs.conversations_db, 'is_soft_deleted', lambda row: bool(row.get('deleted')))
        monkeypatch.setattr(hs.redis_db, 'reserve_rate_limit', self._reserve)
        monkeypatch.setattr(hs.redis_db, 'release_rate_limit', lambda key, policy: self.released.append((key, policy)))
        monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: False)
        monkeypatch.setattr(byok_module, 'has_validated_byok_keys', lambda: False)
        self.byok_keys: dict[str, str] = {}
        monkeypatch.setattr(byok_module, 'get_byok_uid', lambda: 'u1')
        monkeypatch.setattr(byok_module, 'get_byok_key', lambda provider: self.byok_keys.get(provider))
        self.persisted = True
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

    def _read(self, *args, **kwargs):
        self.reads += 1
        return self.reread if self.reads > 1 and self.reread is not None else self.row

    def _process(self, *args, **kwargs):
        observer = kwargs.get('persistence_observer')
        if observer is not None:
            observer(self.persisted)
        return self.processed

    def _reserve(self, key, policy, limit, window):
        if policy in self.rate_limited:
            return False, 0, 60
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
    assert kwargs['trigger'] is ProcessingTrigger.HISTORICAL_OPEN and kwargs['first_party_only'] is True
    assert callable(kwargs['persistence_observer'])
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
    assert historical_projection.summary_on_open(gates.row)
    monkeypatch.setenv(historical_tier.OPEN_ENABLED_ENV, 'false')
    error = _refusal()
    assert error.status_code == 503 and error.detail['code'] == 'historical_summary_disabled'
    assert not historical_projection.summary_on_open(gates.row)
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


def test_budget_denial_is_402_and_spends_no_slot(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.compute.side_effect = HTTPException(status_code=402, detail={'error': 'usage_budget_exhausted'})
    assert _refusal().status_code == 402
    assert gates.reserved == [] and gates.released == []
    gates.process.assert_not_called()


def test_byok_account_without_request_keys_is_409(monkeypatch):
    gates = Gates(monkeypatch, _row())
    monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: True)
    error = _refusal()
    assert error.status_code == 409 and error.detail['code'] == 'byok_keys_required'
    gates.process.assert_not_called()


def test_byok_account_with_a_validated_llm_key_proceeds(monkeypatch):
    gates = Gates(monkeypatch, _row())
    monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: True)
    monkeypatch.setattr(byok_module, 'has_validated_byok_keys', lambda: True)
    gates.byok_keys = {'openai': 'sk-validated'}
    assert hs.open_summary('u1', 'c1')[1] == 'generated'


def test_byok_account_with_only_a_transcription_key_is_409(monkeypatch):
    # A validated Deepgram-only header set funds no summary: the run would fall back to Omi's LLM keys.
    gates = Gates(monkeypatch, _row())
    monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: True)
    monkeypatch.setattr(byok_module, 'has_validated_byok_keys', lambda: True)
    gates.byok_keys = {'deepgram': 'dg-validated'}
    error = _refusal()
    assert error.status_code == 409 and error.detail['code'] == 'byok_keys_required'
    assert gates.reserved == []
    gates.process.assert_not_called()


@pytest.mark.parametrize('refusal', ['byok', 'budget', 'attempts', 'busy'])
def test_refusals_never_spend_the_owners_hourly_or_daily_slots(monkeypatch, refusal):
    gates = Gates(monkeypatch, _row())
    if refusal == 'byok':
        monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: True)
    elif refusal == 'budget':
        gates.compute.side_effect = HTTPException(status_code=402, detail={'error': 'usage_budget_exhausted'})
    elif refusal == 'attempts':
        gates.limits[hs.ATTEMPTS_POLICY] = False
    else:
        gates.claim.return_value = ({'conversation_id': 'c1'}, False)
    _refusal()
    spent = [slot for slot in gates.reserved if slot[1] in (hs.HOURLY_POLICY, hs.DAILY_POLICY)]
    assert all(slot in gates.released for slot in spent)


def test_an_admission_store_error_releases_its_slots_and_is_a_typed_503(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.claim.side_effect = RuntimeError('firestore unavailable')
    error = _refusal()
    assert error.status_code == 503 and error.detail['code'] == 'historical_summary_retry'
    assert gates.reserved and set(gates.reserved) == set(gates.released)
    gates.process.assert_not_called()


def test_a_summary_landed_by_a_racing_open_is_returned_not_regenerated(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.reread = _row(structured={'title': 'T', 'overview': 'Written by the other request'})
    body, outcome = hs.open_summary('u1', 'c1')
    assert outcome == 'existing' and body['structured']['overview'] == 'Written by the other request'
    gates.process.assert_not_called()
    assert gates.finished == ['succeeded'] and set(gates.reserved) == set(gates.released)


def test_a_fenced_persist_is_a_retryable_503_with_no_vector(monkeypatch):
    gates = Gates(monkeypatch, _row())
    gates.persisted = False
    error = _refusal()
    assert error.status_code == 503 and error.detail['code'] == 'historical_summary_retry'
    assert gates.finished == ['failed']
    gates.submitted.assert_not_called()


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
    assert set(gates.released) == set(gates.reserved) and ('u1:c1', hs.ATTEMPTS_POLICY) in gates.released
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
    monkeypatch.setattr(hs, 'open_summary', lambda uid, cid: ({'id': cid}, 'existing'))
    response = SimpleNamespace(headers={})
    assert conv_router.open_historical_summary('c1', response=response, uid='u1') == {'id': 'c1'}
    assert response.headers['X-Omi-Summary-Outcome'] == 'existing'


def test_projection_advertises_only_open_unsummarized_historical_rows(monkeypatch):
    monkeypatch.delenv(historical_tier.OPEN_ENABLED_ENV, raising=False)
    assert historical_projection.project(_row())['summary_on_open'] is True
    for updates in (
        {'processing_tier': None},
        {'structured': {'title': 'T', 'overview': 'done'}},
        {'is_locked': True},
        {'discarded': True},
    ):
        assert 'summary_on_open' not in historical_projection.project(_row(**updates))


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
    structured = build_deterministic_minimum_structured(conversation, uid='u1', historical=True).model_dump()
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


def _reprocess(monkeypatch, gates):
    from database import processing_attention

    monkeypatch.setattr(conv_router, '_get_valid_conversation_by_id', lambda uid, cid: dict(gates.row))
    monkeypatch.setattr(conv_router.conversations_db, 'is_soft_deleted', lambda row: False)
    monkeypatch.setattr(conv_router.transcribing_hold, 'retry_pending', lambda row: False)
    monkeypatch.setattr(conv_router, 'deserialize_conversation', lambda row: SimpleNamespace(language='en', id='c1'))
    monkeypatch.setattr(processing_attention, 'claim', gates.claim)
    monkeypatch.setattr(processing_attention, 'owns_live_claim', lambda *a: True)
    monkeypatch.setattr(processing_attention, 'finish', lambda uid, op, state: gates.finished.append(state))
    executed = MagicMock(return_value=gates.processed)
    monkeypatch.setattr(conv_router, 'execute_reprocess', executed)
    return executed


def _reprocess_refusal():
    with pytest.raises(HTTPException) as caught:
        conv_router.reprocess_conversation('c1', uid='u1')
    return caught.value


def test_reprocess_of_a_historical_row_takes_the_open_admission(monkeypatch):
    gates = Gates(monkeypatch, _row())
    executed = _reprocess(monkeypatch, gates)
    assert conv_router.reprocess_conversation('c1', uid='u1') is gates.processed
    executed.assert_called_once()
    gates.compute.assert_called_once_with('u1', 'historical_summary_open')
    assert ('u1:c1', hs.ATTEMPTS_POLICY) in gates.reserved and ('u1', hs.DAILY_POLICY) in gates.reserved


@pytest.mark.parametrize('gate', ['disabled', 'attempts', 'global', 'byok'])
def test_reprocess_of_a_historical_row_honours_every_open_gate(monkeypatch, gate):
    gates = Gates(monkeypatch, _row())
    executed = _reprocess(monkeypatch, gates)
    if gate == 'disabled':
        monkeypatch.setenv(historical_tier.OPEN_ENABLED_ENV, 'false')
    elif gate == 'attempts':
        gates.limits[hs.ATTEMPTS_POLICY] = False
    elif gate == 'global':
        gates.limits[hs.GLOBAL_POLICY] = False
    else:
        monkeypatch.setattr(hs.users_db, 'is_byok_active', lambda uid: True)
    error = _reprocess_refusal()
    assert error.status_code == {'disabled': 503, 'attempts': 429, 'global': 429, 'byok': 409}[gate]
    executed.assert_not_called()
    gates.claim.assert_not_called()


def test_reprocess_claim_refusal_returns_the_historical_slots(monkeypatch):
    gates = Gates(monkeypatch, _row())
    executed = _reprocess(monkeypatch, gates)
    gates.claim.return_value = ({'conversation_id': 'c1'}, False)
    assert _reprocess_refusal().status_code == 409
    executed.assert_not_called()
    assert gates.reserved and set(gates.reserved) == set(gates.released)


def test_reprocess_of_a_normal_row_takes_no_historical_gate(monkeypatch):
    gates = Gates(monkeypatch, _row(processing_tier=None))
    monkeypatch.setenv(historical_tier.OPEN_ENABLED_ENV, 'false')
    executed = _reprocess(monkeypatch, gates)
    assert conv_router.reprocess_conversation('c1', uid='u1') is gates.processed
    executed.assert_called_once()
    gates.compute.assert_not_called()
