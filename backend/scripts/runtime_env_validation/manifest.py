from __future__ import annotations

import os
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.prerecorded_stt import required_env_for_model_config  # noqa: E402
from config.stt_provider_policy import STTServingSurface, canonical_model_config  # noqa: E402
from scripts.runtime_env_durable_dispatch_contracts import (  # noqa: E402
    validate_account_deletion_dispatch_contract as _validate_account_deletion_dispatch_contract,
    validate_listen_finalization_dispatch_contract as _validate_listen_finalization_dispatch_contract,
)
from scripts.runtime_env_parakeet_contract import validate_parakeet_admission_contract  # noqa: E402
from scripts.runtime_env_memory_contract import validate_retired_memory_manifest  # noqa: E402
from scripts.runtime_env_validation.cloud_run import (
    _build_rendered_cloud_run_state,
    _fetch_live_cloud_run_state,
    _validate_cloud_run,
)
from scripts.runtime_env_validation.common import (
    DEFAULT_MANIFEST,
    ROOT,
    ConfigDict,
    ValidationError,
    _MEMORY_MAINTENANCE_DEV_REQUIRED_FLAGS,
    _NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_ENV,
    _NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_SECRETS,
    _SYNC_LEDGER_FENCE_MODES,
    _SYNC_LEDGER_FENCE_SERVICES,
    _as_config_dict,
    _as_config_list,
    _config_map_names,
    _env_entries_by_name,
    _expected_flag_value,
    _get_env_config,
    _literal_env_value,
    _load_json,
    _load_yaml,
    _manifest_env_value,
    _network_flags,
    _validate_cloud_run_secret_entries,
    _validate_env_entries,
    _validate_forbidden_env_entries,
)

_MEMORY_MAINTENANCE_GATEWAY_REQUIRED_ENV = {
    'OMI_LLM_GATEWAY_URL',
    'OMI_LLM_GATEWAY_FEATURE_MODE',
    'OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION',
}
_MEMORY_MAINTENANCE_GATEWAY_REQUIRED_SECRETS = {'OMI_LLM_GATEWAY_SERVICE_TOKEN'}
from scripts.runtime_env_validation.workflows import _validate_cloud_run_workflows


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


def _manifest_literal_env_value(env_map: object, key: str) -> str | None:
    entries = _as_config_dict(env_map) or {}
    entry = _as_config_dict(entries.get(key))
    if entry is None or 'value' not in entry:
        return None
    return str(entry['value'])


def _validate_gke(env_config: ConfigDict, *, strict_provisional: bool) -> list[ValidationError]:
    errors: list[ValidationError] = []
    gke_config = _as_config_dict(env_config.get('gke')) or {}
    config_map = _as_config_dict(gke_config.get('config_map'))
    config_map_name = config_map.get('name') if config_map is not None else None
    config_map_entries = _as_config_dict(config_map.get('entries')) if config_map is not None else None
    for service, raw_service_config in gke_config.items():
        if service == 'config_map':
            continue
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
        # The generated ConfigMap is a deployment boundary, not merely an
        # envFrom hint. A typo here otherwise applies a new unused map and
        # leaves workloads on stale configuration.
        if config_map is not None:
            for env_name, raw_entry in (_as_config_dict(service_config.get('env')) or {}).items():
                entry = _as_config_dict(raw_entry) or {}
                binding = _as_config_dict(entry.get('config_map'))
                if binding is None:
                    continue
                binding_name = binding.get('name')
                binding_key = binding.get('key')
                if not isinstance(config_map_name, str) or binding_name != config_map_name:
                    errors.append(
                        ValidationError(
                            f'gke/{service}',
                            f'env {env_name} ConfigMap name must match declared gke.config_map.name {config_map_name!r}',
                        )
                    )
                if not isinstance(binding_key, str) or binding_key not in (config_map_entries or {}):
                    errors.append(
                        ValidationError(f'gke/{service}', f'env {env_name} ConfigMap key {binding_key!r} is undeclared')
                    )
    return errors


def _validate_manifest_shape(env_config: ConfigDict, env: str) -> list[ValidationError]:
    errors = validate_retired_memory_manifest(env, env_config)
    for key in ('region', 'gke', 'cloud_run'):
        if key not in env_config:
            errors.append(ValidationError(env, f'missing {key}'))
    if 'compute_project' not in env_config and 'gcp_project' not in env_config:
        errors.append(ValidationError(env, 'missing compute_project'))
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


