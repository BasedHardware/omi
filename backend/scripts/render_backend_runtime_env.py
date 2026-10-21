#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

from scripts.runtime_env_compat import normalize_runtime_manifest  # noqa: E402

DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
ConfigDict = dict[str, Any]
_DEPLOY_CLOUD_RUN_ENV_SEPARATORS = frozenset({',', '\n', '\r', '\u2028', '\u2029'})
# Env names that once carried an exportable service-account key (or the path to one). A service
# pinned to an attached runtime identity drops them in the same deploy: its runtime SA deliberately
# cannot read the key secret, so a lingering ref would fail revision creation.
KEY_CREDENTIAL_ENV_NAMES = ('SERVICE_ACCOUNT_JSON', 'GOOGLE_APPLICATION_CREDENTIALS')

# The literal --remove-env-vars list every Cloud Run service deploy action already carries. The
# manifest's forbidden_env may only append keys missing from it: gcloud rejects a key named twice.
RETIRED_ENV_NAMES = (
    'MEMORY_ENABLED_USERS',
    'MEMORY_CANONICAL_PROMOTION_CRON_ENABLED',
    'MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS',
    'MEMORY_CANONICAL_PROMOTION_FAST_TRACK_ENABLED',
    'BASIC_TIER_MINUTES_LIMIT_PER_MONTH',
    'BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH',
    'BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH',
    'BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH',
    'DEEPGRAM_SELF_HOSTED_ENABLED',
    'DEEPGRAM_SELF_HOSTED_URL',
    'CONVERSATION_RELEVANCE_JEV_ENABLED',
    'CONVERSATION_RELEVANCE_JEV_SHADOW_PERCENT',
    'CONVERSATION_RELEVANCE_JEV_SHADOW_DAILY_CAP',
    'CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST',
    'CONVERSATION_RELEVANCE_KEEP_ALL_PERCENT',
    'CONVERSATION_RELEVANCE_JEV_RESCUE',
    'MEMORY_OWNER_JEV_FLIP_ENABLED',
    'MEMORY_OWNER_JEV_FLIP_PERCENT',
    'MEMORY_OWNER_JEV_SHADOW_PERCENT',
    'MEMORY_OWNER_JEV_SHADOW_DAILY_CAP',
    'CONVERSATION_SMART_MERGE_UID_ALLOWLIST',
    'CONVERSATION_SMART_MERGE_WALLCLOCK_GAP_MODE',
    'DESKTOP_PENDANT_CALL_LINK_MODE',
    'DESKTOP_PENDANT_CALL_LINK_PERCENT',
    'MEETING_NOTES_EPISODE_SELECTION',
    'MEETING_NOTES_EPISODE_JEV_THRESHOLD',
    'MEETING_NOTES_EPISODE_SELECTION_EFFORT',
    'MEETING_NOTES_EPISODE_SELECTION_TIMEOUT_SECONDS',
    'CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED',
    'CONVERSATION_OCR_CONTEXT_ENABLED',
    'MEETING_NOTES_SCREEN_FRAMES_CONTEXT_ENABLED',
    'SCREEN_FRAME_EGRESS_ENABLED',
    'MEMORY_BELIEF_MODEL_ENABLED',
    'FREE_TIER_MEMORY_SUPPRESSION',
    'FREE_TIER_MEMORY_SUPPRESSION_COHORT',
    'KNOWLEDGE_LEDGER_DRAIN_ENABLED',
    'KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST',
    'MEMORY_DAILY_MEMORY_SWEEP_ENABLED',
    'MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH',
    'MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED',
    'MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME',
    'MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES',
    'MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD',
    'MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED',
    'MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG',
    'MEMORY_DAILY_MEMORY_SWEEP_COHORT_NAME',
    'MEMORY_DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_SECONDS',
    'MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED',
    'MEMORY_DAILY_MEMORY_SWEEP_STAGGER_SECONDS',
)
# Only the API service talks to the pusher; every other service drops its URL.
PUSHER_CLIENT_SERVICES = frozenset({'backend'})
FIRESTORE_READ_RUNTIME_ENV_NAMES = (
    'FIRESTORE_READ_LEVERS',
    'FSR_QUEUE_AGE_PUBLISHER',
    'FSR_QUEUE_AGE_LEASE_SECONDS',
    'FSR_LEADER_LEASE_TTL_SECONDS',
    'DELETION_WIPE_RECONCILE_INTERVAL_SECONDS',
    'FSR_DELETION_NEGATIVE_TTL_SECONDS',
    'FSR_USAGE_MONTH_TTL_SECONDS',
    'FSR_SUBSCRIPTION_TTL_SECONDS',
    'FSR_SERVING_CONFIG_TTL_SECONDS',
    'ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS',
    'CANDIDATES_COMPATIBILITY_CACHE_TTL_SECONDS',
)


