#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.prerecorded_stt import required_env_for_model_config  # noqa: E402
from scripts.runtime_env_durable_dispatch_contracts import (  # noqa: E402
    ValidationError,
    validate_account_deletion_dispatch_contract as _validate_account_deletion_dispatch_contract,
    validate_listen_finalization_dispatch_contract as _validate_listen_finalization_dispatch_contract,
)
from scripts.runtime_env_parakeet_contract import validate_parakeet_admission_contract  # noqa: E402
from scripts.runtime_env_memory_contract import validate_retired_memory_manifest  # noqa: E402
from scripts.runtime_env_validation.cloud_run import (  # noqa: E402
    _fetch_live_cloud_run_state,
    _validate_cloud_run,
)
from scripts.runtime_env_validation.common import (  # noqa: E402
    DEFAULT_MANIFEST,
    _as_config_dict,
    _as_config_list,
    _config_map_names,
    _env_entries_by_name,
    _expected_flag_value,
    _get_env_config,
    _has_literal_value,
    _is_provisional,
    _literal_env_value,
    _load_json,
    _load_yaml,
    _manifest_env_value,
    _network_flags,
    _secret_ref,
    _validate_cloud_run_secret_entries,
    _validate_env_entries,
    _validate_forbidden_env_entries,
    compute_project,
    data_plane_project,
)
from scripts.runtime_env_validation.manifest import (  # noqa: E402
    _canonical_memory_surfaces,
    _manifest_env_binding_is_configured,
    _manifest_literal_env_value,
    _validate_gke,
    _validate_manifest_shape,
    _validate_memory_maintenance_job_contract,
    _validate_prerecorded_stt_contract,
    _validate_stt_serving_model_policy,
    _validate_sync_ledger_fence_mode,
    validate_runtime_env,
)
from scripts.runtime_env_validation.workflows import (  # noqa: E402
    _expand_cloud_run_deploy_steps,
    _extract_workflow_cloud_run_targets,
    _validate_cloud_run_workflows,
    _validate_firestore_index_reconciliation_boundary,
    _validate_firestore_readiness_workflow_contract,
    _validate_sync_backfill_co_deploy,
    _workflow_variable_map,
)

__all__ = [
    'DEFAULT_MANIFEST',
    'ROOT',
    'subprocess',
    'ValidationError',
    'validate_parakeet_admission_contract',
    'validate_retired_memory_manifest',
    'validate_runtime_env',
    '_as_config_dict',
    '_as_config_list',
    '_canonical_memory_surfaces',
    '_config_map_names',
    '_env_entries_by_name',
    '_expand_cloud_run_deploy_steps',
    '_expected_flag_value',
    '_extract_workflow_cloud_run_targets',
    '_fetch_live_cloud_run_state',
    '_get_env_config',
    '_has_literal_value',
    '_is_provisional',
    '_literal_env_value',
    '_load_json',
    '_load_yaml',
    '_manifest_env_binding_is_configured',
    '_manifest_env_value',
    '_manifest_literal_env_value',
    '_network_flags',
    '_secret_ref',
    '_validate_account_deletion_dispatch_contract',
    '_validate_cloud_run',
    '_validate_cloud_run_secret_entries',
    '_validate_cloud_run_workflows',
    '_validate_env_entries',
    '_validate_firestore_index_reconciliation_boundary',
    '_validate_firestore_readiness_workflow_contract',
    '_validate_forbidden_env_entries',
    '_validate_gke',
    '_validate_listen_finalization_dispatch_contract',
    '_validate_manifest_shape',
    '_validate_memory_maintenance_job_contract',
    '_validate_prerecorded_stt_contract',
    '_validate_stt_serving_model_policy',
    '_validate_sync_backfill_co_deploy',
    '_validate_sync_ledger_fence_mode',
    '_workflow_variable_map',
    'compute_project',
    'data_plane_project',
    'main',
    'required_env_for_model_config',
]


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate backend runtime env manifests against GKE and Cloud Run.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--cloud-run-state',
        type=Path,
        help='Offline Cloud Run state JSON. Shape: {"services": {"backend": {"env": [...]} }}.',
    )
    parser.add_argument(
        '--check-live-cloud-run',
        action='store_true',
        help='Fetch Cloud Run service state with gcloud and validate required env/secrets.',
    )
    parser.add_argument(
        '--check-workflows',
        action='store_true',
        help='Validate checked-in Cloud Run workflow env_vars blocks against the manifest.',
    )
    parser.add_argument(
        '--workflow-root',
        type=Path,
        help='Immutable source root for workflow YAML and local composite actions; defaults to the runtime root.',
    )
    parser.add_argument(
        '--strict-provisional',
        action='store_true',
        help='Require provisional manifest values to match exactly. By default they only require presence.',
    )
    args = parser.parse_args()

    errors = validate_runtime_env(
        env=args.env,
        manifest_path=args.manifest,
        cloud_run_state_path=args.cloud_run_state,
        check_live_cloud_run=args.check_live_cloud_run,
        check_workflows=args.check_workflows,
        workflow_root=args.workflow_root,
        strict_provisional=args.strict_provisional,
    )
    for error in errors:
        print(f'ERROR [{error.scope}]: {error.message}', file=sys.stderr)
    if errors:
        return 1
    print(f'backend runtime env validation passed for {args.env}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
