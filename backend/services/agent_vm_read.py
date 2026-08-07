"""Shared Agent VM status/read decisions for request paths.

Firestore ``agentVm.status`` is a cache. Desktop status, tools status, and
proxy demotion must agree on when that cache is safe to present as ready
versus when the fenced reconciler must take over.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from services.agent_vm_lifecycle import reconcile_requested


def reconcile_lease_active(vm: Mapping[str, Any], now: float | None = None) -> bool:
    reconcile = vm.get("reconcile")
    lease = reconcile.get("lease") if isinstance(reconcile, Mapping) else None
    if not isinstance(lease, Mapping):
        return False
    return float(lease.get("expiresAt", 0) or 0) > (time.time() if now is None else now)


def reconcile_in_progress(vm: Mapping[str, Any], now: float | None = None) -> bool:
    """True when status/read paths must defer to the fenced reconciler."""
    return reconcile_requested(vm, now) or reconcile_lease_active(vm, now)


def demoted_updating_vm(vm: Mapping[str, Any]) -> dict[str, Any]:
    """Client-facing view of a VM that is no longer safe to treat as ready."""
    return {**dict(vm), "status": "updating", "ip": None}


@dataclass(frozen=True)
class AgentVmProviderObservation:
    """Result of a request-path GCE instance lookup.

    ``not_found`` is a provider-confirmed 404. ``unknown`` is an API/network
    blip and must never erase Firestore ownership. ``running`` / ``stopped`` /
    ``other`` are live instance states.
    """

    kind: str
    gce_status: str | None = None


@dataclass(frozen=True)
class AgentVmReadDecision:
    """Shared status/read decision for desktop, tools, and proxy paths."""

    client_status: str
    queue_start: bool
    preserve_owner: bool
    clear_cached_ip: bool = False


def classify_provider_observation(
    *,
    gce_status: str | None = None,
    probe_failed: bool = False,
) -> AgentVmProviderObservation:
    """Classify a GCE probe without mutating owner state."""
    if probe_failed:
        return AgentVmProviderObservation(kind="unknown")
    normalized = str(gce_status or "").upper()
    if normalized == "NOT_FOUND":
        return AgentVmProviderObservation(kind="not_found", gce_status="NOT_FOUND")
    if normalized in {"TERMINATED", "STOPPED"}:
        return AgentVmProviderObservation(kind="stopped", gce_status=normalized)
    if normalized == "RUNNING":
        return AgentVmProviderObservation(kind="running", gce_status="RUNNING")
    if not normalized:
        return AgentVmProviderObservation(kind="unknown")
    return AgentVmProviderObservation(kind="other", gce_status=normalized)


def decide_agent_vm_read(
    vm: Mapping[str, Any],
    observation: AgentVmProviderObservation | None = None,
    *,
    now: float | None = None,
    usable_cached_ip: bool | None = None,
) -> AgentVmReadDecision:
    """Decide how status/read paths present a Firestore agentVm record.

    Behavior contract:
    - Reconciler already owns the record → demote to ``updating``, do not probe
      demand again from this helper (callers skip provider lookups first).
    - Provider ``NOT_FOUND`` → demote to ``updating`` and queue reconciler
      demand so the fenced job can mark ``missing`` and eventually clear.
    - Provider API blip (``unknown``) → preserve the owner pointer and status.
    - Provider running with a healthy ready cache → leave unchanged.
    """
    stored = str(vm.get("status") or "provisioning")
    if reconcile_in_progress(vm, now):
        return AgentVmReadDecision(
            client_status="updating",
            queue_start=False,
            preserve_owner=True,
            clear_cached_ip=True,
        )
    if observation is None:
        if stored == "ready":
            return AgentVmReadDecision(
                client_status="ready",
                queue_start=False,
                preserve_owner=True,
                clear_cached_ip=False,
            )
        return AgentVmReadDecision(
            client_status=stored,
            queue_start=False,
            preserve_owner=True,
            clear_cached_ip=False,
        )
    if observation.kind == "unknown":
        return AgentVmReadDecision(
            client_status=stored,
            queue_start=False,
            preserve_owner=True,
            clear_cached_ip=False,
        )
    if observation.kind == "not_found":
        return AgentVmReadDecision(
            client_status="updating",
            queue_start=True,
            preserve_owner=True,
            clear_cached_ip=True,
        )
    if observation.kind == "stopped":
        return AgentVmReadDecision(
            client_status="updating",
            queue_start=True,
            preserve_owner=True,
            clear_cached_ip=True,
        )
    if observation.kind == "running":
        needs_repair = stored in {"error", "stopped"} or usable_cached_ip is False
        if needs_repair:
            return AgentVmReadDecision(
                client_status="updating",
                queue_start=True,
                preserve_owner=True,
                clear_cached_ip=True,
            )
        return AgentVmReadDecision(
            client_status=stored,
            queue_start=False,
            preserve_owner=True,
            clear_cached_ip=False,
        )
    return AgentVmReadDecision(
        client_status=stored,
        queue_start=False,
        preserve_owner=True,
        clear_cached_ip=False,
    )


def apply_agent_vm_read_decision(vm: Mapping[str, Any], decision: AgentVmReadDecision) -> dict[str, Any]:
    """Materialize the client-facing VM view for a read decision."""
    if decision.client_status == "updating" and decision.clear_cached_ip:
        return demoted_updating_vm(vm)
    return {**dict(vm), "status": decision.client_status}


__all__ = [
    "AgentVmProviderObservation",
    "AgentVmReadDecision",
    "apply_agent_vm_read_decision",
    "classify_provider_observation",
    "decide_agent_vm_read",
    "demoted_updating_vm",
    "reconcile_in_progress",
    "reconcile_lease_active",
]
