from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.firestore_workflow_policy import (
    has_direct_firestore_mutation,
    reconciliation_invocations,
)
from scripts.runtime_env_durable_dispatch_contracts import ValidationError
from scripts.runtime_env_validation.common import (
    DEFAULT_MANIFEST,
    ROOT,
    ConfigDict,
    EnvEntry,
    EnvEntryMap,
    StringMap,
    _as_config_dict,
    _as_config_list,
    _expected_flag_value,
    _get_env_config,
    _is_provisional,
    _load_yaml,
    _literal_env_entries_by_name,
    _manifest_env_value,
    _network_flags,
    _substitute_values,
    _validate_cloud_run_secret_entries,
    _validate_env_entries,
    _validate_forbidden_env_entries,
    compute_project,
    data_plane_project,
)


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


def _expand_cloud_run_deploy_steps(step: object, *, workflow_root: Path) -> list[ConfigDict]:
    step_dict = _as_config_dict(step)
    if step_dict is None:
        return []
    if _is_cloud_run_deploy_step(step_dict):
        return [step_dict]
    uses = step_dict.get('uses')
    if not isinstance(uses, str) or not uses.startswith('./'):
        return []
    action = _load_local_composite_action(uses, workflow_root=workflow_root)
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
        if nested_dict is None:
            continue
        if not _composite_step_active_for_caller(nested_dict, caller_with):
            continue
        if _is_cloud_run_deploy_step(nested_dict):
            nested_with = _as_config_dict(nested_dict.get('with')) or {}
            expanded.append(
                {
                    **nested_dict,
                    'with': {
                        key: _resolve_composite_input_reference(value, caller_with)
                        for key, value in nested_with.items()
                    },
                }
            )
            continue
        nested_with = _as_config_dict(nested_dict.get('with')) or {}
        resolved_nested = {
            **nested_dict,
            'with': {key: _resolve_composite_input_reference(value, caller_with) for key, value in nested_with.items()},
        }
        expanded.extend(_expand_cloud_run_deploy_steps(resolved_nested, workflow_root=workflow_root))
    return expanded


def _extract_renderer_env(run: str, *, env: str) -> str | None:
    if '--env dev' in run:
        return 'dev'
    if '--env prod' in run:
        return 'prod'
    if '--env ${{ vars.ENV }}' in run:
        return env
    if '--env ${{ inputs.runtime_env }}' in run:
        return env
    return None


def _extract_workflow_cloud_run_targets(
    workflow: ConfigDict,
    *,
    env: str,
    manifest: ConfigDict,
    workflow_root: Path,
) -> dict[str, dict[str, ConfigDict]]:
    workflow_env = _as_config_dict(workflow.get('env')) or {}
    rendered_runtime_env = _rendered_runtime_env_outputs(
        workflow,
        env=env,
        manifest=manifest,
        workflow_root=workflow_root,
    )
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
            for deploy_step in _expand_cloud_run_deploy_steps(step, workflow_root=workflow_root):
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


def _is_cloud_run_deploy_step(step: object) -> bool:
    step_dict = _as_config_dict(step)
    if step_dict is None:
        return False
    uses = step_dict.get('uses')
    return isinstance(uses, str) and uses.startswith('google-github-actions/deploy-cloudrun@')


def _load_local_composite_action(uses: str, *, workflow_root: Path) -> ConfigDict | None:
    relative_uses = uses[2:]
    # deploy-backend-stack executes nested privileged composites from its
    # immutable staged workflow source. Static validation receives the
    # checked-in workflow root, where the same trusted actions live at their
    # canonical `.github/actions` paths.
    staged_prefix = '.deploy-workflow-source/.github/'
    if relative_uses.startswith(staged_prefix):
        relative_uses = '.github/' + relative_uses[len(staged_prefix) :]
    action_dir = workflow_root / relative_uses
    for name in ('action.yml', 'action.yaml'):
        path = action_dir / name
        if path.is_file():
            action = _load_yaml(path)
            runs = _as_config_dict(action.get('runs')) or {}
            if runs.get('using') == 'composite':
                return action
            return None
    return None


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


def _render_manifest_value(name: str, entry: ConfigDict) -> str:
    if 'value' in entry:
        return str(entry['value'])
    env_var = entry.get('env_var')
    if isinstance(env_var, str) and env_var:
        return f'__{name.strip("-").replace("-", "_")}__'
    return ''


def _backend_deploy_stack_composite_steps(workflow: ConfigDict, *, workflow_root: Path) -> list[ConfigDict]:
    steps: list[ConfigDict] = []
    for raw_step in _workflow_steps(workflow):
        step = _as_config_dict(raw_step)
        if step is None:
            continue
        uses = step.get('uses')
        if not isinstance(uses, str) or 'deploy-backend-stack' not in uses:
            continue
        action = _load_local_composite_action(uses, workflow_root=workflow_root)
        if action is None:
            continue
        nested_steps = _as_config_list((_as_config_dict(action.get('runs')) or {}).get('steps'))
        if nested_steps is None:
            continue
        caller_with = _as_config_dict(step.get('with')) or {}
        for nested in nested_steps:
            nested_dict = _as_config_dict(nested)
            if nested_dict is None or not _composite_step_active_for_caller(nested_dict, caller_with):
                continue
            steps.append(nested_dict)
    return steps


