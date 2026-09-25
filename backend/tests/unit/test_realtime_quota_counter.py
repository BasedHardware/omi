"""One chat-question counter across every realtime entry path, on every plan.

Shard S15 of the local-models free tier (decision 8): a push-to-talk turn is a
chat question. The number the gate reads is ``get_monthly_chat_usage(...)['questions']``.

Who debits it, per path:

* text chat and PTT — the chat request (``record_chat_quota_question``). The
  legacy relay is the voice shell only: the desktop client sends the relay's
  transcript through desktop chat, so the relay itself must never debit;
* the direct hub — ``/v2/realtime/usage``, idempotent when the client sends a
  turn id, the historical bare increment otherwise;
* minting a hub session — never.

These tests prove those writers fold into that one number exactly once, that
the relay gates every plan and stops an Omi-paid session one turn past a hard
cap (failing closed when the quota cannot be read), and that the hub never
mints or reports past a hard cap, BYOK or not.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from google.cloud import firestore

import database.llm_usage as llm_usage_db
import database.user_usage as user_usage_db
import utils.subscription as subscription
from config.plan_catalog import PlanType
from routers import desktop_realtime, omni_relay

UID = 'user-s15'
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


# --- a Firestore double that materialises the writers' real payloads -----------------------


def _materialise(existing: Any, value: Any) -> Any:
    if isinstance(value, firestore.Increment):
        base = existing if isinstance(existing, (int, float)) and not isinstance(existing, bool) else 0
        return base + value.value
    if isinstance(value, dict):
        merged = dict(existing) if isinstance(existing, dict) else {}
        for key, inner in value.items():
            merged[key] = _materialise(merged.get(key), inner)
        return merged
    return value


class _Snapshot:
    def __init__(self, doc_id: str, data: dict[str, Any] | None) -> None:
        self.id = doc_id
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return None if self._data is None else dict(self._data)


class _Document:
    def __init__(self, store: '_Store', path: tuple[str, ...]) -> None:
        self._store = store
        self.path = path
        self.id = path[-1]

    def collection(self, name: str) -> '_Collection':
        return _Collection(self._store, self.path + (name,))

    def get(self, _fields: list[str] | None = None, *, transaction: Any = None) -> _Snapshot:
        return _Snapshot(self.id, self._store.rows.get(self.path))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        if self._store.fail_writes:
            raise RuntimeError('firestore unavailable')
        current = self._store.rows.get(self.path, {}) if merge else {}
        self._store.rows[self.path] = _materialise(current, data)


class _Collection:
    def __init__(self, store: '_Store', path: tuple[str, ...], filters: tuple[Any, ...] = ()) -> None:
        self._store = store
        self.path = path
        self._filters = filters

    def document(self, name: str) -> _Document:
        return _Document(self._store, self.path + (name,))

    def where(self, filter: Any) -> '_Collection':
        return _Collection(self._store, self.path, self._filters + (filter,))

    def stream(self):
        for path, data in list(self._store.rows.items()):
            if path[:-1] != self.path:
                continue
            doc_id = path[-1]
            ok = True
            for f in self._filters:
                assert f.field_path == '__name__'
                if f.op_string == '>=' and doc_id < f.value.id:
                    ok = False
                if f.op_string == '<' and doc_id >= f.value.id:
                    ok = False
            if ok:
                yield _Snapshot(doc_id, data)

    def list_documents(self):
        raise AssertionError('chat-quota reads must stay bounded to the current month')


class _Transaction:
    """Enough of the Firestore transaction lifecycle for ``@transactional``."""

    def __init__(self, store: '_Store') -> None:
        self._store = store
        self._staged: list[tuple[_Document, dict[str, Any], bool]] = []
        self._id: bytes | None = None
        self._read_only = False
        self._max_attempts = 1

    def _begin(self, retry_id: bytes | None = None) -> None:
        self._id = retry_id or b'txn'

    def _commit(self) -> None:
        # Writes are staged and applied only here, so a failed commit proves a
        # multi-document write is all-or-nothing.
        if self._store.fail_next_commit:
            self._store.fail_next_commit = False
            self._staged.clear()
            raise RuntimeError('commit failed')
        for ref, data, merge in self._staged:
            ref.set(data, merge=merge)
        self._staged.clear()

    def _rollback(self) -> None:
        self._staged.clear()

    def _clean_up(self) -> None:
        self._id = None

    def set(self, ref: _Document, data: dict[str, Any], merge: bool = False) -> None:
        self._staged.append((ref, data, merge))


class _Store:
    def __init__(self, *, plan: str = 'basic') -> None:
        self.rows: dict[tuple[str, ...], dict[str, Any]] = {('users', UID): {'subscription': {'plan': plan}}}
        self.fail_next_commit = False
        self.fail_writes = False

    def collection(self, name: str) -> _Collection:
        return _Collection(self, (name,))

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def questions(self) -> int:
        return int(user_usage_db.get_monthly_chat_usage(UID, NOW, firestore_client=self)['questions'])


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture
def store(monkeypatch) -> _Store:
    store = _Store()
    monkeypatch.setattr(llm_usage_db, 'datetime', _FrozenDatetime)
    # The relay's admission reads resolve "this month" through user_usage too,
    # so freeze it alongside the writers or the seeded 2026-09-01 buckets are
    # only visible in September.
    monkeypatch.setattr(user_usage_db, 'datetime', _FrozenDatetime)
    monkeypatch.setattr(desktop_realtime, 'get_customer_firestore_client', lambda: store)
    return store


def _hub_report(turn_id: str = '') -> None:
    """The direct hub's write path, exactly as `/v2/realtime/usage` calls it."""
    desktop_realtime._record_usage(
        UID,
        desktop_realtime.UsageReport(provider='openai', input_audio_tokens=10, output_audio_tokens=5, turn_id=turn_id),
        input_tokens=10,
        output_tokens=5,
        cached_tokens=0,
        total_tokens=15,
        cost=0.001,
    )


