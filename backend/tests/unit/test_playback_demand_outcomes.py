"""On-demand playback outcomes are counted so a failed build is visible next to built/exists.

Volume guards (attempts, queue depth, bucket ops) all fall when dispatch or
builds fail, so graduating PLAYBACK_ON_DEMAND_ENABLED needs a failure share.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.responses import JSONResponse

os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import routers.sync as routers_sync
from utils.sync.repeat_work_metrics import PLAYBACK_BUILDS


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _count(representation, outcome):
    return PLAYBACK_BUILDS.labels(representation, outcome)._value.get()


def _record(payload, response):
    asyncio.run(routers_sync._record_demand_playback_outcome(_FakeRequest(payload), response))


V2_DEMAND = {'schema_version': 2, 'uid': 'u', 'conversation_id': 'c', 'on_demand': True}
V1_DEMAND = {'uid': 'u', 'conversation_id': 'c', 'audio_file_id': 'f', 'timestamps': [1.0], 'on_demand': True}


@pytest.mark.parametrize(
    ('body', 'outcome'),
    [
        ({'status': 'done'}, 'built'),
        ({'status': 'exists'}, 'exists'),
        ({'status': 'failed_final'}, 'failed_final'),
        ({'status': 'dropped', 'reason': 'chunks_missing'}, 'chunks_missing'),
        ({'status': 'unavailable', 'reason': 'source_manifest_changed'}, 'unavailable'),
        ({'status': 'retry'}, 'retry'),
        ({'status': 'deferred', 'reason': 'destructive_operation'}, 'destructive_deferred'),
        ({'status': 'surprise'}, 'other'),
    ],
)
def test_demand_outcome_labels(body, outcome):
    before = _count('conversation', outcome)
    _record(V2_DEMAND, JSONResponse(status_code=200, content=body))
    assert _count('conversation', outcome) == before + 1


def test_file_representation_and_unhandled_error():
    before_built = _count('file', 'built')
    before_error = _count('file', 'error')
    _record(V1_DEMAND, JSONResponse(status_code=200, content={'status': 'done'}))
    _record(V1_DEMAND, None)
    assert _count('file', 'built') == before_built + 1
    assert _count('file', 'error') == before_error + 1


@pytest.mark.parametrize('payload', [{**V2_DEMAND, 'on_demand': False}, {'schema_version': 2}, ValueError('bad'), []])
def test_eager_or_unreadable_tasks_are_not_counted(payload):
    before = _count('conversation', 'built')
    _record(payload, JSONResponse(status_code=200, content={'status': 'done'}))
    assert _count('conversation', 'built') == before


def test_route_counts_an_exception_then_reraises(monkeypatch):
    async def boom(request, task_retry_count):
        raise RuntimeError('firestore down')

    monkeypatch.setattr(routers_sync, '_handle_audio_merge_job', boom)
    before = _count('conversation', 'error')
    with pytest.raises(RuntimeError):
        asyncio.run(routers_sync.run_audio_merge_job(_FakeRequest(V2_DEMAND), task_retry_count=0))
    assert _count('conversation', 'error') == before + 1
