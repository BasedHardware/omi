"""EXP-004 admission and failure isolation. All data and providers are synthetic."""

import hashlib
import threading
import time
from concurrent.futures import Future
from dataclasses import replace
from datetime import timedelta
from unittest.mock import MagicMock

import fakeredis
import pytest

from database import jev_shadow as store
from utils import executors, metrics
from utils.conversations import jev_shadow as shadow
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import RelevanceDecision
from utils.llm.jev_client import JevAnswers

SENTINEL = 'PRIVATE_SENTINEL_NEVER_PERSIST_5831'
GET_SHADOW_REDIS = shadow._get_shadow_redis
MODEL = RelevanceDecision(
    'discard',
    'model',
    'model_discard',
    ProcessingTrigger.CAPTURE_END,
    model_tier_reached=True,
    nano_verdict='discard',
    nano_reason='model_discard',
)


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT', '100')
    monkeypatch.setenv('MEMORY_OWNER_JEV_SHADOW_PERCENT', '100')
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP', '60000')
    monkeypatch.setenv('MEMORY_OWNER_JEV_SHADOW_DAILY_CAP', '60000')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(shadow, '_get_shadow_redis', lambda deadline: redis)
    monkeypatch.setattr(shadow, 'get_jev_shadow_executor', MagicMock())
    monkeypatch.setattr(
        shadow, '_slots', {'relevance': threading.BoundedSemaphore(2), 'owner': threading.BoundedSemaphore(2)}
    )
    asked, records, outcomes = [], [], []

    def ask(state, questions, **kwargs):
        asked.append((state, questions, kwargs))
        return JevAnswers(
            'typesafe/jev-1.13-20260917',
            {
                'worth_keeping': {'noul': 0.02},
                'owner': {'probabilities': {'user': 0.91, 'third_party': 0.06, 'general_knowledge': 0.03}},
            },
        )

    def submit(_executor, fn, *args):
        future = Future()
        fn(*args)
        future.set_result(None)
        return future

    monkeypatch.setattr(shadow, 'ask_jev', ask)
    monkeypatch.setattr(shadow, 'submit_with_context', submit)
    monkeypatch.setattr(
        shadow, 'write_jev_shadow', lambda uid, rid, record, **kwargs: records.append((uid, rid, record)) or True
    )
    monkeypatch.setattr(shadow, 'record_jev_shadow_outcome', lambda lane, outcome: outcomes.append((lane, outcome)))
    return redis, asked, records, outcomes


def relevance(**kwargs):
    payload = dict(
        uid='synthetic-user',
        conversation_id='synthetic-conv',
        transcript=f'User: {SENTINEL}',
        decision=MODEL,
        arm='nano',
        source='omi',
        transcript_only=True,
    )
    payload.update(kwargs)
    shadow.submit_relevance_shadow(**payload)


def owner(**kwargs):
    payload = dict(
        uid='synthetic-user',
        conversation_id='synthetic-conv',
        candidate_content=SENTINEL,
        state=f'Synthetic owner state {SENTINEL}',
        user_name=SENTINEL,
        pipeline_subject_kind='speaker',
        source='desktop',
        n_quotes=2,
        user_name_present=True,
    )
    payload.update(kwargs)
    shadow.submit_owner_shadow(**payload)


def test_zero_percent_does_not_submit_or_claim(harness, monkeypatch):
    redis, asked, records, outcomes = harness
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT', '0')
    monkeypatch.setenv('MEMORY_OWNER_JEV_SHADOW_PERCENT', '0')
    submit = MagicMock()
    monkeypatch.setattr(shadow, 'submit_with_context', submit)
    relevance()
    owner()
    submit.assert_not_called()
    assert not asked and not records and redis.dbsize() == 0
    assert outcomes == [('relevance', 'cohort'), ('owner', 'cohort')]


@pytest.mark.parametrize(
    'overrides',
    [
        {'arm': 'jev'},
        {'transcript_only': False},
        {'transcript': ''},
        {'transcript': 'word ' * 101},
        {'decision': replace(MODEL, model_tier_reached=False)},
    ],
)
def test_relevance_admission_requires_the_measured_population(harness, overrides):
    _, asked, records, _ = harness
    relevance(**overrides)
    assert not asked and not records


