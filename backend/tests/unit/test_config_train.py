"""Config-train (B4): ops file schema, plan/apply/verify against a fake gcloud, workflow contract."""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND / 'scripts'))

import ops_train  # noqa: E402

PROD_HEADER = 'schema: omi.ops/v1\nenvironment: prod\nproject: based-hardware\nregion: us-central1\n'


def _container(image: str, env: dict[str, str], *, ports: bool = True, name: str = 'backend') -> dict[str, Any]:
    out: dict[str, Any] = {'name': name, 'image': image, 'env': [{'name': k, 'value': v} for k, v in env.items()]}
    if ports:
        out['ports'] = [{'containerPort': 8080}]
    out['resources'] = {'limits': {'cpu': '2', 'memory': '8Gi'}}
    return out


class FakeGcloud:
    """Models Cloud Run services (template, revisions, traffic, service-level scaling) and Cloud Tasks queues."""

    def __init__(self) -> None:
        self.services: dict[str, dict[str, Any]] = {}
        self.queues: dict[str, dict[str, Any]] = {}
        self.calls: list[list[str]] = []
        self.queues_readable = True

    def add_service(
        self,
        name: str,
        env: dict[str, str],
        *,
        image: str = 'gcr.io/p/backend:abc1234',
        max_scale: int | None = None,
        min_scale: int | None = None,
        pinned: bool = True,
        sidecar: bool = True,
    ) -> None:
        containers = [_container(image, env)]
        if sidecar:
            containers.append(_container('gcr.io/gmp/collector:1', {}, ports=False, name='collector'))
        revision = f'{name}-00001-abc'
        annotations = {}
        if max_scale is not None:
            annotations[ops_train.MAX_SCALE] = str(max_scale)
        if min_scale is not None:
            annotations[ops_train.MIN_SCALE] = str(min_scale)
        self.services[name] = {
            'template': {'containers': copy.deepcopy(containers)},
            'revisions': {revision: {'containers': copy.deepcopy(containers)}},
            'traffic': [{'revisionName': revision, 'percent': 100, 'latestRevision': not pinned}],
            'annotations': annotations,
            'pinned': pinned,
        }

    @staticmethod
    def _flag(args: Sequence[str], prefix: str) -> str | None:
        for arg in args:
            if arg.startswith(prefix + '='):
                return arg.split('=', 1)[1]
        return None

    def json(self, args: Sequence[str]) -> Any:
        self.calls.append(list(args))
        if args[:3] == ['run', 'services', 'describe']:
            name = args[3]
            if name not in self.services:
                raise ops_train.OpsError('NOT_FOUND')
            svc = self.services[name]
            return {
                'metadata': {'annotations': dict(svc['annotations'])},
                'spec': {'template': {'spec': copy.deepcopy(svc['template'])}},
                'status': {'traffic': copy.deepcopy(svc['traffic'])},
            }
        if args[:3] == ['run', 'revisions', 'describe']:
            for svc in self.services.values():
                if args[3] in svc['revisions']:
                    return {'spec': copy.deepcopy(svc['revisions'][args[3]])}
            raise ops_train.OpsError('NOT_FOUND')
        if args[:3] == ['tasks', 'queues', 'list']:
            if not self.queues_readable:
                raise ops_train.OpsError('PERMISSION_DENIED')
            return [dict(q, name=f'projects/p/locations/r/queues/{n}') for n, q in self.queues.items()]
        raise AssertionError(f'unexpected json call {args}')

    def run(self, args: Sequence[str]) -> None:
        self.calls.append(list(args))
        if args[:3] == ['run', 'services', 'update']:
            svc = self.services[args[3]]
            if (value := self._flag(args, '--max')) is not None:
                svc['annotations'][ops_train.MAX_SCALE] = value
            if (value := self._flag(args, '--min')) is not None:
                svc['annotations'][ops_train.MIN_SCALE] = value
            env_flag = self._flag(args, '--update-env-vars')
            if env_flag is not None:
                ingress = svc['template']['containers'][0]
                env = {e['name']: e['value'] for e in ingress['env']}
                env.update(dict(item.split('=', 1) for item in env_flag.split(',')))
                ingress['env'] = [{'name': k, 'value': v} for k, v in env.items()]
                revision = f'{args[3]}-{self._flag(args, "--revision-suffix")}'
                svc['revisions'][revision] = copy.deepcopy(svc['template'])
                if not svc['pinned']:
                    svc['traffic'] = [{'revisionName': revision, 'percent': 100, 'latestRevision': True}]
            return
        if args[:3] == ['run', 'services', 'update-traffic']:
            svc = self.services[args[3]]
            target = self._flag(args, '--to-revisions')
            revision, percent = target.rsplit('=', 1)
            assert revision in svc['revisions'] and percent == '100'
            svc['traffic'] = [{'revisionName': revision, 'percent': 100}]
            svc['pinned'] = True
            return
        if args[:3] in (['tasks', 'queues', 'create'], ['tasks', 'queues', 'update']):
            queue = self.queues.setdefault(args[3], {'state': 'RUNNING'})
            for flag, (section, key) in {
                '--max-concurrent-dispatches': ('rateLimits', 'maxConcurrentDispatches'),
                '--max-dispatches-per-second': ('rateLimits', 'maxDispatchesPerSecond'),
                '--max-attempts': ('retryConfig', 'maxAttempts'),
                '--min-backoff': ('retryConfig', 'minBackoff'),
                '--max-backoff': ('retryConfig', 'maxBackoff'),
                '--max-doublings': ('retryConfig', 'maxDoublings'),
                '--log-sampling-ratio': ('stackdriverLoggingConfig', 'samplingRatio'),
            }.items():
                value = self._flag(args, flag)
                if value is not None:
                    if value == 'unlimited':
                        value = -1
                    queue.setdefault(section, {})[key] = value
            return
        raise AssertionError(f'unexpected run call {args}')

    def mutations(self) -> list[list[str]]:
        return [call for call in self.calls if call[2] in {'update', 'update-traffic', 'create'}]


