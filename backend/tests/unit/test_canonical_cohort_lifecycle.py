from types import SimpleNamespace

import pytest

from database.memory_collections import MemoryCollections
from tests.store_fakes import FakeDocumentStore
from utils.memory import canonical_cohort_lifecycle as lifecycle


def _seeded_store(monkeypatch, docs=None) -> FakeDocumentStore:
    """Install an in-memory neutral store and route the module's facade through it.

    The lifecycle port persists through ``document_store.run_transaction`` (ADR-0028,
    no ``db_client`` handle), so the tests seed a ``FakeDocumentStore`` and monkeypatch
    the facade the module imported instead of a raw Firestore fake.
    """
    store = FakeDocumentStore()
    for path, payload in (docs or {}).items():
        store.set(path, payload)
    monkeypatch.setattr(lifecycle, "document_store", SimpleNamespace(run_transaction=store.run_transaction))
    return store


def _path(uid):
    return MemoryCollections(uid=uid).memory_control_state


def test_lifecycle_advances_only_exact_inert_control_and_runs_bounded_apply(monkeypatch):
    uid = "cohort-a"
    store = _seeded_store(monkeypatch, {_path(uid): lifecycle._inert_control_payload(uid)})
    onboarding = SimpleNamespace(created_uids=(), preserved_uids=(uid,))
    page = SimpleNamespace(summary=SimpleNamespace(read_ready_count=1))
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda: onboarding)
    calls = []
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **kwargs: calls.append(kwargs) or page,
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda: SimpleNamespace(read=lambda _uid: SimpleNamespace(state="not_started")),
    )

    report = lifecycle.run_canonical_cohort_lifecycle()

    assert report.write_enrolled_uids == (uid,)
    assert report.preserved_uids == ()
    assert store.get(_path(uid)).to_dict() == lifecycle._write_control_payload(uid)
    # The port never threads a db_client; the bounded apply still runs dry_run=False.
    assert "db_client" not in calls[0]
    assert calls[0]["config"].dry_run is False


def test_lifecycle_preserves_existing_write_or_read_state(monkeypatch):
    uid = "cohort-a"
    existing = lifecycle._write_control_payload(uid)
    existing["mode"] = "read"
    store = _seeded_store(monkeypatch, {_path(uid): existing})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=0)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda: SimpleNamespace(read=lambda _uid: SimpleNamespace(state="not_started")),
    )

    report = lifecycle.run_canonical_cohort_lifecycle()

    assert report.write_enrolled_uids == ()
    assert report.preserved_uids == (uid,)
    assert store.get(_path(uid)).to_dict() == existing


def test_lifecycle_fails_closed_for_non_scheduler_owned_off_state(monkeypatch):
    uid = "cohort-a"
    malformed = lifecycle._inert_control_payload(uid)
    malformed["grants"] = {"omi_chat": {"default_memory": True, "archive": False}}
    store = _seeded_store(monkeypatch, {_path(uid): malformed})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda: SimpleNamespace())

    with pytest.raises(RuntimeError, match="unsupported_canonical_rollout_state"):
        lifecycle.run_canonical_cohort_lifecycle()

    assert store.get(_path(uid)).to_dict() == malformed


def test_terminal_backfill_reconciles_only_the_scheduler_owned_write_generation(monkeypatch):
    uid = "cohort-a"
    store = _seeded_store(monkeypatch, {_path(uid): lifecycle._write_control_payload(uid)})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=1)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda: SimpleNamespace(read=lambda _uid: SimpleNamespace(state=lifecycle.MigrationState.read_ready)),
    )
    monkeypatch.setattr(
        lifecycle,
        "read_memory_v3_trusted_account_generation",
        lambda **kwargs: SimpleNamespace(require_account_generation=lambda: 1),
    )

    report = lifecycle.run_canonical_cohort_lifecycle()

    assert report.backfill_ready_uids == (uid,)
    assert report.generation_reconciled_uids == (uid,)
    assert store.get(_path(uid)).to_dict()["account_generation"] == 1


