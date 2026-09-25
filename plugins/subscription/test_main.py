"""
Hermetic unit tests for the subscription plugin.

Validates:
- Router prefix and tags configuration
- Subscription endpoint renders with empty uid
- Subscription endpoint renders sanitized uid (security compliance)
- XSS and injection payloads are rejected by _sanitize_uid

These tests stub FastAPI at the module level so they run without
any pip dependencies (truly hermetic).
"""
import sys
import os
import types
import unittest

# ---------------------------------------------------------------------------
# Hermetic stub: install a minimal FastAPI mock into sys.modules BEFORE
# the production module is imported, so `from fastapi import ...` resolves.
# ---------------------------------------------------------------------------


def _install_fastapi_stubs():
    """Create lightweight stubs for fastapi and jinja2 so main.py can import."""

    # --- fastapi ---
    fastapi_mod = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, prefix="", tags=None):
            self.prefix = prefix
            self.tags = tags or []

        def get(self, *args, **kwargs):
            """Decorator stub — just returns the function unchanged."""
            def decorator(fn):
                return fn
            return decorator

    class _Request:
        pass

    fastapi_mod.APIRouter = _APIRouter
    fastapi_mod.Request = _Request
    sys.modules["fastapi"] = fastapi_mod

    # --- fastapi.responses ---
    responses_mod = types.ModuleType("fastapi.responses")

    class _HTMLResponse:
        pass

    responses_mod.HTMLResponse = _HTMLResponse
    sys.modules["fastapi.responses"] = responses_mod

    # --- fastapi.templating ---
    templating_mod = types.ModuleType("fastapi.templating")

    class _Jinja2Templates:
        def __init__(self, directory=""):
            self.directory = directory
            self._captured = None

        def TemplateResponse(self, template_name, context):
            self._captured = context
            return types.SimpleNamespace(status_code=200, body=b"OK")

    templating_mod.Jinja2Templates = _Jinja2Templates
    sys.modules["fastapi.templating"] = templating_mod


# Install stubs before any import of plugins.subscription.main
_install_fastapi_stubs()

# Ensure project root is on sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from plugins.subscription.main import router, subscription_page, _sanitize_uid, templates


class TestSubscriptionRouter(unittest.TestCase):
    """Verify APIRouter configuration."""

    def test_router_prefix_and_tags(self):
        self.assertEqual(router.prefix, "/subscription")
        self.assertIn("subscription", router.tags)


class TestSanitizeUid(unittest.TestCase):
    """Verify _sanitize_uid rejects dangerous payloads (XSS protection from #14478)."""

    def test_valid_uids_pass_through(self):
        self.assertEqual(_sanitize_uid("user_12345"), "user_12345")
        self.assertEqual(_sanitize_uid("usr-abc-DEF_99"), "usr-abc-DEF_99")

    def test_xss_payloads_rejected(self):
        self.assertEqual(_sanitize_uid("<script>alert(1)</script>"), "")
        self.assertEqual(_sanitize_uid("';alert(document.domain);//"), "")

    def test_sql_injection_rejected(self):
        self.assertEqual(_sanitize_uid("admin' OR '1'='1"), "")
        self.assertEqual(_sanitize_uid('admin" OR "1"="1'), "")

    def test_empty_and_whitespace_rejected(self):
        self.assertEqual(_sanitize_uid(""), "")
        self.assertEqual(_sanitize_uid("   "), "")

    def test_oversized_uid_rejected(self):
        self.assertEqual(_sanitize_uid("a" * 129), "")


class TestSubscriptionEndpoint(unittest.TestCase):
    """Hermetic endpoint tests using stubbed Jinja2Templates."""

    def _call_endpoint(self, uid=""):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(subscription_page(None, uid=uid))
        finally:
            loop.close()

    def test_subscription_endpoint_redirect_without_uid(self):
        """Endpoint must render successfully with empty uid."""
        self._call_endpoint(uid="")
        if templates._captured is not None:
            self.assertEqual(templates._captured["uid"], "")
            self.assertEqual(templates._captured["page_title"], "Upgrade to Unlimited")
        else:
            self.fail("TemplateResponse was not called — context not captured")

    def test_subscription_endpoint_valid_uid_rendering(self):
        """Endpoint must pass sanitized uid into template context."""
        self._call_endpoint(uid="user_sub_99")
        if templates._captured is not None:
            self.assertEqual(templates._captured["uid"], "user_sub_99")
        else:
            self.fail("TemplateResponse was not called — context not captured")

    def test_subscription_endpoint_sanitizes_xss_uid(self):
        """Endpoint must sanitize malicious uid via _sanitize_uid (XSS prevention)."""
        self._call_endpoint(uid="<script>alert(1)</script>")
        if templates._captured is not None:
            # _sanitize_uid must reject the XSS payload and return empty string
            self.assertEqual(templates._captured["uid"], "")
        else:
            self.fail("TemplateResponse was not called — context not captured")

    def test_subscription_endpoint_sanitizes_sql_injection_uid(self):
        """Endpoint must reject SQL injection patterns in uid."""
        self._call_endpoint(uid="admin' OR '1'='1")
        if templates._captured is not None:
            self.assertEqual(templates._captured["uid"], "")
        else:
            self.fail("TemplateResponse was not called — context not captured")


if __name__ == "__main__":
    unittest.main()