def _spec(text: str) -> ops_train.OpsSpec:
    return ops_train.parse_ops(PROD_HEADER + text)


QUEUE_SPEC = """
cloud_run:
  backend-sync-backfill:
    env: {SYNC_TASKS_QUEUE: sync-backfill-fresh, SYNC_BACKFILL_TASKS_QUEUE: sync-backfill-fresh}
    max_instances: {owner: redis_guard, floor: 8, ceiling: 40}
cloud_tasks:
  sync-backfill-fresh:
    max_concurrent_dispatches: 90
    max_dispatches_per_second: 15
    min_backoff: 5s
    max_backoff: 60s
"""


def _live_matching(fake: FakeGcloud) -> None:
    fake.add_service(
        'backend-sync-backfill',
        {'SYNC_TASKS_QUEUE': 'sync-backfill-fresh', 'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill-fresh', 'OTHER': 'x'},
        max_scale=24,
    )
    fake.queues['sync-backfill-fresh'] = {
        'state': 'RUNNING',
        'rateLimits': {'maxConcurrentDispatches': 90, 'maxDispatchesPerSecond': 15.0},
        'retryConfig': {'minBackoff': '5s', 'maxBackoff': '60s', 'maxAttempts': 100},
    }


# ----------------------------------------------------------------------------- committed files


@pytest.mark.parametrize('environment', ops_train.ENVIRONMENTS)
def test_committed_ops_files_validate(environment):
    spec = ops_train.load_ops(environment)
    assert spec.services and spec.queues


