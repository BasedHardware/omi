"""Content-free developer credential verification tests; no network or stored credentials."""

import unittest
from unittest.mock import Mock

from omi_cli.key_info import verify_key
from omi_cli.errors import (
    AuthError,
    NotFoundError,
    PermissionDeniedError,
    ServerError,
    TransportError,
    from_status,
)


class CredentialVerificationTests(unittest.TestCase):
    def test_narrow_scopes(self):
        client = Mock()
        client.get.return_value = {"scopes": ["goals:write"]}
        self.assertEqual(verify_key(client), (["goals:write"], None))
        client.get.assert_called_once_with("/v1/dev/key")

    def test_explicit_empty_scopes(self):
        client = Mock()
        client.get.return_value = {"scopes": []}
        self.assertEqual(verify_key(client), ([], None))

    def test_older_backend(self):
        client = Mock()
        client.get.side_effect = [NotFoundError("Not found"), []]
        self.assertEqual(verify_key(client), (None, None))
        self.assertEqual(client.get.call_args.args, ("/v1/dev/user/memories",))
        self.assertEqual(client.get.call_args.kwargs, {"params": {"limit": 1}})

    def test_older_backend_permission_denial(self):
        client = Mock()
        client.get.side_effect = [NotFoundError("Not found"), from_status(403)]
        scopes, warning = verify_key(client)
        self.assertIsNone(scopes)
        self.assertIn("Key is valid", warning)

    def test_no_fallback_for_other_errors(self):
        for error in [
            from_status(401),
            from_status(403),
            ServerError("Unavailable"),
            TransportError("Offline"),
        ]:
            with self.subTest(error=type(error).__name__):
                client = Mock()
                client.get.side_effect = error
                with self.assertRaises(type(error)):
                    verify_key(client)
                client.get.assert_called_once_with("/v1/dev/key")

    def test_fallback_invalid_key_rejected(self):
        client = Mock()
        client.get.side_effect = [NotFoundError("Not found"), from_status(401)]
        with self.assertRaises(AuthError):
            verify_key(client)

    def test_network_error_keeps_transport_type(self):
        client = Mock()
        client.get.side_effect = TransportError("Offline")
        with self.assertRaises(TransportError) as caught:
            verify_key(client)
        self.assertNotIsInstance(caught.exception, AuthError)

    def test_permission_error_retains_auth_exit_code(self):
        error = from_status(403)
        self.assertIsInstance(error, PermissionDeniedError)
        self.assertIsInstance(error, AuthError)
        self.assertEqual(error.exit_code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