def test_atomic_dedupe_includes_content_version_uid_and_lane(harness, monkeypatch):
    _, asked, records, outcomes = harness
    relevance()
    relevance()
    relevance(transcript='User: a different synthetic fragment')
    relevance(uid='other-synthetic-user')
    monkeypatch.setattr(shadow.relevance_jev, 'QUESTION_VERSION', 'relevance_b2')
    relevance()
    owner()
    owner()
    assert len(asked) == 5 and len(records) == 5
    assert outcomes.count(('relevance', 'deduped')) == 1
    assert outcomes.count(('owner', 'deduped')) == 1


@pytest.mark.parametrize(
    'lane,cap_env,submit',
    [
        ('relevance', 'CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP', relevance),
        ('owner', 'MEMORY_OWNER_JEV_SHADOW_DAILY_CAP', owner),
    ],
)
def test_global_cap_is_atomic_and_dedupes_before_consuming_cap(harness, monkeypatch, lane, cap_env, submit):
    _, asked, _, outcomes = harness
    monkeypatch.setenv(cap_env, '1')
    submit()
    submit()
    submit(uid='other-user', conversation_id='other-conversation')
    assert len(asked) == 1
    assert outcomes == [(lane, 'ok'), (lane, 'deduped'), (lane, 'cap')]


@pytest.mark.parametrize('cap', ['broken', '0', '-1', 'nan'])
def test_invalid_cap_never_calls_vendor(harness, monkeypatch, cap):
    _, asked, _, outcomes = harness
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP', cap)
    relevance()
    assert not asked and outcomes == [('relevance', 'cap')]


def test_redis_down_never_calls_vendor(harness, monkeypatch):
    _, asked, _, outcomes = harness
    monkeypatch.setattr(harness[0], 'eval', MagicMock(side_effect=RuntimeError(SENTINEL)))
    relevance()
    owner()
    assert not asked
    assert outcomes == [('relevance', 'redis_unavailable'), ('owner', 'redis_unavailable')]


def test_no_text_in_records_logs_or_metric_labels(harness, monkeypatch, caplog):
    _, asked, records, outcomes = harness
    agreement = MagicMock()
    monkeypatch.setattr(shadow, 'RELEVANCE_JEV_SHADOW_AGREEMENT', agreement)
    relevance(source=SENTINEL)
    owner(source=SENTINEL, pipeline_subject_kind=SENTINEL)
    assert SENTINEL in asked[0][0]
    assert SENTINEL not in repr(records) + repr(outcomes) + caplog.text + repr(agreement.mock_calls)
    assert records[0][2]['source'] == records[1][2]['source'] == 'unknown'
    assert records[1][2]['pipeline_subject_kind'] == 'unknown'
    for _, rid, record in records:
        content = f'User: {SENTINEL}' if record['lane'] == 'relevance' else SENTINEL
        content_sha = hashlib.sha256(content.encode()).hexdigest()
        version = record['question_version']
        assert (
            rid == hashlib.sha256(f"{record['lane']}|synthetic-conv|{content_sha}|{version}".encode()).hexdigest()[:32]
        )
        assert record['served_model'] == 'typesafe/jev-1.13-20260917'
    owner_record = records[1][2]
    assert (owner_record['p_user'], owner_record['p_third_party'], owner_record['p_general_knowledge']) == (
        0.91,
        0.06,
        0.03,
    )
    assert owner_record['candidate_sha'] == hashlib.sha256(SENTINEL.encode()).hexdigest()


@pytest.mark.parametrize('nano', ['keep', 'discard', None])
@pytest.mark.parametrize('p_discard', [0.94, 0.95, 0.97])
def test_agreement_uses_raw_nano_and_strict_threshold(harness, monkeypatch, nano, p_discard):
    agreement = MagicMock()
    monkeypatch.setattr(shadow, 'RELEVANCE_JEV_SHADOW_AGREEMENT', agreement)
    monkeypatch.setattr(shadow, 'ask_jev', lambda *a, **k: JevAnswers(None, {'worth_keeping': {'noul': 1 - p_discard}}))
    relevance(
        decision=replace(
            MODEL,
            verdict='keep',
            decided_by='override',
            reason='calendar_overlap',
            nano_verdict=nano,
            nano_reason='neighbor_fragment' if nano == 'discard' else None,
        )
    )
    agreement.labels.assert_called_once_with(nano or 'none', 'true' if p_discard > 0.95 else 'false')
    assert harness[2][0][2]['nano_reason'] == ('neighbor_fragment' if nano == 'discard' else None)