def _chat_question(request_id: str) -> bool:
    """Text chat and PTT alike: the desktop chat router's own key shape."""
    return llm_usage_db.record_chat_quota_question(
        UID, f'desktop_chat_completions:{request_id}', 'desktop_chat_completions', platform='desktop'
    )


# --- the one counter ---------------------------------------------------------------------


def test_every_writer_folds_into_one_monthly_number(store, monkeypatch) -> None:
    monkeypatch.setattr(llm_usage_db, 'db', store)
    _hub_report()  # legacy client: bare increment
    _hub_report(turn_id='turn-1')  # new client: idempotent question
    assert _chat_question('req-1')  # a PTT or typed chat turn
    assert store.questions() == 3


def test_a_retried_hub_report_with_a_turn_id_counts_once(store) -> None:
    _hub_report(turn_id='turn-1')
    _hub_report(turn_id='turn-1')
    _hub_report(turn_id='turn-2')
    assert store.questions() == 2
    # Question and telemetry land in one transaction: two turns, two rows' worth of tokens, no more.
    day = store.rows[('users', UID, 'llm_usage', '2026-09-02')]
    assert day['desktop_chat']['input_tokens'] == 20
    assert day['desktop_chat']['call_count'] == 2
    assert day['desktop_chat'].get('quota_questions', 0) == 0  # the question is backend_chat's, not a second one
    assert day['backend_chat']['quota_questions'] == 2
    # Positive control for the negative: without a turn id the historical increment repeats.
    _hub_report()
    _hub_report()
    assert store.questions() == 4


def test_hub_telemetry_lands_on_the_question_transactions_own_day_and_plan(store, monkeypatch) -> None:
    """The telemetry is built inside the transaction from its plan key and day, not resolved separately."""
    seen: list[tuple[str, str]] = []
    real = llm_usage_db.usage_bucket_update

    def spy(uid, **kwargs):
        seen.append((kwargs['plan_key'], kwargs['today']))
        return real(uid, **kwargs)

    monkeypatch.setattr(llm_usage_db, 'usage_bucket_update', spy)
    _hub_report(turn_id='turn-1')
    assert seen == [('basic', '2026-09-02')]
    day = store.rows[('users', UID, 'llm_usage', '2026-09-02')]
    assert day['plan_usage']['basic']['desktop_chat']['input_tokens'] == 10
    assert day['plan_usage']['basic']['backend_chat']['quota_questions'] == 1


def test_a_hub_report_that_fails_to_commit_records_neither_question_nor_cost_and_retries_cleanly(store) -> None:
    store.fail_next_commit = True
    with pytest.raises(RuntimeError):
        _hub_report(turn_id='turn-1')
    assert store.questions() == 0
    assert ('users', UID, 'llm_usage', '2026-09-02') not in store.rows  # no telemetry without the question
    _hub_report(turn_id='turn-1')  # the retry is not mistaken for a duplicate
    assert store.questions() == 1
    assert store.rows[('users', UID, 'llm_usage', '2026-09-02')]['desktop_chat']['input_tokens'] == 10


def test_a_retried_chat_question_counts_once(store, monkeypatch) -> None:
    monkeypatch.setattr(llm_usage_db, 'db', store)
    assert _chat_question('req-1') is True
    assert _chat_question('req-1') is False
    assert store.questions() == 1


# --- the relay: gate every plan, never debit, stop one turn past a hard cap -----------------


class _FakeUpstream:
    def __init__(self, frames: list[str | bytes], drained: asyncio.Event) -> None:
        self.frames = frames
        self._drained = drained

    async def send(self, _message: str | bytes) -> None:
        return None

    def __aiter__(self):
        return self._replay()

    async def _replay(self):
        for frame in self.frames:
            yield frame
        self._drained.set()
        await asyncio.Event().wait()


class _FakeConnect:
    def __init__(self, upstream: _FakeUpstream) -> None:
        self.upstream = upstream

    async def __aenter__(self) -> _FakeUpstream:
        return self.upstream

    async def __aexit__(self, *_: object) -> None:
        return None


class _Socket:
    headers = {'authorization': 'Bearer token'}

    def __init__(self, provider: str, drained: asyncio.Event, before_accept: Any = None) -> None:
        self.query_params = {'provider': provider}
        self.closes: list[dict[str, Any]] = []
        self.forwarded = 0
        self.accepted = False
        self._drained = drained
        self._before_accept = before_accept

    async def accept(self) -> None:
        if self._before_accept is not None:
            self._before_accept()
        self.accepted = True

    async def close(self, **kwargs: Any) -> None:
        self.closes.append(kwargs)

    async def send_text(self, _text: str) -> None:
        self.forwarded += 1

    async def send_bytes(self, _data: bytes) -> None:
        self.forwarded += 1

    async def receive(self) -> dict[str, Any]:
        await self._drained.wait()
        return {'type': 'websocket.disconnect'}


