from types import SimpleNamespace
from unittest.mock import MagicMock
import threading

import pytest
from datetime import timedelta

from database import legal_holds


class _Snapshot:
    def __init__(self, payload=None):
        self._payload = payload
        self.exists = payload is not None

    def to_dict(self):
        return dict(self._payload or {})


class _Reference:
    def __init__(self, client, path):
        self.client = client
        self.path = path

    def get(self, transaction=None):
        del transaction
        return _Snapshot(self.client.docs.get(self.path))


class _Collection:
    def __init__(self, client, path):
        self.client = client
        self.path = path

    def document(self, document_id):
        return _Reference(self.client, f"{self.path}/{document_id}")


class _Transaction:
    def __init__(self, client):
        self.client = client

    def set(self, reference, payload, merge=False):
        current = dict(self.client.docs.get(reference.path, {})) if merge else {}
        self.client.docs[reference.path] = {**current, **payload}


class _FakeClient:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def collection(self, path):
        return _Collection(self, path)

    def transaction(self):
        return _Transaction(self)


def _gate(*, token="token-1", state="running", kind="explicit_memory_deletion", started_at=None):
    return {
        "schema_version": "legal_hold_deletion_gate.v1",
        "uid": "uid1",
        "kind": kind,
        "token": token,
        "state": state,
        "started_at": started_at or legal_holds.datetime.now(legal_holds.timezone.utc),
        "finished_at": None,
    }


def _client_for(*, exists: bool, data: dict | None = None):
    snapshot = SimpleNamespace(exists=exists, to_dict=lambda: data or {})
    document = MagicMock()
    document.get.return_value = snapshot
    collection = MagicMock()
    collection.document.return_value = document
    client = MagicMock()
    client.document.return_value = document
    client.collection.return_value = collection
    return client


def test_missing_hold_allows_deletion(monkeypatch):
    client = _client_for(exists=False)
    monkeypatch.setattr(legal_holds, "account_deletion_firestore_client", lambda **_kwargs: client)

    legal_holds.assert_account_deletion_permitted("uid1")

    client.document.assert_called_once_with("legal_holds/uid1")


def test_active_admin_hold_blocks_deletion():
    client = _client_for(
        exists=True,
        data={"schema_version": "legal_hold.v1", "issuer": "admin", "active": True},
    )

    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


def test_inactive_service_hold_allows_deletion():
    client = _client_for(
        exists=True,
        data={"schema_version": "legal_hold.v1", "issuer": "legal_hold_service", "active": False},
    )

    legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


@pytest.mark.parametrize(
    "data",
    [
        {"schema_version": "legal_hold.v1", "issuer": "user", "active": True},
        {"schema_version": "unknown", "issuer": "admin", "active": True},
        {"schema_version": "legal_hold.v1", "issuer": "admin", "active": "true"},
    ],
)
def test_malformed_or_user_owned_hold_fails_closed(data):
    client = _client_for(exists=True, data=data)

    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


def test_authority_read_error_fails_closed():
    client = MagicMock()
    client.collection.side_effect = RuntimeError("firestore unavailable")

    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds.assert_account_deletion_permitted("uid1", firestore_client=client)


def test_acquire_gate_and_hold_placement_have_one_winner():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient()

    legal_holds._acquire_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "explicit_memory_deletion", "token-1", now
    )

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._place_legal_hold_transaction.to_wrap(client.transaction(), client, "uid1", "admin", True, now)
    assert "legal_holds/uid1" not in client.docs


def test_active_hold_blocks_gate_without_mutation():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient(
        {
            "legal_holds/uid1": {
                "schema_version": "legal_hold.v1",
                "issuer": "admin",
                "active": True,
            }
        }
    )

    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "explicit_memory_deletion", "token-1", now
        )
    assert "legal_hold_deletion_gates/uid1" not in client.docs


def test_gate_finish_is_token_cas_and_failed_gate_allows_later_hold():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate()})

    # Wrong token: finish is still token-CAS (row untouched) and the displaced
    # holder now learns it lost authority instead of exiting silently.
    with pytest.raises(legal_holds.DestructiveGateTakeover):
        legal_holds._finish_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "explicit_memory_deletion", "wrong", "failed", now
        )
    assert client.docs["legal_hold_deletion_gates/uid1"]["state"] == "running"

    legal_holds._finish_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "explicit_memory_deletion", "token-1", "failed", now
    )
    legal_holds._place_legal_hold_transaction.to_wrap(
        client.transaction(), client, "uid1", "legal_hold_service", True, now
    )
    assert client.docs["legal_holds/uid1"]["active"] is True


