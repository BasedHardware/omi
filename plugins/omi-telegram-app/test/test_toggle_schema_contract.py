"""Contract test: README /toggle docs must match the real ToggleRequest model.

Code-review sub-agent on PR #8531 caught a documentation regression:
the README claimed POST /toggle required a bot_token body field with
403-on-wrong-token semantics, but the real ToggleRequest Pydantic model
(T-007 security redesign) only accepts {chat_id, enabled} and the
endpoint authenticates via plugin bearer (header), not via a body token.

Long-lived platform secrets deliberately do NOT transit through the chat
assistant (chat history, tool-call logs, traces, model context). The
README must reflect that contract \u2014 otherwise developers will paste a
real bot token into chat thinking it's required.

This test pins both:
1. The ToggleRequest schema (no bot_token field)
2. The README (no "bot_token" example in the /toggle body)
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SHARED = os.path.abspath(os.path.join(_PLUGIN_ROOT, "..", "_shared"))
for p in (_PLUGIN_ROOT, _SHARED):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load_main_module():
    spec = importlib.util.spec_from_file_location("main", os.path.join(_PLUGIN_ROOT, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["main"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestToggleSchemaContract:
    def test_toggle_request_does_not_have_bot_token(self):
        """The /toggle body schema must NOT include bot_token \u2014 the\n        manifest redesign (a9cb72ec) deliberately removed it so the\n        chat assistant never asks the user for long-lived platform\n        secrets. Reviewer-flagged regression on PR #8531."""
        main = _load_main_module()
        ToggleRequest = main.ToggleRequest
        fields = set(ToggleRequest.model_fields.keys())
        assert "bot_token" not in fields, (
            f"ToggleRequest must NOT have a bot_token field (the\n            maintainer security review removed it for AI Clone). "
            f"Found fields: {fields}"
        )
        assert "chat_id" in fields
        assert "enabled" in fields

    def test_toggle_endpoint_auth_is_bearer_not_body_token(self):
        """The /toggle endpoint must use Depends(require_bearer) for auth,\n        not a body bot_token field. Catches regressions where a\n        developer adds bot_token back to the body."""
        main = _load_main_module()
        # Inspect the route's dependencies \u2014 must include require_bearer.
        toggle_route = None
        for route in main.app.routes:
            if getattr(route, "path", None) == "/toggle":
                toggle_route = route
                break
        assert toggle_route is not None, "no /toggle route registered"
        # FastAPI exposes dependencies on route.dependant.dependencies
        dep_names = []
        for d in getattr(toggle_route, "dependant", None).dependencies or []:
            if d.call:
                dep_names.append(getattr(d.call, "__name__", str(d.call)))
        assert any(
            "require_bearer" in n for n in dep_names
        ), f"/toggle must depend on require_bearer. Found deps: {dep_names}"

    def test_readme_does_not_claim_bot_token_required_in_toggle_body(self):
        """README must NOT instruct users to paste bot_token in the\n        /toggle body \u2014 the entire point of the T-007 redesign was\n        that the chat assistant never sees platform secrets."""
        readme_path = os.path.join(_PLUGIN_ROOT, "README.md")
        readme = Path(readme_path).read_text()
        # Find the /toggle section.
        idx = readme.find("`POST /toggle`")
        assert idx != -1, "README must document POST /toggle"
        # Take the next ~1500 chars (covers the auth + body subsection)
        section = readme[idx : idx + 1500]
        # The section MUST mention bearer token as the auth mechanism.
        assert "bearer" in section.lower() or "AI_CLONE_PLUGIN_TOKEN" in section, (
            "README /toggle section must document bearer auth "
            "(AI_CLONE_PLUGIN_TOKEN) \u2014 otherwise developers will "
            "think bot_token in the body is the auth mechanism."
        )
        # The example JSON body must NOT contain a bot_token field.
        assert '"bot_token"' not in section, (
            "README /toggle example body must NOT contain bot_token \u2014 "
            "long-lived secrets should never transit through chat. "
            "The T-007 redesign deliberately removed bot_token from "
            "ToggleRequest for this reason."
        )
