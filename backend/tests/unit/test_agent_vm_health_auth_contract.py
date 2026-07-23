"""Hermetic source contracts for agent VM /health auth (#7326 phase 1).

Behavioral coverage for provision NAT/tag lives in Rust `agent::contract_tests`.
This file is a static tripwire: it would have caught shipping `/health` without
`verifyAuth`, or callers that still hit `/health` without credentials.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_MJS = REPO_ROOT / "desktop" / "macos" / "agent-cloud" / "agent.mjs"
AGENT_PROXY = REPO_ROOT / "backend" / "agent-proxy" / "main.py"
AGENT_SYNC = REPO_ROOT / "desktop" / "macos" / "Desktop" / "Sources" / "AgentSyncService.swift"
AGENT_VM = REPO_ROOT / "desktop" / "macos" / "Desktop" / "Sources" / "AgentVMService.swift"


def _health_handler_block(source: str) -> str:
    match = re.search(
        r"// Health check.*?if \(\(req\.url === \"/health\".*?\n(?P<body>.*?)\n    // Database upload",
        source,
        flags=re.DOTALL,
    )
    assert match, "agent.mjs must define the /health HTTP handler"
    return match.group("body")


def test_agent_mjs_health_requires_verify_auth_before_ok_response():
    source = AGENT_MJS.read_text()
    body = _health_handler_block(source)
    assert "verifyAuth(req)" in body
    assert 'writeHead(401' in body
    assert 'writeHead(200' in body
    assert body.index("verifyAuth(req)") < body.index('writeHead(200')
    assert "no auth" not in body.lower()


def test_agent_proxy_sends_bearer_on_vm_health_checks():
    source = AGENT_PROXY.read_text()
    assert 'headers = {"Authorization": f"Bearer {auth_token}"}' in source
    assert 'client.get(f"http://{vm_ip}:8080/health", headers=headers)' in source
    # Fast-path readiness probe in agent_ws also authenticates.
    assert 'headers = {"Authorization": f"Bearer {vm_token}"} if vm_token else {}' in source


def test_desktop_health_callers_send_auth():
    sync_source = AGENT_SYNC.read_text()
    vm_source = AGENT_VM.read_text()
    for source in (sync_source, vm_source):
        assert r"health?token=\(authToken)" in source
        assert 'forHTTPHeaderField: "Authorization"' in source
        assert r"Bearer \(authToken)" in source
