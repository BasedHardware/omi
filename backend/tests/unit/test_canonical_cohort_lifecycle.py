from types import SimpleNamespace

import pytest

from database.memory_collections import MemoryCollections
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.memory import canonical_cohort_lifecycle as lifecycle


class _Db(StrictFirestore):
    def __init__(self, docs=None):
        super().__init__({tuple(path.split("/")): payload for path, payload in (docs or {}).items()})

    def document(self, path):
        return StrictFirestoreDocument(self, tuple(path.split("/")))

    def payload(self, path):
        return self.rows[tuple(path.split("/"))]


def _path(uid):
    return MemoryCollections(uid=uid).memory_control_state


def test_lifecycle_advances_only_exact_inert_control_and_runs_bounded_apply(monkeypatch):
    uid = "cohort-a"
    db = _Db({_path(uid): lifecycle._inert_control_payload(uid)})
    onboarding = SimpleNamespace(created_uids=(), preserved_uids=(uid,))
    page = SimpleNamespace(summary=SimpleNamespace(read_ready_count=1))
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda _db: onboarding)
    calls = []
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **kwargs: calls.append(kwargs) or page,
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda _db: SimpleNamespace(read=lambda _uid: SimpleNamespace(state="not_started")),
    )

    report = lifecycle.run_canonical_cohort_lifecycle(db_client=db)

    assert report.write_enrolled_uids == (uid,)
    assert report.preserved_uids == ()
    assert db.payload(_path(uid)) == lifecycle._write_control_payload(uid)
    assert calls[0]["db_client"] is db
    assert calls[0]["config"].dry_run is False


def test_lifecycle_preserves_existing_write_or_read_state(monkeypatch):
    uid = "cohort-a"
    existing = lifecycle._write_control_payload(uid)
    existing["mode"] = "read"
    db = _Db({_path(uid): existing})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda _db: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=0)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda _db: SimpleNamespace(read=lambda _uid: SimpleNamespace(state="not_started")),
    )

    report = lifecycle.run_canonical_cohort_lifecycle(db_client=db)

    assert report.write_enrolled_uids == ()
    assert report.preserved_uids == (uid,)
    assert db.transactions[-1].sets == []


def test_lifecycle_fails_closed_for_non_scheduler_owned_off_state(monkeypatch):
    uid = "cohort-a"
    malformed = lifecycle._inert_control_payload(uid)
    malformed["grants"] = {"omi_chat": {"default_memory": True, "archive": False}}
    db = _Db({_path(uid): malformed})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda _db: SimpleNamespace())

    with pytest.raises(RuntimeError, match="unsupported_canonical_rollout_state"):
        lifecycle.run_canonical_cohort_lifecycle(db_client=db)

    assert db.transactions[-1].sets == []


def test_terminal_backfill_reconciles_only_the_scheduler_owned_write_generation(monkeypatch):
    uid = "cohort-a"
    db = _Db({_path(uid): lifecycle._write_control_payload(uid)})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda _db: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=1)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda _db: SimpleNamespace(read=lambda _uid: SimpleNamespace(state=lifecycle.MigrationState.read_ready)),
    )
    monkeypatch.setattr(
        lifecycle,
        "read_memory_v3_trusted_account_generation",
        lambda **kwargs: SimpleNamespace(require_account_generation=lambda: 1),
    )

    report = lifecycle.run_canonical_cohort_lifecycle(db_client=db)

    assert report.backfill_ready_uids == (uid,)
    assert report.generation_reconciled_uids == (uid,)
    assert db.payload(_path(uid))["account_generation"] == 1


def test_terminal_backfill_reconciles_a_newer_trusted_head_after_a_prior_scheduler_generation(monkeypatch):
    uid = "cohort-a"
    db = _Db({_path(uid): lifecycle._write_control_payload(uid, account_generation=1)})
    seen_transactions = []
    monkeypatch.setattr(
        lifecycle,
        "read_memory_v3_trusted_account_generation",
        lambda **kwargs: seen_transactions.append(kwargs["transaction"])
        or SimpleNamespace(require_account_generation=lambda: 2),
    )

    reconciled = lifecycle._reconcile_terminal_backfill_generation(uid=uid, db_client=db)

    assert reconciled is True
    assert len(seen_transactions) == 1
    assert db.payload(_path(uid)) == lifecycle._write_control_payload(uid, account_generation=2)


def test_terminal_backfill_never_updates_a_read_control_generation(monkeypatch):
    uid = "cohort-a"
    control = lifecycle._write_control_payload(uid)
    control.update({"mode": "read", "account_generation": 0, "fallback_projection_ready": True})
    db = _Db({_path(uid): control})
    monkeypatch.setattr(lifecycle, "list_canonical_cohort_uids", lambda: [uid])
    monkeypatch.setattr(lifecycle, "reconcile_canonical_memory_onboarding", lambda _db: SimpleNamespace())
    monkeypatch.setattr(
        lifecycle,
        "run_canonical_legacy_backfill_page",
        lambda **_kwargs: SimpleNamespace(summary=SimpleNamespace(read_ready_count=1)),
    )
    monkeypatch.setattr(
        lifecycle,
        "FirestoreCheckpointStore",
        lambda _db: SimpleNamespace(read=lambda _uid: SimpleNamespace(state=lifecycle.MigrationState.read_ready)),
    )
    monkeypatch.setattr(
        lifecycle,
        "read_memory_v3_trusted_account_generation",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("manual/read controls must not load a trusted head")),
    )

    report = lifecycle.run_canonical_cohort_lifecycle(db_client=db)

    assert report.generation_reconciled_uids == ()
    assert db.payload(_path(uid))["account_generation"] == 0