async def _passthrough(_executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


def _created(response_id: str) -> str:
    return json.dumps({'type': 'response.created', 'response': {'id': response_id}})


def _delta() -> str:
    return json.dumps({'type': 'response.output_audio.delta', 'delta': 'AAAA'})


def _done(tokens: int, response_id: str = 'r1') -> str:
    usage = {
        'input_tokens': tokens,
        'output_tokens': 0,
        'input_token_details': {'audio_tokens': tokens},
        'output_token_details': {},
    }
    return json.dumps({'type': 'response.done', 'response': {'id': response_id, 'status': 'completed', 'usage': usage}})


def _allowed(plan: PlanType, *, used: int = 0, limit: int = 30) -> dict[str, Any]:
    return {'plan': plan, 'allowed': True, 'unit': 'questions', 'used': float(used), 'limit': float(limit)}


def _exhausted(plan: PlanType, *, limit: int = 30) -> dict[str, Any]:
    return {'plan': plan, 'allowed': False, 'unit': 'questions', 'used': float(limit), 'limit': float(limit)}


async def _run_relay(
    monkeypatch,
    *,
    frames: list[str | bytes],
    snapshots: list[Any],
    byok: bool = False,
    provider: str = 'openai',
    store: _Store | None = None,
    before_accept: Any = None,
    upstream: Any = None,
) -> tuple[_Socket, list[str]]:
    """Drive the relay end to end. `snapshots` feeds the connect gate first, then each re-check.

    Returns the socket and the list of counter-writer calls (which must stay empty).
    """
    drained = asyncio.Event()
    writes: list[str] = []
    feed = iter(snapshots)
    last = snapshots[-1]
    store = store or _Store()

    def snapshot(*_a, **_k):
        value = next(feed, last)
        if isinstance(value, Exception):
            raise value
        return value

    validated = {provider: 'sk-user'} if byok else {}
    monkeypatch.setattr(omni_relay, 'raise_if_gateway_feature_mode_blocks_direct_model_surface', lambda _s: None)
    monkeypatch.setattr(omni_relay, 'run_blocking', _passthrough)
    monkeypatch.setattr(omni_relay, '_verify_ws_auth', lambda _authz: UID)
    monkeypatch.setattr(omni_relay, 'extract_byok_from_websocket', lambda _ws: dict(validated))
    monkeypatch.setattr(omni_relay, 'validate_byok_websocket_keys', lambda _uid, keys: (dict(keys), None))
    monkeypatch.setattr(omni_relay, 'set_validated_byok_keys', lambda _keys, _uid: None)
    monkeypatch.setattr(omni_relay, 'is_trial_paywalled', lambda *_a, **_k: False)
    monkeypatch.setattr(omni_relay.users_db, 'is_byok_active', lambda _uid: byok)
    monkeypatch.setattr(omni_relay, 'get_chat_quota_snapshot', snapshot)
    # The relay's own persisted response count and its reader run for real against `store`;
    # the only writer that must never fire is the question writer (the chat request owns it).
    monkeypatch.setattr(omni_relay, 'get_customer_firestore_client', lambda: store)
    monkeypatch.setattr(llm_usage_db, 'record_chat_quota_question', lambda *a, **k: writes.append('question'))
    monkeypatch.setattr(omni_relay, 'schedule_managed_attempt', lambda _attempt: True)
    monkeypatch.setattr(omni_relay, '_upstream', lambda _p, _m: upstream or (('wss://upstream.invalid', {}), None))
    monkeypatch.setattr(
        omni_relay.websockets, 'connect', lambda *_a, **_k: _FakeConnect(_FakeUpstream(frames, drained))
    )
    socket = _Socket(provider, drained, before_accept=before_accept)
    await omni_relay.omni_relay(socket)
    return socket, writes


def _relay_responses_this_month(store: _Store) -> int:
    return user_usage_db.get_monthly_bucket_call_count(
        UID, omni_relay.RELAY_RESPONSE_BUCKET, NOW, firestore_client=store
    )


def _seed_relay_responses(store: _Store, count: int) -> None:
    store.rows[('users', UID, 'llm_usage', '2026-09-01')] = {'realtime_relay': {'call_count': count}}


@pytest.mark.asyncio
async def test_the_relay_never_debits_the_question_the_chat_request_owns(monkeypatch) -> None:
    socket, writes = await _run_relay(
        monkeypatch, frames=[_done(30, 'a'), _done(30, 'b')], snapshots=[_allowed(PlanType.basic)]
    )
    assert socket.accepted and socket.forwarded == 2
    assert writes == []
    assert not any(c.get('code') == 1008 for c in socket.closes)


@pytest.mark.parametrize('plan', [PlanType.basic, PlanType.plus, PlanType.unlimited_v2])
@pytest.mark.asyncio
async def test_the_connect_gate_closes_every_hard_capped_plan_at_its_cap(monkeypatch, plan) -> None:
    socket, writes = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[_exhausted(plan)])
    assert not socket.accepted
    assert socket.closes[0] == {'code': 1008, 'reason': 'quota_exceeded'}
    assert writes == []


@pytest.mark.asyncio
async def test_an_overage_plan_is_served_past_its_included_quota(monkeypatch) -> None:
    socket, _ = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[_exhausted(PlanType.operator)])
    assert socket.accepted and socket.forwarded == 1
    assert not any(c.get('code') == 1008 for c in socket.closes)


