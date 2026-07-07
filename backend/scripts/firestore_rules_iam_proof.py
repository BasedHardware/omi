#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, cast

DEFAULT_DATABASE = "(default)"
DEFAULT_WORKER_SA_NAME = "memory-vector-repair-outbox-worker"
DEFAULT_BACKEND_SA_NAME = "backend"
OUTBOX_PATH = "users/{uid}/memory_outbox/{record_id}"
MEMORY_CONTROL_PATH = "users/{uid}/memory_control/state"
APP_KEY_GRANTS_PATH = "users/{uid}/memory_control/app_key_memory_grants"
MCP_API_KEY_PATH = "mcp_api_keys/{key_id}"
VECTOR_REPAIR_GATE = "vector_repair_outbox_enabled"

READ_ONLY_COMMAND_PREFIXES = (
    "gcloud firestore databases describe",
    "gcloud projects get-iam-policy",
    "gcloud iam service-accounts get-iam-policy",
    "firebase firestore:rules:get",
)

FORBIDDEN_MUTATING_TERMS = (
    "firebase deploy",
    "gcloud firestore databases update",
    "gcloud firestore databases create",
    "gcloud firestore databases delete",
    "gcloud projects set-iam-policy",
    "gcloud iam service-accounts set-iam-policy",
    "add-iam-policy-binding",
    "remove-iam-policy-binding",
    "set-iam-policy",
)


@dataclass(frozen=True)
class FirestoreRulesIamProofConfig:
    project: str
    database: str
    worker_sa: str
    backend_sa: str


def default_service_account(name: str, project: str) -> str:
    return f"{name}@{project}.iam.gserviceaccount.com"


def command_to_string(command: Sequence[str]) -> str:
    return " ".join(command)


def build_read_only_commands(config: FirestoreRulesIamProofConfig) -> Dict[str, List[str]]:
    """Build read-only production Firestore IAM/deployed-rules inventory commands.

    Pass/fail criteria covered by the runner:
    - client_denial.memory_outbox: deployed rules deny client access to
      users/{uid}/memory_outbox/{record_id}; Admin SDK/IAM worker access is required.
    - memory_control.server_owned: deployed rules keep users/{uid}/memory_control/state
      server-owned, including the vector_repair_outbox_enabled rollout gate.
    - app_key_grants.server_owned: deployed rules keep
      users/{uid}/memory_control/app_key_memory_grants server-owned.
    - mcp_api_key_inventory: deployed rules deny client access to mcp_api_keys/{key_id};
      MCP API-key inventory/migration must use Admin IAM context only.
    - no_client_vector_repair_enablement: clients cannot set vector_repair_outbox_enabled.
    - worker_firestore_iam: Admin worker service account has Firestore IAM and no owner/editor.
    - no_broad_public_access: project IAM policy has no allUsers/allAuthenticatedUsers members.
    """
    return {
        "firestore_database": [
            "gcloud",
            "firestore",
            "databases",
            "describe",
            config.database,
            "--project",
            config.project,
            "--format=json",
        ],
        "project_iam": [
            "gcloud",
            "projects",
            "get-iam-policy",
            config.project,
            "--format=json",
        ],
        "worker_service_account_iam": [
            "gcloud",
            "iam",
            "service-accounts",
            "get-iam-policy",
            config.worker_sa,
            "--project",
            config.project,
            "--format=json",
        ],
        "backend_service_account_iam": [
            "gcloud",
            "iam",
            "service-accounts",
            "get-iam-policy",
            config.backend_sa,
            "--project",
            config.project,
            "--format=json",
        ],
        "deployed_firestore_rules": [
            "firebase",
            "firestore:rules:get",
            "--project",
            config.project,
        ],
    }


