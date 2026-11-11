"""Safety checks for the Streamlit example: no debug prints, constant error
surfaces, and a functional proof that a secret inside an exception never reaches
stdout or ``st.error``."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

APP_PATH = Path(__file__).resolve().parent.parent / "examples" / "app.py"
SENTINEL = "s3ntinel-mcp-key-value"


def test_app_has_no_print_or_nonconstant_error_surface() -> None:
    """AST tripwire: print() is forbidden entirely (debug prints leaked user
    content and could leak the API key), and every st.error/st.warning/
    st.exception/message_placeholder.error call must take a constant string."""
    tree = ast.parse(APP_PATH.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            pytest.fail(f"print() call at line {node.lineno} — can leak user data or the API key")
        if isinstance(func, ast.Attribute) and func.attr in {"error", "exception", "warning"}:
            for arg in node.args:
                assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), (
                    f"non-constant {func.attr}() argument at line {node.lineno} "
                    "— error surfaces must use constant messages"
                )


def _install_fake_modules(monkeypatch: pytest.MonkeyPatch, errors: list[str]) -> None:
    fake_st = types.ModuleType("streamlit")
    fake_st.error = lambda msg, *a, **k: errors.append(str(msg))
    fake_st.warning = lambda msg, *a, **k: errors.append(str(msg))

    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **k: None

    fake_agents = types.ModuleType("agents")
    fake_agents.Agent = MagicMock
    fake_agents.Runner = MagicMock
    fake_agents.trace = MagicMock
    fake_agents.ModelSettings = MagicMock

    fake_agents_mcp = types.ModuleType("agents.mcp")

    class _BoomServer:
        def __init__(self, *a, **k):
            raise RuntimeError(f"transport failed, key={SENTINEL}")

    fake_agents_mcp.MCPServerStreamableHttp = _BoomServer

    fake_openai = types.ModuleType("openai")
    fake_openai_types = types.ModuleType("openai.types")
    fake_openai_shared = types.ModuleType("openai.types.shared")
    fake_openai_shared.Reasoning = MagicMock

    for name, module in {
        "streamlit": fake_st,
        "dotenv": fake_dotenv,
        "agents": fake_agents,
        "agents.mcp": fake_agents_mcp,
        "openai": fake_openai,
        "openai.types": fake_openai_types,
        "openai.types.shared": fake_openai_shared,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_process_message_never_leaks_exception_secret(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    errors: list[str] = []
    _install_fake_modules(monkeypatch, errors)

    spec = importlib.util.spec_from_file_location("omi_example_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = asyncio.run(
        module.process_message_with_agent([{"role": "user", "content": "hello"}], "omi_mcp_real_key")
    )
    assert result == ("An error occurred while trying to get a response.", [])

    out = capsys.readouterr()
    assert SENTINEL not in out.out
    assert SENTINEL not in out.err
    for msg in errors:
        assert SENTINEL not in msg
