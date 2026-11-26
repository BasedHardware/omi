"""Sealed owner scans using existing obligation leases and per-member journals.

No new collection or task protocol: ``owner_scan`` lives on the leader's normal
obligation. Only fresh obligations are enrolled; partial legacy runs keep their
cursor and finish independently. Every member's legacy progress stays untouched.
The coalescing kill switch gates enrollment. The workspace release floor excludes
old binaries that cannot fence a re-arm after taking over an expired member.
Switch-off handback retains each member's journal.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator
from uuid import uuid4

from google.cloud import firestore

from config.policy.kill_switches import kill_switch
from database import conversation_batch_purge_jobs as jobs
from database import legal_holds, rpc_deadline
from database.privacy_check_metrics import PURGE_COMPLETED
from database._client import get_firestore_client, run_transactional
from database.batch_pipeline_conversation_purge import (
    ArtifactUploadPending,
    PurgeCheckpointed,
    PurgeIntentMissing,
    purge_conversations,
)
from database.batch_pipeline_purge import NAMESPACES
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
MAX_MEMBERS = 16
ASSOCIATION_CHUNK = 100
SWITCH = 'CONVERSATION_BATCH_PURGE_COALESCING_ENABLED'


def _audit_group(kind: str, outcome: str, epoch: str, members: int) -> None:
    logger.warning(
        'event=conversation_batch_purge_owner_scan_audit kind=%s outcome=%s members=%d epoch_hash=%s',
        kind,
        outcome,
        members,
        sha256(epoch.encode()).hexdigest(),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _in_transaction(client: Any, body: Callable[[Any], Any]) -> Any:
    @firestore.transactional
    def run(transaction):
        return body(transaction)

    return run_transactional(client, run, transient=True)


def enabled() -> bool:
    return kill_switch(SWITCH, log=False)


def owner_candidates(uid: str, *, firestore_client: Any = None) -> list[Any]:
    """Bounded single-field owner lookup; eligibility is re-proved transactionally.

    Only a sealed group, not an unbounded owner's entire deletion backlog, is
    held in memory. Overflow is served by later deliveries/groups.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return list(
        client.collection(jobs.COLLECTION)
        .where(filter=firestore.FieldFilter('uid', '==', uid))
        .limit(MAX_MEMBERS)
        .stream()
    )


def _ref(client: Any, job: str) -> Any:
    return client.collection(jobs.COLLECTION).document(job)


def _arm(row: dict[str, Any]) -> tuple[Any, Any]:
    # armed_at also detects re-arms by older producers that know no revision field.
    return row.get('armed_at'), row.get('arm_revision')


def _same_arm(row: dict[str, Any], member: dict[str, Any]) -> bool:
    return _arm(row) == _arm(member)


def _delegated(row: dict[str, Any], scan: dict[str, Any], member: dict[str, Any]) -> bool:
    return (
        row.get('scan_epoch') == scan['epoch']
        and int(row.get('generation') or 0) == member['generation']
        and row.get('run_token') == scan['token']
    )


