"""Owner cancellation of a legacy upload held in cap holds (the paid-only recovery path).

The memory store commits each ``run`` atomically, as one Firestore transaction
does, so a recovery claim and the fence are real interleavings of committed
writes. The recovery claim below uses cap_hold's own unclaimable-state set.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import Mock

import pytest

from database.cap_hold_redrive import PENDING_STATES as REDRIVE_STATES
from utils.batch_pipeline import owner_cancel
from utils.batch_pipeline.owner_cancel import Outcome
from utils.sync import cap_hold, legacy_dark, owner_cancel_legacy

OWNER = 'owner-synthetic'
OTHER = 'other-synthetic'
JOB = 'legacy-upload-1'
CONTENT = 'content-legacy-1'
NOW = 1_000.0


class MemoryLegacyStore:
    def __init__(self):
        self.rows: dict[tuple[str, str, str], dict] = {}

    def find_content(self, uid, job_id):
        found = [
            key
            for (kind, owner, key), row in self.rows.items()
            if kind == 'ledger' and owner == uid and row.get('job_id') == job_id
        ]
        return found[0] if len(found) == 1 else None

    def run(self, fn):
        staged = deepcopy(self.rows)
        store = self

        class Tx:
            def get(self, kind, uid, key):
                return deepcopy(staged.get((kind, uid, key), {}))

            def put(self, kind, uid, key, row):
                staged[(kind, uid, key)] = deepcopy(row)

        result = fn(Tx())
        store.rows = staged
        return result


class FakeLegacyEraser:
    def __init__(self, store, *, fail_holds=0):
        self.store = store
        self.fail_holds = fail_holds
        self.erased = []
        self.archives = []
        self.archive_paths = ()

    def erase_hold(self, uid, hold_id):
        row = self.store.rows.get(('hold', uid, hold_id))
        if row is None:
            return
        if not owner_cancel_legacy.is_owner_cancelled_hold(row):
            raise AssertionError('eraser must never touch a hold the fence did not mark')
        if self.fail_holds:
            self.fail_holds -= 1
            raise RuntimeError('storage unavailable')
        self.erased.append(row['audio_path'])
        del self.store.rows[('hold', uid, hold_id)]

    def erase_archives(self, uid, job_id, paths=()):
        self.archives.append((uid, job_id))
        self.archive_paths = paths


def hold(seconds, **extra):
    return {
        'state': 'held',
        'seconds': seconds,
        'audio_path': f'chunks/{OWNER}/cap-held/{seconds}.wav.enc',
        'lease_until': 0,
        'next_attempt_at': 0,
        'listed_at': 500,
        **extra,
    }


def held_upload(store, holds=None, **ledger):
    holds = {'h1': hold(30), 'h2': hold(10, state='retained', failed_reconciliation=True)} if holds is None else holds
    for hold_id, row in holds.items():
        store.rows[('hold', OWNER, hold_id)] = row
    store.rows[('summary', OWNER, 'current')] = {'version': 2, 'seconds': 100.0, 'count': 5}
    store.rows[('ledger', OWNER, CONTENT)] = {
        'job_id': JOB,
        'status': 'held',
        'dispatch_protocol': 'stt_cap_hold_v1',
        'cap_hold_ids': sorted([*holds, 'h-settled']),
        'pending_cap_hold_ids': sorted(holds),
        'result': {'held_audio': True, 'new_memories': [], 'updated_memories': []},
        **ledger,
    }


def cancel(store, eraser=None, *, uid=OWNER, job_id=JOB, now=NOW):
    eraser = eraser or FakeLegacyEraser(store)
    return owner_cancel.cancel_owner_upload(uid, job_id, store=None, eraser=eraser, legacy=store, now=now)


def recovery_claim(store, hold_id, now, lease=1800):
    """cap_hold.claim's predicate and write, committed as one transaction."""

    def commit(tx):
        row = tx.get('hold', OWNER, hold_id)
        if (
            not row
            or row.get('state') in cap_hold.UNCLAIMABLE_STATES
            or row.get('lease_until', 0) > now
            or row.get('next_attempt_at', 0) > now
        ):
            return False
        tx.put('hold', OWNER, hold_id, {**row, 'lease_until': now + lease, 'lease_token': 'worker'})
        return True

    return store.run(commit)


