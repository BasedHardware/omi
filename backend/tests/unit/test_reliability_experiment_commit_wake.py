"""Experiment ``commit_wake``: a GPU commit tells the serving backend which owner to project.

The GPU pump commits a result but cannot write it into the conversation; the serving backend finds
the committed row on its next sweep. Off for an owner (the default) that stays exactly so: the pump's
hook drops the owner, the worker sends nothing and builds neither a client nor a thread, and the
endpoint accepts nothing for that owner. On for an owner, the pump's ``on_committed`` hook queues the
owner id, one background thread posts it to ``/v2/batch-pipeline/commit-wake``, and the endpoint asks
for one targeted walk of that owner's log. The wake is a hint: every failure is
swallowed and the sweep remains the backstop.
"""

import asyncio
import json
import threading

import pytest
from fastapi import HTTPException

from config import reliability_experiments
from routers import batch_pipeline as routes
from utils.batch_pipeline import commit_wake
from utils.batch_pipeline.compute_client import ComputeClient

EXPERIMENT = 'commit_wake'
SERVING = 'https://serving.test'


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


def test_the_experiment_is_registered_and_off_by_default(off):
    assert EXPERIMENT in reliability_experiments.EXPERIMENTS
    assert commit_wake.enabled('owner-a') is False
    assert commit_wake.enabled(None) is False


# --- Worker side ---


