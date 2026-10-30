#!/usr/bin/env python3
"""Config-train (B4): plan, apply and verify the ops file against live serving state.

The ops file (`backend/deploy/ops/<env>.yaml`) holds the values that operators
own: queue re-points, Cloud Tasks queue rates and retries, and service-level
Cloud Run scaling. A backend train never sets them; this tool is their only
writer.

    ops_train.py validate [--env prod]           schema check, no cloud access
    ops_train.py plan --env prod [--report F]    diff against live serving state
    ops_train.py apply --env prod --revision-suffix S [--report F]
    ops_train.py render-env --env prod --service backend-sync

Exit codes: 0 no difference (or applied and verified), 2 plan has changes,
3 blocked (a precondition failed; nothing was applied), 1 error.

Safety properties:
- Cloud Run env is read from the revision that serves traffic
  (`status.traffic`), never from `spec.template`, which a failed no-traffic
  deploy can leave pointing at an unqualified image (10-18 23:48Z).
- An env change is refused while the template differs from the serving revision
  in anything but ops-owned keys, so a config-train can never promote an image
  or env that no train qualified.
- Every env change routes 100% of traffic to the new named revision explicitly
  and verifies that it serves. `backend-sync-backfill` pins traffic to a named
  revision, so an unrouted update never serves (10-19 04:52Z).
- Values are printed only for keys declared in the ops file, and the schema
  rejects secret-shaped key names and values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

OPS_DIR = Path(__file__).resolve().parents[1] / 'deploy' / 'ops'
SCHEMA = 'omi.ops/v1'
ENVIRONMENTS = ('prod', 'staging')

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CHANGES = 2
EXIT_BLOCKED = 3

SECRET_KEY = re.compile(r'(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE)', re.IGNORECASE)
ENV_KEY = re.compile(r'^[A-Z][A-Z0-9_]{0,127}$')
ENV_VALUE = re.compile(r'^[A-Za-z0-9._:/-]{0,200}$')
NAME = re.compile(r'^[a-z][a-z0-9-]{0,62}$')
DURATION = re.compile(r'^(\d+(?:\.\d+)?)s$')
REVISION_SUFFIX = re.compile(r'^[a-z0-9][a-z0-9-]{0,40}$')

QUEUE_FIELDS = {
    'max_concurrent_dispatches': ('rateLimits', 'maxConcurrentDispatches', '--max-concurrent-dispatches'),
    'max_dispatches_per_second': ('rateLimits', 'maxDispatchesPerSecond', '--max-dispatches-per-second'),
    'max_attempts': ('retryConfig', 'maxAttempts', '--max-attempts'),
    'min_backoff': ('retryConfig', 'minBackoff', '--min-backoff'),
    'max_backoff': ('retryConfig', 'maxBackoff', '--max-backoff'),
    'max_doublings': ('retryConfig', 'maxDoublings', '--max-doublings'),
    'log_sampling_ratio': ('stackdriverLoggingConfig', 'samplingRatio', '--log-sampling-ratio'),
}
SERVICE_FIELDS = {'env', 'max_instances', 'min_instances'}
MAX_SCALE = 'run.googleapis.com/maxScale'
MIN_SCALE = 'run.googleapis.com/minScale'


class OpsError(RuntimeError):
    pass


# --------------------------------------------------------------------------- schema


@dataclass(frozen=True)
class Bound:
    owner: str
    floor: int
    ceiling: int


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    env: Mapping[str, str]
    max_instances: int | Bound | None = None
    min_instances: int | None = None


@dataclass(frozen=True)
class QueueSpec:
    name: str
    enabled: bool
    fields: Mapping[str, Any]


@dataclass(frozen=True)
class OpsSpec:
    environment: str
    project: str
    region: str
    services: tuple[ServiceSpec, ...]
    queues: tuple[QueueSpec, ...]
    sha256: str


def _int(value: Any, where: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OpsError(f'{where}: expected an integer >= {minimum}')
    return value


def _duration_seconds(value: Any, where: str) -> float:
    if not isinstance(value, str) or not DURATION.match(value):
        raise OpsError(f'{where}: expected a duration like "5s"')
    return float(DURATION.match(value).group(1))


def _parse_service(name: str, raw: Any) -> ServiceSpec:
    where = f'cloud_run.{name}'
    if not NAME.match(name):
        raise OpsError(f'{where}: invalid service name')
    if not isinstance(raw, Mapping):
        raise OpsError(f'{where}: expected a mapping')
    unknown = set(raw) - SERVICE_FIELDS
    if unknown:
        raise OpsError(f'{where}: unknown keys {sorted(unknown)}')
    env_raw = raw.get('env') or {}
    if not isinstance(env_raw, Mapping):
        raise OpsError(f'{where}.env: expected a mapping')
    env: dict[str, str] = {}
    for key, value in env_raw.items():
        if not isinstance(key, str) or not ENV_KEY.match(key):
            raise OpsError(f'{where}.env: invalid key {key!r}')
        if SECRET_KEY.search(key):
            raise OpsError(f'{where}.env.{key}: secret-shaped keys never belong in the ops file')
        if not isinstance(value, str) or not ENV_VALUE.match(value):
            raise OpsError(f'{where}.env.{key}: value must be a short plain string (quote numbers)')
        env[key] = value
    max_raw = raw.get('max_instances')
    max_instances: int | Bound | None
    if max_raw is None:
        max_instances = None
    elif isinstance(max_raw, Mapping):
        if set(max_raw) != {'owner', 'floor', 'ceiling'} or not isinstance(max_raw['owner'], str):
            raise OpsError(f'{where}.max_instances: a bound needs exactly owner, floor and ceiling')
        floor = _int(max_raw['floor'], f'{where}.max_instances.floor', minimum=1)
        ceiling = _int(max_raw['ceiling'], f'{where}.max_instances.ceiling', minimum=1)
        if floor > ceiling:
            raise OpsError(f'{where}.max_instances: floor exceeds ceiling')
        max_instances = Bound(max_raw['owner'], floor, ceiling)
    else:
        max_instances = _int(max_raw, f'{where}.max_instances', minimum=1)
    min_raw = raw.get('min_instances')
    min_instances = None if min_raw is None else _int(min_raw, f'{where}.min_instances')
    upper = max_instances.floor if isinstance(max_instances, Bound) else max_instances
    if min_instances is not None and upper is not None and min_instances > upper:
        raise OpsError(f'{where}: min_instances exceeds max_instances')
    if not env and max_instances is None and min_instances is None:
        raise OpsError(f'{where}: declares nothing')
    return ServiceSpec(name, env, max_instances, min_instances)


def _parse_queue(name: str, raw: Any) -> QueueSpec:
    where = f'cloud_tasks.{name}'
    if not NAME.match(name):
        raise OpsError(f'{where}: invalid queue name')
    if not isinstance(raw, Mapping):
        raise OpsError(f'{where}: expected a mapping')
    unknown = set(raw) - set(QUEUE_FIELDS) - {'enabled'}
    if unknown:
        raise OpsError(f'{where}: unknown keys {sorted(unknown)}')
    enabled = raw.get('enabled', True)
    if not isinstance(enabled, bool):
        raise OpsError(f'{where}.enabled: expected a boolean')
    fields: dict[str, Any] = {}
    for key in QUEUE_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if key in {'min_backoff', 'max_backoff'}:
            _duration_seconds(value, f'{where}.{key}')
            fields[key] = value
        elif key == 'max_attempts':
            if isinstance(value, bool) or not isinstance(value, int) or (value < 1 and value != -1):
                raise OpsError(f'{where}.max_attempts: expected a positive integer or -1 (unlimited)')
            fields[key] = value
        elif key in {'max_dispatches_per_second', 'log_sampling_ratio'}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise OpsError(f'{where}.{key}: expected a non-negative number')
            if key == 'log_sampling_ratio' and value > 1:
                raise OpsError(f'{where}.log_sampling_ratio: must be within [0, 1]')
            fields[key] = float(value)
        else:
            fields[key] = _int(value, f'{where}.{key}', minimum=0 if key == 'max_doublings' else 1)
    if 'min_backoff' in fields and 'max_backoff' in fields:
        if _duration_seconds(fields['min_backoff'], where) > _duration_seconds(fields['max_backoff'], where):
            raise OpsError(f'{where}: min_backoff exceeds max_backoff')
    if not fields:
        raise OpsError(f'{where}: declares nothing')
    return QueueSpec(name, enabled, fields)


def parse_ops(text: str, *, expected_environment: str | None = None) -> OpsSpec:
    data = yaml.safe_load(text)
    if not isinstance(data, Mapping):
        raise OpsError('ops file must be a mapping')
    unknown = set(data) - {'schema', 'environment', 'project', 'region', 'cloud_run', 'cloud_tasks'}
    if unknown:
        raise OpsError(f'unknown top-level keys {sorted(unknown)}')
    if data.get('schema') != SCHEMA:
        raise OpsError(f'schema must be {SCHEMA}')
    environment = data.get('environment')
    if environment not in ENVIRONMENTS:
        raise OpsError(f'environment must be one of {ENVIRONMENTS}')
    if expected_environment is not None and environment != expected_environment:
        raise OpsError(f'file declares environment {environment!r}, expected {expected_environment!r}')
    project, region = data.get('project'), data.get('region')
    if not isinstance(project, str) or not NAME.match(project):
        raise OpsError('project must be a GCP project id')
    if environment == 'prod' and project != 'based-hardware':
        raise OpsError('prod ops must target based-hardware')
    if environment == 'staging' and project != 'based-hardware-dev':
        raise OpsError('staging ops must target based-hardware-dev (contract (i))')
    if not isinstance(region, str) or not NAME.match(region):
        raise OpsError('region must be a GCP region')
    services_raw = data.get('cloud_run') or {}
    queues_raw = data.get('cloud_tasks') or {}
    if not isinstance(services_raw, Mapping) or not isinstance(queues_raw, Mapping):
        raise OpsError('cloud_run and cloud_tasks must be mappings')
    services = tuple(_parse_service(str(name), raw) for name, raw in services_raw.items())
    queues = tuple(_parse_queue(str(name), raw) for name, raw in queues_raw.items())
    if environment == 'staging':
        for service in services:
            if not service.name.endswith('-staging'):
                raise OpsError(f'staging service {service.name} must end with -staging')
        for queue in queues:
            if not queue.name.startswith('staging-'):
                raise OpsError(f'staging queue {queue.name} must start with staging-')
    return OpsSpec(
        environment=environment,
        project=project,
        region=region,
        services=services,
        queues=queues,
        sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
    )


def load_ops(environment: str, ops_dir: Path = OPS_DIR) -> OpsSpec:
    if environment not in ENVIRONMENTS:
        raise OpsError(f'unknown environment {environment!r}')
    path = ops_dir / f'{environment}.yaml'
    return parse_ops(path.read_text(encoding='utf-8'), expected_environment=environment)


# --------------------------------------------------------------------------- live reads


class Gcloud(Protocol):
    def json(self, args: Sequence[str]) -> Any: ...

    def run(self, args: Sequence[str]) -> None: ...


class GcloudCli:
    def json(self, args: Sequence[str]) -> Any:
        proc = subprocess.run(['gcloud', *args, '--format=json'], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise OpsError(f'gcloud {" ".join(args[:3])} failed: {proc.stderr.strip().splitlines()[-1:]}')
        return json.loads(proc.stdout or 'null')

    def run(self, args: Sequence[str]) -> None:
        proc = subprocess.run(['gcloud', *args, '--quiet'], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise OpsError(f'gcloud {" ".join(args[:3])} failed: {proc.stderr.strip().splitlines()[-1:]}')


def _location(spec: OpsSpec) -> list[str]:
    return [f'--project={spec.project}', f'--region={spec.region}']


def _queue_location(spec: OpsSpec) -> list[str]:
    return [f'--project={spec.project}', f'--location={spec.region}']


def _env_map(container: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in container.get('env') or []:
        if isinstance(item, Mapping) and isinstance(item.get('name'), str):
            out[item['name']] = item.get('value') if 'value' in item else {'valueFrom': item.get('valueFrom')}
    return out


def _containers(spec: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    containers = spec.get('containers') or []
    out: dict[str, Mapping[str, Any]] = {}
    for index, container in enumerate(containers):
        out[str(container.get('name') or f'#{index}')] = container
    return out


def _ingress(spec: Mapping[str, Any]) -> Mapping[str, Any]:
    containers = spec.get('containers') or []
    for container in containers:
        if container.get('ports'):
            return container
    if not containers:
        raise OpsError('revision has no containers')
    return containers[0]


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:12]


def template_drift(template: Mapping[str, Any], serving: Mapping[str, Any], ops_keys: set[str]) -> list[str]:
    """Where the template differs from the serving revision, ignoring only ops-owned env keys.

    The whole revision spec counts (service account, concurrency, timeout, volumes, probes,
    mounts, ports), not just image and env: an env apply builds its revision from the template
    and then routes 100% to it, so any other difference would ship unqualified (M1 L07-2).
    """

    drift: list[str] = []
    for key in sorted((set(template) | set(serving)) - {'containers'}):
        if _digest(template.get(key)) != _digest(serving.get(key)):
            drift.append(key)
    left, right = _containers(template), _containers(serving)
    if set(left) != set(right):
        # Cloud Run names an unnamed template container on the revision it creates
        # (`#0` in the template, `backend-1` on the revision): pair them by position.
        lc, rc = template.get('containers') or [], serving.get('containers') or []
        if len(lc) != len(rc) or any(
            a.get('name') and b.get('name') and a['name'] != b['name'] for a, b in zip(lc, rc)
        ):
            return drift + [f'containers:{sorted(left)}!={sorted(right)}']
        left = {f'#{i}': c for i, c in enumerate(lc)}
        right = {f'#{i}': c for i, c in enumerate(rc)}
    for name in sorted(left):
        a, b = left[name], right[name]
        for key in sorted((set(a) | set(b)) - {'name', 'env'}):
            if _digest(a.get(key)) != _digest(b.get(key)):
                drift.append(f'{name}.{key}')
        env_a = {k: v for k, v in _env_map(a).items() if k not in ops_keys}
        env_b = {k: v for k, v in _env_map(b).items() if k not in ops_keys}
        for key in sorted(set(env_a) | set(env_b)):
            if _digest(env_a.get(key)) != _digest(env_b.get(key)):
                drift.append(f'{name}.env.{key}')
    return drift


@dataclass
class Change:
    target: str  # cloud_run | cloud_tasks
    name: str
    field: str
    live: Any
    desired: Any
    action: str  # set | create | clamp


@dataclass
class ServiceState:
    name: str
    serving_revision: str
    serving_env: dict[str, Any]
    max_scale: int | None
    min_scale: int | None


@dataclass
class Plan:
    environment: str
    project: str
    ops_sha256: str
    changes: list[Change] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    services: dict[str, ServiceState] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            'environment': self.environment,
            'project': self.project,
            'ops_sha256': self.ops_sha256,
            'changes': [asdict(change) for change in self.changes],
            'blockers': list(self.blockers),
            'serving': {name: state.serving_revision for name, state in self.services.items()},
        }


def _annotation_int(annotations: Mapping[str, Any], key: str) -> int | None:
    value = annotations.get(key)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def serving_revision(service: Mapping[str, Any]) -> str | None:
    serving = [
        entry
        for entry in (service.get('status') or {}).get('traffic') or []
        if isinstance(entry, Mapping) and (entry.get('percent') or 0) > 0
    ]
    if len(serving) != 1 or serving[0].get('percent') != 100 or not serving[0].get('revisionName'):
        return None
    return str(serving[0]['revisionName'])


def plan_service(spec: OpsSpec, svc: ServiceSpec, gcloud: Gcloud, plan: Plan) -> None:
    try:
        service = gcloud.json(['run', 'services', 'describe', svc.name, *_location(spec)])
    except OpsError as exc:
        plan.blockers.append(f'{svc.name}: service unreadable ({exc})')
        return
    revision_name = serving_revision(service)
    if revision_name is None:
        plan.blockers.append(f'{svc.name}: traffic is not 100% on one revision; finish or roll back the rollout first')
        return
    revision = gcloud.json(['run', 'revisions', 'describe', revision_name, *_location(spec)])
    serving_spec = revision.get('spec') or {}
    template_spec = ((service.get('spec') or {}).get('template') or {}).get('spec') or {}
    annotations = (service.get('metadata') or {}).get('annotations') or {}
    serving_env = _env_map(_ingress(serving_spec))
    state = ServiceState(
        name=svc.name,
        serving_revision=revision_name,
        serving_env=serving_env,
        max_scale=_annotation_int(annotations, MAX_SCALE),
        min_scale=_annotation_int(annotations, MIN_SCALE),
    )
    plan.services[svc.name] = state

    env_changes = [
        Change('cloud_run', svc.name, f'env.{key}', serving_env.get(key), value, 'set')
        for key, value in svc.env.items()
        if serving_env.get(key) != value
    ]
    if env_changes:
        drift = template_drift(template_spec, serving_spec, set(svc.env))
        if drift:
            plan.blockers.append(
                f'{svc.name}: template differs from serving revision {revision_name} in {drift[:6]}; '
                'an env update would ship it. Run a train or repair traffic first'
            )
    plan.changes.extend(env_changes)

    if isinstance(svc.max_instances, Bound):
        live = state.max_scale
        bound = svc.max_instances
        if live is None or live > bound.ceiling:
            plan.changes.append(Change('cloud_run', svc.name, 'max_instances', live, bound.ceiling, 'clamp'))
        elif live < bound.floor:
            plan.changes.append(Change('cloud_run', svc.name, 'max_instances', live, bound.floor, 'clamp'))
    elif svc.max_instances is not None and state.max_scale != svc.max_instances:
        plan.changes.append(Change('cloud_run', svc.name, 'max_instances', state.max_scale, svc.max_instances, 'set'))
    if svc.min_instances is not None and (state.min_scale or 0) != svc.min_instances:
        plan.changes.append(Change('cloud_run', svc.name, 'min_instances', state.min_scale, svc.min_instances, 'set'))


def _normalize(field_name: str, value: Any) -> Any:
    if value is None:
        return None
    if field_name in {'min_backoff', 'max_backoff'}:
        match = DURATION.match(str(value))
        return float(match.group(1)) if match else value
    if field_name in {'max_dispatches_per_second', 'log_sampling_ratio'}:
        return round(float(value), 6)
    return int(value)


def plan_queues(spec: OpsSpec, gcloud: Gcloud, plan: Plan) -> None:
    wanted = [queue for queue in spec.queues if queue.enabled]
    if not wanted:
        return
    try:
        listed = gcloud.json(['tasks', 'queues', 'list', *_queue_location(spec)]) or []
    except OpsError as exc:
        plan.blockers.append(f'cloud_tasks: queues unreadable ({exc})')
        return
    live = {str(item.get('name', '')).rsplit('/', 1)[-1]: item for item in listed if isinstance(item, Mapping)}
    for queue in wanted:
        current = live.get(queue.name)
        if current is None:
            plan.changes.append(Change('cloud_tasks', queue.name, '*', None, dict(queue.fields), 'create'))
            continue
        if current.get('state') not in (None, 'RUNNING'):
            plan.blockers.append(f'{queue.name}: queue state is {current.get("state")}; a human paused or disabled it')
        for key, value in queue.fields.items():
            section, api_key, _flag = QUEUE_FIELDS[key]
            live_value = (current.get(section) or {}).get(api_key)
            if _normalize(key, live_value) != _normalize(key, value):
                plan.changes.append(Change('cloud_tasks', queue.name, key, live_value, value, 'set'))


def build_plan(spec: OpsSpec, gcloud: Gcloud) -> Plan:
    plan = Plan(environment=spec.environment, project=spec.project, ops_sha256=spec.sha256)
    for svc in spec.services:
        plan_service(spec, svc, gcloud, plan)
    plan_queues(spec, gcloud, plan)
    return plan


# --------------------------------------------------------------------------- apply


def _queue_flags(queue: QueueSpec, keys: Sequence[str]) -> list[str]:
    flags = []
    for key in keys:
        value = queue.fields[key]
        if key == 'max_attempts' and value == -1:
            flags.append('--max-attempts=unlimited')
            continue
        if isinstance(value, float) and value.is_integer() and key != 'log_sampling_ratio':
            value = int(value)
        flags.append(f'{QUEUE_FIELDS[key][2]}={value}')
    return flags


def apply_plan(spec: OpsSpec, plan: Plan, gcloud: Gcloud, revision_suffix: str) -> list[str]:
    """Apply the plan's changes. Returns the commands' targets in order. Never runs with blockers."""

    if plan.blockers:
        raise OpsError('refusing to apply a blocked plan')
    if not REVISION_SUFFIX.match(revision_suffix):
        raise OpsError('revision suffix must be lowercase alphanumerics and dashes, at most 41 chars')
    applied: list[str] = []
    by_service: dict[str, list[Change]] = {}
    by_queue: dict[str, list[Change]] = {}
    for change in plan.changes:
        (by_service if change.target == 'cloud_run' else by_queue).setdefault(change.name, []).append(change)
    services = {svc.name: svc for svc in spec.services}
    for name, changes in by_service.items():
        env = {c.field.split('.', 1)[1]: c.desired for c in changes if c.field.startswith('env.')}
        scale = {c.field: c.desired for c in changes if not c.field.startswith('env.')}
        args = ['run', 'services', 'update', name, *_location(spec)]
        if 'max_instances' in scale:
            args.append(f'--max={scale["max_instances"]}')
        if 'min_instances' in scale:
            args.append(f'--min={scale["min_instances"]}')
        if env:
            # Re-assert every ops key, not only the changed ones, so the new revision is complete.
            full = dict(services[name].env)
            args.append('--update-env-vars=' + ','.join(f'{k}={v}' for k, v in sorted(full.items())))
            args.append(f'--revision-suffix={revision_suffix}')
        gcloud.run(args)
        applied.append(f'cloud_run/{name}')
        if env:
            revision = f'{name}-{revision_suffix}'
            gcloud.run(['run', 'services', 'update-traffic', name, *_location(spec), f'--to-revisions={revision}=100'])
            applied.append(f'traffic/{name}={revision}')
    queues = {queue.name: queue for queue in spec.queues}
    for name, changes in by_queue.items():
        queue = queues[name]
        if any(change.action == 'create' for change in changes):
            gcloud.run(
                ['tasks', 'queues', 'create', name, *_queue_location(spec), *_queue_flags(queue, list(queue.fields))]
            )
            applied.append(f'cloud_tasks/{name}:create')
        else:
            keys = [change.field for change in changes]
            gcloud.run(['tasks', 'queues', 'update', name, *_queue_location(spec), *_queue_flags(queue, keys)])
            applied.append(f'cloud_tasks/{name}')
    return applied


def verify_applied(spec: OpsSpec, before: Plan, gcloud: Gcloud, revision_suffix: str) -> Plan:
    after = build_plan(spec, gcloud)
    for name in {c.name for c in before.changes if c.target == 'cloud_run' and c.field.startswith('env.')}:
        expected = f'{name}-{revision_suffix}'
        state = after.services.get(name)
        if state is None or state.serving_revision != expected:
            after.blockers.append(f'{name}: serving {state.serving_revision if state else None}, expected {expected}')
    return after


# --------------------------------------------------------------------------- render (for the train)


def render_env(spec: OpsSpec, service: str) -> list[str]:
    """KEY=VALUE lines a train appends last to a service's env so it cannot undo ops values."""

    for svc in spec.services:
        if svc.name == service:
            return [f'{key}={value}' for key, value in sorted(svc.env.items())]
    return []