@pytest.mark.parametrize('outcome', ['timeout', 'http_429', 'unconfigured'])
def test_failed_answer_is_swallowed_and_classified(harness, monkeypatch, outcome):
    def unavailable(*args, **kwargs):
        kwargs['outcome_observer'](outcome)
        return None

    monkeypatch.setattr(shadow, 'ask_jev', unavailable)
    before = MODEL.as_record()
    relevance()
    assert MODEL.as_record() == before and not harness[2]
    assert harness[3] == [('relevance', outcome if outcome in {'timeout', 'http_429'} else 'jev_failed')]


def test_worker_and_submission_exceptions_never_escape(harness, monkeypatch, caplog):
    monkeypatch.setattr(shadow, 'ask_jev', MagicMock(side_effect=RuntimeError(SENTINEL)))
    relevance()
    owner()
    monkeypatch.setattr(shadow, 'submit_with_context', MagicMock(side_effect=RuntimeError(SENTINEL)))
    relevance(conversation_id='next')
    assert harness[3] == [('relevance', 'jev_failed'), ('owner', 'jev_failed'), ('relevance', 'dropped')]
    assert SENTINEL not in caplog.text
    assert shadow._slots['relevance'].acquire(blocking=False)
    shadow._slots['relevance'].release()


def test_slow_vendor_bounds_pending_work_and_queue_deadline(harness, monkeypatch):
    pending = []
    tick = [0.0]
    monkeypatch.setattr(shadow.time, 'monotonic', lambda: tick[0])

    def enqueue(_executor, fn, *args):
        future = Future()
        pending.append((fn, args, future))
        return future

    monkeypatch.setattr(shadow, 'submit_with_context', enqueue)
    for i in range(3):
        relevance(conversation_id=str(i))
    assert len(pending) == 2 and harness[3] == [('relevance', 'dropped')]
    assert not harness[1]  # submitting never performs Redis/vendor IO
    tick[0] = 3
    for fn, args, future in pending:
        fn(*args)
        future.set_result(None)
    assert harness[3][-2:] == [('relevance', 'timeout'), ('relevance', 'timeout')]
    assert not harness[1] and harness[0].dbsize() == 0


def test_late_vendor_answer_is_timeout_and_does_not_write(harness, monkeypatch):
    tick = [0.0]
    monkeypatch.setattr(shadow.time, 'monotonic', lambda: tick[0])

    def late(*a, **k):
        tick[0] = 3.0
        return JevAnswers(None, {'worth_keeping': {'noul': 0.01}})

    monkeypatch.setattr(shadow, 'ask_jev', late)
    relevance()
    assert harness[3] == [('relevance', 'timeout')] and not harness[2]


def test_cancelled_queue_task_releases_slot(harness, monkeypatch):
    tasks = []

    def enqueue(*args):
        future = Future()
        tasks.append(future)
        return future

    monkeypatch.setattr(shadow, 'submit_with_context', enqueue)
    relevance()
    tasks[0].cancel()
    assert shadow._slots['relevance'].acquire(blocking=False)
    assert shadow._slots['relevance'].acquire(blocking=False)


def _fenced_store_client(monkeypatch, *, deleting: bool):
    """Collections route like the transcription-shadow fence tests: document() returns the mock itself."""
    from types import SimpleNamespace

    client = MagicMock()
    users_root = MagicMock()
    ref = users_root.collection.return_value.document.return_value  # users/{uid}/jev_shadow/{record_id}
    marker = MagicMock()
    marker.get.return_value.exists = deleting
    client.collection.side_effect = lambda name: {
        'users': SimpleNamespace(document=lambda _uid: users_root),
        'account_deletions': SimpleNamespace(document=lambda _uid: marker),
    }[name]
    monkeypatch.setattr(store.firestore, 'transactional', lambda fn: fn)
    return client, ref, marker, client.transaction.return_value


