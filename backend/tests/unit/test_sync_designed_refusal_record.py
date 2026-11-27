"""Designed sync-local-files 503s write exactly one guard-readable refusal record.

The Cloud Run rollout guard excludes a ``POST /v2/sync-local-files`` 503 from its
error rate only when a ``sync_upload_refused ... status=503 reason=... trace=...``
stdout line names that request's trace id (cloud-run-guard.json
``designed_refusals``). Failure 503s such as ``sync_dispatch_unavailable`` write no
record, so the guard counts them.
"""

import ast
import inspect
import logging
import re

import pytest

from tests.unit.test_sync_backfill_day_cap_upload import cap  # noqa: F401
from tests.unit.test_sync_capture_time_skew import client, _default_skew, _filename  # noqa: F401
from routers import sync as router

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
    'dispatch_hold',
}


def _records(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith('sync_upload_refused ')]


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
def test_record_names_the_cloud_trace_id(caplog, header, trace):
    with caplog.at_level(logging.INFO, logger=router.__name__):
        router._log_designed_refusal('uid-1', 'backfill_day_cap', header)
    assert _records(caplog) == [f'sync_upload_refused uid=uid-1 status=503 reason=backfill_day_cap trace={trace}']
    record = caplog.records[-1]
    assert record.levelno == logging.INFO and record.name == 'routers.sync'


def test_guard_parses_the_record_as_written_by_the_shared_text_formatter(caplog):
    with caplog.at_level(logging.INFO, logger=router.__name__):
        router._log_designed_refusal('uid-1', 'dispatch_hold', f'{TRACE}/1;o=1')
    line = logging.Formatter('%(levelname)s %(name)s: %(message)s').format(caplog.records[-1])
    match = GUARD_RECORD.search(line)
    assert match and match.groups() == ('503', TRACE)


def test_over_cap_upload_writes_one_record_with_its_trace(client, cap, caplog):
    cap['seconds'] = 24 * 3600
    with caplog.at_level(logging.INFO, logger=router.__name__):
        response = client.post(
            '/v2/sync-local-files',
            files=[('files', (_filename(-45 * DAY), b'\x00' * 32, 'application/octet-stream'))],
            headers={'X-Cloud-Trace-Context': f'{TRACE}/1;o=1'},
        )
    assert response.status_code == 503, response.text
    records = _records(caplog)
    assert len(records) == 1
    assert records[0].endswith(f' status=503 reason=backfill_day_cap trace={TRACE}')
    assert GUARD_RECORD.search(records[0]).groups() == ('503', TRACE)


def test_each_designed_refusal_records_once_right_before_its_503():
    """Every record call sits directly before a designed 503; failure 503s such as
    sync_dispatch_unavailable have none (the reason set is exhaustive)."""
    source = inspect.getsource(router.sync_local_files_v2)
    tree = ast.parse(source.lstrip())
    reasons = []
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if not isinstance(body, list):
            continue
        for index, statement in enumerate(body):
            call = getattr(statement, 'value', None)
            if not (isinstance(call, ast.Call) and getattr(call.func, 'id', None) == '_log_designed_refusal'):
                continue
            reasons.append(call.args[1].value)
            following = ast.unparse(body[index + 1]) if index + 1 < len(body) else ''
            assert following.startswith(('return JSONResponse(', 'raise HTTPException(503')), following
            assert 'status_code=503' in following or following.startswith('raise HTTPException(503')
    assert sorted(reasons) == sorted(DESIGNED_REASONS)
    # The day-cap line no longer bypasses the helper with a trace-less record.
    assert 'status=503 reason=backfill_day_cap' not in source
