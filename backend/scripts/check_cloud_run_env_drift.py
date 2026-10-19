#!/usr/bin/env python3
"""Read-only runtime-config drift check: serving workloads versus the repository.

What is compared
  * Cloud Run: the revisions that actually serve traffic (``status.traffic``),
    never ``spec.template``. A ``services update`` against a traffic-pinned
    service creates a 0%-traffic revision whose template looks "fixed" while
    nothing serves it (the 2026-10-18 23:50Z misread).
  * GKE (``--gke``): the ReplicaSets of each Deployment that currently hold
    ready pods (listen, pusher, batch-pipeline-worker), never only the
    Deployment template.
  * ``envFrom``: the ConfigMaps a GKE container bulk-loads through ``envFrom``
    are resolved (live read or offline fixture) and their keys join the same
    name/hash comparison, so a missing or out-of-date ConfigMap key is visible
    instead of a silent ``OK``. Unresolvable references report ``INVENTORY``.
    Live reads cannot prove the current ConfigMap data matches what already
    running pods resolved at container start, so live envFrom keys compare as
    ``INVENTORY`` (offline fixtures are snapshots and compare exactly).

Each serving target's application-container env is compared with the
expected env (``runtime_env.yaml`` / rendered deploy state for Cloud Run,
the chart's Helm values for GKE) by key name *and* by a truncated SHA-256 of
the value or secret reference. Values are never printed; hashes of keys whose
names look sensitive (UIDs, allowlists, secrets, tokens) are redacted too.

By default this is a non-blocking visibility report (exit 0). ``--strict``
exits 1 on drift and 2 on fetch/render errors, for use as a train post-gate;
when drift and fetch errors coexist, ``2`` wins (the comparison did not
complete).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence, cast

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_backend_runtime_env  # noqa: E402
from attach_cloud_run_gmp_sidecar import SIDECAR_NAME  # noqa: E402
from runtime_env_validation.common import compute_project  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'backend/deploy/runtime_env.yaml'
DEFAULT_REGION = 'us-central1'
DEFAULT_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
HASH_LENGTH = 12
REDACTED_HASH = 'redacted'
_SENSITIVE_KEY_RE = re.compile(r'(UID|ALLOWLIST|SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|PRIVATE)')

# Keys intentionally set outside backend/deploy/runtime_env.yaml (for example,
# per-revision provenance markers, sidecar ports attached post-deploy, or
# live-managed canary UID allowlists that must not live in the public repo).
LIVE_MANAGED_ENV_ALLOWLIST: dict[str, frozenset[str]] = {
    '*': frozenset(
        {
            'BATCH_PIPELINE_UID_ALLOWLIST',
        }
    ),
    'backend': frozenset(
        {
            'OMI_BACKEND_RELEASE_SHA',
        }
    ),
    'backend-sync': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
            'SYNC_BACKFILL_ORDER_UID_ALLOWLIST',
            'FAIR_USE_EXEMPT_UIDS',
            'DREAM_AGENT_FULL_CONTEXT_UIDS',
        }
    ),
    'backend-sync-backfill': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
            'SYNC_BACKFILL_ORDER_UID_ALLOWLIST',
            'FAIR_USE_EXEMPT_UIDS',
            'DREAM_AGENT_FULL_CONTEXT_UIDS',
        }
    ),
    'backend-integration': frozenset(
        {
            'FIRST_SUMMARY_UID_ALLOWLIST',
        }
    ),
}


@dataclass(frozen=True)
class GkeWorkload:
    chart: str
    values_file: str  # formatted with env=
    deployment: str  # formatted with env=
    container: str
    # Image pins only satisfy the chart's render-time guards; they never reach the env.
    helm_image_args: tuple[str, ...] = ('image.tag=drift-check', 'image.digest=')


GKE_WORKLOADS: dict[str, GkeWorkload] = {
    'backend-listen': GkeWorkload(
        chart='backend/charts/backend-listen',
        values_file='backend/charts/backend-listen/{env}_omi_backend_listen_values.yaml',
        deployment='{env}-omi-backend-listen',
        container='backend-listen',
    ),
    'pusher': GkeWorkload(
        chart='backend/charts/pusher',
        values_file='backend/charts/pusher/{env}_omi_pusher_values.yaml',
        deployment='{env}-omi-pusher',
        container='pusher',
    ),
    'batch-pipeline-worker': GkeWorkload(
        chart='backend/charts/batch-pipeline-worker',
        values_file='backend/charts/batch-pipeline-worker/{env}_omi_batch-pipeline-worker_values.yaml',
        deployment='{env}-omi-batch-pipeline-worker',
        container='worker',
        helm_image_args=('image.digest=sha256:' + '0' * 64,),
    ),
}
DEFAULT_GKE_WORKLOADS = tuple(GKE_WORKLOADS)

# name -> value hash, or None when the expected value is not knowable offline
# (for example a deploy-time ``env_var`` binding with no rendered state).
ExpectedEnv = dict[str, str | None]
LiveEnv = dict[str, str]


@dataclass(frozen=True)
class ValueMismatch:
    key: str
    expected_hash: str
    live_hash: str
    target: str


@dataclass(frozen=True)
class ServingTarget:
    """One serving revision (Cloud Run) or ready ReplicaSet (GKE)."""

    name: str
    weight: int  # traffic percent (Cloud Run) or ready replicas (GKE)
    key_count: int
    fingerprint: str
    display_fingerprint: str = ''  # redacted form; the only one safe to publish


@dataclass(frozen=True)
class ServiceEnvDrift:
    service: str
    manifest_key_count: int
    live_key_count: int
    allowlisted_live_only: tuple[str, ...]
    unallowlisted_live_only: tuple[str, ...]
    error: str | None = None
    platform: str = 'cloud_run'
    source: str = 'serving'  # serving | snapshot (offline env-only fixture)
    serving: tuple[ServingTarget, ...] = ()
    value_mismatches: tuple[ValueMismatch, ...] = ()
    missing_from_live: tuple[str, ...] = ()
    value_unchecked_keys: int = 0
    template_name: str | None = None
    template_matches_serving: bool | None = None
    expected_available: bool = True
    envfrom_refs: tuple[str, ...] = ()  # expected envFrom ConfigMap references
    envfrom_mismatched_refs: tuple[str, ...] = ()  # live vs expected reference drift
    envfrom_unresolved: tuple[str, ...] = ()  # references whose keys could not be compared
    envfrom_unproven: tuple[str, ...] = ()  # live refs whose data may differ from running pods' env

    @property
    def has_drift(self) -> bool:
        return bool(
            self.unallowlisted_live_only
            or self.value_mismatches
            or self.missing_from_live
            or self.envfrom_mismatched_refs
        )

    @property
    def status(self) -> str:
        if self.error:
            return 'ERROR'
        if self.has_drift:
            return 'DRIFT'
        if not self.expected_available or self.envfrom_unresolved or self.envfrom_unproven:
            return 'INVENTORY'
        return 'OK'


# ── hashing ─────────────────────────────────────────────────────────────────


def value_hash(kind: str, payload: str) -> str:
    """Truncated SHA-256 of a typed value; the raw value never leaves this function."""
    return hashlib.sha256(f'omi-env-v1\0{kind}\0{payload}'.encode('utf-8')).hexdigest()[:HASH_LENGTH]


def _secret_ref_hash(resource: str, version: str, *, optional: bool = False) -> str:
    # A project-qualified Secret Manager reference keeps its project so rebinding
    # projects/a/secrets/x to projects/b/secrets/x is a visible hash change; a bare
    # native-secret name hashes by name only, as before. ``optional`` joins the
    # digest (normalized) so a chart/serving difference in optionality is drift.
    ref = resource if '/' in resource else resource.rsplit('/', 1)[-1]
    suffix = ':optional' if optional else ''
    return value_hash('secret', f'{ref}:{version or "latest"}{suffix}')


def env_entry_hash(entry: Mapping[str, Any]) -> str:
    """Hash one Kubernetes-shaped env entry ({name, value} or {name, valueFrom})."""
    value_from = entry.get('valueFrom')
    if isinstance(value_from, Mapping):
        secret = value_from.get('secretKeyRef')
        if isinstance(secret, Mapping):
            return _secret_ref_hash(
                str(secret.get('name', '')), str(secret.get('key', '')), optional=bool(secret.get('optional'))
            )
        config_map = value_from.get('configMapKeyRef')
        if isinstance(config_map, Mapping):
            optional = ':optional' if config_map.get('optional') else ''
            return value_hash('configmap', f'{config_map.get("name", "")}:{config_map.get("key", "")}{optional}')
        field_ref = value_from.get('fieldRef')
        if isinstance(field_ref, Mapping):
            # The API server adds apiVersion: v1 to fieldRef; Helm output omits it.
            return value_hash('field', str(field_ref.get('fieldPath', '')))
        return value_hash('valueFrom', json.dumps(value_from, sort_keys=True, separators=(',', ':')))
    raw = entry.get('value')
    return value_hash('value', '' if raw is None else str(raw))


def env_fingerprint(env: Mapping[str, str], *, redacted: bool = False) -> str:
    # `redacted` swaps sensitive-key hashes for a placeholder before hashing, so a
    # published fingerprint cannot be brute-forced against candidate sensitive
    # values; the full fingerprint stays internal for equality checks only.
    parts = [
        f'{name}={REDACTED_HASH if redacted and _SENSITIVE_KEY_RE.search(name) else env[name]}' for name in sorted(env)
    ]
    return value_hash('env-set', '\n'.join(parts))


def display_hash(key: str, digest: str) -> str:
    return REDACTED_HASH if _SENSITIVE_KEY_RE.search(key) else digest


def _envfrom_sources(container: Mapping[str, Any] | None) -> tuple[tuple[str, str], ...]:
    """(name, prefix) for each envFrom ConfigMap source on one container."""
    if not isinstance(container, Mapping):
        return ()
    sources: list[tuple[str, str]] = []
    for source in container.get('envFrom') or []:
        if not isinstance(source, Mapping):
            continue
        ref = source.get('configMapRef')
        name = ref.get('name') if isinstance(ref, Mapping) else None
        if isinstance(name, str) and name:
            prefix = source.get('prefix')
            sources.append((name, prefix if isinstance(prefix, str) else ''))
    return tuple(dict.fromkeys(sources))


def _envfrom_ref_identities(sources: Iterable[tuple[str, str]]) -> tuple[str, ...]:
    """Comparable reference identities; a prefix is part of the reference because
    it changes the env names a pod receives (``X_KEY`` is not ``KEY``)."""
    return tuple(f'{name}#{prefix}' if prefix else name for name, prefix in sources)


def _config_map_data_keys(data: Mapping[str, Any]) -> LiveEnv:
    """Hashes of the env keys a ConfigMap contributes through ``envFrom``."""
    return {str(key): value_hash('value', str(value)) for key, value in sorted(data.items())}


def _env_list_to_live(entries: object, *, scope: str) -> LiveEnv:
    if not isinstance(entries, list):
        raise ValueError(f'{scope} env must be a list')
    return {
        entry['name']: env_entry_hash(entry)
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']
    }


def _application_container(containers: object, *, scope: str, name: str | None = None) -> Mapping[str, Any]:
    if not isinstance(containers, list):
        raise ValueError(f'{scope} has no containers list')
    candidates = [c for c in containers if isinstance(c, dict) and c.get('name') != SIDECAR_NAME]
    if name is not None:
        named = [c for c in candidates if c.get('name') == name]
        if len(named) == 1:
            return named[0]
    if len(candidates) != 1:
        raise ValueError(f'{scope} expected 1 application container, found {len(candidates)}')
    return candidates[0]


# ── expected env (repository side) ──────────────────────────────────────────


def _manifest_env_config(env: str, manifest_path: Path) -> dict[str, Any]:
    manifest = render_backend_runtime_env._load_yaml(manifest_path)
    environments = render_backend_runtime_env._as_config_dict(manifest.get('environments')) or {}
    env_config = render_backend_runtime_env._as_config_dict(environments.get(env))
    if env_config is None:
        raise ValueError(f'Missing {env!r} environment in {manifest_path}')
    return env_config


def _manifest_entry_hash(name: str, entry: object, *, secret: bool, environ: Mapping[str, str]) -> str | None:
    """Expected hash for one manifest binding; None when only the deploy can resolve it."""
    config = render_backend_runtime_env._as_config_dict(entry) or {}
    if secret:
        if 'secret' in config:
            return _secret_ref_hash(str(config['secret']), str(config.get('version', 'latest')))
        env_var = config.get('env_var')
        resolved = environ.get(env_var, '') if isinstance(env_var, str) else ''
        return _secret_ref_hash(resolved, str(config.get('version', 'latest'))) if resolved else None
    if 'value' in config:
        return value_hash('value', str(config['value']))
    env_var = config.get('env_var')
    if isinstance(env_var, str) and environ.get(env_var):
        return value_hash('value', environ[env_var])
    # A manifest `default` is only the fallback; the deploy usually supplies the value, so
    # without rendered state this key is compared by name only (no false value drift).
    return None


def expected_cloud_run_env(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str, dict[str, ExpectedEnv]]:
    """Expected Cloud Run env per service: rendered deploy state wins over the raw manifest."""
    env_config = _manifest_env_config(env, manifest_path)
    project = compute_project(env_config)
    region = str(env_config.get('region') or DEFAULT_REGION)
    cloud_run = render_backend_runtime_env._as_config_dict(env_config.get('cloud_run')) or {}
    services = render_backend_runtime_env._as_config_dict(cloud_run.get('services')) or {}
    environ = {} if environ is None else environ

    rendered_services: dict[str, Any] = {}
    if rendered_state_path is not None:
        # A supplied path must exist and be the renderer's state: silently falling
        # back to the raw manifest would drop exact-value coverage for deploy-time
        # bindings while appearing to have consumed the requested file.
        if not rendered_state_path.is_file():
            raise ValueError(f'Rendered state file not found: {rendered_state_path}')
        loaded_state = json.loads(rendered_state_path.read_text(encoding='utf-8'))
        if not (isinstance(loaded_state, dict) and isinstance(loaded_state.get('services'), dict)):
            raise ValueError(f'Rendered state {rendered_state_path} must contain a "services" mapping')
        rendered_services = loaded_state['services']

    expected: dict[str, ExpectedEnv] = {}
    for service_name, raw_service_config in services.items():
        service_config = render_backend_runtime_env._as_config_dict(raw_service_config) or {}
        env_map = render_backend_runtime_env._as_config_dict(service_config.get('env')) or {}
        secrets_map = render_backend_runtime_env._as_config_dict(service_config.get('secrets')) or {}
        service_expected: ExpectedEnv = {}
        for key, entry in env_map.items():
            # Unresolved deploy-time bindings stay name-only (None): the renderer may omit them.
            service_expected[str(key)] = _manifest_entry_hash(str(key), entry, secret=False, environ=environ)
        for key, entry in secrets_map.items():
            service_expected[str(key)] = _manifest_entry_hash(str(key), entry, secret=True, environ=environ)
        rendered_service = render_backend_runtime_env._as_config_dict(rendered_services.get(service_name)) or {}
        if rendered_service:
            # The rendered state is the exact deploy contract. A provisional
            # env_var binding the renderer omitted (unset at deploy time, or a
            # secret env_var resolving empty) is not part of what was deployed;
            # inheriting it as a name-only requirement from the raw manifest
            # would report false drift against exact state.
            rendered_names = {
                entry['name']
                for entry in rendered_service.get('env', []) or []
                if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']
            }
            bindings: dict[str, Any] = {**env_map, **secrets_map}
            service_expected = {
                key: digest
                for key, digest in service_expected.items()
                if key in rendered_names
                or not isinstance(bindings.get(key), Mapping)
                or not bindings[key].get('env_var')
            }
        for entry in rendered_service.get('env', []) or []:
            if isinstance(entry, dict) and isinstance(entry.get('name'), str) and entry['name']:
                service_expected[entry['name']] = env_entry_hash(entry)
        expected[str(service_name)] = service_expected
    return project, region, expected


def declared_manifest_keys(
    *,
    env: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
) -> tuple[str, str, dict[str, frozenset[str]]]:
    project, region, expected = expected_cloud_run_env(
        env=env, manifest_path=manifest_path, rendered_state_path=rendered_state_path
    )
    return project, region, {service: frozenset(keys) for service, keys in expected.items()}


def manifest_config_map(env: str, manifest_path: Path = DEFAULT_MANIFEST) -> tuple[str | None, dict[str, Any]]:
    """The environment's shared GKE ConfigMap (name, entries) from the manifest."""
    env_config = _manifest_env_config(env, manifest_path)
    gke = render_backend_runtime_env._as_config_dict(env_config.get('gke')) or {}
    config_map = render_backend_runtime_env._as_config_dict(gke.get('config_map')) or {}
    name = config_map.get('name')
    entries = render_backend_runtime_env._as_config_dict(config_map.get('entries')) or {}
    return (str(name) if isinstance(name, str) and name else None), entries


