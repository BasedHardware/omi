"""Late identity repair eligibility and process-wide admission at pusher drain."""

import asyncio
import threading
import pytest
from types import SimpleNamespace
from datetime import datetime, timezone

from tests.unit.test_pusher_audio_timeline import env, FakeWebSocket, _conversation, _audio, _run, RATE
from routers import pusher
from utils import executors
from utils.conversations import speaker_resolution as stage
from utils.conversations import speaker_identity_retry as retry


@pytest.fixture(autouse=True)
def manifest_committed(env, monkeypatch):
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', ())
    monkeypatch.setattr(
        pusher.conversations_db, 'create_audio_files_from_chunks', lambda *a: [SimpleNamespace(model_dump=lambda: {})]
    )
    monkeypatch.setattr(pusher.conversations_db, 'update_conversation', lambda *a: True)
    monkeypatch.setattr(pusher, 'schedule_person_voice_learning_retry', lambda *a: None)


def _row(cid):
    return {
        'id': cid,
        'status': 'completed' if cid >= 'c08' else 'in_progress',
        'private_cloud_sync_enabled': True,
        'updated_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


async def test_late_candidates_are_selected_after_eligibility(env, monkeypatch):
    repaired = []

    def repair(uid, cid, **kwargs):
        if _row(cid)['status'] == 'completed':
            repaired.append(cid)
        return False

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda uid, cid: _row(cid))
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', repair)
    monkeypatch.setattr(pusher, 'refresh_completed_speaker_identity', repair, raising=False)
    frames = []
    for i in range(10):
        frames.extend([_conversation(f'c{i:02}'), _audio(100.0 + i * 2, b'\x01\x00' * RATE)])
    await _run(FakeWebSocket(frames))
    await asyncio.gather(*list(executors._background_tasks))
    assert repaired == ['c08', 'c09']


async def test_process_admits_only_two_late_jobs_even_while_threads_block(env, monkeypatch):
    release = threading.Event()
    entered = threading.Event()

    def repair(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return False

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda uid, cid: _row(cid))
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', repair)
    monkeypatch.setattr(pusher, 'refresh_completed_speaker_identity', repair, raising=False)
    try:
        for i in range(3):
            await _run(FakeWebSocket([_conversation('c08'), _audio(100.0 + i * 2, b'\x01\x00' * RATE)]))
        await asyncio.sleep(0)
        assert len(executors._background_tasks) <= 2
    finally:
        release.set()
        await asyncio.gather(*list(executors._background_tasks))


async def test_cancelling_waiters_does_not_free_slots_before_threads_finish(env, monkeypatch):
    from utils.conversations import speaker_identity_retry as retry

    release = threading.Event()
    futures = []
    submit = retry.submit_with_context

    def tracked_submit(*a, **kw):
        future = submit(*a, **kw)
        futures.append(future)
        return future

    def repair(*a, **kw):
        assert release.wait(10)
        return False

    monkeypatch.setattr(retry, 'submit_with_context', tracked_submit)
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda uid, cid: _row(cid))
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', repair)
    try:
        assert retry.schedule_completed_identity_retries('u', ['c08'])
        assert retry.schedule_completed_identity_retries('u', ['c09'])
        await asyncio.sleep(0)
        tasks = list(executors._background_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert not retry.schedule_completed_identity_retries('u', ['c10'])
    finally:
        release.set()
        await asyncio.gather(*[asyncio.wrap_future(future) for future in futures])


from tests.unit.test_conversation_speaker_resolution_stage import (
    env as resolution_env,
    empty_manual_receipt,
    _span_flags,
    _install_audio,
    _capture_shifted_conversation,
)


def test_late_pass_caps_embedding_attempts_and_does_not_repair_enrollment(resolution_env, monkeypatch):
    _span_flags(monkeypatch)
    _install_audio(monkeypatch, [0] * 40, offset=180.0)
    _, diarizer = resolution_env
    conversation = _capture_shifted_conversation([0] * 40)
    raw = conversation.model_dump()
    raw.update(status='completed', updated_at=conversation.created_at)
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda *a: raw)
    monkeypatch.setattr(stage.identity_updates_db, 'persist_speaker_resolution_if_current', lambda *a, **kw: True)
    repairs = []
    monkeypatch.setattr(stage, 'load_owner_embedding', lambda *a, **kw: repairs.append(kw['allow_audio_repair']))
    stage.refresh_completed_speaker_identity('u1', 'c1')
    assert diarizer.calls == 24
    assert repairs == [False]


def test_failed_late_calls_still_consume_the_eight_attempt_ceiling(monkeypatch):
    from utils.conversations import speaker_identity_retry as retry

    attempted = []
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda uid, cid: _row(cid))

    def fail(uid, cid, **kw):
        attempted.append(cid)
        raise RuntimeError('fixture unexpected failure')

    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', fail)
    retry._retry_batch('u', tuple(f'c{i:02}' for i in range(8, 28)))
    assert len(attempted) == 8
