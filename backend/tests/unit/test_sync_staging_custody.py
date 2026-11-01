from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import NotFound

from database import _client, sync_ledger
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.other import local_storage, storage
from utils.sync import staging_custody as custody


@pytest.fixture
def local_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stamp = int(datetime(2026, 10, 24, 8, tzinfo=timezone.utc).timestamp())
    raw = f'syncing/synthetic/job/audio_pcm16_{stamp}.bin'
    fragment = f'syncing/synthetic/job/{stamp}.wav'
    Path(raw).parent.mkdir(parents=True)
    Path(raw).write_bytes(b'synthetic original')
    Path(fragment).write_bytes(b'synthetic derived wave')
    sha = hashlib.sha256(Path(raw).read_bytes()).hexdigest()
    archive = f'raw-sync/synthetic/{Path(raw).name}/{sha}.bin.enc'
    receipt = custody.make_staging_custody_receipt('synthetic', [raw], [archive])
    receipt = custody.add_staging_derivatives('synthetic', receipt, [fragment])
    return raw, fragment, archive, receipt


@pytest.fixture
def cleanup(local_receipt, monkeypatch):
    monkeypatch.delenv('AUDIO_CLEANUP_HOLD_ENABLED', raising=False)
    monkeypatch.delenv('AUDIO_CLEANUP_HOLD_WINDOWS', raising=False)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    raw, fragment, archive, receipt = local_receipt
    ledger = {
        'job_id': 'job',
        'status': 'completed',
        'staging_custody': receipt,
        'result': {
            'total_segments': 1,
            'failed_segments': 0,
            'errors': [],
            'outcome': 'success',
        },
    }
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: None)
    ref = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: ledger))
    monkeypatch.setattr(sync_ledger, 'sync_content_reference', lambda *args: ref)
    blobs = {
        name: Mock(generation='42', md5_hash=item['md5']) for name, item in [(x['path'], x) for x in receipt['staging']]
    }
    blobs[archive] = Mock(metadata={'sha256': receipt['originals'][0]['sha256']})
    client = Mock()
    client.bucket.return_value.blob.side_effect = lambda path: blobs[path]
    monkeypatch.setattr(storage, '_get_storage_client', lambda: client)
    monkeypatch.setattr(local_storage, 'create_storage_client', lambda: client)
    monkeypatch.setattr(storage, 'syncing_local_bucket', 'staging')
    monkeypatch.setattr(storage, 'private_cloud_sync_bucket', 'archive')
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda *args: nullcontext())

    def run(paths=None):
        return custody.cleanup_sync_staging(
            paths or [raw, fragment], uid='synthetic', content_id='content', job_id='job'
        )

    return run, ledger, blobs, client


def test_receipt_binds_original_bytes_and_derivatives(local_receipt):
    raw, fragment, archive, receipt = local_receipt
    assert receipt['originals'][0]['archive'] == archive
    assert {item['path'] for item in receipt['staging']} == {raw, fragment}
    assert custody.make_staging_custody_receipt('synthetic', [raw], []) is None
    Path(raw).write_bytes(b'different original')
    assert custody.make_staging_custody_receipt('synthetic', [raw], [archive]) is None


def test_only_durable_success_plus_existing_archive_authorizes_generation_pinned_deletion(cleanup, local_receipt):
    run, _, blobs, _ = cleanup
    raw, fragment, _, _ = local_receipt
    assert run() == 2
    for path in (raw, fragment):
        blobs[path].delete.assert_called_once_with(if_generation_match=42)


@pytest.mark.parametrize('status', ['processing', 'failed', 'partial', 'held'])
def test_failure_or_retry_long_after_eight_minutes_keeps_staging(cleanup, status):
    run, ledger, blobs, _ = cleanup
    ledger['status'] = status
    assert run() == 0
    assert not any(blob.delete.called for blob in blobs.values())


