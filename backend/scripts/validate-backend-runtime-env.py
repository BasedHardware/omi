#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'


@dataclass(frozen=True)
class ValidationError:
    scope: str
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate backend runtime env manifests against checked-in GKE config and Cloud Run state.'
    )
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
    check_workflows: bool = False,
    strict_provisional: bool = False,
) -> list[ValidationError]:
    manifest = _load_yaml(manifest_path)
    env_config = _get_env_config(manifest, env)
    errors = _validate_manifest_shape(env_config, env)
    if errors:
        return errors

    errors.extend(_validate_gke(env_config, strict_provisional=strict_provisional))
    if check_workflows:
        errors.extend(
            _validate_cloud_run_workflows(
                env,
                env_config,
                strict_provisional=strict_provisional,
                manifest_path=manifest_path,
            )
        )

    cloud_run_state = None
    if cloud_run_state_path is not None:
        cloud_run_state = _load_json(cloud_run_state_path)
    elif check_live_cloud_run:
        cloud_run_state = _fetch_live_cloud_run_state(env_config)

    if cloud_run_state is not None:
        errors.extend(_validate_cloud_run(env_config, cloud_run_state, strict_provisional=strict_provisional))
    return errors


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return loaded


def _load_json(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return loaded


def _get_env_config(manifest: dict[str, Any], env: str) -> dict[str, Any]:
    environments = manifest.get('environments')
    if not isinstance(environments, dict) or env not in environments:
        raise ValueError(f'manifest has no environments.{env}')
    env_config = environments[env]
    if not isinstance(env_config, dict):
        raise ValueError(f'environments.{env} must be a mapping')
    return env_config


def _validate_manifest_shape(env_config: dict[str, Any], env: str) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for key in ('gcp_project', 'region', 'gke', 'cloud_run'):
        if key not in env_config:
            errors.append(ValidationError(env, f'missing {key}'))
    cloud_run_services = env_config.get('cloud_run', {}).get('services')
    if not isinstance(cloud_run_services, dict) or not cloud_run_services:
        errors.append(ValidationError(env, 'cloud_run.services must be a non-empty mapping'))
    return errors


def _validate_gke(env_config: dict[str, Any], *, strict_provisional: bool) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for service, service_config in env_config.get('gke', {}).items():
        values_file = ROOT / service_config['values_file']
        values = _load_yaml(values_file)
        actual_env = _env_entries_by_name(values.get('env', []))
        errors.extend(
            _validate_env_entries(
                scope=f'gke/{service}',
                expected=service_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
            )
        )
    return errors


def _validate_cloud_run(
    env_config: dict[str, Any],
    cloud_run_state: dict[str, Any],
    *,
    strict_provisional: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    state_services = cloud_run_state.get('services')
    if not isinstance(state_services, dict):
        return [ValidationError('cloud_run', 'state must contain services mapping')]

    for service, service_config in env_config['cloud_run']['services'].items():
        service_state = state_services.get(service)
        if not isinstance(service_state, dict):
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
            _validate_cloud_run_secret_entries(
                scope=f'cloud_run/{service}',
                expected=service_config.get('secrets', {}),
                actual=actual_env,
            )
        )
        errors.extend(
            _validate_workflow_flags(
                scope=f'cloud_run/{service}',
                expected=env_config.get('cloud_run', {}).get('network', {}).get('flags', {}),
                actual=service_state.get('flags', {}),
                strict_provisional=strict_provisional,
            )
        )
    return errors


def _validate_cloud_run_workflows(
    env: str,
    env_config: dict[str, Any],
    *,
    strict_provisional: bool,
    manifest_path: Path,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    workflow_files = env_config.get('cloud_run', {}).get('workflow_files', [])
    if not isinstance(workflow_files, list):
        return [ValidationError('cloud_run/workflows', 'workflow_files must be a list')]

    expected_services = env_config['cloud_run']['services']
    workflow_services: dict[str, dict[str, Any]] = {}
    for workflow_file in workflow_files:
        if not isinstance(workflow_file, str):
            errors.append(ValidationError('cloud_run/workflows', 'workflow file paths must be strings'))
            continue
        workflow_path = ROOT / workflow_file
        workflow = _load_yaml(workflow_path)
        workflow_services.update(_extract_workflow_cloud_run_services(workflow, env=env, manifest_path=manifest_path))

    for service, service_config in expected_services.items():
        service_state = workflow_services.get(service)
        if service_state is None:
            errors.append(ValidationError(f'cloud_run_workflow/{service}', 'missing deploy-cloudrun env_vars block'))
            continue
        runtime_gcp_project = str(env_config.get('runtime_gcp_project', env_config['gcp_project']))
        workflow_vars = {
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
        actual_env = _literal_env_entries_by_name(service_state.get('env_vars', {}), variables=workflow_vars)
        errors.extend(
            _validate_env_entries(
                scope=f'cloud_run_workflow/{service}',
                expected=service_config.get('env', {}),
                actual=actual_env,
                strict_provisional=strict_provisional,
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
                expected=env_config.get('cloud_run', {}).get('network', {}).get('flags', {}),
                actual=_substitute_values(service_state.get('flags', {}), variables=workflow_vars),
                strict_provisional=strict_provisional,
            )
        )
    return errors


def _manifest_env_value(expected_services: dict[str, Any], name: str) -> str:
    for service_config in expected_services.values():
        env_entry = service_config.get('env', {}).get(name)
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
    expected: dict[str, Any],
    actual: dict[str, dict[str, Any]],
    strict_provisional: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, expected_entry in expected.items():
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


def _validate_cloud_run_secret_entries(
    *,
    scope: str,
    expected: dict[str, Any],
    actual: dict[str, dict[str, Any]],
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


def _env_entries_by_name(raw_env: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_env, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in raw_env:
        if isinstance(entry, dict) and isinstance(entry.get('name'), str):
            result[entry['name']] = entry
    return result


def _literal_env_entries_by_name(raw_env: Any, *, variables: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_env, dict):
        return {}
    variables = variables or {}
    return {name: {'name': name, 'value': variables.get(str(value), str(value))} for name, value in raw_env.items()}


def _substitute_values(raw: Any, *, variables: dict[str, str]) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(name): variables.get(str(value), str(value)) for name, value in raw.items()}


def _workflow_secret_entries_by_name(raw_secrets: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_secrets, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, value in raw_secrets.items():
        secret_name, version = _parse_workflow_secret_ref(str(value))
        result[str(name)] = {
            'name': str(name),
            'valueFrom': {'secretKeyRef': {'name': secret_name, 'key': version}},
        }
    return result


def _extract_workflow_cloud_run_services(
    workflow: dict[str, Any],
    *,
    env: str,
    manifest_path: Path,
) -> dict[str, dict[str, Any]]:
    workflow_env = workflow.get('env', {})
    if not isinstance(workflow_env, dict):
        workflow_env = {}
    rendered_runtime_env = _rendered_runtime_env_outputs(workflow, env=env, manifest_path=manifest_path)
    result: dict[str, dict[str, Any]] = {}
    jobs = workflow.get('jobs', {})
    if not isinstance(jobs, dict):
        return result
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get('steps', [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not _is_cloud_run_deploy_step(step):
                continue
            step_with = step.get('with', {})
            service = _resolve_workflow_string(step_with.get('service'), workflow_env)
            if service is None:
                continue
            env_vars = _parse_workflow_env_vars(
                _resolve_step_output_reference(step_with.get('env_vars'), rendered_runtime_env)
            )
            secrets = _parse_workflow_env_vars(
                _resolve_step_output_reference(step_with.get('secrets'), rendered_runtime_env)
            )
            flags = _parse_workflow_flags(_resolve_step_output_reference(step_with.get('flags'), rendered_runtime_env))
            if env_vars or secrets or flags:
                result[service] = {'env_vars': env_vars, 'secrets': secrets, 'flags': flags}
    return result


def _is_cloud_run_deploy_step(step: Any) -> bool:
    if not isinstance(step, dict):
        return False
    uses = step.get('uses')
    return isinstance(uses, str) and uses.startswith('google-github-actions/deploy-cloudrun@')


def _resolve_workflow_string(value: Any, workflow_env: dict[str, Any]) -> str | None:
    if not isinstance(value, str):
        return None
    resolved = value
    for env_name, env_value in workflow_env.items():
        resolved = resolved.replace('${{ env.' + str(env_name) + ' }}', str(env_value))
    return resolved


def _rendered_runtime_env_outputs(workflow: dict[str, Any], *, env: str, manifest_path: Path) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for step in _workflow_steps(workflow):
        if not isinstance(step, dict):
            continue
        if step.get('id') != 'runtime-env':
            continue
        run = step.get('run')
        if not isinstance(run, str) or 'render-backend-runtime-env.py' not in run:
            continue
        rendered_env = _extract_renderer_env(run, env=env)
        if rendered_env is None:
            continue
        manifest = _load_yaml(manifest_path)
        env_config = _get_env_config(manifest, rendered_env)
        cloud_run = env_config.get('cloud_run', {})
        outputs['cloud_run_flags'] = _render_cloud_run_flags(cloud_run.get('network', {}).get('flags', {}))
        services = cloud_run.get('services', {})
        if not isinstance(services, dict):
            continue
        for service, service_config in services.items():
            if not isinstance(service_config, dict):
                continue
            output_prefix = service.replace('-', '_')
            outputs[f'{output_prefix}_env_vars'] = _render_cloud_run_env_vars(service_config.get('env', {}))
            outputs[f'{output_prefix}_secrets'] = _render_cloud_run_secrets(service_config.get('secrets', {}))
    return outputs


def _workflow_steps(workflow: dict[str, Any]) -> list[Any]:
    steps: list[Any] = []
    jobs = workflow.get('jobs', {})
    if not isinstance(jobs, dict):
        return steps
    for job in jobs.values():
        if isinstance(job, dict) and isinstance(job.get('steps'), list):
            steps.extend(job['steps'])
    return steps


def _extract_renderer_env(run: str, *, env: str) -> str | None:
    if '--env dev' in run:
        return 'dev'
    if '--env prod' in run:
        return 'prod'
    if '--env ${{ vars.ENV }}' in run:
        return env
    return None


def _resolve_step_output_reference(raw_value: Any, rendered_outputs: dict[str, str]) -> Any:
    if not isinstance(raw_value, str):
        return raw_value
    prefix = '${{ steps.runtime-env.outputs.'
    suffix = ' }}'
    resolved = raw_value
    for output_name, output_value in rendered_outputs.items():
        resolved = resolved.replace(f'{prefix}{output_name}{suffix}', output_value)
    return resolved


def _render_cloud_run_env_vars(env_entries: Any) -> str:
    if not isinstance(env_entries, dict):
        return ''
    lines = []
    for name, entry in env_entries.items():
        if isinstance(entry, dict) and ('value' in entry or 'env_var' in entry):
            lines.append(f'{name}={_render_manifest_value(name, entry)}')
    return '\n'.join(lines)


def _render_cloud_run_secrets(secret_entries: Any) -> str:
    if not isinstance(secret_entries, dict):
        return ''
    lines = []
    for name, entry in secret_entries.items():
        if not isinstance(entry, dict) or 'secret' not in entry:
            continue
        version = entry.get('version', 'latest')
        lines.append(f'{name}={entry["secret"]}:{version}')
    return '\n'.join(lines)


def _render_cloud_run_flags(flag_entries: Any) -> str:
    if not isinstance(flag_entries, dict):
        return ''
    flags = []
    for name, entry in flag_entries.items():
        value = _render_manifest_value(name, entry) if isinstance(entry, dict) else entry
        flags.append(f'{name}={value}')
    return ' '.join(flags)


def _render_manifest_value(name: str, entry: dict[str, Any]) -> str:
    if 'value' in entry:
        return str(entry['value'])
    env_var = entry.get('env_var')
    if isinstance(env_var, str) and env_var:
        return f'__{name.strip("-").replace("-", "_")}__'
    return ''


def _parse_workflow_env_vars(raw_env_vars: Any) -> dict[str, str]:
    if raw_env_vars is None:
        return {}
    if isinstance(raw_env_vars, dict):
        return {str(name): str(value) for name, value in raw_env_vars.items()}
    if not isinstance(raw_env_vars, str):
        return {}
    result: dict[str, str] = {}
    for raw_line in raw_env_vars.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        result[name.strip()] = value.strip()
    return result


def _parse_workflow_flags(raw_flags: Any) -> dict[str, str]:
    if raw_flags is None:
        return {}
    if isinstance(raw_flags, dict):
        return {str(name): str(value) for name, value in raw_flags.items()}
    if not isinstance(raw_flags, str):
        return {}
    result: dict[str, str] = {}
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
    expected: dict[str, Any],
    actual: dict[str, str],
    strict_provisional: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, expected_entry in expected.items():
        actual_value = actual.get(name)
        if actual_value is None:
            errors.append(ValidationError(scope, f'missing Cloud Run flag {name}'))
            continue
        if isinstance(expected_entry, dict) and 'env_var' in expected_entry:
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


def _expected_flag_value(expected_entry: Any) -> str:
    if isinstance(expected_entry, dict) and 'value' in expected_entry:
        return str(expected_entry['value'])
    return str(expected_entry)


def _is_provisional(expected_entry: Any) -> bool:
    return isinstance(expected_entry, dict) and bool(expected_entry.get('provisional'))


def _has_literal_value(entry: dict[str, Any]) -> bool:
    return entry.get('value') not in (None, '')


def _secret_ref(entry: dict[str, Any]) -> dict[str, str] | None:
    value_from = entry.get('valueFrom')
    if not isinstance(value_from, dict):
        return None
    secret_ref = value_from.get('secretKeyRef')
    if not isinstance(secret_ref, dict):
        return None
    name = secret_ref.get('name')
    key = secret_ref.get('key')
    if not isinstance(name, str) or not isinstance(key, str):
        return None
    return {'name': name, 'key': key}


def _cloud_run_secret_ref(entry: dict[str, Any]) -> dict[str, str] | None:
    value_from = entry.get('valueFrom')
    if not isinstance(value_from, dict):
        return None
    secret_key_ref = value_from.get('secretKeyRef')
    if isinstance(secret_key_ref, dict):
        name = secret_key_ref.get('name')
        version = secret_key_ref.get('key', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    secret_ref = value_from.get('secretRef')
    if isinstance(secret_ref, dict):
        name = secret_ref.get('name')
        version = secret_ref.get('version', 'latest')
        if isinstance(name, str):
            return {'secret': name, 'version': str(version)}
    return None


def _fetch_live_cloud_run_state(env_config: dict[str, Any]) -> dict[str, Any]:
    services: dict[str, Any] = {}
    project = env_config['gcp_project']
    region = env_config['region']
    for service in env_config['cloud_run']['services']:
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
        service_state = json.loads(result.stdout)
        template = service_state.get('spec', {}).get('template', {})
        annotations = template.get('metadata', {}).get('annotations', {})
        services[service] = {
            'env': template.get('spec', {}).get('containers', [{}])[0].get('env', []),
            'flags': _cloud_run_network_flags_from_annotations(annotations),
        }
    return {'services': services}


def _cloud_run_network_flags_from_annotations(annotations: Any) -> dict[str, str]:
    if not isinstance(annotations, dict):
        return {}
    flags: dict[str, str] = {}
    network_interfaces = annotations.get('run.googleapis.com/network-interfaces')
    if isinstance(network_interfaces, str) and network_interfaces:
        try:
            parsed_interfaces = json.loads(network_interfaces)
        except json.JSONDecodeError:
            parsed_interfaces = []
        if isinstance(parsed_interfaces, list) and parsed_interfaces:
            first_interface = parsed_interfaces[0]
            if isinstance(first_interface, dict):
                network = first_interface.get('network')
                subnet = first_interface.get('subnetwork')
                if isinstance(network, str):
                    flags['--network'] = network
                if isinstance(subnet, str):
                    flags['--subnet'] = subnet
    egress = annotations.get('run.googleapis.com/vpc-access-egress')
    if isinstance(egress, str):
        flags['--vpc-egress'] = egress
    return flags


if __name__ == '__main__':
    raise SystemExit(main())
