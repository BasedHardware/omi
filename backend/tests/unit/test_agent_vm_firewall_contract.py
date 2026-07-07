"""Hermetic contract tests for agent VM network exposure controls (#7326)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
FIREWALL_IAC = REPO_ROOT / "backend" / "charts" / "agent-vm-firewall" / "firewall-rule.yaml"
AGENT_RS = REPO_ROOT / "desktop" / "macos" / "Backend-Rust" / "src" / "routes" / "agent.rs"


def _load_firewall_contract() -> dict:
    return yaml.safe_load(FIREWALL_IAC.read_text())


def test_firewall_iac_denies_public_8080_for_omi_agent_vm_tag():
    rule = _load_firewall_contract()

    assert rule["action"] == "DENY"
    assert rule["direction"] == "INGRESS"
    assert "0.0.0.0/0" in rule["sourceRanges"]
    assert rule["targetTags"] == ["omi-agent-vm"]

    denied_tcp_8080 = any(
        entry.get("protocol") == "tcp" and "8080" in (entry.get("ports") or []) for entry in rule["rules"]
    )
    assert denied_tcp_8080, "firewall IaC must deny tcp:8080 from the public internet"


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
