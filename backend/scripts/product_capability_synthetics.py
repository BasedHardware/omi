#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence, cast

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from llm_gateway.gateway.auth import LEGACY_SERVICE_TOKEN_ENV_VAR, PRIMARY_SERVICE_TOKEN_ENV_VAR
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider
from llm_gateway.main import app as llm_gateway_app
from llm_gateway.routers import dependencies as llm_gateway_dependencies

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIP_NO_CREDENTIALS = "SKIP_NO_CREDENTIALS"
STATUS_NOT_RUN = "NOT_RUN"
VALID_STATUSES = {STATUS_PASS, STATUS_FAIL, STATUS_SKIP_NO_CREDENTIALS, STATUS_NOT_RUN}

SENSITIVE_PATTERNS = [
    re.compile(r"omi_(?:oat|ort|mcp)_[A-Za-z0-9._~+-]+"),
    re.compile(r"sk-[A-Za-z0-9._-]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(client_secret[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+"),
    re.compile(r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+"),
    re.compile(r"(?i)(token[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+"),
]


@dataclass(frozen=True)
class SyntheticConfig:
    backend_url: str | None
    run_local_fixtures: bool
    timeout_seconds: float
    e2e_timeout: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    summary: str
    details: dict[str, Any]
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid synthetic status: {self.status}")
        return {
            "name": self.name,
            "status": self.status,
            "summary": sanitize(self.summary),
            "duration_ms": self.duration_ms,
            "details": sanitize(self.details),
        }


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        typed: Dict[str, Any] = cast(Dict[str, Any], value)
        return {key: sanitize(item) for key, item in typed.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in cast(List[Any], value)]
    if isinstance(value, tuple):
        return [sanitize(item) for item in cast(List[Any], value)]
    if isinstance(value, str):
        redacted = value
        for pattern in SENSITIVE_PATTERNS:
            redacted = pattern.sub(
                lambda match: f"{match.group(1)}[REDACTED]" if match.groups() else "[REDACTED]", redacted
            )
        return redacted
    return value


def timed_check(name: str, fn: Callable[[], tuple[str, str, dict[str, Any]]]) -> CheckResult:
    started = time.monotonic()
    try:
        status, summary, details = fn()
    except Exception as exc:  # noqa: BLE001 - synthetic output should survive unexpected probe errors
        status = STATUS_FAIL
        summary = f"{name} raised {exc.__class__.__name__}"
        details = {"error": str(exc)}
    return CheckResult(
        name=name,
        status=status,
        summary=summary,
        details=details,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def _http_get_json(url: str, timeout_seconds: float) -> tuple[int, dict[str, Any] | None, str]:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(body), body
            except ValueError:
                return response.status, None, body
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return exc.code, None, body


def backend_health_check(config: SyntheticConfig) -> tuple[str, str, dict[str, Any]]:
    if not config.backend_url:
        return (
            STATUS_NOT_RUN,
            "Set OMI_SYNTHETIC_BACKEND_URL or pass --backend-url to check the deployed/local backend health route.",
            {"required": ["backend_url"], "traced_route": "/v1/health"},
        )

    url = f"{config.backend_url.rstrip('/')}/v1/health"
    status_code, body, raw_body = _http_get_json(url, config.timeout_seconds)
    if status_code == 200 and body and body.get("status") == "ok":
        return STATUS_PASS, "Backend health route returned status=ok.", {"url": url, "status_code": status_code}
    return (
        STATUS_FAIL,
        f"Backend health route returned HTTP {status_code} without status=ok.",
        {"url": url, "status_code": status_code, "body": body or raw_body[:500]},
    )


def mcp_oauth_metadata_check(config: SyntheticConfig) -> tuple[str, str, dict[str, Any]]:
    if not config.backend_url:
        return (
            STATUS_NOT_RUN,
            "Set OMI_SYNTHETIC_BACKEND_URL or pass --backend-url to check MCP/OAuth metadata.",
            {
                "required": ["backend_url"],
                "routes": ["/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server"],
            },
        )

    base_url = config.backend_url.rstrip("/")
    resource_url = f"{base_url}/.well-known/oauth-protected-resource"
    authz_url = f"{base_url}/.well-known/oauth-authorization-server"
    resource_status, resource_body, resource_raw = _http_get_json(resource_url, config.timeout_seconds)
    authz_status, authz_body, authz_raw = _http_get_json(authz_url, config.timeout_seconds)

    problems: list[str] = []
    if resource_status != 200 or not resource_body:
        problems.append("protected resource metadata unavailable")
    elif not resource_body.get("authorization_servers") or "memories.read" not in resource_body.get(
        "scopes_supported", []
    ):
        problems.append("protected resource metadata missing OAuth server or memories.read scope")
    if authz_status != 200 or not authz_body:
        problems.append("authorization server metadata unavailable")
    elif "authorization_code" not in authz_body.get("grant_types_supported", []) or "S256" not in authz_body.get(
        "code_challenge_methods_supported", []
    ):
        problems.append("authorization metadata missing authorization_code or S256 support")

    details = {
        "resource_url": resource_url,
        "resource_status_code": resource_status,
        "authorization_server_url": authz_url,
        "authorization_server_status_code": authz_status,
        "resource_body": resource_body or resource_raw[:500],
        "authorization_server_body": authz_body or authz_raw[:500],
    }
    if problems:
        return STATUS_FAIL, "; ".join(problems), details
    return STATUS_PASS, "MCP/OAuth discovery metadata is reachable and advertises required capabilities.", details


def llm_gateway_fake_provider_check(config: SyntheticConfig) -> tuple[str, str, dict[str, Any]]:
    sentinel_token = "product-synthetic-sentinel-token"
    service_token_env_vars = (PRIMARY_SERVICE_TOKEN_ENV_VAR, LEGACY_SERVICE_TOKEN_ENV_VAR)
    previous_service_tokens = {env_var: os.environ.get(env_var) for env_var in service_token_env_vars}
    for env_var in service_token_env_vars:
        os.environ[env_var] = sentinel_token

    provider = FakeChatCompletionProvider()
    llm_gateway_app.dependency_overrides[llm_gateway_dependencies.get_provider_registry] = lambda: ProviderRegistry(
        {"openai": provider}
    )
    try:
        response = TestClient(llm_gateway_app).post(
            "/v1/chat/completions",
            headers={
                "authorization": f"Bearer {sentinel_token}",
                "x-omi-service-caller": "backend",
                "x-omi-user-uid": "synthetic-product-capability-user",
            },
            json={
                "model": "omi:auto:chat-structured",
                "messages": [{"role": "user", "content": "Return a JSON object with capability true."}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ProductCapabilitySynthetic",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"capability": {"type": "boolean"}},
                            "required": ["capability"],
                            "additionalProperties": False,
                        },
                    },
                },
            },
        )
    finally:
        llm_gateway_app.dependency_overrides.clear()
        for env_var, previous_value in previous_service_tokens.items():
            if previous_value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = previous_value

    if response.status_code != 200:
        return (
            STATUS_FAIL,
            f"LLM gateway fake-provider chat auth smoke returned HTTP {response.status_code}.",
            {"status_code": response.status_code, "body": response.text[:500]},
        )
    body = response.json()
    if body.get("object") != "chat.completion" or body.get("model") != "omi:auto:chat-structured" or not provider.calls:
        return STATUS_FAIL, "LLM gateway response did not match the OpenAI-compatible chat contract.", {"body": body}
    return (
        STATUS_PASS,
        "LLM gateway service-auth and OpenAI-compatible chat path passed with fake provider.",
        {
            "status_code": response.status_code,
            "provider_calls": len(provider.calls),
            "network_or_provider_calls": False,
        },
    )


