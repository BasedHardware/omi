"""Cross-component contract test.

The persona client and the persona-chat route are maintained in different
parts of the codebase (plugins/_shared vs backend/routers). When their
contract drifts, integration breaks in production but unit tests in
isolation still pass. v0.1 had exactly this bug: the client sent no ?uid
query param, the route expected it, every request 422'd.

This file pins the contract from BOTH sides simultaneously:

1. The client test (test_persona_client.py::test_sends_uid_as_query_param)
   asserts the client includes params={"uid": uid}.

2. The backend test (test_persona_chat_endpoint.py) asserts the route
   extracts `uid` from query string.

If either side changes without the other, one of those tests fails.

We additionally verify the URL pattern matches: the client constructs
the same path the route is registered at.
"""

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SHARED = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.abspath(os.path.join(_SHARED, "..", "..", "backend"))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_SHARED, ".."))

for p in (_BACKEND, _SHARED, _PLUGIN_ROOT):
    if p not in sys.path:
        sys.path.append(p)


def _read(path: str) -> str:
    return Path(path).read_text()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestPersonaChatContract:
    """Pins the URL and param shape that persona client and backend route share."""

    def test_client_url_matches_route_path(self):
        """The path the client constructs must match the path the route is
        registered at. If either drifts, this test fails."""
        from persona_client import chat
        import inspect

        # Extract URL prefix the client builds
        client_src = _read(os.path.join(_SHARED, "persona_client.py"))
        client_url_match = re.search(
            r'url\s*=\s*f?"\{omi_base\.rstrip\([^)]*\)\}/([^"]+)"',
            client_src,
        )
        assert client_url_match, "could not find URL template in persona_client.py"
        client_path = "/" + client_url_match.group(1)

        # Extract path the backend route is registered at. There are many
        # @router.post decorators in this file; find the one immediately
        # above `async def persona_chat_via_integration`.
        backend_src = _read(os.path.join(_BACKEND, "routers", "integration.py"))
        route_match = re.search(
            r"@router\.post\(\s*['\"]([^'\"]+)['\"][^)]*\)\s*\n\s*" r"async def persona_chat_via_integration",
            backend_src,
        )
        assert route_match, "could not find @router.post above persona_chat_via_integration"
        backend_path = route_match.group(1)

        assert client_path == backend_path, (
            f"URL path mismatch: client constructs {client_path}, " f"backend route is {backend_path}"
        )

    def test_client_sends_uid_in_params(self):
        """The route extracts `uid` as a FastAPI path/query parameter.
        The client must send it as a query param, not in the JSON body."""
        from persona_client import chat
        import inspect

        src = _read(os.path.join(_SHARED, "persona_client.py"))
        # The client.post() call must include `params={"uid": uid}` (or similar)
        assert 'params={"uid": uid}' in src, (
            "persona_client.chat() must send uid as a query param "
            "(the backend route extracts uid from the URL, not the body)"
        )

    def test_backend_route_uses_uid_as_query_param(self):
        """Sanity check: the route signature must include `uid: str` as a
        non-body parameter so FastAPI extracts it from the URL."""
        backend_src = _read(os.path.join(_BACKEND, "routers", "integration.py"))
        # Find the persona_chat_via_integration function signature
        sig_match = re.search(
            r"async def persona_chat_via_integration\([^)]*\)",
            backend_src,
        )
        assert sig_match, "could not find persona_chat_via_integration signature"
        sig = sig_match.group(0)
        # uid should appear (as a top-level arg, not nested in body)
        assert "uid: str" in sig, (
            f"persona_chat_via_integration must accept `uid: str` as a " f"top-level parameter; signature is: {sig}"
        )

    def test_backend_route_requires_uid_not_body(self):
        """Body model must NOT include `uid`. If someone adds uid to the body
        model, the FastAPI dependency resolution will silently use the
        query-string one (because of order) — better to fail loud here."""
        models_src = _read(os.path.join(_BACKEND, "models", "integrations.py"))
        # Find PersonaChatRequest class and ensure uid is not a field
        req_match = re.search(
            r"class PersonaChatRequest.*?(?=\nclass |\Z)",
            models_src,
            re.DOTALL,
        )
        assert req_match, "could not find PersonaChatRequest class"
        body_class = req_match.group(0)
        assert "uid:" not in body_class, (
            "PersonaChatRequest must not have a `uid` field — uid comes from "
            "the URL query string and is the auth boundary. Adding it to the "
            "body would make uid spoofable."
        )
