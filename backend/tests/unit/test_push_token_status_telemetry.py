"""Push Token Status analytics events fire on token registration and invalidation.

Churn/re-engagement analysis (EXP-002) needs to know whether a uid had a deliverable
push token as of a date. PostHog now receives `Push Token Status` (`status=registered`)
on every FCM token save and `Push Token Status` (`status=invalidated`) when a per-user
send removes permanently-dead tokens (`UNREGISTERED` and friends). These tests pin both
emit sites and their payloads. The bulk send path carries no uid, so it intentionally
does not emit — asserted so nobody "fixes" that by attributing tokens to the wrong user.

utils.notifications pulls in firebase/database at import, so we import the REAL module
under a stub finder (so we exercise the real code, not a copy), then patch emit_posthog_event.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Keep these REAL (module under test + its package); stub the heavy leaves.
_REAL = {"utils", "utils.notifications"}
_PREF = ("firebase_admin", "database", "google", "utils.executors", "utils.llm")


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        m = MagicMock()
        setattr(self, n, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if name in _REAL:
            return None
        if any(name == p or name.startswith(p + ".") for p in _PREF):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, m):
        pass


def _install_stub_module(name):
    module = _AutoMock(name)
    sys.modules[name] = module
    parent_name, _, attr = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, attr, module)
    return module


def _load_real_notifications():
    sys.path.insert(0, str(BACKEND_DIR))
    finder = _Finder()
    sys.meta_path.insert(0, finder)
    try:
        firebase_admin = _install_stub_module("firebase_admin")
        firebase_admin.messaging = _install_stub_module("firebase_admin.messaging")
        firebase_admin.auth = _install_stub_module("firebase_admin.auth")

        import utils.notifications as notif

        return notif
    finally:
        sys.meta_path.remove(finder)
        for name in list(sys.modules.keys()):
            if name in _REAL:
                continue
            if any(name == p or name.startswith(p + ".") for p in _PREF):
                sys.modules.pop(name, None)


notif = _load_real_notifications()


def _fcm_result(success=True, code=None):
    result = MagicMock()
    result.success = success
    if not success:
        result.exception.code = code
    else:
        result.exception = None
    return result


def test_registered_emitted_on_token_save():
    """The router emits status=registered with a lowercased platform after saving.

    Structural (AST) like test_bulk_notification_async: importing routers.notifications
    would pull the whole FastAPI/auth stack into a unit test, so the emit wiring is
    pinned by source inspection instead of execution.
    """
    import ast

    source = (BACKEND_DIR / "routers" / "notifications.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    save_token = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "save_token"
    )
    calls = [
        node
        for node in ast.walk(save_token)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "emit_posthog_event"
    ]
    assert len(calls) == 1, "save_token must emit exactly one Push Token Status event"
    call = calls[0]
    assert getattr(call.args[1], "value", None) == "Push Token Status"
    props = call.args[2]
    assert isinstance(props, ast.Dict), "properties must be a dict literal"
    prop_map = {k.value: v for k, v in zip(props.keys, props.values)}
    assert getattr(prop_map["status"], "value", None) == "registered"
    assert "lower()" in ast.unparse(prop_map["platform"]), "platform must be normalized to lowercase"
    # Firestore remains the eligibility source of truth; this is analytics-only.
    assert "Analytics-only" in source


def test_invalidated_emitted_when_permanent_failure_tokens_removed():
    """A per-user send that removes dead tokens emits status=invalidated with a count."""
    response = MagicMock()
    response.responses = [_fcm_result(True), _fcm_result(False, "UNREGISTERED")]
    send_payload = (1, ["dead-token"])

    with patch.object(notif, "_send_messages", return_value=MagicMock()) as send, patch.object(
        notif, "notification_db"
    ) as ndb, patch.object(notif, "emit_posthog_event") as emit:
        ndb.get_all_tokens.return_value = ["live-token", "dead-token"]
        send.return_value = response
        with patch.object(notif, "_collect_send_results", return_value=send_payload):
            count = notif._send_to_user("user-1", "tag", notification=None, data=None)

        assert count == 1
        ndb.remove_bulk_tokens.assert_called_once_with(["dead-token"])
        emit.assert_called_once_with("user-1", "Push Token Status", {"status": "invalidated", "invalidated_count": 1})


def test_no_invalidation_event_without_invalid_tokens():
    """A fully successful send emits nothing (no churn-analysis noise)."""
    response = MagicMock()
    response.responses = [_fcm_result(True)]

    with patch.object(notif, "_send_messages", return_value=MagicMock()) as send, patch.object(
        notif, "notification_db"
    ) as ndb, patch.object(notif, "emit_posthog_event") as emit:
        ndb.get_all_tokens.return_value = ["live-token"]
        send.return_value = response
        with patch.object(notif, "_collect_send_results", return_value=(1, [])):
            count = notif._send_to_user("user-1", "tag", notification=None, data=None)

        assert count == 1
        emit.assert_not_called()


def test_emit_failure_never_breaks_send():
    """emit_posthog_event raising must not fail the notification send."""
    response = MagicMock()
    response.responses = [_fcm_result(True), _fcm_result(False, "UNREGISTERED")]

    with patch.object(notif, "_send_messages", return_value=MagicMock()) as send, patch.object(
        notif, "notification_db"
    ) as ndb, patch.object(notif, "emit_posthog_event", side_effect=RuntimeError("posthog down")):
        ndb.get_all_tokens.return_value = ["live-token", "dead-token"]
        send.return_value = response
        with patch.object(notif, "_collect_send_results", return_value=(1, ["dead-token"])):
            count = notif._send_to_user("user-1", "tag", notification=None, data=None)

        assert count == 1
