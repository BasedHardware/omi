"""A listen admission-fence fault closes the socket instead of crashing the ASGI callable.

Failure-Class: FC-lifecycle-close-classified-by-transport-phase

``run_listen_session`` owns the socket through its admission boundary (1011
terminal close, tick-preserving containment), but the ``/v4/listen`` FastAPI
dependency runs entirely in front of that boundary and had un-owned fault
arms of its own. The same bounded fault surfaces at different dependency
stages today with different outcomes: the deletion watcher that runs one
minute later, mid-session, classifies its fence fault as the retryable 1013
close, while the deletion fence at admission leaked
``ExecutorSaturatedError`` from the plain ``run_blocking`` hop, the
account-cutover fence leaked every datastore fault its read hit except the
malformed-document shape, and the BYOK enrollment read leaked every fault —
each one an unclassified ``Exception in ASGI application`` traceback from
uvicorn's ``run_asgi`` (prod backend-listen 2026-10-22: x8/30m at
``uvicorn/protocols/websockets/websockets_impl.py``) and an abrupt client
drop with no close frame to act on. The dependency stage a bounded failure
surfaces in must not decide its classification: every admission fence now
answers the same retryable close the in-session fence already speaks —
1013 with a retry-later reason — so the client's ordinary reconnect retries
instead of treating the pod as broken. Token verification and the BYOK
critical-pool hop already route through ``run_critical_ws`` and keep that
contract; the deletion, cutover and BYOK state-read fences join it.
Permanent refusals keep their loud classification: only the bounded
transient set (503 ``ServiceUnavailable``, 504 ``DeadlineExceeded``, 500
``InternalServerError``, and the SDK's ``RetryError`` when its drained
budget's cause is in that set) converts; ``PermissionDenied`` and other
permanent refusals still propagate, because a misconfigured fence is a
deploy fault, not a client retry.

Guards:
- an ``ExecutorSaturatedError`` from the deletion-fence hop closes 1013;
- an ``ExecutorSaturatedError`` from the cutover-fence hop closes 1013;
- a transient cutover state-read fault (``ServiceUnavailable``) closes 1013;
- a permanent cutover state-read fault (``PermissionDenied``) still
  propagates — the loud branch is the contract, not a bug;
- a transient BYOK state-read fault closes 1013;
- ``ExecutorSaturatedError`` from the BYOK critical-pool hop keeps its
  existing ``run_critical_ws`` 1013 close;
- a genuine deletion denial keeps its 4005 close (the fence deny path is
  unchanged);
- the healthy admission path still returns the uid.

Isolation: ``utils.other.endpoints`` transitively imports ``firebase_admin.auth``
and several ``database.*`` modules that construct clients / require a Firebase app
at import time. The module-scoped autouse fixture below installs ``firebase_admin``
and ``database`` stubs via the sanctioned ``stub_modules`` reserve helper, exec's
``utils.other.endpoints`` against them, and tears everything down on exit so
nothing leaks to later test files. Same pattern as ``test_ws_auth_handshake.py``
and ``test_ws_auth_rejection_logging.py`` (see ``backend/docs/test_isolation.md``
and DECISIONS D2).
"""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket, WebSocketException
from fastapi.testclient import TestClient
from google.api_core.exceptions import (
    DeadlineExceeded,
    InternalServerError,
    PermissionDenied,
    RetryError,
    ServiceUnavailable,
)
from starlette.websockets import WebSocketDisconnect

from database._client import is_transient_availability_error
from testing.import_isolation import stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


# Populated by the ``_admission_isolation`` module fixture. Tests resolve these
# module globals at call time (after the fixture has run).
get_current_user_uid_ws_listen = None
endpoints = None
database_users_stub = None


