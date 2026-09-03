#!/usr/bin/env python3
"""Hermetic self-test for check_duplicate_routes using temp-dir fixtures."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent / "check_duplicate_routes.py"
sys.path.insert(0, str(SCRIPT.parent))
import check_duplicate_routes as cdr  # noqa: E402


def write(base: Path, rel: str, text: str):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


APP_MAIN = "from routers import conv, items\napp.include_router(conv.router)\napp.include_router(items.router)\n"
ROUTER_A = (
    "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1/conversations')\n"
    "@router.delete('/{id}/action-items')\ndef delete_action_item(id: str):\n    pass\n"
)
ROUTER_B = (
    "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1/conversations')\n"
    "@router.delete('/{id}/action-items')\ndef delete_all(id: str):\n    pass\n"
)
ROUTER_B_UNIQUE = ROUTER_B.replace("action-items", "action-items-all")


class DuplicateRouteCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        write(base, "backend/main.py", APP_MAIN)
        write(base, "backend/desktop_backend.py", "app = 1\n")
        write(base, "backend/pusher/main.py", "app = 1\n")
        write(base, "backend/routers/conv.py", ROUTER_A)
        self.roots = [base]

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        with mock.patch.object(cdr, "ROOT", self.roots[0]), \
             mock.patch.object(cdr, "ROUTERS_DIR", self.roots[0] / "backend" / "routers"), \
             mock.patch.object(cdr, "ENTRYPOINTS", {
                 "main": self.roots[0] / "backend" / "main.py",
                 "desktop_backend": self.roots[0] / "backend" / "desktop_backend.py",
                 "pusher": self.roots[0] / "backend" / "pusher" / "main.py",
             }):
            return cdr.main()

    def test_detects_shadowed_duplicate(self):
        write(self.roots[0], "backend/routers/items.py", ROUTER_B)
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self._run()
        self.assertEqual(code, 1)
        self.assertIn("DELETE /v1/conversations/{id}/action-items", buf.getvalue())

    def test_unique_routes_pass(self):
        write(self.roots[0], "backend/routers/items.py", ROUTER_B_UNIQUE)
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self._run()
        self.assertEqual(code, 0)
        self.assertIn("ok: no duplicate route registrations", buf.getvalue())

    def test_same_path_different_app_is_not_duplicate(self):
        # desktop_backend mounts both too? no: mount only in pusher app instead
        write(self.roots[0], "backend/routers/items.py", ROUTER_B)
        write(self.roots[0], "backend/pusher/main.py",
              "from routers import items\napp.include_router(items.router)\n")
        write(self.roots[0], "backend/main.py",
              "from routers import conv\napp.include_router(conv.router)\n")
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self._run()
        self.assertEqual(code, 0)

    def test_api_route_expands_methods(self):
        write(self.roots[0], "backend/routers/items.py",
              "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1/x')\n"
              "@router.api_route('/thing', methods=['GET', 'POST'])\ndef t():\n    pass\n")
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self._run()
        self.assertEqual(code, 0)

    def test_known_duplicate_is_exempt(self):
        # The real load-bearing duplicate: shipped Flutter clients depend on the
        # first-mounted conversations handler, so an exact KNOWN_DUPLICATES match
        # must pass (with an exemption note) instead of failing the check.
        write(self.roots[0], "backend/routers/conv.py",
              ROUTER_A.replace("/{id}/action-items", "/{conversation_id}/action-items"))
        write(self.roots[0], "backend/routers/items.py",
              ROUTER_B.replace("/{id}/action-items", "/{conversation_id}/action-items"))
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self._run()
        self.assertEqual(code, 0)
        self.assertIn("known duplicates exempted", buf.getvalue())
        self.assertIn("DELETE /v1/conversations/{conversation_id}/action-items", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
