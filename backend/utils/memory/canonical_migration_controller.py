"""Thin reconciliation coordinator for a legacy-to-canonical migration.

It makes no item-level writes. Callers enumerate a legacy source, submit
deterministic operations through the normal canonical apply boundary, then
provide a fresh convergence certificate before the store performs cutover.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol
from models.memory_migration import (
    CanonicalMigrationJob,
    MigrationClaim,
    MigrationPageReceipt,
    MigrationVerificationCertificate,
)


class MigrationOrchestrationError(RuntimeError):
    pass


class MigrationJobStore(Protocol):
    def read_job(self, uid: str, job_id: str) -> Optional[CanonicalMigrationJob]: ...

    def write_page_receipt(
        self, uid: str, job_id: str, claim: MigrationClaim, receipt: MigrationPageReceipt
    ) -> MigrationPageReceipt: ...

    def attach_certificate(
        self, uid: str, job_id: str, claim: MigrationClaim, certificate: MigrationVerificationCertificate
    ) -> CanonicalMigrationJob: ...

    def cutover(
        self, uid: str, job_id: str, claim: MigrationClaim, *, expected_head_commit_id: str
    ) -> CanonicalMigrationJob: ...


@dataclass(frozen=True)
class MigrationRunResult:
    job: CanonicalMigrationJob
    receipts: tuple[MigrationPageReceipt, ...] = ()


class CanonicalMigrationReconciler:
    def __init__(self, store: MigrationJobStore):
        self.store = store

    def reconcile_pages(
        self, job: CanonicalMigrationJob, claim: MigrationClaim, receipts: Iterable[MigrationPageReceipt]
    ) -> MigrationRunResult:
        written = tuple(self.store.write_page_receipt(job.uid, job.job_id, claim, receipt) for receipt in receipts)
        return MigrationRunResult(job=self.store.read_job(job.uid, job.job_id) or job, receipts=written)

    def certify_and_cutover(
        self, job: CanonicalMigrationJob, claim: MigrationClaim, certificate: MigrationVerificationCertificate
    ) -> MigrationRunResult:
        certified = self.store.attach_certificate(job.uid, job.job_id, claim, certificate)
        if certified.claim is None:
            raise MigrationOrchestrationError("certificate write unexpectedly removed migration claim")
        complete = self.store.cutover(
            job.uid, job.job_id, certified.claim, expected_head_commit_id=certificate.canonical_head_commit_id
        )
        return MigrationRunResult(job=complete)


__all__ = ["CanonicalMigrationReconciler", "MigrationOrchestrationError", "MigrationRunResult"]
