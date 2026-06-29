"""Contract test: every ActionType enum value must produce permission text.

When a new ActionType is added (e.g. PERSONA_CHAT for AI Clone plugins),
the OAuth /v1/oauth/authorize handler must register permission text for
it, otherwise the user sees no consent info for that capability during
app install. Identified by cubic (P2) on PR #8531 — PERSONA_CHAT was
silently omitted from routers/oauth.py.

We pin the contract by introspecting both files at the source level so
the test stays fast and dependency-free.
"""

import os
import re
import sys
from pathlib import Path

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(rel_path: str) -> str:
    return Path(os.path.join(_BACKEND, rel_path)).read_text()


class TestOAuthPermissionContract:
    """Every ActionType must have a matching `elif action_type_value == ActionType.X.value`
    branch in routers/oauth.py that appends a permission dict."""

    def test_all_action_types_have_permission_text(self):
        from models.app import ActionType

        oauth_src = _read("routers/oauth.py")
        handled = set(re.findall(r"ActionType\.(\w+)\.value", oauth_src))

        # Every ActionType value that appears in the oauth router must
        # have a matching permission line. This catches the cubic-found
        # regression where PERSONA_CHAT was missing.
        for action in ActionType:
            assert action.name in handled, (
                f"ActionType.{action.name} is missing permission-text "
                f"handling in routers/oauth.py. Users installing an app "
                f"with this action will not see a consent explanation."
            )

    def test_persona_chat_has_permission_text(self):
        """P2 regression test for PR #8531: PERSONA_CHAT was silently
        omitted from the oauth permission list."""
        oauth_src = _read("routers/oauth.py")
        assert "ActionType.PERSONA_CHAT.value" in oauth_src, (
            "PERSONA_CHAT must have a permission branch in oauth.py " "(cubic-found regression on PR #8531)."
        )
        # The branch must actually append a permission — not be a no-op.
        # Match the elif block and assert it contains permissions.append(.
        m = re.search(
            r"elif action_type_value == ActionType\.PERSONA_CHAT\.value:.*?(?=elif|if)",
            oauth_src,
            re.DOTALL,
        )
        assert m, "PERSONA_CHAT branch missing"
        assert "permissions.append" in m.group(0), "PERSONA_CHAT branch exists but does not call permissions.append"
