"""Merge jobs that hit a destructive-operation fence defer instead of burning retries.

Prod 2026-10-13/14: explicit memory deletion held one account's gate for 1–4 min
while 55–65 per-file merge tasks for a conversation retried inside that window,
returned 500 four times each, and ended marked merge_failed.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import routers.sync as routers_sync
from utils import cloud_tasks


def _fence():
    from database.legal_holds import DestructiveOperationInProgress

    return DestructiveOperationInProgress('external data write blocked by destructive operation')


def _conversation():
    return {'id': 'conv-1', 'deleted': False, 'audio_files': [{'id': 'f1', 'chunk_timestamps': [100.0]}]}


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def _common_patches(stack_build, mock_enqueue, mock_unavailable, mock_unavailable_v2, max_attempts=5):
    return [
        patch.object(routers_sync, 'try_acquire_job_run_lock', return_value='token-1'),
        patch.object(routers_sync, 'release_job_run_lock'),
        patch.object(routers_sync, 'should_skip_background_account_mutation', return_value=False),
        patch.object(routers_sync.conversations_db, 'get_conversation', return_value=_conversation()),
        patch.object(routers_sync, 'get_playback_artifact_signed_url', return_value=None),
        patch.object(routers_sync, 'get_conversation_playback_signed_url', return_value=None),
        patch.object(routers_sync, 'compute_audio_files_fingerprint', return_value='fp-1'),
        patch.object(routers_sync.playback_build, 'get_conversation_playback_manifest', return_value=None),
        patch.object(routers_sync, 'enqueue_audio_merge_job_deferred', mock_enqueue),
        patch.object(routers_sync, 'mark_playback_unavailable', mock_unavailable),
        patch.object(routers_sync, 'mark_conversation_playback_unavailable', mock_unavailable_v2),
        patch.object(routers_sync, 'get_sync_tasks_max_attempts', return_value=max_attempts),
        *stack_build,
    ]


async def _run(patches, coro_factory):
    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return await coro_factory()


V1 = {'uid': 'user-1', 'conversation_id': 'conv-1', 'audio_file_id': 'f1', 'timestamps': [100.0]}
V2 = {'schema_version': 2, 'uid': 'user-1', 'conversation_id': 'conv-1', 'fingerprint': 'fp-1'}


@pytest.mark.anyio
@pytest.mark.parametrize('stage', ['build', 'upload'])
async def test_v1_fence_defers_with_delayed_reenqueue(stage):
    enqueue, unavailable, unavailable_v2 = MagicMock(), MagicMock(), MagicMock()
    build = MagicMock(side_effect=_fence()) if stage == 'build' else MagicMock(return_value=b'mp3')
    upload = MagicMock(side_effect=_fence())
    patches = _common_patches(
        [
            patch.object(routers_sync.sync_playback, 'build_playback_artifact', build),
            patch.object(routers_sync, 'upload_playback_artifact', upload),
        ],
        enqueue,
        unavailable,
        unavailable_v2,
    )
    resp = await _run(patches, lambda: routers_sync.run_audio_merge_job(_FakeRequest(dict(V1)), task_retry_count=0))

    assert resp.status_code == 200
    assert b'"status":"deferred"' in resp.body
    (payload, delay), _ = enqueue.call_args
    assert payload['destructive_deferrals'] == 1 and delay == 60
    unavailable.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize('stage', ['build', 'upload'])
async def test_v2_fence_defers_even_on_final_attempt(stage):
    """The final queue attempt must not mark merge_failed while deferrals remain."""
    enqueue, unavailable, unavailable_v2 = MagicMock(), MagicMock(), MagicMock()
    build = (
        MagicMock(side_effect=_fence())
        if stage == 'build'
        else MagicMock(return_value=(b'mp3', [{'len': 1.0, 'wall_offset': 0.0}]))
    )
    patches = _common_patches(
        [
            patch.object(routers_sync.playback_build, 'build_conversation_playback_artifact', build),
            patch.object(
                routers_sync.playback_build, 'upload_conversation_playback_artifact', MagicMock(side_effect=_fence())
            ),
            patch.object(routers_sync.conversations_db, 'update_conversation', MagicMock()),
        ],
        enqueue,
        unavailable,
        unavailable_v2,
        max_attempts=1,
    )
    payload = {**V2, 'destructive_deferrals': 2}
    resp = await _run(patches, lambda: routers_sync._run_conversation_merge_job(payload, task_retry_count=0))

    assert resp.status_code == 200
    assert b'"status":"deferred"' in resp.body
    (sent, delay), _ = enqueue.call_args
    assert sent['destructive_deferrals'] == 3 and delay == 240
    unavailable_v2.assert_not_called()


@pytest.mark.anyio
async def test_exhausted_deferrals_fall_back_to_existing_retry():
    enqueue, unavailable, unavailable_v2 = MagicMock(), MagicMock(), MagicMock()
    patches = _common_patches(
        [
            patch.object(routers_sync.sync_playback, 'build_playback_artifact', MagicMock(side_effect=_fence())),
        ],
        enqueue,
        unavailable,
        unavailable_v2,
    )
    payload = {**V1, 'destructive_deferrals': routers_sync.AUDIO_MERGE_DESTRUCTIVE_DEFERRALS_MAX}
    resp = await _run(patches, lambda: routers_sync.run_audio_merge_job(_FakeRequest(payload), task_retry_count=0))

    assert resp.status_code == 500
    assert b'"status":"retry"' in resp.body
    enqueue.assert_not_called()


@pytest.mark.anyio
async def test_reenqueue_failure_keeps_existing_retry():
    enqueue = MagicMock(side_effect=RuntimeError('tasks unavailable'))
    patches = _common_patches(
        [
            patch.object(routers_sync.sync_playback, 'build_playback_artifact', MagicMock(side_effect=_fence())),
        ],
        enqueue,
        MagicMock(),
        MagicMock(),
    )
    resp = await _run(patches, lambda: routers_sync.run_audio_merge_job(_FakeRequest(dict(V1)), task_retry_count=0))

    assert resp.status_code == 500
    assert b'"status":"retry"' in resp.body


@pytest.mark.anyio
async def test_other_errors_keep_existing_retry():
    enqueue = MagicMock()
    patches = _common_patches(
        [
            patch.object(
                routers_sync.sync_playback, 'build_playback_artifact', MagicMock(side_effect=TimeoutError('gcs'))
            ),
        ],
        enqueue,
        MagicMock(),
        MagicMock(),
    )
    resp = await _run(patches, lambda: routers_sync.run_audio_merge_job(_FakeRequest(dict(V1)), task_retry_count=0))

    assert resp.status_code == 500
    enqueue.assert_not_called()


def test_deferred_task_name_and_schedule(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(cloud_tasks.time, 'time', lambda: 1000.0)
    monkeypatch.setenv('AUDIO_MERGE_TASKS_QUEUE', 'audio-merge')

    cloud_tasks.enqueue_audio_merge_job_deferred({**V2, 'destructive_deferrals': 2}, 240)
    cloud_tasks.enqueue_audio_merge_job_deferred({**V1, 'destructive_deferrals': 1}, 60)

    assert calls[0][0][2] == 'amc-conv-1-fp-1-dd2' and calls[0][1]['schedule_at'] == 1240
    assert calls[1][0][2] == 'am-conv-1-f1-dd1' and calls[1][1]['schedule_at'] == 1060