def test_held_legacy_upload_is_fenced_and_every_copy_erased():
    store = MemoryLegacyStore()
    held_upload(store)
    eraser = FakeLegacyEraser(store)
    result = cancel(store, eraser)
    assert result.outcome is Outcome.CANCELLED and result.erasure == 'complete'
    assert sorted(eraser.erased) == [f'chunks/{OWNER}/cap-held/10.wav.enc', f'chunks/{OWNER}/cap-held/30.wav.enc']
    assert eraser.archives == [(OWNER, JOB)]
    assert ('hold', OWNER, 'h1') not in store.rows and ('hold', OWNER, 'h2') not in store.rows
    # Both holds had audio waiting; the card's running total drops by exactly that.
    assert store.rows[('summary', OWNER, 'current')] == {'version': 2, 'seconds': 60.0, 'count': 3}
    ledger = store.rows[('ledger', OWNER, CONTENT)]
    assert ledger['status'] == 'owner_cancelled' and ledger['pending_cap_hold_ids'] == []
    assert ledger['owner_cancel_erased_at'] == NOW and ledger['expires_at'] is not None
    # Idempotent: the same answer, nothing rewritten, nothing erased twice.
    before = deepcopy(store.rows)
    again = FakeLegacyEraser(store)
    assert cancel(store, again, now=NOW + 5) == result
    assert store.rows == before and again.erased == [] and again.archives == []


@pytest.mark.parametrize(
    'busy',
    [
        hold(30, lease_until=NOW + 60, lease_token='worker'),  # recovery claimed it and is transcribing
        hold(30, state='completed', lease_until=0),  # transcribed; recovery is settling it
        hold(30, state='batch_admitted', batch_job_id='bp_handoff'),  # handed to batch
        hold(30, state='staging'),
        hold(30, state='sealing'),
    ],
)
def test_hold_mid_recovery_answers_in_progress_and_is_untouched(busy):
    store = MemoryLegacyStore()
    held_upload(store, {'h1': hold(20), 'h2': busy})
    before = deepcopy(store.rows)
    eraser = FakeLegacyEraser(store)
    assert cancel(store, eraser).outcome is Outcome.IN_PROGRESS
    assert store.rows == before
    assert eraser.erased == [] and eraser.archives == []


def test_recovery_claim_and_fence_serialise_whichever_commits_first():
    store = MemoryLegacyStore()
    held_upload(store, {'h1': hold(30)})
    # Recovery wins: the fence answers 409 and writes nothing.
    assert recovery_claim(store, 'h1', NOW)
    assert cancel(store).outcome is Outcome.IN_PROGRESS
    # The worker releases without finishing (lease cleared): the next delete fences it.
    store.rows[('hold', OWNER, 'h1')].update(lease_until=0, lease_token='')
    assert cancel(store, now=NOW + 10).outcome is Outcome.CANCELLED

    # Fence wins: a later recovery claim, listing or redrive never reaches the hold.
    store = MemoryLegacyStore()
    held_upload(store, {'h1': hold(30)})
    eraser = FakeLegacyEraser(store, fail_holds=1)
    assert cancel(store, eraser).erasure == 'pending'
    fenced = store.rows[('hold', OWNER, 'h1')]
    assert fenced['state'] == cap_hold.OWNER_CANCELLED_STATE and fenced['owner_cancelled_from'] == 'held'
    assert not recovery_claim(store, 'h1', NOW + 3600)
    assert fenced['state'] not in ('held', 'retained', 'staging', 'sealing')  # held list and backlog queries
    assert fenced['state'] not in REDRIVE_STATES
    assert cap_hold.remaining_seconds(fenced) == 0


