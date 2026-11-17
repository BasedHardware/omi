"""Abrupt exits around actual original-upload cold and suppression FS COMMIT."""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from google.api_core.exceptions import Aborted, GoogleAPICallError

from database import legal_holds
from database.jobstore.cold_purge import erase_recording
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_effect import paid  # noqa: F401
from tests.integration.test_jobstore_result_sessions import result  # noqa: F401
from tests.integration.test_jobstore_upload_cold import upload_cold, close, unit, upload_rows  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('operation', ['copy', 'erase'])
@pytest.mark.parametrize('gap', ['before', 'after'])
def test_original_upload_cold_crash_preserves_custody_and_suppression(upload_cold, operation, gap):
    c = upload_cold
    token, cid = '', ''
    target = upload_rows(c)[-1]
    if operation == 'erase':
        c.sink.apply(target, timeout=1.5)
        retained, cid, identity, manifest = close(c)
        with unit(c) as authority:
            token = authority.token
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
pool=Pool(os.environ['OMI_UC_DSN'],size=2)
client=_emulator_client()
h=Handoff(pool,Fence(pool),client,Epoch(os.environ['OMI_UC_NS'],3))
api=client._firestore_api
real=api.commit
def commit(*a,**k):
    request=CommitRequest(k.get('request') or a[0])
    if os.environ['OMI_UC_OP']=='copy':
        match=any(w.update and 'family' in w.update.fields and
          w.update.fields['family'].string_value=='queue_provider_uploads' for w in request.writes)
    else:
        match=any(w.update and 'through' in w.update.fields and 'cold_only' in w.update.fields for w in request.writes)
    if match and os.environ['OMI_UC_GAP']=='before':os._exit(86)
    result=real(*a,**k)
    if match:os._exit(86)
    return result
api.commit=commit
if os.environ['OMI_UC_OP']=='copy':
    with pool.connection() as conn:
        row=conn.execute('SELECT seq,epoch,family,identity,operation,owner_key,body FROM queue_journal '
          'WHERE namespace=%s AND seq=%s',(h.ticket.namespace,int(os.environ['OMI_UC_SEQ']))).fetchone()
    ColdSink(h).apply(row,timeout=1.5)
else:
    uid,cid=os.environ['OMI_UC_UID'],os.environ['OMI_UC_CID']
    r=RetainedCopies(h)
    identity,manifest=r.inventory(uid,cid)[0]
    authority=legal_holds.UnitAuthority(uid,'explicit_memory_deletion',os.environ['OMI_UC_TOKEN'],client,None)
    erase_recording(r,uid,identity,manifest,authority,conversation=cid)
raise AssertionError('no upload cold COMMIT')
"""
    child = subprocess.run(
        [sys.executable, '-c', command],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            'OMI_UC_DSN': dsn,
            'OMI_UC_NS': c.handoff.ticket.namespace,
            'OMI_UC_UID': c.uid,
            'OMI_UC_CID': cid,
            'OMI_UC_TOKEN': token,
            'OMI_UC_OP': operation,
            'OMI_UC_GAP': gap,
            'OMI_UC_SEQ': str(target[0]),
        },
    )
    assert child.returncode == 86, child.stderr
    if operation == 'copy':
        assert c.sink.ref(target[2], target[3]).get().exists == (gap == 'after')
        for _ in range(64):
            try:
                c.sink.apply(target, timeout=1.5)
                break
            except GoogleAPICallError:
                assert gap == 'before'
        else:
            pytest.fail('abandoned upload read lease exceeded bounded redelivery')
    else:
        assert c.sink.barrier(identity).get().exists == (gap == 'after')
        for _ in range(12):
            try:
                with unit(c) as successor:
                    assert successor.token != token
                    erase_recording(retained, c.uid, identity, manifest, successor, conversation=cid)
                break
            except (ValueError, Aborted) as error:
                assert gap == 'before' and (isinstance(error, Aborted) or isinstance(error.__cause__, Aborted))
        else:
            pytest.fail('abandoned upload erasure read lease exceeded bounded redelivery')
        c.sink.apply(target, timeout=1.5)
        assert not c.sink.ref(target[2], target[3]).get().exists
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM queue_upload_cold_custody WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (1,)
        assert conn.execute(
            'SELECT count(*) FROM units WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (1,)
    assert c.handoff.client.collection(c.handoff.ticket.namespace + '_intakes').document(c.identity).get().exists
