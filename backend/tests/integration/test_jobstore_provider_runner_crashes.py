"""Abrupt exits through the joined driver, never exception-only crash proof."""

import asyncio
import os
import subprocess
import sys

import pytest

from database.jobstore import codec
from database.jobstore.authority import AuthorityRefused
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401
from tests.integration.test_jobstore_provider_runner import runtime, run_sync, claims  # noqa: F401
from utils.batch_pipeline.typed_provider import run_claimed_provider

pytestmark = [pytest.mark.integration, pytest.mark.parametrize('lane', ['runner'], indirect=True)]


@pytest.mark.parametrize('gap', ['after_paid', 'after_publish', 'before_terminal', 'after_terminal'])
def test_actual_joined_driver_process_exit_retains_original_custody(runtime, gap, tmp_path):
    r = runtime
    claim = claims(r)[0]
    with r.x.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    marker = tmp_path / 'paid-send'
    code = '''
import os,asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import testing.pipeline_sim._env
from database.jobstore import codec
from database.jobstore.authority import Epoch
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.provider_handoff import ProviderHandoff
from database.batch_pipeline_purge import provider_result_artifacts
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
from utils.batch_pipeline import provider_stt, vendor_route_contracts
from utils.batch_pipeline.typed_provider import TypedProviderStage
from utils.other.local_storage import LocalStorageClient
from utils.stt import allowance_session
from utils.executors import sync_executor,run_blocking
pool=Pool(os.environ['TYPED_RUN_DSN'],size=2)
h=Handoff(pool,Fence(pool),_emulator_client(),Epoch(os.environ['TYPED_RUN_NS'],3))
adapter=ProviderHandoff(h)
claim=codec.loads(os.environ['TYPED_RUN_CLAIM'])
gap=os.environ['TYPED_RUN_GAP']
storage=LocalStorageClient(Path(os.environ['TYPED_RUN_STORAGE']))
class Operation:
    def __init__(self,uid,surface,*,operation,seconds,billing_period):
        self.uid,self.operation,self.closed=uid,operation,False
        assert billing_period=='2026-11'
    async def reserve_async(self,service):pass
@asynccontextmanager
async def track(scope):yield scope
allowance_session.Operation=Operation
allowance_session.track=track
async def vendor(*args):
    Path(os.environ['TYPED_RUN_MARKER']).write_text('one paid send')
    if gap=='after_paid':os._exit(86)
    return [{'text':'The project is ready.','timestamp':[0.0,4.0],'speaker':'SPEAKER_00'}],'ja'
provider_stt._vendor_words=vendor
stage=TypedProviderStage(adapter,claim['unit_id'],claim['attempt_token'],
    lambda ticket:provider_result_artifacts(ticket,storage,'synthetic',b'x'*32,lease_seconds=60),
    effect_lease_seconds=60,partial_wait=30,clock=lambda:202,
    health=vendor_route_contracts.AlwaysHealthy(),allowed=lambda *a:True,
    inspect=lambda *a:(b'\\0\\0'*480000,30.0,[{'start':0.0,'end':4.0}]),
    armed=lambda:True,failover_routes=lambda _:('modulate',))
if gap=='after_publish':stage._complete=lambda *a:os._exit(86)
if gap=='before_terminal':
    original=adapter.units.settle_in_transaction
    def killed(*a,**k):
        original(*a,**k)
        os._exit(86)
    adapter.units.settle_in_transaction=killed
async def run_sync(fn,*a,**k):return await run_blocking(sync_executor,fn,*a,**k)
asyncio.run(stage.run_async(claim['unit_id'],run_sync))
os._exit(86 if gap=='after_terminal' else 87)
'''
    child = subprocess.run(
        [sys.executable, '-c', code],
        env={
            **os.environ,
            'TYPED_RUN_DSN': dsn,
            'TYPED_RUN_NS': r.x.store.namespace,
            'TYPED_RUN_CLAIM': codec.canonical(
                {k: claim[k] for k in ('unit_id', 'attempt_token', 'admission', 'source')}
            ),
            'TYPED_RUN_GAP': gap,
            'TYPED_RUN_STORAGE': str(r.x.storage.root),
            'TYPED_RUN_MARKER': str(marker),
        },
        capture_output=True,
        timeout=45,
    )
    assert child.returncode == 86, child.stderr.decode()
    assert marker.read_text() == 'one paid send'
    with r.x.handoff.pool.connection() as conn:
        job = r.x.adapter.units._unit(conn, claim['unit_id'])
        upload = conn.execute(
            'SELECT phase FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s',
            (r.x.store.namespace, claim['unit_id']),
        ).fetchone()
        assert job['admission'] == claim['admission'] and job['source'] == claim['source']
        assert job['state'] == ('result_ready' if gap == 'after_terminal' else 'pending')
        assert upload == (None if gap == 'after_paid' else ('published',))
    redeliver = lambda: asyncio.run(
        run_claimed_provider(
            r.x.adapter, claim, r.artifacts, run_sync=run_sync, effect_lease_seconds=60, partial_wait=30, **r.options
        )
    )
    if gap == 'after_paid':
        with pytest.raises(AuthorityRefused, match='another POST forbidden'):
            redeliver()
    else:
        assert redeliver().outcome == 'done'
    assert not any(e[0] == 'send' for e in r.events)
    assert r.x.handoff.ref('intent', 'recording').get().exists
    assert (
        r.x.client.collection(r.x.store.namespace + '_intakes').document('recording').get().to_dict()['repair_lineage']
        == 'synthetic-original'
    )
