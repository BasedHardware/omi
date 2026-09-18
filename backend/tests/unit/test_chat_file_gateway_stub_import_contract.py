"""Regression test: the chat_file suite must import the real module it loads.

Production/CI evidence (2026-08-31): e6b545c1b8 (file-chat gateway-lane
degrade) added ``is_gateway_model_not_found`` to the
``utils.llm.gateway_client`` import block in ``utils/other/chat_file.py``,
but the local ``gateway_client`` stub installed by
``test_chat_file_upload_unsupported.py`` did not grow the attribute. That
suite loads the REAL ``chat_file`` module against its stub, so the module
failed at import time and every test in the file errored at setup —
deterministically, on ``main``, while the push pipeline (which does not run
backend unit tests) stayed green. Any future import added to ``chat_file``
re-creates the same outage the same way.

The contract under test: the stub surface a test harness installs must
satisfy the real module it loads — pinned here by importing the real
``chat_file`` against a stub built from the SAME attribute recipe the
chat-file suite uses, so a missing attribute surfaces here first (named,
actionable) instead of as seven setup ERRORS in the sibling suite.

Failure-Class: FC-ship-before-required-route — the sibling instance of the
same class as e6b545c1b8/#12444 (a client — here the test suite — that
hard-imports a name its serving environment must provide before it loads);
instance fix only, guard surface = this behavioral import test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgu4RZv",
)

import tests.unit._chat_router_test_harness as harness  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _chat_file_gateway_stub() -> ModuleType:
    """The exact attribute recipe test_chat_file_upload_unsupported installs."""
    gateway_client = ModuleType("utils.llm.gateway_client")
    gateway_client.should_route_features_through_gateway = MagicMock(return_value=False)
    gateway_client.CHAT_AGENT_ROUTE_DIRECT = "direct"
    gateway_client.CHAT_AGENT_ROUTE_GATEWAY = "gateway"
    gateway_client.get_chat_agent_route = MagicMock(return_value="direct")
    gateway_client.file_chat_auto_lane_id = MagicMock(return_value="omi:auto:file-chat-vision")
    gateway_client.file_chat_feature_header = MagicMock(return_value={})
    gateway_client.get_file_chat_gateway_async_client = MagicMock()
    gateway_client.get_file_chat_gateway_sync_client = MagicMock()
    gateway_client.is_gateway_model_not_found = MagicMock(return_value=False)
    return gateway_client


def _install_stack(stub: ModuleType) -> None:
    """Install the chat-file suite's package + stub stack (with restore)."""
    harness.install_package("models", BACKEND_DIR / "models")
    harness.install_package("database", BACKEND_DIR / "database")
    harness.install_package("utils", BACKEND_DIR / "utils")
    harness.install_package("utils.other", BACKEND_DIR / "utils" / "other")
    harness.install_package("utils.llm", BACKEND_DIR / "utils" / "llm")

    harness.wire_common_stubs(harness.install_module)
    harness.install_module("models.app")

    harness.install_module("utils.llm.gateway_client", stub)


def test_chat_file_imports_against_the_suite_gateway_stub():
    """The real chat_file module must load against the suite's stub recipe.

    Drives the production seam (import of ``utils/other/chat_file.py``)
    through the same ``load_real_module`` the broken suite uses, with the
    same ``sys.modules`` snapshot/restore discipline. Fails at the exact
    import if the stub falls behind the module's import block.
    """
    saved = {k: v for k, v in sys.modules.items()}
    try:
        _install_stack(_chat_file_gateway_stub())
        module = harness.load_real_module("utils.other.chat_file", BACKEND_DIR / "utils" / "other" / "chat_file.py")
        assert module is not None
        # The module's real public surface: the typed errors the router maps
        # to HTTP codes, present since the suite's founding.
        assert hasattr(module, "UnsupportedChatFileError")
        assert hasattr(module, "StaleChatFileError")
        assert hasattr(module, "ProviderRejectedChatFileError")
    finally:
        harness.cleanup(saved)


def test_a_stale_stub_fails_on_the_exact_missing_attribute():
    """If chat_file grows a gateway import the stub lacks, the failure names it.

    Builds the PRE-FIX stub recipe (no ``is_gateway_model_not_found``) and
    asserts the ImportError carries the missing attribute name, so the
    recurring failure mode of this class is a one-line diagnosis instead of
    seven opaque setup errors. If this ever raises AssertionError instead,
    the module's import block changed and the recipe above must follow.
    """
    saved = {k: v for k, v in sys.modules.items()}
    try:
        stale = _chat_file_gateway_stub()
        del stale.is_gateway_model_not_found
        _install_stack(stale)
        try:
            harness.load_real_module("utils.other.chat_file", BACKEND_DIR / "utils" / "other" / "chat_file.py")
        except ImportError as e:
            assert "is_gateway_model_not_found" in str(e), (
                "import must fail on the exact missing attribute so the stub " "fix is actionable, got: %s" % e
            )
        else:
            raise AssertionError(
                "stale stub unexpectedly satisfied chat_file imports — the "
                "guard recipe no longer matches the module's import block"
            )
    finally:
        harness.cleanup(saved)