@pytest.mark.asyncio
async def test_an_omi_paid_session_stops_one_turn_after_a_hard_cap_is_reached(monkeypatch) -> None:
    """Turn 1 is served (the chat request behind it debits the 30th question); turn 2 never reaches the provider path."""
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b'), _done(30, 'c')],
        snapshots=[_allowed(PlanType.basic), _exhausted(PlanType.basic)],
    )
    assert socket.forwarded == 0  # the response that trips the cap is cut before its first frame
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_exceeded'}


@pytest.mark.asyncio
async def test_relay_responses_are_bounded_per_month_even_if_chat_never_debits(monkeypatch) -> None:
    """The question counter only advances when the client sends the chat request. A client that
    never does still runs out: the relay's own persisted monthly response count is checked against
    the plan's allowance (30 + grace 2) at every boundary. With 30 already served this month, the
    32nd response ends the session; the count survives the socket."""
    store = _Store()
    _seed_relay_responses(store, 30)
    socket, writes = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b'), _done(30, 'c'), _done(30, 'd')],
        snapshots=[_allowed(PlanType.basic, used=29)],  # stays 29 forever: no chat request ever lands
        store=store,
    )
    assert socket.forwarded == 1  # the second response reaches the allowance and is cut before its first frame
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_exceeded'}
    assert writes == []
    assert _relay_responses_this_month(store) == 32

    # Reconnecting buys nothing: the allowance is admission too, read at connect from the
    # persisted count, so the fresh socket is refused before any provider work.
    socket, _ = await _run_relay(
        monkeypatch, frames=[_done(30, 'e'), _done(30, 'f')], snapshots=[_allowed(PlanType.basic, used=29)], store=store
    )
    assert not socket.accepted
    assert socket.forwarded == 0
    assert socket.closes == [{'code': 1008, 'reason': 'quota_exceeded'}]
    assert _relay_responses_this_month(store) == 32


@pytest.mark.asyncio
async def test_a_user_cannot_hold_more_than_the_socket_cap_open_at_once(monkeypatch) -> None:
    """Admission reads a persisted count, so concurrently pre-opened sockets can race at a response
    start; the per-user open-socket cap makes that race finite (two per serving replica)."""
    monkeypatch.setattr(omni_relay, '_open_relay_sockets', {UID: omni_relay.MAX_OPEN_RELAY_SOCKETS_PER_USER})
    socket, _ = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[_allowed(PlanType.basic)])
    assert not socket.accepted
    assert socket.closes == [{'code': 1008, 'reason': 'session_limit'}]

    # A finished session releases its slot: the same user connects again afterwards.
    monkeypatch.setattr(omni_relay, '_open_relay_sockets', {})
    socket, _ = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[_allowed(PlanType.basic)])
    assert socket.accepted
    assert omni_relay._open_relay_sockets == {}


@pytest.mark.asyncio
async def test_the_socket_cap_does_not_touch_byok_or_overage_sessions(monkeypatch) -> None:
    """The cap exists only to bound the hard-cap race; sessions the hard cap does not apply to are not capped."""
    monkeypatch.setattr(omni_relay, '_open_relay_sockets', {UID: omni_relay.MAX_OPEN_RELAY_SOCKETS_PER_USER})
    socket, _ = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[_allowed(PlanType.basic)], byok=True)
    assert socket.accepted and socket.forwarded == 1
    socket, _ = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[_exhausted(PlanType.operator, limit=500)])
    assert socket.accepted and socket.forwarded == 1


@pytest.mark.asyncio
async def test_a_slot_is_released_when_the_session_ends_before_the_pumps(monkeypatch) -> None:
    """The slot is held from admission; a missing provider key or a failed accept must give it back,
    or two such attempts would lock the user out of this replica until it restarts."""
    monkeypatch.setattr(omni_relay, '_open_relay_sockets', {})
    socket, _ = await _run_relay(
        monkeypatch, frames=[_done(30)], snapshots=[_allowed(PlanType.basic)], upstream=(None, 'no OpenAI key')
    )
    assert socket.closes == [{'code': 1011, 'reason': 'no OpenAI key'}]
    assert omni_relay._open_relay_sockets == {}

    def accept_fails():
        raise RuntimeError('handshake failed')

    with pytest.raises(RuntimeError):
        await _run_relay(
            monkeypatch, frames=[_done(30)], snapshots=[_allowed(PlanType.basic)], before_accept=accept_fails
        )
    assert omni_relay._open_relay_sockets == {}


@pytest.mark.asyncio
async def test_a_quota_snapshot_that_cannot_be_read_at_connect_refuses_with_a_controlled_close(monkeypatch) -> None:
    socket, _ = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[RuntimeError('firestore unavailable')])
    assert not socket.accepted
    assert socket.closes == [{'code': 1008, 'reason': 'quota_unavailable'}]


def test_completed_response_identities_are_retained_past_the_largest_hard_capped_allowance() -> None:
    from utils.llm import realtime_usage
    from utils.llm.realtime_usage import RealtimeRelayObserver

    assert realtime_usage._MAX_COMPLETED_IDS >= 1000 + omni_relay.RESPONSES_GRACE_PAST_CAP
    observer = RealtimeRelayObserver('openai')
    for index in range(1002):
        observer.observe_upstream_frame(_created(f'r{index}'))
        observer.observe_upstream_frame(_done(30, f'r{index}'))
    assert observer.starts == 1002
    # A replay of the very first terminal frame, 1,001 responses later, is still recognised.
    assert observer.observe_upstream_frame(_done(30, 'r0')) == ()
    assert observer.starts == 1002


