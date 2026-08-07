#!/usr/bin/env bash
# Scaffold a new Cloud Run Job stub set from the memory-maintenance-job template.
# Dry-run by default: writes under a temp directory and prints checklist TODOs.
# Does NOT create GCP resources, Secret Manager bindings, or Scheduler jobs.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scaffold_cloud_run_job.sh --job-name <kebab-name> [--apply <output-root>]

  --job-name   Required. Kebab-case Cloud Run job name, e.g. my-domain-job
  --apply DIR  Write stubs under DIR (default: mktemp dry-run directory)
  -h, --help   Show this help

Examples:
  backend/scripts/scaffold_cloud_run_job.sh --job-name example-cleanup-job
  backend/scripts/scaffold_cloud_run_job.sh --job-name example-cleanup-job --apply /tmp/example-stubs
EOF
}

JOB_NAME=""
APPLY_ROOT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job-name)
      JOB_NAME="${2:?}"
      shift 2
      ;;
    --apply)
      APPLY_ROOT="${2:?}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$JOB_NAME" ]]; then
  echo "--job-name is required" >&2
  usage >&2
  exit 2
fi

if [[ ! "$JOB_NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "job name must be kebab-case: $JOB_NAME" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE_ENTRY="$REPO_ROOT/backend/modal/memory_maintenance_job.py"
TEMPLATE_DOCKER="$REPO_ROOT/backend/modal/Dockerfile.memory_maintenance_job"
TEMPLATE_WORKFLOW="$REPO_ROOT/.github/workflows/gcp_memory_maintenance_job.yml"

for path in "$TEMPLATE_ENTRY" "$TEMPLATE_DOCKER" "$TEMPLATE_WORKFLOW"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing template: $path" >&2
    exit 1
  fi
done

SNAKE_NAME="${JOB_NAME//-/_}"
MODULE_NAME="${SNAKE_NAME}"
# Preserve an existing _job suffix so we do not double it (foo-job → foo_job).
if [[ "$MODULE_NAME" != *_job ]]; then
  MODULE_NAME="${MODULE_NAME}_job"
fi

DRY_RUN=0
if [[ -z "$APPLY_ROOT" ]]; then
  APPLY_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scaffold-cloud-run-job.XXXXXX")"
  DRY_RUN=1
fi

OUT_MODAL="$APPLY_ROOT/backend/modal"
OUT_WF="$APPLY_ROOT/.github/workflows"
mkdir -p "$OUT_MODAL" "$OUT_WF"

ENTRY_OUT="$OUT_MODAL/${MODULE_NAME}.py"
DOCKER_OUT="$OUT_MODAL/Dockerfile.${MODULE_NAME}"
WF_OUT="$OUT_WF/gcp_${MODULE_NAME}.yml"

# Entrypoint stub: Firebase init + placeholder runner call.
cat >"$ENTRY_OUT" <<EOF
"""Cloud Run Job entrypoint for ${JOB_NAME}.

TODO: replace run_${SNAKE_NAME} with the real domain runner.
Scheduler owns cadence — do not add hour-modulo gates here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import firebase_admin

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


async def run_${SNAKE_NAME}() -> None:
    """TODO: call the single domain module for this job."""
    raise NotImplementedError("scaffold stub — implement domain runner")


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        service_account_info = json.loads(service_account_json)
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials)  # type: ignore[reportUnknownMemberType]
    else:
        firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]


def main() -> None:
    _init_firebase()
    logger.info("Starting ${JOB_NAME}...")
    asyncio.run(run_${SNAKE_NAME}())


if __name__ == "__main__":
    main()
EOF

# Dockerfile: clone memory-maintenance, substitute CMD.
sed \
  -e "s/memory_maintenance_job\\.py/${MODULE_NAME}.py/g" \
  -e "s/ST→LT maintenance is Firestore\\/LLM\\/vector only\\./TODO: document why this image omits ffmpeg\\/curl\\/unzip./" \
  "$TEMPLATE_DOCKER" >"$DOCKER_OUT"

# Workflow: light substitution; strip LLM gateway steps (not universal).
python3 - "$TEMPLATE_WORKFLOW" "$WF_OUT" "$JOB_NAME" "$MODULE_NAME" <<'PY'
import re
import sys
from pathlib import Path

src, dest, job_name, module_name = sys.argv[1:5]
text = Path(src).read_text(encoding="utf-8")
text = text.replace("memory-maintenance-job", job_name)
text = text.replace("memory_maintenance_job", module_name)
text = text.replace("memory-maintenance-hourly", f"{job_name}-schedule")
text = text.replace("Deploy Memory Maintenance Job to Cloud RUN", f"Deploy {job_name} to Cloud RUN")
# Drop LLM-gateway-only steps; keep Build / Verify / Push image pipeline intact.
for step_name in (
    "Get GKE credentials for gateway serving gate",
    "Verify LLM Gateway serving data plane",
    "Probe memory L2 gateway lane from the Cloud Run VPC",
):
    text = re.sub(
        rf"\n      - name: {re.escape(step_name)}\n(?:        .*\n)*",
        "\n",
        text,
        count=1,
    )
text = text.replace(
    "      - name: Render maintenance runtime env from the gated gateway endpoint\n",
    "      - name: Render runtime env\n",
)
# Remove gateway URL env binding while keeping the step-level `run: |` key.
text = text.replace(
    "          OMI_LLM_GATEWAY_URL: ${{ steps.gateway-serving.outputs.gateway_url }}\n        run: |",
    "        run: |",
)
text = text.replace(
    "validate_memory_maintenance_scheduler.py",
    f"validate_{module_name}_scheduler.py",
)
text = text.replace("Validate hourly Scheduler trigger", "Validate Scheduler trigger")
Path(dest).write_text(text, encoding="utf-8")
PY

cat <<EOF

Scaffold wrote stubs under:
  $APPLY_ROOT

Files:
  $ENTRY_OUT
  $DOCKER_OUT
  $WF_OUT

runtime_env.yaml snippet shape (edit sources, then compose):

  cloud_run:
    jobs:
      ${JOB_NAME}:
        secrets:
          SERVICE_ACCOUNT_JSON:
            secret: SERVICE_ACCOUNT_JSON
            version: latest
          # TODO: domain secrets only
        env:
          OMI_ENV_STAGE:
            value: '{env}'
            category: runtime_identity
    workflow_files:
      - .github/workflows/gcp_${MODULE_NAME}.yml

Checklist TODOs:
  [ ] Implement domain runner (replace NotImplementedError)
  [ ] Trim workflow LLM leftovers if any remain; add Scheduler validator if needed
  [ ] Register in backend/runtime_images.json
  [ ] Add cloud_run.jobs.${JOB_NAME} to _base.yaml + overlays; compose_runtime_env.py
  [ ] Unit tests for render + orchestrator isolation
  [ ] Runbook + AGENTS.md service map
  [ ] Concurrency lock in check-deployment-concurrency.py
  [ ] Create GCP job + Scheduler out-of-band (this script never does that)

See: docs/doc/developer/backend/cloud_run_jobs_checklist.md
EOF

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "(dry-run) Temp directory left at $APPLY_ROOT — delete when done."
fi
