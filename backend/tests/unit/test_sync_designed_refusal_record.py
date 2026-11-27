"""Designed sync-local-files 503s write exactly one guard-readable refusal record.

The Cloud Run rollout guard excludes a ``POST /v2/sync-local-files`` 503 from its
error rate only when a ``sync_upload_refused ... status=503 reason=... trace=...``
stdout line names that request's trace id (cloud-run-guard.json
``designed_refusals``). Failure 503s such as ``sync_dispatch_unavailable``, an
invalid fence setting failing closed, and a custody finalizer replacing the
handler's response write no record, so the guard counts them.
"""

import ast
import inspect
import logging
import re

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from tests.unit.test_sync_backfill_day_cap_upload import cap  # noqa: F401
from tests.unit.test_sync_capture_time_skew import client, _default_skew, _filename  # noqa: F401
from routers import sync as router
from database import record_custody_append, sync_jobs
from utils.sync import designed_refusal
from utils.sync import record_token_lease as custody_lease

DAY = 86400
TRACE = '0af7651916cd43dd8448eb211c80319c'
# The guard's record parser (scripts/guard_eval.py in the hold-back lane).
GUARD_RECORD = re.compile(
    r'(?:^|[\s:])sync_upload_refused uid=\S+ status=(\d{3}) reason=[a-z0-9_]+ trace=([0-9a-f]{32})\s*$'
)
DESIGNED_REASONS = {
    'sync_ledger_fence_cutover',
    'backfill_disabled',
    'backfill_day_cap',
    'retained_recovery_disabled',
    'capture_clock_identity_required',
    'repaired_clock_batch_declined',
    # 'dispatch_hold' marked the legacy staging dispatch, deleted with legacy sync (SCA-2965).
}


def _records(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith('sync_upload_refused ')]


def _refuse(reason='backfill_day_cap', header=f'{TRACE}/1;o=1'):
    @designed_refusal.designed_refusal_outcome
    async def handler():
        designed_refusal.mark_designed_refusal('uid-1', reason, header)
        return JSONResponse(status_code=503, content={'code': 'backfill_capacity'})

    return handler


async def _run(stack):
    try:
        return await stack()
    except HTTPException as error:
        return error


@pytest.mark.parametrize(
    'header, trace',
    [
        (f'{TRACE}/1;o=1', TRACE),
        (TRACE.upper() + '/77', TRACE),
        (TRACE, TRACE),
        (None, '-'),
        ('not-a-trace/1', '-'),
        (TRACE + 'ff/1', '-'),
    ],
)
@pytest.mark.asyncio
async def test_record_names_the_cloud_trace_id(caplog, header, trace):
    with caplog.at_level(logging.INFO, logger=designed_refusal.__name__):
        response = await designed_refusal.records_designed_refusals(_refuse(header=header))()
    assert response.status_code == 503
    assert _records(caplog) == [f'sync_upload_refused uid=uid-1 status=503 reason=backfill_day_cap trace={trace}']
    record = caplog.records[-1]
    assert record.levelno == logging.INFO and record.name == 'utils.sync.designed_refusal'


@pytest.mark.asyncio
async def test_guard_parses_the_record_as_written_by_the_shared_text_formatter(caplog):
    with caplog.at_level(logging.INFO, logger=designed_refusal.__name__):
        await designed_refusal.records_designed_refusals(_refuse('dispatch_hold'))()
    line = logging.Formatter('%(levelname)s %(name)s: %(message)s').format(caplog.records[-1])
    match = GUARD_RECORD.search(line)
    assert match and match.groups() == ('503', TRACE)


@pytest.mark.asyncio
async def test_a_raised_designed_503_is_recorded_once_and_still_raised(caplog):
    @designed_refusal.designed_refusal_outcome
    async def handler():
        designed_refusal.mark_designed_refusal('uid-1', 'retained_recovery_disabled', TRACE)
        raise HTTPException(503, detail='Historical recovery is paused; retain local audio')

    with caplog.at_level(logging.INFO, logger=designed_refusal.__name__):
        raised = await _run(designed_refusal.records_designed_refusals(handler))
    assert isinstance(raised, HTTPException) and raised.status_code == 503
    assert len(_records(caplog)) == 1


@pytest.mark.asyncio
async def test_mark_without_the_outer_recorder_writes_nothing(caplog):
    with caplog.at_level(logging.INFO, logger=designed_refusal.__name__):
        await _refuse()()
    assert _records(caplog) == []


@pytest.mark.asyncio
async def test_a_wrapper_that_replaces_the_designed_503_leaves_it_unrecorded(caplog):
    inner = _refuse()

    async def replacing():
        await inner()
        return JSONResponse(status_code=503, content={'code': 'other'})

    with caplog.at_level(logging.INFO, logger=designed_refusal.__name__):
        response = await designed_refusal.records_designed_refusals(replacing)()
    assert response.status_code == 503
    assert _records(caplog) == []


def _custody_stack(monkeypatch, finish):
    monkeypatch.setattr(custody_lease.lease, 'token_lease_mode', lambda: 'on')
    monkeypatch.setattr(record_custody_append, 'finish', finish)

    @designed_refusal.designed_refusal_outcome
    async def handler():
        # The handler acquired a custody session, then refused by design.
        custody_lease._upload.get().update(uid='uid-1', cid='conv-1', session='custody:job-1')
        designed_refusal.mark_designed_refusal('uid-1', 'retained_recovery_disabled', TRACE)
        return JSONResponse(status_code=503, content={'code': 'sync_batch_unavailable'})

    return designed_refusal.records_designed_refusals(custody_lease.custody_upload(handler))


