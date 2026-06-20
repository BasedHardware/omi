#!/usr/bin/env python3
"""Safe `/v3` V17 control-reader Firestore-emulator/security readiness artifact.

This is a read-only local prerequisite inventory for a future Firestore-emulator
or API-backed proof of the server-side V17 `/v3` control reader. It never starts
emulators, imports FastAPI routers, reads/writes Firestore cloud, mutates local
emulator data, calls providers/cloud/network services, implements a production
reader, wires runtime routes, or claims approval.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping


def _load_external_readiness_module():
    spec = importlib.util.spec_from_file_location(
        "v17_p1_3_v3_external_compatibility_readiness",
        Path(__file__).with_name("v17_p1_3_v3_external_compatibility_readiness.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v17_p1_3_v3_external_compatibility_readiness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_EXTERNAL = _load_external_readiness_module()

LINKED_READINESS_PROOFS = {
    "control_reader_contract_proof": _EXTERNAL.CONTROL_READER_CONTRACT_PROOF,
    "control_reader_readiness_proof": _EXTERNAL.CONTROL_READER_READINESS_PROOF,
    "get_runtime_wiring_readiness_proof": _EXTERNAL.GET_RUNTIME_WIRING_READINESS_PROOF,
    "get_dependency_auth_readiness_proof": _EXTERNAL.GET_DEPENDENCY_AUTH_READINESS_PROOF,
}

CONTROL_READER_EMULATOR_READINESS_PROOF = {
    "service": "backend/scripts/v17_p1_3_v3_control_reader_emulator_readiness.py",
    "test": "backend/tests/unit/test_v17_p1_3_v3_control_reader_emulator_readiness.py",
    "runtime_wired": False,
    "production_rollout_approved": False,
    "external_calls": [],
    "covered_defaults": [
        "safe_default_blocked_not_run_no_cloud_or_emulator_side_effects",
        "local_firestore_emulator_harness_config_inventory_without_starting_services",
        "canonical_server_control_source_path_api_still_blocked_until_chosen",
        "control_doc_fixture_schema_uid_generation_grant_projection_write_archive_short_term_fields",
        "security_iam_evidence_no_direct_client_control_reads_server_principal_allowed",
        "rules_static_emulator_and_cloud_iam_proof_separation",
        "contract_decision_case_inventory_matches_v17_v3_control_reader_contract",
        "non_enrolled_legacy_boundary_and_enrolled_no_legacy_fallback_constraints",
    ],
}

CONTROL_FIXTURE_SCHEMA_FIELDS = [
    "uid",
    "schema_version",
    "mode",
    "mode_epoch",
    "cutover_epoch",
    "account_generation",
    "fallback_projection_ready",
    "persistent_v17_writes_started",
    "writes_blocked",
    "stage_gates",
    "grants",
]

EMULATOR_API_PROOF_PREREQUISITES = [
    {
        "prerequisite_id": "canonical_server_control_source_path_api",
        "status": "READY_LOCAL_ADAPTER_PROVEN",
        "explicit_blocker": None,
        "required_before_emulator_or_api_proof": True,
        "canonical_path": "users/{uid}/memory_control/state",
        "candidate_paths": ["users/{uid}/memory_control/state"],
        "must_match_contract": "utils/memory/v17_v3_control_reader_contract.py",
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "prerequisite_id": "firestore_emulator_config_and_cli",
        "status": "BLOCKED",
        "required_before_emulator_or_api_proof": True,
        "requires_firestore_emulator_host": True,
        "required_local_files": ["firebase.json", "firestore.rules", "package.json"],
        "required_tools": ["firebase-tools", "java", "node", "python3"],
        "must_not_start_cloud_services": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "prerequisite_id": "control_reader_fixture_schema",
        "status": "BLOCKED",
        "required_before_emulator_or_api_proof": True,
        "fixture_path_template": "users/{uid}/memory_control/state",
        "required_fields": CONTROL_FIXTURE_SCHEMA_FIELDS,
        "default_denials": {
            "grants.omi_chat.archive": False,
        },
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "prerequisite_id": "api_backed_server_reader_harness",
        "status": "BLOCKED",
        "required_before_emulator_or_api_proof": True,
        "required_harness_shape": "fake-injectable server reader or emulator-backed API proof that calls the decision contract with fixture control docs",
        "must_not_start_cloud_services": True,
        "must_not_write_production_firestore": True,
        "must_not_wire_backend_routers_memories": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
    {
        "prerequisite_id": "security_rules_and_iam_evidence_separation",
        "status": "BLOCKED",
        "required_before_emulator_or_api_proof": True,
        "rules_static_proof_is_not_iam_proof": True,
        "emulator_rules_proof_is_not_cloud_iam": True,
        "cloud_iam_requires_separate_read_only_gcloud_evidence": True,
        "runtime_wired": False,
        "approval_claimed": False,
    },
]

SECURITY_IAM_EVIDENCE_REQUIREMENTS = [
    {
        "evidence_id": "no_direct_client_control_reads_rules_static",
        "status": "BLOCKED",
        "required_evidence": "Checked-in Firestore rules deny client direct reads on the chosen control document path.",
        "direct_client_control_reads_allowed": False,
        "evidence_kind": "static_rules",
        "cloud_credentials_required_now": False,
    },
    {
        "evidence_id": "no_direct_client_control_reads_emulator",
        "status": "BLOCKED",
        "required_evidence": "Local Firestore emulator rules-unit test denies signed-in client get/set/update/delete on control docs.",
        "required_emulator_case": "signed-in client getDoc(users/{uid}/memory_control/state) is denied",
        "direct_client_control_reads_allowed": False,
        "cloud_credentials_required_now": False,
    },
    {
        "evidence_id": "server_principal_control_read_allowed_iam",
        "status": "BLOCKED",
        "required_evidence": "Read-only cloud IAM proof shows the backend/server principal can read the chosen control path without owner/editor broadening.",
        "server_principal_allowed": "required_but_not_proven",
        "cloud_credentials_required_now": False,
        "future_read_only_proof": "gcloud projects get-iam-policy / service-accounts get-iam-policy inventory only",
    },
    {
        "evidence_id": "rules_static_emulator_iam_proof_separation",
        "status": "BLOCKED",
        "required_evidence": "Rules static checks, emulator denial checks, and cloud IAM principal checks are recorded as separate proof classes.",
        "rules_static_proof_is_not_emulator_proof": True,
        "emulator_rules_proof_is_not_cloud_iam": True,
        "cloud_iam_proof_is_not_runtime_cutover_approval": True,
        "cloud_credentials_required_now": False,
    },
]

REQUIRED_CONTRACT_PROOF_CASES = [
    {
        "case_id": "non_enrolled_legacy_allowed",
        "expected_route_family": "legacy_primary",
        "legacy_fallback_allowed": True,
        "required_fixture_overrides": {"cohort_enrolled": False, "firestore_read_expected": False},
    },
    {
        "case_id": "v17_projection_allowed",
        "expected_route_family": "v17_projection",
        "legacy_fallback_allowed": False,
        "required_fixture_overrides": {
            "mode": "read",
            "grants.omi_chat.default_memory": True,
            "fallback_projection_ready": True,
            "stage_gates.read": "passed",
            "global_read_gate_open": True,
            "write_convergence_ready": True,
        },
    },
    {
        "case_id": "missing_control_doc",
        "expected_route_family": "fail_closed",
        "legacy_fallback_allowed": False,
        "required_fixture_overrides": None,
    },
    {
        "case_id": "stale_generation",
        "expected_route_family": "fail_closed",
        "legacy_fallback_allowed": False,
        "required_fixture_overrides": {"account_generation": "not_equal_expected_account_generation"},
    },
    {
        "case_id": "no_default_memory_grant",
        "expected_route_family": "fail_closed",
        "legacy_fallback_allowed": False,
        "required_fixture_overrides": {"grants.omi_chat.default_memory": False},
    },
    {
        "case_id": "projection_not_ready",
        "expected_route_family": "fail_closed",
        "legacy_fallback_allowed": False,
        "required_fixture_overrides": {"fallback_projection_ready": False},
    },
    {
        "case_id": "write_convergence_not_ready",
        "expected_route_family": "fail_closed",
        "legacy_fallback_allowed": False,
        "required_fixture_overrides": {"write_convergence_ready": False},
    },
    {
        "case_id": "invalid_or_missing_cursor_secret",
        "expected_route_family": "fail_closed",
        "legacy_fallback_allowed": False,
        "required_request_overrides": {"cursor_v17_read_requested": True, "cursor_secret_config_present": False},
    },
    {
        "case_id": "archive_not_allowed",
        "expected_route_family": "fail_closed",
        "legacy_fallback_allowed": False,
        "required_request_overrides": {"archive_requested": True},
        "required_fixture_overrides": {"grants.omi_chat.archive": False},
    },
]

LEGACY_BOUNDARY_CONTRACT = {
    "non_enrolled_legacy_primary_allowed_marker_only": True,
    "non_enrolled_offset_zero_limit_5000_preserved_outside_control_contract": True,
    "enrolled_no_legacy_fallback_on_gate_failure": True,
    "legacy_v17_result_merge_allowed": False,
    "archive_default_available": False,
    "stale_short_term_control_state_absent": True,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def local_emulator_harness_inventory(env: Mapping[str, str]) -> dict[str, Any]:
    root = _repo_root()
    firebase_json = _load_json(root / "firebase.json")
    package_json = _load_json(root / "package.json")
    firestore_rules = root / "firestore.rules"
    rules_harness = root / "backend" / "scripts" / "v17_firestore_rules_emulator_test.mjs"
    control_harness = root / "backend" / "scripts" / "v17_p1_3_v3_control_reader_emulator_test.py"
    emulator_config = firebase_json.get("emulators", {}).get("firestore", {})
    scripts = package_json.get("scripts", {})
    return {
        "firebase_json_present": bool(firebase_json),
        "firestore_rules_present": firestore_rules.exists(),
        "firestore_rules_path": "firestore.rules" if firestore_rules.exists() else None,
        "firestore_emulator_configured": bool(emulator_config),
        "firestore_emulator_port": emulator_config.get("port"),
        "rules_emulator_harness_present": rules_harness.exists(),
        "rules_emulator_script_present": "test:v17-firestore-rules:emulator" in scripts,
        "control_reader_emulator_harness_present": control_harness.exists(),
        "control_reader_emulator_script_present": "test:v17-v3-control-reader:emulator" in scripts,
        "firestore_emulator_host_env_present": bool(env.get("FIRESTORE_EMULATOR_HOST")),
        "firestore_emulator_host_env_value_recorded": (
            env.get("FIRESTORE_EMULATOR_HOST") if env.get("FIRESTORE_EMULATOR_HOST") else None
        ),
        "safe_detection_only_no_service_start": True,
    }


def build_report(*, execute: bool = False, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    effective_env = os.environ if env is None else env
    inventory = local_emulator_harness_inventory(effective_env)
    blocked_prerequisites = sum(1 for item in EMULATOR_API_PROOF_PREREQUISITES if item["status"] == "BLOCKED")
    proof_status = "BLOCKED" if execute else "NOT_RUN"
    return {
        "artifact": "v17_p1_3_v3_control_reader_emulator_readiness",
        "status": "BLOCKED",
        "proof_status": proof_status,
        "execute": execute,
        "read_only": True,
        "mutation_allowed": False,
        "runtime_wiring_changed": False,
        "production_control_reader_implemented": False,
        "network_or_provider_calls_executed": False,
        "provider_calls_executed": False,
        "cloud_calls_executed": False,
        "firestore_cloud_reads_executed": False,
        "firestore_cloud_writes_executed": False,
        "firestore_emulator_started": False,
        "firestore_emulator_reads_executed": False,
        "firestore_emulator_writes_executed": False,
        "production_rollout_approved": False,
        "approval_claimed": False,
        "scope": "Readiness inventory for a future Firestore-emulator/API-backed server-side V17 `/v3` control-reader validation and security/IAM proof.",
        "local_emulator_harness_inventory": inventory,
        "emulator_api_proof_prerequisites": EMULATOR_API_PROOF_PREREQUISITES,
        "control_fixture_schema_fields": CONTROL_FIXTURE_SCHEMA_FIELDS,
        "security_iam_evidence_requirements": SECURITY_IAM_EVIDENCE_REQUIREMENTS,
        "required_contract_proof_cases": REQUIRED_CONTRACT_PROOF_CASES,
        "legacy_boundary_contract": LEGACY_BOUNDARY_CONTRACT,
        "linked_readiness_proofs": LINKED_READINESS_PROOFS,
        "proof": CONTROL_READER_EMULATOR_READINESS_PROOF,
        "non_claims": [
            "No Firestore emulator service was started or contacted.",
            "No Firestore cloud reads or writes were executed.",
            "No API-backed production or cloud control reader was implemented.",
            "No `/v3` runtime route wiring changed.",
            "No direct client control reads are allowed or proven safe.",
            "No cloud IAM/server-principal evidence was collected.",
            "No Archive default visibility or stale Short-term default visibility introduced.",
            "No rollout approval claimed.",
        ],
        "summary": {
            "status": "BLOCKED",
            "proof_status": proof_status,
            "read_only": True,
            "mutation_allowed": False,
            "runtime_wiring_changed": False,
            "production_control_reader_implemented": False,
            "approval_claimed": False,
            "prerequisite_count": len(EMULATOR_API_PROOF_PREREQUISITES),
            "blocked_prerequisite_count": blocked_prerequisites,
            "fixture_schema_field_count": len(CONTROL_FIXTURE_SCHEMA_FIELDS),
            "required_contract_case_count": len(REQUIRED_CONTRACT_PROOF_CASES),
            "security_iam_evidence_requirement_count": len(SECURITY_IAM_EVIDENCE_REQUIREMENTS),
            "linked_readiness_proof_count": len(LINKED_READINESS_PROOFS),
            "control_reader_emulator_harness_present": bool(inventory["control_reader_emulator_harness_present"]),
            "firestore_emulator_host_env_present": bool(inventory["firestore_emulator_host_env_present"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Emit BLOCKED readiness with safe local prerequisite detection only"
    )
    args = parser.parse_args()
    print(json.dumps(build_report(execute=args.execute), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
