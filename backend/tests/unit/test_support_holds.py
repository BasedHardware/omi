"""Support operator hold commands and their audit trail (support_actions, hold events)."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import pytest

from database import legal_holds, support_actions
from scripts.support import ops
from utils.support import account, holds

UID = "uid-held"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, path, payload):
        self.id = path.rsplit("/", 1)[-1]
        self.exists = payload is not None
        self._payload = payload

    def to_dict(self):
        return dict(self._payload) if self._payload is not None else None


class _Reference:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def get(self, transaction=None, field_paths=None):
        del transaction, field_paths
        return _Snapshot(self.path, self.client.docs.get(self.path))

    def set(self, payload, merge=False):
        if self.client.fail_writes_under and self.path.startswith(self.client.fail_writes_under):
            raise RuntimeError("write refused")
        current = dict(self.client.docs.get(self.path, {})) if merge else {}
        self.client.docs[self.path] = {**current, **payload}


class _Collection:
    def __init__(self, client, path, limit=None, after=None, descending=False):
        self.client, self.path, self._limit, self._after = client, path, limit, after
        self._descending = descending

    def document(self, document_id):
        return _Reference(self.client, f"{self.path}/{document_id}")

    def limit(self, count):
        return _Collection(self.client, self.path, count, self._after, self._descending)

    def order_by(self, field, direction="ASCENDING"):
        assert field == "__name__"  # rows are already in document-id order
        if direction == "DESCENDING":
            # Production has no composite index for a descending id order on these
            # subcollections and answers 400 FailedPrecondition (2026-11-21).
            raise AssertionError("descending __name__ order needs a composite index that does not exist")
        return self

    def start_after(self, snapshot):
        return _Collection(self.client, self.path, self._limit, snapshot.id)

    def stream(self):
        depth = self.path.count("/") + 1
        rows = [
            _Snapshot(path, payload)
            for path, payload in sorted(self.client.docs.items())
            if path.startswith(f"{self.path}/") and path.count("/") == depth
        ]
        if self._descending:
            rows.reverse()
        if self._after is not None:
            rows = [row for row in rows if row.id > self._after]
        return iter(rows[: self._limit] if self._limit is not None else rows)


class _Transaction:
    def __init__(self, client):
        self.client = client

    def set(self, reference, payload, merge=False):
        reference.set(payload, merge=merge)


class _Client:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.fail_writes_under = None

    def document(self, path):
        return _Reference(self, path)

    def collection(self, path):
        return _Collection(self, path)

    def transaction(self):
        return _Transaction(self)


@pytest.fixture
def client(monkeypatch):
    fake = _Client({f"users/{UID}": {"created_at": NOW, "language": "en", "email": "secret@example.com"}})
    monkeypatch.setattr(holds, "_firestore_client", lambda: fake)
    monkeypatch.setattr(account, "_firestore_client", lambda: fake)
    monkeypatch.setattr(holds, "_now", lambda: NOW)
    monkeypatch.setattr(support_actions, "account_deletion_firestore_client", lambda firestore_client=None: fake)
    monkeypatch.setattr(legal_holds, "account_deletion_firestore_client", lambda firestore_client=None: fake)
    # The real writer runs inside Firestore's retrying decorator; drive its body directly.
    monkeypatch.setattr(legal_holds, "_place_legal_hold_transaction", legal_holds._place_legal_hold_transaction.to_wrap)
    return fake


def _ctx(apply=False, ticket="ic-1"):
    return support_actions.ActionContext(
        ticket=ticket, actor="aryan", reason="litigation hold notice", agent="support-vm", apply=apply
    )


def _run(handler, ctx, **kwargs):
    args = argparse.Namespace(uid=UID, **kwargs)
    with support_actions.record_action(ctx, handler.__name__, vars(args), now=lambda: NOW) as record:
        result = handler(args, ctx, record)
    return result, record


def _actions(client):
    return {path: row for path, row in client.docs.items() if path.startswith("support_actions/")}


def test_place_dry_run_writes_only_the_audit_record(client):
    result, record = _run(holds.place, _ctx(), review_by=None)
    assert result["dry_run"] is True
    assert f"legal_holds/{UID}" not in client.docs
    (audit,) = _actions(client).values()
    assert audit["outcome"] == "succeeded" and audit["apply"] is False and audit["ticket"] == "ic-1"
    assert audit["summary"] == {"already_active": False, "review_days": holds.DEFAULT_REVIEW_DAYS}


def test_place_apply_records_ticket_actor_review_date_and_an_event_and_fences_deletion(client):
    result, record = _run(holds.place, _ctx(apply=True), review_by="2027-05-01")
    hold = client.docs[f"legal_holds/{UID}"]
    assert hold["active"] is True and hold["issuer"] == "admin"
    assert hold["ticket"] == "ic-1" and hold["placed_by"] == "aryan" and hold["reason"] == "litigation hold notice"
    assert hold["review_by"] == datetime(2027, 5, 1, tzinfo=timezone.utc)
    events = [row for path, row in client.docs.items() if path.startswith(f"legal_holds/{UID}/events/")]
    assert [event["action"] for event in events] == ["place"] and events[0]["agent"] == "support-vm"
    with pytest.raises(legal_holds.LegalHoldActive):
        legal_holds.assert_account_deletion_permitted(UID, firestore_client=client)
    assert record.summary["fence_verified"] is True
    assert record.before_digest != record.after_digest


def test_place_refreshes_audit_fields_on_a_legacy_hold(client):
    client.docs[f"legal_holds/{UID}"] = {"schema_version": "legal_hold.v1", "issuer": "admin", "active": True}
    result, record = _run(holds.place, _ctx(apply=True), review_by=None)
    assert record.summary["already_active"] is True
    assert client.docs[f"legal_holds/{UID}"]["ticket"] == "ic-1"


def test_place_cannot_overtake_a_running_deletion(client):
    client.docs[f"legal_hold_deletion_gates/{UID}"] = {
        "schema_version": "legal_hold_deletion_gate.v1",
        "uid": UID,
        "kind": "account_deletion",
        "token": "t",
        "state": "running",
        "started_at": NOW,
    }
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        _run(holds.place, _ctx(apply=True), review_by=None)
    assert f"legal_holds/{UID}" not in client.docs
    (audit,) = _actions(client).values()
    assert audit["outcome"] == "failed" and audit["error_type"] == "DestructiveOperationInProgress"


@pytest.mark.parametrize("value", ["2026-11-01", "2030-01-01", "May 1"])
def test_place_rejects_bad_review_dates(client, value):
    with pytest.raises(holds.HoldCommandError):
        _run(holds.place, _ctx(apply=True), review_by=value)


def test_release_requires_an_active_hold(client):
    with pytest.raises(holds.HoldCommandError):
        _run(holds.release, _ctx(apply=True))


def test_release_records_who_and_why_and_flags_held_deletes_without_erasure(client):
    _run(holds.place, _ctx(apply=True), review_by=None)
    client.docs[f"users/{UID}/deleted_conversations/c1"] = {"legal_hold_deferred": True, "erasure_armed": False}
    client.docs[f"users/{UID}/deleted_conversations/c2"] = {"legal_hold_deferred": True, "erasure_armed": True}
    client.docs[f"users/{UID}/deleted_conversations/c3"] = {"conversation_id": "c3"}

    result, record = _run(holds.release, _ctx(apply=True, ticket="ic-2"))

    hold = client.docs[f"legal_holds/{UID}"]
    assert hold["active"] is False and hold["released_by"] == "aryan" and hold["release_reason"]
    legal_holds.assert_account_deletion_permitted(UID, firestore_client=client)
    events = sorted(row["action"] for path, row in client.docs.items() if path.startswith(f"legal_holds/{UID}/events/"))
    assert events == ["place", "release"]
    assert result["held_deferred_deletes"]["count"] == 2
    assert record.summary["held_deferred_without_erasure"] == 1
    assert "1 conversation" in result["follow_up"]


def test_release_pages_past_the_first_page_and_warns_when_the_scan_is_capped(client, monkeypatch):
    monkeypatch.setattr(holds, "_TOMBSTONE_PAGE", 2)
    _run(holds.place, _ctx(apply=True), review_by=None)
    for index in range(5):
        client.docs[f"users/{UID}/deleted_conversations/c{index}"] = {"conversation_id": f"c{index}"}
    client.docs[f"users/{UID}/deleted_conversations/c9"] = {"legal_hold_deferred": True, "erasure_armed": False}

    result, _ = _run(holds.release, _ctx(apply=True, ticket="ic-3"))
    deferred = result["held_deferred_deletes"]
    assert deferred["tombstones_scanned"] == 6 and deferred["capped"] is False
    assert [row["conversation_id"] for row in deferred["conversations"]] == ["c9"]
    assert "do not erase by hand" in result["follow_up"]

    monkeypatch.setattr(holds, "_TOMBSTONE_SCAN_LIMIT", 4)
    status, _ = _run(holds.status, _ctx())
    assert status["held_deferred_deletes"]["capped"] is True
    assert status["held_deferred_deletes"]["count"] == 0


def test_status_shows_the_newest_events_in_time_order(client):
    for index in range(holds._EVENTS_SHOWN + 5):
        client.docs[f"legal_holds/{UID}/events/2026-11-{index:04d}"] = {"action": "place"}
    status, _ = _run(holds.status, _ctx())
    ids = [row["id"] for row in status["events"]]
    assert len(ids) == holds._EVENTS_SHOWN and ids == sorted(ids)
    assert ids[-1] == f"2026-11-{holds._EVENTS_SHOWN + 4:04d}" and ids[0] == "2026-11-0005"


def test_list_flags_overdue_reviews_and_holds_missing_audit(client):
    client.docs["legal_holds/a"] = {"schema_version": "legal_hold.v1", "issuer": "admin", "active": True}
    client.docs["legal_holds/b"] = {
        "schema_version": "legal_hold.v1",
        "issuer": "admin",
        "active": True,
        "ticket": "ic-9",
        "review_by": NOW - timedelta(days=1),
    }
    client.docs["legal_holds/c"] = {"schema_version": "legal_hold.v1", "issuer": "admin", "active": False}
    result, record = _run(holds.list_holds, _ctx(), all=False)
    assert [hold["uid"] for hold in result["holds"]] == ["a", "b"]
    assert record.summary == {"holds": 2, "review_overdue": 1, "missing_audit": 1, "capped": False}
    assert result["capped"] is False and result["scanned"] == 3


def test_list_reports_a_scan_that_hit_its_bound(client, monkeypatch):
    monkeypatch.setattr(holds, "_HOLD_SCAN_LIMIT", 2)
    for uid in ("a", "b", "c"):
        client.docs[f"legal_holds/{uid}"] = {"schema_version": "legal_hold.v1", "issuer": "admin", "active": True}
    result, record = _run(holds.list_holds, _ctx(), all=False)
    assert result["capped"] is True and record.summary["capped"] is True


def test_audit_write_failure_stops_the_command_before_it_runs(client):
    client.fail_writes_under = "support_actions/"
    with pytest.raises(support_actions.SupportActionError):
        _run(holds.place, _ctx(apply=True), review_by=None)
    assert f"legal_holds/{UID}" not in client.docs


def test_audit_summary_never_stores_long_or_structured_values(client):
    ctx = _ctx()
    with support_actions.record_action(ctx, "x", {}, now=lambda: NOW) as record:
        record.summary = {"count": 3, "blob": {"transcript": "secret"}, "text": "x" * 500}
    (audit,) = _actions(client).values()
    assert audit["summary"]["count"] == 3
    assert set(audit["summary"]["blob"]) == {"digest"} and set(audit["summary"]["text"]) == {"digest"}


@pytest.mark.parametrize("missing", ["ticket", "actor", "reason", "agent"])
def test_action_context_requires_every_field(missing):
    fields = {"ticket": "t", "actor": "a", "reason": "r", "agent": "g", missing: " "}
    with pytest.raises(support_actions.SupportActionError):
        support_actions.ActionContext(**fields)


def test_account_summary_returns_allowlisted_fields_only(client):
    result, record = _run(account.summary, _ctx())
    assert result["exists"] is True and result["profile"] == {"created_at": NOW, "language": "en"}
    assert "email" not in str(result["profile"])
    assert record.summary == {"exists": True, "legal_hold_active": False}


def test_apply_is_accepted_after_the_subcommand_as_the_runbook_documents():
    for argv in (
        ["--ticket", "t", "--actor", "a", "--reason", "r", "hold", "place", UID, "--apply"],
        ["--ticket", "t", "--actor", "a", "--reason", "r", "--apply", "hold", "release", UID],
        ["--ticket", "t", "--actor", "a", "--reason", "r", "dsar", "export", UID, "--approval", "n1", "--apply"],
    ):
        assert ops.build_parser().parse_args(ops._hoist_apply(argv)).apply is True
    plain = ["--ticket", "t", "--actor", "a", "--reason", "r", "hold", "status", UID]
    assert ops.build_parser().parse_args(ops._hoist_apply(plain)).apply is False


def test_a_failed_fence_check_still_audits_the_committed_hold_write(client, monkeypatch):
    def fence_fails(*args, **kwargs):
        raise holds.HoldCommandError("fence not verified")

    monkeypatch.setattr(holds, "_assert_fence", fence_fails)
    with pytest.raises(holds.HoldCommandError):
        _run(holds.place, _ctx(apply=True), review_by=None)
    (audit,) = _actions(client).values()
    assert audit["outcome"] == "failed" and audit["summary"]["hold_written"] is True
    assert client.docs[f"legal_holds/{UID}"]["active"] is True


def test_released_hold_is_never_review_overdue(client):
    client.docs["legal_holds/r"] = {
        "schema_version": "legal_hold.v1",
        "issuer": "admin",
        "active": False,
        "review_by": NOW - timedelta(days=3),
    }
    result, record = _run(holds.list_holds, _ctx(), all=True)
    assert [hold["review_overdue"] for hold in result["holds"]] == [False]


def test_operator_cli_wires_every_group_and_audits_the_run(client, capsys, monkeypatch):
    parser = ops.build_parser()
    groups = {action.dest: action for action in parser._actions}["group"].choices
    assert set(groups) == {"hold", "retention", "dsar", "account"}
    with pytest.raises(SystemExit):
        parser.parse_args(["hold", "list"])  # --ticket/--actor/--reason are required

    monkeypatch.setattr(ops, "_adc_principal", lambda: "support-operator@example.iam.gserviceaccount.com")
    code = ops.main(
        ["--ticket", "ic-1", "--actor", "aryan", "--reason", "triage", "--agent", "vm", "hold", "status", UID]
    )

    assert code == 0
    assert '"action_id"' in capsys.readouterr().out
    (audit,) = _actions(client).values()
    assert audit["command"] == "hold status" and audit["outcome"] == "succeeded"
    assert audit["principal"] == "support-operator@example.iam.gserviceaccount.com"


def test_hold_transaction_with_audit_and_event_reads_before_it_writes():
    # backend/AGENTS.md: transaction tests use StrictFirestore, which rejects any read after a write.
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    strict = StrictFirestore()
    audit = {
        "ticket": "ic-1",
        "reason": "preserve",
        "actor": "aryan",
        "agent": "vm",
        "review_by": NOW + timedelta(days=30),
    }
    legal_holds.place_legal_hold(UID, issuer="admin", active=True, firestore_client=strict, now=NOW, audit=audit)
    hold = strict.rows[("legal_holds", UID)]
    assert hold["active"] is True and hold["ticket"] == "ic-1" and hold["placed_by"] == "aryan"
    events = [key for key in strict.rows if key[:3] == ("legal_holds", UID, "events")]
    assert len(events) == 1
    legal_holds.place_legal_hold(UID, issuer="admin", active=False, firestore_client=strict, now=NOW, audit=audit)
    assert strict.rows[("legal_holds", UID)]["active"] is False
    assert len([key for key in strict.rows if key[:3] == ("legal_holds", UID, "events")]) == 2
    assert all(transaction.has_written for transaction in strict.transactions)
