from __future__ import annotations

from routers import conversations


def test_detail_dispatch_runs_claimed_work_and_completes(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        conversations.conversations_db, "claim_authorized_first_open_work", lambda _uid, _cid, _source: "lease"
    )
    monkeypatch.setattr(
        conversations.conversations_db,
        "get_conversation",
        lambda _uid, _cid: {"id": "conversation", "jit_first_open": {"state": "in_flight"}},
    )
    monkeypatch.setattr(
        conversations.conversations_db,
        "finish_first_open_work",
        lambda _uid, _cid, token, *, succeeded: calls.append((token, succeeded)),
    )
    monkeypatch.setattr(
        conversations,
        "run_first_open_derived_work",
        lambda uid, row, token: calls.append((uid, row["id"], token)),
    )
    monkeypatch.setattr(
        conversations,
        "submit_with_context",
        lambda _executor, operation, *args: operation(*args),
    )

    conversations._dispatch_first_open_work(
        "owner", {"id": "conversation", "source": "desktop", "jit_first_open": {"state": "pending"}}
    )

    assert calls == [("owner", "conversation", "lease"), ("lease", True)]


def test_detail_dispatch_does_not_run_without_claim(monkeypatch) -> None:
    monkeypatch.setattr(
        conversations.conversations_db, "claim_authorized_first_open_work", lambda _uid, _cid, _source: None
    )
    monkeypatch.setattr(
        conversations,
        "submit_with_context",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )

    conversations._dispatch_first_open_work("owner", {"id": "conversation", "jit_first_open": {"state": "in_flight"}})


def test_kill_or_unknown_suspends_outstanding_obligation_without_claim(monkeypatch) -> None:
    observed: list[dict[str, object]] = []

    monkeypatch.setattr(
        conversations.conversations_db,
        "claim_authorized_first_open_work",
        lambda uid, cid, source: observed.append({"uid": uid, "conversation_id": cid, "source": source}) or None,
    )
    monkeypatch.setattr(
        conversations,
        "submit_with_context",
        lambda *_args: (_ for _ in ()).throw(AssertionError("disabled outstanding work must not dispatch")),
    )

    conversations._dispatch_first_open_work(
        "owner", {"id": "conversation", "source": "desktop", "jit_first_open": {"state": "pending"}}
    )

    assert observed == [{"uid": "owner", "conversation_id": "conversation", "source": "desktop"}]