def test_irreversible_transaction_revalidates_matching_hold_and_gate():
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate()})

    legal_holds.assert_destructive_operation_transaction(
        client.transaction(),
        client,
        uid="uid1",
        kind="explicit_memory_deletion",
        token="token-1",
    )

    client.docs["legal_holds/uid1"] = {
        "schema_version": "legal_hold.v1",
        "issuer": "admin",
        "active": True,
    }
    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds.assert_destructive_operation_transaction(
            client.transaction(),
            client,
            uid="uid1",
            kind="explicit_memory_deletion",
            token="token-1",
        )


def test_obsolete_writer_gate_never_blocks_deletion_acquisition():
    """Provider writes no longer own the gate; a lingering writer-kind row is
    always an abandoned artifact and must not block destructive work."""

    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient()

    legal_holds._acquire_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "external_data_write", "writer-token", now
    )

    legal_holds._acquire_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "account_deletion", "delete-token", now
    )
    assert client.docs["legal_hold_deletion_gates/uid1"]["kind"] == "account_deletion"


def test_live_destructive_gate_still_has_exactly_one_owner():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient()

    legal_holds._acquire_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "account_deletion", "delete-token", now
    )

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "explicit_memory_deletion", "memory-token", now
        )


def test_stale_destructive_gate_is_taken_over_instead_of_bricking_the_account():
    """A gate whose holder crashed self-expires: without this, one crash between
    acquire and finish permanently blocks every gated operation for the uid."""

    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    stale_started = now - timedelta(seconds=legal_holds.GATE_STALE_AFTER_SECONDS + 60)
    client = _FakeClient(
        {"legal_hold_deletion_gates/uid1": _gate(kind="account_deletion", token="dead-token", started_at=stale_started)}
    )

    legal_holds._acquire_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "explicit_memory_deletion", "new-token", now
    )
    gate = client.docs["legal_hold_deletion_gates/uid1"]
    assert gate["token"] == "new-token"
    assert gate["kind"] == "explicit_memory_deletion"


def test_external_write_fence_takes_no_lock_and_allows_concurrency():
    client = _FakeClient()

    with legal_holds.external_write_fence("uid1", firestore_client=client):
        # A second concurrent write for the same account must not contend.
        with legal_holds.external_write_fence("uid1", firestore_client=client):
            pass
    assert "legal_hold_deletion_gates/uid1" not in client.docs


def test_external_write_fence_blocks_during_account_deletion():
    client = _FakeClient({"account_deletions/uid1": {"wipe_status": "accepted"}})

    with pytest.raises(legal_holds.DestructiveOperationInProgress, match="account deletion"):
        with legal_holds.external_write_fence("uid1", firestore_client=client):
            raise AssertionError("write must not proceed")


def test_external_write_fence_blocks_during_live_destructive_gate_but_not_stale():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate(kind="explicit_memory_deletion", token="live-token")})
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.external_write_fence("uid1", firestore_client=client):
            raise AssertionError("write must not proceed")

    stale_started = now - timedelta(seconds=legal_holds.GATE_STALE_AFTER_SECONDS + 60)
    client.docs["legal_hold_deletion_gates/uid1"] = _gate(
        kind="explicit_memory_deletion", token="dead-token", started_at=stale_started
    )
    with legal_holds.external_write_fence("uid1", firestore_client=client):
        pass


def test_account_deletion_marker_blocks_stale_external_writer_before_provider_work():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient({"account_deletions/uid1": {"wipe_status": "accepted"}})

    with pytest.raises(legal_holds.DestructiveOperationInProgress, match="account deletion"):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "external_data_write", "writer-token", now
        )
    assert "legal_hold_deletion_gates/uid1" not in client.docs


def test_inflight_deletion_blocks_external_writer_before_provider_work():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate(token="delete-token")})

    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "external_data_write", "writer-token", now
        )