# --------------------------------------------------------------------------- CLI


def _print_plan(plan: Plan) -> None:
    print(f'config-train plan env={plan.environment} project={plan.project} ops_sha256={plan.ops_sha256[:12]}')
    for name, state in sorted(plan.services.items()):
        print(f'  serving {name} -> {state.serving_revision}')
    if not plan.changes:
        print('  no changes')
    for change in plan.changes:
        print(
            f'  {change.action:6} {change.target}/{change.name} {change.field}: {change.live!r} -> {change.desired!r}'
        )
    for blocker in plan.blockers:
        print(f'  BLOCKED {blocker}')


def _write_report(path: str | None, payload: Mapping[str, Any]) -> None:
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n', encoding='utf-8')


def main(argv: Sequence[str] | None = None, *, gcloud: Gcloud | None = None, ops_dir: Path = OPS_DIR) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0])
    sub = parser.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate')
    validate.add_argument('--env', choices=ENVIRONMENTS, action='append')
    for name in ('plan', 'apply'):
        command = sub.add_parser(name)
        command.add_argument('--env', choices=ENVIRONMENTS, required=True)
        command.add_argument('--report')
        if name == 'apply':
            command.add_argument('--revision-suffix', required=True)
    render = sub.add_parser('render-env')
    render.add_argument('--env', choices=ENVIRONMENTS, required=True)
    render.add_argument('--service', required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == 'validate':
            for environment in args.env or ENVIRONMENTS:
                spec = load_ops(environment, ops_dir)
                print(f'{environment}: ok ({len(spec.services)} services, {len(spec.queues)} queues)')
            return EXIT_OK
        spec = load_ops(args.env, ops_dir)
        if args.command == 'render-env':
            for line in render_env(spec, args.service):
                print(line)
            return EXIT_OK
        client = gcloud or GcloudCli()
        plan = build_plan(spec, client)
        _print_plan(plan)
        report: dict[str, Any] = {
            'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'plan': plan.as_dict(),
        }
        if plan.blockers:
            _write_report(args.report, report)
            return EXIT_BLOCKED
        if args.command == 'plan' or not plan.changes:
            _write_report(args.report, report)
            return EXIT_CHANGES if plan.changes else EXIT_OK
        report['applied'] = apply_plan(spec, plan, client, args.revision_suffix)
        after = verify_applied(spec, plan, client, args.revision_suffix)
        report['verify'] = after.as_dict()
        _write_report(args.report, report)
        print('config-train verify:')
        _print_plan(after)
        if after.blockers or after.changes:
            print('VERIFY FAILED: live state does not match the ops file after apply', file=sys.stderr)
            return EXIT_ERROR
        print('VERIFIED')
        return EXIT_OK
    except OpsError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return EXIT_ERROR


if __name__ == '__main__':
    raise SystemExit(main())
