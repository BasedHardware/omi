#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.memory_rollout import PASSED, MemoryRolloutMode, MemoryRolloutStageGate
from utils.memory.default_read_rollout import DEFAULT_READ_ROLLOUT_SCHEMA_VERSION

ROLLLOUT_READINESS_STATUS_NOT_RUN = "NOT_RUN"
CANONICAL_CONSUMERS = ["mcp", "developer_api", "omi_chat"]
CANONICAL_REQUIRED_FIELDS = ["uid", "schema_version", "grants"]
CANONICAL_GRANT_PATHS = [
    "grants.mcp.default_memory",
    "grants.developer_api.default_memory",
    "grants.omi_chat.default_memory",
    "grants.mcp.archive",
    "grants.developer_api.archive",
    "grants.omi_chat.archive",
]
REJECTED_LEGACY_ALIAS_FIELDS = [
    "mcp_default_memory_grant",
    "developer_default_memory_grant",
    "developer_api_default_memory_grant",
    "chat_default_memory_grant",
    "omi_chat_default_memory_grant",
]
NON_CLAIMS = [
    "Default and execute modes are read-only schema inventory only; no Firestore reads/writes, cloud calls, or provider calls are executed.",
    "production_rollout_approved=false; this artifact does not approve rollout or mutate users/{uid}/memory_control/state.",
    "Legacy top-level *_default_memory_grant aliases are rejected compatibility examples only and must not appear in canonical memory rollout examples.",
    "Archive remains default-unavailable; canonical .archive only records a separate explicit Archive capability.",
]


@dataclass(frozen=True)
class RolloutSchemaReadinessConfig:
    execute: bool


def _base_schema_v1_doc(uid: str = "memory-schema-readiness-user") -> Dict[str, Any]:
    return {
        "uid": uid,
        "schema_version": DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        "mode": MemoryRolloutMode.read.value,
        "mode_epoch": 7,
        "cutover_epoch": 7,
        "account_generation": 3,
        "fallback_projection_ready": True,
        "persistent_memory_writes_started": True,
        "writes_blocked": False,
        "stage_gates": {
            MemoryRolloutStageGate.shadow.value: PASSED,
            MemoryRolloutStageGate.write.value: PASSED,
            MemoryRolloutStageGate.read.value: PASSED,
        },
        "grants": {
            "mcp": {"default_memory": True},
            "developer_api": {"default_memory": True},
            "omi_chat": {"default_memory": True, "archive": True},
        },
        "vector_projection_commit_id": "projection-commit-1",
        "vector_repair_outbox_enabled": True,
    }


def _valid_examples() -> list[Dict[str, Any]]:
    uid = "memory-schema-readiness-user"
    document = _base_schema_v1_doc(uid)
    return [
        {
            "name": f"canonical_schema_v1_{consumer}",
            "uid": uid,
            "consumer": consumer,
            "document": document,
            "expected_decision": "USE_MEMORY",
        }
        for consumer in CANONICAL_CONSUMERS
    ]


def _rejected_legacy_shapes() -> list[Dict[str, Any]]:
    uid = "memory-schema-readiness-user"
    missing_schema = _base_schema_v1_doc(uid)
    missing_schema.pop("schema_version")
    mismatched_uid = _base_schema_v1_doc("other-user")
    top_level_mcp_alias_only = _base_schema_v1_doc(uid)
    top_level_mcp_alias_only["grants"] = {"mcp": {}}
    top_level_mcp_alias_only["mcp_default_memory_grant"] = True
    top_level_developer_alias_only = _base_schema_v1_doc(uid)
    top_level_developer_alias_only["grants"] = {"developer_api": {}}
    top_level_developer_alias_only["developer_default_memory_grant"] = True
    top_level_chat_alias_only = _base_schema_v1_doc(uid)
    top_level_chat_alias_only["grants"] = {"omi_chat": {}}
    top_level_chat_alias_only["chat_default_memory_grant"] = True
    nested_chat_alias_only = _base_schema_v1_doc(uid)
    nested_chat_alias_only["grants"] = {"chat": {"default_memory": True}}
    return [
        {
            "name": "missing_schema_version",
            "uid": uid,
            "consumer": "mcp",
            "document": missing_schema,
            "reason": "unsupported_rollout_schema",
        },
        {
            "name": "mismatched_uid",
            "uid": uid,
            "consumer": "mcp",
            "document": mismatched_uid,
            "reason": "uid_mismatch",
        },
        {
            "name": "top_level_mcp_default_memory_grant_alias_only",
            "uid": uid,
            "consumer": "mcp",
            "document": top_level_mcp_alias_only,
            "reason": "missing_mcp_default_memory_grant",
        },
        {
            "name": "top_level_developer_default_memory_grant_alias_only",
            "uid": uid,
            "consumer": "developer_api",
            "document": top_level_developer_alias_only,
            "reason": "missing_developer_default_memory_grant",
        },
        {
            "name": "top_level_chat_default_memory_grant_alias_only",
            "uid": uid,
            "consumer": "omi_chat",
            "document": top_level_chat_alias_only,
            "reason": "missing_chat_default_memory_grant",
        },
        {
            "name": "nested_chat_alias_only",
            "uid": uid,
            "consumer": "omi_chat",
            "document": nested_chat_alias_only,
            "reason": "missing_chat_default_memory_grant",
        },
    ]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe memory rollout/control schema_version=1 readiness inventory; emits canonical and rejected shapes without Firestore/cloud calls."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Emit the same read-only local inventory; no provider calls."
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> RolloutSchemaReadinessConfig:
    return RolloutSchemaReadinessConfig(execute=bool(args.execute))


def build_readiness_artifact(config: RolloutSchemaReadinessConfig) -> Dict[str, Any]:
    return {
        "status": ROLLLOUT_READINESS_STATUS_NOT_RUN,
        "read_only": True,
        "mutation_allowed": False,
        "execute_requested": config.execute,
        "network_or_provider_calls_executed": False,
        "firestore_reads_executed": False,
        "firestore_writes_executed": False,
        "production_rollout_approved": False,
        "canonical_schema_version": DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        "canonical_consumers": CANONICAL_CONSUMERS,
        "canonical_shape": {
            "path": "users/{uid}/memory_control/state",
            "required": CANONICAL_REQUIRED_FIELDS,
            "grant_paths": CANONICAL_GRANT_PATHS,
            "compatibility_notes": [
                "uid must exactly match the path/authenticated uid; missing uid fails closed with uid_mismatch.",
                "schema_version must equal DEFAULT_READ_ROLLOUT_SCHEMA_VERSION / schema_version=1.",
                "default grants are recognized only at grants.<consumer>.default_memory for mcp, developer_api, and omi_chat.",
                "Archive capability is optional and recognized only at grants.<consumer>.archive for explicit Archive reads; it is never default-visible.",
            ],
        },
        "valid_examples": _valid_examples(),
        "rejected_legacy_shapes": _rejected_legacy_shapes(),
        "forbidden_legacy_alias_fields": REJECTED_LEGACY_ALIAS_FIELDS,
        "planned_safe_commands": [
            "python3 backend/scripts/rollout_schema_readiness.py",
            "python3 backend/scripts/rollout_schema_readiness.py --execute",
        ],
        "non_claims": NON_CLAIMS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    config = config_from_args(parse_args(argv or sys.argv[1:]))
    print(json.dumps(build_readiness_artifact(config), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