def _expected_envfrom_entries(entries: Mapping[str, Any]) -> ExpectedEnv:
    """Expected hashes for envFrom ConfigMap keys; deploy-time sources stay name-only."""
    expected: ExpectedEnv = {}
    for key, raw in entries.items():
        entry = render_backend_runtime_env._as_config_dict(raw) or {}
        if entry.get('source') == 'literal' and isinstance(entry.get('value'), str):
            expected[str(key)] = value_hash('value', str(entry['value']))
        else:
            expected[str(key)] = None  # environment-sourced: only deploy time knows the value
    return expected


def expected_gke_envfrom_refs(workload: str, *, env: str, root: Path = ROOT) -> tuple[str, ...]:
    """envFrom ConfigMap references (prefix included) the chart declares for this workload."""
    spec = GKE_WORKLOADS[workload]
    values = _load_values(root / spec.values_file.format(env=env))
    sources: list[tuple[str, str]] = []
    for source in values.get('envFrom') or []:
        if (
            isinstance(source, dict)
            and isinstance(source.get('configMapRef'), dict)
            and isinstance(source['configMapRef'].get('name'), str)
            and source['configMapRef']['name']
        ):
            prefix = source.get('prefix')
            sources.append((source['configMapRef']['name'], prefix if isinstance(prefix, str) else ''))
    if not sources:
        name = values.get('runtimeConfigMapName')
        if isinstance(name, str) and name:
            sources = [(name, '')]
    return _envfrom_ref_identities(tuple(dict.fromkeys(sources)))


