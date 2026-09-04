"""WS auth rejection logging: severity must follow fault origin.

Production evidence (backend-listen, GCP 2026-08-30/31, Loop S sensor):
``ERROR:utils.other.endpoints:WebSocket auth failed: code=4001 error=Token
expired, …`` and ``… error=Certificate for key id 6ac9047f… not found.`` were
the #2 and #3 error signatures, ×9–47 and ×1–34 per 30-min window, for 16
consecutive hours. Root cause is client-side in both: the expired cohort
presents Firebase ID tokens hours past ``exp`` (samples show 3.7h/7.5h/18h
stale), and the certificate cohort presents tokens signed by a key id that is
absent from Google's *currently served* x509 set (verified directly against
https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com
on 2026-08-31 — the kid is retired, so a refresh cannot resurrect it). The
server's rejection — and the close code it sends — is the protocol working.

The defect was on the server side of the boundary: every expected, client-
caused rejection was logged at ERROR, making the stale-client reconnect
population indistinguishable from a serving outage in the error feed that
pages humans (the same feed in which a real outage — the Modulate STT 5xx
storm — had to be found).

Failure-Class: FC-request-input-rejection-escapes-as-server-fault — instance
fix in the class canonized by #11853 ("a route owns the classification of its
own request input"). Here the violated contract is the WS auth boundary's:
a client-caused token rejection (InvalidIdTokenError — Firebase evaluated the
client's token and refused it) must be a warning, while a server fault
(CertificateFetchError — we could not even fetch Google's certs to evaluate
the token; any unexpected error) stays an error. Close codes and reasons are
unchanged — clients already receive the correct remediation hint; only the
severity classification is fixed.

These tests drive the REAL ``_verify_ws_auth`` boundary and the REAL FastAPI
dependencies (``get_current_user_uid_ws_listen`` / ``get_current_user_uid_ws``)
through the sanctioned ``stub_modules`` isolation pattern used by
``test_ws_auth_handshake.py``, asserting on captured log records and the wire
close codes the client receives.
"""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from testing.import_isolation import stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]

# The production error samples these tests replay, verbatim shapes.
EXPIRED_MESSAGE = "Token expired, 1788101015 < 1788114388"
RETIRED_KEY_MESSAGE = "Certificate for key id 6ac9047f6712fcd5cf67a3307941d9fa42283955 not found."


# Firebase auth exception classes. The hierarchy mirrors the real firebase_admin
# (_auth_utils): ExpiredIdTokenError and RevokedIdTokenError are SUBCLASSES of
# InvalidIdTokenError, and CertificateFetchError is a sibling. Defined at module
# scope so @patch decorators evaluated at class-definition time can reference
# them. The module-scoped autouse fixture installs these same objects onto the
# firebase_admin.auth stub, preserving isinstance identity (both the except
# clause and _get_ws_auth_close's isinstance chain) inside utils.other.endpoints.
class InvalidIdTokenError(Exception):
    pass


class ExpiredIdTokenError(InvalidIdTokenError):
    pass


class RevokedIdTokenError(InvalidIdTokenError):
    pass


class CertificateFetchError(Exception):
    pass


# Populated by the _ws_auth_rejection_logging_isolation module fixture; tests
# resolve them at call time (after the fixture has run).
_verify_ws_auth = None
get_current_user_uid_ws_listen = None
get_current_user_uid_ws = None
ENDPOINTS_LOGGER = "utils.other.endpoints"


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
    for err_cls in (CertificateFetchError, ExpiredIdTokenError, InvalidIdTokenError, RevokedIdTokenError):
        setattr(firebase_auth_stub, err_cls.__name__, err_cls)
    firebase_auth_stub.verify_id_token = MagicMock(side_effect=InvalidIdTokenError("Invalid token"))
    firebase_auth_stub.get_user = MagicMock()

    database_client_stub = types.ModuleType("database._client")
    database_client_stub.db = MagicMock()
    database_client_stub.document_id_from_seed = MagicMock(return_value="doc-id")

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
        # Pop polluted/prior copies so endpoints re-execs against these fakes;
        # stub_modules restores/purges them on teardown (same rationale as
        # test_ws_auth_handshake.py).
        "utils.executors": None,
        "utils.other.endpoints": None,
    }
    return fakes


@pytest.fixture(scope="module", autouse=True)
def _ws_auth_rejection_logging_isolation():
    """Install the stubs and exec utils.other.endpoints against them."""
    with stub_modules(_build_fakes()):
        endpoints = importlib.import_module("utils.other.endpoints")
        mod = sys.modules[__name__]
        mod._verify_ws_auth = endpoints._verify_ws_auth
        mod.get_current_user_uid_ws_listen = endpoints.get_current_user_uid_ws_listen
        mod.get_current_user_uid_ws = endpoints.get_current_user_uid_ws
        yield