def _action_removed_env_names(service: str) -> set[str]:
    """The literal --remove-env-vars names the deploy action passes for this service."""
    listed: set[str] = set(RETIRED_ENV_NAMES)
    if service not in PUSHER_CLIENT_SERVICES:
        listed.add('HOSTED_PUSHER_API_URL')
    return listed


def _remove_env_extra(service: str, service_config: ConfigDict) -> str:
    """Manifest forbidden keys the action's literal list lacks, each with a leading comma."""
    listed = _action_removed_env_names(service)
    return ''.join(f',{name}' for name in sorted(set(service_config.get('forbidden_env', [])) - listed))


def _job_removed_env_names(job_config: ConfigDict) -> set[str]:
    """Names a job deploy removes: its forbidden_env plus its own rendered --remove-env-vars flag."""
    flags = _render_flag_values(_as_config_dict(job_config.get('flags')) or {})
    listed = {name for name in flags.get('--remove-env-vars', '').split(',') if name}
    return listed | set(job_config.get('forbidden_env', []))


def _parse_deploy_cloud_run_env_vars(rendered: str) -> list[tuple[str, str]]:
    """Invert _render_env_vars: split deploy-cloudrun's escaped grammar back into pairs."""
    entries: list[str] = []
    current: list[str] = []
    characters = iter(rendered)
    for character in characters:
        if character == '\\':
            current.append(next(characters, ''))
        elif character == '\n':
            entries.append(''.join(current))
            current = []
        else:
            current.append(character)
    entries.append(''.join(current))
    pairs: list[tuple[str, str]] = []
    for entry in entries:
        if entry:
            name, _, value = entry.partition('=')
            pairs.append((name, value))
    return pairs


def assert_manifest_env_renders(workload: str, config: ConfigDict, rendered: str, removed: set[str]) -> None:
    """Fail the deploy before it mutates anything if a manifest env key would not land.

    Ops keys silently reverting after every train is what this guards: each manifest
    key must come back out of the exact text handed to deploy-cloudrun, once, with its
    manifest value, and must not also be named for removal in the same deploy. A
    provisional key with no supplied value is the documented preserve-live omission.
    """
    expected = {
        entry['name']: entry['value'] for entry in _render_env_entries(_as_config_dict(config.get('env')) or {})
    }
    pairs = _parse_deploy_cloud_run_env_vars(rendered)
    names = [name for name, _ in pairs]
    errors: list[str] = []
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        errors.append(f'rendered more than once: {", ".join(duplicated)}')
    missing = sorted(set(expected) - set(names))
    if missing:
        errors.append(f'manifest keys missing from the rendered env: {", ".join(missing)}')
    unexpected = sorted(set(names) - set(expected))
    if unexpected:
        errors.append(f'rendered keys not in the manifest: {", ".join(unexpected)}')
    changed = sorted(name for name, value in pairs if name in expected and expected[name] != value)
    if changed:
        errors.append(f'rendered value differs from the manifest: {", ".join(changed)}')
    removed_too = sorted(set(expected) & removed)
    if removed_too:
        errors.append(f'manifest keys also removed by the deploy: {", ".join(removed_too)}')
    if errors:
        raise ValueError(f'Cloud Run {workload} env does not render every manifest key; ' + '; '.join(errors))


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


_SYNC_LINEAGE_ALLOWLIST_KEY = 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'
_SYNC_LINEAGE_CLOUD_RUN_HOSTS = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


