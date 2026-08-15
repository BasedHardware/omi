"""Hermetic source contracts for agent VM /health auth (#7326 phase 1).

Behavioral coverage for provision NAT/tag lives in `test_desktop_agent_vm.py`
and `test_agent_vm_firewall_contract.py`. This file is a static tripwire: it
would have caught shipping `/health` without auth, or callers that still hit
`/health` without credentials.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_VM_MAIN = REPO_ROOT / "backend" / "agent_vm" / "main.py"
AGENT_PROXY = REPO_ROOT / "backend" / "agent-proxy" / "main.py"
AGENT_SYNC = REPO_ROOT / "desktop" / "macos" / "Desktop" / "Sources" / "AgentSyncService.swift"
AGENT_VM_SERVICE = REPO_ROOT / "desktop" / "macos" / "Desktop" / "Sources" / "AgentVMService.swift"


def _health_handler_block(source: str) -> str:
    match = re.search(
        r'@app\.get\("/health"\).*?async def health\(request: Request\).*?:\n(?P<body>.*?)(?=\n@app\.|\Z)',
        source,
        flags=re.DOTALL,
    )
    assert match, "agent_vm/main.py must define the /health HTTP handler"
    return match.group("body")


def test_agent_vm_health_requires_auth_before_ok_response():
    source = AGENT_VM_MAIN.read_text()
    body = _health_handler_block(source)
    assert "runtime.require_auth(request)" in body
    assert '"databaseReady": runtime.db is not None' in body
    assert body.index("runtime.require_auth(request)") < body.index("return {")
    assert "no auth" not in body.lower()


def test_agent_proxy_sends_bearer_on_vm_health_checks():
    source = AGENT_PROXY.read_text()
    assert 'headers = {"Authorization": f"Bearer {auth_token}"}' in source
    assert 'client.get(f"http://{vm_ip}:8080/health", headers=headers)' in source
    # Fast-path readiness probe in agent_ws also authenticates.
    assert 'headers = {"Authorization": f"Bearer {vm_token}"} if vm_token else {}' in source


def test_desktop_health_callers_send_auth():
    sync_source = AGENT_SYNC.read_text()
    vm_source = AGENT_VM_SERVICE.read_text()
    for source in (sync_source, vm_source):
        assert r"health?token=\(authToken)" in source
        assert 'forHTTPHeaderField: "Authorization"' in source
        assert r"Bearer \(authToken)" in source
