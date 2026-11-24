"""Commit observations require the complete write group from the account writer."""

import hashlib

from google.cloud.firestore_v1.types import (
    CommitRequest,
    CommitResponse,
    Document,
    DocumentMask,
    Precondition,
    Value,
    Write,
)
import pytest

from database import batch_privacy_write_fence as fence
from database.privacy_check_metrics import ACCOUNT_AUTHORITY_WRITES

ROOT = 'projects/demo-privacy/databases/(default)/documents'
USER = f'{ROOT}/users/synthetic'
OWNER = f'{ROOT}/batch_pipeline_privacy/{hashlib.sha256(b"synthetic").hexdigest()}'


def patch(path, field, value):
    return Write(update=Document(name=path, fields={field: value}), update_mask=DocumentMask(field_paths=[field]))


def source():
    return patch(USER, 'private_cloud_sync_enabled', Value(boolean_value=False))


def mutation():
    epoch = Value(integer_value=3)
    receipt = Write(
        update=Document(name=f'{OWNER}/account_operations/{"a" * 64}', fields={'account_epoch': epoch}),
        current_document=Precondition(exists=False),
    )
    return [
        source(),
        patch(OWNER, 'account_epoch', epoch),
        patch(f'{OWNER}/account_authority/head', 'account_epoch', epoch),
        receipt,
    ]


def test_only_complete_same_owner_transaction_certifies_each_write():
    request = CommitRequest(writes=[source(), *mutation(), source()], transaction=b'tx')
    assert fence.account_write_observations(request) == [
        ('users', 'cloud_sync', False),
        ('users', 'cloud_sync', True),
        ('users', 'cloud_sync', False),
    ]
    assert fence.account_write_observations(CommitRequest(writes=mutation())) == [('users', 'cloud_sync', False)]
    for index in range(1, 4):
        incomplete = mutation()
        del incomplete[index]
        assert fence.account_write_observations(CommitRequest(writes=incomplete, transaction=b'tx')) == [
            ('users', 'cloud_sync', False)
        ]
    wrong_plane = mutation()
    wrong_plane[3].update.name = wrong_plane[3].update.name.replace('projects/demo-privacy', 'projects/demo-other')
    assert fence.account_write_observations(CommitRequest(writes=wrong_plane, transaction=b'tx')) == [
        ('users', 'cloud_sync', False)
    ]
    assert fence.account_write_observations(
        CommitRequest(writes=[source(), patch(OWNER, 'generation', Value(integer_value=3))], transaction=b'tx')
    ) == [('users', 'cloud_sync', False)]


def test_existing_metadata_and_speaker_changes_do_not_change_batch_account_facts():
    writes = []
    for document, field in (
        (USER, 'speaker_auto_enroll_privacy_version'),
        (f'{ROOT}/account_deletions/synthetic', 'wipe_running_at'),
    ):
        write = patch(document, field, Value(integer_value=3))
        write.current_document = Precondition(exists=True)
        writes.append(write)
    writes.extend((Write(delete=USER), patch(USER, 'last_seen', Value(integer_value=3))))
    assert fence.account_write_observations(CommitRequest(writes=writes)) == [
        ('users', 'existence', False),
        ('users', 'existence', False),
    ]


def test_sync_counts_successes_only(monkeypatch):
    metric = ACCOUNT_AUTHORITY_WRITES.labels('users', 'cloud_sync', 'false')
    before = metric._value.get()
    monkeypatch.setenv('BATCH_ACCOUNT_PRIVACY_WRITER_ENABLED', 'false')

    def commit(client, request):
        if request.transaction:
            raise RuntimeError('synthetic commit failure')
        return CommitResponse()

    wrapped = fence._wrap_commit(commit)
    with pytest.raises(RuntimeError, match='synthetic commit failure'):
        wrapped(None, CommitRequest(writes=[source()], transaction=b'tx'))
    assert metric._value.get() == before
    wrapped(None, writes=[source()])
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_async_counts_certified_writes_without_counting_an_uncertified_write():
    yes = ACCOUNT_AUTHORITY_WRITES.labels('users', 'cloud_sync', 'true')
    no = ACCOUNT_AUTHORITY_WRITES.labels('users', 'cloud_sync', 'false')
    before = (yes._value.get(), no._value.get())

    async def commit(client, request):
        return CommitResponse()

    await fence._wrap_commit(commit)(None, CommitRequest(writes=mutation(), transaction=b'tx'))
    assert (yes._value.get(), no._value.get()) == (before[0] + 1, before[1])