def test_open_response_identities_stay_exact_past_sixty_four_concurrent_responses() -> None:
    """Plus admits 202 responses and Unlimited-v2 1,002; identity must hold across all of them."""
    from utils.llm import realtime_usage
    from utils.llm.realtime_usage import RealtimeRelayObserver

    assert realtime_usage._MAX_OPEN_RESPONSES >= 1000 + omni_relay.RESPONSES_GRACE_PAST_CAP
    observer = RealtimeRelayObserver('openai')
    for index in range(200):
        observer.observe_upstream_frame(_created(f'r{index}'))
    assert observer.starts == 200
    # A replayed announcement of the 65th response, or of the 200th, is not a new start.
    observer.observe_upstream_frame(_created('r64'))
    observer.observe_upstream_frame(_created('r199'))
    assert observer.starts == 200
    # An unannounced terminal response counts its own start and closes none of the 200 open ones.
    observer.observe_upstream_frame(_done(30, 'unannounced'))
    assert observer.starts == 201
    flushed = observer.flush()
    assert len(flushed) == 16 and observer.dropped_at_flush == 184  # all 200 still open, budgeted at the flush


@pytest.mark.asyncio
async def test_a_session_ends_at_the_identity_capacity_so_a_month_spanning_socket_stays_exact(monkeypatch) -> None:
    """Identity is tracked per socket, the allowance per month. A socket that stays open across a
    month reset must not be able to outgrow the identities the observer can keep, so a session is
    ended (reconnect required) once it has started as many responses as the observer tracks, on
    every plan; here an overage session, which has no monthly admission bound."""
    from utils.llm.realtime_usage import MAX_RESPONSES_PER_SESSION, RealtimeRelayObserver, _MAX_OPEN_RESPONSES

    assert MAX_RESPONSES_PER_SESSION < _MAX_OPEN_RESPONSES  # the refused response keeps its identity
    store = _Store()
    frames = [_created(f'r{i}') for i in range(MAX_RESPONSES_PER_SESSION + 5)]
    socket, _ = await _run_relay(
        monkeypatch, frames=frames, snapshots=[_exhausted(PlanType.operator, limit=500)], store=store
    )
    assert socket.forwarded == MAX_RESPONSES_PER_SESSION  # the response past the limit is never delivered
    assert socket.closes[-1] == {'code': 1008, 'reason': 'session_limit'}
    # ... but the provider had started it, so it is counted for admission like every other.
    assert _relay_responses_this_month(store) == MAX_RESPONSES_PER_SESSION + 1
    # And it still had an identity: the observer never spilled into the identity-less tally.
    observer = RealtimeRelayObserver('openai')
    for frame in frames[: MAX_RESPONSES_PER_SESSION + 1]:
        observer.observe_upstream_frame(frame)
    assert observer._openai_overflow == 0
    assert (
        observer.observe_upstream_frame(_created(f'r{MAX_RESPONSES_PER_SESSION}')) == ()
        and observer.starts == MAX_RESPONSES_PER_SESSION + 1
    )


@pytest.mark.asyncio
async def test_a_cancelled_handler_drains_its_pumps_and_releases_its_slot(monkeypatch) -> None:
    """If the handler itself is cancelled while both pumps are pending, the pumps must not outlive it."""
    monkeypatch.setattr(omni_relay, '_open_relay_sockets', {})
    hold = asyncio.Event()
    upstream_blocked = asyncio.Event()
    client_blocked = asyncio.Event()

    class HoldingUpstream(_FakeUpstream):
        async def _replay(self):
            upstream_blocked.set()  # the upstream pump is now parked in its iterator
            await hold.wait()
            yield ''  # never reached

    class BlockingSocket(_Socket):
        async def receive(self) -> dict[str, Any]:
            client_blocked.set()  # the client pump is now parked in receive()
            return await super().receive()

    drained = asyncio.Event()
    upstream = HoldingUpstream([], drained)
    monkeypatch.setattr(omni_relay, 'raise_if_gateway_feature_mode_blocks_direct_model_surface', lambda _s: None)
    monkeypatch.setattr(omni_relay, 'run_blocking', _passthrough)
    monkeypatch.setattr(omni_relay, '_verify_ws_auth', lambda _authz: UID)
    monkeypatch.setattr(omni_relay, 'extract_byok_from_websocket', lambda _ws: {})
    monkeypatch.setattr(omni_relay, 'validate_byok_websocket_keys', lambda _uid, keys: ({}, None))
    monkeypatch.setattr(omni_relay, 'set_validated_byok_keys', lambda _keys, _uid: None)
    monkeypatch.setattr(omni_relay, 'is_trial_paywalled', lambda *_a, **_k: False)
    monkeypatch.setattr(omni_relay.users_db, 'is_byok_active', lambda _uid: False)
    monkeypatch.setattr(omni_relay, 'get_chat_quota_snapshot', lambda *_a, **_k: _allowed(PlanType.basic))
    monkeypatch.setattr(omni_relay, 'get_customer_firestore_client', lambda: _Store())
    monkeypatch.setattr(omni_relay, 'schedule_managed_attempt', lambda _attempt: True)
    monkeypatch.setattr(omni_relay, '_upstream', lambda _p, _m: (('wss://upstream.invalid', {}), None))
    monkeypatch.setattr(omni_relay.websockets, 'connect', lambda *_a, **_k: _FakeConnect(upstream))
    socket = BlockingSocket('openai', drained)  # receive() also blocks: both pumps stay pending

    handler = asyncio.create_task(omni_relay.omni_relay(socket))
    await asyncio.wait_for(asyncio.gather(upstream_blocked.wait(), client_blocked.wait()), timeout=5)
    assert omni_relay._open_relay_sockets == {UID: 1}
    pumps = [t for t in asyncio.all_tasks() if (t.get_name() or '').startswith(f'ws:{UID}:omni_')]
    assert len(pumps) == 2
    handler.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handler
    assert all(t.done() for t in pumps)  # drained, not orphaned
    assert omni_relay._open_relay_sockets == {}  # slot released after the drain


