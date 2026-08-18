"""Shared Agent VM status/read decisions for stale ready vs provider state.

Read decisions are observational only: no field of ``AgentVmReadDecision`` may
queue reconciler start demand (wake-on-open retired 2026-08-17; measured 135
status-driven restart attempts in 24h against zero successful sessions).
"""

import dataclasses


from services.agent_vm_read import (
    apply_agent_vm_read_decision,
    classify_provider_observation,
    decide_agent_vm_read,
)

READY_VM = {
    "vmName": "omi-agent-user",
    "zone": "us-central1-a",
    "ip": "34.1.2.3",
    "authToken": "token",
    "status": "ready",
}


def test_ready_plus_missing_instance_demotes_and_records_missing_without_demand():
    observation = classify_provider_observation(gce_status="NOT_FOUND")
    decision = decide_agent_vm_read(READY_VM, observation)

    assert observation.kind == "not_found"
    assert decision.client_status == "updating"
    assert decision.record_missing is True
    assert decision.preserve_owner is True
    assert apply_agent_vm_read_decision(READY_VM, decision) == {
        **READY_VM,
        "status": "updating",
        "ip": None,
    }


def test_ready_plus_api_error_preserves_owner_and_ready_status():
    observation = classify_provider_observation(probe_failed=True)
    decision = decide_agent_vm_read(READY_VM, observation)

    assert observation.kind == "unknown"
    assert decision.client_status == "ready"
    assert decision.preserve_owner is True
    assert apply_agent_vm_read_decision(READY_VM, decision)["status"] == "ready"
    assert apply_agent_vm_read_decision(READY_VM, decision)["ip"] == "34.1.2.3"


def test_ready_plus_running_instance_is_unchanged():
    observation = classify_provider_observation(gce_status="RUNNING")
    decision = decide_agent_vm_read(READY_VM, observation, usable_cached_ip=True)

    assert observation.kind == "running"
    assert decision.client_status == "ready"
    assert decision.preserve_owner is True
    assert apply_agent_vm_read_decision(READY_VM, decision) == dict(READY_VM)


def test_ready_plus_transitional_gce_state_is_demoted():
    observation = classify_provider_observation(gce_status="PROVISIONING")
    decision = decide_agent_vm_read(READY_VM, observation)

    assert observation.kind == "other"
    assert decision.client_status == "updating"
    assert apply_agent_vm_read_decision(READY_VM, decision)["ip"] is None


def test_ready_with_unusable_cached_ip_demotes_without_provider_probe():
    decision = decide_agent_vm_read(READY_VM, usable_cached_ip=False)

    assert decision.client_status == "updating"


def test_missing_reconcile_state_demotes_without_extra_demand():
    vm = {
        **READY_VM,
        "reconcile": {"state": "missing", "missingSince": 1.0},
    }
    decision = decide_agent_vm_read(vm)

    assert decision.client_status == "updating"
    assert apply_agent_vm_read_decision(vm, decision)["ip"] is None


def test_read_decision_has_no_demand_channel():
    """Wake-on-open stays retired: read decisions carry no start-demand field."""
    from services.agent_vm_read import AgentVmReadDecision

    field_names = {field.name for field in dataclasses.fields(AgentVmReadDecision)}
    assert field_names == {"client_status", "preserve_owner", "clear_cached_ip", "record_missing"}