def _build_fakes():
    """Build the namespace-package + firebase/database stub mapping for ``stub_modules``."""
    database_pkg = types.ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]
    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [str(BACKEND_DIR / "utils")]
    utils_other_pkg = types.ModuleType("utils.other")
    utils_other_pkg.__path__ = [str(BACKEND_DIR / "utils" / "other")]

    firebase_admin_stub = types.ModuleType("firebase_admin")
    firebase_auth_stub = types.ModuleType("firebase_admin.auth")
    firebase_admin_stub.auth = firebase_auth_stub

    class InvalidIdTokenError(Exception):
        pass

    class CertificateFetchError(Exception):
        pass

    class ExpiredIdTokenError(Exception):
        pass

    class RevokedIdTokenError(Exception):
        pass

    for err_cls in (InvalidIdTokenError, CertificateFetchError, ExpiredIdTokenError, RevokedIdTokenError):
        setattr(firebase_auth_stub, err_cls.__name__, err_cls)
    firebase_auth_stub.verify_id_token = MagicMock(return_value={"uid": "uid-fence"})
    firebase_auth_stub.get_user = MagicMock()

    database_client_stub = types.ModuleType("database._client")
    database_client_stub.db = MagicMock()
    database_client_stub.document_id_from_seed = MagicMock(return_value="doc-id")
    # The real classifier: the admission fences answer faults through it, so
    # the stub carries the production predicate, not a permissive stand-in.
    database_client_stub.is_transient_availability_error = is_transient_availability_error

    database_redis_stub = types.ModuleType("database.redis_db")
    database_redis_stub.check_rate_limit = MagicMock(return_value=True)
    database_redis_stub.try_acquire_listen_lock = MagicMock(return_value=True)
    database_redis_stub.try_acquire_user_platform_write_lock = MagicMock(return_value=True)

    users_stub = types.ModuleType("database.users")
    users_stub.record_user_platform = MagicMock()
    users_stub.record_client_device = MagicMock()
    users_stub.get_user_deletion_wipe_status = MagicMock(return_value=None)

    fakes = {
        "database": database_pkg,
        "utils": utils_pkg,
        "utils.other": utils_other_pkg,
        "firebase_admin": firebase_admin_stub,
        "firebase_admin.auth": firebase_auth_stub,
        "database._client": database_client_stub,
        "database.redis_db": database_redis_stub,
        "database.users": users_stub,
        # Real executors + a fresh endpoints exec, per test_ws_auth_handshake.py.
        "utils.executors": None,
        "utils.other.endpoints": None,
    }
    return fakes, users_stub


@pytest.fixture(scope="module", autouse=True)
def _admission_isolation():
    """Install firebase/database stubs and exec ``utils.other.endpoints`` against them."""
    # Warm the observability chain before stubbing: endpoints' transitive
    # imports reach utils.metrics, whose Prometheus counters register into the
    # process-global registry. Importing it here (a) registers each counter
    # exactly once and (b) keeps the module in sys.modules across this
    # fixture's restore, so a sibling isolation fixture exec'ing
    # utils.other.endpoints later in the same process re-binds the same
    # module instead of re-registering duplicated timeseries.
    importlib.import_module("utils.metrics")
    importlib.import_module("utils.observability.fallback")
    importlib.import_module("utils.account_cutover.telemetry")
    fakes, users_stub = _build_fakes()
    with stub_modules(fakes):
        mod = importlib.import_module("utils.other.endpoints")
        mod.record_user_platform = users_stub.record_user_platform
        module_globals = sys.modules[__name__]
        module_globals.get_current_user_uid_ws_listen = mod.get_current_user_uid_ws_listen
        module_globals.endpoints = mod
        module_globals.database_users_stub = users_stub
        yield


class AdmissionFenceTestCase(unittest.TestCase):
    def setUp(self):
        database_users_stub.record_user_platform.reset_mock()
        database_users_stub.get_user_deletion_wipe_status.reset_mock()
        database_users_stub.get_user_deletion_wipe_status = MagicMock(return_value=None)

    def _client(self):
        app = FastAPI()

        @app.websocket("/ws-listen")
        async def ws_listen(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws_listen)):
            await websocket.accept()
            await websocket.send_json({"uid": uid})
            await websocket.close()

        return TestClient(app)


from fastapi import Depends  # noqa: E402  (used by _client; kept after globals for readability)


