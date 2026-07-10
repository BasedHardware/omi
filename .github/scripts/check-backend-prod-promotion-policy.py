#!/usr/bin/env python3
"""Guard the Python backend prod blessing gate in gcp_backend.yml."""

from pathlib import Path


WORKFLOW = Path(".github/workflows/gcp_backend.yml")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def require(needle: str, text: str, message: str) -> None:
    if needle not in text:
        fail(message)


def require_order(text: str, first: str, second: str, message: str) -> None:
    first_index = text.find(first)
    second_index = text.find(second)
    if first_index == -1 or second_index == -1 or first_index >= second_index:
        fail(message)


def job_block(text: str, job_name: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f"  {job_name}:":
            start = index
            break
    if start is None:
        fail(f"workflow is missing {job_name} job")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break
    return "\n".join(lines[start:end])


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    deploy_text = job_block(text, "deploy")
    repair_text = job_block(text, "repair-traffic")

    require("override_unblessed:", text, "backend prod deploy must expose override_unblessed")
    require("override_confirm:", text, "backend prod deploy must expose override_confirm")
    require("I-ACCEPT-UNBLESSED-PROD-RISK", text, "backend prod deploy must require typed override confirmation")
    if "Validate prod Python backend blessing" in repair_text:
        fail("repair-traffic must not carry the prod blessing gate; it does not deploy new code")
    require("Validate prod Python backend blessing", deploy_text, "deploy job must validate python-backend blessing")
    require("if: ${{ github.event.inputs.environment == 'prod' }}", deploy_text, "blessing gate must only block prod")
    require("check-python-backend-blessing.py", deploy_text, "deploy job must call the blessing validator")
    require("python-backend-bless-${TARGET_SHA}", deploy_text, "deploy job must look up the target SHA blessing")
    require("backend/scripts/bless-python-backend.sh", deploy_text, "deploy job must tell operators how to bless")
    require("DEPLOY_SHA=\"$(git rev-parse HEAD)\"", deploy_text, "deploy identity must use the checked-out ref")
    require("--tag-sha", deploy_text, "deploy job must verify the blessing tag points to the target SHA")
    require(
        "BLESSING_CHECK_ARGS=(",
        deploy_text,
        "workflow must keep blessing-check arguments populated when override is disabled under set -u",
    )
    if "OVERRIDE_ARGS=()" in deploy_text:
        fail("normal prod blessing check must not expand an empty optional array under set -u")
    require("Google Auth", deploy_text, "workflow must authenticate to GCP only after the prod blessing gate")
    require_order(
        deploy_text,
        "Validate prod Python backend blessing",
        "Google Auth",
        "prod blessing gate must run before GCP auth and deploy mutations",
    )
    require_order(
        deploy_text,
        "Validate prod Python backend blessing",
        "Build and Push Docker image",
        "prod blessing gate must run before image build/push",
    )
    require_order(
        deploy_text,
        "Validate prod Python backend blessing",
        "Deploy ${{ env.SERVICE }} to Cloud Run",
        "prod blessing gate must run before Cloud Run deploy",
    )

    print("backend prod promotion policy OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