def validate_sync_lineage_rollout(env: str, env_config: dict[str, Any], *, check_chart: bool = False) -> list[str]:
    # Cloud Run merges omitted env keys; Helm keeps its legacy values until a later cutover.
    services = env_config.get('cloud_run', {}).get('services', {})
    hosts = [(f'cloud_run/{name}', services.get(name, {})) for name in _SYNC_LINEAGE_CLOUD_RUN_HOSTS]
    errors = []
    for scope, host in hosts:
        if _SYNC_LINEAGE_ALLOWLIST_KEY in host.get('env', {}) or _SYNC_LINEAGE_ALLOWLIST_KEY in host.get('secrets', {}):
            errors.append(f'{scope}: {_SYNC_LINEAGE_ALLOWLIST_KEY} must be absent; membership lives in Firestore')
    return errors


def require_sync_lineage_rollout(env: str, env_config: dict[str, Any]) -> None:
    errors = validate_sync_lineage_rollout(env, env_config, check_chart=True)
    if errors:
        raise ValueError('; '.join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description='Render backend Cloud Run runtime env from the manifest.')
    parser.add_argument('--env', choices=('dev', 'prod'), required=True)
    parser.add_argument(
        '--job',
        help='render only this Cloud Run job and the shared network flags; services remain full-environment only',
    )
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--state-output',
        type=Path,
        help='Write the exact rendered Cloud Run service env, secret refs, and flags as validator state JSON.',
    )
    parser.add_argument(
        '--desktop-state-output',
        type=Path,
        help=(
            'Write the rendered desktop-backend env as expected-env-state JSON for '
            'attach_cloud_run_gmp_sidecar.py --expected-env-state.'
        ),
    )
    args = parser.parse_args()
    if args.job and args.state_output:
        parser.error('--state-output is supported only for the full service render')
    if args.job and args.desktop_state_output:
        parser.error('--desktop-state-output is supported only for the full service render')

    manifest = _load_yaml(args.manifest)
    environments = _as_config_dict(manifest['environments']) or {}
    env_config = _as_config_dict(environments[args.env]) or {}

    if args.desktop_state_output:
        desktop_state = _render_desktop_backend_state(env_config)
        args.desktop_state_output.write_text(
            json.dumps(desktop_state, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        # desktop-backend deploys from its own workflow and does not set the
        # backend service env this script otherwise requires. Rendering the
        # sidecar guard must not force those callers to supply it, so stop here
        # unless a backend render was also asked for.
        if not args.state_output and not args.job:
            desktop_env = {
                entry['name']: entry['value'] for entry in desktop_state['services']['desktop-backend']['env']
            }
            missing_firestore_read_env = sorted(set(FIRESTORE_READ_RUNTIME_ENV_NAMES) - desktop_env.keys())
            if missing_firestore_read_env:
                raise ValueError(
                    'desktop-backend runtime env is missing Firestore read bindings: '
                    + ', '.join(missing_firestore_read_env)
                )
            firestore_read_env_vars = '\n'.join(
                f'{name}={_escape_deploy_cloud_run_env_value(desktop_env[name])}'
                for name in FIRESTORE_READ_RUNTIME_ENV_NAMES
            )
            ladder_price_env_vars = '\n'.join(
                f'{name}={_escape_deploy_cloud_run_env_value(desktop_env[name])}'
                for name in desktop_env
                if name.startswith('LADDER_V1_') and name.endswith('_PRICE_ID')
            )
            _emit_output('ladder_price_env_vars', ladder_price_env_vars)
            # Resource references remain in the validated expected state. The
            # deploy action binds the same selected-environment reference directly,
            # without copying credential-shaped mappings through workflow outputs.
            _emit_output('firestore_read_env_vars', firestore_read_env_vars)
            return 0

    if not args.job:
        require_sync_lineage_rollout(args.env, env_config)

    cloud_run = _as_config_dict(env_config['cloud_run']) or {}

    jobs = _as_config_dict(cloud_run.get('jobs')) or {}
    selected_jobs = jobs
    if args.job:
        raw_job_config = jobs.get(args.job)
        if raw_job_config is None:
            raise ValueError(f'unknown Cloud Run job {args.job!r} for environment {args.env}')
        selected_jobs = {args.job: raw_job_config}

    # Render everything before emitting output. A selected job with an invalid
    # contract must fail without leaving a partial GITHUB_OUTPUT file behind.
    rendered_outputs: list[tuple[str, str]] = []
    network = _as_config_dict(cloud_run.get('network')) or {}
    rendered_outputs.append(('cloud_run_flags', _render_flags(_as_config_dict(network.get('flags')) or {})))
    services = _as_config_dict(cloud_run.get('services')) or {}
    if not args.job:
        desktop_backend = _as_config_dict(env_config.get('desktop_backend')) or {}
        desktop_env = _as_config_dict(desktop_backend.get('env')) or {}
        desktop_secrets = _as_config_dict(desktop_backend.get('secrets')) or {}
        if desktop_env:
            rendered_outputs.append(('desktop_backend_env_vars', _render_env_vars(desktop_env)))
        if desktop_secrets:
            rendered_outputs.extend(
                (
                    ('desktop_backend_secrets', _render_secrets(desktop_secrets)),
                    ('desktop_backend_secret_names', _render_secret_names(desktop_secrets)),
                )
            )
        for service, raw_service_config in services.items():
            service_config = _as_config_dict(raw_service_config)
            if service_config is None:
                raise ValueError(f'Cloud Run service {service} must be a mapping')
            output_prefix = _output_prefix(service)
            service_env_vars = _render_env_vars(service_config.get('env', {}))
            assert_manifest_env_renders(
                f'service {service}',
                service_config,
                service_env_vars,
                _action_removed_env_names(service) | set(service_config.get('forbidden_env', [])),
            )
            rendered_outputs.extend(
                (
                    (f'{output_prefix}_env_vars', service_env_vars),
                    (f'{output_prefix}_secrets', _render_secrets(service_config.get('secrets', {}))),
                    (f'{output_prefix}_secret_names', _render_secret_names(service_config.get('secrets', {}))),
                    (f'{output_prefix}_identity_flags', _render_identity_flags(service, service_config)),
                    (f'{output_prefix}_flags', _render_flags(service_config.get('flags', {}))),
                    (f'{output_prefix}_forbidden_env_names', ','.join(sorted(service_config.get('forbidden_env', [])))),
                    (f'{output_prefix}_remove_env_extra', _remove_env_extra(service, service_config)),
                )
            )
    for job, raw_job_config in selected_jobs.items():
        job_config = _as_config_dict(raw_job_config)
        if job_config is None:
            raise ValueError(f'Cloud Run job {job} must be a mapping')
        output_prefix = _output_prefix(job)
        job_env_vars = _render_env_vars(job_config.get('env', {}))
        assert_manifest_env_renders(f'job {job}', job_config, job_env_vars, _job_removed_env_names(job_config))
        rendered_outputs.extend(
            (
                (f'{output_prefix}_flags', _render_flags(_as_config_dict(job_config.get('flags')) or {})),
                (f'{output_prefix}_env_vars', job_env_vars),
                (f'{output_prefix}_secrets', _render_secrets(job_config.get('secrets', {}))),
                (f'{output_prefix}_secret_names', _render_secret_names(job_config.get('secrets', {}))),
            )
        )
    if args.state_output:
        args.state_output.write_text(
            json.dumps(_render_cloud_run_state(env_config), indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
    for name, value in rendered_outputs:
        _emit_output(name, value)
    return 0


def _load_yaml(path: Path) -> ConfigDict:
    with path.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return normalize_runtime_manifest(cast(ConfigDict, loaded))


def _render_env_entries(env_entries: ConfigDict) -> list[ConfigDict]:
    rendered: list[ConfigDict] = []
    for name, raw_entry in env_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is None:
            raise ValueError(f'Cloud Run env {name} must be a mapping')
        value = _runtime_value(name, entry, allow_missing=bool(entry.get('provisional')))
        if value is None:
            # Provisional values belong to services not yet deployed in every environment.
            continue

        rendered.append({'name': str(name), 'value': value})
    return rendered


def _render_env_vars(env_entries: ConfigDict) -> str:
    return '\n'.join(
        f'{entry["name"]}={_escape_deploy_cloud_run_env_value(entry["value"])}'
        for entry in _render_env_entries(env_entries)
    )


def _escape_deploy_cloud_run_env_value(value: str) -> str:
    """Encode a value for deploy-cloudrun's escaped key/value input grammar."""
    return ''.join(
        f'\\{character}' if character == '\\' or character in _DEPLOY_CLOUD_RUN_ENV_SEPARATORS else character
        for character in value
    )


def _validated_resource_name(binding_name: str, candidate: object) -> str:
    """Accept Secret Manager resource metadata, never a credential payload.

    Both checked-in literal descriptors and operator-provided references cross
    this boundary before state or workflow output is written. No secret version
    is accessed here; the runtime resolves the resulting secretKeyRef itself.
    """
    if (
        not isinstance(candidate, str)
        or candidate.startswith(('sk_', 'rk_'))
        or not re.fullmatch(r'(?:projects/[a-z0-9][a-z0-9-]{0,62}/secrets/)?[A-Za-z0-9_-]{1,255}', candidate)
    ):
        raise ValueError(f'Cloud Run secret binding {binding_name} has an invalid resource reference')
    return candidate


def _render_secret_entries(secret_entries: ConfigDict) -> list[ConfigDict]:
    rendered: list[ConfigDict] = []
    for name, raw_entry in secret_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is None:
            raise ValueError(f'Cloud Run secret binding {name} must be a mapping')
        if 'secret' in entry:
            resource_name = _validated_resource_name(name, entry['secret'])
        elif 'env_var' in entry:
            resource_name = _runtime_value(name, entry)
            if not resource_name:
                continue
            resource_name = _validated_resource_name(name, resource_name)
        else:
            raise ValueError(f'Cloud Run secret binding {name} must define secret or env_var')
        version = entry.get('version', 'latest')
        rendered.append(
            {
                'name': str(name),
                'valueFrom': {
                    'secretKeyRef': {
                        'name': resource_name,
                        'key': str(version),
                    }
                },
            }
        )
    return rendered


def _render_secrets(secret_entries: ConfigDict) -> str:
    return '\n'.join(
        f'{entry["name"]}={entry["valueFrom"]["secretKeyRef"]["name"]}:{entry["valueFrom"]["secretKeyRef"]["key"]}'
        for entry in _render_secret_entries(secret_entries)
    )


def _render_secret_names(secret_entries: ConfigDict) -> str:
    return ','.join(entry['name'] for entry in _render_secret_entries(secret_entries))


def _render_flag_values(flag_entries: ConfigDict) -> dict[str, str]:
    flags: dict[str, str] = {}
    for name, raw_entry in flag_entries.items():
        entry = _as_config_dict(raw_entry)
        if entry is not None:
            value = _runtime_value(name, entry)
        else:
            value = raw_entry
        if value in (None, ''):
            raise ValueError(f'Cloud Run flag {name} must have a value')
        flags[str(name)] = str(value)
    return flags


def _render_flags(flag_entries: ConfigDict) -> str:
    return ' '.join(f'{name}={value}' for name, value in _render_flag_values(flag_entries).items())


def _service_account(service: str, service_config: ConfigDict) -> str:
    """The attached runtime identity a Cloud Run service must run as, or '' when undeclared."""
    raw = service_config.get('service_account')
    if raw in (None, ''):
        return ''
    value = str(raw).strip()
    local, _, domain = value.partition('@')
    if not local or not domain.endswith('.iam.gserviceaccount.com') or any(ch.isspace() for ch in value):
        raise ValueError(f'Cloud Run service {service} service_account must be a service-account email')
    secrets = _as_config_dict(service_config.get('secrets')) or {}
    for name in KEY_CREDENTIAL_ENV_NAMES:
        if name in secrets:
            raise ValueError(
                f'Cloud Run service {service} runs as {value} and must not also mount key credential {name}'
            )
    return value


def _render_identity_flags(service: str, service_config: ConfigDict) -> str:
    """Pin the runtime identity and drop any key-credential ref in the same revision."""
    service_account = _service_account(service, service_config)
    if not service_account:
        return ''
    return f'--service-account={service_account} --remove-secrets={",".join(KEY_CREDENTIAL_ENV_NAMES)}'


def _render_cloud_run_state(env_config: ConfigDict) -> ConfigDict:
    """Build validator state from the same values emitted to deploy-cloudrun."""
    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    network = _as_config_dict(cloud_run.get('network')) or {}
    network_flags = _render_flag_values(_as_config_dict(network.get('flags')) or {})
    services: ConfigDict = {}
    for service_name, raw_service_config in (_as_config_dict(cloud_run.get('services')) or {}).items():
        service_config = _as_config_dict(raw_service_config)
        if service_config is None:
            raise ValueError(f'Cloud Run service {service_name} must be a mapping')
        service_state: ConfigDict = {
            'env': _render_state_env(service_config),
            'flags': {**network_flags, **_render_flag_values(_as_config_dict(service_config.get('flags')) or {})},
        }
        service_account = _service_account(str(service_name), service_config)
        if service_account:
            service_state['service_account'] = service_account
        services[str(service_name)] = service_state
    # Jobs ship from their own workflows, but their env, secret and forbidden_env contract is
    # declared in this manifest and validated against this state; omitting them retires that check.
    jobs: ConfigDict = {}
    for job_name, raw_job_config in (_as_config_dict(cloud_run.get('jobs')) or {}).items():
        job_config = _as_config_dict(raw_job_config)
        if job_config is None:
            raise ValueError(f'Cloud Run job {job_name} must be a mapping')
        jobs[str(job_name)] = {
            'env': _render_state_env(job_config),
            'flags': _render_flag_values(_as_config_dict(job_config.get('flags')) or {}),
        }
    return {'services': services, 'jobs': jobs}


def _render_state_env(config: ConfigDict) -> list[ConfigDict]:
    return [
        *_render_env_entries(_as_config_dict(config.get('env')) or {}),
        *_render_secret_entries(_as_config_dict(config.get('secrets')) or {}),
    ]


def _render_desktop_backend_state(env_config: ConfigDict) -> ConfigDict:
    """Build sidecar-guard state for desktop-backend from the same manifest values.

    Deliberately separate from _render_cloud_run_state: that file is also read by
    validate-backend-runtime-env.py, which walks cloud_run.services, and
    desktop-backend is not one of those. Keeping them apart means adding this
    guard cannot perturb the backend deploy path.

    The manifest owns only part of desktop-backend's env today, and that is fine:
    attach_cloud_run_gmp_sidecar.py checks the names it is given and ignores the
    rest, so this asserts a real subset rather than nothing.
    """
    desktop_backend = _as_config_dict(env_config.get('desktop_backend')) or {}
    env_entries = _render_env_entries(_as_config_dict(desktop_backend.get('env')) or {})
    mixed = any(
        entry['name'].startswith('LADDER_V1_') and entry['name'].endswith('_PRICE_ID') and entry['value'].strip()
        for entry in env_entries
    )
    entries = _as_config_dict(desktop_backend.get('secrets')) or {}
    secrets = _render_secret_entries({'SCREEN_VECTOR_STRIPE_API_KEY': entries.get('SCREEN_VECTOR_STRIPE_API_KEY')})
    if mixed and not secrets:
        raise ValueError('Desktop ladder price bindings require SCREEN_VECTOR_STRIPE_READ_SECRET')
    return {'services': {'desktop-backend': {'env': env_entries, 'secrets': secrets}}}


def _runtime_value(name: str, entry: ConfigDict, *, allow_missing: bool = False) -> str | None:
    if 'value' in entry:
        return str(entry['value'])
    env_var = entry.get('env_var')
    if isinstance(env_var, str) and env_var:
        value = os.environ.get(env_var, '')
        if value:
            return value
        default = entry.get('default')
        if default is not None:
            return str(default)
        if allow_missing:
            return None
        raise ValueError(f'{name} requires ${env_var} to be set')
    raise ValueError(f'{name} must define value or env_var')


def _emit_output(name: str, value: str) -> None:
    delimiter = f'__BACKEND_RUNTIME_ENV_{name}__'
    _append_github_output(f'{name}<<{delimiter}\n{value}\n{delimiter}\n')


def _append_github_output(value: str) -> None:
    output_path = os.environ.get('GITHUB_OUTPUT')
    if not output_path:
        raise RuntimeError('GITHUB_OUTPUT must be set to render workflow outputs')
    with Path(output_path).open('a', encoding='utf-8') as output_file:
        output_file.write(value)


def _output_prefix(service: str) -> str:
    return service.replace('-', '_')


if __name__ == '__main__':
    raise SystemExit(main())
