"""End-to-end auth tests for the iq-rating data-plane routes (#14430).

These tests drive the **real** FastAPI application through
``fastapi.testclient.TestClient`` so the full request path is exercised:
routing, ``Depends(require_iq_rating_auth)`` resolution, the real data
functions (``get_people_for_user`` / ``store_people`` / ``hide_person`` /
``adjust_iq`` / ``unhide_person``), a real SQLite database, and the HTTP
status codes an unauthenticated attacker would actually receive.

There are **no mocks and no monkeypatching** in this file. The only test
setup is:
  * point ``main.DB_PATH`` at a throwaway temp SQLite file (configuration,
    not a stub) and re-run ``init_db()`` so the real schema is created there;
  * seed rows through the real ``store_people`` helper.

Everything the auth decision and the handlers touch is the production code.

Run with the project deps installed (``pip install -r requirements.txt httpx``):
    python -m pytest test_iq_auth_e2e.py -v
or directly:
    python test_iq_auth_e2e.py
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent

from fastapi.testclient import TestClient  # noqa: E402  (real dep, see requirements.txt)


def _load_main():
    """Import plugins/iq_rating/main.py as a module without a package context."""
    if str(PLUGIN_DIR) not in sys.path:
        sys.path.insert(0, str(PLUGIN_DIR))
    spec = importlib.util.spec_from_file_location("iq_rating_main", PLUGIN_DIR / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["iq_rating_main"] = module
    spec.loader.exec_module(module)
    return module


class TestIqRatingRoutesEndToEnd(unittest.TestCase):
    SECRET = "e2e-secret-token-abc123"
    VICTIM = "victim-uid-123"
    PERSON = {"id": "person-1", "name": "Alice Example", "iq": 120, "memory_count": 3}

    @classmethod
    def setUpClass(cls):
        # Credentials the app's startup path expects, plus the auth secret.
        os.environ["IQ_RATING_SECRET"] = cls.SECRET
        os.environ.setdefault("OMI_APP_ID", "test-app-id")
        os.environ.setdefault("OMI_APP_SECRET", "test-app-secret")

        cls.main = _load_main()

        # Redirect the real DB to a throwaway temp file (configuration only).
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.main.DB_PATH = Path(cls._tmpdir.name) / "iq_rating_test.db"
        cls.main.init_db()  # real schema, real file

        # Seed real rows through the real helper (no monkeypatching).
        cls.main.store_people(cls.VICTIM, [dict(cls.PERSON)])

        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()
        os.environ.pop("IQ_RATING_SECRET", None)

    def setUp(self):
        # Clear the in-process cache so each test reads the real DB state.
        self.main._cache.clear()

    # ---- helpers -----------------------------------------------------------
    def _assert_unauthorized(self, method, path, **kwargs):
        resp = getattr(self.client, method)(path, **kwargs)
        self.assertEqual(
            resp.status_code, 401,
            msg=f"{method.upper()} {path} should be 401 without a token, "
                f"got {resp.status_code}: {resp.text}",
        )
        return resp

    # ---- the six uid-keyed data-plane routes reject anonymous callers ------
    def test_get_iq_api_requires_auth(self):
        self._assert_unauthorized("get", "/iq-rating/iq/api", params={"uid": self.VICTIM})

    def test_get_iq_preload_requires_auth(self):
        self._assert_unauthorized("get", "/iq-rating/iq/preload", params={"uid": self.VICTIM})

    def test_get_iq_refresh_requires_auth(self):
        self._assert_unauthorized("get", "/iq-rating/iq/refresh", params={"uid": self.VICTIM})

    def test_post_iq_hide_requires_auth(self):
        self._assert_unauthorized(
            "post", "/iq-rating/iq/hide", params={"uid": self.VICTIM, "person_id": self.PERSON["id"]}
        )

    def test_post_iq_unhide_requires_auth(self):
        self._assert_unauthorized(
            "post", "/iq-rating/iq/unhide", params={"uid": self.VICTIM, "person_id": self.PERSON["id"]}
        )

    def test_post_iq_adjust_requires_auth(self):
        self._assert_unauthorized(
            "post",
            "/iq-rating/iq/adjust",
            params={"uid": self.VICTIM, "person_id": self.PERSON["id"], "delta": 10},
        )

    def test_iq_page_with_uid_requires_auth(self):
        # The uid-bearing page is a data-plane surface and must be guarded too.
        self._assert_unauthorized("get", "/iq-rating/iq", params={"uid": self.VICTIM})

    # ---- wrong / malformed credentials are rejected -----------------------
    def test_wrong_bearer_token_rejected(self):
        resp = self.client.get(
            "/iq-rating/iq/api",
            params={"uid": self.VICTIM},
            headers={"Authorization": "Bearer not-the-secret"},
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    def test_wrong_query_token_rejected(self):
        resp = self.client.get(
            "/iq-rating/iq/api", params={"uid": self.VICTIM, "iq_rating_token": "nope"}
        )
        self.assertEqual(resp.status_code, 401, resp.text)

    # ---- valid credentials pass the auth gate AND real data is served ------
    def test_valid_bearer_token_returns_real_seeded_data(self):
        resp = self.client.get(
            "/iq-rating/iq/api",
            params={"uid": self.VICTIM},
            headers={"Authorization": f"Bearer {self.SECRET}"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["uid"], self.VICTIM)
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["total_people"], 1)
        self.assertEqual(body["people"][0]["name"], self.PERSON["name"])
        self.assertEqual(body["people"][0]["iq"], self.PERSON["iq"])

    def test_valid_query_token_preload_reports_already_loaded(self):
        # Victim already has seeded people -> real get_people_for_user returns
        # them, so preload short-circuits to "already_loaded" (no background
        # thread, no network). Proves the query-param token path works.
        resp = self.client.get(
            "/iq-rating/iq/preload", params={"uid": self.VICTIM, "iq_rating_token": self.SECRET}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["status"], "already_loaded")

    def test_valid_token_adjust_mutates_real_db(self):
        # POST /iq/adjust with a valid token must actually change the stored IQ.
        resp = self.client.post(
            "/iq-rating/iq/adjust",
            params={"uid": self.VICTIM, "person_id": self.PERSON["id"], "delta": 10},
            headers={"Authorization": f"Bearer {self.SECRET}"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(resp.json()["new_iq"], self.PERSON["iq"] + 10)
        # Confirm the mutation hit the real DB via the real read path.
        self.main._cache.clear()
        people = self.main.get_people_for_user(self.VICTIM)
        self.assertEqual(people[0]["iq"], self.PERSON["iq"] + 10)

    def test_valid_token_hide_then_unhide_mutates_real_db(self):
        hide = self.client.post(
            "/iq-rating/iq/hide",
            params={"uid": self.VICTIM, "person_id": self.PERSON["id"]},
            headers={"Authorization": f"Bearer {self.SECRET}"},
        )
        self.assertEqual(hide.status_code, 200, hide.text)
        self.assertTrue(hide.json()["success"])
        self.main._cache.clear()
        # Hidden people are excluded from the default (non-hidden) read.
        self.assertEqual(self.main.get_people_for_user(self.VICTIM), [])

        unhide = self.client.post(
            "/iq-rating/iq/unhide",
            params={"uid": self.VICTIM, "person_id": self.PERSON["id"]},
            headers={"Authorization": f"Bearer {self.SECRET}"},
        )
        self.assertEqual(unhide.status_code, 200, unhide.text)
        self.assertTrue(unhide.json()["success"])
        self.main._cache.clear()
        self.assertEqual(len(self.main.get_people_for_user(self.VICTIM)), 1)

    def test_valid_token_iq_page_renders_seeded_person(self):
        resp = self.client.get(
            "/iq-rating/iq",
            params={"uid": self.VICTIM},
            headers={"Authorization": f"Bearer {self.SECRET}"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        # The real person name and a safely json-encoded uid must be present,
        # and the page must NOT contain the raw unescaped XSS sink pattern.
        self.assertIn(self.PERSON["name"], resp.text)
        self.assertIn('"victim-uid-123"', resp.text)  # json.dumps(uid) form
        self.assertNotIn("const uid = '", resp.text)

    # ---- public surfaces stay public --------------------------------------
    def test_uidless_landing_page_is_public(self):
        resp = self.client.get("/iq-rating/iq")
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_setup_status_is_public(self):
        resp = self.client.get("/iq-rating/iq/setup-status")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json(), {"is_setup_completed": True})

    # ---- fail-closed when the secret is unconfigured ----------------------
    def test_unconfigured_secret_fails_closed_503(self):
        saved = os.environ.pop("IQ_RATING_SECRET", None)
        try:
            resp = self.client.get(
                "/iq-rating/iq/api",
                params={"uid": self.VICTIM},
                headers={"Authorization": "Bearer anything"},
            )
            self.assertEqual(resp.status_code, 503, resp.text)
        finally:
            if saved is not None:
                os.environ["IQ_RATING_SECRET"] = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)