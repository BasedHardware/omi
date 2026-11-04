"""PL-057/072/086: retained speech, privacy cancellation and paced admission.

Run the same production scheduler/recovery protocol on the reference simulator,
old Firestore store and new Postgres store. Require every backend when claiming
parity: OMI_REQUIRE_STORE_BACKENDS=all. Only vendor, VAD, metering and artifact
IO are synthetic. Postgres customer tables are the existing harness seam, not
proof of the serving cross-database privacy bridge or physical audio erasure.
"""

from __future__ import annotations

from dataclasses import asdict
import io
from unittest.mock import Mock, call
import wave

import pytest

from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import quarantine_recovery
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem, WorkResult
from utils.batch_pipeline.scheduler import Scheduler
from utils.stt import local_vad

pytestmark = pytest.mark.integration
T0 = 1000.0
DURATION = 4


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0' * (DURATION * 32000))
    return output.getvalue()


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    owner = store_backend.seed_user('recovery')
    store_backend.seed_user('unrelated')
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', owner)
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setattr(quarantine_recovery, 'sync_allowed', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(quarantine_recovery, 'metered', lambda *_args: None)
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', lambda _: [{'start': 0, 'end': 1}])
    return store_backend


def item(h, segment='speech', owner='recovery'):
    return WorkItem(segment, h.uid(owner), T0, f'gs://synthetic/{segment}#17', DURATION, Priority.FRESH)


def job(h, segment='speech'):
    return h.store.run(lambda tx: tx.get('jobs', segment))


def held(h):
    work = item(h)
    queue = Scheduler(h.store)
    assert queue.enqueue(work, T0)
    (lease,) = queue.pull(T0)
    assert queue.fail(work.segment_id, lease.token, T0 + 1, quarantine=True, measured_held_vad_speech_seconds=1)
    binding = ProjectionBinding(work.owner_id, 'upload', 'content', (work.segment_id,))

    def bind(tx):
        current = tx.get('jobs', work.segment_id)
        tx.put('jobs', work.segment_id, {**current, 'projection_binding': asdict(binding)})
        tx.put(
            'content',
            f'{work.owner_id}/{binding.content_id}',
            {
                'dispatch_protocol': 'batch_v1',
                'status': 'processing',
                'job_id': binding.job_id,
                'batch_pipeline': {'protocol_version': 1, 'namespace': h.namespace, 'segment_ids': [work.segment_id]},
            },
        )

    h.store.run(bind)
    return work


def coordinator(h, *, provider=None):
    artifacts = Mock()
    artifacts.fetch_audio.return_value = wav_bytes()
    artifacts.find_recovery_result.return_value = None
    artifacts.persist_recovery_result.return_value = 'gs://synthetic/result#18'
    provider = provider or Mock(side_effect=RuntimeError('synthetic vendor credit unavailable'))
    second = Mock(side_effect=AssertionError('provider failure is not an empty-recognition receipt'))
    recovery = quarantine_recovery.QuarantineRecovery(
        h.store, artifacts, stt=provider, second_stt=second, clock=lambda: T0 + 2
    )
    return recovery, artifacts, provider, second


@pytest.mark.parametrize(
    'error', [RuntimeError('synthetic vendor credit unavailable'), TimeoutError('uncertain reply')]
)
def test_pl057_provider_failure_retains_speech_and_never_replays_paid_intent(h, error):
    work = held(h)
    recovery, artifacts, provider, second = coordinator(h, provider=Mock(side_effect=error))
    assert recovery.recover(work.segment_id, work.owner_id) == 'failed_held'
    failed = job(h)
    assert (failed['state'], failed['recovery_state']) == ('quarantined', 'failed_held')
    assert (failed['audio_uri'], failed['capture_at'], failed['duration_seconds']) == (
        work.audio_uri,
        work.capture_at,
        work.duration_seconds,
    )
    assert failed['recovery']['failure'] == {'stage': 'provider', 'reason': 'operation_failed'}
    assert failed['recovery']['started_at'] == T0 + 2 and failed['recovery']['token']
    assert failed['measured_held_vad_speech_seconds'] == 1
    assert not failed.get('result') and not failed['merge_pending']
    assert h.store.run(lambda tx: tx.get('results', work.segment_id)) == {}
    for _ in range(3):
        # Rebuild the coordinator to exclude a process-local dedupe cache.
        restarted, retry_artifacts, _, _ = coordinator(h, provider=provider)
        assert restarted.recover(work.segment_id, work.owner_id) == 'held'
        assert retry_artifacts.method_calls == []
    assert job(h) == failed
    provider.assert_called_once()
    second.assert_not_called()
    assert artifacts.method_calls == [call.fetch_audio(provider.call_args.args[0])]


def test_pl057_lost_result_ack_reconciles_same_object_without_a_second_paid_call(h):
    work = held(h)
    payload = {'outcome': 'success', 'speech_seconds': 1.0, 'speech_spans': [{'start': 0, 'end': 1}]}
    recovery, artifacts, provider, second = coordinator(h, provider=Mock(return_value=payload))
    uri = 'gs://synthetic/result#18'
    artifacts.persist_recovery_result.side_effect = TimeoutError('synthetic lost storage acknowledgment')
    assert recovery.recover(work.segment_id, work.owner_id) == 'result_held'
    running = job(h)
    assert running['recovery_state'] == 'running' and running['audio_uri'] == work.audio_uri
    # The write landed but its acknowledgment did not. A new process finds it
    # by the original intent token and settles through the real transaction.
    restarted, reconciled, _, _ = coordinator(h, provider=provider)
    reconciled.find_recovery_result.return_value = uri
    reconciled.load_result.return_value = payload
    assert restarted.recover(work.segment_id, work.owner_id) == 'reconciled'
    complete = job(h)
    assert complete['recovery']['token'] == running['recovery']['token']
    assert complete['recovery_state'] == 'recovered' and complete['result']['result_uri'] == uri
    assert complete['audio_uri'] == work.audio_uri
    provider.assert_called_once()
    second.assert_not_called()
    reconciled.fetch_audio.assert_not_called()
    reconciled.persist_recovery_result.assert_not_called()


@pytest.mark.parametrize('phase', ['prepared', 'after_download'])
def test_pl072_account_deletion_cancels_recovery_before_paid_work_or_upload(h, phase, request):
    if h.name in {'sim', 'postgres'}:
        request.node.add_marker(
            pytest.mark.xfail(
                strict=True,
                raises=AttributeError,
                reason='https://github.com/BasedHardware/omi/issues/23761: cancellation bypasses Store',
            )
        )
    work = held(h)
    recovery, artifacts, provider, second = coordinator(h)
    prepared = recovery.protocol.prepare(work.segment_id, work.owner_id, T0 + 1)
    assert prepared and prepared['recovery_state'] == 'prepared'
    token = prepared['recovery']['token']
    if phase == 'prepared':
        h.customer.delete_account(work.owner_id)
    else:

        def download(_item):
            h.customer.delete_account(work.owner_id)
            return wav_bytes()

        artifacts.fetch_audio.side_effect = download
    try:
        outcome = recovery.recover(work.segment_id, work.owner_id)
    except AttributeError as error:
        # Do not accept a different AttributeError as this known migration gap.
        expected = {
            'sim': "'NoneType' object has no attribute 'collection'",
            'postgres': "'PostgresStore' object has no attribute 'client'",
        }
        assert str(error) == expected[h.name]
        raise
    finally:
        # These safety assertions run even on the narrowly expected failure.
        provider.assert_not_called()
        second.assert_not_called()
        artifacts.persist_recovery_result.assert_not_called()
    assert outcome == 'cancelled'
    cancelled = job(h)
    assert cancelled['recovery_state'] == 'cancelled' and cancelled['recovery']['token'] == token
    assert not cancelled.get('result') and not cancelled['merge_pending']
    for _ in range(2):
        restarted, retry_artifacts, _, _ = coordinator(h, provider=provider)
        assert restarted.recover(work.segment_id, work.owner_id) == 'cancelled'
        retry_artifacts.assert_not_called()
        assert retry_artifacts.method_calls == []
    assert job(h) == cancelled
    provider.assert_not_called()
    second.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()
    assert artifacts.fetch_audio.call_count == (phase == 'after_download')
    # The deletion marker is scoped to its owner; unrelated work still runs.
    queue = Scheduler(h.store)
    assert queue.enqueue(item(h, 'unrelated', 'unrelated'), T0 + 3)
    assert queue.pull(T0 + 3)[0].item.owner_id == h.uid('unrelated')


def test_pl086_refusal_backoff_survives_restart_and_completion_resets_it(h):
    work = item(h)
    queue = Scheduler(h.store)
    assert queue.enqueue(work, T0)
    now = T0
    for streak, delay in enumerate((30, 60, 120, 240, 300, 300), 1):
        (lease,) = queue.pull(now)

        def earlier_allow(tx):
            current = tx.get('jobs', work.segment_id)
            tx.put('jobs', work.segment_id, {**current, 'compute_decision': {'outcome': 'allowed', 'at': now}})

        h.store.run(earlier_allow)
        before = job(h)
        assert not queue.defer(work.segment_id, 'stale', now, admission_refused=True)
        assert job(h) == before
        assert queue.defer(work.segment_id, lease.token, now, admission_refused=True)
        waiting = job(h)
        assert waiting['available_at'] == now + delay and waiting['attempt'] == 0
        assert waiting['admission_refusals'] == min(streak, 5)
        assert waiting['audio_uri'] == work.audio_uri and not waiting['token']
        assert 'compute_decision' not in waiting and 'retry_started_at' not in waiting
        queue = Scheduler(h.store)
        queue.recover(now + delay - 1)
        assert queue.pull(now + delay - 1) == []
        now += delay
        queue.recover(now)
    (lease,) = queue.pull(now)
    assert job(h)['admission_refusals'] == 5  # a fresh authorization is not completion
    assert queue.complete(WorkResult(work.segment_id, 'gs://synthetic/result'), lease.token, now)
    assert 'admission_refusals' not in job(h)


@pytest.mark.parametrize('delay,expected', [(3600, 3600), (86400, 86400), (100000, 86400)])
def test_pl086_policy_wait_survives_restart_without_blocking_same_owner(h, delay, expected):
    queue = Scheduler(h.store)
    work = item(h)
    assert queue.enqueue(work, T0)
    (lease,) = queue.pull(T0)
    assert queue.enqueue(item(h, 'sibling'), T0)
    assert queue.defer(
        work.segment_id, lease.token, T0, delay, held_reason='allowance_exhausted', admission_refused=True
    )
    waiting = job(h)
    assert waiting['available_at'] == T0 + expected and waiting['attempt'] == 0
    assert waiting['compute_decision'] == {'reason': 'allowance_exhausted', 'outcome': 'held', 'at': T0}
    restarted = Scheduler(h.store)
    (sibling,) = restarted.pull(T0 + 1)
    assert sibling.item.segment_id == 'sibling'
    assert restarted.complete(WorkResult('sibling', 'gs://synthetic/sibling-result'), sibling.token, T0 + 2)
    restarted.recover(T0 + expected - 1)
    assert restarted.pull(T0 + expected - 1) == []
    restarted.recover(T0 + expected)
    assert restarted.pull(T0 + expected)[0].item.segment_id == work.segment_id