def _pytest_k_expression(pytest_target: str) -> str:
    return pytest_target.rsplit("::", maxsplit=1)[-1]


def _run_e2e_selection(config: SyntheticConfig, name: str, pytest_target: str) -> tuple[str, str, dict[str, Any]]:
    if not config.run_local_fixtures:
        return (
            STATUS_NOT_RUN,
            "Local fixture checks were disabled with --no-local-fixtures.",
            {"pytest_target": pytest_target},
        )

    pytest_k_expression = _pytest_k_expression(pytest_target)
    command = ["bash", str(BACKEND_DIR / "testing" / "e2e" / "run.sh"), "-q", "-k", pytest_k_expression]
    env = os.environ.copy()
    env["E2E_PYTEST_TIMEOUT"] = config.e2e_timeout
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=config.timeout_seconds + 180,
        check=False,
    )
    output = completed.stdout[-4000:]
    if completed.returncode == 0:
        return (
            STATUS_PASS,
            f"{name} passed through the hermetic e2e harness.",
            {"command": command, "pytest_target": pytest_target, "output_tail": output},
        )
    if (
        "E2E test dependencies are not installed" in completed.stdout
        or "Backend dependencies not installed" in completed.stdout
    ):
        return (
            STATUS_NOT_RUN,
            f"{name} did not run because local harness dependencies are missing.",
            {
                "command": command,
                "pytest_target": pytest_target,
                "exit_code": completed.returncode,
                "output_tail": output,
            },
        )
    return (
        STATUS_FAIL,
        f"{name} failed through the hermetic e2e harness.",
        {"command": command, "pytest_target": pytest_target, "exit_code": completed.returncode, "output_tail": output},
    )


