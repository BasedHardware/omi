"""EXP-004 admission and failure isolation. All data and providers are synthetic."""

import hashlib
import threading
from concurrent.futures import Future
from dataclasses import replace
from datetime import timedelta
from unittest.mock import MagicMock

import fakeredis
import pytest

from database import jev_shadow as store
from utils import metrics
from utils.conversations import jev_shadow as shadow
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import RelevanceDecision
from utils.llm.jev_client import JevAnswers

SENTINEL = 'PRIVATE_SENTINEL_NEVER_PERSIST_5831'
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
    monkeypatch.setattr(shadow.redis_db, 'r', redis)
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
    monkeypatch.setattr(shadow, 'write_jev_shadow', lambda uid, rid, record: records.append((uid, rid, record)))
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
    monkeypatch.setattr(shadow.redis_db.r, 'eval', MagicMock(side_effect=RuntimeError(SENTINEL)))
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
        assert rid == hashlib.sha256(f"{record['lane']}|synthetic-conv|{content_sha}".encode()).hexdigest()[:32]
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


def test_store_adds_60_day_expiry_without_plaintext_or_client_reads():
    client = MagicMock()
    store.write_jev_shadow('user', 'hash-id', {'lane': 'owner', 'p_user': 0.91}, firestore_client=client)
    ref = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    record = ref.set.call_args.args[0]
    assert record['expire_at'] - record['created_at'] == timedelta(days=60)
    client.collection.assert_called_once_with('users')
    assert ref.get.call_count == 0
    assert ref.set.call_args.kwargs == {'timeout': 2.5}


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
