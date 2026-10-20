#!/usr/bin/env python3
"""Cross-service deployment contract: one rendered model of every backend process, data-driven invariants.

Per-feature validators check one service at a time. The 2026-10-18 rollout lost hours to wiring that only
breaks *between* deployments: a Cloud Run-shaped ConfigMap entry (#22098), a recovery task enqueued to an
empty audience whose only authenticated target had recovery off (#22149), and a flag flipped on the
listener but never set on the GPU worker that also reads it (#22121).

This module renders dev and prod the way the deploy workflows do (``render_backend_runtime_env`` for Cloud
Run, ``render_gke_backend_config`` for the shared ConfigMap, ``helm template`` for charts whose env is
templated), builds one ``Deployment`` per process with the env it would actually run with, and evaluates
the invariant tables below. New invariants are one row: add a ``TaskEdge``, a ``COUPLED_FLAGS`` entry, or
a function to ``INVARIANTS``.

    python backend/scripts/cross_service_contract.py                # current checkout
    python backend/scripts/cross_service_contract.py --ref 2f1416c4  # any commit (manifest + charts at ref)
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, cast
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scripts import render_backend_runtime_env as cloud_run_renderer  # noqa: E402
from scripts import render_gke_backend_config as gke_renderer  # noqa: E402
from scripts.policy_env_reads import policy_env_reads  # noqa: E402

ConfigDict = dict[str, Any]
ENVS = ('dev', 'prod')
MANIFEST = 'backend/deploy/runtime_env.yaml'
DYNAMIC = '<dynamic>'  # deploy-time GitHub variable with no checked-in default
SECRET = '<secret>'
CLOUD_RUN_DEFAULT_TIMEOUT_SECONDS = 300

# --------------------------------------------------------------------------------------------------
# Invariant data. Each row is one contract; add rows, not code.
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskEdge:
    """A Cloud Tasks (or worker HTTP) hop: who enqueues, where it lands, what the landing host must run.

    ``dispatch_when`` are effective env values (code defaults applied) that make a host enqueue.
    ``target_env`` names the env var holding the target URL/audience on the dispatcher.
    ``dispatch_audience_env`` is what the dispatcher mints; ``verify_audience_env`` (with its
    ``verify_audience_fallback_env``) is what the *target* verifies, per production's
    ``AUDIENCE or handler_url`` fallbacks. ``handler_requires`` are effective env values the target
    needs for the handler to do the work (rather than ack a no-op).
    """

    id: str
    route: str
    dispatch_when: dict[str, str]
    target_env: str
    handler_requires: dict[str, str] = field(default_factory=dict)
    dispatch_audience_env: str | None = None
    verify_audience_env: str | None = None
    verify_audience_fallback_env: str | None = None  # verify-side ``AUDIENCE or URL`` fallback; default target_env
    audience_fallback: bool = False  # production mints ``AUDIENCE or handler_url`` (sync family)
    deadline_seconds: int | None = None
    dispatchers: tuple[str, ...] = ()  # restrict to these deployment ids; empty = every deployment
    empty_target_ok: bool = False  # an empty target selects a documented non-HTTP mode (e.g. direct Firestore)
    append_route: bool = False  # production joins its RPC path onto a bare origin; the URL must carry no path


TASK_EDGES: tuple[TaskEdge, ...] = (
    TaskEdge(
        id='batch-quarantine-recovery',
        route='/v2/batch-pipeline/recover-quarantine',
        dispatch_when={
            'BATCH_PIPELINE_SERVING_ENABLED': 'true',
            'BATCH_PIPELINE_RECOVERY_TASKS_ENABLED': 'true',
        },
        target_env='BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE',
        # Eligibility is the job's recorded recovery part, not the receiving host's env.
        dispatch_audience_env='BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE',
        verify_audience_env='BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE',
        deadline_seconds=1500,  # utils/cloud_tasks.DISPATCH_DEADLINE_SECONDS
        append_route=True,  # quarantine_recovery appends the route to the serving origin at dispatch
    ),
    TaskEdge(
        id='batch-worker-pull',
        route='/v2/batch-pipeline/pull',
        dispatch_when={'BATCH_PIPELINE_WORKER_ENABLED': 'true'},
        target_env='BATCH_PIPELINE_API_URL',
        dispatch_audience_env='BATCH_PIPELINE_WORKER_AUDIENCE',
        verify_audience_env='BATCH_PIPELINE_WORKER_AUDIENCE',
        dispatchers=('helm/batch-pipeline-worker',),
        empty_target_ok=True,  # dev worker runs against Firestore directly; the chart forbids empty in prod
        append_route=True,  # compute_client appends its RPC path to the bare serving origin
    ),
    TaskEdge(
        id='sync-jobs',
        route='/v2/sync-jobs/run',
        dispatch_when={'SYNC_DISPATCH_MODE': 'cloud_tasks'},
        target_env='SYNC_TASKS_HANDLER_URL',
        dispatch_audience_env='SYNC_TASKS_OIDC_AUDIENCE',
        verify_audience_env='SYNC_TASKS_OIDC_AUDIENCE',
        verify_audience_fallback_env='SYNC_TASKS_HANDLER_URL',
        audience_fallback=True,  # _oidc_audience(): SYNC_TASKS_OIDC_AUDIENCE or handler URL
        deadline_seconds=1500,
    ),
    TaskEdge(
        id='sync-backfill',
        route='/v2/sync-jobs/run',
        dispatch_when={'SYNC_DISPATCH_MODE': 'cloud_tasks', 'SYNC_BACKFILL_ROUTING_ENABLED': 'true'},
        target_env='SYNC_BACKFILL_TASKS_HANDLER_URL',
        dispatch_audience_env='SYNC_BACKFILL_TASKS_OIDC_AUDIENCE',
        verify_audience_env='SYNC_TASKS_OIDC_AUDIENCE',
        verify_audience_fallback_env='SYNC_TASKS_HANDLER_URL',
        audience_fallback=True,  # dispatch: SYNC_BACKFILL_TASKS_OIDC_AUDIENCE or backfill handler URL
        deadline_seconds=1500,
    ),
    TaskEdge(
        id='listen-finalization',
        route='/v1/conversation-finalization-jobs/run',
        dispatch_when={'LISTEN_FINALIZATION_DISPATCH_MODE': 'cloud_tasks'},
        target_env='LISTEN_FINALIZATION_TASKS_HANDLER_URL',
        dispatch_audience_env='LISTEN_FINALIZATION_TASKS_OIDC_AUDIENCE',
        verify_audience_env='LISTEN_FINALIZATION_TASKS_OIDC_AUDIENCE',
        verify_audience_fallback_env='LISTEN_FINALIZATION_TASKS_HANDLER_URL',
        audience_fallback=True,  # _listen_finalization_audience(): audience or handler URL
        deadline_seconds=1500,
    ),
    TaskEdge(
        id='account-deletion',
        route='/v1/users/account-deletion-wipes/run',
        dispatch_when={'ACCOUNT_DELETION_DISPATCH_MODE': 'cloud_tasks'},
        target_env='ACCOUNT_DELETION_HANDLER_URL',
        dispatch_audience_env='ACCOUNT_DELETION_TASKS_OIDC_AUDIENCE',
        verify_audience_env='ACCOUNT_DELETION_TASKS_OIDC_AUDIENCE',
        verify_audience_fallback_env='ACCOUNT_DELETION_HANDLER_URL',
        audience_fallback=True,  # _account_deletion_oidc_audience(): audience or handler URL
        deadline_seconds=1500,
    ),
    # Legacy-sync retirement (contracts (a)/(d)): outbox wakes for the workers role. dispatch_when names the real
    # runtime switch (M1 Grok L01-2); the ops file (lane 7) declares the queue wiring.
    TaskEdge(
        id='enrichment',
        route='/v2/enrichment/run',
        # config/enrichment.py: new sr- obligations bind to this queue only when ENRICHMENT_ROUTE=enrichment_queue.
        dispatch_when={'ENRICHMENT_ROUTE': 'enrichment_queue'},
        target_env='ENRICHMENT_TASKS_HANDLER_URL',
        dispatch_audience_env='ENRICHMENT_TASKS_OIDC_AUDIENCE',
        verify_audience_env='ENRICHMENT_TASKS_OIDC_AUDIENCE',
        verify_audience_fallback_env='ENRICHMENT_TASKS_HANDLER_URL',
        audience_fallback=True,  # dispatch_binding() and routers/enrichment.py: audience or handler URL
        deadline_seconds=1500,
    ),
    TaskEdge(
        id='provider-stt',
        route='/v2/batch-pipeline/provider-stt/run',
        # utils/provider_stt_tasks.py wakes whenever the handler URL and queue are set; no mode switch exists.
        dispatch_when={},
        target_env='PROVIDER_STT_TASKS_HANDLER_URL',
        dispatch_audience_env='PROVIDER_STT_TASKS_OIDC_AUDIENCE',
        verify_audience_env='PROVIDER_STT_TASKS_OIDC_AUDIENCE',
        verify_audience_fallback_env='PROVIDER_STT_TASKS_HANDLER_URL',
        audience_fallback=True,  # create_wake(): PROVIDER_STT_TASKS_OIDC_AUDIENCE or handler URL
        empty_target_ok=True,  # unset handler = provider-STT dispatch not configured on that host
        deadline_seconds=1500,
    ),
)

# Flags whose effective value must agree on every listed deployment that exists in the environment. Use for
# flags where a split changes shared durable state (a scheduler order, a projection protocol) rather than a
# per-host behavior.
COUPLED_FLAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', ('gke/backend-listen', 'helm/batch-pipeline-worker')),
    ('BATCH_PIPELINE_SHARED_LIVE_ENABLED', ('gke/backend-listen', 'helm/batch-pipeline-worker')),
    ('BATCH_PIPELINE_UNIT_SECONDS', ('cloud_run/backend-sync', 'gke/backend-listen', 'helm/batch-pipeline-worker')),
)

# Separately deployed processes whose flags must not silently fall back to a code default while every backend
# host sets the flag. Scoped by key prefix: the import closure over-approximates what a process executes.
READER_SPLIT_SCOPES: dict[str, tuple[str, ...]] = {
    'helm/batch-pipeline-worker': ('BATCH_PIPELINE_', 'STT_CAP_', 'PARAKEET_'),
}

# Charts rendered with ``helm template`` exactly like their deploy workflow does. Values files are
# ``{env}_omi_{name}_values.yaml``; ``image_set`` is the workflow's --set-string image argument.
HELM_CHARTS: tuple[tuple[str, str, str], ...] = (
    ('batch-pipeline-worker', 'diarizer.batch_pipeline_runtime', 'image.digest=sha256:' + 'a' * 64),
)

# Process entrypoints (module paths under backend/) per deployment kind, for "who reads this flag".
BACKEND_ENTRYPOINT = 'main'
GKE_ENTRYPOINTS = {'backend-listen': BACKEND_ENTRYPOINT, 'pusher': 'pusher.main'}

# Keys whose literal values must never carry user identifiers in this public repository.
UID_KEY_PATTERN = re.compile(r'(UID|USER|OWNER)S?_?(ALLOW|DENY)?LIST|_UIDS$|COHORT_UIDS|TEST_UIDS')
FIREBASE_UID_PATTERN = re.compile(r'(?<![A-Za-z0-9])[A-Za-z0-9]{28}(?![A-Za-z0-9])')

TRUTHY = frozenset({'true', '1', 'yes', 'on'})
FALSY = frozenset({'false', '0', 'no', 'off', ''})


# --------------------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------------------


@dataclass
class Deployment:
    id: str  # cloud_run/backend-sync, gke/backend-listen, helm/batch-pipeline-worker, job/notifications-job
    entrypoint: str | None
    env: dict[str, str]
    flags: dict[str, str] = field(default_factory=dict)
    url_hosts: tuple[str, ...] = ()  # hosts this deployment answers on (Cloud Run only)

    @property
    def kind(self) -> str:
        return self.id.split('/', 1)[0]

    @property
    def name(self) -> str:
        return self.id.split('/', 1)[1]


@dataclass
class EnvModel:
    env: str
    deployments: dict[str, Deployment]
    config_map: dict[str, str]
    manifest: ConfigDict
    render_errors: list[str]


@dataclass(frozen=True)
class Violation:
    invariant: str
    env: str
    scope: str
    message: str
    fingerprint: str = ''  # non-sensitive identity detail folded into the ratchet key

    @property
    def key(self) -> str:
        base = f'{self.invariant}|{self.env}|{self.scope}'
        return f'{base}|{self.fingerprint}' if self.fingerprint else base

    def __str__(self) -> str:
        # Values can carry cohort identifiers; never echo them into CI logs.
        return FIREBASE_UID_PATTERN.sub('<uid>', f'[{self.invariant}] {self.env}/{self.scope}: {self.message}')


class Source:
    """File access at the working tree or at a git ref, so pre-fix commits replay through the same checks.

    A ref is materialized once with ``git archive`` (backend/ only) so reads stay plain file reads.
    """

    def __init__(self, root: Path = ROOT, ref: str | None = None):
        self.ref = ref
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        if ref is None:
            self.root = root
            return
        self._tmp = tempfile.TemporaryDirectory(prefix='cross-service-contract-')
        archive = subprocess.run(['git', '-C', str(root), 'archive', ref, 'backend'], capture_output=True, check=True)
        subprocess.run(['tar', '-x', '-C', self._tmp.name], input=archive.stdout, check=True)
        self.root = Path(self._tmp.name)

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding='utf-8')

    def exists(self, rel: str) -> bool:
        return (self.root / rel).exists()

    def directory(self, rel: str) -> Path:
        return self.root / rel

    def close(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()


# Renderer modules the ref evaluation must load from the archived tree, not the current checkout.
_REF_RENDERER_MODULES = (
    'config',
    'config.free_tier_rollout',
    'scripts',
    'scripts.runtime_env_compat',
    'scripts.render_backend_runtime_env',
    'scripts.render_gke_backend_config',
)

_RENDERER_CACHE: dict[str, tuple[Any, Any, str]] = {}


def _import_ref_renderers(root: Path) -> tuple[Any, Any]:
    """Import both renderers from ``root``'s archived backend in isolation, then restore the checkout's modules.

    Without this, ``--ref`` would judge a historical commit under renderer behavior it never contained.
    """
    saved_path = sys.path[:]
    saved_modules = [(name, sys.modules.pop(name)) for name in _REF_RENDERER_MODULES if name in sys.modules]
    sys.path.insert(0, str(root / 'backend'))
    try:
        import scripts.render_backend_runtime_env as ref_cloud_run  # noqa: PLC0415
        import scripts.render_gke_backend_config as ref_gke  # noqa: PLC0415

        return ref_cloud_run, ref_gke
    finally:
        sys.path[:] = saved_path
        for name in _REF_RENDERER_MODULES:
            sys.modules.pop(name, None)
        for name, module in saved_modules:
            sys.modules[name] = module


def _renderer_pair(source: Source) -> tuple[Any, Any, str]:
    """(cloud-run renderer, gke renderer, error). Refs load their own; the checkout reuses the imports above."""
    key = str(source.root)
    if key not in _RENDERER_CACHE:
        if source.ref is None:
            _RENDERER_CACHE[key] = (cloud_run_renderer, gke_renderer, '')
        else:
            try:
                ref_cloud_run, ref_gke = _import_ref_renderers(source.root)
                _RENDERER_CACHE[key] = (ref_cloud_run, ref_gke, '')
            except Exception as exc:  # noqa: BLE001 - any load failure is a reported render error, not a crash
                _RENDERER_CACHE[key] = (None, None, f'renderer code failed to load at ref {source.ref}: {exc}')
    return _RENDERER_CACHE[key]


def _mapping(value: object) -> ConfigDict:
    return cast(ConfigDict, value) if isinstance(value, dict) else {}


@contextlib.contextmanager
def _hermetic_environ(required: set[str], defaulted: set[str]) -> Iterator[None]:
    """Stand in for the deploy workflow's GitHub variables so the real renderers run hermetically.

    ``required`` bindings (no checked-in default) get the ``<dynamic>`` placeholder; ``defaulted`` bindings
    are unset so the renderer falls back to the manifest default instead of an ambient shell/CI value —
    otherwise the baseline is nondeterministic and a broken default can be masked.
    """
    saved = {name: os.environ.get(name) for name in required | defaulted}
    try:
        for name in required:
            os.environ[name] = DYNAMIC
        for name in defaulted - required:  # a name bound both ways stays placeholdered: required wins
            os.environ.pop(name, None)
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextlib.contextmanager
def _patched(owner: object, name: str, value: object) -> Iterator[None]:
    original = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, original)


def _env_var_bindings(node: object) -> tuple[set[str], set[str]]:
    """(required, defaulted) env_var names under ``node``; defaulted ones carry a checked-in default."""
    required: set[str] = set()
    defaulted: set[str] = set()
    if isinstance(node, dict):
        mapping = cast(ConfigDict, node)
        env_var = mapping.get('env_var')
        if isinstance(env_var, str):
            (defaulted if mapping.get('default') is not None else required).add(env_var)
        for value in mapping.values():
            req, dflt = _env_var_bindings(value)
            required |= req
            defaulted |= dflt
    elif isinstance(node, list):
        for value in cast(list[object], node):
            req, dflt = _env_var_bindings(value)
            required |= req
            defaulted |= dflt
    return required, defaulted


_YAML_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)


@functools.lru_cache(maxsize=16)
def _parse_yaml(text: str) -> object:
    return yaml.load(text, Loader=_YAML_LOADER)  # noqa: S506 - a safe loader, libyaml when available


def _load_yaml_text(text: str) -> object:
    # The manifest is ~1 MB; pure-Python parsing dominated a run (2 s per parse, 5 parses per build).
    return copy.deepcopy(_parse_yaml(text))


def _load_yaml_path(path: Path) -> ConfigDict:
    loaded = _load_yaml_text(path.read_text(encoding='utf-8'))
    if not isinstance(loaded, dict):
        raise ValueError(f'{path} must contain a YAML mapping')
    return cast(ConfigDict, loaded)


def _render_cloud_run(renderer: Any, env_config: ConfigDict, errors: list[str]) -> ConfigDict:
    required, defaulted = _env_var_bindings(env_config.get('cloud_run'))
    with _hermetic_environ(required, defaulted):
        try:
            return renderer._render_cloud_run_state(env_config)  # pyright: ignore[reportAttributeAccessIssue]
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f'cloud run render failed: {exc}')
            return {}


def _render_config_map(
    renderer: Any, env: str, manifest_text: str, env_config: ConfigDict, errors: list[str]
) -> dict[str, str]:
    entries = _mapping(_mapping(_mapping(env_config.get('gke')).get('config_map')).get('entries'))
    names = {
        str(key)
        for key, entry in entries.items()
        if _mapping(entry).get('source') == 'environment' and _mapping(entry).get('default') is None
    }
    defaulted = {
        str(key)
        for key, entry in entries.items()
        if _mapping(entry).get('source') == 'environment' and _mapping(entry).get('default') is not None
    }
    legacy = set(renderer.LEGACY_GKE_CONFIG_KEYS.get(env, ()))
    with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as handle:
        handle.write(manifest_text)
        path = Path(handle.name)
    try:
        # Same renderer; only its file load is swapped for the cached parse of identical text.
        with _hermetic_environ(names | legacy, defaulted), _patched(renderer, '_load_yaml', _load_yaml_path):
            _, resolved = renderer.config_map_entries(env, path)
        return resolved
    except ValueError as exc:
        errors.append(f'gke ConfigMap render failed: {exc}')
        return {}
    finally:
        path.unlink(missing_ok=True)


def _rendered_env(entries: list[ConfigDict]) -> dict[str, str]:
    env: dict[str, str] = {}
    for entry in entries:
        if 'valueFrom' in entry:
            env[str(entry['name'])] = SECRET
        else:
            env[str(entry['name'])] = str(entry.get('value', ''))
    return env


def _gke_env(raw_env: ConfigDict, config_map: dict[str, str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for name, raw in raw_env.items():
        entry = _mapping(raw)
        if 'value' in entry:
            env[name] = str(entry['value'])
        elif 'config_map' in entry:
            env[name] = config_map.get(str(_mapping(entry['config_map']).get('key', name)), DYNAMIC)
        elif 'secret' in entry:
            env[name] = SECRET
        elif 'env_var' in entry:
            env[name] = str(entry['default']) if entry.get('default') is not None else DYNAMIC
    return env


def _helm_env(source: Source, env: str, chart: str, image_set: str, errors: list[str]) -> dict[str, str] | None:
    helm = shutil.which('helm')
    if helm is None:
        return None
    chart_rel = f'backend/charts/{chart}'
    values_rel = f'{chart_rel}/{env}_omi_{chart}_values.yaml'
    if not source.exists(values_rel):
        return None
    chart_dir = source.directory(chart_rel)
    result = subprocess.run(
        [
            helm,
            'template',
            f'{env}-omi-{chart}',
            str(chart_dir),
            '--namespace',
            f'{env}-omi-backend',
            '-f',
            str(chart_dir / f'{env}_omi_{chart}_values.yaml'),
            '--set-string',
            image_set,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        errors.append(f'helm template {chart} ({env}) failed: {result.stderr.strip()[:400]}')
        return {}
    for document in yaml.safe_load_all(result.stdout):
        if _mapping(document).get('kind') != 'Deployment':
            continue
        containers = _mapping(_mapping(_mapping(document).get('spec')).get('template')).get('spec', {})
        for container in _mapping(containers).get('containers', []):
            out: dict[str, str] = {}
            for item in _mapping(container).get('env', []) or []:
                item = _mapping(item)
                out[str(item['name'])] = str(item['value']) if 'value' in item else SECRET
            return out
    return {}


def _cloud_run_hosts(env_config: ConfigDict) -> dict[str, set[str]]:
    """Every literal Cloud Run URL host in the env, attributed to the service whose name prefixes it."""
    services = sorted(_mapping(_mapping(env_config.get('cloud_run')).get('services')), key=len, reverse=True)
    hosts: dict[str, set[str]] = {name: set() for name in services}
    for url in _urls(env_config):
        host = _host(url)
        service = _service_for_host(host, services)
        if service:
            hosts[service].add(host)
    return hosts


_CLOUD_RUN_HOST = re.compile(
    r'^(?P<prefix>[a-z0-9-]+?)-(?:[a-z0-9]{10}-[a-z]{2}\.a\.run\.app|\d+\.[a-z0-9-]+\.run\.app)$'
)


def _host(url: str) -> str:
    match = re.match(r'^https?://([^/:]+)', url.strip())
    return match.group(1) if match else ''


def _service_for_host(host: str, services: list[str]) -> str | None:
    match = _CLOUD_RUN_HOST.match(host)
    if not match:
        return None
    prefix = match.group('prefix')
    return prefix if prefix in services else None


def _urls(node: object) -> Iterator[str]:
    if isinstance(node, str):
        for match in re.finditer(r'https://[a-z0-9.-]+\.run\.app[^\s\'",]*', node):
            yield match.group(0)
    elif isinstance(node, dict):
        for value in cast(ConfigDict, node).values():
            yield from _urls(value)
    elif isinstance(node, list):
        for value in cast(list[object], node):
            yield from _urls(value)


def build_model(source: Source, env: str) -> EnvModel:
    errors: list[str] = []
    cloud_run, gke, renderer_error = _renderer_pair(source)
    if renderer_error:
        errors.append(renderer_error)
    manifest_text = source.read(MANIFEST)
    manifest = cloud_run.normalize_runtime_manifest(_mapping(_load_yaml_text(manifest_text))) if cloud_run else {}
    env_config = _mapping(_mapping(manifest.get('environments')).get(env))
    deployments: dict[str, Deployment] = {}

    state = _render_cloud_run(cloud_run, env_config, errors) if cloud_run else {}
    hosts = _cloud_run_hosts(env_config)
    for name, service in _mapping(state.get('services')).items():
        deployments[f'cloud_run/{name}'] = Deployment(
            id=f'cloud_run/{name}',
            entrypoint=BACKEND_ENTRYPOINT,
            env=_rendered_env(_mapping(service).get('env', [])),
            flags={str(k): str(v) for k, v in _mapping(_mapping(service).get('flags')).items()},
            url_hosts=tuple(sorted(hosts.get(name, ()))),
        )
    for name, job in _mapping(state.get('jobs')).items():
        deployments[f'job/{name}'] = Deployment(
            id=f'job/{name}', entrypoint=None, env=_rendered_env(_mapping(job).get('env', []))
        )

    config_map = _render_config_map(gke, env, manifest_text, env_config, errors) if gke else {}
    for name, raw in _mapping(env_config.get('gke')).items():
        if name == 'config_map':
            continue
        deployments[f'gke/{name}'] = Deployment(
            id=f'gke/{name}',
            entrypoint=GKE_ENTRYPOINTS.get(name),
            env=_gke_env(_mapping(_mapping(raw).get('env')), config_map),
        )

    for chart, entrypoint, image_set in HELM_CHARTS:
        helm_env = _helm_env(source, env, chart, image_set, errors)
        if helm_env is not None:
            deployments[f'helm/{chart}'] = Deployment(id=f'helm/{chart}', entrypoint=entrypoint, env=helm_env)

    return EnvModel(env=env, deployments=deployments, config_map=config_map, manifest=manifest, render_errors=errors)


# --------------------------------------------------------------------------------------------------
# Code readers: which process reads which env var, with which default and truthy tokens.
# --------------------------------------------------------------------------------------------------

_ENV_KEY = re.compile(r'^[A-Z][A-Z0-9_]{2,}$')


@dataclass
class EnvRead:
    defaults: set[str | None] = field(default_factory=set)
    truthy: set[str] = field(default_factory=set)
    compared: set[str] = field(default_factory=set)  # every token the code compares the value against
    modules: set[str] = field(default_factory=set)


def _literal_key(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if _ENV_KEY.match(node.value) else None
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.Attribute):
        return constants.get(node.attr)
    return None


def _is_env_call(node: ast.AST, constants: dict[str, str]) -> str | None:
    """Env key for os.getenv(K), os.environ.get(K), os.environ[K] and *env*(K) helpers; K literal or constant."""
    if isinstance(node, ast.Call) and node.args:
        key = _literal_key(node.args[0], constants)
        if key is None:
            return None
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ''
        if name == 'getenv' or (
            name == 'get'
            and isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == 'environ'
        ):
            return key
        if 'env' in name.lower():
            return key
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == 'environ':
        return _literal_key(node.slice, constants)
    return None


def _env_root(node: ast.AST, constants: dict[str, str]) -> tuple[str, ast.AST] | None:
    """Unwrap .strip()/.lower()/str() chains down to the env read."""
    current = node
    while True:
        key = _is_env_call(current, constants)
        if key:
            return key, current
        if isinstance(current, ast.Call) and isinstance(current.func, ast.Attribute):
            current = current.func.value
        elif isinstance(current, ast.Call) and isinstance(current.func, ast.Name) and current.args:
            current = current.args[0]
        else:
            return None


def _default_of(call: ast.AST) -> str | None:
    if isinstance(call, ast.Call) and len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        value = call.args[1].value
        return str(value).lower() if isinstance(value, (str, bool, int)) else None
    return None


def _module_constants(tree: ast.AST) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Constant):
            value = node.value.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if isinstance(value, str) and _ENV_KEY.match(value):
                for target in targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = value
    return constants


def _collection_members(node: ast.AST) -> tuple[str, ...] | None:
    """String members of a literal or ``frozenset/set/list/tuple(...)`` collection, else None."""
    if isinstance(node, (ast.Tuple, ast.Set, ast.List)):
        elts = node.elts
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ('frozenset', 'set', 'list', 'tuple')
    ):
        arg = node.args[0] if len(node.args) == 1 else None
        if isinstance(arg, (ast.Tuple, ast.Set, ast.List)):
            elts = arg.elts
        elif arg is None:  # empty constructor
            return ()
        else:
            return None
    else:
        return None
    members = tuple(e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return members if len(members) == len(elts) else None


def _module_collections(tree: ast.AST) -> dict[str, tuple[str, ...]]:
    """Module-level named string collections (``_TRUTHY = frozenset({...})`` and shapes like it)."""
    collections: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            members = _collection_members(node.value)  # type: ignore[arg-type]
            if members is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    collections[target.id] = members
    return collections


@dataclass
class _ModuleIndex:
    constants: dict[str, str]
    collections: dict[str, tuple[str, ...]]  # named string sets: _TRUTHY, _FALSY, mode enums
    candidates: list[ast.AST]  # the only node shapes the env-read scan inspects
    imports: list[ast.Import | ast.ImportFrom]


_INDEX_CACHE: dict[str, _ModuleIndex | None] = {}


def _index(text: str) -> _ModuleIndex | None:
    """Parse and walk each distinct module text once; three entrypoints share most of their closures."""
    if text not in _INDEX_CACHE:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            _INDEX_CACHE[text] = None
            return None
        candidates: list[ast.AST] = []
        imports: list[ast.Import | ast.ImportFrom] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
            elif isinstance(node, (ast.Call, ast.Subscript)) or (isinstance(node, ast.Compare) and len(node.ops) == 1):
                candidates.append(node)
        _INDEX_CACHE[text] = _ModuleIndex(_module_constants(tree), _module_collections(tree), candidates, imports)
    return _INDEX_CACHE[text]


def scan_env_reads(source: Source, module_paths: list[str]) -> dict[str, EnvRead]:
    indexes: dict[str, _ModuleIndex] = {}
    for rel in module_paths:
        try:
            index = _index(source.read(rel))
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        if index is not None:
            indexes[rel] = index
    shared: dict[str, str] = {}
    for index in indexes.values():
        for name, value in index.constants.items():
            shared.setdefault(name, value)  # imported constants resolve by name across the closure
    shared_collections: dict[str, tuple[str, ...]] = {}
    for index in indexes.values():
        for name, members in index.collections.items():
            shared_collections.setdefault(name, members)  # named sets (_TRUTHY et al.) resolve by name too
    reads: dict[str, EnvRead] = {}
    for rel, key, default, boolean in policy_env_reads(source, module_paths):
        read = reads.setdefault(key, EnvRead())
        read.modules.add(rel)
        read.defaults.add(default)
        if boolean:
            read.truthy.add('true')
            read.compared.add('true')
    for rel, index in indexes.items():
        constants = {**shared, **index.constants}
        collections = {**shared_collections, **index.collections}
        for node in index.candidates:
            key = _is_env_call(node, constants)
            if key:
                read = reads.setdefault(key, EnvRead())
                read.modules.add(rel)
                read.defaults.add(_default_of(node))
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                root = _env_root(node.left, constants)
                if not root:
                    continue
                comparator = node.comparators[0]
                tokens: list[str] = []
                if isinstance(node.ops[0], (ast.Eq, ast.NotEq)) and isinstance(comparator, ast.Constant):
                    tokens = [str(comparator.value)]
                elif isinstance(node.ops[0], (ast.In, ast.NotIn)):
                    members = _collection_members(comparator)
                    if members is None and isinstance(comparator, ast.Name):
                        members = collections.get(comparator.id)  # a named set such as _TRUTHY
                    if members is not None:
                        tokens = list(members)
                read = reads.setdefault(root[0], EnvRead())
                read.compared |= {t.lower() for t in tokens}
                if isinstance(node.ops[0], (ast.Eq, ast.In)):
                    read.truthy |= {t.lower() for t in tokens if t.lower() in TRUTHY}
    return reads


def import_closure(source: Source, entrypoint: str) -> list[str]:
    """First-party modules (paths under backend/) reachable from an entrypoint by static imports."""
    seen: set[str] = set()
    stack = [entrypoint]
    paths: list[str] = []
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        rel = _module_path(source, module)
        if rel is None:
            continue
        paths.append(rel)
        index = _index(source.read(rel))
        if index is None:
            continue
        package = module if rel.endswith('__init__.py') else module.rpartition('.')[0]
        for node in index.imports:
            if isinstance(node, ast.Import):
                stack.extend(alias.name for alias in node.names)
            else:
                base = node.module or ''
                if node.level:
                    parts = package.split('.') if package else []
                    parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
                    base = '.'.join([*parts, base] if base else parts)
                stack.append(base)
                stack.extend(f'{base}.{alias.name}' for alias in node.names)
    return sorted(paths)


_MODULE_CACHE: dict[tuple[str | None, str], str | None] = {}


def _module_path(source: Source, module: str) -> str | None:
    cache_key = (source.ref, module)
    if cache_key not in _MODULE_CACHE:
        rel = 'backend/' + module.replace('.', '/')
        found = None
        for candidate in (f'{rel}.py', f'{rel}/__init__.py'):
            if module and source.exists(candidate):
                found = candidate
                break
        _MODULE_CACHE[cache_key] = found
    return _MODULE_CACHE[cache_key]


@dataclass
class Readers:
    by_entrypoint: dict[str, dict[str, EnvRead]]
    all_reads: dict[str, EnvRead]


def build_readers(source: Source, entrypoints: set[str]) -> Readers:
    by_entrypoint = {entry: scan_env_reads(source, import_closure(source, entry)) for entry in sorted(entrypoints)}
    merged: dict[str, EnvRead] = {}
    for reads in by_entrypoint.values():
        for key, read in reads.items():
            target = merged.setdefault(key, EnvRead())
            target.defaults |= read.defaults
            target.truthy |= read.truthy
            target.compared |= read.compared
            target.modules |= read.modules
    return Readers(by_entrypoint=by_entrypoint, all_reads=merged)


def effective(deployment: Deployment, key: str, readers: Readers) -> str | None:
    """The value the process sees: explicit env, else the single code default, else None (unknown)."""
    if key in deployment.env:
        return deployment.env[key].strip().lower()
    reads = readers.by_entrypoint.get(deployment.entrypoint or '', {}).get(key) or readers.all_reads.get(key)
    if reads and len(reads.defaults) == 1:
        (default,) = tuple(reads.defaults)
        return '' if default is None else default
    return None


# --------------------------------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------------------------------


@dataclass
class Context:
    models: dict[str, EnvModel]
    readers: Readers
    source: Source


Check = Callable[[Context], list[Violation]]


def check_renders(ctx: Context) -> list[Violation]:
    """The deploy-time renderers succeed for every environment (Cloud Run state, ConfigMap, Helm)."""
    return [
        Violation('renders', model.env, 'render', error)
        for model in ctx.models.values()
        for error in model.render_errors
    ]


def check_config_map_sources(ctx: Context) -> list[Violation]:
    """Every gke.config_map entry declares a supported source and literal entries carry a string value (#22098)."""
    out: list[Violation] = []
    for model in ctx.models.values():
        gke = _mapping(_mapping(_mapping(model.manifest.get('environments')).get(model.env)).get('gke'))
        for key, raw in _mapping(_mapping(gke.get('config_map')).get('entries')).items():
            entry = _mapping(raw)
            source = entry.get('source')
            if source not in ('literal', 'environment'):
                out.append(Violation('config-map-source', model.env, f'gke/config_map/{key}', f'source={source!r}'))
            elif source == 'literal' and not isinstance(entry.get('value'), str):
                out.append(
                    Violation('config-map-source', model.env, f'gke/config_map/{key}', 'literal without string value')
                )
        for name, deployment in model.deployments.items():
            if name.startswith('gke/'):
                raw_env = _mapping(_mapping(gke.get(deployment.name)).get('env'))
                for key, raw in raw_env.items():
                    ref = _mapping(_mapping(raw).get('config_map'))
                    if ref and str(ref.get('key', key)) not in model.config_map and not model.render_errors:
                        out.append(
                            Violation(
                                'config-map-source',
                                model.env,
                                f'{name}/{key}',
                                'references a ConfigMap key that is not rendered',
                            )
                        )
    return out


def _resolve_target(model: EnvModel, url: str) -> Deployment | None:
    host = _host(url)
    for deployment in model.deployments.values():
        if host and host in deployment.url_hosts:
            return deployment
    return None


def _canonical_hosts(model: EnvModel) -> dict[str, str]:
    """The one host per Cloud Run service that every literal URL naming that service agrees on.

    A service's own deployment URL is authoritative: any other literal URL that shares the service-name
    prefix but disagrees on project/hash (a typo'd host) shows up as a disagreement, not a silent alias.
    """
    hosts: dict[str, str] = {}
    for deployment in model.deployments.values():
        url_hosts = deployment.url_hosts
        if deployment.kind != 'cloud_run' or len(url_hosts) != 1:
            continue  # no URL, or a disagreement the canonical-host invariant reports
        hosts[_host(next(iter(url_hosts)))] = deployment.id
    return hosts


def _check_edge_audience(
    edge: TaskEdge, deployment: Deployment, target: Deployment, env: str, scope: str, out: list[Violation]
) -> None:
    """The audience the dispatcher mints must equal the audience the target verifies (allowing documented
    ``AUDIENCE or URL`` fallbacks on either side), or every task the edge delivers is rejected 403."""
    if not edge.audience_fallback and not edge.dispatch_audience_env and not edge.verify_audience_env:
        return
    sent = (deployment.env.get(edge.dispatch_audience_env, '') if edge.dispatch_audience_env else '').strip()
    verify_key = edge.verify_audience_env or ''
    verified = (target.env.get(verify_key, '') if verify_key else '').strip()
    fallback_key = edge.verify_audience_fallback_env or edge.target_env
    fallback = (target.env.get(fallback_key, '') if fallback_key else '').strip()
    if edge.audience_fallback and not verified:
        verified = fallback  # production: AUDIENCE if set, else the handler URL
    if sent in (DYNAMIC, SECRET):
        return  # bound at deploy time; only the binding is checkable here
    if verified in (DYNAMIC, SECRET):
        return
    if not sent and not verified:
        return  # neither side configures an audience; dispatch itself is unchecked elsewhere
    if sent != verified:
        out.append(
            Violation(
                'task-edge',
                env,
                scope,
                f'dispatcher mints {edge.dispatch_audience_env}={sent!r}, '
                f'target verifies {verify_key or fallback_key}={verified!r}; every task would be rejected',
            )
        )


def check_task_edges(ctx: Context) -> list[Violation]:
    """Every enabled dispatcher has a non-empty HTTPS target that resolves to a service able to do the work:
    the right host (canonically), the right route, and an audience the target will actually verify."""
    out: list[Violation] = []
    for model in ctx.models.values():
        canonical = _canonical_hosts(model)
        for edge in TASK_EDGES:
            for deployment in model.deployments.values():
                if edge.dispatchers and deployment.id not in edge.dispatchers:
                    continue
                if deployment.kind == 'job':
                    continue
                if any(effective(deployment, k, ctx.readers) != v for k, v in edge.dispatch_when.items()):
                    continue
                scope = f'{deployment.id}->{edge.id}'
                url = deployment.env.get(edge.target_env, '').strip()
                if url == DYNAMIC or (not url and edge.empty_target_ok):
                    continue  # bound at deploy time from a GitHub variable; only the binding is checkable
                if not url.startswith('https://'):
                    out.append(
                        Violation(
                            'task-edge', model.env, scope, f'{edge.target_env} is {url!r}; dispatch cannot authenticate'
                        )
                    )
                    continue
                parsed = urlsplit(url)
                host = _host(url)
                canonical_id = canonical.get(host)
                target = _resolve_target(model, url)
                if target is None or (canonical_id is not None and canonical_id != target.id):
                    out.append(
                        Violation(
                            'task-edge',
                            model.env,
                            scope,
                            f'{edge.target_env} host {host} is not the canonical host of a service in {model.env}',
                        )
                    )
                    continue
                if edge.append_route:
                    # The dispatcher joins its RPC path onto the URL: a path here would produce a doubled path.
                    if parsed.path not in ('', '/'):
                        out.append(
                            Violation(
                                'task-edge',
                                model.env,
                                scope,
                                f'{edge.target_env} must be a bare origin; production appends {edge.route!r}',
                            )
                        )
                        continue
                    if parsed.query or parsed.fragment:
                        out.append(
                            Violation(
                                'task-edge',
                                model.env,
                                scope,
                                f'{edge.target_env} must be a bare origin (no query/fragment)',
                            )
                        )
                        continue
                elif parsed.path.rstrip('/') != edge.route.rstrip('/'):
                    out.append(
                        Violation(
                            'task-edge',
                            model.env,
                            scope,
                            f'{edge.target_env} path {parsed.path!r} is not the handler route {edge.route!r}',
                        )
                    )
                    continue
                for key, want in edge.handler_requires.items():
                    got = effective(target, key, ctx.readers)
                    if got != want:
                        out.append(
                            Violation(
                                'task-edge',
                                model.env,
                                scope,
                                f'target {target.id} has {key}={got!r}, handler needs {want!r}',
                            )
                        )
                _check_edge_audience(edge, deployment, target, model.env, scope, out)
                if edge.deadline_seconds and target.kind == 'cloud_run':
                    timeout = _seconds(target.flags.get('--timeout'))
                    if timeout is None:
                        out.append(
                            Violation(
                                'handler-timeout',
                                model.env,
                                f'{target.id}:{edge.id}',
                                f'--timeout undeclared; needs ≥ {edge.deadline_seconds}s',
                            )
                        )
                    elif timeout < edge.deadline_seconds:
                        out.append(
                            Violation(
                                'handler-timeout',
                                model.env,
                                f'{target.id}:{edge.id}',
                                f'--timeout {timeout}s < dispatch deadline {edge.deadline_seconds}s',
                            )
                        )
    return _dedupe(out)


def check_canonical_hosts(ctx: Context) -> list[Violation]:
    """Each Cloud Run service has one canonical host: every literal URL naming the service agrees on it.

    Service identity comes from the service's own deployment URL, not from the target URL being validated —
    otherwise a typo'd project/hash that still starts with the service name would validate itself.
    """
    out: list[Violation] = []
    for model in ctx.models.values():
        env_config = _mapping(_mapping(model.manifest.get('environments')).get(model.env))
        services = sorted(_mapping(_mapping(env_config.get('cloud_run')).get('services')))
        disagreements: dict[str, set[str]] = {name: set() for name in services}
        for url in _urls(env_config):
            host = _host(url)
            service = _service_for_host(host, services)
            if service:
                disagreements[service].add(host)
        for service, hosts in disagreements.items():
            if len(hosts) > 1:
                rendered = ', '.join(sorted(hosts))
                out.append(
                    Violation(
                        'canonical-host', model.env, f'cloud_run/{service}', f'URLs disagree on the host: {rendered}'
                    )
                )
    return out


def check_edges_declared(ctx: Context) -> list[Violation]:
    """Each task edge's dispatch mode is declared somewhere; otherwise it lives only on the running service and
    neither this suite nor a reviewer can see whether (or where) the hop is enabled."""
    out: list[Violation] = []
    for model in ctx.models.values():
        for edge in TASK_EDGES:
            for key, want in edge.dispatch_when.items():
                defaults = (ctx.readers.all_reads.get(key) or EnvRead()).defaults
                if defaults == {want}:
                    continue  # ship-on default: unset already dispatches
                if not any(key in d.env for d in model.deployments.values()):
                    out.append(
                        Violation(
                            'edge-declared',
                            model.env,
                            f'{edge.id}/{key}',
                            'not declared on any deployment; live-only value',
                        )
                    )
    return out


def _seconds(raw: str | None) -> int | None:
    if not raw:
        return None
    match = re.match(r'^(\d+)s?$', raw.strip())
    return int(match.group(1)) if match else None


def check_coupled_flags(ctx: Context) -> list[Violation]:
    """Flags that steer shared durable state agree on every deployment that runs them (#22121)."""
    out: list[Violation] = []
    for model in ctx.models.values():
        for key, ids in COUPLED_FLAGS:
            present = [model.deployments[i] for i in ids if i in model.deployments]
            values = {d.id: effective(d, key, ctx.readers) for d in present}
            if len(set(values.values())) > 1:
                rendered = ', '.join(f'{k}={v!r}' for k, v in values.items())
                out.append(Violation('coupled-flag', model.env, key, f'split: {rendered}'))
    return out


def check_reader_split(ctx: Context) -> list[Violation]:
    """A flag a non-backend process reads must not silently fall back to its default while every backend host
    that sets it agrees on a different value (the generalized #22121: new flag flipped where it is declared,
    never set on the separately deployed worker that also reads it)."""
    out: list[Violation] = []
    for model in ctx.models.values():
        backend = [d for d in model.deployments.values() if d.entrypoint == BACKEND_ENTRYPOINT]
        for process in model.deployments.values():
            prefixes = READER_SPLIT_SCOPES.get(process.id)
            if not prefixes or process.entrypoint in (None, BACKEND_ENTRYPOINT):
                continue
            reads = ctx.readers.by_entrypoint.get(process.entrypoint, {})
            for key in sorted(reads):
                if key in process.env or not key.startswith(prefixes):
                    continue
                declared = {d.env[key].strip().lower() for d in backend if key in d.env}
                default = effective(process, key, ctx.readers)
                if (
                    len(declared) == 1
                    and default is not None
                    and default not in declared
                    and DYNAMIC.lower() not in declared
                ):
                    (fleet,) = tuple(declared)
                    if fleet in (SECRET, ''):
                        continue
                    out.append(
                        Violation(
                            'reader-split',
                            model.env,
                            f'{process.id}/{key}',
                            f'unset (code default {default!r}) while every backend host sets {fleet!r}',
                        )
                    )
    return out


def check_boolean_tokens(ctx: Context) -> list[Violation]:
    """A flag the code compares against a truthy token is only ever deployed as a value the code understands."""
    out: list[Violation] = []
    for model in ctx.models.values():
        for deployment in model.deployments.values():
            for key, value in deployment.env.items():
                read = ctx.readers.all_reads.get(key)
                if not read or not read.truthy or value in (DYNAMIC, SECRET):
                    continue
                if read.compared - TRUTHY - FALSY:
                    continue  # a mode enum (off/shadow/on), not a boolean
                token = value.strip().lower()
                if token not in read.truthy and token not in FALSY:
                    out.append(
                        Violation(
                            'boolean-token',
                            model.env,
                            f'{deployment.id}/{key}',
                            f'{value!r} is read as false (code accepts {sorted(read.truthy)})',
                        )
                    )
    return out


def check_kill_switches(ctx: Context) -> list[Violation]:
    """Declared ops kill switches are read by code; a missing reader means flipping it off does nothing."""
    out: list[Violation] = []
    for model in ctx.models.values():
        environment = _mapping(_mapping(model.manifest.get('environments')).get(model.env))
        hosts = {
            **{
                f'cloud_run/{k}': v for k, v in _mapping(_mapping(environment.get('cloud_run')).get('services')).items()
            },
            **{f'gke/{k}': v for k, v in _mapping(environment.get('gke')).items() if k != 'config_map'},
        }
        for host, raw in hosts.items():
            for key, entry in _mapping(_mapping(raw).get('env')).items():
                if _mapping(entry).get('category') == 'ops_kill' and key not in ctx.readers.all_reads:
                    out.append(
                        Violation(
                            'kill-switch-reader', model.env, f'{host}/{key}', 'no code path reads this kill switch'
                        )
                    )
    return out


def check_no_uid_literals(ctx: Context) -> list[Violation]:
    """No user identifiers in the public manifest or chart values (cohorts belong in Firestore/secrets)."""
    out: list[Violation] = []
    for model in ctx.models.values():
        for deployment in model.deployments.values():
            for key, value in deployment.env.items():
                if UID_KEY_PATTERN.search(key) and FIREBASE_UID_PATTERN.search(value):
                    count = len(FIREBASE_UID_PATTERN.findall(value))
                    out.append(
                        Violation(
                            'no-uid-literals',
                            model.env,
                            f'{deployment.id}/{key}',
                            f'{count} UID-shaped literal(s)',
                            fingerprint=f'uids={count}',  # appending to an accepted cohort must not stay "known"
                        )
                    )
    return _dedupe(out)


def check_cross_env_urls(ctx: Context) -> list[Violation]:
    """A Cloud Run URL host belongs to exactly one environment; a prod host in dev (or vice versa) crosses data planes."""
    hosts_by_env = {
        env: {_host(u) for u in _urls(_mapping(_mapping(m.manifest.get('environments')).get(env)))}
        for env, m in ctx.models.items()
    }
    out: list[Violation] = []
    envs = sorted(hosts_by_env)
    for i, left in enumerate(envs):
        for right in envs[i + 1 :]:
            for host in sorted(hosts_by_env[left] & hosts_by_env[right]):
                out.append(
                    Violation('cross-env-url', f'{left}+{right}', host, 'Cloud Run host appears in both environments')
                )
    return out


def _dedupe(violations: list[Violation]) -> list[Violation]:
    seen: dict[str, Violation] = {}
    for violation in violations:
        seen.setdefault(f'{violation.key}|{violation.message}', violation)
    return list(seen.values())


def _lane_check(module: str, function: str) -> Check:
    """A check whose body lives in ``scripts/cross_service_checks/<module>.py`` (owned by another swarm lane).

    Imported lazily so the module can import this one. Until the module lands, the check contributes nothing;
    once it exists, a missing function is an error, never a silent skip.
    """

    def run(ctx: Context) -> list[Violation]:
        import importlib

        name = f'scripts.cross_service_checks.{module}'
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            return []
        return getattr(mod, function)(ctx)

    run.__name__ = f'{module}.{function}'
    return run


INVARIANTS: tuple[tuple[str, Check], ...] = (
    ('renders', check_renders),
    ('config-map-source', check_config_map_sources),
    ('task-edge', check_task_edges),
    ('canonical-host', check_canonical_hosts),
    ('edge-declared', check_edges_declared),
    ('coupled-flag', check_coupled_flags),
    ('reader-split', check_reader_split),
    ('boolean-token', check_boolean_tokens),
    ('kill-switch-reader', check_kill_switches),
    ('no-uid-literals', check_no_uid_literals),
    ('cross-env-url', check_cross_env_urls),
    ('task-target-retry-semantics', _lane_check('task_targets', 'check_task_target_retry_semantics')),  # lane 4
    ('staging-mirrors-prod', _lane_check('staging', 'check_staging_mirrors_prod')),  # lane 2
)


def build_context(source: Source, envs: tuple[str, ...] = ENVS, readers: Readers | None = None) -> Context:
    """``readers`` may be reused across manifest-only variations; code readers depend on source, not config."""
    models = {env: build_model(source, env) for env in envs}
    if readers is None:
        entrypoints = {d.entrypoint for m in models.values() for d in m.deployments.values() if d.entrypoint}
        readers = build_readers(source, entrypoints)
    return Context(models=models, readers=readers, source=source)


def evaluate(ctx: Context) -> list[Violation]:
    violations: list[Violation] = []
    for _, check in INVARIANTS:
        violations.extend(check(ctx))
    return violations


# --------------------------------------------------------------------------------------------------
# Known gaps: a ratchet. Entries must still occur (stale entries fail) and new violations fail.
# --------------------------------------------------------------------------------------------------

KNOWN_GAPS_PATH = BACKEND / 'deploy' / 'cross_service_known_gaps.json'


def load_known_gaps(path: Path = KNOWN_GAPS_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    return {str(entry['key']): str(entry['why']) for entry in data.get('gaps', [])}


def partition(violations: list[Violation], gaps: dict[str, str]) -> tuple[list[Violation], list[Violation], list[str]]:
    """(new violations, accepted known gaps, stale gap keys)."""
    keys = {v.key for v in violations}
    new = [v for v in violations if v.key not in gaps]
    known = [v for v in violations if v.key in gaps]
    stale = sorted(k for k in gaps if k not in keys)
    return new, known, stale


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n\n')[0])
    parser.add_argument('--ref', help='evaluate the manifest, charts and code at this git ref')
    parser.add_argument('--env', choices=ENVS, action='append')
    parser.add_argument('--all', action='store_true', help='print accepted known gaps too')
    args = parser.parse_args()
    source = Source(ref=args.ref)
    try:
        ctx = build_context(source, tuple(args.env or ENVS))
        violations = evaluate(ctx)
    finally:
        source.close()
    new, known, stale = partition(violations, load_known_gaps())
    if shutil.which('helm') is None:
        print('note: helm unavailable; chart-rendered deployments skipped', file=sys.stderr)
    for violation in new:
        print(f'FAIL {violation}')
    if args.all:
        for violation in known:
            print(f'GAP  {violation}')
    for key in stale if not args.ref else []:
        print(f'note: known gap no longer occurs (delete it from {KNOWN_GAPS_PATH.name}): {key}')
    print(f'{len(new)} new violation(s), {len(known)} known gap(s), {len(stale)} stale gap(s)')
    # Stale gaps never fail: a fix landing elsewhere (e.g. a rollout PR) must not be blocked by this ratchet.
    return 1 if new else 0


if __name__ == '__main__':
    raise SystemExit(main())