def test_socket_admission_is_a_strict_counter_per_user() -> None:
    table: dict[str, int] = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(omni_relay, '_open_relay_sockets', table)
        assert omni_relay._admit_relay_socket(UID)
        assert omni_relay._admit_relay_socket(UID)
        assert not omni_relay._admit_relay_socket(UID)
        assert omni_relay._admit_relay_socket('someone-else')
        omni_relay._release_relay_socket(UID)
        assert omni_relay._admit_relay_socket(UID)
        omni_relay._release_relay_socket(UID)
        omni_relay._release_relay_socket(UID)
        assert UID not in table


def test_a_gemini_usage_block_with_no_tokens_is_not_evidence_of_a_response() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('gemini')
    observer.observe_upstream_frame(b'{"usageMetadata": {"promptTokenCount": 0, "responseTokenCount": 0}}')
    observer.observe_upstream_frame(b'{"serverContent": {"turnComplete": true}}')
    assert observer.starts == 0
    # Positive control: a usage block that adds tokens is (fresh session, so it is not trailing usage).
    observer = RealtimeRelayObserver('gemini')
    observer.observe_upstream_frame(b'{"usageMetadata": {"promptTokenCount": 5, "responseTokenCount": 1}}')
    assert observer.starts == 1
    observer.observe_upstream_frame(b'{"serverContent": {"turnComplete": true}}')
    assert observer.starts == 1  # the boundary does not start a second response


def test_openai_responses_start_once_whether_or_not_they_were_announced() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('openai')
    observer.observe_upstream_frame(_created('a'))
    assert observer.starts == 1
    observer.observe_upstream_frame(_done(30, 'a'))
    assert observer.starts == 1  # the done of an announced response is not a second start
    observer.observe_upstream_frame(_done(30, 'b'))
    assert observer.starts == 2  # a done that was never announced still started


def test_openai_starts_are_keyed_to_response_identity() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('openai')
    observer.observe_upstream_frame(_created('a'))
    observer.observe_upstream_frame(_created('a'))  # a replayed announcement is not a second response
    assert observer.starts == 1
    # An unannounced response B finishing while A is still open is B's start, and does not close A.
    rows = observer.observe_upstream_frame(_done(30, 'b'))
    assert observer.starts == 2 and len(rows) == 1
    assert [t.provider_response_id for t in observer.flush()] == ['a']  # A was still open at disconnect
    # A replayed terminal frame for a finished response is neither a row nor a start.
    observer = RealtimeRelayObserver('openai')
    observer.observe_upstream_frame(_created('c'))
    assert len(observer.observe_upstream_frame(_done(30, 'c'))) == 1
    assert observer.observe_upstream_frame(_done(30, 'c')) == ()
    assert observer.starts == 1


@pytest.mark.asyncio
async def test_a_session_downgraded_to_a_hard_cap_mid_session_joins_the_socket_cap(monkeypatch) -> None:
    """An overage session is not capped at connect; when a fresh snapshot shows a hard cap, it needs a slot
    like any other, and with the user's slots already taken it stops rather than racing uncapped."""
    monkeypatch.setattr(omni_relay, '_open_relay_sockets', {UID: omni_relay.MAX_OPEN_RELAY_SOCKETS_PER_USER})
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b')],
        snapshots=[_allowed(PlanType.operator, limit=500), _allowed(PlanType.basic)],
    )
    assert socket.accepted  # admitted uncapped as operator
    assert socket.forwarded == 0  # the first response start saw the downgrade and found no slot
    assert socket.closes[-1] == {'code': 1008, 'reason': 'session_limit'}
    assert omni_relay._open_relay_sockets == {UID: omni_relay.MAX_OPEN_RELAY_SOCKETS_PER_USER}  # nothing leaked

    # With a slot free, the downgraded session enrolls, keeps going, and releases the slot at the end.
    monkeypatch.setattr(omni_relay, '_open_relay_sockets', {})
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b')],
        snapshots=[_allowed(PlanType.operator, limit=500), _allowed(PlanType.basic)],
    )
    assert socket.forwarded == 2
    assert omni_relay._open_relay_sockets == {}


@pytest.mark.asyncio
async def test_an_unreadable_admission_count_refuses_the_connect(monkeypatch) -> None:
    class Broken(_Store):
        def collection(self, name: str):
            raise RuntimeError('firestore unavailable')

    socket, _ = await _run_relay(monkeypatch, frames=[_done(30)], snapshots=[_allowed(PlanType.basic)], store=Broken())
    assert not socket.accepted
    assert socket.closes == [{'code': 1008, 'reason': 'quota_unavailable'}]


