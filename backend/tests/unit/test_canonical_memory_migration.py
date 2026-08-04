from datetime import timedelta
import pytest
from database.memory_migration_store import (
    HmacMigrationCertificateVerifier,
    InMemoryMigrationStore,
    MigrationCheckpointConflict,
    MigrationFenceConflict,
    MigrationLeaseLost,
    MigrationLeaseUnavailable,
    _read_stage_control_transition,
)
from models.memory_migration import (
    CanonicalMigrationJob,
    MigrationPageReceipt,
    MigrationSurface,
    MigrationVerificationCertificate,
)
from utils.memory.canonical_migration_controller import CanonicalMigrationReconciler
from utils.memory.v3.compatibility_projection_sync import _validated_projection_fences


def _job():
    return CanonicalMigrationJob.new(
        uid="u1",
        transform_version="legacy-v1",
        policy_version="policy-v1",
        source_adapter_version="source-v1",
        account_generation=2,
        source_generation=3,
        required_surfaces=list(MigrationSurface),
        job_id="job1",
    ).model_copy(update={"source_snapshot_token": "snapshot-9", "source_digest": "digest-9"})


def _certificate():
    return MigrationVerificationCertificate(
        uid="u1",
        job_id="job1",
        account_generation=2,
        source_generation=3,
        transform_version="legacy-v1",
        policy_version="policy-v1",
        source_adapter_version="source-v1",
        projection_rebuild_id="rebuild-9",
        verifier_id="test-verifier",
        verification_run_id="run-9",
        signature="test-signature",
        canonical_head_commit_id="head-9",
        canonical_head_sequence=9,
        source_snapshot_token="snapshot-9",
        source_digest="digest-9",
        required_surfaces=list(MigrationSurface),
        converged_surfaces=list(MigrationSurface),
    )


def test_each_claim_gets_a_new_epoch_and_random_claim_id_even_for_same_owner():
    store = InMemoryMigrationStore()
    store.create_job(_job())
    first = store.claim_job("u1", "job1", "worker-a")
    first_claim = first.claim
    assert first_claim is not None
    first = store.renew_claim("u1", "job1", first_claim)
    assert first.claim is not None
    with pytest.raises(MigrationLeaseUnavailable):
        store.claim_job("u1", "job1", "worker-a")
    expired_claim = first.claim.model_copy(update={"expires_at": first.claim.renewed_at - timedelta(seconds=1)})
    store._jobs[("u1", "job1")] = first.model_copy(update={"claim": expired_claim})
    second = store.claim_job("u1", "job1", "worker-a")
    assert second.claim is not None and second.claim.claim_epoch == first_claim.claim_epoch + 1
    assert second.claim.claim_id != first_claim.claim_id


def test_stale_or_other_worker_cannot_write_page_receipt():
    store = InMemoryMigrationStore()
    store.create_job(_job())
    claimed = store.claim_job("u1", "job1", "worker-a")
    claim = claimed.claim
    assert claim is not None
    with pytest.raises(MigrationLeaseUnavailable):
        store.claim_job("u1", "job1", "worker-b")
    receipt = MigrationPageReceipt(
        page_id="p1", source_cursor="cursor-1", source_digest="digest-1", operation_ids=["op-1"]
    )
    store.write_page_receipt("u1", "job1", claim, receipt)
    expired_claim = claim.model_copy(update={"expires_at": claim.renewed_at - timedelta(seconds=1)})
    store._jobs[("u1", "job1")] = claimed.model_copy(update={"claim": expired_claim})
    replacement = store.claim_job("u1", "job1", "worker-a")
    with pytest.raises(MigrationLeaseLost):
        store.write_page_receipt("u1", "job1", claim, receipt)
    assert replacement.claim is not None


def test_page_receipts_are_create_only_and_do_not_store_source_records():
    store = InMemoryMigrationStore()
    store.create_job(_job())
    job = store.claim_job("u1", "job1", "worker-a")
    claim = job.claim
    assert claim is not None
    stored = store.write_page_receipt(
        "u1",
        "job1",
        claim,
        MigrationPageReceipt(
            page_id="p1",
            source_cursor="cursor",
            source_digest="digest",
            operation_ids=["op-1"],
            terminal_outcome_count=1,
        ),
    )
    assert stored.operation_ids == ["op-1"]
    replay = stored.model_copy(update={"created_at": stored.created_at + timedelta(seconds=5)})
    assert store.write_page_receipt("u1", "job1", claim, replay) == stored
    with pytest.raises(MigrationFenceConflict):
        store.write_page_receipt("u1", "job1", claim, stored.model_copy(update={"source_digest": "other"}))


def test_cutover_is_fenced_by_an_exact_fresh_certificate():
    store = InMemoryMigrationStore()
    store.create_job(_job())
    job = store.claim_job("u1", "job1", "worker-a")
    claim = job.claim
    assert claim is not None
    with pytest.raises(MigrationFenceConflict):
        store.cutover("u1", "job1", claim, expected_head_commit_id="head-9")
    reconciler = CanonicalMigrationReconciler(store)
    result = reconciler.certify_and_cutover(job, claim, _certificate())
    assert result.job.state.value == "complete" and result.job.cutover_head_commit_id == "head-9"