def _validate_memory_maintenance_job_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Require memory-maintenance-job to exist and stay aligned with MEMORY_MODE rollout.

    Prod may keep MEMORY_MODE=off with cron disabled. Enabling MEMORY_MODE=read on any
    request-path surface without enabling the dedicated maintenance job fails validation
    so Gate 3 cannot forget ST→LT hosting.

    Also rejects:
    - canonical maintenance env/secrets on notifications-job (its workflow
      removes only those retired live bindings);
    - request-path / other-job hosts keeping MEMORY_CANONICAL_MAINTENANCE_ENABLED=true
      (ST→LT cron must run only on memory-maintenance-job);
    - empty MEMORY_ENABLED_USERS on a read-mode surface while the job has a non-empty allowlist.
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
        'MEMORY_CANONICAL_MAINTENANCE_ENABLED',
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED',
        'PINECONE_INDEX_NAME',
        'TYPESENSE_HOST_PORT',
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
    job_cron = (_manifest_literal_env_value(job_env, 'MEMORY_CANONICAL_MAINTENANCE_ENABLED') or '').strip().lower()
    job_users = (_manifest_literal_env_value(job_env, 'MEMORY_ENABLED_USERS') or '').strip()

    if job_cron == 'true':
        for required_env in sorted(_MEMORY_MAINTENANCE_GATEWAY_REQUIRED_ENV):
            if required_env not in job_env:
                errors.append(
                    ValidationError(scope, f'missing gateway env {required_env} while canonical maintenance is enabled')
                )
        for required_secret in sorted(_MEMORY_MAINTENANCE_GATEWAY_REQUIRED_SECRETS):
            if required_secret not in job_secrets:
                errors.append(
                    ValidationError(
                        scope, f'missing gateway secret {required_secret} while canonical maintenance is enabled'
                    )
                )
        gateway_url = _as_config_dict(job_env.get('OMI_LLM_GATEWAY_URL'))
        if gateway_url is not None and gateway_url.get('env_var') != 'OMI_LLM_GATEWAY_URL':
            errors.append(
                ValidationError(
                    scope, 'OMI_LLM_GATEWAY_URL must be derived from the verified gateway endpoint, not pinned directly'
                )
            )
        gateway_mode = (_manifest_literal_env_value(job_env, 'OMI_LLM_GATEWAY_FEATURE_MODE') or '').strip().lower()
        if gateway_mode != 'gateway':
            errors.append(
                ValidationError(
                    scope, 'OMI_LLM_GATEWAY_FEATURE_MODE must be gateway while canonical maintenance is enabled'
                )
            )
        direct_exception = (
            (_manifest_literal_env_value(job_env, 'OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION') or '').strip().lower()
        )
        if direct_exception != 'false':
            errors.append(
                ValidationError(
                    scope,
                    'OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION must be false for canonical memory L2 maintenance',
                )
            )
        if env == 'prod':
            prod_allow = (
                (_manifest_literal_env_value(job_env, 'OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE') or '').strip().lower()
            )
            if prod_allow != 'true':
                errors.append(
                    ValidationError(
                        scope,
                        'OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE must be true for production canonical maintenance',
                    )
                )

    # Non-job hosts must not enable the ST→LT cron (would duplicate maintenance).
    for other_job_name, raw_other_job in jobs.items():
        if other_job_name == 'memory-maintenance-job':
            continue
        other_job = _as_config_dict(raw_other_job) or {}
        other_env = _as_config_dict(other_job.get('env')) or {}
        other_cron = (
            (_manifest_literal_env_value(other_env, 'MEMORY_CANONICAL_MAINTENANCE_ENABLED') or '').strip().lower()
        )
        if other_cron == 'true':
            errors.append(
                ValidationError(
                    f'{env}/cloud_run/jobs/{other_job_name}',
                    'MEMORY_CANONICAL_MAINTENANCE_ENABLED must be false; '
                    'ST→LT cron is hosted only by memory-maintenance-job',
                )
            )

    read_surfaces = []
    for surface_scope, surface_env in _canonical_memory_surfaces(env_config):
        surface_mode = (_manifest_literal_env_value(surface_env, 'MEMORY_MODE') or '').strip().lower()
        surface_cron = (
            (_manifest_literal_env_value(surface_env, 'MEMORY_CANONICAL_MAINTENANCE_ENABLED') or '').strip().lower()
        )
        if surface_cron == 'true':
            errors.append(
                ValidationError(
                    surface_scope,
                    'MEMORY_CANONICAL_MAINTENANCE_ENABLED must be false on request-path surfaces; '
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
                    'MEMORY_CANONICAL_MAINTENANCE_ENABLED must be false while MEMORY_MODE is off',
                )
            )
        for surface_scope, _surface_env, surface_mode in read_surfaces:
            errors.append(
                ValidationError(
                    scope,
                    f'{surface_scope} MEMORY_MODE={surface_mode!r} requires memory-maintenance-job '
                    'MEMORY_MODE=read and MEMORY_CANONICAL_MAINTENANCE_ENABLED=true '
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
                'MEMORY_CANONICAL_MAINTENANCE_ENABLED must be true when MEMORY_MODE is not off '
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
    if env in {'dev', 'prod'}:
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


def validate_runtime_env(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    cloud_run_state_path: Path | None = None,
    check_live_cloud_run: bool = False,
    check_rendered_cloud_run: bool = False,
    check_workflows: bool = False,
    workflow_root: Path | None = None,
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
                workflow_root=workflow_root,
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