def assert_commands_are_read_only(commands: Mapping[str, Sequence[str]]) -> None:
    for name, command in commands.items():
        command_text = command_to_string(command)
        if not any(command_text.startswith(prefix) for prefix in READ_ONLY_COMMAND_PREFIXES):
            raise ValueError(f"{name} is not an allowlisted read-only proof command: {command_text}")
        for forbidden in FORBIDDEN_MUTATING_TERMS:
            if forbidden in command_text:
                raise ValueError(f"{name} contains forbidden mutating command term {forbidden}: {command_text}")


def run_commands(commands: Mapping[str, Sequence[str]]) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for name, command in commands.items():
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        result: Dict[str, Any] = {
            "command": command_to_string(command),
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        if completed.returncode == 0 and completed.stdout.strip() and command[0] == "gcloud":
            try:
                result["json"] = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                result["json_error"] = str(exc)
        results[name] = result
    return results


def evaluate_results(
    config: FirestoreRulesIamProofConfig, command_results: Mapping[str, Mapping[str, Any]]
) -> List[Dict[str, str]]:
    checks: List[Dict[str, str]] = []
    for name, result in command_results.items():
        if int(result.get("exit_code", 1)) != 0:
            checks.append(
                fail(name, f"read-only command failed: {result.get('stderr') or result.get('stdout') or 'no output'}")
            )

    database = json_result(command_results, "firestore_database")
    project_iam = json_result(command_results, "project_iam")
    rules_text = str(command_results.get("deployed_firestore_rules", {}).get("stdout", ""))
    worker_sa_policy = json_result(command_results, "worker_service_account_iam")
    backend_sa_policy = json_result(command_results, "backend_service_account_iam")

    if database:
        checks.extend(evaluate_firestore_database(database))
    if project_iam:
        checks.extend(evaluate_project_iam(config, project_iam))
    if rules_text:
        checks.extend(evaluate_deployed_rules(rules_text))
    if worker_sa_policy:
        checks.extend(evaluate_service_account_policy("worker_service_account_iam", worker_sa_policy))
    if backend_sa_policy:
        checks.extend(evaluate_service_account_policy("backend_service_account_iam", backend_sa_policy))
    return checks


def json_result(command_results: Mapping[str, Mapping[str, Any]], name: str) -> Optional[Mapping[str, Any]]:
    value = command_results.get(name, {}).get("json")
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else None


def evaluate_firestore_database(database: Mapping[str, Any]) -> List[Dict[str, str]]:
    return [
        check("firestore_database.exists", bool(database.get("name")), "Firestore database describe returned metadata"),
        check(
            "firestore_database.not_delete_protected_assumption_only",
            True,
            "database metadata was inventoried read-only; no database settings were mutated",
        ),
    ]


def evaluate_project_iam(config: FirestoreRulesIamProofConfig, policy: Mapping[str, Any]) -> List[Dict[str, str]]:
    worker_member = f"serviceAccount:{config.worker_sa}"
    backend_member = f"serviceAccount:{config.backend_sa}"
    public_members = {"allUsers", "allAuthenticatedUsers"}
    broad_public = [
        f"{binding.get('role')}:{member}"
        for binding in policy.get("bindings", [])
        for member in binding.get("members", [])
        if member in public_members
    ]
    elevated_roles = {"roles/owner", "roles/editor"}
    worker_elevated = [role for role in elevated_roles if has_binding(policy, role, worker_member)]
    backend_elevated = [role for role in elevated_roles if has_binding(policy, role, backend_member)]
    return [
        check(
            "worker_firestore_iam",
            has_firestore_role(policy, worker_member),
            f"Admin worker service account must have roles/datastore.user or a narrower custom Firestore role: {worker_member}",
        ),
        check(
            "backend_firestore_iam",
            has_firestore_role(policy, backend_member),
            f"backend/Admin service account must have roles/datastore.user or a narrower custom Firestore role: {backend_member}",
        ),
        check(
            "worker_not_owner_editor",
            not worker_elevated,
            "worker service account must not have roles/owner or roles/editor",
        ),
        check(
            "backend_not_owner_editor",
            not backend_elevated,
            "backend service account should not have roles/owner or roles/editor for memory Firestore access",
        ),
        check(
            "no_broad_public_access",
            not broad_public,
            "project IAM must not include public allUsers/allAuthenticatedUsers",
        ),
    ]


def evaluate_service_account_policy(prefix: str, policy: Mapping[str, Any]) -> List[Dict[str, str]]:
    public_members = {"allUsers", "allAuthenticatedUsers"}
    public_bindings = [
        f"{binding.get('role')}:{member}"
        for binding in policy.get("bindings", [])
        for member in binding.get("members", [])
        if member in public_members
    ]
    return [check(f"{prefix}.no_public_members", not public_bindings, "service-account IAM policy must not be public")]


def evaluate_deployed_rules(rules_text: str) -> List[Dict[str, str]]:
    compact = " ".join(rules_text.split())
    has_outbox = "memory_outbox" in rules_text
    has_control = "memory_control" in rules_text
    has_app_key_grants = "app_key_memory_grants" in rules_text or has_control
    has_mcp_api_keys = "mcp_api_keys" in rules_text or "match /{document=**}" in rules_text
    denies_clients = (
        "allow read, create, update, delete: if false" in compact or "allow read, write: if false" in compact
    )
    server_owned_comment = "server-owned" in rules_text or "Admin SDK" in rules_text
    vector_gate_not_allowed = VECTOR_REPAIR_GATE not in rules_text or denies_clients
    return [
        check(
            "client_denial.memory_outbox",
            has_outbox and denies_clients,
            f"deployed rules must deny client read/write on {OUTBOX_PATH}",
        ),
        check(
            "client_denial.memory_control",
            has_control and denies_clients,
            f"deployed rules must deny client writes on {MEMORY_CONTROL_PATH}",
        ),
        check(
            "memory_control.server_owned",
            has_control and server_owned_comment and denies_clients,
            "memory_control paths must remain server-owned/Admin SDK only",
        ),
        check(
            "client_denial.app_key_memory_grants",
            has_app_key_grants and denies_clients,
            f"deployed rules must deny client read/write on {APP_KEY_GRANTS_PATH}",
        ),
        check(
            "app_key_grants.server_owned",
            has_app_key_grants and server_owned_comment and denies_clients,
            "memory app/key memory grants must remain server-owned/Admin SDK only",
        ),
        check(
            "mcp_api_key_inventory",
            has_mcp_api_keys and denies_clients,
            f"deployed rules must deny client read/write on {MCP_API_KEY_PATH}; Admin inventory only",
        ),
        check(
            "no_client_vector_repair_enablement",
            has_control and vector_gate_not_allowed,
            "clients must not be able to enable vector_repair_outbox_enabled through deployed rules",
        ),
    ]


def has_firestore_role(policy: Mapping[str, Any], member: str) -> bool:
    return has_binding(policy, "roles/datastore.user", member) or any(
        str(binding.get("role", "")).startswith("projects/") and member in binding.get("members", [])
        for binding in policy.get("bindings", [])
    )


def has_binding(policy: Mapping[str, Any], role: str, member: str) -> bool:
    return any(
        binding.get("role") == role and member in binding.get("members", []) for binding in policy.get("bindings", [])
    )


def check(name: str, ok: bool, message: str) -> Dict[str, str]:
    return {"name": name, "status": "PASS" if ok else "FAIL", "message": message}


def fail(name: str, message: str) -> Dict[str, str]:
    return {"name": name, "status": "FAIL", "message": message}


def build_config(args: argparse.Namespace) -> FirestoreRulesIamProofConfig:
    project = args.project.strip() if args.project else ""
    database = args.database.strip() if args.database else DEFAULT_DATABASE
    worker_sa = args.worker_sa.strip() if args.worker_sa else default_service_account(DEFAULT_WORKER_SA_NAME, project)
    backend_sa = (
        args.backend_sa.strip() if args.backend_sa else default_service_account(DEFAULT_BACKEND_SA_NAME, project)
    )
    return FirestoreRulesIamProofConfig(project=project, database=database, worker_sa=worker_sa, backend_sa=backend_sa)


def missing_prerequisites(config: FirestoreRulesIamProofConfig, *, execute: bool) -> List[str]:
    missing: List[str] = []
    if not config.project:
        missing.append("--project or MEMORY_FIRESTORE_PROOF_PROJECT is required")
    if execute and shutil.which("gcloud") is None:
        missing.append("gcloud CLI is not installed or not on PATH")
    if execute and shutil.which("firebase") is None:
        missing.append("firebase CLI is not installed or not on PATH")
    return missing


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Firestore IAM and deployed Security Rules proof runner for memory vector repair outbox paths."
    )
    parser.add_argument("--project", default="")
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--worker-sa", default="")
    parser.add_argument("--backend-sa", default="")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run read-only gcloud/firebase describe/get commands against the target project.",
    )
    return parser.parse_args(argv)