def _load_values(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return loaded


def expected_gke_env_from_values(workload: str, *, env: str, root: Path = ROOT) -> ExpectedEnv | None:
    """Expected env from the chart values ``env`` list; None when the chart builds env in its template."""
    spec = GKE_WORKLOADS[workload]
    values = _load_values(root / spec.values_file.format(env=env))
    entries = values.get('env')
    if not isinstance(entries, list):
        return None
    expected: ExpectedEnv = {}
    runtime_config_map = values.get('runtimeConfigMapName')
    for raw in entries:
        if not isinstance(raw, dict) or not isinstance(raw.get('name'), str):
            continue
        name = str(raw['name'])
        entry: dict[str, Any] = dict(raw)
        # Mirror the two chart-template rewrites so values mode matches `helm template`.
        if workload == 'backend-listen' and name == 'GOOGLE_CLOUD_PROJECT':
            entry = {'name': name, 'value': values.get('runtimeGcpProjectId', entry.get('value'))}
        value_from = entry.get('valueFrom')
        if isinstance(value_from, dict) and isinstance(value_from.get('configMapKeyRef'), dict) and runtime_config_map:
            entry['valueFrom'] = {'configMapKeyRef': {**value_from['configMapKeyRef'], 'name': runtime_config_map}}
        expected[name] = env_entry_hash(entry)
    return expected


def expected_gke_env_from_helm(
    workload: str,
    *,
    env: str,
    root: Path = ROOT,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[ExpectedEnv, tuple[str, ...]]:
    """Expected env and envFrom ConfigMap refs from ``helm template`` of the chart
    with its prod/dev values (exact chart semantics)."""
    spec = GKE_WORKLOADS[workload]
    deployment = spec.deployment.format(env=env)
    result = runner(
        [
            'helm',
            'template',
            deployment,
            str(root / spec.chart),
            '-f',
            str(root / spec.values_file.format(env=env)),
            '--namespace',
            f'{env}-omi-backend',
            *(arg for pin in spec.helm_image_args for arg in ('--set-string', pin)),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    for document in yaml.safe_load_all(result.stdout):
        if isinstance(document, dict) and document.get('kind') == 'Deployment':
            if (document.get('metadata') or {}).get('name') != deployment:
                continue
            pod_spec = ((document.get('spec') or {}).get('template') or {}).get('spec') or {}
            container = _application_container(
                pod_spec.get('containers'), scope=f'helm {workload}', name=spec.container
            )
            env = cast(ExpectedEnv, _env_list_to_live(container.get('env', []), scope=f'helm {workload}'))
            return env, _envfrom_ref_identities(_envfrom_sources(container))
    raise ValueError(f'helm template rendered no Deployment {deployment!r}')


# ── live env (serving side) ─────────────────────────────────────────────────


@dataclass
class LiveService:
    targets: list[tuple[ServingTarget, LiveEnv]] = field(default_factory=list)
    source: str = 'serving'
    template_name: str | None = None
    template_env: LiveEnv | None = None
    envfrom_refs: tuple[str, ...] = ()  # envFrom ConfigMaps referenced by serving targets
    envfrom_unresolved: tuple[str, ...] = ()  # referenced ConfigMaps whose data could not be read
    # References whose current ConfigMap data cannot be proven to match what the
    # running pods resolved at container start (all live reads; K8s does not
    # refresh envFrom for existing processes).
    envfrom_unproven: tuple[str, ...] = ()


def _run_json(runner: Callable[..., Any], argv: list[str]) -> Any:
    result = runner(argv, check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def serving_revisions(service_doc: Mapping[str, Any]) -> list[tuple[str, int]]:
    """Revisions with traffic > 0 from ``status.traffic``; resolves ``latestRevision: true`` entries."""
    status = service_doc.get('status')
    if not isinstance(status, Mapping) or not isinstance(status.get('traffic'), list):
        raise ValueError('service has no status.traffic; refusing to fall back to spec.template')
    weights: dict[str, int] = {}
    for entry in status['traffic']:
        if not isinstance(entry, Mapping):
            continue
        percent = int(entry.get('percent') or 0)
        if percent <= 0:
            continue
        name = entry.get('revisionName')
        if not name and entry.get('latestRevision'):
            name = status.get('latestReadyRevisionName')
        if not isinstance(name, str) or not name:
            raise ValueError('status.traffic entry has no resolvable revision name')
        weights[name] = weights.get(name, 0) + percent
    if not weights:
        raise ValueError('status.traffic routes no traffic to any revision')
    return sorted(weights.items(), key=lambda item: (-item[1], item[0]))


def _template_env(service_doc: Mapping[str, Any], *, service: str) -> tuple[str | None, LiveEnv | None]:
    template = (service_doc.get('spec') or {}).get('template')
    if not isinstance(template, Mapping):
        return None, None
    containers = (template.get('spec') or {}).get('containers')
    if containers is None:
        return None, None
    container = _application_container(containers, scope=f'Cloud Run service {service} template')
    name = (template.get('metadata') or {}).get('name')
    return (name if isinstance(name, str) else None), _env_list_to_live(container.get('env', []), scope=service)


def _revision_env(revision_doc: Mapping[str, Any], *, revision: str) -> LiveEnv:
    containers = (revision_doc.get('spec') or {}).get('containers')
    container = _application_container(containers, scope=f'Cloud Run revision {revision}')
    return _env_list_to_live(container.get('env', []), scope=f'revision {revision}')


def read_cloud_run_service(
    service: str,
    *,
    project: str,
    region: str,
    offline_services: Mapping[str, Any] | None = None,
    offline_revisions: Mapping[str, Any] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> LiveService:
    if offline_services is not None:
        service_doc = offline_services.get(service)
        if not isinstance(service_doc, Mapping):
            raise ValueError(f'Missing service {service!r} in offline Cloud Run state')
        if isinstance(service_doc.get('env'), list):
            # Env-only snapshot fixture (no traffic information): compare it as given.
            # Anything else — including a spec.template without status.traffic — is
            # refused below by serving_revisions() instead of being misread as serving.
            env = _env_list_to_live(service_doc['env'], scope=service)
            target = ServingTarget(
                name='snapshot',
                weight=100,
                key_count=len(env),
                fingerprint=env_fingerprint(env),
                display_fingerprint=env_fingerprint(env, redacted=True),
            )
            return LiveService(targets=[(target, env)], source='snapshot')
    else:
        service_doc = _run_json(
            runner,
            [
                'gcloud',
                'run',
                'services',
                'describe',
                service,
                f'--project={project}',
                f'--region={region}',
                '--format=json',
            ],
        )
        if not isinstance(service_doc, Mapping):
            raise ValueError(f'Cloud Run service {service} describe did not return a JSON object')

    live = LiveService()
    live.template_name, live.template_env = _template_env(service_doc, service=service)
    for revision, percent in serving_revisions(service_doc):
        if offline_revisions is not None:
            revision_doc = offline_revisions.get(revision)
            if not isinstance(revision_doc, Mapping):
                raise ValueError(f'Missing serving revision {revision!r} in offline Cloud Run state')
        else:
            revision_doc = _run_json(
                runner,
                [
                    'gcloud',
                    'run',
                    'revisions',
                    'describe',
                    revision,
                    f'--project={project}',
                    f'--region={region}',
                    '--format=json',
                ],
            )
        env = _revision_env(revision_doc, revision=revision)
        live.targets.append(
            (
                ServingTarget(
                    name=revision,
                    weight=percent,
                    key_count=len(env),
                    fingerprint=env_fingerprint(env),
                    display_fingerprint=env_fingerprint(env, redacted=True),
                ),
                env,
            )
        )
    return live


def read_gke_workload(
    workload: str,
    *,
    env: str,
    kube_context: str | None,
    offline_gke: Mapping[str, Any] | None = None,
    runner: Callable[..., Any] = subprocess.run,
    replicaset_cache: dict[str, Any] | None = None,
    configmap_cache: dict[str, Any] | None = None,
) -> LiveService:
    """Env of every ReplicaSet of the Deployment that holds ready pods (what is actually serving)."""
    spec = GKE_WORKLOADS[workload]
    deployment_name = spec.deployment.format(env=env)
    namespace = f'{env}-omi-backend'
    if offline_gke is not None:
        workload_doc = offline_gke.get(workload)
        if not isinstance(workload_doc, Mapping):
            raise ValueError(f'Missing GKE workload {workload!r} in offline state')
        deployment = workload_doc.get('deployment') or {}
        replicasets = workload_doc.get('replicasets') or []
        configmaps = workload_doc.get('configmaps')
        if not isinstance(configmaps, Mapping):
            shared = offline_gke.get('configmaps')
            configmaps = shared if isinstance(shared, Mapping) else {}

        def resolve_configmap(ref: str) -> Mapping[str, Any] | None:
            # None marks an offline fixture that does not carry this ConfigMap's
            # data; the workload reports INVENTORY rather than guessing.
            doc = configmaps.get(ref)
            if isinstance(doc, Mapping) and isinstance(doc.get('data'), Mapping):
                return doc['data']
            if (
                isinstance(doc, Mapping)
                and doc
                and all(isinstance(k, str) and isinstance(v, str) for k, v in doc.items())
            ):
                return doc  # plain key -> value fixture
            return None

        def configmap_is_proven(ref: str) -> bool:
            # An offline fixture is a captured snapshot: the data given is exactly
            # what the captured pods resolved. Nothing to prove.
            return True

    else:
        if not kube_context:
            raise ValueError('--kube-context is required for live GKE reads')
        base = ['kubectl', f'--context={kube_context}', '-n', namespace, 'get']
        deployment = _run_json(runner, [*base, 'deployment', deployment_name, '-o', 'json'])
        cache = replicaset_cache if replicaset_cache is not None else {}
        if namespace not in cache:
            cache[namespace] = _run_json(runner, [*base, 'replicasets', '-o', 'json']).get('items', [])
        replicasets = cache[namespace]
        cm_cache = configmap_cache if configmap_cache is not None else {}

        def resolve_configmap(ref: str) -> Mapping[str, Any] | None:
            # A live read that fails raises (fetch error); one that succeeds but has
            # no data mapping resolves to an empty key set.
            if ref not in cm_cache:
                cm_doc = _run_json(runner, [*base, 'configmap', ref, '-o', 'json'])
                cm_cache[ref] = cm_doc.get('data') if isinstance(cm_doc.get('data'), Mapping) else {}
            return cm_cache[ref]

        def configmap_is_proven(ref: str) -> bool:
            # Kubernetes never refreshes envFrom for running containers, and a
            # ConfigMap's metadata carries no trustworthy last-write timestamp
            # (updates bump resourceVersion, which is not comparable across
            # objects, and leave creationTimestamp untouched). A live read
            # therefore cannot prove the ready pods resolved this data; the
            # workload reports INVENTORY for envFrom keys instead of asserting OK.
            return False

    def envfrom_entries(container: Mapping[str, Any] | None) -> LiveEnv:
        merged: LiveEnv = {}
        for name, prefix in _envfrom_sources(container):
            data = resolve_configmap(name)
            if data is None:
                continue
            for key, digest in _config_map_data_keys(data).items():
                merged.setdefault(f'{prefix}{key}', digest)
        return merged

    live = LiveService()
    refs_seen: set[str] = set()
    refs_unresolved: set[str] = set()
    refs_unproven: set[str] = set()
    template_spec = ((deployment.get('spec') or {}).get('template') or {}).get('spec') or {}
    if template_spec.get('containers') is not None:
        container = _application_container(template_spec['containers'], scope=deployment_name, name=spec.container)
        live.template_name = deployment_name
        template_env = _env_list_to_live(container.get('env', []), scope=deployment_name)
        # envFrom keys join the template fingerprint too, so template vs serving
        # stays comparable when both bulk-load the same ConfigMap.
        live.template_env = {**envfrom_entries(container), **template_env}
    for rs in replicasets:
        if not isinstance(rs, Mapping):
            continue
        owners = (rs.get('metadata') or {}).get('ownerReferences') or []
        if not any(o.get('kind') == 'Deployment' and o.get('name') == deployment_name for o in owners):
            continue
        ready = int((rs.get('status') or {}).get('readyReplicas') or 0)
        if ready <= 0:
            continue
        rs_name = str((rs.get('metadata') or {}).get('name') or 'replicaset')
        pod_spec = ((rs.get('spec') or {}).get('template') or {}).get('spec') or {}
        container = _application_container(pod_spec.get('containers'), scope=rs_name, name=spec.container)
        env_map = _env_list_to_live(container.get('env', []), scope=rs_name)
        for ref in _envfrom_ref_identities(_envfrom_sources(container)):
            refs_seen.add(ref)
            source_name = ref.split('#', 1)[0]
            if resolve_configmap(source_name) is None:
                refs_unresolved.add(ref)
            elif not configmap_is_proven(source_name):
                refs_unproven.add(ref)
        # Explicit env entries win over envFrom keys, matching pod runtime semantics.
        env_map = {**envfrom_entries(container), **env_map}
        live.targets.append(
            (
                ServingTarget(
                    name=rs_name,
                    weight=ready,
                    key_count=len(env_map),
                    fingerprint=env_fingerprint(env_map),
                    display_fingerprint=env_fingerprint(env_map, redacted=True),
                ),
                env_map,
            )
        )
    if not live.targets:
        raise ValueError(f'Deployment {deployment_name} has no ReplicaSet with ready pods')
    live.envfrom_refs = tuple(sorted(refs_seen))
    live.envfrom_unresolved = tuple(sorted(refs_unresolved))
    live.envfrom_unproven = tuple(sorted(refs_unproven))
    live.targets.sort(key=lambda item: (-item[0].weight, item[0].name))
    return live


# ── comparison ──────────────────────────────────────────────────────────────


def compare_service(
    service: str,
    *,
    expected: ExpectedEnv | None,
    live: LiveService,
    allowed: frozenset[str],
    platform: str,
    expected_envfrom_refs: tuple[str, ...] = (),
    expected_envfrom_unresolved: tuple[str, ...] = (),
    expected_envfrom_keys: frozenset[str] = frozenset(),
) -> ServiceEnvDrift:
    expected_env: ExpectedEnv = expected or {}
    declared = frozenset(expected_env)
    envfrom_mismatched: tuple[str, ...] = ()
    envfrom_unresolved: tuple[str, ...] = ()
    envfrom_unproven: tuple[str, ...] = ()
    unresolved_live_refs: set[str] = set()
    if expected is not None:
        mismatched = set(live.envfrom_refs) ^ set(expected_envfrom_refs)
        envfrom_mismatched = tuple(sorted(mismatched))
        envfrom_unresolved = tuple(
            sorted((set(live.envfrom_unresolved) | set(expected_envfrom_unresolved)) - mismatched)
        )
        # Live ConfigMap data cannot prove what already-running pods resolved at
        # container start (K8s never refreshes envFrom); comparisons on those keys
        # would be assertions, so they are skipped and the workload reports INVENTORY.
        envfrom_unproven = tuple(sorted(set(live.envfrom_unproven) - set(live.envfrom_unresolved) - mismatched))
        # If a live envFrom ConfigMap could not be read, its expected keys cannot be
        # judged missing; excluding all envFrom keys (not just that ref's) is the
        # conservative coarse grain — one shared ConfigMap per environment in practice.
        unresolved_live_refs = set(live.envfrom_unresolved) & set(expected_envfrom_refs)
    skip_missing = expected_envfrom_keys if (unresolved_live_refs or envfrom_unproven) else frozenset()
    skip_compare = expected_envfrom_keys if envfrom_unproven else frozenset()
    live_only: set[str] = set()
    missing: set[str] = set()
    mismatches: list[ValueMismatch] = []
    for target, env_map in live.targets:
        live_only |= ((set(env_map) - declared) - skip_compare) if expected is not None else (set(env_map) - declared)
        if expected is None:
            continue
        # Key presence is checked even when the expected value is unknown (deploy-time
        # binding): a None hash skips only the value comparison, never the key check.
        missing |= declared - set(env_map) - skip_missing
        for key in sorted((declared & set(env_map)) - skip_compare):
            want = expected_env[key]
            if want is not None and env_map[key] != want:
                mismatches.append(
                    ValueMismatch(key=key, expected_hash=want, live_hash=env_map[key], target=target.name)
                )
    template_matches: bool | None = None
    if live.template_env is not None and live.source == 'serving':
        template_fp = env_fingerprint(live.template_env)
        template_matches = all(target.fingerprint == template_fp for target, _ in live.targets)
    primary = live.targets[0][0]
    return ServiceEnvDrift(
        service=service,
        manifest_key_count=len(declared),
        live_key_count=primary.key_count,
        allowlisted_live_only=tuple(sorted(live_only & allowed)),
        unallowlisted_live_only=tuple(sorted(live_only - allowed)) if expected is not None else (),
        platform=platform,
        source=live.source,
        serving=tuple(target for target, _ in live.targets),
        value_mismatches=tuple(mismatches),
        missing_from_live=tuple(sorted(missing)),
        value_unchecked_keys=sum(1 for digest in expected_env.values() if digest is None),
        template_name=live.template_name,
        template_matches_serving=template_matches,
        expected_available=expected is not None,
        envfrom_refs=expected_envfrom_refs if expected is not None else (),
        envfrom_mismatched_refs=envfrom_mismatched,
        envfrom_unresolved=envfrom_unresolved,
        envfrom_unproven=envfrom_unproven,
    )


def allowlist_for_service(
    service: str,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
) -> frozenset[str]:
    return allowlist_map.get('*', frozenset()) | allowlist_map.get(service, frozenset())


def load_allowlist_file(path: Path) -> dict[str, frozenset[str]]:
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict):
        raise ValueError(f'{path} must contain a mapping of service name (or "*") to key lists')
    merged: dict[str, set[str]] = {key: set(values) for key, values in LIVE_MANAGED_ENV_ALLOWLIST.items()}
    for scope, keys in raw.items():
        if not isinstance(scope, str) or not isinstance(keys, list) or not all(isinstance(k, str) and k for k in keys):
            raise ValueError(f'{path}: allowlist entry for {scope!r} must be a list of non-empty key names')
        merged.setdefault(scope, set()).update(keys)
    return {scope: frozenset(names) for scope, names in merged.items()}


def _error_result(service: str, *, declared: int, platform: str, exc: Exception) -> ServiceEnvDrift:
    return ServiceEnvDrift(
        service=service,
        manifest_key_count=declared,
        live_key_count=0,
        allowlisted_live_only=(),
        unallowlisted_live_only=(),
        error=str(exc),
        platform=platform,
    )


def _split_offline_state(state: Mapping[str, Any] | None) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    if state is None:
        return None, None
    services = state.get('services')
    revisions = state.get('revisions')
    return (
        services if isinstance(services, Mapping) else state,
        revisions if isinstance(revisions, Mapping) else {},
    )


def inspect_services_drift(
    *,
    env: str,
    services: Sequence[str] = DEFAULT_SERVICES,
    project: str | None = None,
    region: str | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
    rendered_state_path: Path | None = None,
    cloud_run_state: Mapping[str, Any] | None = None,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
    runner: Any = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str, tuple[ServiceEnvDrift, ...]]:
    manifest_project, manifest_region, expected_by_service = expected_cloud_run_env(
        env=env, manifest_path=manifest_path, rendered_state_path=rendered_state_path, environ=environ
    )
    resolved_project = project or manifest_project
    resolved_region = region or manifest_region
    offline_services, offline_revisions = _split_offline_state(cloud_run_state)

    results: list[ServiceEnvDrift] = []
    for service in services:
        if service not in expected_by_service:
            raise ValueError(f'Service {service!r} is not declared in {manifest_path} for env {env!r}')
        expected = expected_by_service[service]
        try:
            live = read_cloud_run_service(
                service,
                project=resolved_project,
                region=resolved_region,
                offline_services=offline_services,
                offline_revisions=offline_revisions,
                runner=runner,
            )
            results.append(
                compare_service(
                    service,
                    expected=expected,
                    live=live,
                    allowed=allowlist_for_service(service, allowlist_map),
                    platform='cloud_run',
                )
            )
        except Exception as exc:
            results.append(_error_result(service, declared=len(expected), platform='cloud_run', exc=exc))
    return resolved_project, resolved_region, tuple(results)


def inspect_gke_drift(
    *,
    env: str,
    workloads: Sequence[str] = DEFAULT_GKE_WORKLOADS,
    kube_context: str | None = None,
    render: str = 'values',
    gke_state: Mapping[str, Any] | None = None,
    expected_overrides: Mapping[str, ExpectedEnv] | None = None,
    allowlist_map: Mapping[str, frozenset[str]] = LIVE_MANAGED_ENV_ALLOWLIST,
    runner: Any = subprocess.run,
    root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> tuple[ServiceEnvDrift, ...]:
    cm_name, cm_entries = manifest_config_map(env, manifest_path)
    envfrom_expected = _expected_envfrom_entries(cm_entries) if cm_name else {}
    results: list[ServiceEnvDrift] = []
    replicaset_cache: dict[str, Any] = {}
    configmap_cache: dict[str, Any] = {}
    for workload in workloads:
        if workload not in GKE_WORKLOADS:
            raise ValueError(f'Unknown GKE workload {workload!r}; known: {", ".join(GKE_WORKLOADS)}')
        expected: ExpectedEnv | None = None
        expected_refs: tuple[str, ...] = ()
        expected_unresolved: tuple[str, ...] = ()
        expected_envfrom_keys: frozenset[str] = frozenset()
        try:
            if expected_overrides is not None and workload in expected_overrides:
                expected = dict(expected_overrides[workload])
                expected_refs = expected_gke_envfrom_refs(workload, env=env, root=root)
            elif render == 'helm':
                expected, expected_refs = expected_gke_env_from_helm(workload, env=env, root=root, runner=runner)
            else:
                expected = expected_gke_env_from_values(workload, env=env, root=root)
                expected_refs = expected_gke_envfrom_refs(workload, env=env, root=root)
            if expected is not None:
                merged_keys: set[str] = set()
                for ref in expected_refs:
                    if ref == cm_name:
                        for key, digest in envfrom_expected.items():
                            expected.setdefault(key, digest)
                            merged_keys.add(key)
                    else:
                        # The chart references a ConfigMap whose expected keys the
                        # repository cannot enumerate; report inventory, not silence.
                        expected_unresolved = (*expected_unresolved, ref)
                expected_envfrom_keys = frozenset(merged_keys)
            live = read_gke_workload(
                workload,
                env=env,
                kube_context=kube_context,
                offline_gke=gke_state,
                runner=runner,
                replicaset_cache=replicaset_cache,
                configmap_cache=configmap_cache,
            )
            results.append(
                compare_service(
                    workload,
                    expected=expected,
                    live=live,
                    allowed=allowlist_for_service(workload, allowlist_map),
                    platform='gke',
                    expected_envfrom_refs=expected_refs if expected is not None else (),
                    expected_envfrom_unresolved=expected_unresolved,
                    expected_envfrom_keys=expected_envfrom_keys,
                )
            )
        except Exception as exc:
            results.append(_error_result(workload, declared=len(expected or {}), platform='gke', exc=exc))
    return tuple(results)


# ── reports ─────────────────────────────────────────────────────────────────


def _template_cell(item: ServiceEnvDrift) -> str:
    if item.template_matches_serving is None:
        return 'n/a'
    return 'yes' if item.template_matches_serving else '**no**'


def render_markdown_report(
    *,
    env: str,
    project: str,
    region: str,
    results: Sequence[ServiceEnvDrift],
) -> str:
    lines = [
        f'## Runtime env drift: serving workloads vs repository ({env} / `{project}` / `{region}`)',
        '',
        'Read-only comparison of the env that is **serving** (Cloud Run `status.traffic` revisions; GKE ReplicaSets '
        'with ready pods) against `backend/deploy/runtime_env.yaml` and chart values, by key name and value hash. '
        'Values are never printed; hashes of sensitive-looking keys are redacted.',
        '',
        '| Workload | Platform | Serving | Expected keys | Live keys | Value mismatches | Missing live | '
        'Unallowlisted live-only | Allowlisted live-only | Template = serving | Status |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |',
    ]
    for item in results:
        status = f'ERROR ({item.error})' if item.error else item.status
        serving = ', '.join(
            f'`{t.name}` ({t.weight}{"%" if item.platform == "cloud_run" else " ready"})' for t in item.serving
        )
        lines.append(
            f'| `{item.service}` | {item.platform} | {serving or "-"} | {item.manifest_key_count} | {item.live_key_count} | '
            f'{len(item.value_mismatches)} | {len(item.missing_from_live)} | {len(item.unallowlisted_live_only)} | '
            f'{len(item.allowlisted_live_only)} | {_template_cell(item)} | {status} |'
        )
    lines.append('')
    for item in results:
        lines.append(f'### `{item.service}` ({item.platform})')
        if item.error:
            lines.extend([f'- Fetch error: `{item.error}`', ''])
            continue
        for target in item.serving:
            lines.append(
                f'- Serving `{target.name}`: weight {target.weight}, {target.key_count} keys, '
                f'env fingerprint `{target.display_fingerprint}`'
            )
        if item.template_matches_serving is False:
            lines.append(
                f'- Template `{item.template_name}` differs from what is serving. Read serving revisions, not the template.'
            )
        if not item.expected_available:
            lines.append(
                '- Expected env unavailable in values mode (chart builds env in its template); use `--gke-render helm`.'
            )
        if item.envfrom_unresolved:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_unresolved)
            lines.append(f'- envFrom ConfigMap keys not compared (unresolved): {refs_str}')
        if item.envfrom_unproven:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_unproven)
            lines.append(
                f'- envFrom ConfigMap keys not compared (live data unproven for running pods; '
                f'K8s never refreshes envFrom): {refs_str}'
            )
        if item.envfrom_mismatched_refs:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_mismatched_refs)
            lines.append(f'- envFrom ConfigMap reference drift (live vs expected): {refs_str}')
        elif item.envfrom_refs:
            refs_str = ', '.join(f'`{name}`' for name in item.envfrom_refs)
            lines.append(f'- envFrom ConfigMaps (expected and serving): {refs_str}')
        if item.value_unchecked_keys:
            lines.append(
                f'- Keys compared by name only (deploy-time binding, no rendered state): {item.value_unchecked_keys}'
            )
        allowlisted_str = ', '.join(f'`{name}`' for name in item.allowlisted_live_only) or 'none'
        lines.append(f'- Allowlisted live-managed keys ({len(item.allowlisted_live_only)}): {allowlisted_str}')
        drift_str = ', '.join(f'`{name}`' for name in item.unallowlisted_live_only) or 'none'
        lines.append(
            f'- Unallowlisted live keys missing from manifest ({len(item.unallowlisted_live_only)}): {drift_str}'
        )
        missing_str = ', '.join(f'`{name}`' for name in item.missing_from_live) or 'none'
        lines.append(f'- Expected keys absent from serving env ({len(item.missing_from_live)}): {missing_str}')
        lines.append(f'- Value mismatches ({len(item.value_mismatches)}):' + ('' if item.value_mismatches else ' none'))
        for mismatch in item.value_mismatches:
            lines.append(
                f'  - `{mismatch.key}` on `{mismatch.target}`: expected `{display_hash(mismatch.key, mismatch.expected_hash)}`, '
                f'serving `{display_hash(mismatch.key, mismatch.live_hash)}`'
            )
        lines.append('')
    return '\n'.join(lines)


def render_json_report(
    *,
    env: str,
    project: str,
    region: str,
    results: Sequence[ServiceEnvDrift],
) -> str:
    payload = {
        'env': env,
        'project': project,
        'region': region,
        'drift': any(item.has_drift for item in results),
        'errors': sum(1 for item in results if item.error),
        'services': {
            item.service: {
                'platform': item.platform,
                'status': item.status,
                'source': item.source,
                'manifest_key_count': item.manifest_key_count,
                'live_key_count': item.live_key_count,
                'serving': [
                    {'name': t.name, 'weight': t.weight, 'key_count': t.key_count, 'fingerprint': t.display_fingerprint}
                    for t in item.serving
                ],
                'template_name': item.template_name,
                'template_matches_serving': item.template_matches_serving,
                'allowlisted_live_only': list(item.allowlisted_live_only),
                'unallowlisted_live_only': list(item.unallowlisted_live_only),
                'missing_from_live': list(item.missing_from_live),
                'value_unchecked_keys': item.value_unchecked_keys,
                'envfrom_refs': list(item.envfrom_refs),
                'envfrom_mismatched_refs': list(item.envfrom_mismatched_refs),
                'envfrom_unresolved': list(item.envfrom_unresolved),
                'envfrom_unproven': list(item.envfrom_unproven),
                'value_mismatches': [
                    {
                        'key': m.key,
                        'target': m.target,
                        'expected_hash': display_hash(m.key, m.expected_hash),
                        'live_hash': display_hash(m.key, m.live_hash),
                    }
                    for m in item.value_mismatches
                ],
                **({'error': item.error} if item.error else {}),
            }
            for item in results
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + '\n'


def exit_code(results: Sequence[ServiceEnvDrift], *, strict: bool) -> int:
    if not strict:
        return 0
    # An incomplete comparison outranks drift found elsewhere: a train gate must not
    # read a fetch/render failure as an ordinary, already-diagnosed drift case.
    if any(item.error for item in results):
        return 2
    if any(item.has_drift for item in results):
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=('dev', 'prod'), default='prod')
    parser.add_argument('--project', help='GCP project ID (defaults to manifest compute_project for --env).')
    parser.add_argument('--region', help='Cloud Run region (defaults to manifest region for --env).')
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        '--rendered-state',
        type=Path,
        help='Optional state JSON from render_backend_runtime_env.py --state-output (exact expected values).',
    )
    parser.add_argument(
        '--cloud-run-state',
        type=Path,
        help='Offline JSON fixture: {"services": {name: describe-doc}, "revisions": {name: revision-doc}}.',
    )
    parser.add_argument(
        '--allowlist-file',
        type=Path,
        help='Optional YAML/JSON file extending the live-managed key allowlist.',
    )
    parser.add_argument('--service', action='append', dest='services', help='Cloud Run service name (repeatable).')
    parser.add_argument('--no-cloud-run', action='store_true', help='Skip Cloud Run services (GKE only).')
    parser.add_argument('--gke', action='store_true', help='Also check GKE workloads (listen, pusher, batch worker).')
    parser.add_argument(
        '--gke-workload',
        action='append',
        dest='gke_workloads',
        choices=tuple(GKE_WORKLOADS),
        help='GKE workload to check (repeatable; implies --gke).',
    )
    parser.add_argument('--kube-context', help='Explicit kubectl context for live GKE reads (required with --gke).')
    parser.add_argument(
        '--gke-render',
        choices=('values', 'helm', 'auto'),
        default='auto',
        help='Expected GKE env source: chart values env list, `helm template`, or helm when on PATH.',
    )
    parser.add_argument(
        '--gke-state',
        type=Path,
        help='Offline GKE JSON fixture: {workload: {deployment, replicasets}} plus optional '
        'shared {"configmaps": {name: {"data": {...}}}} for envFrom resolution.',
    )
    parser.add_argument('--format', choices=('markdown', 'json'), default='markdown')
    parser.add_argument(
        '--summary-file', type=Path, help='Append markdown report to this file (e.g. GITHUB_STEP_SUMMARY).'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit 1 on drift (value mismatch, missing or unallowlisted key), 2 on fetch/render errors '
        '(2 wins when both: the comparison did not complete).',
    )
    args = parser.parse_args(argv)

    if args.no_cloud_run and not (args.gke or args.gke_workloads):
        parser.error('--no-cloud-run requires --gke or --gke-workload; otherwise there is nothing to check')

    allowlist_map = load_allowlist_file(args.allowlist_file) if args.allowlist_file else LIVE_MANAGED_ENV_ALLOWLIST
    services = tuple(args.services or DEFAULT_SERVICES)

    try:
        # Offline fixture loads belong inside the handled section: a missing or
        # malformed --cloud-run-state / --gke-state is an operational (exit 2)
        # failure, not drift, and must not escape as an uncaught exception.
        offline_state = (
            cast(Mapping[str, Any], json.loads(args.cloud_run_state.read_text(encoding='utf-8')))
            if args.cloud_run_state
            else None
        )
        project, region, results = inspect_services_drift(
            env=args.env,
            services=() if args.no_cloud_run else services,
            project=args.project,
            region=args.region,
            manifest_path=args.manifest,
            rendered_state_path=args.rendered_state,
            cloud_run_state=offline_state,
            allowlist_map=allowlist_map,
        )
        if args.gke or args.gke_workloads:
            render = args.gke_render
            if render == 'auto':
                render = 'helm' if shutil.which('helm') else 'values'
            gke_state = (
                cast(Mapping[str, Any], json.loads(args.gke_state.read_text(encoding='utf-8')))
                if args.gke_state
                else None
            )
            results = results + inspect_gke_drift(
                env=args.env,
                workloads=tuple(args.gke_workloads or DEFAULT_GKE_WORKLOADS),
                kube_context=args.kube_context,
                render=render,
                gke_state=gke_state,
                allowlist_map=allowlist_map,
                manifest_path=args.manifest,
            )
    except Exception as exc:
        # Expected-state render failures (unreadable/malformed manifest or rendered
        # state) are operational errors, not drift: report and exit with the
        # documented render-error status instead of a traceback and exit 1.
        print(f'ERROR: could not render expected state: {exc}', file=sys.stderr)
        return 2 if args.strict else 0

    markdown = render_markdown_report(env=args.env, project=project, region=region, results=results)
    if args.format == 'json':
        sys.stdout.write(render_json_report(env=args.env, project=project, region=region, results=results))
    else:
        sys.stdout.write(markdown)

    if args.summary_file is not None:
        try:
            with args.summary_file.open('a', encoding='utf-8') as handle:
                handle.write(markdown)
                if not markdown.endswith('\n'):
                    handle.write('\n')
        except OSError as exc:
            print(f'WARNING: could not write summary file {args.summary_file}: {exc}', file=sys.stderr)

    return exit_code(results, strict=args.strict)


if __name__ == '__main__':
    raise SystemExit(main())
