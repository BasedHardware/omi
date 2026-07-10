from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_mcp_oauth_deploy_contract.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_mcp_oauth_deploy_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_prod_mcp_oauth_deploy_contract_is_wired():
    checker = load_checker()
    assert checker.validate_mcp_oauth_deploy_contract() == []


def test_live_env_consistency_rejects_drift(monkeypatch):
    checker = load_checker()
    monkeypatch.setenv(
        "MCP_OAUTH_CLIENTS_JSON",
        '{"omi-claude-prod":{"name":"Claude stale","allowed_redirect_uris":["https://stale.example/callback"]}}',
    )
    monkeypatch.setenv("MCP_OAUTH_CLAUDE_CLIENT_ID", "omi-claude-prod")
    monkeypatch.setenv("MCP_OAUTH_CLAUDE_CLIENT_NAME", "Claude")
    monkeypatch.setenv("MCP_OAUTH_CLAUDE_REDIRECT_URIS", "https://claude.ai/api/mcp/auth_callback")

    errors = checker._validate_live_env_consistency()

    assert "MCP_OAUTH_CLIENTS_JSON Claude name differs from MCP_OAUTH_CLAUDE_CLIENT_NAME" in errors
    assert "MCP_OAUTH_CLIENTS_JSON Claude redirect URIs differ from MCP_OAUTH_CLAUDE_REDIRECT_URIS" in errors


def test_live_env_consistency_accepts_matching_claude_entry(monkeypatch):
    checker = load_checker()
    monkeypatch.setenv(
        "MCP_OAUTH_CLIENTS_JSON",
        '{"omi-claude-prod":{"name":"Claude","allowed_redirect_uris":["https://claude.ai/api/mcp/auth_callback"]}}',
    )
    monkeypatch.setenv("MCP_OAUTH_CLAUDE_CLIENT_ID", "omi-claude-prod")
    monkeypatch.setenv("MCP_OAUTH_CLAUDE_CLIENT_NAME", "Claude")
    monkeypatch.setenv("MCP_OAUTH_CLAUDE_REDIRECT_URIS", "https://claude.ai/api/mcp/auth_callback")

    assert checker._validate_live_env_consistency() == []
