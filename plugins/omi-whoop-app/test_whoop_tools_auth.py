"""Tests for the Whoop /tools/* caller-authentication guard.

These exercise require_whoop_tools_auth directly (no network / no Whoop API),
covering the fail-closed, wrong-token, and correct-token paths.
"""

import asyncio
import os
import unittest

from fastapi import HTTPException

import whoop_tools_auth as guard


class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def call(headers=None, query_token=None):
    req = FakeRequest(headers=headers)
    return asyncio.run(guard.require_whoop_tools_auth(req, whoop_tools_token=query_token))


class WhoopToolsAuth(unittest.TestCase):
    def setUp(self):
        os.environ.pop("WHOOP_TOOLS_SECRET", None)

    def tearDown(self):
        os.environ.pop("WHOOP_TOOLS_SECRET", None)

    def test_unconfigured_fails_closed_503(self):
        with self.assertRaises(HTTPException) as ctx:
            call(headers={"Authorization": "Bearer anything"})
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_token_401(self):
        os.environ["WHOOP_TOOLS_SECRET"] = "s3cr3t"
        with self.assertRaises(HTTPException) as ctx:
            call(headers={})
        self.assertEqual(ctx.exception.status_code, 401)

    def test_wrong_token_401(self):
        os.environ["WHOOP_TOOLS_SECRET"] = "s3cr3t"
        with self.assertRaises(HTTPException) as ctx:
            call(headers={"Authorization": "Bearer wrong"})
        self.assertEqual(ctx.exception.status_code, 401)

    def test_correct_bearer_ok(self):
        os.environ["WHOOP_TOOLS_SECRET"] = "s3cr3t"
        self.assertIsNone(call(headers={"Authorization": "Bearer s3cr3t"}))

    def test_correct_query_token_ok(self):
        os.environ["WHOOP_TOOLS_SECRET"] = "s3cr3t"
        self.assertIsNone(call(query_token="s3cr3t"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
