"""Abrupt exits around the actual original handoff metadata COMMIT."""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from database import legal_holds
from database.jobstore.original_copies import OriginalCopies
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401
from tests.integration.test_jobstore_retained_copies import retained  # noqa: F401
from tests.integration.test_jobstore_original_copies import objects, prepared, unit  # noqa: F401
from utils.batch_pipeline.retention import delete_batch_object

pytestmark = [pytest.mark.integration, pytest.mark.parametrize('lane', [True], indirect=True)]


@pytest.mark.parametrize('gap', ['before', 'after'])
def test_original_metadata_commit_exit_preserves_intake_and_pg_custodian(retained, objects, gap):
    r = retained
    with unit(r) as authority:
        operations, first = prepared(r, authority)
        original = OriginalCopies(r.purge)
        row, _, uris = original._plan(r.uid, r.view.identity, r.conversation)
        for i, uri in enumerate(uris):
            target = (
                first
                if i == 0
                else operations.prepare(
                    r.uid,
                    r.view.identity,
                    authority,
                    'object',
                    dict(uri=uri, completion_hash=row['completion_hash']),
                    conversation=r.conversation,
                )
            )
            authority.remote(lambda: delete_batch_object(r.uid, uri, storage_client=objects.storage), target=uri)
            authority.remote(
                lambda: operations.finish(r.uid, target, authority, conversation=r.conversation), target=target
            )
        token = authority.token
    assert not objects.left
    legal_holds.acquire_destructive_operation(
        r.uid,
        kind='explicit_memory_deletion',
        token=token,
        firestore_client=r.handoff.client,
        now=datetime.now(timezone.utc) - timedelta(seconds=2 * legal_holds.UNIT_EXPIRY_SECONDS),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=legal_holds.UNIT_EXPIRY_SECONDS),
    )
    with r.handoff.pool.connection() as conn:
        dsn = conn.info.dsn
    command = """
import os
import testing.pipeline_sim._env
from google.cloud.firestore_v1.types import CommitRequest
from database import legal_holds
from database.jobstore.connection import Pool
from database.jobstore.handoff import Handoff
from database.jobstore.authority import Epoch
from database.jobstore.retained_copies import RetainedCopies
from database.jobstore.original_copies import OriginalCopies
from database.privacy_fence import Fence
from testing.store_fixtures import _emulator_client
pool=Pool(os.environ['OMI_META_DSN'],size=2)
client=_emulator_client()
handoff=Handoff(pool,Fence(pool),client,Epoch(os.environ['OMI_META_NS'],3))
uid,cid=os.environ['OMI_META_UID'],os.environ['OMI_META_CID']
authority=legal_holds.UnitAuthority(uid,'explicit_memory_deletion',os.environ['OMI_META_TOKEN'],client,None)
api=client._firestore_api
real=api.commit
def commit(*a,**k):
    request=CommitRequest(k.get('request') or a[0])
    erasing=any(w.delete.endswith('/'+handoff.ref('intent','recording').id) for w in request.writes)
    if erasing and os.environ['OMI_META_GAP']=='before':os._exit(86)
    result=real(*a,**k)
    if erasing:os._exit(86)
    return result
api.commit=commit
OriginalCopies(RetainedCopies(handoff)).retire(uid,'recording',authority,conversation=cid)
raise AssertionError('did not exit at metadata COMMIT')
"""
    result = subprocess.run(
        [sys.executable, '-c', command],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            'OMI_META_DSN': dsn,
            'OMI_META_NS': r.handoff.ticket.namespace,
            'OMI_META_UID': r.uid,
            'OMI_META_CID': r.conversation,
            'OMI_META_TOKEN': token,
            'OMI_META_GAP': gap,
        },
    )
    assert result.returncode == 86, result.stderr
    assert r.handoff.ref('intent', r.view.identity).get().exists == (gap == 'before')
    assert r.view.ref('intakes', r.view.identity).get().exists
    from google.api_core.exceptions import Aborted

    for _ in range(12):
        try:
            with unit(r) as successor:
                assert successor.token != token
                original.retire(r.uid, r.view.identity, successor, conversation=r.conversation)
            break
        except (ValueError, Aborted) as error:
            assert gap == 'before' and (isinstance(error, Aborted) or isinstance(error.__cause__, Aborted))
    else:
        pytest.fail('abandoned original metadata read lease exceeded bounded redelivery')
    assert not r.handoff.ref('intent', r.view.identity).get().exists
    assert r.view.ref('intakes', r.view.identity).get().to_dict()['repair_lineage'] == 'synthetic-original'
    with r.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT count(*) FROM units WHERE namespace=%s', (r.handoff.ticket.namespace,)
        ).fetchone() == (2,)