def _rendered_runtime_env_outputs(
    workflow: ConfigDict,
    *,
    env: str,
    manifest: ConfigDict,
    workflow_root: Path | None = None,
) -> StringMap:
    outputs: StringMap = {}
    workflow_root = workflow_root or ROOT
    validation_steps = [
        *_workflow_steps(workflow),
        *_backend_deploy_stack_composite_steps(workflow, workflow_root=workflow_root),
    ]
    for step in validation_steps:
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


def _resolve_composite_input_reference(value: object, caller_with: ConfigDict) -> object:
    if not isinstance(value, str):
        return value
    resolved = value
    for name, raw in caller_with.items():
        resolved = resolved.replace('${{ inputs.' + str(name) + ' }}', str(raw))
    return resolved


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


def _resolve_workflow_string(value: object, workflow_env: ConfigDict) -> str | None:
    if not isinstance(value, str):
        return None
    resolved = value
    for env_name, env_value in workflow_env.items():
        resolved = resolved.replace('${{ env.' + str(env_name) + ' }}', str(env_value))
    return resolved


def _validate_cloud_run_workflows(
    env: str,
    env_config: ConfigDict,
    *,
    strict_provisional: bool,
    manifest_path: Path,
    manifest: ConfigDict | None = None,
    workflow_root: Path | None = None,
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
    workflow_root = workflow_root or ROOT
    for workflow_file in workflow_files:
        if not isinstance(workflow_file, str):
            errors.append(ValidationError('cloud_run/workflows', 'workflow file paths must be strings'))
            continue
        workflow_path = workflow_root / workflow_file
        workflow = _load_yaml(workflow_path)
        errors.extend(
            _validate_firestore_index_reconciliation_boundary(
                workflow_file,
                workflow,
                workflow_root=workflow_root,
            )
        )
        extracted = _extract_workflow_cloud_run_targets(
            workflow,
            env=env,
            manifest=manifest,
            workflow_root=workflow_root,
        )
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


def _validate_firestore_index_reconciliation_boundary(
    workflow_file: str,
    workflow: ConfigDict,
    *,
    workflow_root: Path | None = None,
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
    errors.extend(
        _validate_firestore_readiness_workflow_contract(
            workflow_file,
            workflow,
            workflow_root=workflow_root,
        )
    )
    return errors


def _validate_firestore_readiness_workflow_contract(
    workflow_file: str,
    workflow: ConfigDict,
    *,
    workflow_root: Path | None = None,
) -> list[ValidationError]:
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
    deploy_stack_step = next(
        (step for step in deploy_steps if isinstance(step.get('uses'), str) and 'deploy-backend-stack' in step['uses']),
        None,
    )
    deploy_with = _as_config_dict((deploy_stack_step or {}).get('with')) or {}
    admitted_output_ref = '${{ needs.firestore_readiness.outputs.admitted_sha }}'
    resolved_workflow_root = workflow_root or ROOT
    deploy_backend_stack = _load_local_composite_action(
        './.github/actions/deploy-backend-stack',
        workflow_root=resolved_workflow_root,
    )
    composite_steps = [
        _as_config_dict(step) or {}
        for step in (
            _as_config_list((_as_config_dict((deploy_backend_stack or {}).get('runs')) or {}).get('steps')) or []
        )
    ]
    runtime_checkout = next(
        (step for step in composite_steps if step.get('name') == 'Checkout admitted runtime source'),
        None,
    )
    workflow_control_checkout = next(
        (step for step in composite_steps if step.get('name') == 'Checkout workflow-owned deploy-control source'),
        None,
    )
    runtime_with = _as_config_dict((runtime_checkout or {}).get('with')) or {}
    workflow_control_with = _as_config_dict((workflow_control_checkout or {}).get('with')) or {}
    if (
        deploy_stack_step is None
        or deploy_with.get('admitted_sha') != admitted_output_ref
        or runtime_with.get('ref') != '${{ inputs.admitted_sha }}'
        or workflow_control_with.get('ref') != '${{ github.sha }}'
        or workflow_control_with.get('path') != '.workflow-source'
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


def _workflow_variable_map(env_config: ConfigDict, expected_services: ConfigDict) -> StringMap:
    runtime_project = data_plane_project(env_config)
    deployment_project = compute_project(env_config)
    return {
        '${{ vars.GCP_PROJECT_ID }}': deployment_project,
        '${{vars.GCP_PROJECT_ID}}': deployment_project,
        '${{ vars.RUNTIME_GCP_PROJECT_ID }}': runtime_project,
        '${{vars.RUNTIME_GCP_PROJECT_ID}}': runtime_project,
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
        '${{ vars.MEMORY_CANONICAL_MAINTENANCE_ENABLED }}': _manifest_env_value(
            expected_services, 'MEMORY_CANONICAL_MAINTENANCE_ENABLED'
        ),
        '${{vars.MEMORY_CANONICAL_MAINTENANCE_ENABLED}}': _manifest_env_value(
            expected_services, 'MEMORY_CANONICAL_MAINTENANCE_ENABLED'
        ),
    }
