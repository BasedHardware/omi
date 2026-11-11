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
# Note: the fixture route must NOT collide with the real KNOWN_DUPLICATES entry
# ("/v1/conversations/{}/action-items") — path normalization would exempt it.
ROUTER_A = (
    "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1/conversations')\n"
    "@router.delete('/{id}/notes')\ndef delete_note(id: str):\n    pass\n"
)
ROUTER_B = (
    "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1/conversations')\n"
    "@router.delete('/{id}/notes')\ndef delete_all(id: str):\n    pass\n"
)
ROUTER_B_UNIQUE = ROUTER_B.replace("notes", "notes-all")


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
        with mock.patch.object(cdr, "ROOT", self.roots[0]), mock.patch.object(
            cdr, "ROUTERS_DIR", self.roots[0] / "backend" / "routers"
        ), mock.patch.object(
            cdr,
            "ENTRYPOINTS",
            {
                "main": self.roots[0] / "backend" / "main.py",
                "desktop_backend": self.roots[0] / "backend" / "desktop_backend.py",
                "pusher": self.roots[0] / "backend" / "pusher" / "main.py",
            },
        ):
            return cdr.main()

    def _run_capture(self):
        import contextlib, io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self._run()
        return code, buf.getvalue()

    def test_detects_shadowed_duplicate(self):
        write(self.roots[0], "backend/routers/items.py", ROUTER_B)
        code, out = self._run_capture()
        self.assertEqual(code, 1)
        self.assertIn("DELETE /v1/conversations/{}/notes", out)

    def test_unique_routes_pass(self):
        write(self.roots[0], "backend/routers/items.py", ROUTER_B_UNIQUE)
        code, out = self._run_capture()
        self.assertEqual(code, 0)
        self.assertIn("ok: no duplicate route registrations", out)

    def test_same_path_different_app_is_not_duplicate(self):
        # mount the conflicting router only in the pusher app instead
        write(self.roots[0], "backend/routers/items.py", ROUTER_B)
        write(
            self.roots[0],
            "backend/pusher/main.py",
            "from routers import items\napp.include_router(items.router)\n",
        )
        write(
            self.roots[0],
            "backend/main.py",
            "from routers import conv\napp.include_router(conv.router)\n",
        )
        code, _ = self._run_capture()
        self.assertEqual(code, 0)

    def test_api_route_expands_declared_methods_only(self):
        # api_route with methods=['GET', 'POST'] registers exactly GET+POST,
        # not all five verbs; a plain DELETE on the same path is not a duplicate.
        write(
            self.roots[0],
            "backend/routers/items.py",
            "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1/x')\n"
            "@router.api_route('/thing', methods=['GET', 'POST'])\ndef t():\n    pass\n"
            "@router.delete('/thing')\ndef d():\n    pass\n",
        )
        code, _ = self._run_capture()
        self.assertEqual(code, 0)

    def test_api_route_method_overlap_is_duplicate(self):
        write(
            self.roots[0],
            "backend/routers/items.py",
            "from fastapi import APIRouter\nrouter = APIRouter(prefix='/v1/x')\n"
            "@router.api_route('/thing', methods=['GET', 'POST'])\ndef t():\n    pass\n"
            "@router.get('/thing')\ndef g():\n    pass\n",
        )
        code, out = self._run_capture()
        self.assertEqual(code, 1)
        self.assertIn("GET /v1/x/thing", out)

    def test_known_duplicate_is_exempt(self):
        # The real load-bearing duplicate: shipped Flutter clients depend on the
        # first-mounted conversations handler, so an exact KNOWN_DUPLICATES match
        # must pass (with an exemption note) instead of failing the check.
        write(
            self.roots[0],
            "backend/routers/conv.py",
            ROUTER_A.replace("/{id}/notes", "/{conversation_id}/action-items"),
        )
        write(
            self.roots[0],
            "backend/routers/items.py",
            ROUTER_B.replace("/{id}/notes", "/{conversation_id}/action-items"),
        )
        code, out = self._run_capture()
        self.assertEqual(code, 0)
        self.assertIn("known duplicates exempted", out)
        self.assertIn("DELETE /v1/conversations/{}/action-items", out)

    def test_param_name_normalization_detects_shadowing(self):
        # /{id}/x vs /{conversation_id}/x are the same FastAPI path pattern;
        # raw-string keys would miss the duplicate.
        write(
            self.roots[0],
            "backend/routers/items.py",
            ROUTER_B.replace("/{id}/notes", "/{conversation_id}/notes"),
        )
        code, out = self._run_capture()
        self.assertEqual(code, 1)
        self.assertIn("DELETE /v1/conversations/{}/notes", out)

    def test_named_attribute_mounts_are_checked(self):
        # api_key_management pattern: one module exposing mcp_router and
        # developer_router, both mounted via named attributes. A duplicate across
        # two modules' named routers must be caught, and mounting both routers of
        # the same module must not be a false duplicate.
        write(
            self.roots[0],
            "backend/main.py",
            "from routers import api_key_management\n"
            "app.include_router(api_key_management.mcp_router)\n"
            "app.include_router(api_key_management.developer_router)\n",
        )
        write(
            self.roots[0],
            "backend/routers/api_key_management.py",
            "from fastapi import APIRouter\nmcp_router = APIRouter()\ndeveloper_router = APIRouter()\n"
            "@mcp_router.get('/v1/mcp/keys')\ndef mk():\n    pass\n"
            "@developer_router.get('/v1/dev/keys')\ndef dk():\n    pass\n",
        )
        code, out = self._run_capture()
        self.assertEqual(code, 0)
        self.assertIn("ok: no duplicate route registrations", out)
        # now shadow mcp_router's path from another module's mounted router
        write(
            self.roots[0],
            "backend/routers/shadow.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/v1/mcp/keys')\ndef s():\n    pass\n",
        )
        write(
            self.roots[0],
            "backend/main.py",
            "from routers import api_key_management, shadow\n"
            "app.include_router(api_key_management.mcp_router)\n"
            "app.include_router(shadow.router)\n",
        )
        code, out = self._run_capture()
        self.assertEqual(code, 1)
        self.assertIn("GET /v1/mcp/keys", out)

    def test_constant_path_decorators_are_checked(self):
        # jit_* pattern: path is a module-level constant.
        write(
            self.roots[0],
            "backend/routers/items.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "_SNAPSHOT_PATH = '/v1/jit/snapshot'\n"
            "@router.get(_SNAPSHOT_PATH)\ndef snap():\n    pass\n",
        )
        write(
            self.roots[0],
            "backend/routers/shadow.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/v1/jit/snapshot')\ndef s():\n    pass\n",
        )
        write(
            self.roots[0],
            "backend/main.py",
            "from routers import items, shadow\n"
            "app.include_router(items.router)\napp.include_router(shadow.router)\n",
        )
        code, out = self._run_capture()
        self.assertEqual(code, 1)
        self.assertIn("GET /v1/jit/snapshot", out)

    def test_add_api_route_table_is_checked(self):
        # desktop_deprecated pattern: literal dict + loop with add_api_route.
        write(
            self.roots[0],
            "backend/main.py",
            "from routers import dep, shadow\n"
            "app.include_router(dep.router)\napp.include_router(shadow.router)\n",
        )
        write(
            self.roots[0],
            "backend/routers/dep.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "_ROUTES = {\n    '/v1/legacy/thing': ('GET', 'PATCH'),\n}\n"
            "for route_path, route_methods in _ROUTES.items():\n"
            "    router.add_api_route(route_path, deprecated_handler, methods=list(route_methods))\n"
            "async def deprecated_handler(request):\n    pass\n",
        )
        write(
            self.roots[0],
            "backend/routers/shadow.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            "@router.get('/v1/legacy/thing')\ndef s():\n    pass\n",
        )
        code, out = self._run_capture()
        self.assertEqual(code, 1)
        self.assertIn("GET /v1/legacy/thing", out)

    def test_double_mount_of_same_router_is_duplicate(self):
        # Mounting the same router twice registers every route twice; FastAPI's
        # first-match makes the second mount dead code. len(set(v)) > 1 missed it.
        write(
            self.roots[0],
            "backend/main.py",
            "from routers import conv\n"
            "app.include_router(conv.router)\napp.include_router(conv.router)\n",
        )
        code, out = self._run_capture()
        self.assertEqual(code, 1)
        self.assertIn("DELETE /v1/conversations/{}/notes", out)


if __name__ == "__main__":
    unittest.main()
