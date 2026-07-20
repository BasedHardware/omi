#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.prerecorded_stt import required_env_for_model_config  # noqa: E402
from config.stt_provider_policy import STTServingSurface, canonical_model_config  # noqa: E402
from scripts.firestore_workflow_policy import (  # noqa: E402
    has_direct_firestore_mutation,
    reconciliation_invocations,
)
from scripts.runtime_env_durable_dispatch_contracts import (  # noqa: E402
    ValidationError,
    validate_account_deletion_dispatch_contract as _validate_account_deletion_dispatch_contract,
    validate_listen_finalization_dispatch_contract as _validate_listen_finalization_dispatch_contract,
)
from scripts.runtime_env_parakeet_contract import validate_parakeet_admission_contract  # noqa: E402

DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
ConfigDict = dict[str, Any]
EnvEntry = dict[str, Any]
EnvEntryMap = dict[str, EnvEntry]
StringMap = dict[str, str]

_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_ENV = frozenset(
    {
        'MEMORY_MODE',
        'MEMORY_ENABLED_USERS',
        'MEMORY_V3_GET_ENABLED',
        'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED',
        'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED',
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED',
        'MEMORY_TYPESENSE_COLLECTION',
        'TYPESENSE_HOST',
        'TYPESENSE_HOST_PORT',
        'TYPESENSE_API_KEY',
    }
)
_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_SECRETS = frozenset({'TYPESENSE_HOST', 'TYPESENSE_API_KEY'})
_SYNC_LEDGER_FENCE_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill')
_SYNC_LEDGER_FENCE_MODES = frozenset({'legacy', 'standby', 'active'})
_MEMORY_MAINTENANCE_DEV_REQUIRED_FLAGS = {
    '--task-timeout': '3600s',
    '--cpu': '2',
    '--memory': '2Gi',
}


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _as_config_list(value: object) -> list[Any] | None:
    return cast(list[Any], value) if isinstance(value, list) else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate backend runtime env manifests against checked-in GKE config and Cloud Run state.'
    )
    parser.add_argument('--env', choices=('dev', 'beta', 'prod'), required=True)
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
        '--check-rendered-cloud-run',
        action='store_true',
        help='Validate manifest Cloud Run env/secrets against an offline rendered revision shape.',
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
        check_rendered_cloud_run=args.check_rendered_cloud_run,
        check_workflows=args.check_workflows,
        strict_provisional=args.strict_provisional,
    )
    for error in errors:
        print(f'ERROR [{error.scope}]: {error.message}', file=sys.stderr)
    if errors:
        return 1
    print(f'backend runtime env validation passed for {args.env}')
    return 0


def validate_runtime_env(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    cloud_run_state_path: Path | None = None,
    check_live_cloud_run: bool = False,
    check_rendered_cloud_run: bool = False,
    check_workflows: bool = False,
    strict_provisional: bool = False,
) -> list[ValidationError]:
    manifest = _load_yaml(manifest_path)
    env_config = _get_env_config(manifest, env)
    errors = _validate_manifest_shape(env_config, env)
    if errors:
        return errors

    errors.extend(_validate_gke(env_config, strict_provisional=strict_provisional))
    errors.extend(_validate_stt_serving_model_policy(env, env_config))
    errors.extend(validate_parakeet_admission_contract(env, env_config))
    errors.extend(_validate_prerecorded_stt_contract(env, env_config))
    errors.extend(_validate_memory_maintenance_job_contract(env, env_config))
    errors.extend(_validate_account_deletion_dispatch_contract(env, env_config))
    errors.extend(_validate_listen_finalization_dispatch_contract(env, env_config))
    if check_workflows:
        errors.extend(
            _validate_cloud_run_workflows(
                env,
                env_config,
                strict_provisional=strict_provisional,
                manifest_path=manifest_path,
                manifest=manifest,
            )
        )

    cloud_run_state = None
    if cloud_run_state_path is not None:
        cloud_run_state = _load_json(cloud_run_state_path)
    elif check_rendered_cloud_run:
        cloud_run_state = _build_rendered_cloud_run_state(env_config)
    elif check_live_cloud_run:
        cloud_run_state = _fetch_live_cloud_run_state(env_config)

    if cloud_run_state is not None:
        errors.extend(_validate_cloud_run(env_config, cloud_run_state, strict_provisional=strict_provisional))
        errors.extend(_validate_sync_ledger_fence_mode(env_config, cloud_run_state))
    return errors


def _build_rendered_cloud_run_state(env_config: ConfigDict) -> ConfigDict:
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    service_configs = _as_config_dict(cloud_run.get('services')) or {}
    network_flags = _rendered_network_flags(env_config)
    services: ConfigDict = {}
    for service_name, raw_service_config in service_configs.items():
        service_config = _as_config_dict(raw_service_config) or {}
        env_entries: list[ConfigDict] = []
        for env_name, raw_entry in (service_config.get('env') or {}).items():
            entry = _as_config_dict(raw_entry)
            if entry is None:
                continue
            if 'value' in entry:
                if entry.get('provisional') and str(entry['value']).startswith('TBD_'):
                    env_entries.append({'name': str(env_name), 'value': 'rendered-provisional-placeholder'})
                    continue
                env_entries.append({'name': str(env_name), 'value': str(entry['value'])})
            elif 'env_var' in entry:
                env_entries.append(
                    {
                        'name': str(env_name),
                        'value': str(entry.get('default', f'__rendered_{env_name}__')),
                    }
                )
        for secret_name, raw_entry in (service_config.get('secrets') or {}).items():
            entry = _as_config_dict(raw_entry)
            if entry is None or 'secret' not in entry:
                continue
            env_entries.append(
                {
                    'name': str(secret_name),
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': str(entry['secret']),
                            'key': str(entry.get('version', 'latest')),
                        }
                    },
                }
            )
        services[str(service_name)] = {'env': env_entries, 'flags': dict(network_flags)}
    jobs: ConfigDict = {}
    job_configs = _as_config_dict(cloud_run.get('jobs')) or {}
    for job_name, raw_job_config in job_configs.items():
        job_config = _as_config_dict(raw_job_config) or {}
        env_entries = []
        for env_name, raw_entry in (job_config.get('env') or {}).items():
            entry = _as_config_dict(raw_entry)
            if entry is None:
                continue
            if 'value' in entry:
                env_entries.append({'name': str(env_name), 'value': str(entry['value'])})
            elif 'env_var' in entry:
                env_entries.append(
                    {
                        'name': str(env_name),
                        'value': str(entry.get('default', f'__rendered_{env_name}__')),
                    }
                )
        for secret_name, raw_entry in (job_config.get('secrets') or {}).items():
            entry = _as_config_dict(raw_entry)
            if entry is None or 'secret' not in entry:
                continue
            env_entries.append(
                {
                    'name': str(secret_name),
                    'valueFrom': {
                        'secretKeyRef': {
                            'name': str(entry['secret']),
                            'key': str(entry.get('version', 'latest')),
                        }
                    },
                }
            )
        jobs[str(job_name)] = {'env': env_entries, 'flags': dict(job_config.get('flags') or {})}
    return {'services': services, 'jobs': jobs}


def _rendered_network_flags(env_config: ConfigDict) -> StringMap:
    flags = _network_flags(env_config)
    rendered: StringMap = {}
    for name, raw_entry in flags.items():
        entry = _as_config_dict(raw_entry)
        if entry is not None and 'env_var' in entry:
            rendered[str(name)] = f'__rendered_flag_{str(name).lstrip("-").replace("-", "_")}__'
        else:
            rendered[str(name)] = _expected_flag_value(raw_entry)
    return rendered


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return cast(ConfigDict, loaded)