def test_erasure_failure_keeps_earlier_archive_reachable_past_receipt_ttl():
    store = MemoryLegacyStore()
    earlier_archive = f'raw-mobile-batch/{OWNER}/a/prior.bin'
    held_upload(store, raw_capture_paths=[earlier_archive], expires_at=datetime.fromtimestamp(NOW, timezone.utc))
    first = cancel(store, FakeLegacyEraser(store, fail_holds=1))
    assert first.outcome is Outcome.CANCELLED and first.erasure == 'pending'
    ledger = store.rows[('ledger', OWNER, CONTENT)]
    assert 'expires_at' not in ledger
    assert 'owner_cancel_erased_at' not in ledger
    assert ledger['raw_capture_paths'] == [earlier_archive]
    retry = FakeLegacyEraser(store)
    retry_at = NOW + timedelta(days=46).total_seconds()
    assert cancel(store, retry, now=retry_at).erasure == 'complete'
    assert len(retry.erased) == 2 and retry.archives == [(OWNER, JOB)]
    assert retry.archive_paths == (earlier_archive,)
    ledger = store.rows[('ledger', OWNER, CONTENT)]
    assert 'raw_capture_paths' not in ledger
    assert ledger['expires_at'] == datetime.fromtimestamp(retry_at, timezone.utc) + timedelta(days=45)


@pytest.mark.parametrize('mode', tuple(legacy_dark.LegacySyncMode))
def test_cancelled_legacy_content_is_terminal_in_duplicate_admission(mode):
    from database import sync_ledger

    store = MemoryLegacyStore()
    held_upload(store)
    assert cancel(store).erasure == 'complete'
    ledger = store.rows['ledger', OWNER, CONTENT]
    after_stale = ledger['updated_at'] + timedelta(days=3)
    decision = legacy_dark.fence_decision(ledger, mode, now=after_stale, batch_adopts_stranded=True)
    response = legacy_dark.fence_response(decision, total_files=1, lane='fresh')
    assert response.status_code == 202
    assert json.loads(response.body)['reason_code'] == 'owner_cancelled'
    assert json.loads(response.body)['job_id'] == JOB

    ref, transaction = Mock(), Mock()
    ref.get.return_value.to_dict.return_value = ledger
    wrapped = getattr(sync_ledger._claim_transaction, 'to_wrap', sync_ledger._claim_transaction)
    assert wrapped(transaction, ref, 'duplicate', 'fresh', after_stale, missing_owner=JOB) == {
        'outcome': 'owner_cancelled',
        'job_id': JOB,
    }
    transaction.set.assert_not_called()


def test_completed_legacy_content_is_already_processed_and_untouched():
    store = MemoryLegacyStore()
    held_upload(
        store,
        status='completed',
        result={
            'new_memories': ['conv-1'],
            'updated_memories': [],
            'failed_segments': 0,
            'total_segments': 1,
            'errors': [],
        },
    )
    before = deepcopy(store.rows)
    result = cancel(store)
    assert result.outcome is Outcome.ALREADY_PROCESSED and result.conversation_ids == ('conv-1',)
    assert store.rows == before


@pytest.mark.parametrize('purged', [False, True])
@pytest.mark.parametrize('projected', [False, True])
def test_gone_legacy_holds_do_not_fence_the_ledger(purged, projected):
    from utils.batch_pipeline.cap_hold_admission import held_content_id

    store = MemoryLegacyStore()
    held_upload(store, {'h1': hold(30, state='purged')} if purged else {}, cap_hold_ids=['h1'])
    if projected:
        store.rows['ledger', OWNER, held_content_id(OWNER, 'h1')] = {
            'status': 'completed',
            'result': {
                'new_memories': ['conv-1'],
                'updated_memories': [],
                'failed_segments': 0,
                'total_segments': 1,
                'errors': [],
            },
        }
    before = deepcopy(store.rows)
    result = cancel(store)
    assert result.outcome is (Outcome.ALREADY_PROCESSED if projected else Outcome.NOT_CANCELLABLE)
    assert result.conversation_ids == (('conv-1',) if projected else ())
    assert store.rows == before


