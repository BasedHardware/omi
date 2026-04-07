"""Tests for Phase 2: async OAuth/auth token exchanges (issue #6369).

Verifies that auth.py, oauth.py, custom_auth.py use httpx.AsyncClient
instead of blocking requests.post/get.
"""

import ast
import os

import pytest


def _get_async_functions_with_requests(filepath: str) -> list:
    """Parse a Python file and find async functions using requests.*."""
    with open(filepath) as f:
        source = f.read()
    tree = ast.parse(source)

    violations = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self._in_async = False

        def visit_AsyncFunctionDef(self, node):
            old = self._in_async
            self._in_async = True
            self.generic_visit(node)
            self._in_async = old

        def visit_FunctionDef(self, node):
            old = self._in_async
            self._in_async = False
            self.generic_visit(node)
            self._in_async = old

        def visit_Call(self, node):
            if self._in_async and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == 'requests':
                    violations.append((node.lineno, f'requests.{node.func.attr}'))
            self.generic_visit(node)

    Visitor().visit(tree)
    return violations


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAuthNoBlockingRequests:
    """Verify auth.py has no blocking requests in async functions."""

    def test_auth_no_blocking_requests(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'auth.py')
        violations = _get_async_functions_with_requests(filepath)
        assert violations == [], f"Blocking requests calls in async auth.py: {violations}"

    def test_oauth_no_blocking_requests(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'oauth.py')
        violations = _get_async_functions_with_requests(filepath)
        assert violations == [], f"Blocking requests calls in async oauth.py: {violations}"

    def test_custom_auth_no_blocking_requests(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'custom_auth.py')
        violations = _get_async_functions_with_requests(filepath)
        assert violations == [], f"Blocking requests calls in async custom_auth.py: {violations}"


class TestSocialNoBlockingPatterns:
    """Verify social.py has no blocking patterns in async functions."""

    def test_social_no_sync_httpx(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'social.py')
        with open(filepath) as f:
            source = f.read()
        tree = ast.parse(source)

        violations = []

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self._in_async = False

            def visit_AsyncFunctionDef(self, node):
                self._in_async = True
                self.generic_visit(node)
                self._in_async = False

            def visit_FunctionDef(self, node):
                self._in_async = False
                self.generic_visit(node)

            def visit_Call(self, node):
                if self._in_async and isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == 'httpx':
                        # Allow httpx.AsyncClient() and httpx.Timeout() — only flag sync methods
                        if node.func.attr not in ('AsyncClient', 'Timeout'):
                            violations.append((node.lineno, f'httpx.{node.func.attr}'))
                self.generic_visit(node)

        Visitor().visit(tree)
        assert violations == [], f"Sync httpx calls in async social.py: {violations}"

    def test_social_no_time_sleep(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'social.py')
        with open(filepath) as f:
            source = f.read()
        # time.sleep should not exist at all
        assert 'time.sleep' not in source, "social.py still uses time.sleep — use asyncio.sleep"

    def test_social_uses_asyncio_sleep(self):
        filepath = os.path.join(BACKEND_DIR, 'utils', 'social.py')
        with open(filepath) as f:
            source = f.read()
        assert 'asyncio.sleep' in source, "social.py retry should use asyncio.sleep"

    def test_social_no_shared_webhook_client(self):
        """social.py must use local httpx.AsyncClient, not shared webhook client,
        because it runs in background threads with separate event loops."""
        filepath = os.path.join(BACKEND_DIR, 'utils', 'social.py')
        with open(filepath) as f:
            source = f.read()
        assert 'get_webhook_client' not in source, (
            "social.py should use local httpx.AsyncClient, not shared get_webhook_client() — "
            "shared client breaks when used across event loops in background threads"
        )


class TestAppsNoBlockingIO:
    """Verify apps.py file I/O uses asyncio.to_thread."""

    def test_apps_no_sync_file_write_in_persona(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'apps.py')
        with open(filepath) as f:
            source = f.read()
        tree = ast.parse(source)

        sync_file_writes_in_async = []

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self._in_async = False
                self._func_name = None

            def visit_AsyncFunctionDef(self, node):
                self._in_async = True
                self._func_name = node.name
                self.generic_visit(node)
                self._in_async = False

            def visit_FunctionDef(self, node):
                self._in_async = False
                self.generic_visit(node)

            def visit_Call(self, node):
                if self._in_async and isinstance(node.func, ast.Name) and node.func.id == 'open':
                    # Sync open() in async function — should be offloaded
                    sync_file_writes_in_async.append((node.lineno, self._func_name))
                self.generic_visit(node)

        Visitor().visit(tree)
        # All open() calls should be in _write_file helper, not directly in async functions
        assert sync_file_writes_in_async == [], f"Direct sync open() in async apps.py: {sync_file_writes_in_async}"

    def test_apps_no_blocking_requests(self):
        filepath = os.path.join(BACKEND_DIR, 'routers', 'apps.py')
        violations = _get_async_functions_with_requests(filepath)
        assert violations == [], f"Blocking requests calls in async apps.py: {violations}"
