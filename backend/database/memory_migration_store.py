"""Fenced persistence for canonical-memory migration jobs.

The store owns leases, immutable page receipts, certificates, and the final
cutover CAS.  It intentionally does not own item outcomes: the canonical
operation ledger remains the only mutation/idempotency authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Protocol
from uuid import uuid4

from database.memory_collections import MemoryCollections
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


class MigrationCertificateVerifier(Protocol):
    """Trust boundary for certificates produced by the authoritative verifier.

    Firestore deliberately has no permissive default: a caller holding a job
    lease is not thereby allowed to manufacture a readiness certificate.
    """

    def verify(self, job: CanonicalMigrationJob, certificate: MigrationVerificationCertificate) -> None: ...


class HmacMigrationCertificateVerifier:
    """Authenticates certificates issued by the server-only migration verifier.

    The key belongs to the migration worker's runtime identity and is never
    stored in Firestore.  This lets the job store distinguish an authoritative
    verifier result from a certificate-shaped payload supplied by a caller.
    """

    def __init__(self, *, verifier_id: str, signing_key: bytes):
        if not verifier_id.strip() or not signing_key:
            raise ValueError("migration certificate verifier id and signing key are required")
        self._verifier_id = verifier_id
        self._signing_key = signing_key

    @classmethod
    def from_environment(cls) -> Optional["HmacMigrationCertificateVerifier"]:
        verifier_id = os.getenv("CANONICAL_MIGRATION_VERIFIER_ID", "")
        signing_key = os.getenv("CANONICAL_MIGRATION_CERTIFICATE_HMAC_KEY", "")
        if not verifier_id or not signing_key:
            return None
        return cls(verifier_id=verifier_id, signing_key=signing_key.encode("utf-8"))

    def sign(self, certificate: MigrationVerificationCertificate) -> str:
        if certificate.verifier_id != self._verifier_id:
            raise MigrationFenceConflict("certificate was issued by an unexpected verifier")
        return hmac.new(self._signing_key, _certificate_signing_payload(certificate), hashlib.sha256).hexdigest()

    def verify(self, job: CanonicalMigrationJob, certificate: MigrationVerificationCertificate) -> None:
        if certificate.verifier_id != self._verifier_id:
            raise MigrationFenceConflict("certificate was issued by an unexpected verifier")
        expected = self.sign(certificate)
        if not hmac.compare_digest(certificate.signature, expected):
            raise MigrationFenceConflict("migration certificate signature is invalid")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _assert_certificate_matches_job(job: CanonicalMigrationJob, certificate: MigrationVerificationCertificate) -> None:
    """Reject cross-tenant, stale-generation, and un-snapshotted certificates."""
    if not job.certificate_matches(certificate):
        raise MigrationFenceConflict("certificate identity, versions, or source snapshot differ from migration job")


def _certificate_signing_payload(certificate: MigrationVerificationCertificate) -> bytes:
    """Stable, non-secret payload for a verifier signature."""
    payload = certificate.model_dump(mode="json", exclude={"signature"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_stage_control_transition(*, control_data: object, uid: str, account_generation: int) -> dict[str, object]:
    """Build the complete per-user read-stage rollout transition.

    Cutover is a privileged, server-owned operation.  Writing only ``mode`` is
    insufficient: the V3 reader also requires the fallback projection fence,
    read stage gate, and consumer grant.  Validate the existing control
    document before changing those fields so a malformed or cross-generation
    document cannot be silently upgraded into a readable state.
    """
    if not isinstance(control_data, dict):
        raise MigrationFenceConflict("authoritative memory control is unavailable for cutover")
    if control_data.get("uid") != uid or control_data.get("account_generation") != account_generation:
        raise MigrationFenceConflict("authoritative memory control is unavailable for cutover")
    if control_data.get("schema_version") != 1:
        raise MigrationFenceConflict("authoritative memory control has an unsupported schema")
    mode = control_data.get("mode")
    if mode not in {"off", "shadow", "write", "read"}:
        raise MigrationFenceConflict("authoritative memory control has an unsupported mode")
    mode_epoch = control_data.get("mode_epoch")
    cutover_epoch = control_data.get("cutover_epoch")
    if (
        not isinstance(mode_epoch, int)
        or isinstance(mode_epoch, bool)
        or mode_epoch < 0
        or not isinstance(cutover_epoch, int)
        or isinstance(cutover_epoch, bool)
        or cutover_epoch < 0
    ):
        raise MigrationFenceConflict("authoritative memory control has invalid rollout epochs")
    stage_gates = control_data.get("stage_gates")
    grants = control_data.get("grants")
    if not isinstance(stage_gates, dict) or not isinstance(grants, dict):
        raise MigrationFenceConflict("authoritative memory control is missing typed read gates")
    omi_chat_grant = grants.get("omi_chat")
    if not isinstance(omi_chat_grant, dict):
        raise MigrationFenceConflict("authoritative memory control is missing the omi_chat grant")

    next_mode_epoch = mode_epoch if mode == "read" else mode_epoch + 1
    next_cutover_epoch = cutover_epoch if mode == "read" and cutover_epoch > 0 else next_mode_epoch
    next_stage_gates = dict(stage_gates)
    next_stage_gates.update({"shadow": "passed", "write": "passed", "read": "passed"})
    next_grants = dict(grants)
    next_omi_chat_grant = dict(omi_chat_grant)
    next_omi_chat_grant["default_memory"] = True
    next_grants["omi_chat"] = next_omi_chat_grant
    return {
        "mode": "read",
        "mode_epoch": next_mode_epoch,
        "cutover_epoch": next_cutover_epoch,
        "fallback_projection_ready": True,
        "persistent_memory_writes_started": True,
        "writes_blocked": False,
        "stage_gates": next_stage_gates,
        "grants": next_grants,
    }


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
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be claimed")
            prior = job.claim
            now = _now()
            if prior and not prior.expired(now):
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
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
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
            job = self._require(uid, job_id)
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            key = (uid, job_id, receipt.page_id)
            prior = self._pages.get(key)
            if prior and not prior.matches_replay(receipt):
                raise MigrationFenceConflict("page receipt is immutable")
            self._pages[key] = prior or receipt
            return self._pages[key]

    def record_source_snapshot(
        self, uid: str, job_id: str, claim: MigrationClaim, *, snapshot_token: str, source_digest: str
    ) -> CanonicalMigrationJob:
        if not snapshot_token.strip() or not source_digest.strip():
            raise ValueError("source snapshot token and digest must be nonblank")
        with self._lock:
            job = self._require(uid, job_id)
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            if job.source_snapshot_token not in {None, snapshot_token} or job.source_digest not in {
                None,
                source_digest,
            }:
                raise MigrationFenceConflict("source snapshot is immutable once captured")
            return self._write(
                job.model_copy(
                    update={
                        "source_snapshot_token": snapshot_token,
                        "source_digest": source_digest,
                        "version": job.version + 1,
                        "updated_at": _now(),
                    }
                )
            )

    def attach_certificate(
        self, uid: str, job_id: str, claim: MigrationClaim, certificate: MigrationVerificationCertificate
    ) -> CanonicalMigrationJob:
        with self._lock:
            job = self._require(uid, job_id)
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            _assert_certificate_matches_job(job, certificate)
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
            if job.state == MigrationState.complete:
                if job.cutover_head_commit_id == expected_head_commit_id:
                    return job
                raise MigrationFenceConflict("migration already cut over at a different head")
            if job.state == MigrationState.aborted:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            certificate = job.certificate
            if certificate is None or certificate.canonical_head_commit_id != expected_head_commit_id:
                raise MigrationFenceConflict("fresh certificate/head is required for cutover")
            _assert_certificate_matches_job(job, certificate)
            return self._write(
                job.model_copy(
                    update={
                        "cutover_head_commit_id": expected_head_commit_id,
                        "state": MigrationState.complete,
                        "claim": None,
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

    def __init__(self, db_client: Any, *, certificate_verifier: Optional[MigrationCertificateVerifier] = None):
        self._db = db_client
        self._certificate_verifier = certificate_verifier or HmacMigrationCertificateVerifier.from_environment()

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
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be claimed")
            prior = job.claim
            now = _now()
            if prior and not prior.expired(now):
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
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
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
            job = self._decode(job_ref.get(transaction=tx))
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            snapshot = page_ref.get(transaction=tx)
            if getattr(snapshot, "exists", False):
                prior = parse_snapshot_strict(MigrationPageReceipt, snapshot)
                if not prior.matches_replay(receipt):
                    raise MigrationFenceConflict("page receipt is immutable")
                return prior
            if hasattr(tx, "create"):
                tx.create(page_ref, receipt.model_dump(mode="python"))
            else:
                tx.set(page_ref, receipt.model_dump(mode="python"))
            return receipt

        return self._run(write)

    def record_source_snapshot(
        self, uid: str, job_id: str, claim: MigrationClaim, *, snapshot_token: str, source_digest: str
    ) -> CanonicalMigrationJob:
        if not snapshot_token.strip() or not source_digest.strip():
            raise ValueError("source snapshot token and digest must be nonblank")

        def record(tx: Any) -> CanonicalMigrationJob:
            job = self._decode(self._ref(uid, job_id).get(transaction=tx))
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            if job.source_snapshot_token not in {None, snapshot_token} or job.source_digest not in {
                None,
                source_digest,
            }:
                raise MigrationFenceConflict("source snapshot is immutable once captured")
            written = job.model_copy(
                update={
                    "source_snapshot_token": snapshot_token,
                    "source_digest": source_digest,
                    "version": job.version + 1,
                    "updated_at": _now(),
                }
            )
            tx.set(self._ref(uid, job_id), written.model_dump(mode="python"))
            return written

        return self._run(record)

    def attach_certificate(
        self, uid: str, job_id: str, claim: MigrationClaim, certificate: MigrationVerificationCertificate
    ) -> CanonicalMigrationJob:
        if self._certificate_verifier is None:
            raise MigrationFenceConflict("no authoritative migration certificate verifier is configured")
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
        job_ref = self._ref(uid, job_id)
        paths = MemoryCollections(uid=uid)
        head_ref = self._db.document(paths.memory_state_head)
        control_ref = self._db.document(paths.memory_control_state)
        projection_ref = self._db.document(paths.v3_compatibility_projection_state)

        def cutover_transaction(tx: Any) -> CanonicalMigrationJob:
            job = self._decode(job_ref.get(transaction=tx))
            if job.state == MigrationState.complete:
                if job.cutover_head_commit_id == expected_head_commit_id:
                    return job
                raise MigrationFenceConflict("migration already cut over at a different head")
            if job.state == MigrationState.aborted:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            if job.certificate is None or job.certificate.canonical_head_commit_id != expected_head_commit_id:
                raise MigrationFenceConflict("fresh certificate/head is required for cutover")
            _assert_certificate_matches_job(job, job.certificate)
            head = head_ref.get(transaction=tx)
            control = control_ref.get(transaction=tx)
            projection = projection_ref.get(transaction=tx)
            head_data = head.to_dict() if getattr(head, "exists", False) else None
            control_data = control.to_dict() if getattr(control, "exists", False) else None
            projection_data = projection.to_dict() if getattr(projection, "exists", False) else None
            if not isinstance(head_data, dict) or (
                head_data.get("uid") != uid
                or head_data.get("schema_version") != 1
                or head_data.get("source") != "memory_state_head"
                or head_data.get("head_commit_id") != expected_head_commit_id
                or head_data.get("commit_sequence") != job.certificate.canonical_head_sequence
                or head_data.get("account_generation") != job.account_generation
            ):
                raise MigrationFenceConflict("authoritative memory head changed before cutover")
            if not isinstance(control_data, dict) or (
                control_data.get("uid") != uid
                or control_data.get("account_generation") != job.account_generation
                or control_data.get("source_generation") != job.source_generation
            ):
                raise MigrationFenceConflict("authoritative memory control is unavailable for cutover")
            if not isinstance(projection_data, dict) or (
                projection_data.get("uid") != uid
                or projection_data.get("schema_version") != 1
                or projection_data.get("source") != "memory_items_projection"
                or projection_data.get("projection_version") != "v3_memorydb_compatibility"
                or projection_data.get("source_commit_id") != expected_head_commit_id
                or projection_data.get("account_generation") != job.account_generation
                or projection_data.get("projection_generation") != job.account_generation
                or projection_data.get("freshness_fence_generation") != job.account_generation
                or projection_data.get("tombstone_fence_generation") != job.account_generation
                or projection_data.get("source_evidence_fence") != f"head-{expected_head_commit_id}"
                or projection_data.get("projection_evidence_fence") != f"head-{expected_head_commit_id}"
                or projection_data.get("writer_admission_ready", projection_data.get("ready")) is not True
                or projection_data.get("rebuild_complete") is not True
                or projection_data.get("rebuild_id") != job.certificate.projection_rebuild_id
                or projection_data.get("write_convergence_complete") is not True
                or projection_data.get("delete_convergence_complete") is not True
                or projection_data.get("tombstone_convergence_complete") is not True
            ):
                raise MigrationFenceConflict("compatibility projection is not fenced to the verified head")
            updated = job.model_copy(
                update={
                    "cutover_head_commit_id": expected_head_commit_id,
                    "state": MigrationState.complete,
                    "claim": None,
                }
            )
            updated = updated.model_copy(update={"version": job.version + 1, "updated_at": _now()})
            tx.set(
                control_ref,
                _read_stage_control_transition(
                    control_data=control_data,
                    uid=uid,
                    account_generation=job.account_generation,
                ),
                merge=True,
            )
            tx.set(projection_ref, {"ready": True}, merge=True)
            tx.set(job_ref, updated.model_dump(mode="python"))
            return updated

        return self._run(cutover_transaction)

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
            if job.state in {MigrationState.complete, MigrationState.aborted}:
                raise MigrationCheckpointConflict("terminal migration jobs cannot be mutated")
            self._assert_claim(job, claim)
            if certificate is not None:
                _assert_certificate_matches_job(job, certificate)
                assert self._certificate_verifier is not None  # checked by attach_certificate
                self._certificate_verifier.verify(job, certificate)
            updated = mutation(job).model_copy(update={"version": job.version + 1, "updated_at": _now()})
            tx.set(ref, updated.model_dump(mode="python"))
            return updated

        return self._run(update)


MemoryMigrationStore = FirestoreMigrationStore
InMemoryCheckpointStore = InMemoryMigrationStore