def test_prod_carries_both_stall_repoints_and_recovery_16_8():
    spec = ops_train.load_ops('prod')
    services = {s.name: s for s in spec.services}
    queues_of = lambda name: {k: v for k, v in services[name].env.items() if k.endswith('_QUEUE')}  # noqa: E731
    assert queues_of('backend-sync') == {
        'SYNC_TASKS_QUEUE': 'sync-jobs-fresh',
        'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill-fresh',
    }
    assert queues_of('backend-sync-backfill') == {
        'SYNC_TASKS_QUEUE': 'sync-backfill-fresh',
        'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill-fresh',
    }
    assert queues_of('backend-integration') == {'SYNC_TASKS_QUEUE': 'sync-jobs-fresh'}
    # C4: the enrichment-maintenance tick on backend-integration owns summary-debt repair.
    assert services['backend-integration'].env['SUMMARY_DEBT_REPAIR_ENABLED'] == 'true'
    # Prod live-only settings carried into source (2026-10-20 inventory, lesson 9).
    assert all(services[s].env['FAIR_USE_ENABLED'] == 'true' for s in services)
    queues = {q.name: q for q in spec.queues}
    recovery = queues['batch-quarantine-recovery'].fields
    assert (recovery['max_concurrent_dispatches'], recovery['max_dispatches_per_second']) == (16, 8.0)
    # Lane 9's enrichment queue is declared but not created before M3.
    assert queues['enrichment'].enabled is False


def test_staging_mirrors_prod_except_names():
    prod, staging = ops_train.load_ops('prod'), ops_train.load_ops('staging')
    staging_services = {s.name: s for s in staging.services}
    for svc in prod.services:
        twin = staging_services[f'{svc.name}-staging']
        assert set(twin.env) == set(svc.env)
        # Queue names carry the staging- prefix; every other ops value is identical.
        assert all(twin.env[k] == (f'staging-{v}' if k.endswith('_QUEUE') else v) for k, v in svc.env.items())
        # Scaling (replica counts) is on contract (i)'s staging allowlist; only env must mirror.
    staging_queues = {q.name: q for q in staging.queues}
    for queue in prod.queues:
        assert staging_queues[f'staging-{queue.name}'].fields == queue.fields


# ----------------------------------------------------------------------------- schema


@pytest.mark.parametrize(
    'body, message',
    [
        ('cloud_run:\n  backend:\n    env: {STRIPE_API_KEY: x}\n', 'secret-shaped'),
        ('cloud_run:\n  backend:\n    env: {A: "a,b"}\n', 'short plain string'),
        ('cloud_run:\n  backend:\n    env: {A: 5}\n', 'short plain string'),
        ('cloud_run:\n  backend:\n    cpu: 2\n', 'unknown keys'),
        ('cloud_run:\n  backend:\n    max_instances: {owner: g, floor: 9, ceiling: 8}\n', 'floor exceeds'),
        ('cloud_run:\n  backend:\n    max_instances: 2\n    min_instances: 3\n', 'min_instances exceeds'),
        ('cloud_tasks:\n  q:\n    min_backoff: 5\n', 'duration'),
        ('cloud_tasks:\n  q:\n    max_attempts: 0\n', 'unlimited'),
        ('cloud_tasks:\n  q:\n    min_backoff: 60s\n    max_backoff: 5s\n', 'min_backoff exceeds'),
        ('cloud_tasks:\n  q:\n    retry: 1\n', 'unknown keys'),
        ('cloud_tasks:\n  q:\n    enabled: false\n', 'declares nothing'),
    ],
)
def test_schema_rejects(body, message):
    with pytest.raises(ops_train.OpsError, match=message):
        _spec(body)


def test_prod_file_cannot_target_another_project():
    with pytest.raises(ops_train.OpsError, match='based-hardware'):
        ops_train.parse_ops(PROD_HEADER.replace('project: based-hardware', 'project: based-hardware-dev'))


def test_staging_names_are_fenced():
    text = 'schema: omi.ops/v1\nenvironment: staging\nproject: based-hardware-dev\nregion: us-central1\n'
    with pytest.raises(ops_train.OpsError, match='-staging'):
        ops_train.parse_ops(text + 'cloud_run:\n  backend-sync:\n    min_instances: 1\n')
    with pytest.raises(ops_train.OpsError, match='staging-'):
        ops_train.parse_ops(text + 'cloud_tasks:\n  sync-jobs:\n    max_attempts: 3\n')


# ----------------------------------------------------------------------------- plan


def test_plan_is_empty_when_live_matches():
    fake = FakeGcloud()
    _live_matching(fake)
    plan = ops_train.build_plan(_spec(QUEUE_SPEC), fake)
    assert plan.changes == [] and plan.blockers == []
    assert fake.mutations() == []


