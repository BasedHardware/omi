"""Shared Agent VM status/read decisions for stale ready vs provider state."""

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


def test_ready_plus_missing_instance_demotes_and_queues_reprovision_demand():
    observation = classify_provider_observation(gce_status="NOT_FOUND")
    decision = decide_agent_vm_read(READY_VM, observation)

    assert observation.kind == "not_found"
    assert decision.client_status == "updating"
    assert decision.queue_start is True
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
    assert decision.queue_start is False
    assert decision.preserve_owner is True
    assert apply_agent_vm_read_decision(READY_VM, decision)["status"] == "ready"
    assert apply_agent_vm_read_decision(READY_VM, decision)["ip"] == "34.1.2.3"


def test_ready_plus_running_instance_is_unchanged():
    observation = classify_provider_observation(gce_status="RUNNING")
    decision = decide_agent_vm_read(READY_VM, observation, usable_cached_ip=True)

    assert observation.kind == "running"
    assert decision.client_status == "ready"
    assert decision.queue_start is False
    assert decision.preserve_owner is True
    assert apply_agent_vm_read_decision(READY_VM, decision) == dict(READY_VM)


def test_missing_reconcile_state_demotes_without_extra_demand():
    vm = {
        **READY_VM,
        "reconcile": {"state": "missing", "missingSince": 1.0},
    }
    decision = decide_agent_vm_read(vm)

    assert decision.client_status == "updating"
    assert decision.queue_start is False
    assert apply_agent_vm_read_decision(vm, decision)["ip"] is None