@pytest.mark.parametrize('change', ['held', 'failed_segment', 'wrong_job', 'no_receipt'])
def test_completed_label_cannot_hide_incomplete_custody(cleanup, change):
    run, ledger, blobs, _ = cleanup
    if change == 'held':
        ledger['result']['held_audio'] = True
    elif change == 'failed_segment':
        ledger['result']['failed_segments'] = 1
    elif change == 'wrong_job':
        ledger['job_id'] = 'replacement'
    else:
        ledger.pop('staging_custody')
    assert run() == 0
    assert not any(blob.delete.called for blob in blobs.values())


def test_legacy_timer_and_terminal_cleanup_without_receipt_have_no_delete_authority(cleanup, local_receipt):
    _, _, blobs, client = cleanup
    assert custody.cleanup_sync_staging([local_receipt[0]]) == 0
    client.bucket.assert_not_called()
    assert not any(blob.delete.called for blob in blobs.values())


def test_missing_or_mismatched_archive_preserves_every_staged_byte(cleanup, local_receipt):
    run, _, blobs, _ = cleanup
    archive = blobs[local_receipt[2]]
    archive.metadata = {'sha256': 'different'}
    assert run() == 0
    archive.reload.side_effect = NotFound('archive erased')
    with pytest.raises(NotFound):
        run()
    assert not any(blob.delete.called for blob in blobs.values())


def test_replaced_staging_generation_is_preserved(cleanup, local_receipt):
    run, _, blobs, _ = cleanup
    raw, fragment, _, _ = local_receipt
    blobs[raw].md5_hash = 'different'
    assert run() == 1
    blobs[raw].delete.assert_not_called()
    blobs[fragment].delete.assert_called_once_with(if_generation_match=42)


@pytest.mark.parametrize('attribute', ['md5_hash', 'generation'])
def test_storage_without_checksum_or_generation_cannot_authorize_deletion(cleanup, local_receipt, attribute):
    run, _, blobs, _ = cleanup
    raw, fragment, _, _ = local_receipt
    delattr(blobs[raw], attribute)
    assert run() == 1
    blobs[raw].delete.assert_not_called()
    blobs[fragment].delete.assert_called_once_with(if_generation_match=42)


def test_hold_applies_to_original_capture_even_when_fragment_is_later(cleanup, local_receipt, monkeypatch):
    run, _, blobs, _ = cleanup
    monkeypatch.setenv('AUDIO_CLEANUP_HOLD_WINDOWS', '2026-10-24T08:00:00Z..2026-10-24T09:00:00Z')
    assert run() == 0
    assert not any(blob.delete.called for blob in blobs.values())
    monkeypatch.setenv('AUDIO_CLEANUP_HOLD_ENABLED', 'false')
    assert run() == 2


def test_unlisted_or_cross_owner_paths_are_preserved(cleanup):
    run, _, blobs, _ = cleanup
    assert run(['syncing/other/job/audio.bin']) == 0
    assert not any(blob.delete.called for blob in blobs.values())


def test_custody_receipt_shares_the_owner_fenced_completion_transaction(local_receipt):
    client = StrictFirestore()
    ref = client.collection('ledger').document('content')
    ref.create({'job_id': 'job', 'status': 'processing', 'ledger_run_token': '1:token', 'ledger_run_epoch': 1})
    result = {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'}
    now = datetime.now(timezone.utc)

    def transaction():
        tx = client.transaction()

        def merge_existing(reference, values, *, merge):
            # This boundary has just read an existing, owner-matching row;
            # merge-set has update semantics here. Keep strict read ordering.
            assert merge is True and reference.get(transaction=tx).exists
            tx.update(reference, values)

        tx.set = merge_existing
        return tx

    assert not sync_ledger._mark_completed_transaction.to_wrap(
        transaction(), ref, 'other', result, now, '1:token', 1, local_receipt[3]
    )
    assert 'staging_custody' not in ref.get().to_dict()
    assert sync_ledger._mark_completed_transaction.to_wrap(
        transaction(), ref, 'job', result, now, '1:token', 1, local_receipt[3]
    )
    completed = ref.get().to_dict()
    assert completed['status'] == 'completed'
    assert completed['staging_custody'] == local_receipt[3]
    assert 'staging_custody' not in completed['result']