def test_plan_reads_env_from_serving_revision_not_template():
    """10-18 23:48Z: the template held a value the serving revision did not."""

    fake = FakeGcloud()
    _live_matching(fake)
    svc = fake.services['backend-sync-backfill']
    template_env = svc['template']['containers'][0]['env']
    for item in template_env:
        if item['name'] == 'SYNC_TASKS_QUEUE':
            item['value'] = 'sync-backfill'
    plan = ops_train.build_plan(_spec(QUEUE_SPEC), fake)
    assert plan.changes == []


def test_train_reset_is_planned_back():
    """A train that hard-codes sync-backfill re-points the worker at the stalled queue."""

    fake = FakeGcloud()
    _live_matching(fake)
    svc = fake.services['backend-sync-backfill']
    for container in (svc['template'], *svc['revisions'].values()):
        for item in container['containers'][0]['env']:
            if item['name'].endswith('QUEUE'):
                item['value'] = 'sync-backfill'
    plan = ops_train.build_plan(_spec(QUEUE_SPEC), fake)
    assert {(c.field, c.live, c.desired) for c in plan.changes} == {
        ('env.SYNC_TASKS_QUEUE', 'sync-backfill', 'sync-backfill-fresh'),
        ('env.SYNC_BACKFILL_TASKS_QUEUE', 'sync-backfill', 'sync-backfill-fresh'),
    }
    assert plan.blockers == []


def test_env_change_is_blocked_when_template_carries_an_unqualified_image():
    fake = FakeGcloud()
    _live_matching(fake)
    svc = fake.services['backend-sync-backfill']
    svc['template']['containers'][0]['image'] = 'gcr.io/p/backend:failed99'
    for item in next(iter(svc['revisions'].values()))['containers'][0]['env']:
        if item['name'] == 'SYNC_TASKS_QUEUE':
            item['value'] = 'sync-backfill'
    plan = ops_train.build_plan(_spec(QUEUE_SPEC), fake)
    assert any('template differs' in b and 'backend.image' in b for b in plan.blockers)
    with pytest.raises(ops_train.OpsError, match='blocked'):
        ops_train.apply_plan(_spec(QUEUE_SPEC), plan, fake, 'cfg-abc1234-1')
    assert fake.mutations() == []


def test_template_env_drift_outside_ops_keys_blocks_but_ops_keys_do_not():
    fake = FakeGcloud()
    _live_matching(fake)
    svc = fake.services['backend-sync-backfill']
    serving = next(iter(svc['revisions'].values()))
    for item in serving['containers'][0]['env']:
        if item['name'] == 'SYNC_TASKS_QUEUE':
            item['value'] = 'sync-backfill'
    assert ops_train.build_plan(_spec(QUEUE_SPEC), fake).blockers == []
    svc['template']['containers'][0]['env'].append({'name': 'NEW_FLAG', 'value': 'true'})
    blockers = ops_train.build_plan(_spec(QUEUE_SPEC), fake).blockers
    assert blockers and 'backend.env.NEW_FLAG' in blockers[0]
    assert 'true' not in blockers[0]


def test_split_traffic_blocks():
    fake = FakeGcloud()
    _live_matching(fake)
    fake.services['backend-sync-backfill']['traffic'] = [
        {'revisionName': 'a', 'percent': 50},
        {'revisionName': 'b', 'percent': 50},
    ]
    plan = ops_train.build_plan(_spec(QUEUE_SPEC), fake)
    assert any('not 100% on one revision' in b for b in plan.blockers)


@pytest.mark.parametrize('live, desired', [(48, 40), (4, 8), (None, 40)])
def test_controller_owned_scale_is_only_clamped_to_bounds(live, desired):
    fake = FakeGcloud()
    _live_matching(fake)
    annotations = fake.services['backend-sync-backfill']['annotations']
    annotations.pop(ops_train.MAX_SCALE, None)
    if live is not None:
        annotations[ops_train.MAX_SCALE] = str(live)
    plan = ops_train.build_plan(_spec(QUEUE_SPEC), fake)
    assert [(c.field, c.action, c.desired) for c in plan.changes] == [('max_instances', 'clamp', desired)]


