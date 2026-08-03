"""Transactional persistence for canonical-memory migration control state.

The in-memory implementation is intentionally strict and is used by unit
tests.  ``FirestoreMigrationStore`` mirrors the same compare-and-set and lease
rules at the document boundary; callers never perform an un-fenced read/write
sequence themselves.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database.read_boundary import parse_snapshot_strict
from models.memory_migration import (
    CanonicalMigrationCheckpoint,
    CanonicalMigrationManifest,
    CanonicalMigrationWorkRecord,
    MigrationLease,
)

try:
    from google.cloud.firestore_v1 import transactional as _firestore_transactional  # type: ignore[reportAssignmentType,reportUnknownMemberType]
except ImportError:  # pragma: no cover - lightweight unit tests mock Firestore.
    _firestore_transactional = None

MIGRATION_CONTROL_DOC = "memory_control/canonical_migration"
MIGRATION_MANIFEST_COLLECTION = "canonical_migration_manifests"
MIGRATION_WORK_COLLECTION = "canonical_migration_work"


class MigrationStoreError(RuntimeError):
    """Base class for durable migration store failures."""


class MigrationCheckpointConflict(MigrationStoreError):
    """The checkpoint version changed since the caller's read."""


class MigrationLeaseUnavailable(MigrationStoreError):
    """Another owner currently holds a non-expired lease."""


class MigrationLeaseLost(MigrationStoreError):
    """The owner or ownership epoch no longer matches."""


