"""Fenced persistence for canonical-memory migration jobs.

The store owns leases, immutable page receipts, certificates, and the final
cutover CAS.  It intentionally does not own item outcomes: the canonical
operation ledger remains the only mutation/idempotency authority.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from database.read_boundary import parse_snapshot_strict
from models.memory_migration import (
    CanonicalMigrationJob,
    MigrationClaim,
    MigrationPageReceipt,
    MigrationState,
    MigrationVerificationCertificate,
)

try:
    from google.cloud.firestore_v1 import transactional as _firestore_transactional
except ImportError:  # pragma: no cover
    _firestore_transactional = None

MIGRATION_JOB_COLLECTION = "canonical_memory_migrations"


class MigrationStoreError(RuntimeError):
    pass


class MigrationCheckpointConflict(MigrationStoreError):
    pass


class MigrationLeaseUnavailable(MigrationStoreError):
    pass


class MigrationLeaseLost(MigrationStoreError):
    pass


class MigrationFenceConflict(MigrationStoreError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryMigrationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[tuple[str, str], CanonicalMigrationJob] = {}
        self._pages: Dict[tuple[str, str, str], MigrationPageReceipt] = {}

    def read_job(self, uid: str, job_id: str) -> Optional[CanonicalMigrationJob]:
        with self._lock:
            return self._jobs.get((uid, job_id))

    def create_job(self, job: CanonicalMigrationJob) -> CanonicalMigrationJob:
        with self._lock:
            key = (job.uid, job.job_id)
            if key in self._jobs:
                raise MigrationCheckpointConflict("migration job already exists")
            self._jobs[key] = job
            return job

    def claim_job(
        self, uid: str, job_id: str, owner_instance_id: str, *, ttl_seconds: float = 60
    ) -> CanonicalMigrationJob:
        if ttl_seconds <= 0:
            raise ValueError("claim ttl must be positive")
        with self._lock:
            job = self._require(uid, job_id)
            prior = job.claim
            now = _now()
            if prior and not prior.expired(now) and prior.owner_instance_id != owner_instance_id:
                raise MigrationLeaseUnavailable("migration claim is held by another owner")
            epoch = (prior.claim_epoch if prior else 0) + 1
            claim = MigrationClaim(
                owner_instance_id=owner_instance_id,
                claim_epoch=epoch,
                claim_id=uuid4().hex,
                renewed_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            return self._write(
                job.model_copy(
                    update={
                        "claim": claim,
                        "state": MigrationState.running,
                        "version": job.version + 1,
                        "updated_at": now,
                    }
                )
            )

    def renew_claim(
        self, uid: str, job_id: str, claim: MigrationClaim, *, ttl_seconds: float = 60
    ) -> CanonicalMigrationJob:
        with self._lock:
            job = self._require(uid, job_id)
            self._assert_claim(job, claim)
            return self._write(
                job.model_copy(
                    update={
                        "claim": claim.renew(ttl_seconds=ttl_seconds),
                        "version": job.version + 1,
                        "updated_at": _now(),
                    }
                )
            )

    def write_page_receipt(
        self, uid: str, job_id: str, claim: MigrationClaim, receipt: MigrationPageReceipt
    ) -> MigrationPageReceipt:
        with self._lock:
            self._assert_claim(self._require(uid, job_id), claim)
            key = (uid, job_id, receipt.page_id)
            prior = self._pages.get(key)
            if prior and prior != receipt:
                raise MigrationFenceConflict("page receipt is immutable")
            self._pages[key] = prior or receipt
            return self._pages[key]

    def attach_certificate(
        self, uid: str, job_id: str, claim: MigrationClaim, certificate: MigrationVerificationCertificate
    ) -> CanonicalMigrationJob:
        with self._lock:
            job = self._require(uid, job_id)
            self._assert_claim(job, claim)
            if certificate.required_surfaces != job.required_surfaces:
                raise MigrationFenceConflict("certificate surfaces differ from job")
            return self._write(
                job.model_copy(
                    update={
                        "certificate": certificate,
                        "state": MigrationState.soaking,
                        "version": job.version + 1,
                        "updated_at": _now(),
                    }
                )
            )

    def cutover(
        self, uid: str, job_id: str, claim: MigrationClaim, *, expected_head_commit_id: str
    ) -> CanonicalMigrationJob:
        with self._lock:
            job = self._require(uid, job_id)
            self._assert_claim(job, claim)
            certificate = job.certificate
            if certificate is None or certificate.canonical_head_commit_id != expected_head_commit_id:
                raise MigrationFenceConflict("fresh certificate/head is required for cutover")
            return self._write(
                job.model_copy(
                    update={
                        "cutover_head_commit_id": expected_head_commit_id,
                        "state": MigrationState.complete,
                        "version": job.version + 1,
                        "updated_at": _now(),
                    }
                )
            )

    def _require(self, uid: str, job_id: str) -> CanonicalMigrationJob:
        job = self._jobs.get((uid, job_id))
        if job is None:
            raise MigrationCheckpointConflict("migration job does not exist")
        return job

    def _assert_claim(self, job: CanonicalMigrationJob, claim: MigrationClaim) -> None:
        if job.claim != claim or claim.expired():
            raise MigrationLeaseLost("migration claim is stale or lost")

    def _write(self, job: CanonicalMigrationJob) -> CanonicalMigrationJob:
        self._jobs[(job.uid, job.job_id)] = job
        return job


class FirestoreMigrationStore:
    """Firestore implementation with claim checks and writes in one transaction."""

    def __init__(self, db_client: Any):
        self._db = db_client

    def _ref(self, uid: str, job_id: str) -> Any:
        return self._db.document(f"users/{uid}/{MIGRATION_JOB_COLLECTION}/{job_id}")

    def _page_ref(self, uid: str, job_id: str, page_id: str) -> Any:
        return self._db.document(f"users/{uid}/{MIGRATION_JOB_COLLECTION}/{job_id}/pages/{page_id}")

    def read_job(self, uid: str, job_id: str) -> Optional[CanonicalMigrationJob]:
        snapshot = self._ref(uid, job_id).get()
        return parse_snapshot_strict(CanonicalMigrationJob, snapshot) if getattr(snapshot, "exists", False) else None

    def _run(self, callback: Any) -> Any:
        tx = self._db.transaction()
        if _firestore_transactional is not None and tx.__class__.__module__.startswith("google.cloud.firestore"):
            return _firestore_transactional(callback)(tx)
        if hasattr(tx, "_begin"):
            tx._begin()
        try:
            result = callback(tx)
            if hasattr(tx, "_commit"):
                tx._commit()
            return result
        except Exception:
            if hasattr(tx, "_rollback"):
                tx._rollback()
            raise
        finally:
            if hasattr(tx, "_clean_up"):
                tx._clean_up()

    @staticmethod
    def _decode(snapshot: Any) -> CanonicalMigrationJob:
        if not getattr(snapshot, "exists", False):
            raise MigrationCheckpointConflict("migration job does not exist")
        return parse_snapshot_strict(CanonicalMigrationJob, snapshot)

    @staticmethod
    def _assert_claim(job: CanonicalMigrationJob, claim: MigrationClaim) -> None:
        if job.claim != claim or claim.expired():
            raise MigrationLeaseLost("migration claim is stale or lost")

    def create_job(self, job: CanonicalMigrationJob) -> CanonicalMigrationJob:
        ref = self._ref(job.uid, job.job_id)

        def write(tx: Any) -> CanonicalMigrationJob:
            if getattr(ref.get(transaction=tx), "exists", False):
                raise MigrationCheckpointConflict("migration job already exists")
            if hasattr(tx, "create"):
                tx.create(ref, job.model_dump(mode="python"))
            else:
                tx.set(ref, job.model_dump(mode="python"))
            return job

        return self._run(write)

    def claim_job(
        self, uid: str, job_id: str, owner_instance_id: str, *, ttl_seconds: float = 60
    ) -> CanonicalMigrationJob:
        if ttl_seconds <= 0:
            raise ValueError("claim ttl must be positive")
        ref = self._ref(uid, job_id)

        def claim(tx: Any) -> CanonicalMigrationJob:
            job = self._decode(ref.get(transaction=tx))
            prior = job.claim
            now = _now()
            if prior and not prior.expired(now) and prior.owner_instance_id != owner_instance_id:
                raise MigrationLeaseUnavailable("migration claim is held by another owner")
            next_claim = MigrationClaim(
                owner_instance_id=owner_instance_id,
                claim_epoch=(prior.claim_epoch if prior else 0) + 1,
                claim_id=uuid4().hex,
                renewed_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            written = job.model_copy(
                update={
                    "claim": next_claim,
                    "state": MigrationState.running,
                    "version": job.version + 1,
                    "updated_at": now,
                }
            )
            tx.set(ref, written.model_dump(mode="python"))
            return written

        return self._run(claim)

    def renew_claim(
        self, uid: str, job_id: str, claim: MigrationClaim, *, ttl_seconds: float = 60
    ) -> CanonicalMigrationJob:
        ref = self._ref(uid, job_id)

        def renew(tx: Any) -> CanonicalMigrationJob:
            job = self._decode(ref.get(transaction=tx))
            self._assert_claim(job, claim)
            written = job.model_copy(
                update={"claim": claim.renew(ttl_seconds=ttl_seconds), "version": job.version + 1, "updated_at": _now()}
            )
            tx.set(ref, written.model_dump(mode="python"))
            return written

        return self._run(renew)

    def write_page_receipt(
        self, uid: str, job_id: str, claim: MigrationClaim, receipt: MigrationPageReceipt
    ) -> MigrationPageReceipt:
        job_ref, page_ref = self._ref(uid, job_id), self._page_ref(uid, job_id, receipt.page_id)

        def write(tx: Any) -> MigrationPageReceipt:
            self._assert_claim(self._decode(job_ref.get(transaction=tx)), claim)
            snapshot = page_ref.get(transaction=tx)
            if getattr(snapshot, "exists", False):
                prior = parse_snapshot_strict(MigrationPageReceipt, snapshot)
                if prior != receipt:
                    raise MigrationFenceConflict("page receipt is immutable")
                return prior
            if hasattr(tx, "create"):
                tx.create(page_ref, receipt.model_dump(mode="python"))
            else:
                tx.set(page_ref, receipt.model_dump(mode="python"))
            return receipt

        return self._run(write)

    def attach_certificate(
        self, uid: str, job_id: str, claim: MigrationClaim, certificate: MigrationVerificationCertificate
    ) -> CanonicalMigrationJob:
        return self._update_with_claim(
            uid,
            job_id,
            claim,
            lambda job: job.model_copy(update={"certificate": certificate, "state": MigrationState.soaking}),
            certificate,
        )

    def cutover(
        self, uid: str, job_id: str, claim: MigrationClaim, *, expected_head_commit_id: str
    ) -> CanonicalMigrationJob:
        def mutation(job: CanonicalMigrationJob) -> CanonicalMigrationJob:
            if job.certificate is None or job.certificate.canonical_head_commit_id != expected_head_commit_id:
                raise MigrationFenceConflict("fresh certificate/head is required for cutover")
            return job.model_copy(
                update={"cutover_head_commit_id": expected_head_commit_id, "state": MigrationState.complete}
            )

        return self._update_with_claim(uid, job_id, claim, mutation)

    def _update_with_claim(
        self,
        uid: str,
        job_id: str,
        claim: MigrationClaim,
        mutation: Any,
        certificate: Optional[MigrationVerificationCertificate] = None,
    ) -> CanonicalMigrationJob:
        ref = self._ref(uid, job_id)

        def update(tx: Any) -> CanonicalMigrationJob:
            job = self._decode(ref.get(transaction=tx))
            self._assert_claim(job, claim)
            if certificate is not None and certificate.required_surfaces != job.required_surfaces:
                raise MigrationFenceConflict("certificate surfaces differ from job")
            updated = mutation(job).model_copy(update={"version": job.version + 1, "updated_at": _now()})
            tx.set(ref, updated.model_dump(mode="python"))
            return updated

        return self._run(update)


MemoryMigrationStore = FirestoreMigrationStore
InMemoryCheckpointStore = InMemoryMigrationStore