def test_unreadable_queues_block_instead_of_raising():
    fake = FakeGcloud()
    _live_matching(fake)
    fake.queues_readable = False
    plan = ops_train.build_plan(_spec(QUEUE_SPEC), fake)
    assert plan.blockers == ['cloud_tasks: queues unreadable (PERMISSION_DENIED)']


def test_paused_queue_blocks():
    fake = FakeGcloud()
    _live_matching(fake)
    fake.queues['sync-backfill-fresh']['state'] = 'PAUSED'
    assert any('PAUSED' in b for b in ops_train.build_plan(_spec(QUEUE_SPEC), fake).blockers)


def test_queue_values_compare_after_normalization():
    fake = FakeGcloud()
    _live_matching(fake)
    fake.queues['sync-backfill-fresh']['rateLimits']['maxDispatchesPerSecond'] = 15
    fake.queues['sync-backfill-fresh']['retryConfig']['minBackoff'] = '5.000s'
    assert ops_train.build_plan(_spec(QUEUE_SPEC), fake).changes == []


# ----------------------------------------------------------------------------- apply + verify


def test_apply_routes_pinned_backfill_to_the_new_revision_and_verifies():
    """10-19 04:52Z: backend-sync-backfill pins traffic, so an unrouted env update never serves."""

    fake = FakeGcloud()
    _live_matching(fake)
    svc = fake.services['backend-sync-backfill']
    for container in (svc['template'], *svc['revisions'].values()):
        for item in container['containers'][0]['env']:
            if item['name'].endswith('QUEUE'):
                item['value'] = 'sync-backfill'
    spec = _spec(QUEUE_SPEC)
    plan = ops_train.build_plan(spec, fake)
    applied = ops_train.apply_plan(spec, plan, fake, 'cfg-abc1234-77')
    assert applied == [
        'cloud_run/backend-sync-backfill',
        'traffic/backend-sync-backfill=backend-sync-backfill-cfg-abc1234-77',
    ]
    update, traffic = fake.mutations()
    assert '--revision-suffix=cfg-abc1234-77' in update
    assert (
        '--update-env-vars=SYNC_BACKFILL_TASKS_QUEUE=sync-backfill-fresh,SYNC_TASKS_QUEUE=sync-backfill-fresh' in update
    )
    assert '--to-revisions=backend-sync-backfill-cfg-abc1234-77=100' in traffic
    after = ops_train.verify_applied(spec, plan, fake, 'cfg-abc1234-77')
    assert after.changes == [] and after.blockers == []


def test_verify_fails_when_the_new_revision_does_not_serve():
    fake = FakeGcloud()
    _live_matching(fake)
    svc = fake.services['backend-sync-backfill']
    for container in (svc['template'], *svc['revisions'].values()):
        for item in container['containers'][0]['env']:
            if item['name'] == 'SYNC_TASKS_QUEUE':
                item['value'] = 'sync-backfill'
    spec = _spec(QUEUE_SPEC)
    plan = ops_train.build_plan(spec, fake)
    original_run = fake.run

    def run_without_traffic(args):
        if args[:3] == ['run', 'services', 'update-traffic']:
            fake.calls.append(list(args))
            return None
        return original_run(args)

    fake.run = run_without_traffic  # type: ignore[method-assign]
    ops_train.apply_plan(spec, plan, fake, 'cfg-abc1234-78')
    after = ops_train.verify_applied(spec, plan, fake, 'cfg-abc1234-78')
    assert any('expected backend-sync-backfill-cfg-abc1234-78' in b for b in after.blockers)


def test_scale_only_change_creates_no_revision_and_moves_no_traffic():
    fake = FakeGcloud()
    _live_matching(fake)
    fake.services['backend-sync-backfill']['annotations'][ops_train.MAX_SCALE] = '60'
    spec = _spec(QUEUE_SPEC)
    plan = ops_train.build_plan(spec, fake)
    ops_train.apply_plan(spec, plan, fake, 'cfg-x')
    (update,) = fake.mutations()
    assert '--max=40' in update
    assert not any(arg.startswith(('--update-env-vars', '--revision-suffix')) for arg in update)


