"""Contract guard: the Google grant the Gmail reader uses must request Gmail scope.

``get_gmail_messages_tool`` (``utils/retrieval/tools/gmail_tools.py``) reads email using the
token stored under the ``google_calendar`` integration — Gmail has no standalone backend OAuth
provider. So the ``google_calendar`` grant in ``AUTH_PROVIDERS`` MUST request a Gmail read
scope, or every server-side Gmail read 403s with insufficient scope while the reader code looks
correct. This is a config-contract guard (static — it reads the source, it does not exercise a
live OAuth grant), pinning the cross-file coupling that a scope trim could silently break.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
INTEGRATIONS_ROUTER = BACKEND_DIR / "routers" / "integrations.py"
GMAIL_TOOLS = BACKEND_DIR / "utils" / "retrieval" / "tools" / "gmail_tools.py"

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def _auth_providers() -> dict:
    """Evaluate the AUTH_PROVIDERS literal without importing the router (no import-time IO).

    AUTH_PROVIDERS is an *annotated* assignment (``AUTH_PROVIDERS: Dict[...] = {...}``),
    so it parses as ast.AnnAssign, not ast.Assign — handle both.
    """
    tree = ast.parse(INTEGRATIONS_ROUTER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "AUTH_PROVIDERS" for t in node.targets
        ):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "AUTH_PROVIDERS":
            assert node.value is not None, "AUTH_PROVIDERS declared without a value"
            return ast.literal_eval(node.value)
    raise AssertionError("AUTH_PROVIDERS assignment not found in routers/integrations.py")


class TestGmailScopeContract:
    def test_google_calendar_grant_requests_gmail_read_scope(self):
        scope = _auth_providers()["google_calendar"]["query"]["scope"]
        assert GMAIL_READ_SCOPE in scope.split(), (
            "google_calendar grant is missing the Gmail read scope; get_gmail_messages_tool "
            "reads this integration's token, so Gmail reads will 403 with insufficient scope."
        )

    def test_gmail_reader_reads_the_google_calendar_integration(self):
        # Pins the other half of the coupling: if the reader ever switches to its own
        # integration key, this guard must move with it (and this test should fail loudly).
        source = GMAIL_TOOLS.read_text(encoding="utf-8")
        assert "'google_calendar'" in source, (
            "gmail_tools.py no longer reads the google_calendar integration — the scope "
            "contract in this test is pinned to the wrong grant; update both together."
        )
