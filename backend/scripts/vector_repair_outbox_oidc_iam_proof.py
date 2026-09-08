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

WORKER_ENABLED_ENV = "MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED"
DEFAULT_SERVICE = "memory-vector-repair-outbox-worker"
DEFAULT_SCHEDULER_JOB = "memory-vector-repair-outbox-worker-tick"
DEFAULT_TASKS_QUEUE = "memory-vector-repair-outbox-worker"
DEFAULT_WORKER_SA_NAME = "memory-vector-repair-outbox-worker"
DEFAULT_SCHEDULER_SA_NAME = "memory-vector-repair-scheduler"
TICK_PATH = "/memory-vector-repair-outbox-worker/tick"

READ_ONLY_GCLOUD_VERBS = (
    "gcloud run services describe",
    "gcloud run services get-iam-policy",
    "gcloud scheduler jobs describe",
    "gcloud tasks queues describe",
    "gcloud projects get-iam-policy",
    "gcloud iam service-accounts get-iam-policy",
)

FORBIDDEN_MUTATING_GCLOUD_TERMS = (
    "add-iam-policy-binding",
    "set-iam-policy",
    "deploy",
    "update",
    "create",
    "resume",
    "pause",
    "remove-iam-policy-binding",
)


@dataclass(frozen=True)
class ProofConfig:
    project: str
    region: str
    service: str
    scheduler_job: str
    tasks_queue: str
    worker_sa: str
    scheduler_sa: str
    expected_audience: str


def default_service_account(name: str, project: str) -> str:
    return f"{name}@{project}.iam.gserviceaccount.com"


def default_audience(region: str, project: str, service: str) -> str:
    return f"https://{region}-{project}.run.app/{service}/tick"