@pytest.mark.asyncio
async def test_custody_finalizer_failure_after_a_designed_refusal_is_not_recorded(monkeypatch, caplog):
    def finish(*_a, **_k):
        raise RuntimeError('custody store unavailable')

    with caplog.at_level(logging.INFO):
        outcome = await _run(_custody_stack(monkeypatch, finish))
    # The finalizer's own 503 replaced the designed response: it must count.
    assert isinstance(outcome, HTTPException) and outcome.status_code == 503
    assert outcome.detail == 'Retain local audio and retry custody admission'
    assert _records(caplog) == []


@pytest.mark.asyncio
async def test_designed_refusal_is_recorded_when_custody_finalizes_cleanly(monkeypatch, caplog):
    finished = []
    with caplog.at_level(logging.INFO, logger=designed_refusal.__name__):
        outcome = await _run(_custody_stack(monkeypatch, lambda *a, **k: finished.append(k)))
    assert outcome.status_code == 503 and finished == [{'accepted': False, 'late_observed': False}]
    assert len(_records(caplog)) == 1


def test_recorder_is_outside_custody_and_capture_is_innermost():
    layers, fn = [], router.sync_local_files_v2
    while fn is not None:
        layers.append(fn.__code__.co_qualname)
        fn = getattr(fn, '__wrapped__', None)
    assert layers == [
        'records_designed_refusals.<locals>.run',
        'custody_upload.<locals>.run',
        'observe_upload.<locals>.run',
        'designed_refusal_outcome.<locals>.run',
        'sync_local_files_v2',
    ]


def _post(client, filename):
    return client.post(
        '/v2/sync-local-files',
        files=[('files', (filename, b'\x00' * 32, 'application/octet-stream'))],
        headers={'X-Cloud-Trace-Context': f'{TRACE}/1;o=1'},
    )


def test_over_cap_upload_writes_one_record_with_its_trace(client, cap, caplog):
    cap['seconds'] = 24 * 3600
    with caplog.at_level(logging.INFO, logger=designed_refusal.__name__):
        response = _post(client, _filename(-45 * DAY))
    assert response.status_code == 503, response.text
    records = _records(caplog)
    assert len(records) == 1
    assert records[0].endswith(f' status=503 reason=backfill_day_cap trace={TRACE}')
    assert GUARD_RECORD.search(records[0]).groups() == ('503', TRACE)


@pytest.mark.parametrize('setting, recorded', [('standby', 1), (' STANDBY ', 1), ('stanby', 0), ('on', 0)])
def test_only_an_explicitly_configured_fence_standby_is_a_designed_refusal(
    client, monkeypatch, caplog, setting, recorded
):
    monkeypatch.setattr(router, 'get_sync_ledger_fence_mode', sync_jobs.get_sync_ledger_fence_mode)
    monkeypatch.setenv(sync_jobs.SYNC_LEDGER_FENCE_MODE_ENV, setting)
    with caplog.at_level(logging.INFO):
        response = _post(client, _filename(0))
    # Both answer the same fail-closed 503; only the configured cutover is designed.
    assert response.status_code == 503, response.text
    assert response.json()['code'] == 'sync_ledger_fence_cutover'
    assert len(_records(caplog)) == recorded
    invalid = [r for r in caplog.records if 'event=sync_ledger_fence_mode outcome=invalid_config' in r.getMessage()]
    assert bool(invalid) == (not recorded)


def _mark_sites(tree):
    """Yield (reason, statement after the mark) for every mark, including one guarded by an ``if``."""

    def is_mark(statement):
        call = getattr(statement, 'value', None)
        return isinstance(call, ast.Call) and getattr(call.func, 'attr', None) == 'mark_designed_refusal'

    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if not isinstance(body, list) or (isinstance(node, ast.If) and len(body) == 1 and is_mark(body[0])):
            continue  # A guarded mark is checked against the statement after its ``if``.
        for index, statement in enumerate(body):
            following = body[index + 1] if index + 1 < len(body) else None
            if is_mark(statement):
                yield statement.value.args[1].value, following
            elif isinstance(statement, ast.If) and not statement.orelse and len(statement.body) == 1:
                if is_mark(statement.body[0]):
                    yield statement.body[0].value.args[1].value, following


def test_each_designed_refusal_is_marked_once_right_before_its_503():
    """Every mark sits directly before a designed 503; failure 503s such as
    sync_dispatch_unavailable have none (the reason set is exhaustive)."""
    source = inspect.getsource(inspect.unwrap(router.sync_local_files_v2))
    reasons = []
    for reason, following in _mark_sites(ast.parse(source.lstrip())):
        reasons.append(reason)
        text = ast.unparse(following) if following is not None else ''
        assert text.startswith(('return JSONResponse(', 'raise HTTPException(503')), text
        assert 'status_code=503' in text or text.startswith('raise HTTPException(503')
    assert sorted(reasons) == sorted(DESIGNED_REASONS)
    assert source.count('mark_designed_refusal(') == len(DESIGNED_REASONS)
    # No raw record bypasses the outer recorder.
    assert 'sync_upload_refused uid=%s status=503' not in source