class _SeverityAssertions(unittest.TestCase):
    """Shared assertions on captured log records."""

    def _assert_client_rejection_warns(self, captured, expected_code):
        errors = [r for r in captured.records if r.levelname == "ERROR"]
        self.assertEqual(
            len(errors),
            0,
            f"client-caused rejection must not log at ERROR, got: {[r.getMessage() for r in errors]}",
        )
        self.assertEqual(len(captured.records), 1, f"expected exactly one log record, got {len(captured.records)}")
        record = captured.records[0]
        self.assertEqual(record.levelname, "WARNING")
        self.assertIn(f"code={expected_code}", record.getMessage())

    def _assert_server_fault_errors(self, captured, expected_code):
        self.assertTrue(
            any(r.levelname == "ERROR" for r in captured.records),
            f"server fault must log at ERROR, got: {[(r.levelname, r.getMessage()) for r in captured.records]}",
        )
        self.assertIn(f"code={expected_code}", captured.records[0].getMessage())


class TestRejectionSeverityAtTheBoundary(_SeverityAssertions):
    """Direct calls to the real _verify_ws_auth: severity follows fault origin."""

    def test_expired_token_rejection_logs_warning_not_error(self):
        """The ×47/30m 'Token expired' signature is a client fault -> WARNING."""
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=InvalidIdTokenError(EXPIRED_MESSAGE)
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(Exception):
                    _verify_ws_auth("Bearer expired-token")
        self._assert_client_rejection_warns(captured, expected_code=4001)
        self.assertIn(EXPIRED_MESSAGE, captured.records[0].getMessage())

    def test_retired_signing_key_rejection_logs_warning_not_error(self):
        """The ×34/30m 'Certificate for key id … not found' signature is a client
        presenting a token signed by a key Google retired -> WARNING."""
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=InvalidIdTokenError(RETIRED_KEY_MESSAGE)
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(Exception):
                    _verify_ws_auth("Bearer retired-key-token")
        self._assert_client_rejection_warns(captured, expected_code=4001)
        self.assertIn("6ac9047f6712fcd5cf67a3307941d9fa42283955", captured.records[0].getMessage())

    def test_typed_expired_token_error_logs_warning(self):
        """ExpiredIdTokenError (typed, not message-derived) is client-caused -> WARNING."""
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=ExpiredIdTokenError(EXPIRED_MESSAGE)
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(Exception):
                    _verify_ws_auth("Bearer typed-expired-token")
        self._assert_client_rejection_warns(captured, expected_code=4001)

    def test_revoked_token_rejection_logs_warning(self):
        """Revoked token: the client must re-login (4004) — still a client fault."""
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=RevokedIdTokenError("Token revoked")
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(Exception):
                    _verify_ws_auth("Bearer revoked-token")
        self._assert_client_rejection_warns(captured, expected_code=4004)

    def test_generic_invalid_token_rejection_logs_warning(self):
        """Any other InvalidIdTokenError (audience, malformed…) is client-caused."""
        with patch.object(
            sys.modules["utils.other.endpoints"],
            "verify_token",
            side_effect=InvalidIdTokenError("Firebase ID token has incorrect \"aud\" claim"),
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(Exception):
                    _verify_ws_auth("Bearer wrong-audience-token")
        self._assert_client_rejection_warns(captured, expected_code=1008)

    def test_certificate_fetch_failure_stays_error(self):
        """CertificateFetchError = the SERVER could not fetch Google's certs to
        evaluate the token — a genuine server fault, must stay at ERROR."""
        with patch.object(
            sys.modules["utils.other.endpoints"],
            "verify_token",
            side_effect=CertificateFetchError("Could not fetch certificates", RuntimeError("network unavailable")),
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(Exception):
                    _verify_ws_auth("Bearer any-token")
        self._assert_server_fault_errors(captured, expected_code=4001)

    def test_message_derived_certificate_rejection_is_warning_not_error(self):
        """An InvalidIdTokenError whose *message* mentions a certificate (retired
        key id — client-caused) must be classified differently from a typed
        CertificateFetchError (server-caused), even though both close with 4001."""
        with patch.object(
            sys.modules["utils.other.endpoints"],
            "verify_token",
            side_effect=InvalidIdTokenError("Could not verify token: certificate problems"),
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(Exception):
                    _verify_ws_auth("Bearer message-cert-token")
        errors = [r for r in captured.records if r.levelname == "ERROR"]
        self.assertEqual(errors, [], "message-derived certificate rejection is client-caused, not a server fault")


class TestSeverityThroughListenDep(_SeverityAssertions):
    """The /v4/listen dependency path: severity fixed, wire contract unchanged."""

    def setUp(self):
        self.app = FastAPI()

        @self.app.websocket("/ws-listen")
        async def ws_listen(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws_listen)):
            await websocket.accept()
            await websocket.send_json({"uid": uid})
            await websocket.close()

        self.client = TestClient(self.app)

    def test_expired_token_close_4001_and_warning(self):
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=InvalidIdTokenError(EXPIRED_MESSAGE)
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer expired_token"}):
                        self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001, "client-visible close code must stay 4001 (refresh token)")
        self._assert_client_rejection_warns(captured, expected_code=4001)

    def test_retired_key_close_4001_and_warning(self):
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=InvalidIdTokenError(RETIRED_KEY_MESSAGE)
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with self.client.websocket_connect(
                        "/ws-listen", headers={"Authorization": "Bearer stale_key_token"}
                    ):
                        self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001, "client-visible close code must stay 4001 (refresh token)")
        self._assert_client_rejection_warns(captured, expected_code=4001)

    def test_revoked_token_close_4004_and_warning(self):
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=RevokedIdTokenError("Token revoked")
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer revoked_token"}):
                        self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4004, "client-visible close code must stay 4004 (re-login)")
        self._assert_client_rejection_warns(captured, expected_code=4004)

    def test_certificate_fetch_failure_close_4001_and_error(self):
        with patch.object(
            sys.modules["utils.other.endpoints"],
            "verify_token",
            side_effect=CertificateFetchError("Could not fetch certificates", RuntimeError("network unavailable")),
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with self.client.websocket_connect(
                        "/ws-listen", headers={"Authorization": "Bearer cert_fetch_token"}
                    ):
                        self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001, "client-visible close code must stay 4001")
        self._assert_server_fault_errors(captured, expected_code=4001)

    def test_unexpected_verify_error_stays_error_close_1008(self):
        """The generic handler (unexpected exception) is a server fault: untouched
        by the reclassification — still ERROR, still close 1008."""
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=RuntimeError("unexpected error")
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with self.client.websocket_connect("/ws-listen", headers={"Authorization": "Bearer token"}):
                        self.fail("Expected connection to fail")
        self.assertEqual(ctx.exception.code, 1008)
        errors = [r for r in captured.records if r.levelname == "ERROR"]
        self.assertTrue(errors, "unexpected errors must keep logging at ERROR")