class MigrationFenceConflict(MigrationStoreError):
    """A write attempted to change an immutable migration fence."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryMigrationStore:
    """Thread-safe fake with production-like CAS and lease semantics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._checkpoints: Dict[str, CanonicalMigrationCheckpoint] = {}
        self._leases: Dict[str, MigrationLease] = {}
        self._manifests: Dict[tuple[str, str], CanonicalMigrationManifest] = {}
        self._work: Dict[tuple[str, str, str], CanonicalMigrationWorkRecord] = {}

    def read_checkpoint(self, uid: str) -> Optional[CanonicalMigrationCheckpoint]:
        with self._lock:
            return self._checkpoints.get(uid)

    # Short aliases make the store convenient for controller adapters.
    read = read_checkpoint

    def create_checkpoint(self, checkpoint: CanonicalMigrationCheckpoint) -> CanonicalMigrationCheckpoint:
        with self._lock:
            if checkpoint.uid in self._checkpoints:
                raise MigrationCheckpointConflict("checkpoint already exists")
            self._checkpoints[checkpoint.uid] = checkpoint
            return checkpoint

    def compare_and_set_checkpoint(
        self,
        uid: str,
        expected_version: int,
        checkpoint: CanonicalMigrationCheckpoint,
        *,
        owner_id: Optional[str] = None,
        ownership_epoch: Optional[int] = None,
    ) -> CanonicalMigrationCheckpoint:
        with self._lock:
            if checkpoint.uid != uid:
                raise MigrationFenceConflict("checkpoint uid mismatch")
            current = self._checkpoints.get(uid)
            if current is None:
                if expected_version != -1:
                    raise MigrationCheckpointConflict("checkpoint does not exist")
            elif current.version != expected_version:
                raise MigrationCheckpointConflict(
                    f"checkpoint version mismatch: expected {expected_version}, current {current.version}"
                )
            if checkpoint.uid != uid:
                raise MigrationFenceConflict("checkpoint uid mismatch")
            if current is not None and checkpoint.fence != current.fence:
                raise MigrationFenceConflict("migration fence is immutable")
            self._assert_lease(checkpoint.uid, owner_id=owner_id, ownership_epoch=ownership_epoch)
            written = checkpoint.model_copy(update={"version": expected_version + 1, "updated_at": _now()})
            self._checkpoints[uid] = written
            return written

    cas_checkpoint = compare_and_set_checkpoint

    def acquire_lease(self, uid: str, owner_id: str, *, ttl_seconds: float = 60.0) -> MigrationLease:
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        with self._lock:
            now = _now()
            prior = self._leases.get(uid)
            if prior and not prior.is_expired(now) and prior.owner_id != owner_id:
                raise MigrationLeaseUnavailable("migration lease is held by another owner")
            epoch = (
                prior.ownership_epoch
                if prior and prior.owner_id == owner_id and not prior.is_expired(now)
                else (prior.ownership_epoch + 1 if prior else 1)
            )
            lease = MigrationLease(
                uid=uid,
                owner_id=owner_id,
                ownership_epoch=epoch,
                renewed_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._leases[uid] = lease
            return lease

    def renew_lease(
        self, uid: str, owner_id: str, ownership_epoch: int, *, ttl_seconds: float = 60.0
    ) -> MigrationLease:
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        with self._lock:
            current = self._leases.get(uid)
            if current is None or current.owner_id != owner_id or current.ownership_epoch != ownership_epoch:
                raise MigrationLeaseLost("migration lease owner/epoch mismatch")
            renewed = current.renewed(owner_id=owner_id, ownership_epoch=ownership_epoch, ttl_seconds=ttl_seconds)
            self._leases[uid] = renewed
            return renewed

    def release_lease(self, uid: str, owner_id: str, ownership_epoch: int) -> None:
        with self._lock:
            current = self._leases.get(uid)
            if current is None:
                return
            if current.owner_id != owner_id or current.ownership_epoch != ownership_epoch:
                raise MigrationLeaseLost("migration lease owner/epoch mismatch")
            # Retain an expired lease as the durable epoch fence.  Deleting it
            # would let the next owner restart at epoch 1 and allow an old
            # worker to look current after a release/takeover cycle.
            expired = current.model_copy(update={"expires_at": _now(), "renewed_at": _now()})
            self._leases[uid] = expired
            checkpoint = self._checkpoints.get(uid)
            if checkpoint is not None and checkpoint.lease == current:
                self._checkpoints[uid] = checkpoint.model_copy(update={"lease": expired, "updated_at": _now()})

    acquire_user_lease = acquire_lease
    renew_user_lease = renew_lease
    release_user_lease = release_lease

    def write_manifest(self, manifest: CanonicalMigrationManifest) -> CanonicalMigrationManifest:
        with self._lock:
            if not manifest.uid.strip():
                raise MigrationFenceConflict("manifest uid must not be blank")
            key = (manifest.uid, manifest.manifest_id)
            prior = self._manifests.get(key)
            if prior is not None and prior != manifest:
                raise MigrationCheckpointConflict("manifest id already contains different data")
            self._manifests[key] = manifest
            return manifest

    def read_manifest(self, uid: str, manifest_id: str) -> Optional[CanonicalMigrationManifest]:
        with self._lock:
            return self._manifests.get((uid, manifest_id))

    def upsert_work_record(self, record: CanonicalMigrationWorkRecord) -> CanonicalMigrationWorkRecord:
        with self._lock:
            if not record.uid.strip() or not record.manifest_id.strip() or not record.item_id.strip():
                raise MigrationFenceConflict("work record identity must not be blank")
            key = (record.uid, record.manifest_id, record.item_id)
            prior = self._work.get(key)
            if prior is not None:
                if (prior.uid, prior.manifest_id, prior.item_id) != (record.uid, record.manifest_id, record.item_id):
                    raise MigrationFenceConflict("work record identity mismatch")
                if (
                    prior.item_revision,
                    prior.content_hash,
                    prior.evidence_ids,
                    prior.account_generation,
                    prior.source_generation,
                ) != (
                    record.item_revision,
                    record.content_hash,
                    record.evidence_ids,
                    record.account_generation,
                    record.source_generation,
                ):
                    raise MigrationFenceConflict("work record item fence is immutable")
            self._work[key] = record
            return record

    def read_work_records(self, uid: str, manifest_id: str) -> List[CanonicalMigrationWorkRecord]:
        with self._lock:
            return sorted(
                [
                    value
                    for (record_uid, record_manifest, _), value in self._work.items()
                    if (record_uid, record_manifest) == (uid, manifest_id)
                ],
                key=lambda value: value.item_id,
            )

    def _assert_lease(self, uid: str, *, owner_id: Optional[str], ownership_epoch: Optional[int]) -> None:
        if owner_id is None and ownership_epoch is None:
            return
        current = self._leases.get(uid)
        if (
            current is None
            or current.owner_id != owner_id
            or current.ownership_epoch != ownership_epoch
            or current.is_expired()
        ):
            raise MigrationLeaseLost("migration lease owner/epoch mismatch or expired")


class FirestoreMigrationStore:
    """Firestore adapter using a transaction for every checkpoint/lease CAS."""

    def __init__(self, firestore_client: Any):
        self._db = firestore_client

    @staticmethod
    def _control_path(uid: str) -> str:
        return f"users/{uid}/{MIGRATION_CONTROL_DOC}"

    @staticmethod
    def _manifest_path(uid: str, manifest_id: str) -> str:
        return f"users/{uid}/{MIGRATION_MANIFEST_COLLECTION}/{manifest_id}"

    @staticmethod
    def _work_path(uid: str, manifest_id: str, item_id: str) -> str:
        return f"users/{uid}/{MIGRATION_WORK_COLLECTION}/{manifest_id}/items/{item_id}"

    def _ref(self, path: str) -> Any:
        return self._db.document(path)

    def _decode_checkpoint(self, uid: str, snapshot: Any) -> Optional[CanonicalMigrationCheckpoint]:
        if not getattr(snapshot, "exists", False):
            return None
        checkpoint = parse_snapshot_strict(CanonicalMigrationCheckpoint, snapshot)
        if checkpoint.uid != uid:
            raise MigrationFenceConflict("checkpoint uid does not match requested user")
        return checkpoint

    def read_checkpoint(self, uid: str) -> Optional[CanonicalMigrationCheckpoint]:
        return self._decode_checkpoint(uid, self._ref(self._control_path(uid)).get())

    read = read_checkpoint

    def create_checkpoint(self, checkpoint: CanonicalMigrationCheckpoint) -> CanonicalMigrationCheckpoint:
        return self.compare_and_set_checkpoint(checkpoint.uid, -1, checkpoint)

    def compare_and_set_checkpoint(
        self,
        uid: str,
        expected_version: int,
        checkpoint: CanonicalMigrationCheckpoint,
        *,
        owner_id: Optional[str] = None,
        ownership_epoch: Optional[int] = None,
    ) -> CanonicalMigrationCheckpoint:
        transaction = self._db.transaction()
        ref = self._ref(self._control_path(uid))

        def body(tx: Any) -> CanonicalMigrationCheckpoint:
            snapshot = ref.get(transaction=tx)
            current = self._decode_checkpoint(uid, snapshot)
            if checkpoint.uid != uid:
                raise MigrationFenceConflict("checkpoint uid mismatch")
            if (current is None and expected_version != -1) or (
                current is not None and current.version != expected_version
            ):
                raise MigrationCheckpointConflict("checkpoint version mismatch")
            if current is not None and current.fence != checkpoint.fence:
                raise MigrationFenceConflict("migration fence is immutable")
            if current is not None and (owner_id is not None or ownership_epoch is not None):
                if owner_id is None:
                    raise MigrationLeaseUnavailable("owner id is required when checking lease ownership")
                self._check_snapshot_lease(current, owner_id=owner_id, ownership_epoch=ownership_epoch)
            written = checkpoint.model_copy(update={"version": expected_version + 1, "updated_at": _now()})
            tx.set(ref, written.model_dump(mode="python"))
            return written

        return self._transactional(transaction, body)

    cas_checkpoint = compare_and_set_checkpoint

    def acquire_lease(self, uid: str, owner_id: str, *, ttl_seconds: float = 60.0) -> MigrationLease:
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        transaction = self._db.transaction()
        ref = self._ref(self._control_path(uid))

        def body(tx: Any) -> MigrationLease:
            snapshot = ref.get(transaction=tx)
            current_checkpoint = self._decode_checkpoint(uid, snapshot)
            prior = current_checkpoint.lease if current_checkpoint else None
            now = _now()
            if prior and not prior.is_expired(now) and prior.owner_id != owner_id:
                raise MigrationLeaseUnavailable("migration lease is held by another owner")
            epoch = (
                prior.ownership_epoch
                if prior and prior.owner_id == owner_id and not prior.is_expired(now)
                else (prior.ownership_epoch + 1 if prior else 1)
            )
            lease = MigrationLease(
                uid=uid,
                owner_id=owner_id,
                ownership_epoch=epoch,
                renewed_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            if current_checkpoint is not None:
                tx.set(
                    ref,
                    current_checkpoint.model_copy(update={"lease": lease, "updated_at": now}).model_dump(mode="python"),
                )
            return lease

        return self._transactional(transaction, body)

    def renew_lease(
        self, uid: str, owner_id: str, ownership_epoch: int, *, ttl_seconds: float = 60.0
    ) -> MigrationLease:
        if ttl_seconds <= 0:
            raise ValueError("lease ttl must be positive")
        transaction = self._db.transaction()
        ref = self._ref(self._control_path(uid))

        def body(tx: Any) -> MigrationLease:
            snapshot = ref.get(transaction=tx)
            checkpoint = self._decode_checkpoint(uid, snapshot)
            if checkpoint is None or checkpoint.lease is None:
                raise MigrationLeaseLost("migration lease is absent")
            self._check_snapshot_lease(checkpoint, owner_id=owner_id, ownership_epoch=ownership_epoch)
            lease = checkpoint.lease.renewed(
                owner_id=owner_id, ownership_epoch=ownership_epoch, ttl_seconds=ttl_seconds
            )
            tx.set(ref, checkpoint.model_copy(update={"lease": lease, "updated_at": _now()}).model_dump(mode="python"))
            return lease

        return self._transactional(transaction, body)

    def release_lease(self, uid: str, owner_id: str, ownership_epoch: int) -> None:
        transaction = self._db.transaction()
        ref = self._ref(self._control_path(uid))

        def body(tx: Any) -> None:
            checkpoint = self._decode_checkpoint(uid, ref.get(transaction=tx))
            if checkpoint is None or checkpoint.lease is None:
                return
            self._check_snapshot_lease(checkpoint, owner_id=owner_id, ownership_epoch=ownership_epoch)
            # Keep a visibly expired lease as an ownership-epoch tombstone so
            # a later owner always advances the fence instead of reusing 1.
            expired = checkpoint.lease.model_copy(update={"expires_at": _now(), "renewed_at": _now()})
            tx.set(
                ref, checkpoint.model_copy(update={"lease": expired, "updated_at": _now()}).model_dump(mode="python")
            )

        self._transactional(transaction, body)

    acquire_user_lease = acquire_lease
    renew_user_lease = renew_lease
    release_user_lease = release_lease

    def write_manifest(self, manifest: CanonicalMigrationManifest) -> CanonicalMigrationManifest:
        if not manifest.uid.strip() or not manifest.manifest_id.strip():
            raise MigrationFenceConflict("manifest identity must not be blank")
        transaction = self._db.transaction()
        ref = self._ref(self._manifest_path(manifest.uid, manifest.manifest_id))

        def body(tx: Any) -> CanonicalMigrationManifest:
            snapshot = ref.get(transaction=tx)
            if getattr(snapshot, "exists", False):
                prior = parse_snapshot_strict(CanonicalMigrationManifest, snapshot)
                if prior.uid != manifest.uid or prior.manifest_id != manifest.manifest_id:
                    raise MigrationFenceConflict("manifest identity mismatch")
                if prior != manifest:
                    raise MigrationCheckpointConflict("manifest id already contains different data")
                return prior
            (
                tx.create(ref, manifest.model_dump(mode="python"))
                if hasattr(tx, "create")
                else tx.set(ref, manifest.model_dump(mode="python"))
            )
            return manifest

        return self._transactional(transaction, body)

    def read_manifest(self, uid: str, manifest_id: str) -> Optional[CanonicalMigrationManifest]:
        snapshot = self._ref(self._manifest_path(uid, manifest_id)).get()
        manifest = (
            parse_snapshot_strict(CanonicalMigrationManifest, snapshot) if getattr(snapshot, "exists", False) else None
        )
        if manifest is not None and (manifest.uid != uid or manifest.manifest_id != manifest_id):
            raise MigrationFenceConflict("manifest identity does not match requested path")
        return manifest

    def upsert_work_record(self, record: CanonicalMigrationWorkRecord) -> CanonicalMigrationWorkRecord:
        if not record.uid.strip() or not record.manifest_id.strip() or not record.item_id.strip():
            raise MigrationFenceConflict("work record identity must not be blank")
        transaction = self._db.transaction()
        ref = self._ref(self._work_path(record.uid, record.manifest_id, record.item_id))

        def body(tx: Any) -> CanonicalMigrationWorkRecord:
            snapshot = ref.get(transaction=tx)
            if getattr(snapshot, "exists", False):
                prior = parse_snapshot_strict(CanonicalMigrationWorkRecord, snapshot)
                if (prior.uid, prior.manifest_id, prior.item_id) != (record.uid, record.manifest_id, record.item_id):
                    raise MigrationFenceConflict("work record identity mismatch")
                if (
                    prior.item_revision,
                    prior.content_hash,
                    prior.evidence_ids,
                    prior.account_generation,
                    prior.source_generation,
                ) != (
                    record.item_revision,
                    record.content_hash,
                    record.evidence_ids,
                    record.account_generation,
                    record.source_generation,
                ):
                    raise MigrationFenceConflict("work record item fence is immutable")
            tx.set(ref, record.model_dump(mode="python"))
            return record

        return self._transactional(transaction, body)

    def read_work_records(self, uid: str, manifest_id: str) -> List[CanonicalMigrationWorkRecord]:
        parent = self._ref(f"users/{uid}/{MIGRATION_WORK_COLLECTION}/{manifest_id}")
        items = parent.collection("items").stream()
        return sorted(
            [self._decode_work_record(uid, manifest_id, snapshot) for snapshot in items],
            key=lambda value: value.item_id,
        )

    @staticmethod
    def _decode_work_record(uid: str, manifest_id: str, snapshot: Any) -> CanonicalMigrationWorkRecord:
        record = parse_snapshot_strict(CanonicalMigrationWorkRecord, snapshot)
        if record.uid != uid or record.manifest_id != manifest_id:
            raise MigrationFenceConflict("work record identity does not match requested path")
        return record

    @staticmethod
    def _check_snapshot_lease(
        checkpoint: CanonicalMigrationCheckpoint, *, owner_id: str, ownership_epoch: Optional[int]
    ) -> None:
        lease = checkpoint.lease
        if (
            lease is None
            or lease.owner_id != owner_id
            or lease.ownership_epoch != ownership_epoch
            or lease.is_expired()
        ):
            raise MigrationLeaseLost("migration lease owner/epoch mismatch or expired")

    @staticmethod
    def _transactional(transaction: Any, body: Any) -> Any:
        if _firestore_transactional is not None:
            return _firestore_transactional(body)(transaction)
        if hasattr(transaction, "_begin"):
            transaction._begin()
        try:
            result = body(transaction)
            if hasattr(transaction, "_commit"):
                transaction._commit()
            return result
        finally:
            if hasattr(transaction, "_clean_up"):
                transaction._clean_up()


# Conventional names for dependency injection in tests/callers.
MemoryMigrationStore = FirestoreMigrationStore
InMemoryCheckpointStore = InMemoryMigrationStore

__all__ = [
    "FirestoreMigrationStore",
    "InMemoryCheckpointStore",
    "InMemoryMigrationStore",
    "MemoryMigrationStore",
    "MigrationCheckpointConflict",
    "MigrationFenceConflict",
    "MigrationLeaseLost",
    "MigrationLeaseUnavailable",
    "MigrationStoreError",
]
