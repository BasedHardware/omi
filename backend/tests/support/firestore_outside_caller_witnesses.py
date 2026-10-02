"""Named runtime witnesses for serving query callers outside ``database/``.

Same contract as ``tests.support.firestore_caller_witnesses``: every statically
discovered binding to the witnessed helpers maps to a named ``CallerWitness``
here, and each recipe executes the *real* owning function while the helper's
import site is patched to a signature-bound capture. AST discovery stays the
detection layer; it never constructs query shapes.
"""

from __future__ import annotations

from typing import Any

import pytest

import routers.desktop_prompts as desktop_prompts_router
import routers.desktop_tts_updates as desktop_tts_updates_router
import routers.fair_use_admin as fair_use_admin_router
import utils.task_intelligence.chat_first_materialization_health as health
from tests.support.firestore_caller_witnesses import (
    CallerWitness,
    HelperCapture,
    trial,
)
from tests.support.firestore_query_drivers import FROZEN_NOW, SHAPE_UID

TARGETS = frozenset(
    {
        'database.serving_query_reads.list_active_desktop_prompt_snapshots',
        'database.serving_query_reads.list_desktop_release_snapshots',
        'database.serving_query_reads.find_fair_use_case_snapshots',
        'utils.task_intelligence.chat_first_materialization_health._documents',
    }
)


def _run_desktop_prompts(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(capture, desktop_prompts_router.get_desktop_prompts, uid='u1')


def _run_release_models(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(capture, desktop_tts_updates_router._release_models)


def _run_lookup_case(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(capture, fair_use_admin_router.lookup_case, 'case-1', admin_id='admin-1')


def _run_public_case_status(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(capture, fair_use_admin_router.get_public_case_status, 'case-1')


def _run_health_collect(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    for uid in (None, SHAPE_UID):
        for min_created_at in (None, FROZEN_NOW):
            trial(
                capture,
                health.collect,
                uid,
                25,
                health.DEFAULT_STALE_AFTER_HOURS,
                FROZEN_NOW,
                min_created_at,
            )


def _run_scheduled_health_check(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> Any:
    """Drive the real weekly wrapper through the real collector.

    Returns ``run_scheduled_check``'s status so the caller asserts the captured
    window and the not-due path; ``_documents`` is signature-captured by
    ``install_capture`` with ``abort=False``.
    """
    due = health.datetime(2026, 1, 5, 14, 0, tzinfo=health.timezone.utc)
    status = health.run_scheduled_check(now=due, collector=health.collect)
    expected_start = due - health.timedelta(days=health.HEALTH_CHECK_WINDOW_DAYS)
    assert capture.calls == [{'uid': None, 'limit': None, 'min_created_at': expected_start, 'firestore_client': None}]
    captured = dict(capture.calls[0])
    capture.calls.clear()
    assert health.run_scheduled_check(now=due + health.timedelta(hours=1), collector=health.collect) == 'not_due'
    assert not capture.calls
    return status, captured


WITNESSES: dict[str, CallerWitness] = {
    witness.key: witness
    for witness in (
        CallerWitness(
            'routers/desktop_prompts.py:get_desktop_prompts:database.serving_query_reads.list_active_desktop_prompt_snapshots',
            'database.serving_query_reads.list_active_desktop_prompt_snapshots',
            'routers.desktop_prompts.list_active_desktop_prompt_snapshots',
            ('request',),
            1,
            _run_desktop_prompts,
        ),
        CallerWitness(
            'routers/desktop_tts_updates.py:_release_models:database.serving_query_reads.list_desktop_release_snapshots',
            'database.serving_query_reads.list_desktop_release_snapshots',
            'routers.desktop_tts_updates.list_desktop_release_snapshots',
            ('request',),
            1,
            _run_release_models,
        ),
        CallerWitness(
            'routers/fair_use_admin.py:lookup_case:database.serving_query_reads.find_fair_use_case_snapshots',
            'database.serving_query_reads.find_fair_use_case_snapshots',
            'routers.fair_use_admin.find_fair_use_case_snapshots',
            ('request',),
            1,
            _run_lookup_case,
        ),
        CallerWitness(
            'routers/fair_use_admin.py:get_public_case_status:database.serving_query_reads.find_fair_use_case_snapshots',
            'database.serving_query_reads.find_fair_use_case_snapshots',
            'routers.fair_use_admin.find_fair_use_case_snapshots',
            ('request',),
            1,
            _run_public_case_status,
        ),
        CallerWitness(
            'utils/task_intelligence/chat_first_materialization_health.py:collect:utils.task_intelligence.chat_first_materialization_health._documents',
            'utils.task_intelligence.chat_first_materialization_health._documents',
            'utils.task_intelligence.chat_first_materialization_health._documents',
            ('operational-materialization-health',),
            1,
            _run_health_collect,
        ),
    )
}