class TestSeverityThroughRateLimitedDep(_SeverityAssertions):
    """The rate-limited WS dependency funnels through the same boundary."""

    def setUp(self):
        self.app = FastAPI()

        @self.app.websocket("/ws-ratelimited")
        async def ws_ratelimited(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws)):
            await websocket.accept()
            await websocket.send_json({"uid": uid})
            await websocket.close()

        self.client = TestClient(self.app)

    def test_expired_token_close_4001_and_warning(self):
        with patch.object(
            sys.modules["utils.other.endpoints"], "verify_token", side_effect=InvalidIdTokenError(EXPIRED_MESSAGE)
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with self.client.websocket_connect(
                        "/ws-ratelimited", headers={"Authorization": "Bearer expired_token"}
                    ):
                        self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001)
        self._assert_client_rejection_warns(captured, expected_code=4001)

    def test_certificate_fetch_failure_stays_error(self):
        with patch.object(
            sys.modules["utils.other.endpoints"],
            "verify_token",
            side_effect=CertificateFetchError("Could not fetch certificates", RuntimeError("network unavailable")),
        ):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                with self.assertRaises(WebSocketDisconnect) as ctx:
                    with self.client.websocket_connect(
                        "/ws-ratelimited", headers={"Authorization": "Bearer cert_fetch_token"}
                    ):
                        self.fail("Expected WebSocket to be closed by server")
        self.assertEqual(ctx.exception.code, 4001)
        self._assert_server_fault_errors(captured, expected_code=4001)


class TestErrorFeedPollutionContract(_SeverityAssertions):
    """The incident restated as a contract: a burst of client-caused rejections
    must leave the ERROR feed empty, while server faults land in it."""

    def test_client_rejection_burst_leaves_error_feed_empty(self):
        rejections = [
            InvalidIdTokenError(EXPIRED_MESSAGE),
            InvalidIdTokenError(RETIRED_KEY_MESSAGE),
            RevokedIdTokenError("Token revoked"),
        ]
        with patch.object(sys.modules["utils.other.endpoints"], "verify_token", side_effect=rejections):
            with self.assertLogs(ENDPOINTS_LOGGER, level="WARNING") as captured:
                for _ in rejections:
                    with self.assertRaises(Exception):
                        _verify_ws_auth("Bearer stale-token")
        self.assertEqual(
            len(captured.records),
            len(rejections),
            f"each rejection logs exactly once, got {len(captured.records)}",
        )
        errors = [r for r in captured.records if r.levelname == "ERROR"]
        self.assertEqual(
            errors,
            [],
            f"the stale-client population must not pollute the ERROR feed: {[r.getMessage() for r in errors]}",
        )

    def test_missing_auth_header_short_circuits_before_rejection_logging(self):
        """No Authorization header -> close 1008 without any rejection log: the
        classifier owns token-evaluation rejections only, not missing-input ones."""
        with self.assertNoLogs(ENDPOINTS_LOGGER, level="WARNING"):
            with self.assertRaises(Exception):
                _verify_ws_auth(None)


if __name__ == "__main__":
    unittest.main()