def test_foreign_unknown_and_non_hold_legacy_handles_write_nothing():
    store = MemoryLegacyStore()
    held_upload(store)
    before = deepcopy(store.rows)
    assert cancel(store, uid=OTHER).outcome is Outcome.NOT_FOUND
    assert cancel(store, job_id='legacy-unknown').outcome is Outcome.NOT_FOUND
    assert cancel(store, job_id='a/b').outcome is Outcome.NOT_FOUND
    assert store.rows == before
    # Legacy content that is not held (an abandoned claim) is not erased here.
    store.rows[('ledger', OWNER, CONTENT)].update(status='processing', dispatch_protocol=None)
    before = deepcopy(store.rows)
    assert cancel(store).outcome is Outcome.NOT_CANCELLABLE
    assert store.rows == before


def test_summary_mid_rebuild_is_left_to_the_rebuild():
    store = MemoryLegacyStore()
    held_upload(store)
    store.rows[('summary', OWNER, 'current')] = {'version': 1, 'build_owner': 'rebuild'}
    assert cancel(store, FakeLegacyEraser(store, fail_holds=1)).erasure == 'pending'
    assert store.rows[('summary', OWNER, 'current')] == {'version': 1, 'build_owner': 'rebuild'}
    assert cap_hold.remaining_seconds(store.rows['hold', OWNER, 'h2']) == 0


def test_without_a_legacy_store_a_legacy_handle_is_not_found():
    assert owner_cancel.cancel_owner_upload(OWNER, JOB, store=None, eraser=None, now=NOW).outcome is Outcome.NOT_FOUND


class _Snapshot:
    def __init__(self, row):
        self.exists = row is not None
        self._row = row

    def to_dict(self):
        return deepcopy(self._row)


class _Holds:
    def __init__(self, rows):
        self.rows = rows

    def document(self, hold_id):
        rows = self.rows

        class Ref:
            def get(self):
                return _Snapshot(rows.get(hold_id))

        return Ref()


@pytest.mark.parametrize('row', [hold(30), hold(30, state='retained'), {**hold(30), 'state': 'owner_cancelled'}])
def test_production_eraser_refuses_a_hold_the_fence_did_not_write(monkeypatch, row):
    from utils.sync import cap_hold_erasure

    monkeypatch.setattr(cap_hold, 'holds', lambda uid: _Holds({'h1': row}))
    monkeypatch.setattr(cap_hold_erasure, 'erase', lambda *a: pytest.fail('must not erase'))
    with pytest.raises(owner_cancel_legacy.HoldNotFenced):
        owner_cancel_legacy.FirestoreLegacyEraser().erase_hold(OWNER, 'h1')


def test_production_eraser_erases_a_fenced_hold_and_skips_gone_ones(monkeypatch):
    from utils.batch_pipeline import owner_cancel_erase
    from utils.sync import cap_hold_erasure

    fenced = {**hold(30), 'state': 'owner_cancelled', 'owner_cancelled_at': NOW}
    rows = {'h1': fenced, 'h2': {'state': 'purged'}}
    monkeypatch.setattr(cap_hold, 'holds', lambda uid: _Holds(rows))
    erased = []
    monkeypatch.setattr(cap_hold_erasure, 'erase', lambda uid, snapshot, row: erased.append((uid, row['audio_path'])))
    archives = []
    eraser = owner_cancel_erase.FirestoreEraser(
        'batch_pipeline_prod', client=object(), delete_archives=lambda uid, raw, paths: archives.append((uid, raw)) or 0
    )
    for hold_id in ('h1', 'h2', 'missing'):
        eraser.erase_hold(OWNER, hold_id)
    eraser.erase_archives(OWNER, JOB)
    assert erased == [(OWNER, fenced['audio_path'])]
    assert archives == [(OWNER, JOB)]  # a legacy handle is the archived upload id itself