@pytest.mark.asyncio
async def test_gemini_activity_is_parsed_evidence_not_a_substring_match(monkeypatch) -> None:
    """A tool call opens a response (real activity); a frame whose text merely mentions the markers
    inside a string is not activity and neither starts nor ends anything."""
    store = _Store()
    _seed_relay_responses(store, 30)
    decoy = json.dumps({'serverContent': {'inputTranscription': {'text': 'say "turnComplete": true and "modelTurn"'}}})
    tool_call = json.dumps({'toolCall': {'functionCalls': [{'name': 'note', 'args': {}}]}})
    real_end = json.dumps({'serverContent': {'turnComplete': True}})
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[decoy.encode(), decoy.encode(), tool_call.encode(), real_end.encode(), tool_call.encode()],
        snapshots=[_allowed(PlanType.basic, used=29)],
        provider='gemini',
        store=store,
    )
    # decoys: nothing; tool call: response 31 starts (< 32, served); boundary; second tool call: 32 → cut before it.
    assert socket.forwarded == 4
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_exceeded'}
    assert _relay_responses_this_month(store) == 32


def test_the_admission_counter_does_not_mark_the_plan_cost_missing(monkeypatch) -> None:
    store = _Store()
    monkeypatch.setattr(omni_relay, 'get_customer_firestore_client', lambda: store)
    monkeypatch.setattr(omni_relay, 'get_chat_quota_snapshot', lambda *_a, **_k: _allowed(PlanType.basic))
    responses, _ = omni_relay._count_relay_response(UID)
    assert responses == 1
    day = next(data for path, data in store.rows.items() if path[:3] == ('users', UID, 'llm_usage'))
    metadata = day['plan_usage']['basic']['_metadata']
    assert metadata['last_cost_status'] == 'excluded'
    assert 'missing' not in metadata['cost_status_counts']


@pytest.mark.asyncio
async def test_a_response_is_counted_when_it_starts_so_a_mid_response_disconnect_cannot_dodge_it(monkeypatch) -> None:
    """Provider work begins at response.created; a client that hangs up before response.done is still counted."""
    store = _Store()
    socket, _ = await _run_relay(
        monkeypatch, frames=[_created('a'), _delta(), _delta()], snapshots=[_allowed(PlanType.basic)], store=store
    )
    assert socket.forwarded == 3
    assert _relay_responses_this_month(store) == 1  # counted at the start, not at a terminal frame that never came


@pytest.mark.asyncio
async def test_gemini_responses_are_counted_on_their_first_activity(monkeypatch) -> None:
    """The spend observer holds a completed Gemini turn for trailing usage; admission must not wait for it."""
    store = _Store()
    _seed_relay_responses(store, 31)
    audio = json.dumps(
        {'serverContent': {'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm', 'data': 'AA'}}]}}}
    )
    turn_end = json.dumps({'serverContent': {'turnComplete': True}, 'usageMetadata': {'promptTokenCount': 10}})
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[audio.encode(), turn_end.encode(), audio.encode(), turn_end.encode()],
        snapshots=[_allowed(PlanType.basic, used=29)],
        provider='gemini',
        store=store,
    )
    # Turn 1's first audio frame: count 32 = allowance → cut before that frame; nothing is forwarded.
    assert socket.forwarded == 0
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_exceeded'}
    assert _relay_responses_this_month(store) == 32


@pytest.mark.asyncio
async def test_a_gemini_response_that_is_cut_before_its_boundary_was_still_counted(monkeypatch) -> None:
    store = _Store()
    audio = json.dumps(
        {'serverContent': {'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm', 'data': 'AA'}}]}}}
    )
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[audio.encode(), audio.encode()],
        snapshots=[_allowed(PlanType.basic)],
        provider='gemini',
        store=store,
    )
    assert socket.forwarded == 2
    assert _relay_responses_this_month(store) == 1


@pytest.mark.asyncio
async def test_the_allowance_follows_a_fresh_snapshot_at_every_boundary(monkeypatch) -> None:
    """An upgrade to an overage plan mid-session lifts the bound."""
    store = _Store()
    _seed_relay_responses(store, 31)
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b'), _done(30, 'c')],
        snapshots=[_allowed(PlanType.basic, used=29), _exhausted(PlanType.operator, limit=500)],
        store=store,
    )
    assert socket.forwarded == 3  # operator: no response bound, and overage is served past its cap


@pytest.mark.asyncio
async def test_an_overage_plan_has_no_monthly_admission_bound_but_is_still_counted(monkeypatch) -> None:
    """Overage plans are billed per question, so the monthly allowance does not apply; the only bound
    they carry is the operational per-session identity limit tested elsewhere."""
    store = _Store()
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b'), _done(30, 'c')],
        snapshots=[{'plan': PlanType.operator, 'allowed': False, 'unit': 'questions', 'used': 501.0, 'limit': 500.0}],
        store=store,
    )
    assert socket.forwarded == 3
    assert _relay_responses_this_month(store) == 3


@pytest.mark.asyncio
async def test_a_snapshot_without_a_question_allowance_bounds_the_session_to_the_grace(monkeypatch) -> None:
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b'), _done(30, 'c')],
        snapshots=[{'plan': PlanType.basic, 'allowed': True}],
    )
    assert socket.forwarded == 1
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_exceeded'}


