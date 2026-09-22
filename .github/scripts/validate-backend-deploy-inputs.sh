#!/usr/bin/env bash
# Shared backend deploy input validation for manual and auto-dev entry points.
set -euo pipefail

DEPLOY_PROFILE="${1:?deploy profile required (manual|auto-dev)}"
DEPLOY_ENVIRONMENT="${2:-}"
DEPLOY_TARGETS="${3:-}"
DEPLOY_GATEWAY="${4:-false}"

if [[ "$DEPLOY_PROFILE" == "manual" ]]; then
  if [[ "$DEPLOY_ENVIRONMENT" != "development" && "$DEPLOY_ENVIRONMENT" != "prod" ]]; then
    echo "Invalid environment: $DEPLOY_ENVIRONMENT. Must be 'development' or 'prod'." >&2
    exit 1
  fi
  if [[ "$DEPLOY_TARGETS" != "all" && "$DEPLOY_TARGETS" != "cloud-run-only" ]]; then
    echo "Invalid deploy_targets: $DEPLOY_TARGETS. Must be 'all' or 'cloud-run-only'." >&2
    exit 1
  fi
  if [[ "$DEPLOY_ENVIRONMENT" == "prod" && "$DEPLOY_TARGETS" == "all" ]]; then
    echo "environment=prod, deploy_targets=all is unsupported; use the dedicated GKE release workflow." >&2
    exit 1
  fi
  if [[ "$DEPLOY_GATEWAY" == "true" && "$DEPLOY_ENVIRONMENT" == "prod" ]]; then
    echo "environment=prod, deploy_gateway=true is unsupported; use the standalone manual LLM gateway workflow." >&2
    exit 1
  fi
  if [[ "$DEPLOY_GATEWAY" == "true" && "$DEPLOY_TARGETS" != "all" ]]; then
    echo "deploy_gateway=true requires deploy_targets=all." >&2
    exit 1
  fi
fi
