#!/usr/bin/env python3
"""Live config drift check: live against source, and live staging against live prod.

Lessons 7-9 (batch-rollout-and-staging-traps): staging drifted from prod with no source diff
showing it (the batch serving leader at min-instances 0, recovery off, backfill on the wrong task
audience), and prod carries live-only settings that a deploy from source would drop. The
``staging-mirrors-prod`` invariant compares composed *source*; this compares what actually serves.

Three subcommands:

  snapshot         read live state with gcloud/kubectl and write a redacted snapshot file;
  source           snapshot vs source (composed runtime env, deploy flags, the ops file, Helm values),
                   with ``deploy/ops/live_only.yaml`` as a ratchet of reviewed prod live-only keys;
  staging-vs-prod  staging snapshot vs prod snapshot, with reviewed allowlists, self-referential
                   URL/audience topology, scale rules, and (``--ramp-env``) each side's ramp position.

Run a snapshot on an agent tier (``ro-prod``, ``ro-dev``); ``--k8s`` needs a copied KUBECONFIG and
an explicit ``--kube-context``. Example::

  drift_check.py snapshot --project based-hardware --service backend-integration --out prod.json
  drift_check.py source --env prod --live prod.json --ramp-env <omi-workspace>/infra/rollout/ramp_env.json

Comparisons read snapshot files only, so they run offline. Snapshots never hold a sensitive value:
secret bindings keep their presence, and sensitive or secret-looking plain values keep a short
digest. Output names services, keys and finding kinds; it prints a value only when it is a plain
flag or number. Exit 1 on any unexplained difference.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

import yaml

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
SNAPSHOT_SCHEMA = 'omi.drift-snapshot/v1'
STAGING_SUFFIX = '-staging'
LISTEN = 'backend-listen'

# Matched per underscore segment, so ASSIGNMENT is not SIGN and KEYBOARD is not KEY.
SENSITIVE_SEGMENTS = frozenset(
    'KEY KEYS APIKEY SECRET SECRETS TOKEN TOKENS PASSWORD PASSWD CREDENTIAL CREDENTIALS PRIVATE UID UIDS '
    'EMAIL EMAILS ALLOWLIST COHORT DSN WEBHOOK SALT SIGNER SIGNING CERT SID'.split()
)
# A long opaque run looks like a UID, key or token even under an innocent name.
SECRET_LOOKING_VALUE = re.compile(r'[A-Za-z0-9_+=-]{24,}')
PRINTABLE_VALUE = re.compile(r'^(|true|false|on|off|-?\d+(\.\d+)?[a-zA-Z]{0,3}|[a-z][a-z0-9_-]{0,23})$')

# Keys the deploy itself stamps on every revision; they are expected to be live-only and to differ.
DEPLOY_STAMPED = ('OMI_BACKEND_RELEASE_SHA', 'OMI_RELEASE_TREE')

# Live-managed keys that must never live in the public repo (UID cohorts). They persist across trains
# because deploy-cloudrun merges env; note them, do not fail on them.
LIVE_MANAGED: tuple[str, ...] = (
    '*_UID_ALLOWLIST',
    '*_UIDS',
)

# staging-vs-prod: env keys whose *value* may differ, with the reason. Self-referential URLs and
# audiences are value-allowlisted but still checked for *which* service they point at
# (``_self_reference``), which is how the wrong backfill audience is caught.
LIVE_DIFF_ALLOWLIST: dict[str, str] = {
    'OMI_BACKEND_RELEASE_SHA': 'deploy-stamped release identity',
    'OMI_RELEASE_TREE': 'deploy-stamped release identity',
    '*_UID_ALLOWLIST': 'prod-only UID cohort; staging has no prod users',
    '*_UIDS': 'prod-only UID cohort; staging has no prod users',
    'BATCH_PIPELINE_SHADOW_*': 'prod shadow sampling; staging has no prod traffic to shadow',
    'FIRESTORE_READ_LEVERS': 'the AVO Firestore-reads loop ramps prod levers; staging takes them at its next deploy',
}
# Present on only one side without failing (names, with the reason).
LIVE_ONE_SIDED_ALLOWLIST: dict[str, str] = {
    'OMI_RELEASE_TREE': 'staging deploy.sh stamps it; the prod train does not yet (B7)',
    'OMI_BACKEND_RELEASE_SHA': 'staging stamps every service; the prod train stamps backend only (B7)',
    '*_UID_ALLOWLIST': 'prod-only UID cohort',
    '*_UIDS': 'prod-only UID cohort',
    'BATCH_JOBSTORE_MODE': 'A2 job-store shadow is staging-only',
    'JOBSTORE_*': 'A2 job-store shadow is staging-only',
    'OMI_DEPLOYMENT': 'staging identity',
}
# staging-vs-prod scale rules. Staging is prod-shaped, not prod-sized: it idles at min 0 by design
# (staging.overlay.yaml scale_flags). The 2026-10-24 right-sizing retired the warm-exception for
# backend-integration (lesson 8, #22757): staging's serving leader may idle even while prod stays
# warm; a replay window warms it with --warm. Min and max never exceed prod's. cpu, memory and
# concurrency are equal, so per-instance behaviour matches.
EQUAL_SCALE_FIELDS = ('cpu', 'memory', 'concurrency')
# Listen env whose prod values come from the LISTEN_PRIVATE_VALUES_YAML secret (#22763 privateEnv),
# so source states presence only.
LISTEN_PRIVATE_ENV = ('STT_CAP_DISPATCH_ENFORCEMENT', 'STT_CAP_DISPATCH_COHORT', 'STT_CAP_DISPATCH_LANES')
# Ramp position: staging sits on prod's set, or ahead of it on the full-ramp set it proves (plan §1).
STAGING_AHEAD_SET = '100_percent'


@dataclass(frozen=True)
class Finding:
    service: str
    key: str
    kind: str
    explained: str = ''  # non-empty: the reason it does not fail (class c or reviewed allowlist)

    def line(self) -> str:
        tail = f'  [{self.explained}]' if self.explained else ''
        return f'{self.service}/{self.key}: {self.kind}{tail}'


# ------------------------------------------------------------------------------------------------
# Redaction
# ------------------------------------------------------------------------------------------------


def sensitive(name: str, value: str) -> bool:
    if SENSITIVE_SEGMENTS.intersection(name.upper().split('_')):
        return True
    url = urlparse(value) if '://' in value else None
    if url is not None and url.hostname:
        # Hosts (run.app names are long) stay readable for the self-reference check. Any userinfo
        # or query redacts the whole value; a path redacts it when it holds a token-like run.
        if url.username or url.password or url.query or url.fragment:
            return True
        value = url.path
    return bool(SECRET_LOOKING_VALUE.search(value))


def plain(name: str, value: str) -> dict[str, str]:
    """The redacted form of one plain value, comparable with snapshot entries."""
    return redact_env([{'name': name, 'value': value}])[name]


def _digest(value: str) -> str:
    return 'sha256:' + hashlib.sha256(value.encode()).hexdigest()[:16]


def redact_env(entries: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """``{name: {'value': v} | {'digest': d} | {'secret': ref} | {'from': kind}}``; raw values never survive."""
    out: dict[str, dict[str, str]] = {}
    for entry in entries:
        name = entry.get('name')
        if not isinstance(name, str) or not name:
            continue
        if 'valueFrom' not in entry:  # Cloud Run omits ``value`` when it is the empty string
            value = str(entry.get('value') or '')
            out[name] = {'digest': _digest(value)} if sensitive(name, value) else {'value': value}
            continue
        source = entry.get('valueFrom') or {}
        ref = source.get('secretKeyRef')
        if ref:
            out[name] = {'secret': str(ref.get('name') or ref.get('key') or '')}
        else:
            out[name] = {'from': next(iter(source), 'unknown')}
    return out


def printable(name: str, entry: Mapping[str, str] | None) -> str:
    """A value fit for a report: plain flags and numbers only."""
    if entry is None:
        return '<absent>'
    if 'value' in entry and not sensitive(name, entry['value']) and PRINTABLE_VALUE.match(entry['value']):
        return entry['value'] or "''"
    return '<' + next(iter(entry)) + '>'


# ------------------------------------------------------------------------------------------------
# Snapshot (live reads; the only code that touches gcloud/kubectl)
# ------------------------------------------------------------------------------------------------


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


_QUANTITY = re.compile(r'^(\d+(?:\.\d+)?)(m|Ki|Mi|Gi|Ti|k|M|G)?$')
_UNITS = {None: 1, 'm': 0.001, 'k': 1e3, 'M': 1e6, 'G': 1e9, 'Ki': 2**10, 'Mi': 2**20, 'Gi': 2**30, 'Ti': 2**40}


def quantity(value: Any) -> str | None:
    """Kubernetes/Cloud Run quantity in base units, so ``2000m`` == ``2`` and ``3584Mi`` == ``3.5Gi``."""
    if value is None:
        return None
    match = _QUANTITY.match(str(value))
    if not match:
        return str(value)
    return f'{float(match.group(1)) * _UNITS[match.group(2)]:g}'


def normalize_cloud_run(service_doc: Mapping[str, Any], revision_doc: Mapping[str, Any]) -> dict[str, Any]:
    """One Cloud Run service: the serving revision's app container plus service-level scale."""
    meta = service_doc.get('metadata') or {}
    annotations = meta.get('annotations') or {}
    rev_meta = revision_doc.get('metadata') or {}
    rev_annotations = rev_meta.get('annotations') or {}
    rev_spec = revision_doc.get('spec') or {}
    containers = rev_spec.get('containers') or [{}]
    # The ingress container carries the ports; sidecars (the GMP collector) have none.
    app = next((c for c in containers if c.get('ports')), containers[0])
    limits = (app.get('resources') or {}).get('limits') or {}
    status = service_doc.get('status') or {}
    try:
        urls = json.loads(annotations.get('run.googleapis.com/urls') or '[]')
    except json.JSONDecodeError:
        urls = []
    return {
        'revision': rev_meta.get('name'),
        'urls': sorted({*urls, *([status['url']] if status.get('url') else [])}),
        'env': redact_env(app.get('env') or []),
        'scale': {
            'service_min': _int_or_none(annotations.get('run.googleapis.com/minScale')),
            'service_max': _int_or_none(annotations.get('run.googleapis.com/maxScale')),
            'revision_min': _int_or_none(rev_annotations.get('autoscaling.knative.dev/minScale')),
            'revision_max': _int_or_none(rev_annotations.get('autoscaling.knative.dev/maxScale')),
            'concurrency': _int_or_none(rev_spec.get('containerConcurrency')),
            'cpu': str(limits.get('cpu')) if limits.get('cpu') is not None else None,
            'memory': limits.get('memory'),
        },
    }