def test_store_adds_60_day_expiry_without_plaintext_or_client_reads(monkeypatch):
    client, ref, marker, _ = _fenced_store_client(monkeypatch, deleting=False)
    monkeypatch.setattr(store.time, 'monotonic', lambda: 12.0)
    store.write_jev_shadow('user', 'hash-id', {'lane': 'owner', 'p_user': 0.91}, deadline=12.4, firestore_client=client)
    transaction = client.transaction.return_value
    record = transaction.set.call_args.args[1]
    assert record['expire_at'] - record['created_at'] == timedelta(days=60)
    client.collection.assert_any_call('users')
    client.collection.assert_any_call('account_deletions')
    marker.get.assert_called_once_with(transaction=transaction, retry=None, timeout=pytest.approx(0.4))
    assert ref.get.call_count == 0
    assert transaction.set.call_args.args[0] is ref


def test_store_deadline_includes_lazy_client_setup_and_never_retries(monkeypatch):
    tick = [10.0]
    client, ref, marker, _ = _fenced_store_client(monkeypatch, deleting=False)

    def get_client():
        tick[0] = 12.0
        return client

    monkeypatch.setattr(store, 'get_data_plane_firestore_client', get_client)
    monkeypatch.setattr(store.time, 'monotonic', lambda: tick[0])
    assert store.write_jev_shadow('user', 'hash-id', {'lane': 'owner'}, deadline=12.5) is True
    transaction = client.transaction.return_value
    # Lazy client setup consumed the budget; the commit itself is bounded by the
    # transaction, with the caller's deadline re-checked before starting.
    assert len(transaction.set.call_args_list) == 1


def test_store_commit_race_bounds_a_stalled_sdk_commit(monkeypatch):
    """The SDK's transactional commit uses its own default timeout, not the deadline.

    ``@firestore.transactional`` calls ``transaction._commit()`` with no timeout
    (google-cloud-firestore 2.20.0), so a stalled commit RPC must be raced by the
    remaining budget: the caller sees ``TimeoutError`` inside its documented task
    deadline instead of blocking a shadow worker for the SDK default (~60 s).
    """
    started = threading.Event()
    release = threading.Event()

    class _StalledCommit:
        def __call__(self, transaction):
            started.set()
            release.wait(timeout=30)
            return True

    client, _ref, _marker, _ = _fenced_store_client(monkeypatch, deleting=False)
    monkeypatch.setattr(store.time, 'monotonic', lambda: 12.0)
    monkeypatch.setattr(store.firestore, 'transactional', lambda fn: _StalledCommit())
    with pytest.raises(TimeoutError):
        store.write_jev_shadow('user', 'hash-id', {'lane': 'owner'}, deadline=12.4, firestore_client=client)
    assert started.wait(timeout=5), 'the stalled commit must have started before the deadline race fired'
    release.set()


