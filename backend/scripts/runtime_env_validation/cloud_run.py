from __future__ import annotations

import json
import os
import subprocess

from scripts.runtime_env_durable_dispatch_contracts import ValidationError
from scripts.runtime_env_validation.common import (
    ConfigDict,
    StringMap,
    _as_config_dict,
    _as_config_list,
    _env_entries_by_name,
    _expected_flag_value,
    _network_flags,
    _validate_cloud_run_secret_entries,
    _validate_env_entries,
    _validate_forbidden_env_entries,
    compute_project,
)
from scripts.runtime_env_validation.workflows import _validate_workflow_flags


def _rendered_env_var_value(entry: ConfigDict, *, env_name: str) -> str:
    default = str(entry.get('default', f'__rendered_{env_name}__'))
    env_var = entry.get('env_var')
    if isinstance(env_var, str):
        return os.getenv(env_var, default)
    return default


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
                        'value': _rendered_env_var_value(entry, env_name=str(env_name)),
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
                        'value': _rendered_env_var_value(entry, env_name=str(env_name)),
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


def _fetch_live_cloud_run_state(env_config: ConfigDict) -> ConfigDict:
    # This deploy pipeline (gcp_backend.yml) deploys Cloud Run *services* only — the declared
    # Cloud Run jobs (memory-maintenance-job, notifications-job) ship via their own workflows,
    # so their live state is owned elsewhere. Fetch and live-validate services only; validating
    # a job this pipeline does not deploy produced false failures (a not-found job crashed the
    # whole deploy, and notifications-job's separately-managed env legitimately differs). The
    # job contract is still validated statically against the rendered state.
    services: ConfigDict = {}
    project = compute_project(env_config)
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