def apply_env_defaults(args: argparse.Namespace, env: Mapping[str, str]) -> argparse.Namespace:
    if not args.project:
        args.project = env.get("MEMORY_FIRESTORE_PROOF_PROJECT", "")
    return args


def main(argv: Optional[Sequence[str]] = None, env: Optional[Mapping[str, str]] = None) -> int:
    effective_env = os.environ if env is None else env
    args = apply_env_defaults(parse_args(argv), effective_env)
    config = build_config(args)
    commands = build_read_only_commands(config)
    assert_commands_are_read_only(commands)
    missing = missing_prerequisites(config, execute=args.execute)

    summary: Dict[str, Any] = {
        "status": "NOT_RUN",
        "execute": bool(args.execute),
        "project": config.project or None,
        "database": config.database,
        "worker_sa": config.worker_sa if config.project else None,
        "backend_sa": config.backend_sa if config.project else None,
        "read_only": True,
        "commands": {name: command_to_string(command) for name, command in commands.items()},
        "checks": [],
        "pass_fail_criteria": [
            f"client_denial.memory_outbox: deployed Security Rules deny client read/create/update/delete on {OUTBOX_PATH}",
            f"client_denial.app_key_memory_grants: deployed Security Rules deny client read/create/update/delete on {APP_KEY_GRANTS_PATH}",
            f"mcp_api_key_inventory: deployed Security Rules/IAM proof includes {MCP_API_KEY_PATH} inventory as Admin-only",
            "worker_firestore_iam: Admin worker service account has Firestore read/write IAM and no owner/editor",
            f"memory_control.server_owned: {MEMORY_CONTROL_PATH} remains Admin/server-owned",
            f"app_key_grants.server_owned: {APP_KEY_GRANTS_PATH} remains Admin/server-owned",
            "no_client_vector_repair_enablement: no client enablement of vector_repair_outbox_enabled is possible",
            "no_broad_public_access: project and service-account IAM have no allUsers/allAuthenticatedUsers broad public access",
        ],
        "prerequisites": missing,
        "non_claims": [
            "production Firestore IAM/deployed rules validation is not claimed unless --execute runs and every check passes",
            "MCP API-key scope inventory and memory app/key memory grant assignment are not migrated by this runner",
            "this runner never deploys Security Rules, mutates Firestore databases, or changes IAM",
            "real Pinecone duplicate stale physical ID delete/repair validation remains open",
            "shared ns2 isolation evidence remains open",
        ],
    }

    if missing:
        print(json.dumps(summary, sort_keys=True))
        return 2 if args.execute else 0
    if not args.execute:
        print(json.dumps(summary, sort_keys=True))
        return 0

    command_results = run_commands(commands)
    checks = evaluate_results(config, command_results)
    failed = [item for item in checks if item.get("status") == "FAIL"]
    summary["status"] = "FAIL" if failed else "PASS"
    summary["checks"] = checks
    summary["command_results"] = command_results
    print(json.dumps(summary, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