def _read_members(client: Any, transaction: Any, scan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {job: (_ref(client, job).get(transaction=transaction).to_dict() or {}) for job in scan['members']}


def handback(client: Any, leader: str, epoch: str, token: str) -> bool:
    """Fence the shared run and release only its still-delegated members.

    Journals and legacy progress were never moved, so nothing needs copying.
    A member already taken over by an old worker is left to that owner.
    """

    def body(transaction):
        ref = _ref(client, leader)
        row = ref.get(transaction=transaction).to_dict() or {}
        scan: dict[str, Any] = row.get('owner_scan') or {}
        if scan.get('epoch') != epoch or scan.get('token') != token:
            return 0
        rows = _read_members(client, transaction, scan)
        for job, member in scan['members'].items():
            current = rows[job]
            if current.get('scan_epoch') != epoch:
                continue
            # Never release a lease claimed by somebody else after expiry.
            owned = _delegated(current, scan, member)
            changes: dict[str, Any] = {'scan_epoch': None, 'scan_leader': None}
            if job == leader:
                changes['owner_scan'] = None
            if owned:
                changes.update(run_token=None, lease_generation=None, lease_until=None, due_at=_now())
            transaction.update(_ref(client, job), changes)
        return len(scan['members'])

    changed = _in_transaction(client, body)
    if changed:
        _audit_group('terminal', 'handed_back', epoch, changed)
        record_fallback(
            component='other',
            from_mode='coalesced_owner_scan',
            to_mode='per_conversation_purge',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    return bool(changed)


def _claim(client: Any, job: str, generation: int) -> tuple[str, dict[str, Any] | None]:
    row = _ref(client, job).get().to_dict() or {}
    if not row:
        return 'missing', None
    if int(row.get('generation') or 0) != generation:
        return 'superseded', None
    coalescing = enabled()
    leader = row.get('scan_leader')
    if leader:
        leader_row = row if leader == job else _ref(client, leader).get().to_dict() or {}
        scan = leader_row.get('owner_scan') or {}
        if scan.get('epoch') is not None and scan.get('epoch') == row.get('scan_epoch'):
            if not coalescing:
                handback(client, leader, scan['epoch'], scan['token'])
                return 'legacy', None
            if leader != job:
                # The named leader alone resumes a live scan. An expired
                # follower delivery must fall back, never inherit its cursor.
                if jobs.lease_held(leader_row):
                    return 'in_progress', None
                handback(client, leader, scan['epoch'], scan['token'])
                return 'legacy', None
            return _resume(client, job, generation, scan)
        # A legacy leader may have completed after lease expiry. Its followers
        # keep their own journals and resume independently.
        return 'legacy', None
    if not coalescing or row.get('progress') or jobs.lease_held(row):
        return 'legacy', None
    candidates = owner_candidates(str(row['uid']), firestore_client=client)
    refs = {snapshot.id: snapshot.reference for snapshot in candidates}
    if job not in refs and len(refs) >= MAX_MEMBERS:
        refs.pop(next(reversed(refs)))
    refs[job] = _ref(client, job)
    now, token, epoch = _now(), uuid4().hex, uuid4().hex

    def body(transaction):
        if not enabled():
            return 'legacy', None
        snapshots = {key: ref.get(transaction=transaction) for key, ref in refs.items()}
        current = snapshots[job].to_dict() or {}
        committed = current.get('owner_scan') or {}
        if committed.get('epoch') == epoch and committed.get('token') == token:
            return 'run', committed  # A retried, ambiguous seal commit already succeeded.
        if int(current.get('generation') or 0) != generation or jobs.lease_held(current, now=now):
            return 'legacy', None
        eligible = {}
        for key, snapshot in snapshots.items():
            value = snapshot.to_dict() or {}
            if (
                value.get('uid') == row['uid']
                and value.get('conversation_id')
                and not value.get('progress')
                and not value.get('scan_epoch')
                and not jobs.lease_held(value, now=now)
            ):
                eligible[key] = value
        if job not in eligible or len(eligible) < 2:
            return 'legacy', None
        # Read every tombstone before ANY write, including on emulator retries.
        tombstones = {
            key: client.collection('users')
            .document(row['uid'])
            .collection(jobs.TOMBSTONES)
            .document(value['conversation_id'])
            .get(transaction=transaction)
            .exists
            for key, value in eligible.items()
        }
        eligible = {key: value for key, value in eligible.items() if tombstones[key]}
        if job not in eligible or len(eligible) < 2:
            return 'legacy', None
        members = {
            key: {
                'conversation_id': value['conversation_id'],
                'generation': generation if key == job else int(value.get('generation') or 0) + 1,
                'armed_at': value.get('armed_at'),
                'arm_revision': value.get('arm_revision'),
            }
            for key, value in eligible.items()
        }
        scan = {'epoch': epoch, 'token': token, 'uid': row['uid'], 'members': members, 'position': {}}
        for key, member in members.items():
            changes = {
                'generation': member['generation'],
                'lease_generation': member['generation'],
                'run_token': token,
                'lease_until': now + timedelta(seconds=jobs.LEASE_SECONDS),
                'due_at': now + timedelta(seconds=jobs.LEASE_SECONDS),
                'scan_epoch': epoch,
                'scan_leader': job,
            }
            if key == job:
                changes['owner_scan'] = scan
            transaction.update(_ref(client, key), changes)
        return 'run', scan

    status, scan = _in_transaction(client, body)
    if status == 'run' and scan is not None:
        _audit_group('sealed', 'sealed', epoch, len(scan['members']))
    return status, scan


def _resume(client: Any, leader: str, generation: int, observed: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    now, token = _now(), uuid4().hex

    def body(transaction):
        if not enabled():
            return 'handback', observed
        row = _ref(client, leader).get(transaction=transaction).to_dict() or {}
        scan: dict[str, Any] = row.get('owner_scan') or {}
        if scan.get('epoch') != observed['epoch'] or int(row.get('generation') or 0) != generation:
            return 'superseded', None
        if scan.get('token') == token and row.get('run_token') == token:
            return 'run', scan  # Same resume, retried after an ambiguous commit.
        if jobs.lease_held(row, now=now):
            return 'in_progress', None
        rows = _read_members(client, transaction, scan)
        for key, member in scan['members'].items():
            value = rows[key]
            # Only the leader's dispatch generation may advance. Followers
            # retain the shared delegation until takeover/handback.
            if key == leader:
                valid = (
                    value.get('scan_epoch') == scan['epoch']
                    and value.get('run_token') == scan['token']
                    and not value.get('progress')
                )
            else:
                valid = _delegated(value, scan, member)
            if not valid or not _same_arm(value, member):
                return 'handback', scan
        scan = {**scan, 'token': token, 'members': {key: dict(value) for key, value in scan['members'].items()}}
        scan['members'][leader]['generation'] = generation
        for key, member in scan['members'].items():
            changes = {
                'run_token': token,
                'lease_generation': member['generation'],
                'lease_until': now + timedelta(seconds=jobs.LEASE_SECONDS),
                'due_at': now + timedelta(seconds=jobs.LEASE_SECONDS),
            }
            if key == leader:
                changes['owner_scan'] = scan
            transaction.update(_ref(client, key), changes)
        return 'run', scan

    status, scan = _in_transaction(client, body)
    if status == 'handback':
        handback(client, leader, observed['epoch'], observed['token'])
        return 'legacy', None
    return status, scan


class ScanProgress(jobs.RunProgress):
    """One sealed cursor, with ownership re-proved for every member per unit."""

    def __init__(self, client: Any, leader: str, scan: dict[str, Any], **kwargs: Any):
        member = scan['members'][leader]
        super().__init__(client, leader, member['generation'], scan['token'], scan['uid'], scan['position'], **kwargs)
        self.scan = scan

    def _owned(self, transaction: Any) -> None:
        if not enabled():
            raise jobs.RunSuperseded()
        rows = _read_members(self.client, transaction, self.scan)
        for job, member in self.scan['members'].items():
            row = rows[job]
            if not _delegated(row, self.scan, member) or not _same_arm(row, member):
                raise jobs.RunSuperseded()
        leader = rows[self.job]
        if leader.get('lease_generation') != self.generation or leader.get('lease_until') is None:
            raise jobs.RunSuperseded()  # A paused run cannot keep checkpointing with its retained proof token.
        for member in self.scan['members'].values():
            ref = (
                self.client.collection('users')
                .document(self.uid)
                .collection(jobs.TOMBSTONES)
                .document(member['conversation_id'])
            )
            if not ref.get(transaction=transaction).exists:
                raise jobs.RunSuperseded()

    def check_authority(self) -> None:
        # Revalidate before the traversal's data-plane tombstone/storage probes.
        _in_transaction(self.client, self._owned)

    def _renew_all(self, transaction: Any) -> None:
        renewal = self._renewal()
        for job in self.scan['members']:
            # A delegated member cannot dispatch before this lease expires.
            # Keep active groups out of the bounded due queue until then.
            transaction.update(_ref(self.client, job), {**renewal, 'due_at': renewal['lease_until']})

    def checkpoint(self, position: dict[str, Any], *, add_segments=None) -> None:
        if add_segments is not None:
            raise ValueError('shared discoveries must be associated with individual members')

        def body(transaction):
            self._owned(transaction)
            self._renew_all(transaction)
            transaction.update(self._ref(), {'owner_scan.position': position})

        _in_transaction(self.client, body)
        self.position = dict(position)
        self._checkpointed = True

    def add_segments(self, job: str, namespace: str, found: Iterable[str]) -> None:
        segment_ids = sorted(set(found))
        for offset in range(0, len(segment_ids), ASSOCIATION_CHUNK):
            chunk = segment_ids[offset : offset + ASSOCIATION_CHUNK]

            def body(transaction):
                self._owned(transaction)
                for segment_id in chunk:
                    transaction.set(
                        jobs.segment_ref(self.client, job, namespace, segment_id),
                        {'namespace': namespace, 'segment_id': segment_id},
                    )
                self._renew_all(transaction)

            _in_transaction(self.client, body)

    def segments(self, namespace: str) -> set[str]:
        return {
            str(record['segment_id'])
            for job in self.scan['members']
            for record in jobs.segment_records(job, namespace, firestore_client=self.client)
            if record.get('segment_id')
        }

    def pending_segments(self, namespace: str, limit: int) -> list[str]:
        found: set[str] = set()
        for job in self.scan['members']:
            found.update(
                str(record['segment_id'])
                for record in jobs.segment_records(job, namespace, limit=limit, firestore_client=self.client)
                if record.get('segment_id')
            )
            if len(found) >= limit:
                break
        return sorted(found)[:limit]

    def segments_done(self, namespace: str, segment_ids: Iterable[str]) -> None:
        # Full dependent+parked passes have finished for ALL members before
        # entering bindings. Removing these receipts cannot strand an owed row.
        refs = [
            jobs.segment_ref(self.client, job, namespace, segment)
            for job in self.scan['members']
            for segment in segment_ids
        ]
        for offset in range(0, len(refs), ASSOCIATION_CHUNK):
            chunk = refs[offset : offset + ASSOCIATION_CHUNK]

            def body(transaction):
                self._owned(transaction)
                for ref in chunk:
                    transaction.delete(ref)
                self._renew_all(transaction)

            _in_transaction(self.client, body)

    @contextmanager
    def unit(self) -> Iterator[Any]:
        with legal_holds.bounded_destructive_unit(
            self.uid, kind=jobs.GATE_KIND, wait_seconds=jobs.UNIT_GATE_WAIT_SECONDS
        ) as authority:

            def renew(transaction):
                self._owned(transaction)
                self._renew_all(transaction)

            _in_transaction(self.client, renew)
            yield authority
        self._sleep(jobs.UNIT_YIELD_SECONDS)

    def finish(self, outcome: str) -> bool:
        def body(transaction):
            self._owned(transaction)
            if outcome == 'completed':
                if int(self.position.get('ns') or 0) < len(NAMESPACES):
                    raise RuntimeError('owner scan phases are not complete')
                for job in self.scan['members']:
                    transaction.delete(_ref(self.client, job))
                return True
            wait = {
                'held': jobs.HOLD_RECHECK_SECONDS,
                'failed': jobs.REDRIVE_SECONDS,
                'busy': jobs.BUSY_RETRY_SECONDS,
                'artifact_pending': jobs.ARTIFACT_RETRY_SECONDS,
                'checkpointed': 0,
            }[outcome]
            # Only the leader becomes dispatchable. Followers retain ordinary,
            # finite leases, so older binaries recover if the leader disappears.
            transaction.update(
                self._ref(),
                {
                    # Retain proof across dispatch handoffs. A legacy worker
                    # overwrites/clears it, invalidating this saved scan.
                    'run_token': self.token,
                    'lease_generation': None,
                    'lease_until': None,
                    'due_at': _now() + timedelta(seconds=wait),
                    'last_outcome': outcome,
                    **({'attempts': 0} if outcome in {'checkpointed', 'busy', 'artifact_pending'} else {}),
                },
            )
            return False

        return _in_transaction(self.client, body)


class _MemberProgress:
    def __init__(self, scan: ScanProgress, job: str):
        self.scan, self.job = scan, job
        self.position: dict[str, Any] = {}

    def checkpoint(self, position: dict[str, Any], *, add_segments=None) -> None:
        if add_segments:
            self.scan.add_segments(self.job, *add_segments)


def run_job(
    job: str,
    generation: int,
    *,
    firestore_client: Any = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    budget_seconds: float = jobs.RUN_BUDGET_SECONDS,
) -> str:
    """Existing task consumer entrypoint; incompatible/partial work stays legacy."""
    started = clock()
    client = firestore_client if firestore_client is not None else get_firestore_client()
    rpc_deadline.bind_firestore_client(client)
    with rpc_deadline.rpc_deadline(rpc_deadline.now() + budget_seconds + jobs.RUN_FINALIZE_SECONDS):
        status, scan = _claim(client, job, generation)
        if status == 'legacy':
            return jobs.run_job(
                job,
                generation,
                firestore_client=client,
                clock=clock,
                sleep=sleep,
                budget_seconds=max(0, budget_seconds - (clock() - started)),
            )
        if status != 'run' or scan is None:
            return status
        progress = ScanProgress(
            client, job, scan, clock=clock, sleep=sleep, budget_seconds=budget_seconds, started=started
        )

        def hand_off(outcome: str) -> str:
            try:
                progress.finish(outcome)
            except jobs.RunSuperseded:
                handback(client, job, scan['epoch'], scan['token'])
                return 'superseded'
            return outcome

        logger.info('event=conversation_batch_purge_owner_scan_started members=%d count=1', len(scan['members']))
        try:
            progress.check_authority()
            legal_holds.assert_account_deletion_permitted(scan['uid'])
            members = {
                member['conversation_id']: _MemberProgress(progress, key) for key, member in scan['members'].items()
            }
            purge_conversations(scan['uid'], members, progress, clock=clock, check_tombstones=False)
            if any(progress.pending_segments(namespace, 1) for namespace in NAMESPACES):
                raise RuntimeError('owner scan finished with segment erasure still recorded')
            if not progress.finish('completed'):
                raise jobs.RunSuperseded()
        except (jobs.RunSuperseded, PurgeIntentMissing):
            handback(client, job, scan['epoch'], scan['token'])
            return 'superseded'
        except legal_holds.LegalHoldActive:
            return hand_off('held')
        except ArtifactUploadPending:
            return hand_off('artifact_pending')
        except PurgeCheckpointed:
            return hand_off('checkpointed')
        except BaseException as error:
            outcome = (
                'busy' if isinstance(error, Exception) and jobs.lost_gate_to_peer(error, scan['uid']) else 'failed'
            )
            try:
                progress.finish(outcome)
            except jobs.RunSuperseded:
                try:
                    handback(client, job, scan['epoch'], scan['token'])
                except Exception:
                    pass  # Preserve the original failure; finite leases permit redrive.
            except Exception:
                pass  # As in the legacy runner, failed settlement must not hide the original error.
            else:
                if outcome == 'busy':
                    return 'busy'
            raise
        logger.info('event=conversation_batch_purge_owner_scan_completed members=%d count=1', len(scan['members']))
        _audit_group('terminal', 'completed', scan['epoch'], len(scan['members']))
        PURGE_COMPLETED.labels('conversation_owner_scan').inc()
        return 'purged'
