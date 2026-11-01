"""Static half of contract (d): task targets never 429/503, 500 only from the unexpected fallback."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.cross_service_checks import task_targets as tt
from scripts.cross_service_contract import TASK_EDGES, Source, Violation


@dataclass(frozen=True)
class Edge:
    id: str
    route: str


class TreeSource:
    def __init__(self, root: Path):
        self.root = root

    def read(self, rel):
        return (self.root / rel).read_text()

    def directory(self, rel):
        return self.root / rel


def _keys(tmp_path, files, routes):
    for name, text in files.items():
        path = tmp_path / 'backend' / 'routers' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    modules = tt.load_router_modules(TreeSource(tmp_path))
    return sorted(v.scope for v in tt.violations_for([Edge(*r) for r in routes], modules, Violation))


HEADER = 'from fastapi import APIRouter, HTTPException, status\nfrom fastapi.responses import JSONResponse\n'


def test_flags_503_429_and_unguarded_500_but_allows_fallback_500(tmp_path):
    src = HEADER + '''
router = APIRouter(prefix='/v2/x')

@router.post('/run')
async def run(payload: dict):
    if payload.get('a'):
        raise HTTPException(status_code=503, detail='standby')
    if payload.get('b'):
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={})
    try:
        work()
    except ValueError:
        return JSONResponse(status_code=500, content={'status': 'retry'})
    except Exception:
        return JSONResponse(status_code=500, content={'status': 'retry'})
    return JSONResponse(status_code=409, content={'status': 'retry'})

@router.post('/other')
async def other():
    raise HTTPException(503)
'''
    assert _keys(tmp_path, {'x.py': src}, [('x', '/v2/x/run')]) == [
        'x/routers/x.py:run/429',
        'x/routers/x.py:run/500',
        'x/routers/x.py:run/503',
    ]


def test_follows_helpers_across_router_modules(tmp_path):
    helper = HEADER + '''
async def enrichment_response(payload):
    if not payload:
        return JSONResponse(status_code=503, content={})
    return JSONResponse(status_code=200, content={})
'''
    main = HEADER + '''
from routers.helper import enrichment_response
router = APIRouter()

@router.post('/v2/sync-jobs/run')
async def run(payload: dict):
    return await _body(payload)

async def _body(payload):
    return await enrichment_response(payload)
'''
    keys = _keys(tmp_path, {'helper.py': helper, 'main_router.py': main}, [('sync-jobs', '/v2/sync-jobs/run')])
    assert keys == ['sync-jobs/routers/helper.py:enrichment_response/503']


def test_expected_retry_must_answer_retry_response(tmp_path):
    src = HEADER + '''
from utils.workers.retry import ExpectedRetry, retry_response
router = APIRouter()

@router.post('/good')
async def good():
    try:
        work()
    except ExpectedRetry as exc:
        return retry_response(exc.reason)

@router.post('/bad')
async def bad():
    try:
        work()
    except ExpectedRetry:
        return JSONResponse(status_code=200, content={})
'''
    keys = _keys(tmp_path, {'r.py': src}, [('good', '/good'), ('bad', '/bad')])
    assert keys == ['bad/routers/r.py:bad/expected-retry-shape']


def test_unmounted_route_reports_nothing(tmp_path):
    assert _keys(tmp_path, {'r.py': HEADER + 'router = APIRouter()\n'}, [('enrichment', '/v2/enrichment/run')]) == []


# Known violators on integration (contract (d) table). Shrink-only: a new key fails here and in
# the cross-service contract run; a fixed one must be deleted from this set and from
# deploy/cross_service_known_gaps.json.
KNOWN = {
    'account-deletion/routers/users.py:run_account_deletion_wipe/500',
    'listen-finalization/routers/conversation_finalization.py:run_listen_finalization_job/500',
    'sync-backfill/routers/sync.py:_run_sync_job_attempt/500',
    'sync-backfill/routers/sync.py:_run_sync_job_attempt/503',
    'sync-backfill/routers/sync.py:_run_sync_job_body/500',
    'sync-backfill/routers/sync.py:run_sync_job/500',
    'sync-backfill/routers/sync.py:run_sync_job/503',
    'sync-jobs/routers/sync.py:_run_sync_job_attempt/500',
    'sync-jobs/routers/sync.py:_run_sync_job_attempt/503',
    'sync-jobs/routers/sync.py:_run_sync_job_body/500',
    'sync-jobs/routers/sync.py:run_sync_job/500',
    'sync-jobs/routers/sync.py:run_sync_job/503',
}


@pytest.fixture(scope='module')
def real_keys():
    # Parsing every router is the expensive part; do it in setup, not the timed call.
    class Ctx:
        source = Source()

    return {v.key for v in tt.check_task_target_retry_semantics(Ctx())}


def test_real_tree_has_no_new_violators(real_keys):
    prefix = 'task-target-retry-semantics|code|'
    assert all(k.startswith(prefix) for k in real_keys)
    found = {k.removeprefix(prefix) for k in real_keys}
    assert found <= KNOWN, sorted(found - KNOWN)


def test_listen_finalization_route_never_answers_503(real_keys):
    # M1 L04-3: the sync_reprocess branch answered 503 on an expected first-summary retry.
    assert not [k for k in real_keys if 'conversation_finalization.py' in k and k.endswith('/503')]
