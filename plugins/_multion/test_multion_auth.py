"""
Hermetic regression tests for MultiOn endpoint authentication (#14463).

Verifies require_multion_auth enforces shared-secret validation (Bearer header or query param)
and guards mutating endpoints (POST /multion/submit_uid, POST /multion) against unauthenticated access.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add parent directories to sys.path
multion_dir = os.path.dirname(os.path.abspath(__file__))
if multion_dir not in sys.path:
    sys.path.insert(0, multion_dir)

from multion_auth import (
    require_multion_auth,
    _MULTION_WEBHOOK_SECRET_ENV,
    _QUERY_TOKEN_PARAM,
)
from fastapi import HTTPException


class TestMultiOnAuthGuard(unittest.TestCase):
    def test_unconfigured_secret_returns_503(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(_MULTION_WEBHOOK_SECRET_ENV, None)
            req = Mock()
            with self.assertRaises(HTTPException) as ctx:
                require_multion_auth(req)
            self.assertEqual(ctx.exception.status_code, 503)
            self.assertIn("not configured", ctx.exception.detail)

    def test_missing_token_returns_401(self):
        with patch.dict(os.environ, {_MULTION_WEBHOOK_SECRET_ENV: "valid_secret"}):
            req = Mock()
            req.headers = {}
            req.query_params = {}
            with self.assertRaises(HTTPException) as ctx:
                require_multion_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "unauthorized")

    def test_invalid_token_returns_401(self):
        with patch.dict(os.environ, {_MULTION_WEBHOOK_SECRET_ENV: "valid_secret"}):
            req = Mock()
            req.headers = {"Authorization": "Bearer wrong_secret"}
            req.query_params = {}
            with self.assertRaises(HTTPException) as ctx:
                require_multion_auth(req)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_valid_bearer_token_passes(self):
        with patch.dict(os.environ, {_MULTION_WEBHOOK_SECRET_ENV: "valid_secret"}):
            req = Mock()
            req.headers = {"Authorization": "Bearer valid_secret"}
            req.query_params = {}
            # Should not raise
            require_multion_auth(req)

    def test_valid_query_token_passes(self):
        with patch.dict(os.environ, {_MULTION_WEBHOOK_SECRET_ENV: "valid_secret"}):
            req = Mock()
            req.headers = {}
            req.query_params = {_QUERY_TOKEN_PARAM: "valid_secret"}
            # Should not raise
            require_multion_auth(req)

    def test_empty_or_whitespace_secret_treated_as_unconfigured(self):
        with patch.dict(os.environ, {_MULTION_WEBHOOK_SECRET_ENV: "   "}):
            req = Mock()
            with self.assertRaises(HTTPException) as ctx:
                require_multion_auth(req)
            self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