def _load_json(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return cast(ConfigDict, loaded)


def _get_env_config(manifest: ConfigDict, env: str) -> ConfigDict:
    environments = _as_config_dict(manifest.get('environments'))
    if environments is None or env not in environments:
        raise ValueError(f'manifest has no environments.{env}')
    env_config = _as_config_dict(environments[env])
    if env_config is None:
        raise ValueError(f'environments.{env} must be a mapping')
    return env_config


def _validate_manifest_shape(env_config: ConfigDict, env: str) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for key in ('gcp_project', 'region', 'gke', 'cloud_run'):
        if key not in env_config:
            errors.append(ValidationError(env, f'missing {key}'))
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    cloud_run_services = _as_config_dict(cloud_run.get('services'))
    if cloud_run_services is None or not cloud_run_services:
        errors.append(ValidationError(env, 'cloud_run.services must be a non-empty mapping'))
    else:
        for service in _SYNC_LEDGER_FENCE_SERVICES:
            service_config = _as_config_dict(cloud_run_services.get(service)) or {}
            env_entries = _as_config_dict(service_config.get('env')) or {}
            entry = _as_config_dict(env_entries.get('SYNC_LEDGER_FENCE_MODE'))
            if entry is None:
                errors.append(ValidationError(f'{env}/cloud_run/{service}', 'missing SYNC_LEDGER_FENCE_MODE'))
                continue
            if entry.get('env_var') != 'SYNC_LEDGER_FENCE_MODE':
                errors.append(
                    ValidationError(
                        f'{env}/cloud_run/{service}',
                        'SYNC_LEDGER_FENCE_MODE must bind the protected SYNC_LEDGER_FENCE_MODE variable',
                    )
                )
            if entry.get('default') != 'legacy':
                errors.append(
                    ValidationError(
                        f'{env}/cloud_run/{service}',
                        'SYNC_LEDGER_FENCE_MODE must default to legacy until protected cutover activation',
                    )
                )
    return errors


def _validate_sync_ledger_fence_mode(env_config: ConfigDict, cloud_run_state: ConfigDict) -> list[ValidationError]:
    """Keep the protected rollout mode identical across all sync surfaces.

    A normal deploy must never regress a live active cutover back to legacy,
    nor leave one service in standby while another starts fenced work. The
    renderer receives the desired value from the protected environment
    variable; its absence deliberately means the safe legacy default.
    """
    expected = os.getenv('SYNC_LEDGER_FENCE_MODE', 'legacy').strip().lower() or 'legacy'
    errors: list[ValidationError] = []
    if expected not in _SYNC_LEDGER_FENCE_MODES:
        return [ValidationError('sync_ledger_fence', f'invalid protected mode {expected!r}')]

    services = _as_config_dict(cloud_run_state.get('services')) or {}
    for service in _SYNC_LEDGER_FENCE_SERVICES:
        state = _as_config_dict(services.get(service))
        if state is None:
            # Keep the existing provisional-rendered behavior intact. Live
            # validation will still require every cutover service once it is
            # deployed, because no state is then provisional.
            continue
        actual = _env_entries_by_name(state.get('env', [])).get('SYNC_LEDGER_FENCE_MODE')
        actual_value = _literal_env_value(actual) if actual is not None else ''
        if actual_value not in _SYNC_LEDGER_FENCE_MODES:
            errors.append(
                ValidationError(
                    f'cloud_run/{service}',
                    'SYNC_LEDGER_FENCE_MODE must be one of legacy, standby, active',
                )
            )
            continue
        if actual_value != expected:
            errors.append(
                ValidationError(
                    f'cloud_run/{service}',
                    f'SYNC_LEDGER_FENCE_MODE mismatch: expected protected mode {expected!r}, got {actual_value!r}',
                )
            )
    return errors


def _manifest_literal_env_value(env_map: object, key: str) -> str | None:
    entries = _as_config_dict(env_map) or {}
    entry = _as_config_dict(entries.get(key))
    if entry is None or 'value' not in entry:
        return None
    return str(entry['value'])


def _manifest_env_binding_is_configured(env_map: ConfigDict, secrets_map: ConfigDict, key: str) -> bool:
    """Return whether a manifest binding will yield a non-empty runtime env value."""
    entry = _as_config_dict(env_map.get(key))
    if entry is not None:
        if 'value' in entry:
            return bool(str(entry['value']).strip())
        if 'secret' in entry or 'env_var' in entry or 'config_map' in entry:
            return True
    secret_entry = _as_config_dict(secrets_map.get(key))
    return secret_entry is not None and bool(str(secret_entry.get('secret', '')).strip())


def _validate_stt_serving_model_policy(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Require deployable model values to match the code-owned serving policy."""
    errors: list[ValidationError] = []
    model_policy = {
        'STT_PRERECORDED_MODEL': canonical_model_config(STTServingSurface.PRERECORDED),
        'STT_SERVICE_MODELS': canonical_model_config(STTServingSurface.STREAMING),
    }
    surfaces: list[tuple[str, ConfigDict]] = []

    gke = _as_config_dict(env_config.get('gke')) or {}
    for service, raw_service in gke.items():
        service_config = _as_config_dict(raw_service) or {}
        surfaces.append((f'{env}/gke/{service}', _as_config_dict(service_config.get('env')) or {}))

    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    cloud_run_services = _as_config_dict(cloud_run.get('services')) or {}
    for service, raw_service in cloud_run_services.items():
        service_config = _as_config_dict(raw_service) or {}
        surfaces.append((f'{env}/cloud_run/{service}', _as_config_dict(service_config.get('env')) or {}))

    for scope, env_map in surfaces:
        for env_name, expected_value in model_policy.items():
            if env_name not in env_map:
                continue
            actual_value = _manifest_literal_env_value(env_map, env_name)
            if actual_value is None:
                errors.append(
                    ValidationError(scope, f'{env_name} must be a literal value owned by stt_provider_policy')
                )
            elif actual_value != expected_value:
                errors.append(
                    ValidationError(
                        scope,
                        f'{env_name} must match stt_provider_policy: expected {expected_value!r}, got {actual_value!r}',
                    )
                )
    return errors


def _validate_prerecorded_stt_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Keep selected providers and their required runtime bindings deployable together."""
    errors: list[ValidationError] = []
    surfaces: list[tuple[str, ConfigDict, ConfigDict]] = []

    gke = _as_config_dict(env_config.get('gke')) or {}
    for service, raw_service in gke.items():
        service_config = _as_config_dict(raw_service) or {}
        surfaces.append(
            (
                f'{env}/gke/{service}',
                _as_config_dict(service_config.get('env')) or {},
                {},
            )
        )

    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    cloud_run_services = _as_config_dict(cloud_run.get('services')) or {}
    required_cloud_run_scopes: set[str] = set()
    if env in {'dev', 'beta', 'prod'}:
        for service in ('backend', 'backend-sync', 'backend-integration'):
            if service not in cloud_run_services:
                continue
            scope = f'{env}/cloud_run/{service}'
            required_cloud_run_scopes.add(scope)
            service_config = _as_config_dict(cloud_run_services.get(service)) or {}
            env_map = _as_config_dict(service_config.get('env')) or {}
            secrets_map = _as_config_dict(service_config.get('secrets')) or {}
            if 'STT_PRERECORDED_MODEL' not in env_map and 'STT_PRERECORDED_MODEL' not in secrets_map:
                errors.append(ValidationError(scope, 'required Cloud Run service is missing STT_PRERECORDED_MODEL'))

    for service, raw_service in cloud_run_services.items():
        service_config = _as_config_dict(raw_service) or {}
        surfaces.append(
            (
                f'{env}/cloud_run/{service}',
                _as_config_dict(service_config.get('env')) or {},
                _as_config_dict(service_config.get('secrets')) or {},
            )
        )

    for scope, env_map, secrets_map in surfaces:
        model_is_bound = 'STT_PRERECORDED_MODEL' in env_map or 'STT_PRERECORDED_MODEL' in secrets_map
        is_required_cloud_run = scope in required_cloud_run_scopes
        if not model_is_bound and not is_required_cloud_run:
            continue

        literal_models = _manifest_literal_env_value(env_map, 'STT_PRERECORDED_MODEL')
        source_is_opaque = literal_models is None
        for required_env in required_env_for_model_config(
            literal_models,
            source_is_opaque=source_is_opaque,
        ):
            if _manifest_env_binding_is_configured(env_map, secrets_map, required_env):
                continue
            message = (
                f'required Cloud Run service is missing non-empty {required_env}'
                if is_required_cloud_run
                else f'STT_PRERECORDED_MODEL requires non-empty {required_env}'
            )
            errors.append(
                ValidationError(
                    scope,
                    message,
                )
            )
    return errors


def _canonical_memory_surfaces(env_config: ConfigDict) -> list[tuple[str, ConfigDict]]:
    """Return (scope, env-map) for every surface that can enable canonical memory."""
    surfaces: list[tuple[str, ConfigDict]] = []
    gke = _as_config_dict(env_config.get('gke')) or {}
    for service, raw_service in gke.items():
        service_config = _as_config_dict(raw_service) or {}
        env_map = _as_config_dict(service_config.get('env')) or {}
        if 'MEMORY_MODE' in env_map:
            surfaces.append((f'gke/{service}', env_map))
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    for service, raw_service in (_as_config_dict(cloud_run.get('services')) or {}).items():
        service_config = _as_config_dict(raw_service) or {}
        env_map = _as_config_dict(service_config.get('env')) or {}
        if 'MEMORY_MODE' in env_map:
            surfaces.append((f'cloud_run/{service}', env_map))
    return surfaces


def _validate_memory_maintenance_job_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Require memory-maintenance-job to exist and stay aligned with MEMORY_MODE rollout.

    Prod may keep MEMORY_MODE=off with cron disabled. Enabling MEMORY_MODE=read on any
    request-path surface without enabling the dedicated maintenance job fails validation
    so Gate 3 cannot forget ST→LT hosting.

    Also rejects:
    - canonical maintenance env/secrets on notifications-job (its workflow
      removes only those retired live bindings);
    - request-path / other-job hosts keeping MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true
      (ST→LT cron must run only on memory-maintenance-job);
    - empty MEMORY_ENABLED_USERS on a read-mode surface while the job has a non-empty allowlist;
    - mismatched MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED between job and read surfaces.
    """
    errors: list[ValidationError] = []
    scope = f'{env}/cloud_run/jobs/memory-maintenance-job'
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    jobs = _as_config_dict(cloud_run.get('jobs')) or {}
    notifications_job = _as_config_dict(jobs.get('notifications-job')) or {}
    notifications_env = _as_config_dict(notifications_job.get('env')) or {}
    notifications_secrets = _as_config_dict(notifications_job.get('secrets')) or {}
    notifications_scope = f'{env}/cloud_run/jobs/notifications-job'
    for forbidden_env in sorted(_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_ENV.intersection(notifications_env)):
        errors.append(
            ValidationError(
                notifications_scope,
                f'env {forbidden_env} belongs only on memory-maintenance-job',
            )
        )
    for forbidden_secret in sorted(_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_SECRETS.intersection(notifications_secrets)):
        errors.append(
            ValidationError(
                notifications_scope,
                f'secret {forbidden_secret} belongs only on memory-maintenance-job',
            )
        )

    job = _as_config_dict(jobs.get('memory-maintenance-job'))
    if job is None:
        errors.append(ValidationError(scope, 'missing cloud_run.jobs.memory-maintenance-job'))
        return errors

    job_env = _as_config_dict(job.get('env')) or {}
    job_secrets = _as_config_dict(job.get('secrets')) or {}
    if env == 'dev':
        job_flags = _as_config_dict(job.get('flags')) or {}
        for flag_name, expected_value in _MEMORY_MAINTENANCE_DEV_REQUIRED_FLAGS.items():
            actual_entry = job_flags.get(flag_name)
            if actual_entry is None:
                errors.append(ValidationError(scope, f'missing required dev Cloud Run flag {flag_name}'))
                continue
            if _expected_flag_value(actual_entry) != expected_value:
                errors.append(
                    ValidationError(
                        scope,
                        f'dev Cloud Run flag {flag_name} must be {expected_value!r}',
                    )
                )
    for required_env in (
        'MEMORY_MODE',
        'MEMORY_ENABLED_USERS',
        'MEMORY_V3_GET_ENABLED',
        'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED',
        'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED',
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED',
    ):
        if required_env not in job_env:
            errors.append(ValidationError(scope, f'missing env {required_env}'))
    for required_secret in (
        'SERVICE_ACCOUNT_JSON',
        'ENCRYPTION_SECRET',
        'OPENAI_API_KEY',
        'PINECONE_API_KEY',
        'TYPESENSE_HOST',
        'TYPESENSE_API_KEY',
    ):
        if required_secret not in job_secrets:
            errors.append(ValidationError(scope, f'missing secret {required_secret}'))

    job_mode = (_manifest_literal_env_value(job_env, 'MEMORY_MODE') or '').strip().lower()
    job_cron = (_manifest_literal_env_value(job_env, 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED') or '').strip().lower()
    job_fast_track = (
        (_manifest_literal_env_value(job_env, 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED') or '').strip().lower()
    )
    job_users = (_manifest_literal_env_value(job_env, 'MEMORY_ENABLED_USERS') or '').strip()

    # Non-job hosts must not enable the ST→LT cron (would duplicate maintenance).
    for other_job_name, raw_other_job in jobs.items():
        if other_job_name == 'memory-maintenance-job':
            continue
        other_job = _as_config_dict(raw_other_job) or {}
        other_env = _as_config_dict(other_job.get('env')) or {}
        other_cron = (
            (_manifest_literal_env_value(other_env, 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED') or '').strip().lower()
        )
        if other_cron == 'true':
            errors.append(
                ValidationError(
                    f'{env}/cloud_run/jobs/{other_job_name}',
                    'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED must be false; '
                    'ST→LT cron is hosted only by memory-maintenance-job',
                )
            )

    read_surfaces = []
    for surface_scope, surface_env in _canonical_memory_surfaces(env_config):
        surface_mode = (_manifest_literal_env_value(surface_env, 'MEMORY_MODE') or '').strip().lower()
        surface_cron = (
            (_manifest_literal_env_value(surface_env, 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED') or '').strip().lower()
        )
        if surface_cron == 'true':
            errors.append(
                ValidationError(
                    surface_scope,
                    'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED must be false on request-path surfaces; '
                    'ST→LT cron is hosted only by memory-maintenance-job',
                )
            )
        if surface_mode and surface_mode != 'off':
            read_surfaces.append((surface_scope, surface_env, surface_mode))

    if job_mode in ('', 'off'):
        if job_cron == 'true':
            errors.append(
                ValidationError(
                    scope,
                    'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED must be false while MEMORY_MODE is off',
                )
            )
        for surface_scope, _surface_env, surface_mode in read_surfaces:
            errors.append(
                ValidationError(
                    scope,
                    f'{surface_scope} MEMORY_MODE={surface_mode!r} requires memory-maintenance-job '
                    'MEMORY_MODE=read and MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true '
                    '(ST→LT is not hosted by notifications-job)',
                )
            )
        return errors

    # Canonical request-path is on somewhere — maintenance job must be fully enabled.
    if job_mode != 'read':
        errors.append(
            ValidationError(scope, f'MEMORY_MODE must be read when enabling canonical memory (got {job_mode!r})')
        )
    if job_cron != 'true':
        errors.append(
            ValidationError(
                scope,
                'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED must be true when MEMORY_MODE is not off '
                '(ST→LT maintenance is hosted by memory-maintenance-job, not notifications-job)',
            )
        )
    if not job_users:
        errors.append(ValidationError(scope, 'MEMORY_ENABLED_USERS must be non-empty when MEMORY_MODE is not off'))

    for surface_scope, surface_env, surface_mode in read_surfaces:
        if surface_mode != job_mode:
            errors.append(
                ValidationError(
                    scope,
                    f'{surface_scope} MEMORY_MODE={surface_mode!r} must match memory-maintenance-job MEMORY_MODE={job_mode!r}',
                )
            )
        surface_users = (_manifest_literal_env_value(surface_env, 'MEMORY_ENABLED_USERS') or '').strip()
        if surface_users != job_users:
            errors.append(
                ValidationError(
                    scope,
                    f'{surface_scope} MEMORY_ENABLED_USERS must match memory-maintenance-job allowlist '
                    '(empty surface allowlist is not allowed while the job has a non-empty cohort)',
                )
            )
        surface_fast_track = (
            (_manifest_literal_env_value(surface_env, 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED') or '')
            .strip()
            .lower()
        )
        if surface_fast_track and job_fast_track and surface_fast_track != job_fast_track:
            errors.append(
                ValidationError(
                    scope,
                    f'{surface_scope} MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED={surface_fast_track!r} '
                    f'must match memory-maintenance-job ({job_fast_track!r})',
                )
            )
    return errors


def _validate_gke(env_config: ConfigDict, *, strict_provisional: bool) -> list[ValidationError]:
    errors: list[ValidationError] = []
    gke_config = _as_config_dict(env_config.get('gke')) or {}
    for service, raw_service_config in gke_config.items():
        service_config = _as_config_dict(raw_service_config)
        if service_config is None:
            errors.append(ValidationError(f'gke/{service}', 'service config must be a mapping'))
            continue
        values_file = ROOT / service_config['values_file']
        values = _load_yaml(values_file)
        actual_env = _env_entries_by_name(values.get('env', []))
        errors.extend(
            _validate_env_entries(
                scope=f'gke/{service}',
                expected=service_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
                config_maps=_config_map_names(values.get('envFrom', [])),
            )
        )
    return errors


def _validate_cloud_run(
    env_config: ConfigDict,
    cloud_run_state: ConfigDict,
    *,
    strict_provisional: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    state_services = _as_config_dict(cloud_run_state.get('services'))
    if state_services is None:
        return [ValidationError('cloud_run', 'state must contain services mapping')]

    cloud_run = _as_config_dict(env_config['cloud_run']) or {}
    service_configs = _as_config_dict(cloud_run.get('services')) or {}
    for service, raw_service_config in service_configs.items():
        service_config = _as_config_dict(raw_service_config) or {}
        service_state = _as_config_dict(state_services.get(service))
        if service_state is None:
            if service_config.get('provisional') and not strict_provisional:
                continue
            errors.append(ValidationError(f'cloud_run/{service}', 'missing service state'))
            continue
        actual_env = _env_entries_by_name(service_state.get('env', []))
        errors.extend(
            _validate_env_entries(
                scope=f'cloud_run/{service}',
                expected=service_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
            )
        )
        errors.extend(
            _validate_forbidden_env_entries(
                scope=f'cloud_run/{service}',
                forbidden=service_config.get('forbidden_env'),
                actual=actual_env,
            )
        )
        errors.extend(
            _validate_cloud_run_secret_entries(
                scope=f'cloud_run/{service}',
                expected=service_config.get('secrets', {}),
                actual=actual_env,
            )
        )
        errors.extend(
            _validate_workflow_flags(
                scope=f'cloud_run/{service}',
                expected=_network_flags(env_config),
                actual=service_state.get('flags', {}),
                strict_provisional=strict_provisional,
            )
        )
    state_jobs = _as_config_dict(cloud_run_state.get('jobs'))
    if state_jobs is not None:
        job_configs = _as_config_dict(cloud_run.get('jobs')) or {}
        for job, raw_job_config in job_configs.items():
            job_config = _as_config_dict(raw_job_config) or {}
            job_state = _as_config_dict(state_jobs.get(job))
            if job_state is None:
                errors.append(ValidationError(f'cloud_run/{job}', 'missing job state'))
                continue
            actual_env = _env_entries_by_name(job_state.get('env', []))
            errors.extend(
                _validate_env_entries(
                    scope=f'cloud_run/{job}',
                    expected=job_config.get('env', {}),
                    actual=actual_env,
                    strict_provisional=strict_provisional,
                )
            )
            errors.extend(
                _validate_forbidden_env_entries(
                    scope=f'cloud_run/{job}',
                    forbidden=job_config.get('forbidden_env'),
                    actual=actual_env,
                )
            )
            errors.extend(
                _validate_cloud_run_secret_entries(
                    scope=f'cloud_run/{job}',
                    expected=job_config.get('secrets', {}),
                    actual=actual_env,
                )
            )
    return errors


def _validate_cloud_run_workflows(
    env: str,
    env_config: ConfigDict,
    *,
    strict_provisional: bool,
    manifest_path: Path,
    manifest: ConfigDict | None = None,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    workflow_files = _as_config_list(cloud_run.get('workflow_files'))
    if workflow_files is None:
        return [ValidationError('cloud_run/workflows', 'workflow_files must be a list')]

    expected_services = _as_config_dict(cloud_run.get('services')) or {}
    expected_jobs = _as_config_dict(cloud_run.get('jobs')) or {}
    workflow_services: dict[str, ConfigDict] = {}
    workflow_jobs: dict[str, ConfigDict] = {}
    manifest = manifest if manifest is not None else _load_yaml(manifest_path)
    for workflow_file in workflow_files:
        if not isinstance(workflow_file, str):
            errors.append(ValidationError('cloud_run/workflows', 'workflow file paths must be strings'))
            continue
        workflow_path = ROOT / workflow_file
        workflow = _load_yaml(workflow_path)
        errors.extend(_validate_firestore_index_reconciliation_boundary(workflow_file, workflow))
        extracted = _extract_workflow_cloud_run_targets(workflow, env=env, manifest=manifest)
        errors.extend(_validate_sync_backfill_co_deploy(workflow_file, extracted['services']))
        workflow_services.update(extracted['services'])
        workflow_jobs.update(extracted['jobs'])

    workflow_vars = _workflow_variable_map(env_config, expected_services)
    for service, service_config in expected_services.items():
        service_state = workflow_services.get(service)
        if service_state is None:
            errors.append(ValidationError(f'cloud_run_workflow/{service}', 'missing deploy-cloudrun env_vars block'))
            continue
        actual_env = _literal_env_entries_by_name(service_state.get('env_vars', {}), variables=workflow_vars)
        errors.extend(
            _validate_env_entries(
                scope=f'cloud_run_workflow/{service}',
                expected=service_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
            )
        )
        errors.extend(
            _validate_forbidden_env_entries(
                scope=f'cloud_run_workflow/{service}',
                forbidden=service_config.get('forbidden_env'),
                actual=actual_env,
            )
        )
        service_flags = _substitute_values(service_state.get('flags', {}), variables=workflow_vars)
        errors.extend(
            _validate_forbidden_workflow_removals(
                scope=f'cloud_run_workflow/{service}',
                forbidden=service_config.get('forbidden_env'),
                flags=service_flags,
            )
        )
        actual_secrets = _workflow_secret_entries_by_name(service_state.get('secrets', {}))
        errors.extend(
            _validate_cloud_run_secret_entries(
                scope=f'cloud_run_workflow/{service}',
                expected=service_config.get('secrets', {}),
                actual=actual_secrets,
            )
        )
        errors.extend(
            _validate_workflow_flags(
                scope=f'cloud_run_workflow/{service}',
                expected=_network_flags(env_config),
                actual=_substitute_values(service_state.get('flags', {}), variables=workflow_vars),
                strict_provisional=strict_provisional,
            )
        )

    for job, job_config in expected_jobs.items():
        job_state = workflow_jobs.get(job)
        if job_state is None:
            errors.append(ValidationError(f'cloud_run_workflow/{job}', 'missing deploy-cloudrun job env_vars block'))
            continue
        actual_env = _literal_env_entries_by_name(job_state.get('env_vars', {}), variables=workflow_vars)
        errors.extend(
            _validate_env_entries(
                scope=f'cloud_run_workflow/{job}',
                expected=job_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
            )
        )
        errors.extend(
            _validate_forbidden_env_entries(
                scope=f'cloud_run_workflow/{job}',
                forbidden=job_config.get('forbidden_env'),
                actual=actual_env,
            )
        )
        job_flags = _substitute_values(job_state.get('flags', {}), variables=workflow_vars)
        errors.extend(
            _validate_forbidden_workflow_removals(
                scope=f'cloud_run_workflow/{job}',
                forbidden=job_config.get('forbidden_env'),
                flags=job_flags,
            )
        )
        actual_secrets = _workflow_secret_entries_by_name(job_state.get('secrets', {}))
        errors.extend(
            _validate_cloud_run_secret_entries(
                scope=f'cloud_run_workflow/{job}',
                expected=job_config.get('secrets', {}),
                actual=actual_secrets,
            )
        )
        errors.extend(
            _validate_workflow_flags(
                scope=f'cloud_run_workflow/{job}',
                expected=_as_config_dict(job_config.get('flags')) or {},
                actual=_substitute_values(job_state.get('flags', {}), variables=workflow_vars),
                strict_provisional=strict_provisional,
            )
        )
    return errors


def _validate_firestore_readiness_workflow_contract(workflow_file: str, workflow: ConfigDict) -> list[ValidationError]:
    if Path(workflow_file).name not in {'gcp_backend.yml', 'gcp_backend_auto_dev.yml'}:
        return []

    scope = f'cloud_run_workflow/{workflow_file}'
    errors: list[ValidationError] = []
    jobs = _as_config_dict(workflow.get('jobs')) or {}
    readiness_job = _as_config_dict(jobs.get('firestore_readiness'))
    deploy_job = _as_config_dict(jobs.get('deploy'))
    if readiness_job is None:
        return [ValidationError(scope, 'Firestore readiness must run in an isolated firestore_readiness job')]
    if deploy_job is None:
        return [ValidationError(scope, 'Firestore readiness contract requires the backend deploy job')]

    needs = deploy_job.get('needs')
    normalized_needs = {needs} if isinstance(needs, str) else set(needs) if isinstance(needs, list) else set()
    if 'firestore_readiness' not in normalized_needs:
        errors.append(ValidationError(scope, 'backend deploy must depend on the isolated Firestore readiness job'))

    expected_path = (
        '${{ runner.temp }}/firestore-schema-proposal-' '${{ github.run_id }}-${{ github.run_attempt }}.json'
    )
    is_manual_deploy = Path(workflow_file).name == 'gcp_backend.yml'
    permissions = _as_config_dict(readiness_job.get('permissions')) or {}
    expected_permissions = {'actions': 'read', 'contents': 'read'} if is_manual_deploy else {'contents': 'read'}
    if permissions != expected_permissions:
        errors.append(
            ValidationError(scope, 'Firestore readiness job permissions must be limited to its release-proof boundary')
        )

    steps = _as_config_list(readiness_job.get('steps')) or []
    parsed_steps = [_as_config_dict(step) or {} for step in steps]
    serialized_readiness_job = json.dumps(readiness_job, sort_keys=True)
    if 'secrets.GCP_CREDENTIALS' in serialized_readiness_job:
        errors.append(ValidationError(scope, 'Firestore readiness must not receive backend deployment credentials'))
    auth_steps = [step for step in parsed_steps if step.get('uses') == 'google-github-actions/auth@v3']
    if len(auth_steps) != 1 or (_as_config_dict(auth_steps[0].get('with')) or {}).get('credentials_json') != (
        '${{ secrets.GCP_FIRESTORE_READONLY_CREDENTIALS }}'
    ):
        errors.append(ValidationError(scope, 'Firestore readiness must use the dedicated read-only credentials'))
    checkout_steps = [step for step in parsed_steps if step.get('uses') == 'actions/checkout@v7']
    admitted_readiness_ref = '${{ steps.admitted_source.outputs.admitted_sha }}'
    admission_checkout_name = (
        'Checkout current main for source admission'
        if is_manual_deploy
        else 'Checkout current main for automatic source admission'
    )
    admission_error = (
        f"{'manual' if is_manual_deploy else 'automatic'} Firestore readiness must check out "
        f"{'main' if is_manual_deploy else 'current main'} then the admitted SHA"
    )
    admission_checkout = next((step for step in checkout_steps if step.get('name') == admission_checkout_name), None)
    admitted_checkout = next(
        (step for step in checkout_steps if step.get('name') == 'Checkout admitted Firestore source'), None
    )
    admission_with = _as_config_dict((admission_checkout or {}).get('with')) or {}
    admitted_with = _as_config_dict((admitted_checkout or {}).get('with')) or {}
    if (
        len(checkout_steps) != 2
        or admission_with.get('ref') != 'main'
        or admission_with.get('fetch-depth') != 0
        or admitted_with.get('ref') != admitted_readiness_ref
    ):
        errors.append(ValidationError(scope, admission_error))
    deploy_steps = [_as_config_dict(step) or {} for step in (_as_config_list(deploy_job.get('steps')) or [])]
    deploy_checkout = [step for step in deploy_steps if step.get('uses') == 'actions/checkout@v7']
    if (
        len(deploy_checkout) != 1
        or (_as_config_dict(deploy_checkout[0].get('with')) or {}).get('ref')
        != '${{ needs.firestore_readiness.outputs.admitted_sha }}'
    ):
        errors.append(
            ValidationError(scope, 'backend deploy checkout must remain bound to the readiness-approved commit')
        )
    outputs = _as_config_dict(readiness_job.get('outputs')) or {}
    if outputs.get('admitted_sha') != admitted_readiness_ref:
        message = (
            'manual deploy must export the exact release-proof-admitted SHA'
            if is_manual_deploy
            else 'automatic Firestore readiness must export the exact release-proof-admitted SHA'
        )
        errors.append(ValidationError(scope, message))

    readiness_steps: list[tuple[int, ConfigDict, Any]] = []
    validation_steps: list[tuple[int, ConfigDict, Any]] = []
    for index, step in enumerate(parsed_steps):
        run = step.get('run')
        if not isinstance(run, str):
            continue
        for invocation in reconciliation_invocations(run):
            if invocation.is_readiness_check:
                readiness_steps.append((index, step, invocation))
            elif invocation.is_proposal_validation:
                validation_steps.append((index, step, invocation))
    if len(readiness_steps) != 1:
        errors.append(
            ValidationError(scope, 'Firestore readiness job must contain exactly one bounded readiness check')
        )
        return errors
    readiness_index, readiness_step, readiness_invocation = readiness_steps[0]
    if readiness_step.get('id') != 'firestore_readiness':
        errors.append(ValidationError(scope, 'Firestore readiness step must expose the firestore_readiness outcome'))
    readiness_env = _as_config_dict(readiness_step.get('env')) or {}
    if readiness_env.get('FIRESTORE_PROPOSAL_PATH') != expected_path:
        errors.append(ValidationError(scope, 'Firestore proposal path must be unique to the workflow run and attempt'))
    if readiness_invocation.option_values('--proposal-output') != ('$FIRESTORE_PROPOSAL_PATH',):
        errors.append(ValidationError(scope, 'Firestore readiness must write only to FIRESTORE_PROPOSAL_PATH'))

    expected_validation_if = "${{ failure() && steps.firestore_readiness.outcome == 'failure' }}"
    if len(validation_steps) != 1:
        errors.append(ValidationError(scope, 'failed Firestore readiness must run exactly one proposal validator'))
        return errors
    validation_index, validation_step, validation_invocation = validation_steps[0]
    if (
        validation_index <= readiness_index
        or validation_step.get('id') != 'validate_firestore_proposal'
        or validation_step.get('if') != expected_validation_if
        or (_as_config_dict(validation_step.get('env')) or {}).get('FIRESTORE_PROPOSAL_PATH') != expected_path
        or validation_invocation.option_values('--validate-proposal') != ('$FIRESTORE_PROPOSAL_PATH',)
        or validation_invocation.project_values != ('${{ vars.RUNTIME_GCP_PROJECT_ID }}',)
    ):
        errors.append(ValidationError(scope, 'proposal validation must bind the failed gate path, target, and outcome'))

    upload_steps = [
        (index, step) for index, step in enumerate(parsed_steps) if step.get('uses') == 'actions/upload-artifact@v7'
    ]
    expected_upload_if = (
        "${{ failure() && steps.firestore_readiness.outcome == 'failure' "
        "&& steps.validate_firestore_proposal.outcome == 'success' }}"
    )
    if len(upload_steps) != 1:
        errors.append(ValidationError(scope, 'Firestore readiness must upload exactly one validated proposal artifact'))
        return errors
    upload_index, upload_step = upload_steps[0]
    upload_with = _as_config_dict(upload_step.get('with')) or {}
    if (
        upload_index <= validation_index
        or upload_step.get('if') != expected_upload_if
        or (_as_config_dict(upload_step.get('env')) or {}).get('FIRESTORE_PROPOSAL_PATH') != expected_path
        or upload_with.get('path') != '${{ env.FIRESTORE_PROPOSAL_PATH }}'
        or upload_with.get('if-no-files-found') != 'error'
        or upload_with.get('retention-days') != 1
    ):
        errors.append(ValidationError(scope, 'only a successfully validated bounded proposal may be uploaded'))
    return errors


def _validate_firestore_index_reconciliation_boundary(
    workflow_file: str, workflow: ConfigDict
) -> list[ValidationError]:
    """Keep backend deploys read-only against the serving Firestore project."""

    runtime_project_refs = {
        '${{ vars.RUNTIME_GCP_PROJECT_ID }}',
        '${{vars.RUNTIME_GCP_PROJECT_ID}}',
    }
    errors: list[ValidationError] = []
    for step in _workflow_steps(workflow):
        step_dict = _as_config_dict(step)
        if step_dict is None:
            continue
        run = step_dict.get('run')
        if not isinstance(run, str):
            continue
        if has_direct_firestore_mutation(run):
            errors.append(
                ValidationError(
                    f'cloud_run_workflow/{workflow_file}',
                    'backend deploy Firestore operations must be read-only (--check-only)',
                )
            )
        invocations = tuple(
            invocation for invocation in reconciliation_invocations(run) if not invocation.is_proposal_validation
        )
        if not invocations:
            continue
        if any(
            len(invocation.project_values) != 1 or invocation.project_values[0] not in runtime_project_refs
            for invocation in invocations
        ):
            errors.append(
                ValidationError(
                    f'cloud_run_workflow/{workflow_file}',
                    'Firestore index reconciliation must target vars.RUNTIME_GCP_PROJECT_ID',
                )
            )
        if len(invocations) != 1 or not invocations[0].is_readiness_check:
            errors.append(
                ValidationError(
                    f'cloud_run_workflow/{workflow_file}',
                    'backend deploy Firestore reconciliation must use bounded --check-only proposal mode',
                )
            )
    errors.extend(_validate_firestore_readiness_workflow_contract(workflow_file, workflow))
    return errors


def _workflow_variable_map(env_config: ConfigDict, expected_services: ConfigDict) -> StringMap:
    runtime_gcp_project = str(env_config.get('runtime_gcp_project', env_config['gcp_project']))
    return {
        '${{ vars.GCP_PROJECT_ID }}': str(env_config['gcp_project']),
        '${{vars.GCP_PROJECT_ID}}': str(env_config['gcp_project']),
        '${{ vars.RUNTIME_GCP_PROJECT_ID }}': runtime_gcp_project,
        '${{vars.RUNTIME_GCP_PROJECT_ID}}': runtime_gcp_project,
        '${{ vars.OMI_LLM_GATEWAY_URL }}': _manifest_env_value(expected_services, 'OMI_LLM_GATEWAY_URL'),
        '${{vars.OMI_LLM_GATEWAY_URL}}': _manifest_env_value(expected_services, 'OMI_LLM_GATEWAY_URL'),
        '${{ vars.CLOUD_RUN_VPC_NETWORK }}': _expected_flag_value(
            env_config.get('cloud_run', {}).get('network', {}).get('flags', {}).get('--network', '')
        ),
        '${{vars.CLOUD_RUN_VPC_NETWORK}}': _expected_flag_value(
            env_config.get('cloud_run', {}).get('network', {}).get('flags', {}).get('--network', '')
        ),
        '${{ vars.CLOUD_RUN_VPC_SUBNET }}': _expected_flag_value(
            env_config.get('cloud_run', {}).get('network', {}).get('flags', {}).get('--subnet', '')
        ),
        '${{vars.CLOUD_RUN_VPC_SUBNET}}': _expected_flag_value(
            env_config.get('cloud_run', {}).get('network', {}).get('flags', {}).get('--subnet', '')
        ),
        '${{ vars.MEMORY_MODE }}': _manifest_env_value(expected_services, 'MEMORY_MODE'),
        '${{vars.MEMORY_MODE}}': _manifest_env_value(expected_services, 'MEMORY_MODE'),
        '${{ vars.MEMORY_ENABLED_USERS }}': _manifest_env_value(expected_services, 'MEMORY_ENABLED_USERS'),
        '${{vars.MEMORY_ENABLED_USERS}}': _manifest_env_value(expected_services, 'MEMORY_ENABLED_USERS'),
        '${{ vars.MEMORY_V3_GET_ENABLED }}': _manifest_env_value(expected_services, 'MEMORY_V3_GET_ENABLED'),
        '${{vars.MEMORY_V3_GET_ENABLED}}': _manifest_env_value(expected_services, 'MEMORY_V3_GET_ENABLED'),
        '${{ vars.MEMORY_CANONICAL_PROMOTION_CRON_ENABLED }}': _manifest_env_value(
            expected_services, 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED'
        ),
        '${{vars.MEMORY_CANONICAL_PROMOTION_CRON_ENABLED}}': _manifest_env_value(
            expected_services, 'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED'
        ),
        '${{ vars.MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED }}': _manifest_env_value(
            expected_services, 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED'
        ),
        '${{vars.MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED}}': _manifest_env_value(
            expected_services, 'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED'
        ),
    }


def _network_flags(env_config: ConfigDict) -> ConfigDict:
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    network = _as_config_dict(cloud_run.get('network')) or {}
    return _as_config_dict(network.get('flags')) or {}


def _manifest_env_value(expected_services: ConfigDict, name: str) -> str:
    for raw_service_config in expected_services.values():
        service_config = _as_config_dict(raw_service_config) or {}
        env_config = _as_config_dict(service_config.get('env')) or {}
        env_entry = _as_config_dict(env_config.get(name))
        if isinstance(env_entry, dict) and 'value' in env_entry:
            return str(env_entry['value'])
    return ''


def _literal_env_value(entry: dict[str, Any]) -> str:
    value = entry.get('value')
    if value is None:
        return ''
    return str(value)


def _validate_env_entries(
    *,
    scope: str,
    expected: ConfigDict,
    actual: EnvEntryMap,
    strict_provisional: bool,
    config_maps: set[str] | None = None,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, expected_entry in expected.items():
        if 'config_map' in expected_entry:
            config_map = _as_config_dict(expected_entry['config_map']) or {}
            expected_name = config_map.get('name')
            if not isinstance(expected_name, str) or expected_name not in (config_maps or set()):
                errors.append(ValidationError(scope, f'env {name} must come from ConfigMap {expected_name!r}'))
            continue
        actual_entry = actual.get(name)
        if actual_entry is None:
            if _is_provisional(expected_entry) and not strict_provisional:
                continue
            errors.append(ValidationError(scope, f'missing env {name}'))
            continue
        if 'value' in expected_entry:
            if expected_entry.get('provisional') and not strict_provisional:
                if not _has_literal_value(actual_entry):
                    errors.append(ValidationError(scope, f'env {name} must have a literal value'))
                continue
            actual_value = _literal_env_value(actual_entry)
            expected_value = str(expected_entry['value'])
            if actual_value != expected_value:
                errors.append(ValidationError(scope, f'env {name} value mismatch: expected {expected_value!r}'))
        elif 'env_var' in expected_entry:
            if not _has_literal_value(actual_entry):
                errors.append(ValidationError(scope, f'env {name} must have a literal value'))
        elif 'secret' in expected_entry:
            expected_secret = expected_entry['secret']
            actual_secret = _secret_ref(actual_entry)
            if actual_secret != expected_secret:
                errors.append(ValidationError(scope, f'env {name} secret mismatch: expected {expected_secret!r}'))
    return errors


def _validate_forbidden_env_entries(
    *,
    scope: str,
    forbidden: object,
    actual: EnvEntryMap,
) -> list[ValidationError]:
    if forbidden is None:
        return []
    forbidden_names = _as_config_list(forbidden)
    if forbidden_names is None or any(not isinstance(name, str) or not name for name in forbidden_names):
        return [ValidationError(scope, 'forbidden_env must be a list of non-empty env names')]
    return [
        ValidationError(scope, f'forbidden env {name} is present')
        for name in sorted(set(forbidden_names).intersection(actual))
    ]


def _validate_forbidden_workflow_removals(
    *,
    scope: str,
    forbidden: object,
    flags: StringMap,
) -> list[ValidationError]:
    if forbidden is None:
        return []
    forbidden_names = _as_config_list(forbidden)
    if forbidden_names is None or any(not isinstance(name, str) or not name for name in forbidden_names):
        return []
    removed = {name.strip() for name in flags.get('--remove-env-vars', '').split(',') if name.strip()}
    return [
        ValidationError(scope, f'forbidden env {name} must be listed in --remove-env-vars')
        for name in sorted(set(forbidden_names).difference(removed))
    ]


def _validate_cloud_run_secret_entries(
    *,
    scope: str,
    expected: ConfigDict,
    actual: EnvEntryMap,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, expected_entry in expected.items():
        actual_entry = actual.get(name)
        if actual_entry is None:
            errors.append(ValidationError(scope, f'missing secret binding {name}'))
            continue
        actual_secret = _cloud_run_secret_ref(actual_entry)
        expected_secret = {
            'secret': expected_entry['secret'],
            'version': str(expected_entry.get('version', 'latest')),
        }
        if actual_secret != expected_secret:
            errors.append(ValidationError(scope, f'secret binding {name} mismatch: expected {expected_secret!r}'))
    return errors


def _env_entries_by_name(raw_env: object) -> EnvEntryMap:
    raw_env_list = _as_config_list(raw_env)
    if raw_env_list is None:
        return {}
    result: EnvEntryMap = {}
    for entry in raw_env_list:
        entry_dict = _as_config_dict(entry)
        if entry_dict is not None and isinstance(entry_dict.get('name'), str):
            result[entry_dict['name']] = entry_dict
    return result


def _config_map_names(raw_env_from: object) -> set[str]:
    entries = _as_config_list(raw_env_from) or []
    names: set[str] = set()
    for entry in entries:
        config_map_ref = _as_config_dict((_as_config_dict(entry) or {}).get('configMapRef'))
        name = config_map_ref.get('name') if config_map_ref is not None else None
        if isinstance(name, str):
            names.add(name)
    return names


def _literal_env_entries_by_name(raw_env: object, *, variables: StringMap | None = None) -> EnvEntryMap:
    raw_env_dict = _as_config_dict(raw_env)
    if raw_env_dict is None:
        return {}
    variables = variables or {}
    return {
        name: {'name': name, 'value': variables.get(str(value), str(value))} for name, value in raw_env_dict.items()
    }


def _substitute_values(raw: object, *, variables: StringMap) -> StringMap:
    raw_dict = _as_config_dict(raw)
    if raw_dict is None:
        return {}
    return {str(name): variables.get(str(value), str(value)) for name, value in raw_dict.items()}


def _workflow_secret_entries_by_name(raw_secrets: object) -> EnvEntryMap:
    raw_secret_dict = _as_config_dict(raw_secrets)
    if raw_secret_dict is None:
        return {}
    result: EnvEntryMap = {}
    for name, value in raw_secret_dict.items():
        secret_name, version = _parse_workflow_secret_ref(str(value))
        result[str(name)] = {
            'name': str(name),
            'valueFrom': {'secretKeyRef': {'name': secret_name, 'key': version}},
        }
    return result


def _extract_workflow_cloud_run_targets(
    workflow: ConfigDict,
    *,
    env: str,
    manifest: ConfigDict,
) -> dict[str, dict[str, ConfigDict]]:
    workflow_env = _as_config_dict(workflow.get('env')) or {}
    rendered_runtime_env = _rendered_runtime_env_outputs(workflow, env=env, manifest=manifest)
    services: dict[str, ConfigDict] = {}
    jobs: dict[str, ConfigDict] = {}
    workflow_jobs = _as_config_dict(workflow.get('jobs'))
    if workflow_jobs is None:
        return {'services': services, 'jobs': jobs}
    for raw_job in workflow_jobs.values():
        job = _as_config_dict(raw_job)
        if job is None:
            continue
        steps = _as_config_list(job.get('steps'))
        if steps is None:
            continue
        for step in steps:
            for deploy_step in _expand_cloud_run_deploy_steps(step):
                step_dict = _as_config_dict(deploy_step) or {}
                step_with = _as_config_dict(step_dict.get('with')) or {}
                env_vars = _parse_workflow_env_vars(
                    _resolve_step_output_reference(step_with.get('env_vars'), rendered_runtime_env)
                )
                secrets = _parse_workflow_env_vars(
                    _resolve_step_output_reference(step_with.get('secrets'), rendered_runtime_env)
                )
                flags = _parse_workflow_flags(
                    _resolve_step_output_reference(step_with.get('flags'), rendered_runtime_env)
                )
                if not (env_vars or secrets or flags):
                    continue
                service = _resolve_workflow_string(step_with.get('service'), workflow_env)
                job_name = _resolve_workflow_string(step_with.get('job'), workflow_env)
                payload = {'env_vars': env_vars, 'secrets': secrets, 'flags': flags}
                if service is not None:
                    services[service] = payload
                if job_name is not None:
                    jobs[job_name] = payload
    return {'services': services, 'jobs': jobs}


def _validate_sync_backfill_co_deploy(workflow_file: str, services: dict[str, ConfigDict]) -> list[ValidationError]:
    """Fail when a workflow deploys backend-sync without its bounded backfill worker.

    Union-across-workflow_files validation can mask this: manual deploy of
    backend-sync-backfill would otherwise hide an auto-dev omission.
    """
    if 'backend-sync' not in services:
        return []
    if 'backend-sync-backfill' in services:
        return []
    return [
        ValidationError(
            f'cloud_run_workflow/{workflow_file}',
            'deploys backend-sync without backend-sync-backfill',
        )
    ]


def _expand_cloud_run_deploy_steps(step: object) -> list[ConfigDict]:
    step_dict = _as_config_dict(step)
    if step_dict is None:
        return []
    if _is_cloud_run_deploy_step(step_dict):
        return [step_dict]
    uses = step_dict.get('uses')
    if not isinstance(uses, str) or not uses.startswith('./'):
        return []
    action = _load_local_composite_action(uses)
    if action is None:
        return []
    runs = _as_config_dict(action.get('runs')) or {}
    nested_steps = _as_config_list(runs.get('steps'))
    if nested_steps is None:
        return []
    caller_with = _as_config_dict(step_dict.get('with')) or {}
    expanded: list[ConfigDict] = []
    for nested in nested_steps:
        nested_dict = _as_config_dict(nested)
        if nested_dict is None or not _is_cloud_run_deploy_step(nested_dict):
            continue
        if not _composite_step_active_for_caller(nested_dict, caller_with):
            continue
        nested_with = _as_config_dict(nested_dict.get('with')) or {}
        expanded.append(
            {
                **nested_dict,
                'with': {
                    key: _resolve_composite_input_reference(value, caller_with) for key, value in nested_with.items()
                },
            }
        )
    return expanded


def _composite_step_active_for_caller(nested_step: ConfigDict, caller_with: ConfigDict) -> bool:
    """Skip composite steps gated on inputs.mode when the caller uses another mode."""
    condition = nested_step.get('if')
    if not isinstance(condition, str) or 'inputs.mode' not in condition:
        return True
    mode = str(caller_with.get('mode', ''))
    if "inputs.mode == 'worker'" in condition:
        return mode == 'worker'
    if "inputs.mode == 'platform'" in condition:
        return mode == 'platform'
    return True


def _load_local_composite_action(uses: str) -> ConfigDict | None:
    action_dir = ROOT / uses[2:]
    for name in ('action.yml', 'action.yaml'):
        path = action_dir / name
        if path.is_file():
            action = _load_yaml(path)
            runs = _as_config_dict(action.get('runs')) or {}
            if runs.get('using') == 'composite':
                return action
            return None
    return None


def _resolve_composite_input_reference(value: object, caller_with: ConfigDict) -> object:
    if not isinstance(value, str):
        return value
    resolved = value
    for name, raw in caller_with.items():
        resolved = resolved.replace('${{ inputs.' + str(name) + ' }}', str(raw))
    return resolved


def _is_cloud_run_deploy_step(step: object) -> bool:
    step_dict = _as_config_dict(step)
    if step_dict is None:
        return False
    uses = step_dict.get('uses')
    return isinstance(uses, str) and uses.startswith('google-github-actions/deploy-cloudrun@')


def _resolve_workflow_string(value: object, workflow_env: ConfigDict) -> str | None:
    if not isinstance(value, str):
        return None
    resolved = value
    for env_name, env_value in workflow_env.items():
        resolved = resolved.replace('${{ env.' + str(env_name) + ' }}', str(env_value))
    return resolved


def _rendered_runtime_env_outputs(workflow: ConfigDict, *, env: str, manifest: ConfigDict) -> StringMap:
    outputs: StringMap = {}
    for step in _workflow_steps(workflow):
        step_dict = _as_config_dict(step)
        if step_dict is None:
            continue
        if step_dict.get('id') != 'runtime-env':
            continue
        run = step_dict.get('run')
        if not isinstance(run, str) or 'render_backend_runtime_env.py' not in run:
            continue
        rendered_env = _extract_renderer_env(run, env=env)
        if rendered_env is None:
            continue
        env_config = _get_env_config(manifest, rendered_env)
        cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
        network = _as_config_dict(cloud_run.get('network')) or {}
        outputs['cloud_run_flags'] = _render_cloud_run_flags((_as_config_dict(network.get('flags')) or {}))
        services = _as_config_dict(cloud_run.get('services'))
        if services is None:
            continue
        for service, raw_service_config in services.items():
            service_config = _as_config_dict(raw_service_config)
            if service_config is None:
                continue
            output_prefix = service.replace('-', '_')
            outputs[f'{output_prefix}_env_vars'] = _render_cloud_run_env_vars(service_config.get('env', {}))
            outputs[f'{output_prefix}_secrets'] = _render_cloud_run_secrets(service_config.get('secrets', {}))
        jobs = _as_config_dict(cloud_run.get('jobs')) or {}
        for job, raw_job_config in jobs.items():
            job_config = _as_config_dict(raw_job_config)
            if job_config is None:
                continue
            output_prefix = job.replace('-', '_')
            outputs[f'{output_prefix}_flags'] = _render_cloud_run_flags(job_config.get('flags', {}))
            outputs[f'{output_prefix}_env_vars'] = _render_cloud_run_env_vars(job_config.get('env', {}))
            outputs[f'{output_prefix}_secrets'] = _render_cloud_run_secrets(job_config.get('secrets', {}))
    return outputs


def _workflow_steps(workflow: ConfigDict) -> list[Any]:
    steps: list[Any] = []
    jobs = _as_config_dict(workflow.get('jobs'))
    if jobs is None:
        return steps
    for raw_job in jobs.values():
        job = _as_config_dict(raw_job)
        if job is None:
            continue
        job_steps = _as_config_list(job.get('steps'))
        if job_steps is not None:
            steps.extend(job_steps)
    return steps


def _extract_renderer_env(run: str, *, env: str) -> str | None:
    if '--env dev' in run:
        return 'dev'
    if '--env prod' in run:
        return 'prod'
    if '--env ${{ vars.ENV }}' in run:
        return env
    return None


def _resolve_step_output_reference(raw_value: object, rendered_outputs: StringMap) -> object:
    if not isinstance(raw_value, str):
        return raw_value
    prefix = '${{ steps.runtime-env.outputs.'
    suffix = ' }}'
    resolved = raw_value
    for output_name, output_value in rendered_outputs.items():
        resolved = resolved.replace(f'{prefix}{output_name}{suffix}', output_value)
    # The backfill worker clones backend-sync's live runtime contract and then
    # overlays the manifest-rendered lane settings. Static validation checks
    # that guaranteed overlay; the deploy step separately tests the live clone.
    # Support both inline workflow steps and the sync-backfill-lifecycle composite.
    resolved = resolved.replace(
        '${{ steps.backfill-runtime.outputs.env_vars }}',
        rendered_outputs.get('backend_sync_backfill_env_vars', ''),
    )
    resolved = resolved.replace(
        '${{ steps.backfill-runtime.outputs.secrets }}',
        rendered_outputs.get('backend_sync_backfill_secrets', ''),
    )
    sync_backfill_overlay = (
        'SYNC_BACKFILL_TASKS_QUEUE=sync-backfill\n'
        'SYNC_BACKFILL_TASKS_HANDLER_URL=https://backend-sync-backfill.example.invalid/v2/sync-jobs/run\n'
        'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE=https://backend-sync-backfill.example.invalid/v2/sync-jobs/run'
    )
    resolved = resolved.replace(
        '${{ steps.sync-backfill.outputs.sync_backfill_env_vars }}',
        sync_backfill_overlay,
    )
    return resolved


def _render_cloud_run_env_vars(env_entries: object) -> str:
    env_entry_map = _as_config_dict(env_entries)
    if env_entry_map is None:
        return ''
    lines: list[str] = []
    for name, raw_entry in env_entry_map.items():
        entry = _as_config_dict(raw_entry)
        if entry is not None and ('value' in entry or 'env_var' in entry):
            lines.append(f'{name}={_render_manifest_value(name, entry)}')
    return '\n'.join(lines)


def _render_cloud_run_secrets(secret_entries: object) -> str:
    secret_entry_map = _as_config_dict(secret_entries)
    if secret_entry_map is None:
        return ''
    lines: list[str] = []
    for name, raw_entry in secret_entry_map.items():
        entry = _as_config_dict(raw_entry)
        if entry is None or 'secret' not in entry:
            continue
        version = entry.get('version', 'latest')
        lines.append(f'{name}={entry["secret"]}:{version}')
    return '\n'.join(lines)


def _render_cloud_run_flags(flag_entries: object) -> str:
    flag_entry_map = _as_config_dict(flag_entries)
    if flag_entry_map is None:
        return ''
    flags: list[str] = []
    for name, raw_entry in flag_entry_map.items():
        entry = _as_config_dict(raw_entry)
        value = _render_manifest_value(name, entry) if entry is not None else raw_entry
        flags.append(f'{name}={value}')
    return ' '.join(flags)


def _render_manifest_value(name: str, entry: ConfigDict) -> str:
    if 'value' in entry:
        return str(entry['value'])
    env_var = entry.get('env_var')
    if isinstance(env_var, str) and env_var:
        return f'__{name.strip("-").replace("-", "_")}__'
    return ''


def _parse_workflow_env_vars(raw_env_vars: object) -> StringMap:
    if raw_env_vars is None:
        return {}
    raw_env_vars_dict = _as_config_dict(raw_env_vars)
    if raw_env_vars_dict is not None:
        return {str(name): str(value) for name, value in raw_env_vars_dict.items()}
    if not isinstance(raw_env_vars, str):
        return {}
    result: StringMap = {}
    for raw_line in raw_env_vars.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        result[name.strip()] = value.strip()
    return result


def _parse_workflow_flags(raw_flags: object) -> StringMap:
    if raw_flags is None:
        return {}
    raw_flags_dict = _as_config_dict(raw_flags)
    if raw_flags_dict is not None:
        return {str(name): str(value) for name, value in raw_flags_dict.items()}
    if not isinstance(raw_flags, str):
        return {}
    result: StringMap = {}
    for raw_part in raw_flags.split():
        part = raw_part.strip()
        if not part.startswith('--') or '=' not in part:
            continue
        name, value = part.split('=', 1)
        result[name] = value
    return result


def _parse_workflow_secret_ref(raw_value: str) -> tuple[str, str]:
    if ':' not in raw_value:
        return raw_value, 'latest'
    secret_name, version = raw_value.rsplit(':', 1)
    return secret_name, version or 'latest'


def _validate_workflow_flags(
    *,
    scope: str,
    expected: ConfigDict,
    actual: StringMap,
    strict_provisional: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, expected_entry in expected.items():
        actual_value = actual.get(name)
        if actual_value is None:
            errors.append(ValidationError(scope, f'missing Cloud Run flag {name}'))
            continue
        expected_entry_dict = _as_config_dict(expected_entry)
        if expected_entry_dict is not None and 'env_var' in expected_entry_dict:
            if actual_value == '':
                errors.append(ValidationError(scope, f'Cloud Run flag {name} must have a value'))
            continue
        expected_value = _expected_flag_value(expected_entry)
        if _is_provisional(expected_entry) and not strict_provisional:
            if actual_value == '':
                errors.append(ValidationError(scope, f'Cloud Run flag {name} must have a value'))
            continue
        if actual_value != expected_value:
            errors.append(ValidationError(scope, f'Cloud Run flag {name} mismatch: expected {expected_value!r}'))
    return errors


def _expected_flag_value(expected_entry: object) -> str:
    expected_dict = _as_config_dict(expected_entry)
    if expected_dict is not None and 'value' in expected_dict:
        return str(expected_dict['value'])
    return str(expected_entry)


def _is_provisional(expected_entry: object) -> bool:
    expected_dict = _as_config_dict(expected_entry)
    return expected_dict is not None and bool(expected_dict.get('provisional'))


def _has_literal_value(entry: EnvEntry) -> bool:
    return entry.get('value') not in (None, '')


def _secret_ref(entry: EnvEntry) -> StringMap | None:
    value_from = _as_config_dict(entry.get('valueFrom'))
    if value_from is None:
        return None
    secret_ref = _as_config_dict(value_from.get('secretKeyRef'))
    if secret_ref is None:
        return None
    name = secret_ref.get('name')
    key = secret_ref.get('key')
    if not isinstance(name, str) or not isinstance(key, str):
        return None
    return {'name': name, 'key': key}


def _cloud_run_secret_ref(entry: EnvEntry) -> StringMap | None:
    value_from = _as_config_dict(entry.get('valueFrom'))
    if value_from is None:
        return None
    secret_key_ref = _as_config_dict(value_from.get('secretKeyRef'))
    if secret_key_ref is not None:
        name = secret_key_ref.get('name')
        version = secret_key_ref.get('key', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    secret_ref = _as_config_dict(value_from.get('secretRef'))
    if secret_ref is not None:
        name = secret_ref.get('name')
        version = secret_ref.get('version', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    return None


def _fetch_live_cloud_run_state(env_config: ConfigDict) -> ConfigDict:
    # This deploy pipeline (gcp_backend.yml) deploys Cloud Run *services* only — the declared
    # Cloud Run jobs (memory-maintenance-job, notifications-job) ship via their own workflows,
    # so their live state is owned elsewhere. Fetch and live-validate services only; validating
    # a job this pipeline does not deploy produced false failures (a not-found job crashed the
    # whole deploy, and notifications-job's separately-managed env legitimately differs). The
    # job contract is still validated statically against the rendered state.
    services: ConfigDict = {}
    project = env_config['gcp_project']
    region = env_config['region']
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    service_configs = _as_config_dict(cloud_run.get('services')) or {}
    for service in service_configs:
        command = [
            'gcloud',
            'run',
            'services',
            'describe',
            service,
            f'--project={project}',
            f'--region={region}',
            '--format=json',
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        raw_service_state = json.loads(result.stdout)
        service_state = _as_config_dict(raw_service_state) or {}
        spec = _as_config_dict(service_state.get('spec')) or {}
        template = _as_config_dict(spec.get('template')) or {}
        metadata = _as_config_dict(template.get('metadata')) or {}
        annotations = _as_config_dict(metadata.get('annotations')) or {}
        template_spec = _as_config_dict(template.get('spec')) or {}
        containers = _as_config_list(template_spec.get('containers')) or [{}]
        first_container = _as_config_dict(containers[0]) or {}
        services[service] = {
            'env': first_container.get('env', []),
            'flags': _cloud_run_network_flags_from_annotations(annotations),
        }
    return {'services': services}


def _cloud_run_network_flags_from_annotations(annotations: object) -> StringMap:
    annotations_dict = _as_config_dict(annotations)
    if annotations_dict is None:
        return {}
    flags: StringMap = {}
    network_interfaces = annotations_dict.get('run.googleapis.com/network-interfaces')
    if isinstance(network_interfaces, str) and network_interfaces:
        try:
            parsed_interfaces = _as_config_list(json.loads(network_interfaces)) or []
        except json.JSONDecodeError:
            parsed_interfaces = []
        if parsed_interfaces:
            first_interface = _as_config_dict(parsed_interfaces[0])
            if first_interface is not None:
                network = first_interface.get('network')
                subnet = first_interface.get('subnetwork')
                if isinstance(network, str):
                    flags['--network'] = network
                if isinstance(subnet, str):
                    flags['--subnet'] = subnet
    egress = annotations_dict.get('run.googleapis.com/vpc-access-egress')
    if isinstance(egress, str):
        flags['--vpc-egress'] = egress
    return flags


if __name__ == '__main__':
    raise SystemExit(main())