def k8s_container(deployment: Mapping[str, Any], container: str) -> Mapping[str, Any]:
    spec = ((deployment.get('spec') or {}).get('template') or {}).get('spec') or {}
    containers = spec.get('containers') or [{}]
    return next((c for c in containers if c.get('name') == container), containers[0])


def normalize_k8s(
    deployment: Mapping[str, Any],
    hpa: Mapping[str, Any] | None,
    container: str,
    config_maps: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """``config_maps`` are the envFrom ConfigMaps; only their key names are kept."""
    app = k8s_container(deployment, container)
    hpa_spec = (hpa or {}).get('spec') or {}
    limits = (app.get('resources') or {}).get('limits') or {}
    env: dict[str, dict[str, str]] = {}
    for name, config_map in (config_maps or {}).items():
        env.update({key: {'from': f'configMap:{name}'} for key in (config_map.get('data') or {})})
    env.update(redact_env(app.get('env') or []))  # explicit env wins over envFrom
    return {
        'revision': ((deployment.get('metadata') or {}).get('annotations') or {}).get(
            'deployment.kubernetes.io/revision'
        ),
        'urls': [],
        'env': env,
        'scale': {
            'service_min': _int_or_none(hpa_spec.get('minReplicas')),
            'service_max': _int_or_none(hpa_spec.get('maxReplicas')),
            'revision_min': None,
            'revision_max': None,
            'concurrency': None,
            'cpu': str(limits.get('cpu')) if limits.get('cpu') is not None else None,
            'memory': limits.get('memory'),
        },
    }


def serving_revision(service_doc: Mapping[str, Any]) -> str:
    """The revision serving the most traffic (fails closed on an unreadable status)."""
    traffic = [t for t in (service_doc.get('status') or {}).get('traffic') or [] if t.get('percent')]
    if not traffic:
        raise ValueError('no revision is serving traffic')
    return str(max(traffic, key=lambda t: t['percent'])['revisionName'])


def _run_json(args: list[str]) -> Any:
    done = subprocess.run(args, check=True, text=True, capture_output=True)
    return json.loads(done.stdout)


def take_snapshot(
    *,
    project: str,
    region: str,
    services: Iterable[str],
    k8s: Iterable[str] = (),
    kube_context: str | None = None,
    read: Callable[[list[str]], Any] = _run_json,
) -> dict[str, Any]:
    """``k8s`` items are ``namespace/deployment:container``; HPA shares the deployment name."""
    out: dict[str, Any] = {'schema': SNAPSHOT_SCHEMA, 'project': project, 'services': {}}
    loc = [f'--project={project}', f'--region={region}', '--format=json']
    for name in services:
        svc = read(['gcloud', 'run', 'services', 'describe', name, *loc])
        rev = read(['gcloud', 'run', 'revisions', 'describe', serving_revision(svc), *loc])
        out['services'][name] = normalize_cloud_run(svc, rev)
    for item in k8s:
        if not kube_context:
            raise ValueError('k8s snapshots need an explicit --kube-context')
        target, _, container = item.partition(':')
        namespace, _, deployment = target.partition('/')
        base = ['kubectl', '--context', kube_context, '-n', namespace, 'get']
        dep = read([*base, 'deployment', deployment, '-o', 'json'])
        try:
            hpa = read([*base, 'hpa', deployment, '-o', 'json'])
        except subprocess.CalledProcessError:
            hpa = None
        refs = [
            e['configMapRef']['name']
            for e in k8s_container(dep, container).get('envFrom') or []
            if e.get('configMapRef')
        ]
        config_maps = {ref: read([*base, 'configmap', ref, '-o', 'json']) for ref in refs}
        out['services'][container or deployment] = normalize_k8s(dep, hpa, container or deployment, config_maps)
    return out


def load_snapshot(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != SNAPSHOT_SCHEMA:
        raise ValueError(f'{path}: not a {SNAPSHOT_SCHEMA} snapshot')
    return data


# ------------------------------------------------------------------------------------------------
# Source model: what a deploy from this tree would put on each service
# ------------------------------------------------------------------------------------------------


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STAGING_INPUT_PLACEHOLDER = '10.0.0.1'  # compose_staging needs a private address; deploy.sh supplies the real one


def _source_env(entries: Mapping[str, Any], secrets: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for name, entry in (entries or {}).items():
        if isinstance(entry, dict) and str(entry.get('value')) == STAGING_INPUT_PLACEHOLDER:
            out[name] = {'from': 'deploy-input'}
        elif isinstance(entry, dict) and 'value' in entry:
            out[name] = plain(name, str(entry['value']))
        elif isinstance(entry, dict) and 'secret' in entry:
            out[name] = {'secret': ''}
        elif isinstance(entry, dict) and ('provisional' in entry or 'default' in entry):
            out[name] = {'from': 'optional-deploy-input'}  # the deploy omits it when the input is unset
        else:
            out[name] = {'from': 'deploy-input'}  # env_var/config_map: supplied at deploy time
    for name in secrets or {}:
        out[str(name)] = {'secret': ''}
    return out


_FLAG = re.compile(r'--(min-instances|max-instances|max|min|concurrency|cpu|memory)=([^\s$]+)(?=\s|$)')

# Prod-scoping conditionals used by the deploy actions (runtime_env == 'prod',
# project_id == 'based-hardware') resolve to their prod branch here: this model is
# the prod declaration. Dev takes the || branch and never reaches this parser.
_PROD_BRANCH = re.compile(
    r"\$\{\{\s*inputs\.(?:runtime_env == 'prod'|project_id == 'based-hardware')" r" && '([^']*)' \|\| '([^']*)'\s*\}\}"
)
_INPUT_REF = re.compile(r'\$\{\{\s*inputs\.(\w+)\s*\}\}')
# Manual-workflow `with:` entries scoped by deploy environment resolve to their prod branch.
_WORKFLOW_ENV_SCOPED = re.compile(
    r"^\$\{\{\s*vars\.\w+\s*\|\|\s*\(github\.event\.inputs\.environment == 'prod' && '([^']*)' \|\| '([^']*)'\)\s*\}\}$"
)


def workflow_input_values(path: Path) -> dict[str, str]:
    """Prod-branch values for deploy-backend-stack inputs the manual workflow scopes by deploy
    environment (`vars.X || (environment == 'prod' && 'A' || 'B')`). A set `vars.X` overrides live;
    the source model stays the source-declared fallback, so an override shows as drift."""
    doc = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    out: dict[str, str] = {}
    for job in (doc.get('jobs') or {}).values():
        for step in (job or {}).get('steps') or []:
            if not str((step or {}).get('uses', '')).endswith('/deploy-backend-stack'):
                continue
            for name, value in ((step or {}).get('with') or {}).items():
                m = _WORKFLOW_ENV_SCOPED.match(str(value))
                if m:
                    out[str(name)] = m.group(1)
    return out


def deploy_action_flags(
    paths: Iterable[Path], input_values: Mapping[str, str] | None = None
) -> dict[str, dict[str, str]]:
    """Literal scale flags per service from the deploy-cloudrun steps of the prod deploy actions."""
    resolved = dict(input_values or {})
    out: dict[str, dict[str, str]] = {}
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        for step in (doc.get('runs') or {}).get('steps') or []:
            if not str(step.get('uses', '')).startswith('google-github-actions/deploy-cloudrun'):
                continue
            with_ = step.get('with') or {}
            service = str(with_.get('service', '')).replace('${{ inputs.service }}', 'backend')
            flags = out.setdefault(service, {})
            flag_text = _PROD_BRANCH.sub(r'\1', str(with_.get('flags', '')))
            flag_text = _INPUT_REF.sub(lambda m: resolved.get(m.group(1), m.group(0)), flag_text)
            for flag, value in _FLAG.findall(flag_text):
                flags[flag] = value
    return out


_DEPLOY_SH_CASE = re.compile(r'^\s*([a-z-]+)\)\s*echo\s+"([^"]*)"\s*;;', re.MULTILINE)


def staging_deploy_flags(path: Path) -> dict[str, dict[str, str]]:
    """Per-service flags from ``deploy/staging/deploy.sh``'s case table."""
    out: dict[str, dict[str, str]] = {}
    for service, flags in _DEPLOY_SH_CASE.findall(path.read_text(encoding='utf-8')):
        out[service] = dict(_FLAG.findall(flags + ' '))
    return out


def _flag_scale(flags: Mapping[str, str]) -> dict[str, Any]:
    return {
        'revision_min': _int_or_none(flags.get('min-instances')),
        'revision_max': _int_or_none(flags.get('max-instances')),
        'service_min': _int_or_none(flags.get('min')),
        'service_max': _int_or_none(flags.get('max')),
        'concurrency': _int_or_none(flags.get('concurrency')),
        'cpu': flags.get('cpu'),
        'memory': flags.get('memory'),
    }


def listen_values(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    doc = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    env: dict[str, dict[str, str]] = {}
    for entry in doc.get('env') or []:
        if 'value' in entry:
            env[entry['name']] = plain(entry['name'], str(entry['value']))
        else:
            env.update(redact_env([entry]))
    for name in [*(doc.get('privateEnv') or {}), *LISTEN_PRIVATE_ENV]:
        env[str(name)] = {'from': 'private-values'}
    autoscaling = doc.get('autoscaling') or {}
    limits = (doc.get('resources') or {}).get('limits') or {}
    scale = {
        'service_min': _int_or_none(autoscaling.get('minReplicas')),
        'service_max': _int_or_none(autoscaling.get('maxReplicas')),
        'cpu': str(limits['cpu']) if 'cpu' in limits else None,
        'memory': limits.get('memory'),
    }
    return env, scale


@dataclass
class SourceService:
    env: dict[str, dict[str, str]]
    scale: dict[str, Any]  # None = not managed by source (inherits live)
    ops_env: dict[str, str]
    ops_scale: dict[str, Any]  # service_min / service_max (int or {'floor','ceiling'})


def source_model(environment: str, root: Path = ROOT) -> dict[str, SourceService]:
    """What a deploy from ``root`` would set, per service (unsuffixed names)."""
    backend = root / 'backend'
    runtime_env_dir = backend / 'deploy' / 'runtime_env'
    composer = _load_module('_drift_compose_runtime_env', backend / 'deploy' / 'compose_runtime_env.py')
    if environment == 'staging':
        composed = composer.compose_staging(
            base_path=runtime_env_dir / '_base.yaml',
            runtime_env_dir=runtime_env_dir,
            inputs={'STAGING_REDIS_HOST': STAGING_INPUT_PLACEHOLDER},
        )
        flags = staging_deploy_flags(backend / 'deploy' / 'staging' / 'deploy.sh')
    else:
        composed = composer.compose_environment(
            environment, base_path=runtime_env_dir / '_base.yaml', runtime_env_dir=runtime_env_dir
        )
        actions = root / '.github' / 'actions'
        # The manual workflow scopes some action inputs by deploy environment; the prod model
        # takes their prod branch (e.g. backend-sync memory) so the fallback stays drift-checked.
        input_values = workflow_input_values(root / '.github' / 'workflows' / 'gcp_backend.yml')
        flags = deploy_action_flags(
            [actions / 'deploy-backend-stack' / 'action.yml', actions / 'sync-backfill-lifecycle' / 'action.yml'],
            input_values=input_values,
        )
    ops = yaml.safe_load((backend / 'deploy' / 'ops' / f'{environment}.yaml').read_text(encoding='utf-8'))
    ops_services = {_base_name(name): cfg or {} for name, cfg in ((ops or {}).get('cloud_run') or {}).items()}

    out: dict[str, SourceService] = {}
    for name, cfg in ((composed.get('cloud_run') or {}).get('services') or {}).items():
        op = ops_services.get(name, {})
        # Composed flags (staging's overlay scale_flags) first; deploy-script literals override.
        composed_flags = dict(_FLAG.findall(' '.join(f'{k}={v}' for k, v in (cfg.get('flags') or {}).items()) + ' '))
        out[name] = SourceService(
            env=_source_env(cfg.get('env') or {}, cfg.get('secrets') or {}),
            scale=_flag_scale({**composed_flags, **flags.get(name, {})}),
            ops_env={k: str(v) for k, v in (op.get('env') or {}).items()},
            ops_scale={'service_min': op.get('min_instances'), 'service_max': op.get('max_instances')},
        )
    if environment == 'prod':
        gke = (composed.get('gke') or {}).get(LISTEN) or {}
        env = _source_env(gke.get('env') or {}, gke.get('secrets') or {})
        values_env, scale = listen_values(backend / 'charts' / LISTEN / 'prod_omi_backend_listen_values.yaml')
        env.update(values_env)
        out[LISTEN] = SourceService(env=env, scale=scale, ops_env={}, ops_scale={})
    return out


def ramp_keys(path: Path | None) -> dict[str, set[str]]:
    """Keys ``ramp_env.json`` owns per service (any set), keyed by unsuffixed service name."""
    if path is None:
        return {}
    out: dict[str, set[str]] = {}
    for sets in json.loads(path.read_text(encoding='utf-8')).values():
        for target, keys in sets.items():
            kind, _, rest = target.partition('/')
            name = rest.rsplit('/', 1)[-1].split(':')[0] if kind == 'gke' else rest
            out.setdefault(name, set()).update(keys)
    return out


# ------------------------------------------------------------------------------------------------
# Comparisons
# ------------------------------------------------------------------------------------------------


def _base_name(name: str) -> str:
    return name[: -len(STAGING_SUFFIX)] if name.endswith(STAGING_SUFFIX) else name


def _matches(name: str, patterns: Iterable[str]) -> str | None:
    return next((p for p in patterns if fnmatch.fnmatchcase(name, p)), None)


def _same(a: Mapping[str, str], b: Mapping[str, str]) -> bool:
    """Equal by value or digest; two secret bindings match on presence (names differ by environment)."""
    if 'secret' in a and 'secret' in b:
        return True
    return dict(a) == dict(b)


def _min_range(scale: Mapping[str, Any]) -> tuple[int, int]:
    """(lowest, highest) effective min across the two readings of a service/revision annotation split:
    the larger wins, or the service-level value wins when set. Rules use the reading that fails."""
    service, revision = scale.get('service_min'), scale.get('revision_min')
    larger = max(service or 0, revision or 0)
    service_wins = service if service is not None else (revision or 0)
    return min(larger, service_wins), max(larger, service_wins)


def _max_range(scale: Mapping[str, Any]) -> tuple[int, int] | None:
    """(lowest, highest) effective max: the smaller cap wins, or the service-level cap wins when set."""
    service, revision = scale.get('service_max'), scale.get('revision_max')
    caps = [v for v in (service, revision) if v]
    if not caps:
        return None
    readings = (min(caps), service or revision or min(caps))
    return min(readings), max(readings)


KNOWN_LIVE_ONLY = BACKEND / 'deploy' / 'ops' / 'live_only.yaml'


def load_known(path: Path | None, environment: str) -> dict[tuple[str, str], str]:
    """``(service, key) -> class`` from the reviewed live-only inventory (a ratchet, like known gaps)."""
    if path is None or not path.exists():
        return {}
    doc = (yaml.safe_load(path.read_text(encoding='utf-8')) or {}).get(environment) or {}
    return {
        (service, key): klass
        for klass, keys in doc.items()
        for key, services in (keys or {}).items()
        for service in services
    }


def compare_source(
    live: Mapping[str, Any],
    source: Mapping[str, SourceService],
    ramp: Mapping[str, set[str]],
    known: Mapping[tuple[str, str], str] | None = None,
) -> list[Finding]:
    """Live vs source. Ops-file keys are judged strictly; ramp keys, deploy stamps, UID cohorts and
    reviewed ``known`` live-only entries are explained. A known entry that is no longer live fails,
    so the inventory only shrinks."""
    known = dict(known or {})
    findings: list[Finding] = []
    for live_name, svc in sorted((live.get('services') or {}).items()):
        name = _base_name(live_name)
        src = source.get(name)
        if src is None:
            findings.append(Finding(live_name, '-', 'service not in source'))
            continue
        live_env: dict[str, dict[str, str]] = svc.get('env') or {}
        expected = {**src.env, **{k: plain(k, v) for k, v in src.ops_env.items()}}

        ops_keys = set(src.ops_env)

        def explain(key: str, kind: str) -> Finding:
            if key in ops_keys:
                return Finding(live_name, key, kind + ' (ops file not applied)')
            entry = known.pop((name, key), None) if kind.startswith('live-only') else None
            return _explain(live_name, key, kind, name, ramp, entry)

        for key in sorted(set(live_env) | set(expected)):
            have, want = live_env.get(key), expected.get(key)
            if have is not None and want is not None:
                if 'from' in want:
                    continue  # deploy-time input: presence is all source states
                if 'secret' in want and 'secret' not in have:
                    findings.append(Finding(live_name, key, 'source binds a secret; live has a plain value'))
                elif 'secret' not in want and not _same(have, want):
                    findings.append(explain(key, 'value differs from source'))
                continue
            if have is None and want == {'from': 'optional-deploy-input'}:
                findings.append(Finding(live_name, key, 'in source, missing live', 'optional deploy input unset'))
            elif have is None:
                findings.append(explain(key, 'in source, missing live'))
            else:
                findings.append(explain(key, 'live-only (not in source)'))
        findings.extend(_scale_vs_source(live_name, svc.get('scale') or {}, src))
    snapshotted = {_base_name(n) for n in live.get('services') or {}}
    for (service, key), klass in sorted(known.items()):
        if service in snapshotted:
            findings.append(Finding(service, key, f'known live-only ({klass}) is gone: remove it from live_only.yaml'))
    return findings


def _explain(
    service: str, key: str, kind: str, base: str, ramp: Mapping[str, set[str]], known: str | None = None
) -> Finding:
    if key in ramp.get(base, set()):
        return Finding(service, key, kind, 'ramp-owned: infra/rollout/ramp_env.json')
    if not kind.startswith('live-only'):
        return Finding(service, key, kind)
    if key in DEPLOY_STAMPED:
        return Finding(service, key, kind, 'deploy-stamped')
    pattern = _matches(key, LIVE_MANAGED)
    if pattern:
        return Finding(service, key, kind, f'live-managed UID cohort ({pattern})')
    if known:
        return Finding(service, key, kind, f'known live-only: {known}')
    return Finding(service, key, kind)


def _scale_vs_source(service: str, live: Mapping[str, Any], src: SourceService) -> list[Finding]:
    out: list[Finding] = []
    for field, want in src.scale.items():
        if want is None or field not in live:
            continue
        have = live.get(field)
        if field.endswith('_min') and have is None:
            have = 0  # an unset min is zero
        if quantity(have) != quantity(want):
            out.append(Finding(service, field, f'scale: live {live.get(field)} != deploy flag {want}'))
    for field, want in src.ops_scale.items():
        have = live.get(field)
        if want is None:
            continue
        if isinstance(want, dict):
            if have is None or not want.get('floor', 0) <= have <= want.get('ceiling', have):
                out.append(Finding(service, field, f'scale: live {have} outside ops bounds'))
        elif have != want:
            out.append(Finding(service, field, f'scale: live {have} != ops file {want}'))
    return out


def _host(value: str) -> str | None:
    if '://' not in value:
        return None
    return urlparse(value).hostname


def _route(entry: Mapping[str, str] | None) -> str:
    """Path of a plain URL value, normalized for a trailing slash."""
    return urlparse((entry or {}).get('value', '')).path.rstrip('/')


def _url_index(snapshot: Mapping[str, Any]) -> dict[str, str]:
    """hostname -> unsuffixed service name, from each service's own URLs."""
    index: dict[str, str] = {}
    for name, svc in (snapshot.get('services') or {}).items():
        for url in svc.get('urls') or []:
            host = _host(url)
            if host:
                index[host] = _base_name(name)
    return index


def _self_reference(entry: Mapping[str, str] | None, own: Mapping[str, str], other: Mapping[str, str]) -> str | None:
    """Which service a URL/audience value points at: a service name, 'other-env', or None (external)."""
    if not entry or 'value' not in entry:
        return None
    host = _host(entry['value'])
    if host is None:
        return None
    if host in own:
        return own[host]
    if host in other:
        return 'other-env:' + other[host]
    return None


def load_ramp_sets(path: Path | None) -> dict[str, dict[str, dict[str, str]]]:
    """``{set: {service: {key: value}}}`` from ramp_env.json, Cloud Run targets only."""
    if path is None:
        return {}
    out: dict[str, dict[str, dict[str, str]]] = {}
    for set_name, targets in json.loads(path.read_text(encoding='utf-8')).items():
        for target, keys in targets.items():
            kind, _, service = target.partition('/')
            if kind == 'cloud_run':
                out.setdefault(set_name, {})[service] = {k: str(v) for k, v in keys.items()}
    return out


def ramp_position(
    snapshot: Mapping[str, Any], ramp_sets: Mapping[str, Mapping[str, Mapping[str, str]]]
) -> tuple[str | None, list[tuple[str, str]]]:
    """The ramp set an environment sits on (fewest disagreeing keys among sets that cover every
    snapshotted service), and the ``(service, key)`` pairs off it."""
    services = {_base_name(n): svc for n, svc in (snapshot.get('services') or {}).items()}
    best: tuple[str | None, list[tuple[str, str]]] = (None, [])
    for set_name, targets in ramp_sets.items():
        if not set(services) - {LISTEN} <= set(targets):
            continue  # a partial set (restore/toggle) is not a position
        off = [
            (service, key)
            for service, keys in targets.items()
            if service in services
            for key, value in keys.items()
            if (services[service].get('env') or {}).get(key) != plain(key, value)
        ]
        if best[0] is None or len(off) < len(best[1]):
            best = (set_name, off)
    return best


def compare_staging_prod(
    staging: Mapping[str, Any],
    prod: Mapping[str, Any],
    ramp_sets: Mapping[str, Mapping[str, Mapping[str, str]]] | None = None,
    known_prod: Mapping[tuple[str, str], str] | None = None,
) -> list[Finding]:
    """Live staging vs live prod. Ramp-owned keys are judged per environment instead: each must sit
    on one coherent ramp set (staging may lead prod), and a key off that set fails. Prod keys in the
    live-only inventory (``known_prod``) that staging lacks are explained; the ratchet tracks them."""
    from scripts.cross_service_checks.staging import STAGING_DIFF_ALLOWLIST

    known_prod = dict(known_prod or {})
    ramp_sets = ramp_sets or {}
    findings: list[Finding] = []
    positions: dict[str, str | None] = {}
    for env_name, snapshot in (('staging', staging), ('prod', prod)) if ramp_sets else ():
        position, off = ramp_position(snapshot, ramp_sets)
        positions[env_name] = position
        if position is None:
            findings.append(Finding(env_name, 'ramp', 'no ramp set covers every snapshotted service'))
            continue
        findings.append(Finding(env_name, 'ramp', f'sits on ramp set {position}', 'ramp position'))
        for service, key in off:
            findings.append(Finding(f'{env_name}:{service}', key, f'ramp key off its set {position}'))
    s_pos, p_pos = positions.get('staging'), positions.get('prod')
    if s_pos and p_pos and s_pos not in (p_pos, STAGING_AHEAD_SET):
        findings.append(Finding('staging', 'ramp', f'on {s_pos}, neither prod\'s {p_pos} nor {STAGING_AHEAD_SET}'))
    # Equality is skipped only where both winning sets judge the key; anything else is compared.
    ramp_owned = (
        {(s, k) for s, keys in ramp_sets[s_pos].items() for k in keys}
        & {(s, k) for s, keys in ramp_sets[p_pos].items() for k in keys}
        if s_pos and p_pos
        else set()
    )
    s_urls, p_urls = _url_index(staging), _url_index(prod)
    s_services = {_base_name(n): (n, svc) for n, svc in (staging.get('services') or {}).items()}
    p_services = dict((prod.get('services') or {}).items())
    for name in sorted(set(s_services) ^ set(p_services)):
        side = 'staging' if name in s_services else 'prod'
        findings.append(Finding(name, '-', f'service snapshotted only in {side}', 'not compared'))
    for name in sorted(set(s_services) & set(p_services)):
        s_name, s_svc = s_services[name]
        p_svc = p_services[name]
        s_env, p_env = s_svc.get('env') or {}, p_svc.get('env') or {}
        for key in sorted(set(s_env) | set(p_env)):
            s, p = s_env.get(key), p_env.get(key)
            s_ref = _self_reference(s, s_urls, p_urls)
            p_ref = _self_reference(p, p_urls, s_urls)
            if s_ref and s_ref.startswith('other-env:'):
                findings.append(Finding(s_name, key, f'points at a prod service ({s_ref[10:]})'))
                continue
            if (name, key) in ramp_owned:
                continue  # judged by ramp position above
            if s is None or p is None:
                side = 'prod' if s is None else 'staging'
                reason = LIVE_ONE_SIDED_ALLOWLIST.get(_matches(key, LIVE_ONE_SIDED_ALLOWLIST) or '')
                if not reason and s is None and (name, key) in known_prod:
                    reason = f'known prod live-only: {known_prod[(name, key)]}'
                if not reason and _matches(key, STAGING_DIFF_ALLOWLIST):
                    reason = 'STAGING_DIFF_ALLOWLIST'
                findings.append(Finding(s_name, key, f'only in {side}', reason or ''))
                continue
            if _same(s, p):
                continue
            if s_ref or p_ref:
                if s_ref != p_ref:
                    findings.append(
                        Finding(s_name, key, f'points at {s_ref or "external"}; prod points at {p_ref or "external"}')
                    )
                elif _route(s) != _route(p):  # same service, different handler (e.g. /v1 vs /v2 sync-jobs)
                    findings.append(Finding(s_name, key, f'points at {s_ref} on a different path than prod'))
                continue
            reason = LIVE_DIFF_ALLOWLIST.get(_matches(key, LIVE_DIFF_ALLOWLIST) or '')
            if not reason and _matches(key, STAGING_DIFF_ALLOWLIST):
                reason = 'STAGING_DIFF_ALLOWLIST'
            kind = f'value differs (staging {printable(key, s)}, prod {printable(key, p)})'
            findings.append(Finding(s_name, key, kind, reason or ''))
        findings.extend(_scale_vs_prod(s_name, s_svc.get('scale') or {}, p_svc.get('scale') or {}))
    return findings


def _scale_vs_prod(service: str, s: Mapping[str, Any], p: Mapping[str, Any]) -> list[Finding]:
    out: list[Finding] = []
    s_high, p_high = _min_range(s)[1], _min_range(p)[1]
    if s_high > p_high:
        out.append(Finding(service, 'min_instances', f'staging {s_high} > prod {p_high}'))
    s_max, p_max = _max_range(s), _max_range(p)
    if s_max is not None and p_max is not None and s_max[1] > p_max[0]:
        out.append(Finding(service, 'max_instances', f'staging {s_max[1]} > prod {p_max[0]}'))
    for field in EQUAL_SCALE_FIELDS:
        if s.get(field) is not None and p.get(field) is not None and quantity(s[field]) != quantity(p[field]):
            out.append(Finding(service, field, f'staging {s[field]}, prod {p[field]}'))
    return out


# ------------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------------


def report(findings: list[Finding], *, show_explained: bool) -> int:
    failing = [f for f in findings if not f.explained]
    for finding in findings:
        if show_explained or not finding.explained:
            print(finding.line())
    print(f'{len(failing)} unexplained difference(s), {len(findings) - len(failing)} explained')
    return 1 if failing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    snap = sub.add_parser('snapshot', help='read live state (gcloud/kubectl) into a redacted snapshot file')
    snap.add_argument('--project', required=True)
    snap.add_argument('--region', default='us-central1')
    snap.add_argument('--service', action='append', default=[], help='Cloud Run service (repeatable)')
    snap.add_argument('--k8s', action='append', default=[], help='namespace/deployment:container (repeatable)')
    snap.add_argument('--kube-context', help='explicit kubectl context (required with --k8s)')
    snap.add_argument('--out', type=Path, required=True)

    src = sub.add_parser('source', help='live snapshot vs what a deploy from this tree would set')
    src.add_argument('--env', choices=('prod', 'staging'), required=True)
    src.add_argument('--live', type=Path, required=True)
    src.add_argument('--ramp-env', type=Path, help='omi-workspace infra/rollout/ramp_env.json (ramp-owned keys)')
    src.add_argument('--known', type=Path, default=KNOWN_LIVE_ONLY, help='reviewed live-only inventory (ratchet)')
    src.add_argument('--all', action='store_true', help='print explained differences too')

    svp = sub.add_parser('staging-vs-prod', help='live staging snapshot vs live prod snapshot')
    svp.add_argument('--staging', type=Path, required=True)
    svp.add_argument('--prod', type=Path, required=True)
    svp.add_argument('--ramp-env', type=Path, help='ramp_env.json: judge ramp keys by ramp position, not equality')
    svp.add_argument('--known', type=Path, default=KNOWN_LIVE_ONLY, help='reviewed prod live-only inventory')
    svp.add_argument('--all', action='store_true', help='print explained differences too')

    args = parser.parse_args(argv)
    if args.command == 'snapshot':
        data = take_snapshot(
            project=args.project,
            region=args.region,
            services=args.service,
            k8s=args.k8s,
            kube_context=args.kube_context,
        )
        args.out.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(f'wrote {args.out}: {len(data["services"])} service(s)')
        return 0
    if args.command == 'source':
        findings = compare_source(
            load_snapshot(args.live), source_model(args.env), ramp_keys(args.ramp_env), load_known(args.known, args.env)
        )
        return report(findings, show_explained=args.all)
    findings = compare_staging_prod(
        load_snapshot(args.staging),
        load_snapshot(args.prod),
        load_ramp_sets(args.ramp_env),
        load_known(args.known, 'prod'),
    )
    return report(findings, show_explained=args.all)


if __name__ == '__main__':
    sys.path.insert(0, str(BACKEND))
    raise SystemExit(main())