@pytest.mark.asyncio
async def test_a_quota_read_that_cannot_be_answered_stops_a_managed_session(monkeypatch) -> None:
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b')],
        snapshots=[_allowed(PlanType.basic), RuntimeError('firestore unavailable')],
    )
    assert socket.forwarded == 0
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_unavailable'}


@pytest.mark.asyncio
async def test_a_response_count_that_cannot_be_written_stops_a_managed_session(monkeypatch) -> None:
    store = _Store()
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[_done(30, 'a'), _done(30, 'b')],
        snapshots=[_allowed(PlanType.basic)],
        store=store,
        before_accept=lambda: setattr(store, 'fail_writes', True),
    )
    assert socket.accepted  # the connect-time read worked; the boundary write is what fails
    assert socket.forwarded == 0
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_unavailable'}


@pytest.mark.asyncio
async def test_every_started_response_counts_toward_admission_even_without_usage(monkeypatch) -> None:
    """A cancelled response that reports no usage is still provider work that began; admission is
    about work started, so it counts, and here it is the response on which the plan runs out."""
    store = _Store()
    no_usage = json.dumps({'type': 'response.done', 'response': {'id': 'x', 'status': 'cancelled'}})
    socket, _ = await _run_relay(
        monkeypatch,
        frames=[no_usage, _done(30, 'z')],
        snapshots=[_allowed(PlanType.basic), _exhausted(PlanType.basic)],
        store=store,
    )
    assert socket.forwarded == 0
    assert socket.closes[-1] == {'code': 1008, 'reason': 'quota_exceeded'}
    assert _relay_responses_this_month(store) == 1


@pytest.mark.asyncio
async def test_a_byok_served_session_is_never_re_checked(monkeypatch) -> None:
    socket, writes = await _run_relay(
        monkeypatch, frames=[_done(30, 'a'), _done(30, 'b')], snapshots=[_exhausted(PlanType.basic)], byok=True
    )
    assert socket.accepted and socket.forwarded == 2
    assert writes == []


# --- the hub: minting is not a question, and BYOK buys no managed token ------------------


@pytest.mark.asyncio
async def test_minting_a_session_debits_nothing(monkeypatch) -> None:
    """A rewarm mint (#12331 class) and a turn mint look identical here; neither may consume quota."""
    monkeypatch.setenv('OPENAI_API_KEY', 'platform-key')
    gates: list[tuple[Any, ...]] = []

    async def run(_executor, function, *args, **kwargs):
        gates.append((function, args, kwargs))
        assert function is desktop_realtime.enforce_desktop_chat_quota
        return None

    async def post_json(*_a, **_k):
        return {'value': 'ek_secret', 'expires_at': 1}, None

    async def persist(*_a):
        return None

    def forbidden(*_a, **_k):
        raise AssertionError('a mint must not touch the chat counter')

    monkeypatch.setattr(desktop_realtime, 'run_blocking', run)
    monkeypatch.setattr(desktop_realtime, '_post_json', post_json)
    monkeypatch.setattr(desktop_realtime, '_persist_session', persist)
    monkeypatch.setattr(desktop_realtime.llm_usage_db, 'record_llm_usage_bucket', forbidden)
    monkeypatch.setattr(desktop_realtime.llm_usage_db, 'record_chat_quota_question', forbidden)

    response = await desktop_realtime.mint_session(desktop_realtime.MintRequest(provider='openai'), UID)
    assert response.status_code == 200
    assert [(g[1], g[2]) for g in gates] == [((UID, 'desktop'), {'byok_exempt': False})]


@pytest.mark.parametrize('byok_active', [False, True])
def test_no_mint_at_zero_remaining_on_a_hard_capped_plan_byok_or_not(monkeypatch, byok_active) -> None:
    """The hub hands out Omi's key; a user's Anthropic BYOK must not buy a managed OpenAI session past the cap."""
    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *_a, **_k: False)
    monkeypatch.setattr(subscription.users_db, 'is_byok_active', lambda *_a, **_k: byok_active)
    monkeypatch.setattr(subscription, '_request_has_byok_provider', lambda *_a, **_k: True)
    monkeypatch.setattr(subscription, 'get_customer_firestore_client', lambda: object())
    monkeypatch.setattr(
        subscription,
        'get_chat_quota_snapshot',
        lambda *_a, **_k: {
            'plan': PlanType.basic,
            'unit': 'questions',
            'used': 30.0,
            'limit': 30.0,
            'allowed': False,
            'reset_at': 0,
        },
    )
    with pytest.raises(HTTPException) as error:
        subscription.enforce_desktop_chat_quota(UID, 'desktop', byok_exempt=False)
    assert error.value.status_code == 402
    # Positive control: desktop chat (Anthropic-served, BYOK-exempt) still lets that user through.
    if byok_active:
        subscription.enforce_desktop_chat_quota(UID, 'desktop')


def test_an_overage_plan_still_mints(monkeypatch) -> None:
    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *_a, **_k: False)
    monkeypatch.setattr(subscription.users_db, 'is_byok_active', lambda *_a, **_k: False)
    monkeypatch.setattr(subscription, 'get_customer_firestore_client', lambda: object())
    monkeypatch.setattr(
        subscription,
        'get_chat_quota_snapshot',
        lambda *_a, **_k: {
            'plan': PlanType.operator,
            'unit': 'questions',
            'used': 501.0,
            'limit': 500.0,
            'allowed': False,
            'reset_at': 0,
        },
    )
    subscription.enforce_desktop_chat_quota(UID, 'desktop', byok_exempt=False)