def test_off_the_hook_sends_nothing_and_builds_neither_client_nor_thread(off, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_RECOVERY_API_URL', SERVING)
    from utils.batch_pipeline import compute_client

    monkeypatch.setattr(compute_client, 'shadow_from_env', lambda: pytest.fail('no client while off'))
    hook = commit_wake.sender_from_env()
    hook({'owner_id': 'owner-a', 'segment_id': 's1'})
    assert hook._thread is None and hook._pending == {}
    assert hook.flush() == 0


def test_the_hook_decides_per_owner(off, monkeypatch):
    monkeypatch.setattr(reliability_experiments, '_resolver', lambda name, uid: name == EXPERIMENT and uid == 'in')
    calls = []
    hook = commit_wake.CommitWakeSender(lambda owners: calls.append(list(owners)) or len(owners), start_thread=False)
    hook({'owner_id': 'in'})
    hook({'owner_id': 'out'})
    assert hook.flush() == 1 and calls == [['in']]


def test_without_a_serving_target_the_pump_gets_no_hook(on, monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_SHADOW_RECOVERY_API_URL', raising=False)
    assert commit_wake.sender_from_env() is None


def test_on_the_hook_posts_to_the_serving_backend(on, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_RECOVERY_API_URL', SERVING)
    sent = threading.Event()
    calls = []

    class Client:
        def commit_wake(self, owners):
            calls.append(list(owners))
            sent.set()
            return len(owners)

    from utils.batch_pipeline import compute_client

    monkeypatch.setattr(compute_client, 'shadow_from_env', Client)
    hook = commit_wake.sender_from_env()
    assert isinstance(hook, commit_wake.CommitWakeSender)
    hook({'owner_id': 'owner-a', 'segment_id': 's1'})
    assert sent.wait(5), 'the background thread sends without being asked'
    assert calls == [['owner-a']]


def test_an_owner_waits_once_and_calls_are_bounded(on):
    calls = []
    hook = commit_wake.CommitWakeSender(lambda owners: calls.append(list(owners)) or len(owners), start_thread=False)
    for index in range(40):
        hook({'owner_id': f'owner-{index}'})
        hook({'owner_id': f'owner-{index}'})  # a second commit of the same owner before the call
    assert hook.flush() == 40
    assert [len(call) for call in calls] == [32, 8]
    assert calls[0][:2] == ['owner-0', 'owner-1'], 'arrival order'
    assert hook.flush() == 0, 'nothing is sent twice'


def test_entries_without_a_usable_owner_and_overflow_are_dropped(on):
    calls = []
    hook = commit_wake.CommitWakeSender(lambda owners: calls.append(list(owners)) or len(owners), start_thread=False)
    for entry in ({}, {'owner_id': None}, {'owner_id': ''}, {'owner_id': 'x' * 129}, 'not a row'):
        hook(entry)
    assert hook.flush() == 0 and calls == []
    for index in range(commit_wake.MAX_PENDING_OWNERS + 50):
        hook({'owner_id': f'owner-{index}'})
    assert hook.flush() == commit_wake.MAX_PENDING_OWNERS


def test_a_failed_call_is_swallowed_and_later_owners_still_go(on, caplog):
    calls = []

    def send(owners):
        calls.append(list(owners))
        if len(calls) == 1:
            raise TimeoutError('serving backend busy')
        return len(owners)

    hook = commit_wake.CommitWakeSender(send, start_thread=False)
    hook({'owner_id': 'owner-a'})
    assert hook.flush() == 0, 'the failed owner is dropped: the sweep finds its row'
    hook({'owner_id': 'owner-b'})
    assert hook.flush() == 1
    assert calls == [['owner-a'], ['owner-b']]
    assert 'owner-a' not in caplog.text and 'owner-b' not in caplog.text, 'no identity in the log'


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return self.body


def test_the_client_sends_owner_ids_with_the_worker_token():
    seen = {}

    def send(request, timeout):
        seen.update(url=request.full_url, body=json.loads(request.data), auth=request.get_header('Authorization'))
        seen['timeout'] = timeout
        return Response(b'{"accepted": 2}')

    client = ComputeClient(SERVING, SERVING, 'dev', token=lambda: 'worker-token', send=send)
    assert client.commit_wake(['owner-a', 'owner-b']) == 2
    assert seen == {
        'url': SERVING + '/v2/batch-pipeline/commit-wake',
        'body': {'stage': 'dev', 'owner_ids': ['owner-a', 'owner-b']},
        'auth': 'Bearer worker-token',
        'timeout': 3,
    }


@pytest.mark.parametrize('body', [b'[]', b'{"accepted": "2"}', b'{"accepted": 3}', b'{"accepted": -1}', b'{}'])
def test_the_client_refuses_a_receipt_it_cannot_read(body):
    client = ComputeClient(SERVING, SERVING, 'dev', token=lambda: 't', send=lambda request, timeout: Response(body))
    with pytest.raises(ValueError):
        client.commit_wake(['owner-a', 'owner-b'])


# --- Serving side ---


class Wakes:
    def __init__(self):
        self.requested = []

    def request(self, owner_id):
        self.requested.append(owner_id)
        return True


def test_off_the_endpoint_accepts_nothing_and_starts_nothing(off, monkeypatch):
    wakes = Wakes()
    monkeypatch.setattr(commit_wake, 'wakes', lambda: wakes)
    body = routes.CommitWakeRequest(stage='dev', owner_ids=['owner-a'])
    assert asyncio.run(routes.commit_wake(body)) == {'accepted': 0}
    assert wakes.requested == []


def test_on_the_endpoint_asks_for_one_walk_per_owner(on, monkeypatch):
    wakes = Wakes()
    monkeypatch.setattr(commit_wake, 'wakes', lambda: wakes)
    body = routes.CommitWakeRequest(stage='dev', owner_ids=['owner-a', 'owner-b', 'owner-a', 'x' * 129])
    assert asyncio.run(routes.commit_wake(body)) == {'accepted': 2}
    assert wakes.requested == ['owner-a', 'owner-b']


def test_on_a_wake_for_another_stage_is_refused(on, monkeypatch):
    wakes = Wakes()
    monkeypatch.setattr(commit_wake, 'wakes', lambda: wakes)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(routes.commit_wake(routes.CommitWakeRequest(stage='prod', owner_ids=['owner-a'])))
    assert refused.value.status_code == 409
    assert wakes.requested == []


def test_the_request_is_bounded():
    with pytest.raises(ValueError):
        routes.CommitWakeRequest(stage='dev', owner_ids=[])
    with pytest.raises(ValueError):
        routes.CommitWakeRequest(stage='dev', owner_ids=['o'] * 33)
    with pytest.raises(ValueError):
        routes.CommitWakeRequest(stage='dev', owner_ids=['owner-a'], extra=1)


def test_the_endpoint_is_authenticated_as_the_worker_on_the_serving_audience(monkeypatch):
    from utils import cloud_tasks

    seen = {}

    def verify(request, *, audience, invoker_sa, log_failure):
        seen.update(audience=audience, invoker=invoker_sa)
        return 1

    monkeypatch.setattr(cloud_tasks, 'verify_configured_cloud_tasks_oidc', verify)
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_AUDIENCE', 'https://admission.test')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', SERVING)
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', 'worker@test')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'tasks@test')

    class Url:
        path = '/v2/batch-pipeline/commit-wake'

    class Request:
        url = Url()

    routes.verify_worker(Request())
    assert seen == {'audience': SERVING, 'invoker': 'worker@test'}


def test_a_wake_walks_at_once_and_a_wake_during_the_walk_adds_exactly_one(monkeypatch):
    walks = []

    async def scenario():
        gate = asyncio.Event()

        async def walk(owner_id):
            walks.append(owner_id)
            if len(walks) == 1:
                await gate.wait()

        monkeypatch.setattr(commit_wake, '_project_owner', walk)
        monkeypatch.setattr(commit_wake, '_wakes', None)
        coalescer = commit_wake.wakes()
        coalescer.request('owner-a')
        await asyncio.sleep(0.05)
        assert walks == ['owner-a'], 'no settle delay before the first walk'
        coalescer.request('owner-a')
        coalescer.request('owner-a')
        gate.set()
        for _ in range(100):
            if coalescer.pending() == 0:
                break
            await asyncio.sleep(0.01)
        assert coalescer.pending() == 0

    asyncio.run(scenario())
    monkeypatch.setattr(commit_wake, '_wakes', None)
    assert walks == ['owner-a', 'owner-a'], 'no head-wait round, one follow-up for the wakes that arrived meanwhile'
