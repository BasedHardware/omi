"""Hermetic contract tests for agent VM network exposure controls (#7326).

Phase 1 keeps public NAT and gates firewall apply. These tests lock the prepare
surface: firewall-tag on provision, deferred IaC shape, and apply refuse-by-default.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
FIREWALL_IAC = REPO_ROOT / "backend" / "charts" / "agent-vm-firewall" / "firewall-rule.yaml"
APPLY_SCRIPT = REPO_ROOT / "backend" / "scripts" / "apply-agent-vm-firewall.sh"
AGENT_RS = REPO_ROOT / "desktop" / "macos" / "Backend-Rust" / "src" / "routes" / "agent.rs"


def _load_firewall_doc() -> dict:
    return yaml.safe_load(FIREWALL_IAC.read_text())


def _load_firewall_rules() -> list[dict]:
    return _load_firewall_doc()["firewallRules"]


def _rule(name: str) -> dict:
    matches = [rule for rule in _load_firewall_rules() if rule["name"] == name]
    assert len(matches) == 1, f"expected exactly one firewall rule named {name}"
    return matches[0]


def _has_tcp_8080(rule: dict) -> bool:
    return any(entry.get("protocol") == "tcp" and "8080" in (entry.get("ports") or []) for entry in rule["rules"])


def test_firewall_iac_is_deferred_phase3_and_apply_disabled():
    doc = _load_firewall_doc()
    assert doc.get("applyEnabled") is False
    assert doc.get("phase") == 3


def test_firewall_iac_allows_private_8080_before_public_deny_for_omi_agent_vm_tag():
    allow = _rule("omi-agent-vm-allow-private-8080")
    deny = _rule("omi-agent-vm-deny-public-8080")

    assert allow["action"] == "ALLOW"
    assert allow["direction"] == "INGRESS"
    assert set(allow["sourceRanges"]) >= {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"}
    assert allow["targetTags"] == ["omi-agent-vm"]
    assert _has_tcp_8080(allow), "private firewall IaC must allow tcp:8080 from private ranges"

    assert deny["action"] == "DENY"
    assert deny["direction"] == "INGRESS"
    assert "0.0.0.0/0" in deny["sourceRanges"]
    assert deny["targetTags"] == ["omi-agent-vm"]
    assert _has_tcp_8080(deny), "firewall IaC must deny tcp:8080 from the public internet"

    assert allow["priority"] < deny["priority"], "private allow must outrank the 0.0.0.0/0 deny"


def test_apply_script_refuses_without_phase3_gate():
    env = os.environ.copy()
    env.pop("AGENT_VM_FIREWALL_APPLY_PHASE3", None)
    result = subprocess.run(
        ["bash", str(APPLY_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 1
    assert "REFUSED" in result.stderr
    assert "PHASE3" in result.stderr or "phase-3" in result.stderr.lower()


def _provision_insert_body_source() -> str:
    source = AGENT_RS.read_text()
    body_fn = source.split("fn build_gce_vm_insert_body", 1)[1]
    return body_fn.split("\n/// Create a GCE VM", 1)[0]


def test_provision_keeps_public_nat_and_firewall_tag():
    """Phase 1: public NAT stays; VMs stay tagged for a later cutover."""
    source = AGENT_RS.read_text()
    insert_body = _provision_insert_body_source()

    assert "fn build_gce_vm_insert_body" in source
    assert "contract_create_gce_vm_provision_json_keeps_public_nat_and_firewall_tag" in source
    assert "contract_agent_vm_ip_uses_public_nat_ip" in source
    assert '"items": ["omi-agent-vm"]' in insert_body
    assert "ONE_TO_ONE_NAT" in insert_body
    assert "accessConfigs" in insert_body


def test_apply_script_update_path_omits_immutable_flags():
    """Static tripwire: gcloud firewall-rules update must not receive create-only flags.

    --action, --direction, and --network are immutable after creation.
    Passing them to update makes the script non-idempotent - it fails instead of
    refreshing an existing rule during cutover.
    """
    source = APPLY_SCRIPT.read_text()

    # The update invocation line must not carry immutable flags.
    update_line = next((ln for ln in source.splitlines() if "firewall-rules update" in ln), None)
    assert update_line, "expected a firewall-rules update invocation"
    for flag in ("--action", "--direction", "--network"):
        assert flag not in update_line, f"firewall-rules update must not receive immutable flag {flag}"

    # The create invocation block (create line + continuation lines) must carry them.
    create_idx = next((i for i, ln in enumerate(source.splitlines()) if "firewall-rules create" in ln), None)
    assert create_idx is not None, "expected a firewall-rules create invocation"
    create_block = "\n".join(source.splitlines()[create_idx : create_idx + 6])
    for flag in ("--action", "--direction", "--network"):
        assert flag in create_block, f"firewall-rules create must receive {flag}"
