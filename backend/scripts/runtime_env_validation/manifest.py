from __future__ import annotations

import os
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.prerecorded_stt import required_env_for_model_config, required_env_for_held_recovery  # noqa: E402
from config.stt_provider_policy import STTServingSurface, canonical_model_config, model_is_enabled  # noqa: E402
from scripts.runtime_env_durable_dispatch_contracts import (  # noqa: E402
    validate_account_deletion_dispatch_contract as _validate_account_deletion_dispatch_contract,
    validate_listen_finalization_dispatch_contract as _validate_listen_finalization_dispatch_contract,
)
from scripts.runtime_env_parakeet_contract import validate_parakeet_admission_contract  # noqa: E402
from scripts.runtime_env_capability_contracts import (
    validate_conversation_finalization_capabilities,
    validate_speaker_embedding_hosts,
    validate_voice_transcription_storage,
)  # noqa: E402
from scripts.runtime_env_memory_contract import validate_retired_memory_manifest  # noqa: E402
from scripts.render_backend_runtime_env import validate_sync_lineage_rollout  # noqa: E402
from scripts.runtime_env_validation.cloud_run import (
    _fetch_live_cloud_run_state,
    _validate_cloud_run,
)
from scripts.runtime_env_validation.common import (
    DEFAULT_MANIFEST,
    ROOT,
    ConfigDict,
    ValidationError,
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
    data_plane_project,
    validate_mentor_pipeline,
    validate_proactivity_v2_posthog_token,
)

from scripts.runtime_env_validation.workflows import _validate_cloud_run_workflows


def _canonical_memory_surfaces(env_config: ConfigDict) -> list[tuple[str, ConfigDict]]:
    """Return (scope, env-map) for every surface that can enable canonical memory."""
    surfaces: list[tuple[str, ConfigDict]] = []
    gke = _as_config_dict(env_config.get('gke')) or {}
    for service, raw_service in gke.items():
        service_config = _as_config_dict(raw_service) or {}
        env_map = _as_config_dict(service_config.get('env')) or {}
        if 'MEMORY_ENABLED' in env_map:
            surfaces.append((f'gke/{service}', env_map))
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    for service, raw_service in (_as_config_dict(cloud_run.get('services')) or {}).items():
        service_config = _as_config_dict(raw_service) or {}
        env_map = _as_config_dict(service_config.get('env')) or {}
        if 'MEMORY_ENABLED' in env_map:
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
        # GKE ports are declared in Helm values, while the host may come from
        # the manifest's shared ConfigMap. Validate the effective pair.
        if 'REDIS_DB_HOST' in (service_config.get('env') or {}):
            port = actual_env.get('REDIS_DB_PORT') or {}
            if not port.get('value') and not port.get('valueFrom'):
                errors.append(
                    ValidationError(f'gke/{service}', 'Redis requires an explicit non-empty REDIS_DB_PORT binding')
                )
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
    errors.extend(_validate_redis_ports(env_config, env))
    errors.extend(
        ValidationError('sync_lineage_rollout', message) for message in validate_sync_lineage_rollout(env, env_config)
    )
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


def _validate_redis_ports(env_config: ConfigDict, env: str) -> list[ValidationError]:
    """A Redis host must not silently fall back to the application's 6379 default.

    The four managed Cloud Run services also carry Redis host secret bindings
    from existing deployments. Require their ports even without a host entry
    in the manifest, so removing a port cannot evade this check.
    """
    required_services = {'backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'}
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    targets: list[tuple[str, ConfigDict, bool]] = []
    for group in ('services', 'jobs'):
        for name, raw in (_as_config_dict(cloud_run.get(group)) or {}).items():
            scope = f'{env}/cloud_run/{name}' if group == 'services' else f'{env}/cloud_run/jobs/{name}'
            targets.append((scope, _as_config_dict(raw) or {}, group == 'services' and name in required_services))
    desktop = _as_config_dict(env_config.get('desktop_backend'))
    if desktop is not None:
        targets.append((f'{env}/desktop_backend', desktop, False))
    errors: list[ValidationError] = []
    for scope, target, required in targets:
        bindings = _as_config_dict(target.get('env')) or {}
        secrets = _as_config_dict(target.get('secrets')) or {}
        if not required and 'REDIS_DB_HOST' not in bindings and 'REDIS_DB_HOST' not in secrets:
            continue
        if not _manifest_env_binding_is_configured(bindings, secrets, 'REDIS_DB_PORT'):
            errors.append(ValidationError(scope, 'Redis requires an explicit non-empty REDIS_DB_PORT binding'))
            continue
        port = _as_config_dict(bindings.get('REDIS_DB_PORT')) or {}
        if 'value' in port:
            value = str(port['value'])
            if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 65535:
                errors.append(ValidationError(scope, 'REDIS_DB_PORT must be a TCP port from 1 to 65535'))
        if port.get('provisional'):
            errors.append(ValidationError(scope, 'REDIS_DB_PORT must not be provisional for a Redis host'))
    return errors