def conversation_processing_fixture_check(config: SyntheticConfig) -> tuple[str, str, dict[str, Any]]:
    return _run_e2e_selection(
        config,
        "Conversation processing fixture",
        "testing/e2e/test_conversation_processing.py::test_conversation_create_process_finalize_lifecycle",
    )


def listen_protocol_fixture_check(config: SyntheticConfig) -> tuple[str, str, dict[str, Any]]:
    return _run_e2e_selection(
        config,
        "Listen custom-STT protocol fixture",
        "testing/e2e/test_listen_stt.py::test_web_listen_custom_stt_suggested_transcript_is_emitted_and_persisted",
    )


def build_report(config: SyntheticConfig) -> dict[str, Any]:
    checks = [
        timed_check("backend_health", lambda: backend_health_check(config)),
        timed_check("llm_gateway_chat_fake_provider", lambda: llm_gateway_fake_provider_check(config)),
        timed_check("conversation_processing_local_fixture", lambda: conversation_processing_fixture_check(config)),
        timed_check("mcp_oauth_metadata", lambda: mcp_oauth_metadata_check(config)),
        timed_check("listen_protocol_local_fixture", lambda: listen_protocol_fixture_check(config)),
    ]
    counts = {status: sum(1 for check in checks if check.status == status) for status in sorted(VALID_STATUSES)}
    overall_status = STATUS_FAIL if counts[STATUS_FAIL] else STATUS_PASS
    if counts[STATUS_PASS] == 0 and not counts[STATUS_FAIL]:
        overall_status = STATUS_NOT_RUN
    return {
        "suite": "omi_product_capability_synthetics",
        "status": overall_status,
        "status_vocabulary": sorted(VALID_STATUSES),
        "secret_safety": {
            "uses_production_credentials": False,
            "uses_production_user_data": False,
            "redaction_applied": True,
            "fixture_policy": "fake sentinel tokens and local synthetic fixtures only",
        },
        "summary": counts,
        "checks": [check.to_dict() for check in checks],
    }


def print_human_summary(report: dict[str, Any]) -> None:
    print(f"Omi product-capability synthetics: {report['status']}")
    for check in report["checks"]:
        print(f"- {check['status']} {check['name']}: {check['summary']}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run safe Omi product-capability synthetic checks.")
    parser.add_argument("--backend-url", default=os.environ.get("OMI_SYNTHETIC_BACKEND_URL"))
    parser.add_argument("--json-only", action="store_true", help="Emit machine-readable JSON only.")
    parser.add_argument("--no-local-fixtures", action="store_true", help="Skip hermetic e2e fixture checks.")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--e2e-timeout", default=os.environ.get("E2E_PYTEST_TIMEOUT", "120s"))
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> SyntheticConfig:
    return SyntheticConfig(
        backend_url=(args.backend_url or "").strip() or None,
        run_local_fixtures=not args.no_local_fixtures,
        timeout_seconds=args.timeout_seconds,
        e2e_timeout=args.e2e_timeout,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = build_report(config_from_args(args))
    if args.json_only:
        print(json.dumps(sanitize(report), indent=2, sort_keys=True))
    else:
        print_human_summary(report)
        print("\nJSON:")
        print(json.dumps(sanitize(report), indent=2, sort_keys=True))
    return 1 if report["status"] == STATUS_FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