def test_missing_queue_is_created_with_every_declared_field():
    fake = FakeGcloud()
    _live_matching(fake)
    del fake.queues['sync-backfill-fresh']
    spec = _spec(QUEUE_SPEC)
    plan = ops_train.build_plan(spec, fake)
    assert [(c.name, c.action) for c in plan.changes] == [('sync-backfill-fresh', 'create')]
    ops_train.apply_plan(spec, plan, fake, 'cfg-x')
    (create,) = fake.mutations()
    assert create[:4] == ['tasks', 'queues', 'create', 'sync-backfill-fresh']
    assert {
        '--max-concurrent-dispatches=90',
        '--max-dispatches-per-second=15',
        '--min-backoff=5s',
        '--max-backoff=60s',
    } <= set(create)


def test_queue_update_sends_only_changed_fields_and_unlimited_attempts():
    spec = _spec("""
cloud_tasks:
  enrichment:
    max_concurrent_dispatches: 50
    max_attempts: -1
""")
    fake = FakeGcloud()
    fake.queues['enrichment'] = {
        'state': 'RUNNING',
        'rateLimits': {'maxConcurrentDispatches': 50},
        'retryConfig': {'maxAttempts': 5},
    }
    plan = ops_train.build_plan(spec, fake)
    ops_train.apply_plan(spec, plan, fake, 'cfg-x')
    (update,) = fake.mutations()
    assert update[:4] == ['tasks', 'queues', 'update', 'enrichment']
    assert update[4:] == ['--project=based-hardware', '--location=us-central1', '--max-attempts=unlimited']
    assert ops_train.build_plan(spec, fake).changes == []


def test_disabled_queue_is_neither_read_nor_created():
    spec = _spec('cloud_tasks:\n  enrichment:\n    enabled: false\n    max_attempts: 3\n')
    fake = FakeGcloud()
    plan = ops_train.build_plan(spec, fake)
    assert plan.changes == [] and fake.calls == []


def test_render_env_lists_ops_values_for_the_train():
    spec = ops_train.load_ops('prod')
    backfill = ops_train.render_env(spec, 'backend-sync-backfill')
    assert backfill == sorted(backfill)
    assert {'SYNC_BACKFILL_TASKS_QUEUE=sync-backfill-fresh', 'SYNC_TASKS_QUEUE=sync-backfill-fresh'} <= set(backfill)
    assert 'FAIR_USE_ENABLED=true' in ops_train.render_env(spec, 'backend')
    assert ops_train.render_env(spec, 'pusher') == []


def test_cli_exit_codes(tmp_path, capsys):
    (tmp_path / 'prod.yaml').write_text(PROD_HEADER + QUEUE_SPEC)
    fake = FakeGcloud()
    _live_matching(fake)
    assert ops_train.main(['plan', '--env', 'prod'], gcloud=fake, ops_dir=tmp_path) == ops_train.EXIT_OK
    fake.queues['sync-backfill-fresh']['rateLimits']['maxConcurrentDispatches'] = 60
    report = tmp_path / 'out' / 'plan.json'
    assert ops_train.main(['plan', '--env', 'prod', '--report', str(report)], gcloud=fake, ops_dir=tmp_path) == 2
    assert yaml.safe_load(report.read_text())['plan']['changes'][0]['field'] == 'max_concurrent_dispatches'
    assert ops_train.main(['apply', '--env', 'prod', '--revision-suffix', 'cfg-1'], gcloud=fake, ops_dir=tmp_path) == 0
    assert 'VERIFIED' in capsys.readouterr().out
    fake.queues_readable = False
    assert ops_train.main(['apply', '--env', 'prod', '--revision-suffix', 'cfg-2'], gcloud=fake, ops_dir=tmp_path) == 3


# ----------------------------------------------------------------------------- workflow contract


def _workflow() -> dict[str, Any]:
    return yaml.safe_load((ROOT / '.github/workflows/config_train.yml').read_text())