def test_certificate_rejects_missing_surface_or_mismatch():
    with pytest.raises(ValueError):
        MigrationVerificationCertificate(
            uid="u1",
            job_id="job1",
            account_generation=2,
            source_generation=3,
            transform_version="legacy-v1",
            policy_version="policy-v1",
            source_adapter_version="source-v1",
            projection_rebuild_id="rebuild-9",
            verifier_id="test-verifier",
            verification_run_id="run-9",
            canonical_head_commit_id="h",
            canonical_head_sequence=1,
            source_snapshot_token="s",
            source_digest="d",
            required_surfaces=list(MigrationSurface),
            converged_surfaces=[MigrationSurface.canonical],
        )


def test_terminal_job_cannot_be_reclaimed_and_certificate_surface_order_is_ignored():
    store = InMemoryMigrationStore()
    store.create_job(_job())
    claimed = store.claim_job("u1", "job1", "worker-a")
    assert claimed.claim is not None
    certificate = _certificate().model_copy(
        update={
            "required_surfaces": list(reversed(list(MigrationSurface))),
            "converged_surfaces": list(reversed(list(MigrationSurface))),
        }
    )
    complete = CanonicalMigrationReconciler(store).certify_and_cutover(claimed, claimed.claim, certificate)
    assert complete.job.state.value == "complete"
    with pytest.raises(MigrationCheckpointConflict):
        store.claim_job("u1", "job1", "worker-a")


def test_certificate_is_bound_to_the_exact_job_snapshot_and_terminal_cutover_is_idempotent():
    store = InMemoryMigrationStore()
    store.create_job(_job())
    claimed = store.claim_job("u1", "job1", "worker-a")
    assert claimed.claim is not None
    with pytest.raises(MigrationFenceConflict, match="identity"):
        store.attach_certificate(
            "u1", "job1", claimed.claim, _certificate().model_copy(update={"source_digest": "different"})
        )
    complete = CanonicalMigrationReconciler(store).certify_and_cutover(claimed, claimed.claim, _certificate()).job
    # A lost response may retry the exact operation after the lease was cleared;
    # it must not re-open or mutate the terminal job.
    assert store.cutover("u1", "job1", claimed.claim, expected_head_commit_id="head-9") == complete
    assert complete.claim is None


def test_hmac_verifier_rejects_tampered_certificate():
    certificate = _certificate()
    verifier = HmacMigrationCertificateVerifier(verifier_id="test-verifier", signing_key=b"not-a-production-key")
    signed = certificate.model_copy(update={"signature": verifier.sign(certificate)})
    verifier.verify(_job(), signed)
    with pytest.raises(MigrationFenceConflict, match="signature"):
        verifier.verify(_job(), signed.model_copy(update={"canonical_head_sequence": 10}))


def test_migration_job_requires_all_surfaces_and_known_schema_version():
    payload = _job().model_dump(mode="python")
    payload["required_surfaces"] = [MigrationSurface.canonical]
    with pytest.raises(ValueError, match="every migration surface"):
        CanonicalMigrationJob.model_validate(payload)

    payload = _job().model_dump(mode="python")
    payload["schema_version"] = "canonical_memory_migration.v1"
    with pytest.raises(ValueError):
        CanonicalMigrationJob.model_validate(payload)


def test_read_stage_transition_publishes_all_per_user_gates():
    transition = _read_stage_control_transition(
        control_data={
            "uid": "u1",
            "schema_version": 1,
            "mode": "write",
            "mode_epoch": 4,
            "cutover_epoch": 0,
            "account_generation": 2,
            "stage_gates": {"shadow": "passed", "write": "passed", "read": "blocked"},
            "grants": {"omi_chat": {"default_memory": False, "archive": False}},
        },
        uid="u1",
        account_generation=2,
    )
    assert transition["mode"] == "read"
    assert transition["mode_epoch"] == 5
    assert transition["cutover_epoch"] == 5
    assert transition["fallback_projection_ready"] is True
    assert transition["persistent_memory_writes_started"] is True
    assert transition["writes_blocked"] is False
    assert transition["stage_gates"] == {"shadow": "passed", "write": "passed", "read": "passed"}
    assert transition["grants"] == {"omi_chat": {"default_memory": True, "archive": False}}


def test_read_stage_transition_fails_closed_for_malformed_control():
    with pytest.raises(MigrationFenceConflict):
        _read_stage_control_transition(control_data={"uid": "u1"}, uid="u1", account_generation=2)


def test_projection_writer_admission_is_independent_from_reader_readiness():
    state = {
        "uid": "u1",
        "schema_version": 1,
        "source": "memory_items_projection",
        "ready": False,
        "writer_admission_ready": True,
        "projection_version": "v3_memorydb_compatibility",
        "account_generation": 2,
        "projection_generation": 2,
        "freshness_fence_generation": 2,
        "tombstone_fence_generation": 2,
        "vector_cleanup_fence_generation": 2,
        "source_commit_id": "head-2",
        "projection_commit_id": "commit-head-2",
        "projection_evidence_fence": "head-head-2",
        "source_evidence_fence": "head-head-2",
        "source_version": "v1",
        "write_convergence_complete": True,
        "delete_convergence_complete": True,
        "tombstone_convergence_complete": True,
    }
    assert _validated_projection_fences(uid="u1", account_generation=2, state=state)["source_commit_id"] == "head-2"
