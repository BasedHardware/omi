"""Synthetic local memory product scenario fixtures and seed/reset tooling.

These fixtures are for the local emulator dev harness only. They are safe to
commit, use deterministic synthetic IDs/content, and intentionally cannot choose
evidence labels. Any local report/session metadata emitted by this module is
hard-coded to ``LOCAL_EMULATOR_DEV`` and ``activation_eligible=false``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal, Mapping, Sequence
from urllib.parse import quote

from . import config, safety

SCHEMA_VERSION = 1
EVIDENCE_CLASS = "LOCAL_EMULATOR_DEV"
ACTIVATION_ELIGIBLE = False
WATERMARK = "NOT_ACTIVATION_EVIDENCE"
DEFAULT_LOCAL_USER_ID = "local_default_user"
ALICE_USER_ID = "alice"
BOB_USER_ID = "bob"
# Short-term seeds must stay visible across long local-dev sessions.
SHORT_TERM_EXPIRES_AT = "2027-12-31T23:59:59Z"
SYNTHETIC_SOURCE_VERSION = "memory-local-synthetic-source-1"
AUTH_UID_MANIFEST = "canonical-auth-uids.json"
LOCAL_DEV_PROJECT_ID = safety.DEFAULT_LOCAL_FIREBASE_PROJECT_ID
LOCAL_DEV_DATABASE_ID = safety.DEFAULT_FIRESTORE_DATABASE_ID
GLOBAL_READ_GATE_PATH = "memory_control/global_read_gate"
WRITE_CONVERGENCE_GATE_PATH = "memory_control/write_convergence_gate"

RouteDecision = Literal["disabled", "legacy_primary", "memory_read", "fail_closed"]


@dataclass(frozen=True)
class DeterministicContext:
    now: str
    run_id: str
    cursor_secret: str
    cursor_policy_version: str
    cursor_secret_version: str
    cursor_ttl_seconds: int
    ids: Mapping[str, str]
    cursors: Mapping[str, str]


@dataclass(frozen=True)
class ScenarioUser:
    uid: str
    email: str
    display_name: str
    password: str


@dataclass(frozen=True)
class FirestoreSeed:
    path: str
    data: Mapping[str, object]
    protected: bool = False


@dataclass(frozen=True)
class RedisSeed:
    key: str
    value: str


@dataclass(frozen=True)
class FileSeed:
    relative_path: str
    content: str


@dataclass(frozen=True)
class RequestCase:
    case_id: str
    method: str
    path: str
    query: Mapping[str, str] = field(default_factory=dict)
    authenticated_user: str = ALICE_USER_ID
    expected_status: int = 200
    expected_route_decision: RouteDecision = "memory_read"
    expected_memory_ids: tuple[str, ...] = ()
    expected_read_paths: tuple[str, ...] = ()
    expected_no_write: bool = True
    expected_fail_closed_reason: str | None = None


@dataclass(frozen=True)
class ExpectedProtectedCollectionChange:
    collection_path: str
    allowed_changes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpectedFailClosedBehavior:
    fail_closed: bool
    reason: str | None = None
    no_legacy_fallback: bool = True
    no_cross_user_disclosure: bool = True
    no_memory_writes: bool = True


@dataclass(frozen=True)
class LocalReportMetadata:
    evidence_class: str = EVIDENCE_CLASS
    activation_eligible: bool = ACTIVATION_ELIGIBLE
    watermark: str = WATERMARK
    firebase_project_id: str = LOCAL_DEV_PROJECT_ID
    firestore_database_id: str = LOCAL_DEV_DATABASE_ID


@dataclass(frozen=True)
class MemoryScenario:
    schema_version: int
    scenario_id: str
    description: str
    deterministic: DeterministicContext
    users: tuple[ScenarioUser, ...]
    selected_user: str
    local_flags: Mapping[str, object]
    auth_seed: tuple[Mapping[str, object], ...]
    profile_seed: tuple[FirestoreSeed, ...]
    firestore_seed: tuple[FirestoreSeed, ...]
    redis_seed: tuple[RedisSeed, ...]
    file_seed: tuple[FileSeed, ...]
    request_cases: tuple[RequestCase, ...]
    expected_protected_collection_changes: tuple[ExpectedProtectedCollectionChange, ...]
    expected_fail_closed: ExpectedFailClosedBehavior
    report_metadata: LocalReportMetadata = field(default_factory=LocalReportMetadata)


@dataclass(frozen=True)
class SeedOperation:
    kind: Literal["auth", "firestore", "redis", "file", "metadata"]
    action: Literal["upsert", "delete", "write"]
    target: str
    payload: Mapping[str, object] | str | None = None
    protected: bool = False


@dataclass(frozen=True)
class SeedManifest:
    schema_version: int
    scenario_id: str
    scenario_digest: str
    generated_at: str
    dry_run: bool
    applied: bool
    emulator_available: Mapping[str, bool]
    report_metadata: LocalReportMetadata
    operations: tuple[SeedOperation, ...]


def _iso(ts: str) -> str:
    return ts


def _user(uid: str, name: str) -> ScenarioUser:
    return ScenarioUser(
        uid=uid,
        email=f"{uid}@local.omi.invalid",
        display_name=f"Synthetic {name}",
        password=f"{uid}-local-password-030",
    )


USERS = (_user(DEFAULT_LOCAL_USER_ID, "Default"), _user(ALICE_USER_ID, "Alice"), _user(BOB_USER_ID, "Bob"))


def _auth_seed(users: Sequence[ScenarioUser]) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            "localId": user.uid,
            "email": user.email,
            "displayName": user.display_name,
            "password": user.password,
            "emailVerified": True,
            "disabled": False,
        }
        for user in users
    )


def _profile_seeds(users: Sequence[ScenarioUser]) -> tuple[FirestoreSeed, ...]:
    return tuple(
        FirestoreSeed(
            path=f"users/{user.uid}",
            protected=True,
            data={
                "uid": user.uid,
                "email": user.email,
                "display_name": user.display_name,
                "synthetic": True,
                "local_harness": True,
                "created_by": "TICKET-030-memory-scenario-fixtures",
            },
        )
        for user in users
    )


def _clock() -> DeterministicContext:
    return DeterministicContext(
        now="2026-01-15T12:00:00Z",
        run_id="memory-local-synthetic-run-030",
        cursor_secret="synthetic-memory-local-cursor-secret-030",
        cursor_policy_version="memory-v3-cursor-policy-local-030",
        cursor_secret_version="local-synthetic-030",
        cursor_ttl_seconds=600,
        ids={
            "alice_short_active": "mem_alice_short_active_030",
            "alice_short_stale": "mem_alice_short_stale_030",
            "alice_short_demo": "mem_alice_short_demo_030",
            "alice_short_dentist": "mem_alice_short_dentist_030",
            "alice_short_grocery": "mem_alice_short_grocery_030",
            "alice_short_call_mom": "mem_alice_short_call_mom_030",
            "alice_short_pr_review": "mem_alice_short_pr_review_030",
            "alice_short_yoga": "mem_alice_short_yoga_030",
            "alice_short_presentation": "mem_alice_short_presentation_030",
            "alice_short_flights": "mem_alice_short_flights_030",
            "alice_long": "mem_alice_long_030",
            "alice_long_birthplace": "mem_alice_long_birthplace_030",
            "alice_long_partner": "mem_alice_long_partner_030",
            "alice_long_work": "mem_alice_long_work_030",
            "alice_long_tool_warp": "mem_alice_long_tool_warp_030",
            "alice_long_tool_obsidian": "mem_alice_long_tool_obsidian_030",
            "alice_long_pref_coffee": "mem_alice_long_pref_coffee_030",
            "alice_long_pref_sf": "mem_alice_long_pref_sf_030",
            "alice_long_family_sister": "mem_alice_long_family_sister_030",
            "alice_long_commit_rust": "mem_alice_long_commit_rust_030",
            "alice_long_health_running": "mem_alice_long_health_running_030",
            "alice_long_lang_spanish": "mem_alice_long_lang_spanish_030",
            "alice_long_pet": "mem_alice_long_pet_030",
            "alice_long_goal_marathon": "mem_alice_long_goal_marathon_030",
            "alice_long_edu": "mem_alice_long_edu_030",
            "alice_archive": "mem_alice_archive_030",
            "bob_long": "mem_bob_long_030",
            "kg_alice": "kg_alice_030",
            "kg_jordan": "kg_jordan_030",
            "kg_mia": "kg_mia_030",
            "kg_omi": "kg_omi_030",
            "kg_sf": "kg_sf_030",
            "kg_portland": "kg_portland_030",
            "kg_warp": "kg_warp_030",
            "kg_pixel": "kg_pixel_030",
            "projection_commit": "projection_commit_local_030",
            "source_commit": "source_commit_local_030",
        },
        cursors={
            "valid_start": "cursor_local_start_030",
            "malformed": "not-a-valid-memory-cursor",
            "cross_user_bob": "cursor_claims_bob_subject_synthetic_invalid_for_alice",
        },
    )


def _global_gate(*, enabled: bool, kill: bool = False) -> FirestoreSeed:
    return FirestoreSeed(
        path=GLOBAL_READ_GATE_PATH,
        protected=True,
        data={
            "route_scope": "get_v3_memories",
            "purpose": "memory_v3_runtime_enablement",
            "owner": "memory_platform_local_harness",
            "config_schema_version": 1,
            "memory_reads_enabled": enabled,
            "kill_switch_active": kill,
            "fixture_source": "TICKET-030-local-synthetic",
        },
    )


def _write_convergence() -> FirestoreSeed:
    return FirestoreSeed(
        path=WRITE_CONVERGENCE_GATE_PATH,
        protected=True,
        data={
            "route_scope": "get_v3_memories",
            "purpose": "memory_v3_write_convergence_gate",
            "owner": "memory_platform_local_harness",
            "config_schema_version": 1,
            "durable_outbox_enabled": True,
            "dual_write_projection_ready": True,
            "delete_convergence_ready": True,
            "idempotency_contract_ready": True,
        },
    )


def _control(uid: str, *, read: bool = True, default_grant: bool = True, archive: bool = False) -> FirestoreSeed:
    return FirestoreSeed(
        path=f"users/{uid}/memory_control/state",
        protected=True,
        data={
            "uid": uid,
            "schema_version": 1,
            "head_commit_id": "ledger_commit_local_030",
            "account_generation": 7,
            "source_generation": 1,
            "commit_sequence": 1,
            "mode": "read" if read else "off",
            "mode_epoch": 1,
            "cutover_epoch": 1 if read else 0,
            "fallback_projection_ready": read,
            "persistent_memory_writes_started": False,
            "decommission_reconciled": False,
            "writes_blocked": False,
            "stage_gates": {"shadow": "passed", "write": "passed", "read": "passed" if read else "blocked"},
            "grants": {"omi_chat": {"default_memory": default_grant, "archive": archive}},
        },
    )


def _projection_state(uid: str, ctx: DeterministicContext) -> FirestoreSeed:
    return FirestoreSeed(
        path=f"users/{uid}/v3_compatibility_projection/state",
        protected=True,
        data={
            "uid": uid,
            "account_generation": 7,
            "projection_generation": 3,
            "projection_commit_id": ctx.ids["projection_commit"],
            "source_commit_id": ctx.ids["source_commit"],
            "source_version": "memory-local-synthetic-source-1",
            "updated_at": ctx.now,
        },
    )


def _synthetic_conversation_id(memory_key: str) -> str:
    return f"conv_local_{memory_key}_030"


def _synthetic_evidence_id(memory_key: str) -> str:
    return f"ev_local_{memory_key}_030"


def _synthetic_memory_evidence(memory_key: str, content: str) -> dict[str, object]:
    """Structurally valid synthetic local-QA evidence for the dev harness.

    Self-referential (quote equals memory content; no seeded transcript or
    conversation document). Satisfies apply validation in the local emulator
    but is not transcript-grounded or production-grade authoritative evidence.
    """
    conversation_id = _synthetic_conversation_id(memory_key)
    return {
        "evidence_id": _synthetic_evidence_id(memory_key),
        "source_type": "conversation",
        "source_id": conversation_id,
        "source_version": SYNTHETIC_SOURCE_VERSION,
        "conversation_id": conversation_id,
        "artifact_refs": [],
        "artifact_preservation": "preserved",
        "quote_refs": [{"quote": content, "source_id": conversation_id}],
        "source_state": "active",
        "provenance_visibility": "visible",
        "redaction_status": "active",
        "encryption_or_redaction_status": "active",
    }


def _memory_evidence_doc(uid: str, memory_key: str, content: str) -> FirestoreSeed:
    """Firestore seed for synthetic local-QA evidence (see ``_synthetic_memory_evidence``)."""
    evidence = _synthetic_memory_evidence(memory_key, content)
    return FirestoreSeed(
        path=f"users/{uid}/memory_evidence/{evidence['evidence_id']}",
        protected=True,
        data=evidence,
    )


def _append_sourced_memory(
    seeds: list[FirestoreSeed],
    uid: str,
    memory_key: str,
    memory_id: str,
    tier: str,
    content: str,
    captured: str,
    expires: str | None = None,
) -> None:
    """Append a memory_items doc plus matching synthetic local-QA evidence doc."""
    seeds.append(_memory_doc(uid, memory_id, tier, content, captured, expires, memory_key=memory_key))
    seeds.append(_memory_evidence_doc(uid, memory_key, content))


def _memory_doc(
    uid: str,
    memory_id: str,
    tier: str,
    content: str,
    captured: str,
    expires: str | None = None,
    *,
    memory_key: str | None = None,
) -> FirestoreSeed:
    evidence_entries: list[dict[str, object]] = []
    if memory_key is not None:
        evidence_entries = [_synthetic_memory_evidence(memory_key, content)]
    data: dict[str, object] = {
        "memory_id": memory_id,
        "uid": uid,
        "canonical_memory_id": memory_id,
        "version": 1,
        "tier": tier,
        "status": "active",
        "processing_state": "processed",
        "content": content,
        "evidence": evidence_entries,
        "source_state": "active",
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": captured,
        "updated_at": captured,
        "ledger_commit_id": "ledger_commit_local_030" if tier == "long_term" else None,
        "ledger_sequence": 1 if tier == "long_term" else None,
        "item_revision": 1,
        "source_commit_id": "source_commit_local_030",
        "source_commit_sequence": 1,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "account_generation": 7,
    }
    if expires is not None:
        data["expires_at"] = expires
    return FirestoreSeed(path=f"users/{uid}/memory_items/{memory_id}", protected=True, data=data)


def _projection_item(
    uid: str,
    memory_id: str,
    content: str,
    created: str,
    *,
    archive: bool = False,
    category: str = "memory-local-synthetic",
) -> FirestoreSeed:
    return FirestoreSeed(
        path=f"users/{uid}/v3_compatibility_projection_items/{memory_id}",
        protected=True,
        data={
            "id": memory_id,
            "uid": uid,
            "content": content,
            "category": category,
            "visibility": "private",
            "created_at": created,
            "updated_at": created,
            "account_generation": 7,
            "projection_generation": 3,
            "projection_commit_id": "projection_commit_local_030",
            "source_commit_id": "source_commit_local_030",
            "source_version": "memory-local-synthetic-source-1",
            "tier": "archive" if archive else "default",
            "synthetic": True,
        },
    )


def _kg_node(uid: str, node_id: str, label: str, node_type: str, *, memory_ids: Sequence[str] = ()) -> FirestoreSeed:
    label_lower = label.lower()
    return FirestoreSeed(
        path=f"users/{uid}/knowledge_nodes/{node_id}",
        protected=True,
        data={
            "id": node_id,
            "label": label,
            "node_type": node_type,
            "aliases": [],
            "memory_ids": list(memory_ids),
            "created_at": "2026-01-10T09:00:00Z",
            "updated_at": "2026-01-10T09:00:00Z",
            "label_lower": label_lower,
            "aliases_lower": [],
        },
    )


def _kg_edge(
    uid: str, edge_id: str, source_id: str, target_id: str, label: str, *, memory_ids: Sequence[str] = ()
) -> FirestoreSeed:
    return FirestoreSeed(
        path=f"users/{uid}/knowledge_edges/{edge_id}",
        protected=True,
        data={
            "id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "label": label,
            "memory_ids": list(memory_ids),
            "created_at": "2026-01-10T09:00:00Z",
        },
    )


def _alice_default_memory_ids(ctx: DeterministicContext) -> tuple[str, ...]:
    short_keys = (
        "alice_short_active",
        "alice_short_demo",
        "alice_short_dentist",
        "alice_short_grocery",
        "alice_short_call_mom",
        "alice_short_pr_review",
    )
    long_keys = (
        "alice_long",
        "alice_long_birthplace",
        "alice_long_partner",
        "alice_long_work",
        "alice_long_tool_warp",
        "alice_long_tool_obsidian",
        "alice_long_pref_coffee",
        "alice_long_pref_sf",
        "alice_long_family_sister",
        "alice_long_commit_rust",
        "alice_long_health_running",
        "alice_long_lang_spanish",
        "alice_long_pet",
        "alice_long_goal_marathon",
        "alice_long_edu",
        "alice_short_yoga",
        "alice_short_presentation",
        "alice_short_flights",
    )
    return tuple(ctx.ids[key] for key in (*short_keys, *long_keys))


def _alice_knowledge_graph_seeds(uid: str, ctx: DeterministicContext) -> list[FirestoreSeed]:
    ids = ctx.ids
    long_work = ids["alice_long_work"]
    long_partner = ids["alice_long_partner"]
    long_sf = ids["alice_long_pref_sf"]
    long_warp = ids["alice_long_tool_warp"]
    long_pet = ids["alice_long_pet"]
    long_sister = ids["alice_long_family_sister"]
    long_birthplace = ids["alice_long_birthplace"]
    return [
        _kg_node(uid, ids["kg_alice"], "Alice", "person"),
        _kg_node(uid, ids["kg_jordan"], "Jordan Chen", "person", memory_ids=(long_partner,)),
        _kg_node(uid, ids["kg_mia"], "Mia", "person", memory_ids=(long_sister,)),
        _kg_node(uid, ids["kg_omi"], "Omi", "organization", memory_ids=(long_work,)),
        _kg_node(uid, ids["kg_sf"], "San Francisco", "place", memory_ids=(long_sf,)),
        _kg_node(uid, ids["kg_portland"], "Portland", "place", memory_ids=(long_birthplace,)),
        _kg_node(uid, ids["kg_warp"], "Warp", "thing", memory_ids=(long_warp,)),
        _kg_node(uid, ids["kg_pixel"], "Pixel", "thing", memory_ids=(long_pet,)),
        _kg_edge(uid, "kg_edge_alice_lives_sf_030", ids["kg_alice"], ids["kg_sf"], "lives_in", memory_ids=(long_sf,)),
        _kg_edge(
            uid, "kg_edge_alice_works_omi_030", ids["kg_alice"], ids["kg_omi"], "works_at", memory_ids=(long_work,)
        ),
        _kg_edge(
            uid,
            "kg_edge_alice_partner_jordan_030",
            ids["kg_alice"],
            ids["kg_jordan"],
            "partner",
            memory_ids=(long_partner,),
        ),
        _kg_edge(
            uid, "kg_edge_alice_sister_mia_030", ids["kg_alice"], ids["kg_mia"], "sibling", memory_ids=(long_sister,)
        ),
        _kg_edge(uid, "kg_edge_alice_uses_warp_030", ids["kg_alice"], ids["kg_warp"], "uses", memory_ids=(long_warp,)),
        _kg_edge(uid, "kg_edge_alice_pet_pixel_030", ids["kg_alice"], ids["kg_pixel"], "owns", memory_ids=(long_pet,)),
        _kg_edge(
            uid,
            "kg_edge_alice_from_portland_030",
            ids["kg_alice"],
            ids["kg_portland"],
            "grew_up_in",
            memory_ids=(long_birthplace,),
        ),
    ]


def _base_firestore(
    ctx: DeterministicContext, *, global_enabled: bool = True, kill: bool = False
) -> list[FirestoreSeed]:
    uid = ALICE_USER_ID
    alice_short = "Alice has a synthetic local standup at 09:00 in the lab room."
    alice_long = "Alice prefers concise memory summaries for local QA."
    alice_archive = "Alice archived an old synthetic project codename: Blue Acorn."
    alice_stale = "Alice stale short memory that should not appear after expiry."
    bob_long = "Bob keeps a separate synthetic notebook for isolation checks."
    short_memories: tuple[tuple[str, str, str], ...] = (
        ("alice_short_active", alice_short, "2026-01-15T11:30:00Z"),
        (
            "alice_short_demo",
            "Alice is presenting the memory platform demo to the team on Friday at 14:00.",
            "2026-01-15T10:45:00Z",
        ),
        (
            "alice_short_dentist",
            "Alice has a dentist appointment on Thursday at 14:30 downtown.",
            "2026-01-15T09:15:00Z",
        ),
        (
            "alice_short_grocery",
            "Alice needs to pick up oat milk and espresso beans after work.",
            "2026-01-15T08:45:00Z",
        ),
        (
            "alice_short_call_mom",
            "Alice promised to call her mom this weekend about summer travel plans.",
            "2026-01-14T18:00:00Z",
        ),
        (
            "alice_short_pr_review",
            "Alice needs to review PR #482 for the canonical memory adapter before end of day.",
            "2026-01-14T16:00:00Z",
        ),
        ("alice_short_yoga", "Alice has yoga class Wednesday at 07:00 at Mission Yoga Studio.", "2026-01-13T06:30:00Z"),
        (
            "alice_short_presentation",
            "Alice is preparing slides for next week's product review on Brain Map UX.",
            "2026-01-12T13:20:00Z",
        ),
        (
            "alice_short_flights",
            "Alice should check her SFO to Seattle flight status before Friday's trip to visit Mia.",
            "2026-01-11T08:00:00Z",
        ),
    )
    promoted_short_to_long: tuple[tuple[str, str, str, str], ...] = (
        (
            "alice_short_yoga",
            "Alice has yoga class Wednesday at 07:00 at Mission Yoga Studio.",
            "2026-01-13T06:30:00Z",
            "commitments",
        ),
        (
            "alice_short_presentation",
            "Alice is preparing slides for next week's product review on Brain Map UX.",
            "2026-01-12T13:20:00Z",
            "work",
        ),
        (
            "alice_short_flights",
            "Alice should check her SFO to Seattle flight status before Friday's trip to visit Mia.",
            "2026-01-11T08:00:00Z",
            "travel",
        ),
    )
    long_memories: tuple[tuple[str, str, str, str], ...] = (
        ("alice_long", alice_long, "2026-01-10T09:00:00Z", "preferences"),
        (
            "alice_long_birthplace",
            "Alice grew up in Portland, Oregon and visits her parents there each winter.",
            "2024-11-03T10:00:00Z",
            "biographical",
        ),
        (
            "alice_long_partner",
            "Alice's partner is Jordan Chen; they have been together since 2019.",
            "2025-02-14T12:00:00Z",
            "relationships",
        ),
        (
            "alice_long_work",
            "Alice is a software engineer at Omi working on the memory platform and desktop sync.",
            "2025-08-01T09:00:00Z",
            "work",
        ),
        (
            "alice_long_tool_warp",
            "Alice uses Warp as her primary terminal on macOS for local development.",
            "2025-09-12T15:30:00Z",
            "tools",
        ),
        (
            "alice_long_tool_obsidian",
            "Alice keeps personal research notes in Obsidian with a daily journaling workflow.",
            "2025-10-02T08:45:00Z",
            "tools",
        ),
        (
            "alice_long_pref_coffee",
            "Alice prefers oat milk lattes with no sugar, usually from local cafes in the Mission.",
            "2025-05-20T07:30:00Z",
            "preferences",
        ),
        (
            "alice_long_pref_sf",
            "Alice lives in San Francisco's Mission District and bikes to work when weather allows.",
            "2025-01-08T18:00:00Z",
            "location",
        ),
        (
            "alice_long_family_sister",
            "Alice's younger sister Mia lives in Seattle and works in UX research.",
            "2025-03-22T19:00:00Z",
            "relationships",
        ),
        (
            "alice_long_commit_rust",
            "Alice is learning Rust to contribute to Omi's desktop backend components.",
            "2026-02-01T10:00:00Z",
            "commitments",
        ),
        (
            "alice_long_health_running",
            "Alice runs a 5K three times per week, usually along the Embarcadero.",
            "2025-07-15T06:00:00Z",
            "health",
        ),
        (
            "alice_long_lang_spanish",
            "Alice speaks conversational Spanish and is studying for professional fluency.",
            "2025-11-11T20:00:00Z",
            "skills",
        ),
        (
            "alice_long_pet",
            "Alice has a tabby cat named Pixel who often sits on her desk during standups.",
            "2025-04-18T21:00:00Z",
            "relationships",
        ),
        (
            "alice_long_goal_marathon",
            "Alice is training for the Oakland Marathon in fall 2026.",
            "2026-01-05T07:00:00Z",
            "commitments",
        ),
        (
            "alice_long_edu",
            "Alice earned a BS in Computer Science from the University of Washington in 2018.",
            "2024-09-01T12:00:00Z",
            "biographical",
        ),
    )
    seeds: list[FirestoreSeed] = [
        _global_gate(enabled=global_enabled, kill=kill),
        _write_convergence(),
        _control(ALICE_USER_ID, read=True, default_grant=True, archive=True),
        _control(BOB_USER_ID, read=True, default_grant=True, archive=False),
        _projection_state(ALICE_USER_ID, ctx),
        _projection_state(BOB_USER_ID, ctx),
        _memory_doc(
            ALICE_USER_ID,
            ctx.ids["alice_short_stale"],
            "short_term",
            alice_stale,
            "2026-01-01T11:30:00Z",
            "2026-01-02T11:30:00Z",
            memory_key="alice_short_stale",
        ),
        _memory_evidence_doc(ALICE_USER_ID, "alice_short_stale", alice_stale),
        _memory_doc(ALICE_USER_ID, ctx.ids["alice_archive"], "archive", alice_archive, "2025-12-01T08:00:00Z"),
        _memory_doc(BOB_USER_ID, ctx.ids["bob_long"], "long_term", bob_long, "2026-01-11T09:00:00Z"),
        _projection_item(
            ALICE_USER_ID,
            ctx.ids["alice_archive"],
            alice_archive,
            "2025-12-01T08:00:00Z",
            archive=True,
            category="archive",
        ),
        _projection_item(BOB_USER_ID, ctx.ids["bob_long"], bob_long, "2026-01-11T09:00:00Z", category="work"),
    ]
    for key, content, captured in short_memories:
        if any(key == promoted[0] for promoted in promoted_short_to_long):
            continue
        memory_id = ctx.ids[key]
        _append_sourced_memory(seeds, uid, key, memory_id, "short_term", content, captured, SHORT_TERM_EXPIRES_AT)
        seeds.append(_projection_item(uid, memory_id, content, captured, category="commitments"))
    for key, content, captured, category in promoted_short_to_long:
        memory_id = ctx.ids[key]
        _append_sourced_memory(seeds, uid, key, memory_id, "long_term", content, captured)
        seeds.append(_projection_item(uid, memory_id, content, captured, category=category))
    for key, content, captured, category in long_memories:
        memory_id = ctx.ids[key]
        _append_sourced_memory(seeds, uid, key, memory_id, "long_term", content, captured)
        seeds.append(_projection_item(uid, memory_id, content, captured, category=category))
    seeds.extend(_alice_knowledge_graph_seeds(uid, ctx))
    return seeds


def _local_flags(ctx: DeterministicContext, *, enabled: bool = True) -> Mapping[str, object]:
    return {
        "MEMORY_V3_GET_ENABLED": "true" if enabled else "false",
        "MEMORY_MODE": "read" if enabled else "off",
        "MEMORY_ENABLED_USERS": f"{ALICE_USER_ID},{BOB_USER_ID}",
        "MEMORY_ARCHIVE_OPT_IN_ENABLED": "true",
        "MEMORY_V3_CURSOR_SECRET": ctx.cursor_secret,
        "MEMORY_V3_CURSOR_POLICY_VERSION": ctx.cursor_policy_version,
        "MEMORY_V3_CURSOR_SECRET_VERSION": ctx.cursor_secret_version,
        "MEMORY_V3_CURSOR_TTL_SECONDS": str(ctx.cursor_ttl_seconds),
        "LOCAL_EMULATOR_DEV": True,
        "activation_eligible": False,
    }


def _expected_protected() -> tuple[ExpectedProtectedCollectionChange, ...]:
    return (
        ExpectedProtectedCollectionChange("memory_control", ()),
        ExpectedProtectedCollectionChange(f"users/{ALICE_USER_ID}/memory_items", ()),
        ExpectedProtectedCollectionChange(f"users/{ALICE_USER_ID}/memory_evidence", ()),
        ExpectedProtectedCollectionChange(f"users/{ALICE_USER_ID}/v3_compatibility_projection_items", ()),
        ExpectedProtectedCollectionChange(f"users/{ALICE_USER_ID}/knowledge_nodes", ()),
        ExpectedProtectedCollectionChange(f"users/{ALICE_USER_ID}/knowledge_edges", ()),
        ExpectedProtectedCollectionChange(f"users/{BOB_USER_ID}/memory_items", ()),
    )


def _scenario(
    scenario_id: str,
    description: str,
    *,
    selected_user: str = ALICE_USER_ID,
    firestore: Sequence[FirestoreSeed] | None = None,
    flags_enabled: bool = True,
    cases: Sequence[RequestCase],
    fail_closed: ExpectedFailClosedBehavior,
) -> MemoryScenario:
    ctx = _clock()
    return MemoryScenario(
        schema_version=SCHEMA_VERSION,
        scenario_id=scenario_id,
        description=description,
        deterministic=ctx,
        users=USERS,
        selected_user=selected_user,
        local_flags=_local_flags(ctx, enabled=flags_enabled),
        auth_seed=_auth_seed(USERS),
        profile_seed=_profile_seeds(USERS),
        firestore_seed=tuple(firestore if firestore is not None else _base_firestore(ctx)),
        redis_seed=(RedisSeed(key=f"memory:scenario:{scenario_id}:selected_user", value=selected_user),),
        file_seed=(
            FileSeed(
                relative_path=f"memory-scenarios/{scenario_id}/README.txt",
                content=f"Synthetic local-only memory scenario: {scenario_id}\n",
            ),
        ),
        request_cases=tuple(cases),
        expected_protected_collection_changes=_expected_protected(),
        expected_fail_closed=fail_closed,
    )


def _build_scenarios() -> dict[str, MemoryScenario]:
    ctx = _clock()
    default_reads = _alice_default_memory_ids(ctx)
    base_reads = (
        GLOBAL_READ_GATE_PATH,
        f"users/{ALICE_USER_ID}/memory_control/state",
        f"users/{ALICE_USER_ID}/v3_compatibility_projection/state",
        f"users/{ALICE_USER_ID}/v3_compatibility_projection_items",
    )
    happy = _scenario(
        "happy_path",
        "Enabled local memory /v3 read with synthetic Short-term and Long-term memories; Archive and stale Short-term are excluded by default.",
        cases=(
            RequestCase(
                case_id="alice_default_read",
                method="GET",
                path="/v3/memories",
                query={"limit": "10", "offset": "0"},
                expected_status=200,
                expected_route_decision="memory_read",
                expected_memory_ids=default_reads,
                expected_read_paths=base_reads,
            ),
        ),
        fail_closed=ExpectedFailClosedBehavior(False, None),
    )
    default_off = _scenario(
        "default_off",
        "Legacy-safe default-off scenario: server env does not select memory reads and must perform zero memory adapter reads/writes.",
        flags_enabled=False,
        cases=(
            RequestCase(
                case_id="memory_route_disabled",
                method="GET",
                path="/v3/memories",
                expected_route_decision="disabled",
                expected_memory_ids=(),
            ),
        ),
        fail_closed=ExpectedFailClosedBehavior(False, "memory_disabled", no_legacy_fallback=False),
    )
    kill = _scenario(
        "kill_switch",
        "Global memory read kill switch is active; Memory selection must fail closed with no legacy fallback after selection.",
        firestore=_base_firestore(ctx, global_enabled=True, kill=True),
        cases=(
            RequestCase(
                case_id="kill_switch_blocks",
                method="GET",
                path="/v3/memories",
                expected_status=403,
                expected_route_decision="fail_closed",
                expected_fail_closed_reason="global_memory_read_kill_switch_active",
            ),
        ),
        fail_closed=ExpectedFailClosedBehavior(True, "global_memory_read_kill_switch_active"),
    )
    malformed_cursor = _scenario(
        "malformed_cursor",
        "Malformed memory cursor must return a stable fail-closed client error and never disclose cross-user state.",
        cases=(
            RequestCase(
                case_id="malformed_cursor",
                method="GET",
                path="/v3/memories",
                query={"cursor": ctx.cursors["malformed"]},
                expected_status=400,
                expected_route_decision="fail_closed",
                expected_fail_closed_reason="malformed_cursor",
            ),
        ),
        fail_closed=ExpectedFailClosedBehavior(True, "malformed_cursor"),
    )
    stale = _scenario(
        "stale_short_exclusion",
        "Default read excludes expired Short-term records while keeping active Short-term and Long-term records visible.",
        cases=(
            RequestCase(
                case_id="stale_short_excluded",
                method="GET",
                path="/memory/search",
                expected_memory_ids=default_reads,
                expected_route_decision="memory_read",
                expected_read_paths=base_reads,
            ),
        ),
        fail_closed=ExpectedFailClosedBehavior(False, None),
    )
    archive = _scenario(
        "archive_default_exclusion",
        "Archive memories exist but default reads exclude them unless an explicit archive-capable route is used.",
        cases=(
            RequestCase(
                case_id="archive_not_in_default",
                method="GET",
                path="/v3/memories",
                expected_memory_ids=default_reads,
                expected_route_decision="memory_read",
                expected_read_paths=base_reads,
            ),
            RequestCase(
                case_id="archive_explicit",
                method="GET",
                path="/memory/archive/search",
                query={"include_archive": "true"},
                expected_memory_ids=(ctx.ids["alice_archive"],),
                expected_route_decision="memory_read",
            ),
        ),
        fail_closed=ExpectedFailClosedBehavior(False, None),
    )
    isolation = _scenario(
        "cross_user_isolation",
        "Alice and Bob are both seeded; Alice requests must never return Bob's synthetic memory even with a cross-user cursor.",
        cases=(
            RequestCase(
                case_id="alice_default_no_bob",
                method="GET",
                path="/v3/memories",
                authenticated_user=ALICE_USER_ID,
                expected_memory_ids=default_reads,
                expected_route_decision="memory_read",
            ),
            RequestCase(
                case_id="alice_with_bob_cursor",
                method="GET",
                path="/v3/memories",
                authenticated_user=ALICE_USER_ID,
                query={"cursor": ctx.cursors["cross_user_bob"]},
                expected_status=400,
                expected_route_decision="fail_closed",
                expected_fail_closed_reason="cursor_subject_mismatch",
            ),
        ),
        fail_closed=ExpectedFailClosedBehavior(True, "cursor_subject_mismatch"),
    )
    return {s.scenario_id: s for s in (happy, default_off, kill, malformed_cursor, stale, archive, isolation)}


SCENARIOS = _build_scenarios()


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(v) for v in value]
    return value


def scenario_digest(scenario: MemoryScenario) -> str:
    payload = json.dumps(_jsonable(scenario), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def list_scenarios() -> tuple[MemoryScenario, ...]:
    return tuple(SCENARIOS[name] for name in sorted(SCENARIOS))


def get_scenario(scenario_id: str) -> MemoryScenario:
    try:
        return SCENARIOS[scenario_id]
    except KeyError as exc:
        raise ValueError(
            f"Unknown memory scenario {scenario_id!r}; choose one of {', '.join(sorted(SCENARIOS))}"
        ) from exc


def validate_scenario(scenario: MemoryScenario) -> None:
    if scenario.schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported scenario schema_version={scenario.schema_version}")
    if scenario.scenario_id not in SCENARIOS:
        raise ValueError("Scenario ID must be registered")
    user_ids = {user.uid for user in scenario.users}
    required = {DEFAULT_LOCAL_USER_ID, ALICE_USER_ID, BOB_USER_ID}
    if not required.issubset(user_ids):
        raise ValueError(f"Scenario users must include {sorted(required)}")
    if scenario.selected_user not in user_ids:
        raise ValueError("selected_user must be one of scenario.users")
    if scenario.report_metadata.evidence_class != EVIDENCE_CLASS or scenario.report_metadata.activation_eligible:
        raise ValueError("Local scenario report metadata must remain LOCAL_EMULATOR_DEV and activation_eligible=false")
    for seed in (*scenario.profile_seed, *scenario.firestore_seed):
        if not seed.path or seed.path.startswith("/") or ".." in seed.path.split("/"):
            raise ValueError(f"Unsafe Firestore seed path {seed.path!r}")
        if "evidence_class" in seed.data or "activation_eligible" in seed.data:
            raise ValueError("Fixture seed documents cannot select evidence/report labels")
    for request in scenario.request_cases:
        if request.method != "GET":
            raise ValueError("Local memory scenario request cases are read-only GET paths in this slice")
        if request.expected_no_write is not True:
            raise ValueError("GET request cases must assert no memory writes")
        if request.authenticated_user not in user_ids:
            raise ValueError("Request authenticated_user must be a synthetic scenario user")
    if scenario.local_flags.get("activation_eligible") is not False:
        raise ValueError("local_flags must hard-code activation_eligible=false")


def validate_all_scenarios() -> None:
    for scenario in SCENARIOS.values():
        validate_scenario(scenario)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _metadata_operation(scenario: MemoryScenario) -> SeedOperation:
    return SeedOperation(
        kind="metadata",
        action="write",
        target=f"scenario:{scenario.scenario_id}",
        payload={
            "scenario_id": scenario.scenario_id,
            "scenario_digest": scenario_digest(scenario),
            "selected_user": scenario.selected_user,
            "report_metadata": _jsonable(scenario.report_metadata),
        },
    )


def _lookup_auth_uid(cfg: config.HarnessConfig, email: str, password: str) -> str:
    url = f"http://{cfg.auth_host}/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=local-dev-harness"
    status, body = _request_json(
        "POST",
        url,
        {"email": email, "password": password, "returnSecureToken": True},
    )
    if status >= 400:
        raise RuntimeError(f"Auth uid lookup failed for {email}: HTTP {status} {body[:200]}")
    payload = json.loads(body)
    local_id = payload.get("localId")
    if not isinstance(local_id, str) or not local_id.strip():
        raise RuntimeError(f"Auth uid lookup for {email} returned no localId")
    return local_id


def _resolve_auth_uid_map(cfg: config.HarnessConfig, users: Sequence[ScenarioUser]) -> dict[str, str]:
    return {user.uid: _lookup_auth_uid(cfg, user.email, user.password) for user in users}


def _remap_firestore_seed(seed: FirestoreSeed, uid_map: Mapping[str, str]) -> FirestoreSeed:
    parts = seed.path.split("/")
    if len(parts) >= 2 and parts[0] == "users" and parts[1] in uid_map:
        parts[1] = uid_map[parts[1]]
        data = dict(seed.data)
        uid_value = data.get("uid")
        if isinstance(uid_value, str) and uid_value in uid_map:
            data["uid"] = uid_map[uid_value]
        return FirestoreSeed(path="/".join(parts), protected=seed.protected, data=data)
    return seed


def _remap_auth_operation(op: SeedOperation, uid_map: Mapping[str, str]) -> SeedOperation:
    if op.kind != "auth":
        return op
    resolved = uid_map.get(op.target, op.target)
    return SeedOperation(op.kind, op.action, resolved, op.payload, op.protected)


def _remap_seed_operation(op: SeedOperation, uid_map: Mapping[str, str]) -> SeedOperation:
    if op.kind != "firestore" or not isinstance(op.payload, Mapping):
        return op
    remapped = _remap_firestore_seed(FirestoreSeed(path=op.target, data=op.payload, protected=op.protected), uid_map)
    return SeedOperation(op.kind, op.action, remapped.path, remapped.data, remapped.protected)


def _auth_uid_manifest_path(cfg: config.HarnessConfig) -> Path:
    return cfg.layout.state_root / "manifests" / AUTH_UID_MANIFEST


def write_auth_uid_manifest(cfg: config.HarnessConfig, uid_map: Mapping[str, str]) -> Path:
    path = _auth_uid_manifest_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": _now(),
        "users": dict(uid_map),
        "canonical_users": [uid_map[ALICE_USER_ID], uid_map[BOB_USER_ID]],
        "selected_user": uid_map[ALICE_USER_ID],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_auth_uid_manifest(cfg: config.HarnessConfig) -> dict[str, object]:
    path = _auth_uid_manifest_path(cfg)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def canonical_users_from_manifest(cfg: config.HarnessConfig) -> str | None:
    payload = read_auth_uid_manifest(cfg)
    canonical = payload.get("canonical_users")
    if isinstance(canonical, list):
        values = [str(item).strip() for item in canonical if str(item).strip()]
        if values:
            return ",".join(values)
    users = payload.get("users")
    if isinstance(users, dict):
        alice_uid = users.get(ALICE_USER_ID)
        if isinstance(alice_uid, str) and alice_uid.strip():
            return alice_uid.strip()
    selected = payload.get("selected_user")
    if isinstance(selected, str) and selected.strip():
        return selected.strip()
    return None


def _apply_seed_operations(
    cfg: config.HarnessConfig, scenario: MemoryScenario, ops: tuple[SeedOperation, ...]
) -> dict[str, str] | None:
    auth_ops = [op for op in ops if op.kind == "auth"]
    other_ops = [op for op in ops if op.kind != "auth"]
    for op in auth_ops:
        _apply_operation(cfg, op)
    uid_map = _resolve_auth_uid_map(cfg, scenario.users)
    write_auth_uid_manifest(cfg, uid_map)
    for op in other_ops:
        _apply_operation(cfg, _remap_seed_operation(op, uid_map))
    return uid_map


def build_seed_operations(scenario: MemoryScenario) -> tuple[SeedOperation, ...]:
    validate_scenario(scenario)
    ops: list[SeedOperation] = [_metadata_operation(scenario)]
    ops.extend(SeedOperation("auth", "upsert", str(user["localId"]), user) for user in scenario.auth_seed)
    ops.extend(
        SeedOperation("firestore", "upsert", seed.path, seed.data, seed.protected) for seed in scenario.profile_seed
    )
    ops.extend(
        SeedOperation("firestore", "upsert", seed.path, seed.data, seed.protected) for seed in scenario.firestore_seed
    )
    ops.extend(SeedOperation("redis", "upsert", seed.key, seed.value) for seed in scenario.redis_seed)
    ops.extend(SeedOperation("file", "write", seed.relative_path, seed.content) for seed in scenario.file_seed)
    return tuple(ops)


def build_reset_operations(scenario: MemoryScenario) -> tuple[SeedOperation, ...]:
    validate_scenario(scenario)
    ops: list[SeedOperation] = []
    ops.extend(SeedOperation("auth", "delete", str(user["localId"])) for user in scenario.auth_seed)
    ops.extend(
        SeedOperation("firestore", "delete", seed.path, protected=seed.protected)
        for seed in (*scenario.profile_seed, *scenario.firestore_seed)
    )
    ops.extend(SeedOperation("redis", "delete", seed.key) for seed in scenario.redis_seed)
    ops.extend(SeedOperation("file", "delete", seed.relative_path) for seed in scenario.file_seed)
    ops.append(SeedOperation("metadata", "delete", f"scenario:{scenario.scenario_id}"))
    return tuple(ops)


def _port_open(hostport: str, timeout: float = 0.2) -> bool:
    host, raw_port = hostport.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(raw_port)), timeout=timeout):
            return True
    except OSError:
        return False


def emulator_availability(cfg: config.HarnessConfig) -> dict[str, bool]:
    return {
        "firestore": _port_open(cfg.firestore_host),
        "auth": _port_open(cfg.auth_host),
        "redis": _port_open(f"{cfg.redis_host}:{cfg.redis_port}"),
    }


def _firestore_value(value: object) -> dict[str, object]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        if value.endswith("Z"):
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                return {"timestampValue": value}
            except ValueError:
                pass
        return {"stringValue": value}
    if isinstance(value, Mapping):
        return {"mapValue": {"fields": {str(k): _firestore_value(v) for k, v in value.items()}}}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return {"arrayValue": {"values": [_firestore_value(v) for v in value]}}
    return {"stringValue": str(value)}


def _firestore_document_payload(data: Mapping[str, object]) -> dict[str, object]:
    return {"fields": {str(k): _firestore_value(v) for k, v in data.items()}}


def _request_json(method: str, url: str, payload: Mapping[str, object] | None = None) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=2) as response:
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")


def _apply_firestore_admin_sdk(cfg: config.HarnessConfig, op: SeedOperation) -> bool:
    """Apply Firestore seed/reset through emulator Admin-style credentials when available.

    The repo's Firestore rules intentionally deny all client writes to memory
    protected collections. For live local emulator seeding, use the Python
    Firestore client with AnonymousCredentials against FIRESTORE_EMULATOR_HOST,
    which bypasses rules like backend/Admin tooling. If the dependency is not
    installed, return False and let the REST fallback produce an actionable
    error.
    """

    try:
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore
    except Exception:
        return False

    old_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    os.environ["FIRESTORE_EMULATOR_HOST"] = cfg.firestore_host
    try:
        client = firestore.Client(project=cfg.project_id, credentials=AnonymousCredentials())
        document = client.document(op.target)
        if op.action == "upsert":
            payload = dict(op.payload if isinstance(op.payload, Mapping) else {})
            document.set(payload)
        elif op.action == "delete":
            document.delete()
        else:
            raise RuntimeError(f"Unsupported Firestore scenario action: {op.action}")
        return True
    finally:
        if old_host is None:
            os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
        else:
            os.environ["FIRESTORE_EMULATOR_HOST"] = old_host


def _apply_operation(cfg: config.HarnessConfig, op: SeedOperation) -> None:
    if op.kind == "file":
        target = cfg.layout.state_root / "files" / op.target
        safety.validate_destructive_target(target.parent, state_root=cfg.layout.state_root, repo_root=cfg.repo_root)
        if op.action == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(op.payload), encoding="utf-8")
        elif target.exists():
            safety.validate_destructive_target(target, state_root=cfg.layout.state_root, repo_root=cfg.repo_root)
            target.unlink()
        return
    if op.kind == "metadata":
        target = cfg.layout.state_root / "manifests" / "memory-scenario-current.json"
        if op.action == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(op.payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        elif target.exists():
            target.unlink()
        return
    if op.kind == "firestore":
        if _apply_firestore_admin_sdk(cfg, op):
            return
        encoded_path = "/".join(quote(part, safe="") for part in op.target.split("/"))
        url = f"http://{cfg.firestore_host}/v1/projects/{cfg.project_id}/databases/{quote(cfg.database_id, safe='')}/documents/{encoded_path}"
        if op.action == "upsert":
            status, body = _request_json(
                "PATCH", url, _firestore_document_payload(op.payload if isinstance(op.payload, Mapping) else {})
            )
            if status >= 400:
                raise RuntimeError(f"Firestore emulator write failed for {op.target}: HTTP {status} {body[:200]}")
        elif op.action == "delete":
            status, body = _request_json("DELETE", url)
            if status not in {200, 404}:
                raise RuntimeError(f"Firestore emulator delete failed for {op.target}: HTTP {status} {body[:200]}")
        return
    if op.kind == "auth":
        # Firebase Auth emulator supports account creation via identitytoolkit and
        # deletion via emulator admin endpoints. If an existing user causes a 400
        # on upsert, the seed remains idempotent for local QA purposes.
        if op.action == "upsert":
            payload = dict(op.payload if isinstance(op.payload, Mapping) else {})
            url = f"http://{cfg.auth_host}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=local-dev-harness"
            status, body = _request_json("POST", url, payload)
            if status >= 400 and "UNEXPECTED_PARAMETER : User ID" in body:
                # The Auth emulator signUp endpoint rejects caller-specified
                # localId values. Retry without localId so a live manual-QA
                # seed still succeeds; the deterministic user IDs remain in
                # the scenario manifest and desktop placeholder contract.
                payload.pop("localId", None)
                status, body = _request_json("POST", url, payload)
            if status >= 400 and "EMAIL_EXISTS" not in body:
                raise RuntimeError(f"Auth emulator user seed failed for {op.target}: HTTP {status} {body[:200]}")
        elif op.action == "delete":
            url = f"http://{cfg.auth_host}/emulator/v1/projects/{cfg.project_id}/accounts?localId={quote(op.target, safe='')}"
            status, body = _request_json("DELETE", url)
            if status not in {200, 404}:
                raise RuntimeError(f"Auth emulator user reset failed for {op.target}: HTTP {status} {body[:200]}")
        return
    if op.kind == "redis":
        # Avoid mutating arbitrary shared Redis here. Live Redis seeding is a later
        # harness integration; the manifest records the intended namespace.
        return


def build_manifest(
    scenario: MemoryScenario,
    cfg: config.HarnessConfig,
    *,
    operations: tuple[SeedOperation, ...],
    dry_run: bool,
    applied: bool,
) -> SeedManifest:
    return SeedManifest(
        schema_version=SCHEMA_VERSION,
        scenario_id=scenario.scenario_id,
        scenario_digest=scenario_digest(scenario),
        generated_at=_now(),
        dry_run=dry_run,
        applied=applied,
        emulator_available=emulator_availability(cfg),
        report_metadata=scenario.report_metadata,
        operations=operations,
    )


def write_manifest(cfg: config.HarnessConfig, manifest: SeedManifest, *, reset: bool = False) -> Path:
    cfg.layout.process_manifest.parent.mkdir(parents=True, exist_ok=True)
    name = f"memory-scenario-{manifest.scenario_id}-{'reset' if reset else 'seed'}.json"
    path = cfg.layout.process_manifest.parent / name
    path.write_text(json.dumps(_jsonable(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def seed_scenario(scenario_id: str, cfg: config.HarnessConfig, *, dry_run: bool | None = None) -> SeedManifest:
    scenario = get_scenario(scenario_id)
    ops = build_seed_operations(scenario)
    availability = emulator_availability(cfg)
    effective_dry_run = (not (availability["firestore"] and availability["auth"])) if dry_run is None else dry_run
    applied = False
    if not effective_dry_run:
        safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=cfg.repo_root, instance=cfg.instance)
        _apply_seed_operations(cfg, scenario, ops)
        applied = True
    else:
        # Still materialize local metadata/file intent under sentinel-owned state
        # only when the layout exists; this keeps dry runs useful in temp-state tests.
        if cfg.layout.sentinel_path.exists():
            for op in ops:
                if op.kind in {"metadata", "file"}:
                    _apply_operation(cfg, op)
    manifest = build_manifest(scenario, cfg, operations=ops, dry_run=effective_dry_run, applied=applied)
    write_manifest(cfg, manifest)
    return manifest


def reset_scenario(scenario_id: str, cfg: config.HarnessConfig, *, dry_run: bool | None = None) -> SeedManifest:
    scenario = get_scenario(scenario_id)
    ops = build_reset_operations(scenario)
    availability = emulator_availability(cfg)
    effective_dry_run = (not (availability["firestore"] and availability["auth"])) if dry_run is None else dry_run
    applied = False
    if not effective_dry_run:
        safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=cfg.repo_root, instance=cfg.instance)
        uid_map = read_auth_uid_manifest(cfg).get("users")
        if not isinstance(uid_map, dict):
            uid_map = _resolve_auth_uid_map(cfg, scenario.users)
        typed_uid_map = {str(k): str(v) for k, v in uid_map.items()}
        for op in ops:
            remapped = (
                _remap_auth_operation(op, typed_uid_map)
                if op.kind == "auth"
                else _remap_seed_operation(op, typed_uid_map)
            )
            _apply_operation(cfg, remapped)
        manifest_path = _auth_uid_manifest_path(cfg)
        if manifest_path.exists():
            manifest_path.unlink()
        applied = True
    else:
        if cfg.layout.sentinel_path.exists():
            for op in ops:
                if op.kind in {"metadata", "file"}:
                    _apply_operation(cfg, op)
    manifest = build_manifest(scenario, cfg, operations=ops, dry_run=effective_dry_run, applied=applied)
    write_manifest(cfg, manifest, reset=True)
    return manifest


def _repo_root() -> Path:
    return config.repo_root_from(Path.cwd())


def print_scenario_list(*, json_output: bool = False) -> None:
    validate_all_scenarios()
    if json_output:
        print(
            json.dumps(
                [
                    {"scenario_id": s.scenario_id, "description": s.description, "selected_user": s.selected_user}
                    for s in list_scenarios()
                ],
                indent=2,
                sort_keys=True,
            )
        )
        return
    print("Local memory emulator scenarios (LOCAL_EMULATOR_DEV, activation_eligible=false)")
    for scenario in list_scenarios():
        print(f"- {scenario.scenario_id}: {scenario.description}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-scenarios")
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument("scenario")
    seed_parser.add_argument("--dry-run", action="store_true", default=None)
    seed_parser.add_argument("--apply", action="store_false", dest="dry_run")
    reset_parser = sub.add_parser("reset")
    reset_parser.add_argument("scenario")
    reset_parser.add_argument("--dry-run", action="store_true", default=None)
    reset_parser.add_argument("--apply", action="store_false", dest="dry_run")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "list":
            print_scenario_list(json_output=bool(args.json))
            return 0
        cfg = config.load_config(_repo_root(), create_layout=True)
        if args.command == "seed":
            manifest = seed_scenario(args.scenario, cfg, dry_run=args.dry_run)
            write_manifest(cfg, manifest)
            print(json.dumps(_jsonable(manifest), indent=2, sort_keys=True))
            return 0
        if args.command == "reset":
            manifest = reset_scenario(args.scenario, cfg, dry_run=args.dry_run)
            write_manifest(cfg, manifest, reset=True)
            print(json.dumps(_jsonable(manifest), indent=2, sort_keys=True))
            return 0
    except (ValueError, safety.SafetyError, RuntimeError) as exc:
        print(f"Memory scenario command failed: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