def _validate_memory_job_retirement(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Keep the retired memory-maintenance bindings out of every runtime surface.

    memory-maintenance-job never served production and was retired on
    2026-10-26: required intake runs inline at write time with Dream's sweep
    as retry owner. The manifest must not re-introduce the job, its retired
    maintenance or consolidation switches, or its deploy window, and
    notifications-job keeps none of the memory-plane bindings. The scheduled
    X-extraction Flex contract stays.
    """
    errors: list[ValidationError] = []
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    jobs = _as_config_dict(cloud_run.get('jobs')) or {}

    notifications_job = _as_config_dict(jobs.get('notifications-job')) or {}
    notifications_env = _as_config_dict(notifications_job.get('env')) or {}
    notifications_secrets = _as_config_dict(notifications_job.get('secrets')) or {}
    notifications_scope = f'{env}/cloud_run/jobs/notifications-job'
    for forbidden_env in sorted(_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_ENV.intersection(notifications_env)):
        errors.append(ValidationError(notifications_scope, f'env {forbidden_env} belongs to the retired memory job'))
    for forbidden_secret in sorted(_NOTIFICATIONS_JOB_FORBIDDEN_MEMORY_SECRETS.intersection(notifications_secrets)):
        errors.append(
            ValidationError(notifications_scope, f'secret {forbidden_secret} belongs to the retired memory job')
        )

    x_sync_scope = f'{env}/cloud_run/jobs/x-connector-sync-job'
    x_sync_job = _as_config_dict(jobs.get('x-connector-sync-job')) or {}
    x_sync_env = _as_config_dict(x_sync_job.get('env')) or {}
    x_sync_secrets = _as_config_dict(x_sync_job.get('secrets')) or {}
    x_sync_flex_capable = (_manifest_literal_env_value(x_sync_env, 'OMI_BACKGROUND_FLEX_CAPABLE') or '').strip().lower()
    if x_sync_flex_capable != 'true':
        errors.append(
            ValidationError(
                x_sync_scope,
                'OMI_BACKGROUND_FLEX_CAPABLE must be true so the shared live flag covers scheduled X extraction',
            )
        )
    x_sync_gateway_url = _as_config_dict(x_sync_env.get('OMI_LLM_GATEWAY_URL'))
    if x_sync_gateway_url is None or x_sync_gateway_url.get('env_var') != 'OMI_LLM_GATEWAY_URL':
        errors.append(
            ValidationError(
                x_sync_scope,
                'OMI_LLM_GATEWAY_URL must be derived from the verified gateway endpoint for scheduled X Flex',
            )
        )
    if 'OMI_LLM_GATEWAY_SERVICE_TOKEN' not in x_sync_secrets:
        errors.append(
            ValidationError(
                x_sync_scope,
                'missing secret OMI_LLM_GATEWAY_SERVICE_TOKEN for scheduled X Flex',
            )
        )

    if 'memory-maintenance-job' in jobs:
        errors.append(
            ValidationError(f'{env}/cloud_run/jobs', 'memory-maintenance-job is retired; remove its manifest block')
        )
    retired_env = (
        'MEMORY_CANONICAL_MAINTENANCE_ENABLED',
        'MEMORY_MAINTENANCE_CAPTURED_AFTER',
        'MEMORY_CANONICAL_CONSOLIDATION_ENABLED',
        'MEMORY_CANONICAL_MAINTENANCE_FLEX',
    )
    for job_name, raw_job in jobs.items():
        other_env = _as_config_dict(_as_config_dict(raw_job).get('env')) or {}
        for name in retired_env:
            if name in other_env:
                errors.append(
                    ValidationError(f'{env}/cloud_run/jobs/{job_name}', f'retired memory env {name} must be absent')
                )
    for surface_scope, surface_env in _canonical_memory_surfaces(env_config):
        for name in retired_env:
            if name in surface_env:
                errors.append(ValidationError(surface_scope, f'retired memory env {name} must be absent'))
    return errors


def _validate_prerecorded_stt_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Keep selected providers and their required runtime bindings deployable together."""
    errors: list[ValidationError] = []
    surfaces: list[tuple[str, ConfigDict, ConfigDict]] = []

    gke = _as_config_dict(env_config.get('gke')) or {}
    for service, raw_service in gke.items():
        service_config = _as_config_dict(raw_service) or {}
        surfaces.append((f'{env}/gke/{service}', _as_config_dict(service_config.get('env')) or {}, {}))

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
        # This audience identifies the CPU recovery host, not general STT/GPU
        # workers. Default-on independent recovery needs the same pure contract
        # checked by the runtime before it claims its sole paid attempt.
        independent = _manifest_literal_env_value(env_map, 'BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED')
        if (
            _manifest_env_binding_is_configured(env_map, secrets_map, 'BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE')
            and (independent or '').strip().lower() != 'false'
        ):
            for required_env in required_env_for_held_recovery():
                if not _manifest_env_binding_is_configured(env_map, secrets_map, required_env):
                    errors.append(
                        ValidationError(scope, f'independent held recovery requires non-empty {required_env}')
                    )
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
    """Require deployed STT lists to follow the code-owned serving policy."""
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
            if env_name == 'STT_SERVICE_MODELS':
                models = [model.strip() for model in (_manifest_literal_env_value(env_map, env_name) or '').split(',')]
                if scope == f'{env}/gke/backend-listen':
                    # The live listener may also use reviewed route aliases such as parakeet-window.
                    if models and all(model_is_enabled(model, STTServingSurface.STREAMING) for model in models):
                        continue
                else:
                    # Other services may omit providers while retaining canonical policy order.
                    ordered_subset = [model for model in expected_value.split(',') if model in models]
                    if models and models == ordered_subset:
                        continue
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


VERTEX_PT_CONTRACT = 'Vertex PT: 5 GSU gemini-2.5-flash us-central1, expires ~2027-05-28'
_DESKTOP_BACKEND_VERTEX_PT_ENV = {
    'USE_VERTEX_AI': 'true',
    'GCP_LOCATION': 'us-central1',
}


def _validate_desktop_backend_vertex_pt_contract(env: str, env_config: ConfigDict) -> list[ValidationError]:
    expected_project = 'based-hardware' if env == 'prod' else 'based-hardware-dev'
    desktop = _as_config_dict(env_config.get('desktop_backend')) or {}
    env_map = _as_config_dict(desktop.get('env')) or {}
    required = {**_DESKTOP_BACKEND_VERTEX_PT_ENV, 'GOOGLE_CLOUD_PROJECT': expected_project}
    errors: list[ValidationError] = []
    for name, expected in required.items():
        actual = _manifest_literal_env_value(env_map, name)
        if actual != expected:
            errors.append(
                ValidationError(
                    f'{env}/desktop_backend',
                    f'{name} must be {expected!r} so company-paid Flash consumes Vertex PT. {VERTEX_PT_CONTRACT}',
                )
            )
    return errors


def _validate_proactivity_v2_flag_hosts(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Every feed/mentor host and gateway admission executor needs the dedicated token."""
    gke = _as_config_dict(env_config.get('gke')) or {}
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    services = _as_config_dict(cloud_run.get('services')) or {}
    hosts = [(f'gke/{name}', gke.get(name)) for name in ('backend-listen', 'pusher')]
    hosts.extend((f'cloud_run/{name}', host) for name, host in services.items())
    hosts.extend((name, env_config.get(name)) for name in ('llm_gateway', 'desktop_backend'))
    errors: list[ValidationError] = []
    for name, host in hosts:
        env_map = _as_config_dict((_as_config_dict(host) or {}).get('env')) or {}
        errors.extend(validate_proactivity_v2_posthog_token(scope=f'{env}/{name}', env_entries=env_map, required=True))

    # Gateway has its own manifest section, outside _validate_gke's service loop.
    gateway = _as_config_dict(env_config.get('llm_gateway')) or {}
    gateway_env = _as_config_dict(gateway.get('env')) or {}
    values = _load_yaml(ROOT / f'backend/charts/llm-gateway/{env}_omi_llm_gateway_values.yaml')
    errors.extend(
        _validate_env_entries(
            scope=f'{env}/llm_gateway',
            expected={
                name: gateway_env[name]
                for name in ('PROACTIVITY_V2_POSTHOG_TOKEN', 'PROACTIVITY_V2_POSTHOG_HOST')
                if name in gateway_env
            },
            actual=_env_entries_by_name(values.get('env', [])),
            strict_provisional=True,
        )
    )
    return errors


def validate_runtime_env(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    cloud_run_state_path: Path | None = None,
    check_live_cloud_run: bool = False,
    check_workflows: bool = False,
    workflow_root: Path | None = None,
    strict_provisional: bool = False,
) -> list[ValidationError]:
    manifest = _load_yaml(manifest_path)
    env_config = _get_env_config(manifest, env)
    errors = _validate_manifest_shape(env_config, env)
    errors.extend(validate_mentor_pipeline(scope=env, config=env_config))
    if errors:
        return errors

    errors.extend(_validate_desktop_backend_vertex_pt_contract(env, env_config))
    errors.extend(_validate_proactivity_v2_flag_hosts(env, env_config))
    errors.extend(_validate_gke(env_config, strict_provisional=strict_provisional))
    errors.extend(validate_conversation_finalization_capabilities(env, env_config))
    errors.extend(validate_speaker_embedding_hosts(env, env_config))
    errors.extend(validate_voice_transcription_storage(env, env_config))
    errors.extend(_validate_stt_serving_model_policy(env, env_config))
    errors.extend(validate_parakeet_admission_contract(env, env_config))
    errors.extend(_validate_prerecorded_stt_contract(env, env_config))
    errors.extend(_validate_memory_job_retirement(env, env_config))
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
    elif check_live_cloud_run:
        cloud_run_state = _fetch_live_cloud_run_state(env_config)

    if cloud_run_state is not None:
        errors.extend(_validate_cloud_run(env_config, cloud_run_state, strict_provisional=strict_provisional))
        errors.extend(_validate_sync_ledger_fence_mode(env_config, cloud_run_state))
    return errors