class TestDeletionFenceContainment(AdmissionFenceTestCase):
    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_deletion_fence_executor_saturation_closes_1013(self, _verify):
        """db-pool saturation under the deletion fence is a retryable close, not a crash."""
        with patch.object(
            endpoints,
            "enforce_account_deletion_ws_access",
            side_effect=endpoints.ExecutorSaturatedError("db executor is saturated"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected overload close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_deletion_fence_denial_still_closes_4005(self, _verify):
        """A genuine deletion denial keeps its 4005 close — the deny path is unchanged."""
        database_users_stub.get_user_deletion_wipe_status = MagicMock(return_value="requested")
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                self.fail("Expected deletion-denial close frame")
        self.assertEqual(ctx.exception.code, 4005)


class TestCutoverFenceContainment(AdmissionFenceTestCase):
    def setUp(self):
        super().setUp()
        enforcement = patch.object(endpoints, "cutover_enforcement_enabled", return_value=True)
        enforcement.start()
        self.addCleanup(enforcement.stop)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_cutover_fence_executor_saturation_closes_1013(self, _verify):
        """db-pool saturation under the cutover fence is a retryable close, not a crash."""
        with patch.object(
            endpoints,
            "enforce_account_cutover_ws_access",
            side_effect=endpoints.ExecutorSaturatedError("db executor is saturated"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected overload close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_cutover_fence_transient_read_closes_1013(self, _verify):
        """A momentary datastore fault under the cutover read is a retryable close."""
        with patch.object(
            endpoints,
            "enforce_account_cutover_ws_access",
            side_effect=ServiceUnavailable("SYNTHETIC-CUTOVER-READ-UNAVAILABLE"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_cutover_fence_drained_retry_budget_closes_1013(self, _verify):
        """The SDK's drained-retry envelope over a transient cause is the same bounded fault."""
        with patch.object(
            endpoints,
            "enforce_account_cutover_ws_access",
            side_effect=RetryError("SYNTHETIC-DRAINED-ENVELOPE", ServiceUnavailable("SYNTHETIC-DRAINED-TRANSIENT")),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_cutover_fence_permanent_fault_stays_loud(self, _verify):
        """A permanent refusal is a deploy fault: it keeps propagating, not a retry frame."""
        with patch.object(
            endpoints,
            "enforce_account_cutover_ws_access",
            side_effect=PermissionDenied("SYNTHETIC-CUTOVER-PERMANENT"),
        ):
            with self.assertRaises(Exception) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected the permanent refusal to propagate")
        self.assertNotIsInstance(ctx.exception, WebSocketDisconnect)
        self.assertNotIsInstance(ctx.exception, WebSocketException)


class TestByokFenceContainment(AdmissionFenceTestCase):
    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_byok_state_transient_read_closes_1013(self, _verify):
        """A momentary datastore fault under the BYOK enrollment read is a retryable close."""
        with patch.object(
            endpoints,
            "validate_byok_websocket_keys",
            side_effect=ServiceUnavailable("SYNTHETIC-BYOK-READ-UNAVAILABLE"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_byok_drained_retry_budget_closes_1013(self, _verify):
        """The SDK's drained-retry envelope over a transient BYOK cause is the same fault."""
        with patch.object(
            endpoints,
            "validate_byok_websocket_keys",
            side_effect=RetryError("SYNTHETIC-BYOK-ENVELOPE", ServiceUnavailable("SYNTHETIC-BYOK-CAUSE")),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_byok_permanent_fault_stays_loud(self, _verify):
        """A permanent refusal under the BYOK read is a deploy fault: it propagates."""
        with patch.object(
            endpoints,
            "validate_byok_websocket_keys",
            side_effect=PermissionDenied("SYNTHETIC-BYOK-PERMANENT"),
        ):
            with self.assertRaises(Exception) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected the permanent refusal to propagate")
        self.assertNotIsInstance(ctx.exception, WebSocketDisconnect)
        self.assertNotIsInstance(ctx.exception, WebSocketException)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_byok_mismatch_keeps_4003(self, _verify):
        """The fence's own fingerprint-mismatch verdict keeps its 4003 close."""
        with patch.object(
            endpoints, "validate_byok_websocket_keys", return_value=({}, "BYOK key fingerprint mismatch")
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected the BYOK mismatch close frame")
        self.assertEqual(ctx.exception.code, 4003)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_byok_critical_pool_saturation_keeps_1013(self, _verify):
        """The critical-pool hop keeps its existing run_critical_ws 1013 close."""
        with patch.object(
            endpoints,
            "validate_byok_websocket_keys",
            side_effect=endpoints.ExecutorSaturatedError("critical executor is saturated"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected overload close frame")
        self.assertEqual(ctx.exception.code, 1013)


class TestDeletionFenceTransientMembers(AdmissionFenceTestCase):
    """Each availability class the classifier admits, on the deletion fence."""

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_deadline_exceeded_closes_1013(self, _verify):
        with patch.object(
            endpoints,
            "enforce_account_deletion_ws_access",
            side_effect=DeadlineExceeded("SYNTHETIC-DELETION-READ-504"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_drained_retry_envelope_closes_1013(self, _verify):
        with patch.object(
            endpoints,
            "enforce_account_deletion_ws_access",
            side_effect=RetryError("SYNTHETIC-DELETION-ENVELOPE", ServiceUnavailable("SYNTHETIC-DELETION-CAUSE")),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_permanent_fault_stays_loud(self, _verify):
        """A misconfigured deletion fence is a deploy fault: it propagates uncaught."""
        with patch.object(
            endpoints,
            "enforce_account_deletion_ws_access",
            side_effect=PermissionDenied("SYNTHETIC-DELETION-PERMANENT"),
        ):
            with self.assertRaises(Exception) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected the permanent refusal to propagate")
        self.assertNotIsInstance(ctx.exception, WebSocketDisconnect)
        self.assertNotIsInstance(ctx.exception, WebSocketException)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_causeless_retry_envelope_stays_loud(self, _verify):
        """A cause-less drained envelope carries no transient evidence; it propagates."""
        with patch.object(
            endpoints,
            "enforce_account_deletion_ws_access",
            side_effect=RetryError("SYNTHETIC-CAUSELESS-ENVELOPE", None),
        ):
            with self.assertRaises(Exception) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected the evidence-free envelope to propagate")
        self.assertNotIsInstance(ctx.exception, WebSocketDisconnect)


class TestCutoverFenceTransientMembers(AdmissionFenceTestCase):
    """The remaining availability members on the cutover fence."""

    def setUp(self):
        super().setUp()
        enforcement = patch.object(endpoints, "cutover_enforcement_enabled", return_value=True)
        enforcement.start()
        self.addCleanup(enforcement.stop)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_deadline_exceeded_closes_1013(self, _verify):
        with patch.object(
            endpoints,
            "enforce_account_cutover_ws_access",
            side_effect=DeadlineExceeded("SYNTHETIC-CUTOVER-READ-504"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_denial_close_4006_passes_through(self, _verify):
        """The fence's own generation-mismatch denial keeps its 4006 close."""
        from fastapi import WebSocketException as _WSE

        with patch.object(
            endpoints,
            "enforce_account_cutover_ws_access",
            side_effect=_WSE(code=4006, reason="generation mismatch"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected the cutover denial close frame")
        self.assertEqual(ctx.exception.code, 4006)


class TestHealthyAdmission(AdmissionFenceTestCase):
    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_healthy_admission_still_returns_uid(self, _verify):
        """The over-catch guard: every fence passing still admits the connection."""
        with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}) as ws:
            payload = ws.receive_json()
        self.assertEqual(payload, {"uid": "uid-fence"})

    @patch("utils.other.endpoints.verify_token", return_value="uid-fence")
    def test_internal_server_error_is_transient_too(self, _verify):
        """500 InternalServerError is in the bounded set, like the rest of database/."""
        with patch.object(
            endpoints,
            "enforce_account_deletion_ws_access",
            side_effect=InternalServerError("SYNTHETIC-DELETION-READ-500"),
        ):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self._client().websocket_connect("/ws-listen", headers={"Authorization": "Bearer valid"}):
                    self.fail("Expected retryable close frame")
        self.assertEqual(ctx.exception.code, 1013)
