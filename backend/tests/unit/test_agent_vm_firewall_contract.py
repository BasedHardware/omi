"""Hermetic contract tests for agent VM network exposure controls (#7326)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
FIREWALL_IAC = REPO_ROOT / "backend" / "charts" / "agent-vm-firewall" / "firewall-rule.yaml"
AGENT_RS = REPO_ROOT / "desktop" / "macos" / "Backend-Rust" / "src" / "routes" / "agent.rs"


def _load_firewall_rules() -> list[dict]:
    return yaml.safe_load(FIREWALL_IAC.read_text())["firewallRules"]


def _rule(name: str) -> dict:
    matches = [rule for rule in _load_firewall_rules() if rule["name"] == name]
    assert len(matches) == 1, f"expected exactly one firewall rule named {name}"
    return matches[0]


def _denies_tcp_8080(rule: dict) -> bool:
    return any(entry.get("protocol") == "tcp" and "8080" in (entry.get("ports") or []) for entry in rule["rules"])


def test_firewall_iac_allows_private_8080_before_public_deny_for_omi_agent_vm_tag():
    allow = _rule("omi-agent-vm-allow-private-8080")
    deny = _rule("omi-agent-vm-deny-public-8080")

    assert allow["action"] == "ALLOW"
    assert allow["direction"] == "INGRESS"
    assert set(allow["sourceRanges"]) >= {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"}
    assert allow["targetTags"] == ["omi-agent-vm"]
    assert _denies_tcp_8080(allow), "private firewall IaC must allow tcp:8080 from private ranges"

    assert deny["action"] == "DENY"
    assert deny["direction"] == "INGRESS"
    assert "0.0.0.0/0" in deny["sourceRanges"]
    assert deny["targetTags"] == ["omi-agent-vm"]
    assert _denies_tcp_8080(deny), "firewall IaC must deny tcp:8080 from the public internet"

    assert allow["priority"] < deny["priority"], "private allow must outrank the 0.0.0.0/0 deny"


def _provision_insert_body_source() -> str:
    source = AGENT_RS.read_text()
    body_fn = source.split("fn build_gce_vm_insert_body", 1)[1]
    return body_fn.split("\n/// Create a GCE VM", 1)[0]


def test_provision_rust_contract_test_guards_public_ip_exposure():
    """Provision payload contract lives in agent.rs — keep IaC and code linked."""
    source = AGENT_RS.read_text()
    insert_body = _provision_insert_body_source()

    assert "fn build_gce_vm_insert_body" in source
    assert "contract_create_gce_vm_provision_json_has_no_public_nat" in source
    assert "contract_agent_vm_ip_uses_private_network_ip" in source
    assert '"items": ["omi-agent-vm"]' in insert_body
    assert "ONE_TO_ONE_NAT" not in insert_body
    assert "accessConfigs" not in insert_body


@pytest.mark.parametrize(
    "needle",
    [
        "natIP",
        "ONE_TO_ONE_NAT",
        "External NAT",
        "accessConfigs",
    ],
)
def test_provision_fixture_json_has_no_public_ip_fields(needle: str):
    """Serialized GCE insert body must not request or embed public IP fields."""
    fixture = {
        "name": "omi-agent-contract",
        "machineType": "zones/us-central1-a/machineTypes/e2-small",
        "networkInterfaces": [{"network": "global/networks/default"}],
        "tags": {"items": ["omi-agent-vm"]},
    }
    serialized = json.dumps(fixture)
    assert needle not in serialized
