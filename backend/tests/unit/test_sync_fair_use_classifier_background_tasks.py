"""Fair-use classifier scheduling must use tracked start_background_task."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import utils.executors as executors_mod
import utils.sync.pipeline as pipeline_mod


def _source(rel_path: str) -> str:
    return (Path(__file__).resolve().parents[2] / rel_path).read_text(encoding='utf-8')


def test_sync_router_schedules_classifier_via_start_background_task():
    source = _source('routers/sync.py')
    assert 'start_background_task(' in source
    assert 'trigger_classifier_if_needed(uid, triggered_caps)' in source
    assert 'asyncio.create_task(trigger_classifier_if_needed' not in source


def test_pipeline_schedules_classifier_via_start_background_task():
    source = _source('utils/sync/pipeline.py')
    assert 'start_background_task(' in source
    assert 'trigger_classifier_if_needed(uid, triggered_caps)' in source
    assert 'asyncio.create_task(trigger_classifier_if_needed' not in source


def test_start_background_task_tracks_and_logs_classifier_failures(monkeypatch, caplog):
    created_tasks = []
    real_create_task = asyncio.create_task

    def spying_create_task(coro, *args, **kwargs):
        task = real_create_task(coro, *args, **kwargs)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(asyncio, 'create_task', spying_create_task)

    async def boom(_uid, _caps):
        raise RuntimeError('boom-classifier')

    monkeypatch.setattr(pipeline_mod, 'trigger_classifier_if_needed', boom)
    baseline = executors_mod.get_background_task_count()

    async def scenario():
        executors_mod.start_background_task(
            pipeline_mod.trigger_classifier_if_needed('uid-1', ['soft']),
            name='sync_job_fair_use_classifier:uid-1',
        )
        tracked_delta = executors_mod.get_background_task_count() - baseline
        await asyncio.gather(*created_tasks, return_exceptions=True)
        return tracked_delta

    caplog.set_level(logging.ERROR, logger='utils.executors')
    tracked_delta = asyncio.run(scenario())
    assert tracked_delta == 1
    assert 'background_task failed' in caplog.text
    assert 'boom-classifier' in caplog.text
