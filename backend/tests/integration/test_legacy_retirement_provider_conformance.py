"""C8 custody on each real Store; synthetic vendor/VAD/artifacts, no ASR quality claim."""

from dataclasses import replace

import pytest

from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from database.outbox import EnqueueResult
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.provider_stt import ProviderSttStage, provider_enqueue, resolve_route
from utils.batch_pipeline.scheduler import Scheduler

pytestmark = pytest.mark.integration


class Artifacts:
    def __init__(self):
        self.results = {}

    def fetch_audio(self, item):
        return b'synthetic'

    def persist_recovery_result(self, item, payload, token):
        uri = 'gs://synthetic/results/' + token
        self.results[token] = uri
        return uri

    def find_recovery_result(self, item, token):
        return self.results.get(token)


class Outbox:
    def __init__(self):
        self.calls = 0

    def enqueue(self, dedupe_key, owner_id, payload, available_at, *, tx=None, now):
        assert tx is not None
        self.calls += 1
        return EnqueueResult(dedupe_key, False, 'synthetic')


@pytest.mark.parametrize('byok', [False, True])
@pytest.mark.parametrize('vendor_fails', [False, True])
def test_provider_custody_merges_once_and_replay_never_calls_vendor(store_backend, byok, vendor_fails):
    h = store_backend
    owner = h.seed_user('o')
    h.customer.add_conversation(owner, 'synthetic-conversation')
    work = WorkItem(
        'synthetic',
        owner,
        10.0,
        'gs://synthetic/audio',
        5.0,
        Priority.FRESH,
        conversation_id='synthetic-conversation',
        privacy_generation=0,
    )
    route = resolve_route('ja', byok=byok)
    policy = replace(
        BatchUnitPolicy(batch_enabled=True, batch_percent=100),
        stt_route=route.stt_route,
        provider_reason=route.provider_reason,
        provider_service=route.provider_service,
    )
    binding = ProjectionBinding(owner, 'bp_synthetic', 'synthetic', (work.segment_id,), language='ja')
    outbox = Outbox()

    def submit():
        return admit(
            h.store,
            [work],
            binding,
            100.0,
            namespace=h.namespace,
            policy=policy,
            enqueue=provider_enqueue(route, outbox, {}),
        )

    assert submit()['outcome'] == 'batch'
    assert submit()['outcome'] == 'batch'
    assert outbox.calls == 1
    assert Scheduler(h.store).pull(150.0) == []
    calls = []
    artifacts = Artifacts()

    def stt(item, language, inspected, *, service):
        calls.append(service)
        if vendor_fails:
            raise RuntimeError('synthetic provider failure')
        return {
            'audio_seconds': 5.0,
            'speech_seconds': 1.0,
            'speech_spans': [{'start': 0.5, 'end': 1.5}],
            'words': [{'word': 'synthetic', 'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_00'}],
            'diarization': {'turns': []},
            'words_provider': service,
            'language': language,
            'recovery_version': 1,
        }

    runner = ProviderSttStage(
        h.store,
        artifacts,
        stt=stt,
        allowed=lambda *_: True,
        inspect=lambda *_: (b'\0\0' * 80000, 5.0, [{'start': 0.5, 'end': 1.5}]),
        clock=lambda: 200.0,
    )
    assert runner.run(work.segment_id).outcome == 'done'
    assert runner.run(work.segment_id).outcome == 'done'
    assert calls == ['modulate']
    row = h.store.run(lambda tx: tx.get('jobs', work.segment_id))
    assert row['provider_intent']['settled_at'] == 200.0
    assert row['policy']['provider_reason'] == ('byok' if byok else 'unsupported_language')
    if vendor_fails:
        assert row['state'] == 'quarantined' and row['recovery_state'] == 'failed_held'
        assert row['audio_uri'] == work.audio_uri
        assert not row.get('result')
        return
    merge = OrderedMerge(h.store)
    assert merge.commit_next(owner, 201.0)['segment_id'] == work.segment_id
    assert merge.commit_next(owner, 202.0) is None
    assert h.store.run(lambda tx: tx.get('jobs', work.segment_id))['state'] == 'committed'
