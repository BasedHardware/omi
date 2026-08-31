"""A WHOLE-BATCH FCM send_each failure must never invalidate tokens. It used to synthesize a per-token
failure that reused the batch exception; if that exception carried a permanent-looking code, every token
in the batch was deleted — a transient outage could wipe every recipient (cubic PR 10887
notifications.py:173). Only individual BatchResponse errors may invalidate a token."""

from types import SimpleNamespace

from utils import notifications as n


def test_whole_batch_send_failure_does_not_invalidate_any_token(monkeypatch):
    class _PermBoom(Exception):
        code = "UNREGISTERED"  # a permanent per-token code — must NOT delete tokens at batch level

    def _boom(_batch):
        raise _PermBoom("fcm down")

    monkeypatch.setattr(n.messaging, "send_each", _boom)
    msgs = [SimpleNamespace() for _ in range(n._FCM_SEND_EACH_LIMIT + 100)]  # >500 -> batch path
    tokens = [f"t{i}" for i in range(len(msgs))]

    resp = n._send_messages(msgs)
    success, invalid = n._collect_send_results(resp, tokens)

    assert success == 0
    assert invalid == []  # NOT the whole batch


def test_individual_permanent_error_still_invalidates_its_token():
    # A real per-token permanent error (from a successful send_each BatchResponse) still invalidates only
    # that token — the batch-level guard must not suppress genuine per-token cleanup.
    responses = [
        SimpleNamespace(success=True, exception=None),
        SimpleNamespace(success=False, exception=SimpleNamespace(code="UNREGISTERED")),
    ]
    success, invalid = n._collect_send_results(SimpleNamespace(responses=responses), ["good", "dead"])
    assert success == 1
    assert invalid == ["dead"]