def test_one_principal_missing_state_head_does_not_starve_the_rest_of_the_cohort(monkeypatch):
    """The dev cohort carries synthetic principals with read_ready checkpoints
    and no migrated state head; raising for them starved every other user's
    lifecycle progression on each scheduled run."""
    legacy_uid = "cohort-legacy"
    healthy_uid = "cohort-healthy"
    store = _seeded_store(
        monkeypatch,
        {
            _path(legacy_uid): lifecycle._write_control_payload(legacy_uid),
            _path(healthy_uid): lifecycle._write_control_payload(healthy_uid),
        },
    )
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [legacy_uid, healthy_uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=2)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda: SimpleNamespace(read=lambda _uid: SimpleNamespace(state=lifecycle.MigrationState.read_ready)),
    )

    def _trusted_read(**kwargs):
        uid = kwargs["uid"]
        if uid == legacy_uid:
            return SimpleNamespace(
                require_account_generation=lambda: (_ for _ in ()).throw(
                    lifecycle.V3TrustedAccountGenerationReadError(
                        lifecycle.V3AccountGenerationFailureReason.MISSING_STATE_HEAD
                    )
                )
            )
        return SimpleNamespace(require_account_generation=lambda: 3)

    monkeypatch.setattr(lifecycle, "read_memory_v3_trusted_account_generation", _trusted_read)

    report = lifecycle.run_canonical_cohort_lifecycle()

    assert report.generation_reconciled_uids == (healthy_uid,)
    assert report.generation_reconcile_errors == ()
    assert store.get(_path(healthy_uid)).to_dict()["account_generation"] == 3


def test_a_malformed_state_head_is_reported_per_principal_without_starving_the_cohort(monkeypatch):
    broken_uid = "cohort-broken"
    healthy_uid = "cohort-healthy"
    store = _seeded_store(
        monkeypatch,
        {
            _path(broken_uid): lifecycle._write_control_payload(broken_uid),
            _path(healthy_uid): lifecycle._write_control_payload(healthy_uid),
        },
    )
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [broken_uid, healthy_uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=2)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda: SimpleNamespace(read=lambda _uid: SimpleNamespace(state=lifecycle.MigrationState.read_ready)),
    )

    def _trusted_read(**kwargs):
        uid = kwargs["uid"]
        if uid == broken_uid:
            return SimpleNamespace(
                require_account_generation=lambda: (_ for _ in ()).throw(
                    lifecycle.V3TrustedAccountGenerationReadError(
                        lifecycle.V3AccountGenerationFailureReason.MALFORMED_STATE_HEAD
                    )
                )
            )
        return SimpleNamespace(require_account_generation=lambda: 4)

    monkeypatch.setattr(lifecycle, "read_memory_v3_trusted_account_generation", _trusted_read)

    report = lifecycle.run_canonical_cohort_lifecycle()

    assert report.generation_reconciled_uids == (healthy_uid,)
    assert report.generation_reconcile_errors == (f"uid={broken_uid}: generation_reconcile:malformed_state_head",)
    assert store.get(_path(healthy_uid)).to_dict()["account_generation"] == 4


def test_terminal_backfill_reconciles_a_newer_trusted_head_after_a_prior_scheduler_generation(monkeypatch):
    uid = "cohort-a"
    store = _seeded_store(monkeypatch, {_path(uid): lifecycle._write_control_payload(uid, account_generation=1)})
    seen_transactions = []
    monkeypatch.setattr(
        lifecycle,
        "read_memory_v3_trusted_account_generation",
        lambda **kwargs: seen_transactions.append(kwargs["tx"])
        or SimpleNamespace(require_account_generation=lambda: 2),
    )

    reconciled = lifecycle._reconcile_terminal_backfill_generation(uid=uid)

    assert reconciled is True
    assert len(seen_transactions) == 1
    assert store.get(_path(uid)).to_dict() == lifecycle._write_control_payload(uid, account_generation=2)


def test_terminal_backfill_never_updates_a_read_control_generation(monkeypatch):
    uid = "cohort-a"
    control = lifecycle._write_control_payload(uid)
    control.update({"mode": "read", "account_generation": 0, "fallback_projection_ready": True})
    store = _seeded_store(monkeypatch, {_path(uid): control})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=1)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda: SimpleNamespace(read=lambda _uid: SimpleNamespace(state=lifecycle.MigrationState.read_ready)),
    )
    monkeypatch.setattr(
        lifecycle,
        "read_memory_v3_trusted_account_generation",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("manual/read controls must not load a trusted head")),
    )

    report = lifecycle.run_canonical_cohort_lifecycle()

    assert report.generation_reconciled_uids == ()
    assert store.get(_path(uid)).to_dict()["account_generation"] == 0
