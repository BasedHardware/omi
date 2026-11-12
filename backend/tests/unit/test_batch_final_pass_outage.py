"""Cloud Tasks acknowledge storage outages; durable rows retain recovery custody."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import ssl
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core import exceptions as api
import httpx
import pytest

from database.batch_final_pass_retry import MAX_ATTEMPTS
from tests.unit.fixtures.speaker_final_pass_retry import retry_state  # noqa: F401
from tests.unit.test_batch_final_pass import prod_shaped, UID, run_prod, batch_outcome_counts  # noqa: F401
from tests.unit.test_batch_final_pass_retry import ready, next_wake  # noqa: F401
from utils.conversations import final_pass_retry as retry, final_pass_pyannote as final
from utils.conversations.final_pass_dependencies import transient_cause
from utils.stt import diarization, vad_compaction


@pytest.mark.parametrize('edge', ['enrichment', 'sync'])
def test_claim_outage_is_acked_without_consuming_attempt_or_queue_hot_loop(ready, monkeypatch, edge):
    from routers import enrichment, sync

    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setattr(sync.uid_sequencer, 'production_fence_mode', lambda: sync.SyncLedgerFenceMode.LEGACY)
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    before_rows, before_wakes = deepcopy(ready.state.rows), len(ready.state.wakes)
    before_counts = batch_outcome_counts()
    original = ready.state.store.claim

    def unavailable(*args, **kwargs):
        raise api.ServiceUnavailable('PRIVATE provider content')

    monkeypatch.setattr(ready.state.store, 'claim', unavailable)
    app = FastAPI()
    module = enrichment if edge == 'enrichment' else sync
    app.include_router(module.router)
    dependency = enrichment.verify_enrichment_task if edge == 'enrichment' else sync.verify_cloud_tasks_oidc
    app.dependency_overrides[dependency] = lambda: 0
    with TestClient(app) as client:
        response = client.post(
            '/v2/enrichment/run' if edge == 'enrichment' else '/v2/sync-jobs/run',
            json={'kind': 'batch_final_pass', 'key': key, 'task_token': token},
        )
    assert response.status_code == 200
    assert response.json()['outcome'] == 'deferred_custody'
    assert response.json()['phase'] == 'claim'
    assert 'PRIVATE' not in response.text
    assert ready.state.rows == before_rows and ready.state.rows[key]['attempts'] == 0
    assert len(ready.state.wakes) == before_wakes  # No immediate requeue or model work.
    assert not ready.lane.gpu and not ready.writes
    assert batch_outcome_counts() == before_counts
    monkeypatch.setattr(ready.state.store, 'claim', original)
    ready.state.clock[0] = ready.state.rows[key]['repair_after'] + 1
    assert retry.sweep(now=ready.state.clock[0]) == 1
    assert retry.consume(key, token)['outcome'] == 'stale'
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert ready.state.rows[key]['attempts'] == 1
    assert sum(batch_outcome_counts().values()) - sum(before_counts.values()) == 1


@pytest.mark.parametrize('method', ['claim', 'settle', 'take_terminal'])
@pytest.mark.parametrize(
    'factory', [api.ServiceUnavailable, api.DeadlineExceeded, api.Aborted, api.InternalServerError]
)
def test_custody_outage_leaves_sweeper_obligation_without_counting_a_terminal(ready, monkeypatch, method, factory):
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    before, wakes = batch_outcome_counts(), len(ready.state.wakes)
    original = getattr(ready.state.store, method)

    def fail(*args, **kwargs):
        raise factory('PRIVATE')

    monkeypatch.setattr(ready.state.store, method, fail)
    result = retry.consume(key, token)
    assert result['outcome'] == 'deferred_custody'
    assert result['phase'] == ('terminal_report' if method == 'take_terminal' else method)
    assert len(ready.state.wakes) == wakes
    assert ready.state.rows[key]['attempts'] == (0 if method == 'claim' else 1)
    assert batch_outcome_counts() == before
    monkeypatch.setattr(ready.state.store, method, original)
    ready.state.clock[0] = ready.state.rows[key]['repair_after'] + 1
    assert retry.sweep(now=ready.state.clock[0]) == 1
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1
    assert len(ready.lane.gpu) == (2 if method == 'settle' else 1)
    assert 'repair_after' not in ready.state.rows[key]


def test_lost_terminal_settlement_reply_repairs_reporting_without_repeating_inference(ready, monkeypatch):
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    before = batch_outcome_counts()
    settle = ready.state.store.settle

    def lost_reply(*args, **kwargs):
        settle(*args, **kwargs)
        raise api.ServiceUnavailable('PRIVATE lost reply after commit')

    monkeypatch.setattr(ready.state.store, 'settle', lost_reply)
    assert retry.consume(key, token)['outcome'] == 'deferred_custody'
    row = ready.state.rows[key]
    assert row['outcome'] == 'success' and row['terminal_pending']
    assert not any(field in row for field in ('uid', 'conversation_id', 'dispatch'))
    assert len(ready.lane.gpu) == len(ready.writes) == 1
    assert batch_outcome_counts() == before
    monkeypatch.setattr(ready.state.store, 'settle', settle)
    ready.state.clock[0] = row['repair_after'] + 1
    assert retry.sweep(now=ready.state.clock[0]) == 1
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert len(ready.lane.gpu) == len(ready.writes) == 1
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


@pytest.mark.parametrize(
    'factory', [api.ServiceUnavailable, api.DeadlineExceeded, api.Aborted, api.InternalServerError]
)
def test_committed_terminal_report_with_lost_reply_is_eventually_counted_once(ready, monkeypatch, factory):
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    take = ready.state.store.take_terminal
    before = batch_outcome_counts()

    def lost_reply(*args, **kwargs):
        assert take(*args, **kwargs)
        raise factory('PRIVATE lost terminal-report reply after commit')

    monkeypatch.setattr(ready.state.store, 'take_terminal', lost_reply)
    assert retry.consume(key, token)['outcome'] == 'deferred_custody'
    assert len(ready.lane.gpu) == len(ready.writes) == 1
    monkeypatch.setattr(ready.state.store, 'take_terminal', take)
    ready.state.clock[0] += 2000
    retry.sweep(now=ready.state.clock[0])
    if ready.state.rows[key].get('terminal_pending'):
        key, token = next_wake(ready.state)
        retry.consume(key, token)
    assert retry.consume(key, token)['outcome'] == 'stale'
    retry.sweep(now=ready.state.clock[0] + 2000)
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1
    assert len(ready.lane.gpu) == len(ready.writes) == 1
    from utils.observability.speaker_retry_terminal import TERMINALS

    exported = [
        sample.value
        for family in TERMINALS.collect()
        for sample in family.samples
        if sample.name.endswith('_total') and sample.labels['outcome'] == 'success'
    ]
    assert exported == [1]  # Recovery exports the committed metric, not a second report.


def test_lost_claim_replies_cannot_reset_four_claim_cap(ready, monkeypatch):
    retry.enqueue(UID, ready.lane.conversation)
    claim = ready.state.store.claim

    def lost_reply(*args, **kwargs):
        claim(*args, **kwargs)
        raise api.ServiceUnavailable('PRIVATE')

    monkeypatch.setattr(ready.state.store, 'claim', lost_reply)
    before = batch_outcome_counts()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        key, token = next_wake(ready.state)
        assert retry.consume(key, token)['outcome'] == 'deferred_custody'
        assert ready.state.rows[key]['attempts'] == attempt
        ready.state.clock[0] = ready.state.rows[key]['repair_after'] + 1
        assert retry.sweep(now=ready.state.clock[0]) == 1
    monkeypatch.setattr(ready.state.store, 'claim', claim)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'skipped_retry_exhausted'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert not ready.lane.gpu and not ready.writes
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def test_duplicate_terminal_recovery_wakes_count_once_without_model_work(ready, monkeypatch):
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    state, claim = ready.state.store.claim(key, token, now=ready.state.clock[0])
    assert state == 'claimed'
    ready.state.store.settle(key, claim, 'success', now=ready.state.clock[0])
    take = ready.state.store.take_terminal
    barrier = threading.Barrier(2)

    def concurrent(*args):
        barrier.wait(timeout=2)
        return take(*args)

    monkeypatch.setattr(ready.state.store, 'take_terminal', concurrent)
    before = batch_outcome_counts()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: retry.consume(key, token), range(2)))
    assert {result['outcome'] for result in results} == {'success', 'stale'}
    assert not ready.lane.gpu and not ready.writes
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def tls_failure():
    tls = ssl.SSLCertVerificationError('PRIVATE certificate detail')
    core = httpx.ConnectError('PRIVATE nested transport')
    core.__cause__ = tls
    error = httpx.ConnectError('PRIVATE outer HTTPX wrapper')
    error.__cause__ = core
    return error


def test_wrapped_httpx_tls_is_permanent_even_under_another_wrapper():
    error = tls_failure()
    assert transient_cause(error) is None
    wrapper = RuntimeError('unit unavailable')
    wrapper.__cause__ = error
    assert transient_cause(wrapper) is None
    error.__context__ = error
    assert transient_cause(error) is None


def test_tls_is_not_immediately_retried_by_real_http_adapter(monkeypatch):
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'https://synthetic.invalid')
    calls = []

    def fail(*args, **kwargs):
        calls.append(True)
        raise tls_failure()

    monkeypatch.setattr(diarization.httpx, 'post', fail)
    with pytest.raises(httpx.ConnectError):
        diarization.HttpDiarizer('pyannote').diarize(b'\0\0', deadline=diarization.time.monotonic() + 10)
    assert len(calls) == 1


@pytest.mark.parametrize('status', [408, 429, 500, 502, 503, 504, 599, 400, 401, 403, 404, 409, 422, 499])
@pytest.mark.parametrize('attempt', ['initial', 'retry'])
def test_real_http_status_classification_after_immediate_retry(ready, monkeypatch, status, attempt):
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'https://synthetic.invalid')
    monkeypatch.setattr(vad_compaction, 'final_pass_vad_compaction_enabled', lambda: False)
    monkeypatch.setattr(final, 'diarize_with_speech_compaction', vad_compaction.diarize_with_speech_compaction)
    calls = []

    def response(*args, **kwargs):
        calls.append(True)
        return httpx.Response(status, request=httpx.Request('POST', 'https://synthetic.invalid'))

    monkeypatch.setattr(diarization.httpx, 'post', response)
    before = batch_outcome_counts()
    if attempt == 'initial':
        result = run_prod(ready.lane)
    else:
        retry.enqueue(UID, ready.lane.conversation)
        key, token = next_wake(ready.state)
        result = retry.consume(key, token)
        assert retry.consume(key, token)['outcome'] == 'stale'
    transient = status in (408, 429) or status >= 500
    assert result['outcome'] == ('deferred_transient' if transient else 'failed_batch_audio'), result
    assert len(calls) == (2 if transient else 1)
    assert not ready.writes
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == (0 if transient else 1)


@pytest.mark.parametrize('status', range(500, 600))
def test_all_5xx_statuses_are_transient(status):
    response = httpx.Response(status, request=httpx.Request('GET', 'https://synthetic.invalid'))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    assert transient_cause(caught.value) is caught.value
