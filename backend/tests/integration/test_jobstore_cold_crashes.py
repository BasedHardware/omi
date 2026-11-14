"""Abrupt exits on both sides of actual cold copy and erasure FS COMMIT."""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from database import legal_holds
from database.jobstore.cold_purge import erase_recording
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401
from tests.integration.test_jobstore_cold_sink import cold, terminal, unit  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('operation', ['copy', 'erase'])
@pytest.mark.parametrize('gap', ['before', 'after'])
def test_actual_cold_commit_exit_replays_without_resurrection_or_lost_custody(cold, operation, gap):
    c = cold
    token, cid = '', ''
    if operation == 'erase':
        # Prime the crash precondition with bounded pages. This is not a
        # hundred-row throughput test: every actual page keeps its unchanged
        # 1.5s budget, and every original row still reaches the real cold sink.
        for _ in c.rows:
            assert c.sink.page(limit=1) == 1
        retained, cid, identity, manifest = terminal(c)
        with unit(c) as authority:
            token = authority.token
        # Age before the child obtains its read lease; no post-kill update can
        # bypass Firestore's outstanding read locks.
        legal_holds.acquire_destructive_operation(
            c.uid,
            kind='explicit_memory_deletion',
            token=token,
            firestore_client=c.handoff.client,
            now=datetime.now(timezone.utc) - timedelta(seconds=2 * legal_holds.UNIT_EXPIRY_SECONDS),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=legal_holds.UNIT_EXPIRY_SECONDS),
        )
    with c.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    command = """
import os
import testing.pipeline_sim._env
from google.cloud.firestore_v1.types import CommitRequest
from database import legal_holds
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.authority import Epoch
from database.jobstore.cold_sink import ColdSink
from database.jobstore.cold_purge import erase_recording
from database.jobstore.retained_copies import RetainedCopies
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
pool=Pool(os.environ['OMI_COLD_DSN'],size=2)
client=_emulator_client()
h=Handoff(pool,Fence(pool),client,Epoch(os.environ['OMI_COLD_NS'],3))
api=client._firestore_api
real=api.commit
def commit(*a,**k):
    request=CommitRequest(k.get('request') or a[0])
    match=any(w.update and 'cold_only' in w.update.fields for w in request.writes)
    if match and os.environ['OMI_COLD_GAP']=='before':os._exit(86)
    result=real(*a,**k)
    if match:os._exit(86)
    return result
api.commit=commit
if os.environ['OMI_COLD_OP']=='copy':
    ColdSink(h).page(limit=1)
else:
    uid,cid=os.environ['OMI_COLD_UID'],os.environ['OMI_COLD_CID']
    r=RetainedCopies(h)
    identity,manifest=r.inventory(uid,cid)[0]
    authority=legal_holds.UnitAuthority(uid,'explicit_memory_deletion',os.environ['OMI_COLD_TOKEN'],client,None)
    erase_recording(r,uid,identity,manifest,authority,conversation=cid)
raise AssertionError('did not reach cold COMMIT')
"""
    result = subprocess.run(
        [sys.executable, '-c', command],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            'OMI_COLD_DSN': dsn,
            'OMI_COLD_NS': c.handoff.ticket.namespace,
            'OMI_COLD_UID': c.uid,
            'OMI_COLD_CID': cid,
            'OMI_COLD_TOKEN': token,
            'OMI_COLD_OP': operation,
            'OMI_COLD_GAP': gap,
        },
    )
    assert result.returncode == 86, result.stderr
    if operation == 'copy':
        row = c.rows[0]
        assert c.sink.ref(row[2], row[3]).get().exists == (gap == 'after')
        with c.handoff.pool.connection() as conn:
            assert conn.execute(
                'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
            ).fetchone() == (0,)
        from google.api_core.exceptions import GoogleAPICallError

        # A killed client's read lease can outlive one delivery. Each keeps
        # the unchanged 1.5s page bound and cannot checkpoint an unknown COMMIT.
        for _ in range(64):
            try:
                c.sink.page(limit=1)
                break
            except GoogleAPICallError:
                assert gap == 'before'
        else:
            pytest.fail('abandoned cold copy read lease exceeded bounded redelivery')
        c.sink.page(limit=100)
    else:
        assert c.sink.barrier(identity).get().exists == (gap == 'after')
        from google.api_core.exceptions import Aborted

        for _ in range(12):
            try:
                with unit(c) as successor:
                    assert successor.token != token
                    erase_recording(retained, c.uid, identity, manifest, successor, conversation=cid)
                break
            except (ValueError, Aborted) as error:
                assert gap == 'before' and (isinstance(error, Aborted) or isinstance(error.__cause__, Aborted))
        else:
            pytest.fail('abandoned cold read lease exceeded bounded redelivery')
        for row in c.rows:
            c.sink.apply(row, timeout=1.5)
        assert all(not c.handoff.client.document(path).get().exists for path in manifest['cold_paths'])
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM queue_journal WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone()[0] == len(c.rows)
        assert conn.execute(
            'SELECT count(*) FROM units WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (2,)
    assert c.handoff.ref('intent', c.view.identity).get().exists
    assert c.view.ref('intakes', c.view.identity).get().exists