def test_workflow_keeps_the_prod_approval_gate_and_the_train_lock():
    workflow = _workflow()
    on = workflow.get(True) or workflow['on']
    assert set(on) == {'workflow_dispatch'}
    inputs = on['workflow_dispatch']['inputs']
    assert inputs['environment']['options'] == ['staging', 'prod']
    assert inputs['mode']['default'] == 'plan'
    assert "'prod-train'" in workflow['concurrency']['group']
    assert workflow['concurrency']['cancel-in-progress'] is False
    (job,) = workflow['jobs'].values()
    assert job['environment'] == "${{ github.event.inputs.environment == 'prod' && 'prod' || 'development' }}"
    runs = '\n'.join(step.get('run', '') for step in job['steps'])
    assert 'backend/scripts/ops_train.py plan' in runs
    assert 'backend/scripts/ops_train.py apply' in runs
    assert 'merge-base --is-ancestor' in runs


def _ops_queue_step() -> str:
    action = yaml.safe_load((ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text())
    return next(step for step in action['runs']['steps'] if step.get('id') == 'ops-queues')['run']


@pytest.mark.parametrize(
    'project, expected',
    [
        ('based-hardware', ('sync-backfill-fresh', 'sync-backfill-fresh')),
        ('based-hardware-dev', ('sync-backfill', 'sync-backfill')),
    ],
)
def test_train_takes_backfill_queues_from_the_ops_file(tmp_path, project, expected):
    """A train must not re-point the backfill worker at a queue an operator retired (10-19 04:52Z)."""

    import os
    import subprocess

    shim = tmp_path / 'python3'
    shim.write_text(f'#!/bin/sh\n[ "$1" = "-m" ] && exit 0\nexec {sys.executable} "$@"\n')
    shim.chmod(0o755)
    output = tmp_path / 'out'
    script = _ops_queue_step().replace("${{ inputs.project_id }}", project).replace("${{ inputs.service }}", 'backend')
    result = subprocess.run(
        ['bash', '-c', script],
        env={
            **os.environ,
            'PATH': f'{tmp_path}:{os.environ["PATH"]}',
            'DEPLOY_CONTROL_SCRIPTS': str(BACKEND / 'scripts'),
            'GITHUB_OUTPUT': str(output),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    values = dict(line.split('=', 1) for line in output.read_text().splitlines())
    assert (values['backfill_queue'], values['worker_queue']) == expected


def test_prod_train_leaves_the_backfill_queue_to_the_ops_file(tmp_path):
    """One owner for the live backfill queue: the config-train, never the train's reconcile."""

    import os
    import subprocess

    action = yaml.safe_load((ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text())
    step = next(s for s in action['runs']['steps'] if s.get('name') == 'Reconcile bounded sync backfill queue')
    gcloud = tmp_path / 'gcloud'
    gcloud.write_text('#!/bin/sh\necho "$@" >> "$CALLS"\n')
    gcloud.chmod(0o755)
    calls = tmp_path / 'calls'
    script = (
        step['run'].replace('${{ inputs.project_id }}', 'based-hardware').replace('${{ inputs.region }}', 'us-central1')
    )
    result = subprocess.run(
        ['bash', '-c', script],
        env={
            **os.environ,
            'PATH': f'{tmp_path}:{os.environ["PATH"]}',
            'CALLS': str(calls),
            'BACKFILL_MAX_CONCURRENT_DISPATCHES': '90',
            'BACKFILL_ENV': 'SYNC_BACKFILL_TASKS_QUEUE=sync-backfill-fresh',
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not calls.exists(), 'a prod train must not create or update the ops-owned backfill queue'


@pytest.fixture(scope='module')
def prod_manifest_services():
    # Parsed in fixture setup: the 4.5k-line manifest exceeds the fast-unit call-phase budget.
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    manifest = yaml.load((BACKEND / 'deploy/runtime_env.yaml').read_text(), Loader=loader)
    return manifest['environments']['prod']['cloud_run']['services']


def test_manifest_queue_values_agree_with_the_ops_file(prod_manifest_services):
    """Until trains apply ops env directly, a prod key both files declare must carry the same value.

    A disagreement means the next train and the next config-train write different queues.
    """

    services = prod_manifest_services
    checked = 0
    for svc in ops_train.load_ops('prod').services:
        env = services.get(svc.name, {}).get('env', {})
        for key, value in svc.env.items():
            declared = env.get(key)
            if isinstance(declared, dict) and 'value' in declared:
                assert (
                    str(declared['value']) == value
                ), f'{svc.name}.{key}: manifest {declared["value"]!r} != ops {value!r}'
                checked += 1
    assert checked >= 5  # the five queue re-points (#22460) are declared in both today


def test_unnamed_template_container_matches_the_revision_cloud_run_named():
    """Staging 10-19: template container `#0` vs serving `backend-1` was reported as drift."""

    template = {'containers': [{'image': 'i', 'env': [{'name': 'A', 'value': '1'}]}]}
    serving = {'containers': [{'name': 'backend-1', 'image': 'i', 'env': [{'name': 'A', 'value': '1'}]}]}
    assert ops_train.template_drift(template, serving, set()) == []
    serving['containers'][0]['image'] = 'other'
    assert ops_train.template_drift(template, serving, set()) == ['#0.image']
    renamed = {'containers': [{'name': 'x', 'image': 'i'}]}
    assert ops_train.template_drift(renamed, {'containers': [{'name': 'y', 'image': 'i'}]}, set())


@pytest.mark.parametrize(
    'field, value',
    [
        ('serviceAccountName', 'other@sa'),
        ('containerConcurrency', 6),
        ('timeoutSeconds', 60),
        ('volumes', [{'name': 'v'}]),
    ],
)
def test_revision_level_template_drift_blocks(field, value):
    """M1 L07-2: an env apply ships the whole template, so revision-level fields count too."""

    container = {'name': 'c', 'image': 'i', 'env': [{'name': 'OPS', 'value': '1'}]}
    serving = {'serviceAccountName': 'sa', 'containerConcurrency': 80, 'timeoutSeconds': 300, 'containers': [container]}
    template = {**serving, field: value, 'containers': [{**container, 'env': [{'name': 'OPS', 'value': '2'}]}]}
    assert ops_train.template_drift(template, serving, {'OPS'}) == [field]


def test_container_probe_and_mount_drift_blocks():
    serving = {'containers': [{'name': 'c', 'image': 'i'}]}
    template = {'containers': [{'name': 'c', 'image': 'i', 'volumeMounts': [{'name': 'v', 'mountPath': '/m'}]}]}
    assert ops_train.template_drift(template, serving, set()) == ['c.volumeMounts']


@pytest.mark.parametrize('env', ['prod', 'staging'])
def test_sync_queues_carry_the_five_attempt_contract(env):
    """M1 L07-4: sync's 409 leaves the retry to the queue, and utils/cloud_tasks.py
    get_sync_tasks_max_attempts mirrors 5. The config-train is the only writer of that cap."""

    source = (BACKEND / 'utils/cloud_tasks.py').read_text()
    default = re.search(r"os\.getenv\('SYNC_TASKS_MAX_ATTEMPTS', '(\d+)'\)", source)
    assert default, 'get_sync_tasks_max_attempts default moved'
    queues = yaml.safe_load((BACKEND / f'deploy/ops/{env}.yaml').read_text())['cloud_tasks']
    sync_queues = {name: q for name, q in queues.items() if 'sync-' in name}
    assert len(sync_queues) == 2
    for name, queue in sync_queues.items():
        assert queue.get('max_attempts') == int(default.group(1)) == 5, name


def test_staging_enrichment_stays_off_until_prod_turns_it_on():
    """M1 L07-5: a missing `enabled` defaults to true, which would create an unlimited-retry queue."""

    prod = yaml.safe_load((BACKEND / 'deploy/ops/prod.yaml').read_text())['cloud_tasks']
    staging = yaml.safe_load((BACKEND / 'deploy/ops/staging.yaml').read_text())['cloud_tasks']
    for name, queue in prod.items():
        assert staging[f'staging-{name}'].get('enabled', True) == queue.get('enabled', True), name