def test_concurrent_same_kind_delete_waits_then_acquires_after_release(monkeypatch):
    """Same-kind contenders queue on the account gate; fences stay blocked."""
    client = _FakeClient()
    gate_lock = threading.Lock()

    def acquire(uid, *, kind, token, firestore_client=None, now=None):
        current = now or legal_holds.datetime.now(legal_holds.timezone.utc)
        with gate_lock:
            legal_holds._acquire_destructive_operation_transaction.to_wrap(
                client.transaction(), client, uid, kind, token, current
            )

    def finish(uid, *, kind, token, outcome, firestore_client=None, now=None):
        current = now or legal_holds.datetime.now(legal_holds.timezone.utc)
        with gate_lock:
            legal_holds._finish_destructive_operation_transaction.to_wrap(
                client.transaction(), client, uid, kind, token, outcome, current
            )

    monkeypatch.setattr(legal_holds, "acquire_destructive_operation", acquire)
    monkeypatch.setattr(legal_holds, "finish_destructive_operation", finish)
    monkeypatch.setattr(legal_holds, "account_deletion_firestore_client", lambda **_kwargs: client)

    started = threading.Event()
    release = threading.Event()
    outcomes: list[str] = []

    def holder():
        with legal_holds.destructive_operation_gate("uid1", firestore_client=client):
            started.set()
            assert release.wait(timeout=5)
            outcomes.append("first_ok")

    def contender():
        assert started.wait(timeout=5)
        try:
            with legal_holds.external_write_fence("uid1", firestore_client=client):
                outcomes.append("fence_leaked")
        except legal_holds.DestructiveOperationInProgress:
            outcomes.append("fence_blocked")
        # While the holder is inside the gate, a same-kind acquire still raises.
        try:
            with legal_holds.destructive_operation_gate("uid1", firestore_client=client):
                outcomes.append("second_ok_early")
        except legal_holds.DestructiveOperationInProgress:
            outcomes.append("second_blocked_while_held")
        release.set()
        deadline = legal_holds.datetime.now(legal_holds.timezone.utc)
        import time as _time

        for _ in range(100):
            if "first_ok" in outcomes:
                break
            _time.sleep(0.05)
        # After the holder releases, the same-kind contender acquires cleanly.
        with legal_holds.destructive_operation_gate("uid1", firestore_client=client):
            outcomes.append("second_ok")

    first = threading.Thread(target=holder)
    second = threading.Thread(target=contender)
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)
    assert not first.is_alive() and not second.is_alive()
    assert outcomes.count("first_ok") == 1
    assert outcomes.count("second_blocked_while_held") == 1
    assert "second_ok_early" not in outcomes
    assert outcomes.count("second_ok") == 1
    assert "fence_blocked" in outcomes
    assert "fence_leaked" not in outcomes
    assert legal_holds.GATE_STALE_AFTER_SECONDS == 6 * 60 * 60


@pytest.mark.parametrize("kind", ["explicit_memory_deletion", "retention_cleanup", "account_deletion"])
def test_same_kind_fresh_gate_still_blocks(kind):
    """Any fresh running gate — same kind included — blocks acquisition.

    Replacing a fresh same-kind token would let the replaced holder's
    check-then-delete chunks continue after a legal hold lands (the peer can
    finish the single gate row while the original holder is still mid-loop).
    Same-kind overlap therefore waits like every other kind; only stale
    (6h) and obsolete-kind rows are takeover candidates.
    """
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    original = _gate(kind=kind)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": original})
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", kind, "peer-token", now
        )
    assert client.docs["legal_hold_deletion_gates/uid1"] == original


@pytest.mark.parametrize(
    "owner,attempt",
    [
        ("retention_cleanup", "explicit_memory_deletion"),
        ("explicit_memory_deletion", "retention_cleanup"),
        ("account_deletion", "retention_cleanup"),
    ],
)
def test_different_kind_fresh_gate_still_blocks(owner, attempt):
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    original = _gate(kind=owner)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": original})
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        legal_holds._acquire_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", attempt, "peer-token", now
        )
    assert client.docs["legal_hold_deletion_gates/uid1"] == original


@pytest.mark.parametrize("state", ["running", "completed", "failed"])
def test_finish_same_kind_takeover_never_mutates_peer(state):
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    original = _gate(token="peer-token", state=state)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": original})
    # The displaced holder must not exit reporting success: a same-kind peer
    # owns the row now, so finish raises the takeover signal and preserves it.
    with pytest.raises(legal_holds.DestructiveGateTakeover):
        legal_holds._finish_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "explicit_memory_deletion", "old-token", "completed", now
        )
    assert client.docs["legal_hold_deletion_gates/uid1"] == original


def test_finish_refuses_different_kind_fresh_owner():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    original = _gate(kind="account_deletion", token="peer-token")
    client = _FakeClient({"legal_hold_deletion_gates/uid1": original})
    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds._finish_destructive_operation_transaction.to_wrap(
            client.transaction(), client, "uid1", "explicit_memory_deletion", "old-token", "completed", now
        )
    assert client.docs["legal_hold_deletion_gates/uid1"] == original


@pytest.mark.parametrize("outcome", ["failed", "completed"])
def test_finish_same_outcome_is_idempotent_but_opposite_outcome_fails(outcome):
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    original = _gate(state=outcome)
    client = _FakeClient({"legal_hold_deletion_gates/uid1": original})
    legal_holds._finish_destructive_operation_transaction.to_wrap(
        client.transaction(), client, "uid1", "explicit_memory_deletion", "token-1", outcome, now
    )
    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds._finish_destructive_operation_transaction.to_wrap(
            client.transaction(),
            client,
            "uid1",
            "explicit_memory_deletion",
            "token-1",
            "failed" if outcome == "completed" else "completed",
            now,
        )
    assert client.docs["legal_hold_deletion_gates/uid1"] == original