def test_expired_store_budget_does_not_write(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(store.time, 'monotonic', lambda: 12.5)
    with pytest.raises(TimeoutError):
        store.write_jev_shadow('user', 'hash-id', {'lane': 'owner'}, deadline=12.5, firestore_client=client)
    transaction = client.transaction.return_value
    transaction.set.assert_not_called()


def test_store_write_is_fenced_by_account_deletion(monkeypatch):
    """A deleting account must not receive shadow records after its sweep."""
    client, _ref, marker, _ = _fenced_store_client(monkeypatch, deleting=True)
    monkeypatch.setattr(store.time, 'monotonic', lambda: 12.0)
    assert store.write_jev_shadow('user', 'hash-id', {'lane': 'owner'}, deadline=12.4, firestore_client=client) is False
    transaction = client.transaction.return_value
    marker.get.assert_called_once_with(transaction=transaction, retry=None, timeout=pytest.approx(0.4))
    transaction.set.assert_not_called()


def test_worker_passes_original_deadline_to_store(harness, monkeypatch):
    tick = [10.0]
    monkeypatch.setattr(shadow.time, 'monotonic', lambda: tick[0])
    answer = shadow.ask_jev

    def slow_answer(*args, **kwargs):
        tick[0] = 12.2
        return answer(*args, **kwargs)

    client, _ref, _marker, _ = _fenced_store_client(monkeypatch, deleting=False)
    monkeypatch.setattr(shadow, 'ask_jev', slow_answer)
    monkeypatch.setattr(store, 'get_data_plane_firestore_client', lambda: client)
    monkeypatch.setattr(shadow, 'write_jev_shadow', store.write_jev_shadow)
    relevance()
    transaction = client.transaction.return_value
    # 12.5 deadline - 12.2 consumed = 0.3s left when the store commit begins.
    assert len(transaction.set.call_args_list) == 1
    assert harness[3] == [('relevance', 'ok')]


@pytest.mark.parametrize('remaining', [0.08, 0.8, 2.5, 10.0])
def test_redis_client_is_lazy_attempt_owned_and_uses_remaining_budget(monkeypatch, remaining):
    constructor = MagicMock()
    monkeypatch.setattr(shadow.redis, 'Redis', constructor)
    monkeypatch.setattr(shadow.time, 'monotonic', lambda: 10.0)
    monkeypatch.setenv('REDIS_DB_HOST', 'synthetic-redis')
    monkeypatch.setenv('REDIS_DB_PORT', '6380')
    monkeypatch.setenv('REDIS_DB_PASSWORD', 'synthetic-password')
    constructor.assert_not_called()
    first = GET_SHADOW_REDIS(10.0 + remaining)
    second = GET_SHADOW_REDIS(10.0 + remaining / 2)
    assert constructor.call_count == 2
    assert first is constructor.return_value and second is constructor.return_value
    for call, budget in zip(constructor.call_args_list, (remaining, remaining / 2)):
        kwargs = call.kwargs
        assert kwargs['host'] == 'synthetic-redis' and kwargs['port'] == 6380
        assert kwargs['username'] == 'default' and kwargs['password'] == 'synthetic-password'
        assert kwargs['ssl'] is False  # redis_db uses Redis's non-TLS default.
        assert 0 < kwargs['socket_connect_timeout'] <= min(0.5, budget)
        assert 0 < kwargs['socket_timeout'] <= min(0.5, budget)
        assert kwargs['retry']._retries == 0 and kwargs['retry_on_timeout'] is False
        assert kwargs['max_connections'] == 1 and kwargs['health_check_interval'] == 0
        assert kwargs['lib_name'] == kwargs['lib_version'] == ''


@pytest.mark.parametrize('failure', ['construct', 'close', 'expired'])
def test_redis_client_errors_fail_closed(harness, monkeypatch, failure):
    client = MagicMock()
    client.__enter__.return_value = client
    client.eval.return_value = 1
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(shadow.redis, 'Redis', constructor)
    monkeypatch.setattr(shadow, '_get_shadow_redis', GET_SHADOW_REDIS)
    if failure == 'construct':
        constructor.side_effect = ValueError(SENTINEL)
    elif failure == 'close':
        client.__exit__.side_effect = RuntimeError(SENTINEL)
    deadline = time.monotonic() + (2.5 if failure != 'expired' else -1)
    assert shadow._admit('relevance', 'u', 'c', 'sha', 'version', deadline) == 'redis_unavailable'
    assert not harness[1]
    if failure == 'expired':
        constructor.assert_not_called()


def test_hung_redis_releases_shadow_worker_within_task_deadline(harness, monkeypatch):
    blocked = threading.Event()
    clients = []

    class HungRedis:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            clients.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def eval(self, *args):
            # Simulate a stalled connect and read honoring the actual SDK bounds.
            blocked.wait(self.kwargs['socket_connect_timeout'])
            blocked.wait(self.kwargs['socket_timeout'])
            raise shadow.redis.exceptions.TimeoutError(SENTINEL)

    monkeypatch.setattr(shadow.redis, 'Redis', HungRedis)
    monkeypatch.setattr(shadow, '_get_shadow_redis', GET_SHADOW_REDIS)
    monkeypatch.setattr(shadow, 'DEADLINE_SECONDS', 0.5)
    futures = []

    def submit(executor, fn, *args):
        future = executors.submit_with_context(executor, fn, *args)
        futures.append(future)
        return future

    monkeypatch.setattr(shadow, 'submit_with_context', submit)
    with executors.MonitoredThreadPoolExecutor(
        name='test-shadow', max_workers=4, thread_name_prefix='jev-shadow'
    ) as pool:
        monkeypatch.setattr(shadow, 'get_jev_shadow_executor', lambda: pool)
        started = time.monotonic()
        relevance()
        futures[0].result(timeout=0.5)
        assert time.monotonic() - started < 0.5
        assert shadow._slots['relevance'].acquire(blocking=False)
        assert shadow._slots['relevance'].acquire(blocking=False)
    assert clients[0].closed
    assert not harness[1] and not harness[2]
    assert harness[3] == [('relevance', 'redis_unavailable')]


def test_both_shadow_lanes_use_dedicated_pool_without_touching_llm_executor(harness, monkeypatch):
    monkeypatch.setattr(executors, '_jev_shadow_executor', None)
    monkeypatch.setattr(executors, '_ALL_EXECUTORS', list(executors._ALL_EXECUTORS))
    foreground = MagicMock(side_effect=AssertionError('foreground LLM pool touched'))
    monkeypatch.setattr(executors.llm_executor, 'submit', foreground)
    monkeypatch.setattr(shadow, 'get_jev_shadow_executor', executors.get_jev_shadow_executor)
    futures, threads = [], []
    answer = shadow.ask_jev

    def ask(*args, **kwargs):
        threads.append(threading.current_thread().name)
        return answer(*args, **kwargs)

    def submit(executor, fn, *args):
        future = executors.submit_with_context(executor, fn, *args)
        futures.append(future)
        return future

    monkeypatch.setattr(shadow, 'ask_jev', ask)
    monkeypatch.setattr(shadow, 'submit_with_context', submit)
    try:
        relevance()
        owner()
        for future in futures:
            future.result(timeout=2)
        assert len(threads) == 2 and all(thread.startswith('jev-shadow') for thread in threads)
        assert sorted(harness[3]) == [('owner', 'ok'), ('relevance', 'ok')]
        foreground.assert_not_called()
    finally:
        executors.get_jev_shadow_executor().shutdown(wait=True)


def test_metric_labels_are_bounded_and_never_raise(monkeypatch):
    counter = MagicMock()
    monkeypatch.setattr(metrics, 'JEV_SHADOW_TOTAL', counter)
    metrics.record_jev_shadow_outcome(SENTINEL, SENTINEL)
    counter.labels.assert_called_once_with(lane='other', outcome='jev_failed')
    counter.labels.side_effect = RuntimeError(SENTINEL)
    metrics.record_jev_shadow_outcome('relevance', 'ok')


def test_owner_incomplete_distribution_is_not_persisted(harness, monkeypatch):
    monkeypatch.setattr(
        shadow,
        'ask_jev',
        lambda *a, **k: JevAnswers(None, {'owner': {'probabilities': {'user': 0.91, 'third_party': 0.09}}}),
    )
    owner()
    assert not harness[2] and harness[3] == [('owner', 'jev_failed')]


def test_firestore_deadline_exceeded_is_classified_as_timeout(harness, monkeypatch):
    from google.api_core import exceptions as google_api_exceptions

    monkeypatch.setattr(shadow, 'ask_jev', lambda *a, **k: JevAnswers(None, {'worth_keeping': {'noul': 0.9}}))
    monkeypatch.setattr(
        shadow,
        'write_jev_shadow',
        MagicMock(side_effect=google_api_exceptions.DeadlineExceeded('deadline exceeded')),
    )
    relevance()
    assert harness[3] == [('relevance', 'timeout')] and not harness[2]


def test_shadow_calls_suppress_the_live_decision_metric(harness, monkeypatch):
    """Shadow asks must not touch omi_jev_decision_total or its latency histogram."""
    asked_kwargs = []

    def ask(state, questions, **kwargs):
        asked_kwargs.append(kwargs)
        return JevAnswers(None, {'worth_keeping': {'noul': 0.02}})

    monkeypatch.setattr(shadow, 'ask_jev', ask)
    relevance()
    owner()
    assert len(asked_kwargs) == 2
    assert all(kwargs.get('record_decision_metrics') is False for kwargs in asked_kwargs)


def test_fenced_store_write_records_dropped_not_ok(harness, monkeypatch):
    client, _ref, _marker, _ = _fenced_store_client(monkeypatch, deleting=True)
    monkeypatch.setattr(store, 'get_data_plane_firestore_client', lambda: client)
    monkeypatch.setattr(shadow, 'write_jev_shadow', store.write_jev_shadow)
    relevance()
    assert harness[3] == [('relevance', 'dropped')] and not harness[2]