def build_read_only_gcloud_commands(config: ProofConfig) -> Dict[str, List[str]]:
    """Return only read-only gcloud proof commands.

    The required proof targets are intentionally explicit:
    - gcloud run services describe checks serviceAccountName and
      MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED remains false.
    - gcloud run services get-iam-policy checks roles/run.invoker and rejects
      allUsers/allAuthenticatedUsers.
    - gcloud scheduler jobs describe checks state == PAUSED plus
      oidcToken.serviceAccountEmail and oidcToken.audience.
    - gcloud tasks queues describe checks queue retry/concurrency shape.
    - gcloud projects get-iam-policy checks roles/datastore.user for the worker.
    - gcloud iam service-accounts get-iam-policy checks
      roles/iam.serviceAccountTokenCreator on the scheduler identity.
    """
    return {
        "run_service": [
            "gcloud",
            "run",
            "services",
            "describe",
            config.service,
            "--region",
            config.region,
            "--project",
            config.project,
            "--format=json",
        ],
        "run_iam": [
            "gcloud",
            "run",
            "services",
            "get-iam-policy",
            config.service,
            "--region",
            config.region,
            "--project",
            config.project,
            "--format=json",
        ],
        "scheduler_job": [
            "gcloud",
            "scheduler",
            "jobs",
            "describe",
            config.scheduler_job,
            "--location",
            config.region,
            "--project",
            config.project,
            "--format=json",
        ],
        "tasks_queue": [
            "gcloud",
            "tasks",
            "queues",
            "describe",
            config.tasks_queue,
            "--location",
            config.region,
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
        "scheduler_service_account_iam": [
            "gcloud",
            "iam",
            "service-accounts",
            "get-iam-policy",
            config.scheduler_sa,
            "--project",
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
    }


def assert_commands_are_read_only(commands: Mapping[str, Sequence[str]]) -> None:
    for name, command in commands.items():
        command_text = command_to_string(command)
        if not any(command_text.startswith(prefix) for prefix in READ_ONLY_GCLOUD_VERBS):
            raise ValueError(f"{name} is not an allowlisted read-only gcloud proof command: {command_text}")
        for forbidden in FORBIDDEN_MUTATING_GCLOUD_TERMS:
            if forbidden in command:
                raise ValueError(f"{name} contains forbidden mutating gcloud term {forbidden}: {command_text}")


def command_to_string(command: Sequence[str]) -> str:
    return " ".join(command)


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
        if completed.returncode == 0 and completed.stdout.strip():
            try:
                result["json"] = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                result["json_error"] = str(exc)
        results[name] = result
    return results


def evaluate_results(config: ProofConfig, command_results: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, str]]:
    checks: List[Dict[str, str]] = []
    for name, result in command_results.items():
        if int(result.get("exit_code", 1)) != 0:
            checks.append(
                fail(name, f"read-only command failed: {result.get('stderr') or result.get('stdout') or 'no output'}")
            )

    service = json_result(command_results, "run_service")
    run_iam = json_result(command_results, "run_iam")
    scheduler = json_result(command_results, "scheduler_job")
    tasks_queue = json_result(command_results, "tasks_queue")
    project_iam = json_result(command_results, "project_iam")
    scheduler_sa_iam = json_result(command_results, "scheduler_service_account_iam")

    if service:
        checks.extend(evaluate_run_service(config, service))
    if run_iam:
        checks.extend(evaluate_run_iam(config, run_iam))
    if scheduler:
        checks.extend(evaluate_scheduler_job(config, scheduler))
    if tasks_queue:
        checks.extend(evaluate_tasks_queue(tasks_queue))
    if project_iam:
        checks.extend(evaluate_project_iam(config, project_iam))
    if scheduler_sa_iam:
        checks.extend(evaluate_scheduler_sa_iam(scheduler_sa_iam))
    return checks


def json_result(command_results: Mapping[str, Mapping[str, Any]], name: str) -> Optional[Mapping[str, Any]]:
    value = command_results.get(name, {}).get("json")
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    return None


def evaluate_run_service(config: ProofConfig, service: Mapping[str, Any]) -> List[Dict[str, str]]:
    template = service.get("spec", {}).get("template", {}).get("spec", {})
    env_values = extract_container_env(template.get("containers", []))
    checks = [
        check(
            "run_service.worker_service_account",
            template.get("serviceAccountName") == config.worker_sa,
            f"serviceAccountName must equal {config.worker_sa}",
        ),
        check(
            "run_service.worker_disabled_env",
            env_values.get(WORKER_ENABLED_ENV) == "false",
            f"{WORKER_ENABLED_ENV} must remain false",
        ),
    ]
    ingress = service.get("metadata", {}).get("annotations", {}).get("run.googleapis.com/ingress")
    invoker_disabled = service.get("metadata", {}).get("annotations", {}).get("run.googleapis.com/invoker-iam-disabled")
    checks.append(
        check(
            "run_service.ingress_restricted",
            ingress in {"internal", "internal-and-cloud-load-balancing"},
            "Cloud Run ingress must be restricted",
        )
    )
    checks.append(
        check(
            "run_service.invoker_iam_required",
            invoker_disabled in {None, "false", False},
            "Cloud Run invoker IAM must remain required",
        )
    )
    return checks


def extract_container_env(containers: Any) -> Dict[str, str]:
    env_values: Dict[str, str] = {}
    if not isinstance(containers, list):
        return env_values
    items: List[Any] = cast(List[Any], containers)
    for container in items:
        if not isinstance(container, Mapping):
            continue
        container_mapping: Mapping[str, Any] = cast(Mapping[str, Any], container)
        env_list_raw = container_mapping.get("env", [])
        if not isinstance(env_list_raw, list):
            continue
        env_list: List[Any] = cast(List[Any], env_list_raw)
        for env in env_list:
            if not isinstance(env, Mapping):
                continue
            env_mapping: Mapping[str, Any] = cast(Mapping[str, Any], env)
            name = env_mapping.get("name")
            if isinstance(name, str) and "value" in env_mapping:
                env_values[name] = str(env_mapping.get("value"))
    return env_values


def evaluate_run_iam(config: ProofConfig, policy: Mapping[str, Any]) -> List[Dict[str, str]]:
    bindings = policy.get("bindings", [])
    public_members = {"allUsers", "allAuthenticatedUsers"}
    public_invokers = [
        member
        for binding in bindings
        if binding.get("role") == "roles/run.invoker"
        for member in binding.get("members", [])
        if member in public_members
    ]
    scheduler_member = f"serviceAccount:{config.scheduler_sa}"
    has_scheduler_invoker = has_binding(policy, "roles/run.invoker", scheduler_member)
    return [
        check("run_iam.no_public_invoker", not public_invokers, "roles/run.invoker must not include public members"),
        check("run_iam.scheduler_invoker", has_scheduler_invoker, f"roles/run.invoker must include {scheduler_member}"),
    ]


def evaluate_scheduler_job(config: ProofConfig, job: Mapping[str, Any]) -> List[Dict[str, str]]:
    http_target = job.get("httpTarget", {})
    oidc_token = http_target.get("oidcToken", {})
    return [
        check("scheduler.state_paused", job.get("state") == "PAUSED", "state == PAUSED"),
        check("scheduler.method_post", http_target.get("httpMethod") == "POST", "httpMethod must be POST"),
        check(
            "scheduler.oidc_service_account",
            oidc_token.get("serviceAccountEmail") == config.scheduler_sa,
            "oidcToken.serviceAccountEmail must match scheduler service account",
        ),
        check(
            "scheduler.oidc_audience",
            oidc_token.get("audience") == config.expected_audience,
            "oidcToken.audience must match worker tick URI",
        ),
    ]


def evaluate_tasks_queue(queue: Mapping[str, Any]) -> List[Dict[str, str]]:
    rate_limits = queue.get("rateLimits", {})
    retry = queue.get("retryConfig", {})
    return [
        check(
            "tasks_queue.single_concurrency",
            int(rate_limits.get("maxConcurrentDispatches", 0) or 0) == 1,
            "tasks queue maxConcurrentDispatches must be 1",
        ),
        check(
            "tasks_queue.retry_bounded",
            int(retry.get("maxAttempts", 0) or 0) <= 3 and bool(retry.get("maxRetryDuration")),
            "tasks queue retry must be bounded with maxRetryDuration",
        ),
    ]


def evaluate_project_iam(config: ProofConfig, policy: Mapping[str, Any]) -> List[Dict[str, str]]:
    worker_member = f"serviceAccount:{config.worker_sa}"
    has_firestore = has_binding(policy, "roles/datastore.user", worker_member) or any(
        binding.get("role", "").startswith("projects/") and worker_member in binding.get("members", [])
        for binding in policy.get("bindings", [])
    )
    elevated_roles = ["roles/owner", "roles/editor"]
    elevated = [role for role in elevated_roles if has_binding(policy, role, worker_member)]
    return [
        check(
            "project_iam.worker_firestore",
            has_firestore,
            f"worker service account must have roles/datastore.user or a narrower custom Firestore role: {worker_member}",
        ),
        check("project_iam.worker_not_owner_editor", not elevated, "worker service account must not have owner/editor"),
    ]


def evaluate_scheduler_sa_iam(policy: Mapping[str, Any]) -> List[Dict[str, str]]:
    has_token_creator = any(
        binding.get("role") == "roles/iam.serviceAccountTokenCreator" and binding.get("members")
        for binding in policy.get("bindings", [])
    )
    return [
        check(
            "scheduler_sa_iam.token_creator_present",
            has_token_creator,
            "scheduler service account IAM policy must include roles/iam.serviceAccountTokenCreator for the scheduler service agent",
        )
    ]


def has_binding(policy: Mapping[str, Any], role: str, member: str) -> bool:
    return any(
        binding.get("role") == role and member in binding.get("members", []) for binding in policy.get("bindings", [])
    )


def check(name: str, ok: bool, message: str) -> Dict[str, str]:
    return {"name": name, "status": "PASS" if ok else "FAIL", "message": message}


def fail(name: str, message: str) -> Dict[str, str]:
    return {"name": name, "status": "FAIL", "message": message}


def build_config(args: argparse.Namespace) -> ProofConfig:
    project = args.project.strip() if args.project else ""
    region = args.region.strip() if args.region else ""
    service = args.service.strip() if args.service else DEFAULT_SERVICE
    worker_sa = args.worker_sa.strip() if args.worker_sa else default_service_account(DEFAULT_WORKER_SA_NAME, project)
    scheduler_sa = (
        args.scheduler_sa.strip() if args.scheduler_sa else default_service_account(DEFAULT_SCHEDULER_SA_NAME, project)
    )
    expected_audience = args.audience.strip() if args.audience else default_audience(region, project, service)
    return ProofConfig(
        project=project,
        region=region,
        service=service,
        scheduler_job=args.scheduler_job.strip() if args.scheduler_job else DEFAULT_SCHEDULER_JOB,
        tasks_queue=args.tasks_queue.strip() if args.tasks_queue else DEFAULT_TASKS_QUEUE,
        worker_sa=worker_sa,
        scheduler_sa=scheduler_sa,
        expected_audience=expected_audience,
    )


def missing_prerequisites(config: ProofConfig, *, execute: bool) -> List[str]:
    missing: List[str] = []
    if not config.project:
        missing.append("--project or MEMORY_VECTOR_REPAIR_PROOF_PROJECT is required")
    if not config.region:
        missing.append("--region or MEMORY_VECTOR_REPAIR_PROOF_REGION is required")
    if execute and shutil.which("gcloud") is None:
        missing.append("gcloud CLI is not installed or not on PATH")
    return missing


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only OIDC/IAM proof runner for the disabled memory vector repair outbox HTTP worker."
    )
    parser.add_argument("--project", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--scheduler-job", default=DEFAULT_SCHEDULER_JOB)
    parser.add_argument("--tasks-queue", default=DEFAULT_TASKS_QUEUE)
    parser.add_argument("--worker-sa", default="")
    parser.add_argument("--scheduler-sa", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument(
        "--execute", action="store_true", help="Run the read-only gcloud describe/get-iam-policy commands."
    )
    parser.set_defaults(
        project="",
        region="",
    )
    return parser.parse_args(argv)


def apply_env_defaults(args: argparse.Namespace, env: Mapping[str, str]) -> argparse.Namespace:
    if not args.project:
        args.project = env.get("MEMORY_VECTOR_REPAIR_PROOF_PROJECT", "")
    if not args.region:
        args.region = env.get("MEMORY_VECTOR_REPAIR_PROOF_REGION", "")
    return args


def main(argv: Optional[Sequence[str]] = None, env: Optional[Mapping[str, str]] = None) -> int:
    if env is None:
        effective_env: Mapping[str, str] = os.environ
    else:
        effective_env = env
    args = apply_env_defaults(parse_args(argv), effective_env)
    config = build_config(args)
    commands = build_read_only_gcloud_commands(config)
    assert_commands_are_read_only(commands)
    missing = missing_prerequisites(config, execute=args.execute)

    summary: Dict[str, Any] = {
        "status": "NOT_RUN",
        "execute": bool(args.execute),
        "project": config.project or None,
        "region": config.region or None,
        "service": config.service,
        "scheduler_job": config.scheduler_job,
        "tasks_queue": config.tasks_queue,
        "worker_sa": config.worker_sa if config.project else None,
        "scheduler_sa": config.scheduler_sa if config.project else None,
        "expected_audience": config.expected_audience if config.project and config.region else None,
        "read_only": True,
        "commands": {name: command_to_string(command) for name, command in commands.items()},
        "checks": [],
        "prerequisites": missing,
        "non_claims": [
            "production OIDC/IAM proof is not claimed unless every read-only command executes and every check passes",
            "production Firestore IAM/deployed rules validation gates remain open unless separately proven",
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