def test_six_hour_takeover_boundary_is_unchanged():
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    gate = _gate(kind="account_deletion", started_at=now - timedelta(hours=6))
    assert not legal_holds._gate_blocks(gate, now, kind="explicit_memory_deletion")
    assert legal_holds._gate_blocks(gate, now - timedelta(microseconds=1), kind="explicit_memory_deletion")


@pytest.mark.parametrize(
    "state,token", [("running", "peer"), ("completed", "peer"), ("completed", "token-1"), ("failed", "token-1")]
)
def test_revalidation_stops_rotated_or_finished_holder(state, token):
    client = _FakeClient({"legal_hold_deletion_gates/uid1": _gate(state=state, token=token)})
    with pytest.raises(legal_holds.DestructiveGateTakeover):
        legal_holds.assert_destructive_gate_still_ours(
            "uid1", "explicit_memory_deletion", token="token-1", firestore_client=client
        )


@pytest.mark.parametrize("payload", [None, {}, {"schema_version": "unsupported"}])
def test_revalidation_missing_or_malformed_gate_fails_closed(payload):
    client = _FakeClient({"legal_hold_deletion_gates/uid1": payload} if payload is not None else {})
    with pytest.raises(legal_holds.LegalHoldAuthorityUnavailable):
        legal_holds.assert_destructive_gate_still_ours(
            "uid1", "explicit_memory_deletion", token="token-1", firestore_client=client
        )


def test_active_context_revalidation_detects_stale_takeover(monkeypatch):
    """A stale (6h) takeover rotates the token; the old holder's next chunk aborts."""
    client = _FakeClient()
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    monkeypatch.setattr(
        legal_holds,
        "_acquire_destructive_operation_transaction",
        legal_holds._acquire_destructive_operation_transaction.to_wrap,
    )
    monkeypatch.setattr(
        legal_holds,
        "_finish_destructive_operation_transaction",
        legal_holds._finish_destructive_operation_transaction.to_wrap,
    )
    # The holder that lost authority mid-flight cannot exit reporting success
    # either: both its next chunk and its context-manager exit surface takeover.
    with pytest.raises(legal_holds.DestructiveGateTakeover):
        with legal_holds.destructive_operation_gate("uid1", firestore_client=client):
            legal_holds.assert_destructive_gate_still_ours("uid1", "explicit_memory_deletion", firestore_client=client)
            future = now + timedelta(seconds=legal_holds.GATE_STALE_AFTER_SECONDS + 1)
            legal_holds.acquire_destructive_operation(
                "uid1", kind="explicit_memory_deletion", token="peer", firestore_client=client, now=future
            )
            with pytest.raises(legal_holds.DestructiveGateTakeover):
                legal_holds.assert_destructive_gate_still_ours(
                    "uid1", "explicit_memory_deletion", firestore_client=client
                )


def test_stale_holder_exit_cannot_report_success_after_takeover(monkeypatch):
    """The displaced holder's context-manager exit raises instead of succeeding.

    A stale (6h-bound) gate is rotated by a same-kind peer; the original
    holder may have already finished its chunks without revalidating, so its
    ``__exit__`` path must surface the takeover rather than exit cleanly.
    """
    client = _FakeClient()
    now = legal_holds.datetime.now(legal_holds.timezone.utc)
    monkeypatch.setattr(
        legal_holds,
        "_acquire_destructive_operation_transaction",
        legal_holds._acquire_destructive_operation_transaction.to_wrap,
    )
    monkeypatch.setattr(
        legal_holds,
        "_finish_destructive_operation_transaction",
        legal_holds._finish_destructive_operation_transaction.to_wrap,
    )
    with pytest.raises(legal_holds.DestructiveGateTakeover):
        with legal_holds.destructive_operation_gate("uid1", firestore_client=client):
            # The peer rotates the token past the staleness bound while the
            # original holder is still inside the gate.
            future = now + timedelta(seconds=legal_holds.GATE_STALE_AFTER_SECONDS + 1)
            legal_holds.acquire_destructive_operation(
                "uid1", kind="explicit_memory_deletion", token="peer", firestore_client=client, now=future
            )
    # The stale holder's exit raised DestructiveGateTakeover (never success),
    # and the peer's running row was preserved untouched.
    gate = client.docs["legal_hold_deletion_gates/uid1"]
    assert gate["token"] == "peer" and gate["state"] == "running"
