"""Feature activation manifest checker: pure verdicts over fixtures, and the read-only collector with fakes."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import activation_check as check
from scripts import activation_collect as collect

BACKEND = Path(__file__).resolve().parents[2]
MANIFEST_PATH = BACKEND / 'deploy' / 'activation' / 'conversations-v3.yaml'
FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'activation'


@pytest.fixture(scope='module')
def manifest():
    return check.load_manifest(MANIFEST_PATH)


def _state(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def _by_status(verdict, status, controlled=True):
    return {r.id for r in verdict.results if r.status == status and r.controlled == controlled}


# ---------------------------------------------------------------------------------------------- fixtures


def test_2026_11_17_state_reports_each_escape(manifest):
    verdict = check.evaluate(manifest, _state('state-2026-11-17.json'))

    assert verdict.verdict == check.BLOCKED and verdict.exit_code == 1
    missing = _by_status(verdict, check.MISSING)
    assert missing == {
        # Stale gateway: older than the commit that adds the v3 lanes, and the lanes are not served.
        'service:llm-gateway:contains:012329830a9e',
        'lane:omi:auto:conversation-v3-outline',
        'lane:omi:auto:conversation-v3-summary',
        'lane:omi:auto:conversation-v3-summary-open',
        # Version skew: pusher's 11-09 image predates v3-aware finalization and admission.
        'service:pusher:contains:012329830a9e',
        'service:pusher:contains:156b50921d7e',
        # Pusher lacks the task binding listen has.
        'env:v3-task-binding:pusher:SYNC_TASKS_PROJECT',
        'env:v3-task-binding:pusher:SYNC_TASKS_LOCATION',
        'env-equal:v3-task-binding:SYNC_TASKS_PROJECT',
        'env-equal:v3-task-binding:SYNC_TASKS_LOCATION',
        # Infra never created in prod.
        'queue:conversations-v3',
        'scheduler-job:conversations-v3-sweep',
        'scheduler-job:conversations-v3-legacy-users',
    }
    # The backfill queue is missing too, but admission does not use it: reported, not blocking.
    assert _by_status(verdict, check.MISSING, controlled=False) == {'queue:conversations-v3-backfill'}


def test_correct_state_passes(manifest):
    verdict = check.evaluate(manifest, _state('state-ready.json'))

    assert verdict.verdict == check.READY and verdict.exit_code == 0
    assert not _by_status(verdict, check.MISSING) and not _by_status(verdict, check.UNKNOWN)
    # Firestore indexes are named as owned elsewhere: always unknown here, never blocking.
    assert _by_status(verdict, check.UNKNOWN, controlled=False) == {'external:firestore-indexes'}


def test_cli_exit_codes_and_text(capsys):
    args = ['--manifest', str(MANIFEST_PATH), '--state']
    assert check.main(args + [str(FIXTURES / 'state-ready.json')]) == 0
    assert check.main(args + [str(FIXTURES / 'state-2026-11-17.json')]) == 1
    out = capsys.readouterr().out
    assert 'verdict=BLOCKED' in out and 'MISSING   queue:conversations-v3 -- does not exist' in out
    assert check.main(args + [str(FIXTURES / 'state-ready.json'), '--json']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['verdict'] == 'READY' and payload['counts']['missing'] == 0


def test_report_never_prints_env_values(manifest):
    verdict = check.evaluate(manifest, _state('state-2026-11-17.json'))
    text = check.render_text(verdict) + json.dumps(verdict.to_json())
    assert 'based-hardware' not in text and 'us-central1' not in text and 'sync-tasks-invoker' not in text


# ---------------------------------------------------------------------------------------------- unknown


def test_unreadable_service_is_unknown_never_satisfied(manifest):
    state = _state('state-ready.json')
    state['services']['pusher'] = {'kind': 'gke', 'error': 'ReadError: no running pods'}

    verdict = check.evaluate(manifest, state)

    assert verdict.verdict == check.UNDETERMINED and verdict.exit_code == 2
    unknown = _by_status(verdict, check.UNKNOWN)
    assert 'service:pusher:contains:012329830a9e' in unknown
    assert 'env:v3-task-binding:pusher:SYNC_TASKS_PROJECT' in unknown
    assert not any(r.status == check.SATISFIED and ':pusher:' in r.id for r in verdict.results)


def test_missing_beats_unknown(manifest):
    state = _state('state-2026-11-17.json')
    state['queues'] = {'_error': 'tasks queues list: gcloud exit 1'}
    verdict = check.evaluate(manifest, state)
    assert verdict.verdict == check.BLOCKED
    assert 'queue:conversations-v3' in _by_status(verdict, check.UNKNOWN)


def test_unknown_ancestry_and_unread_lanes(manifest):
    state = _state('state-ready.json')
    gateway = state['services']['llm-gateway']['serving'][0]
    gateway['source_sha'] = 'f' * 40  # not in the ancestry table: the collector could not answer
    del gateway['lanes']
    gateway['lanes_error'] = 'serving source unknown'

    verdict = check.evaluate(manifest, state)

    assert verdict.verdict == check.UNDETERMINED
    assert {'service:llm-gateway:contains:012329830a9e', 'lane:omi:auto:conversation-v3-outline'} <= _by_status(
        verdict, check.UNKNOWN
    )


def test_uncontrolled_requirements_never_change_the_exit(manifest):
    state = _state('state-ready.json')
    state['queues']['conversations-v3-backfill'] = {'error': 'permission denied'}
    assert check.evaluate(manifest, state).verdict == check.READY
    state['queues']['conversations-v3-backfill'] = {'exists': False}
    assert check.evaluate(manifest, state).verdict == check.READY


def test_split_traffic_needs_every_serving_revision(manifest):
    state = _state('state-ready.json')
    old = dict(state['services']['backend']['serving'][0], name='backend-00099-old', source_sha='a' * 40, percent=10)
    state['services']['backend']['serving'][0]['percent'] = 90
    state['services']['backend']['serving'].append(old)
    state['ancestry']['a' * 40] = {'012329830a9ed7b65642401b7f2af827af7cfb2c': False}

    verdict = check.evaluate(manifest, state)

    result = next(r for r in verdict.results if r.id == 'service:backend:contains:012329830a9e')
    assert result.status == check.MISSING and 'backend-00099-old@10%' in result.detail


# ---------------------------------------------------------------------------------------------- env


def test_stage_skew_and_defaults(manifest):
    state = _state('state-ready.json')
    state['services']['pusher']['serving'][0]['env']['CONVERSATIONS_V3_STAGE'] = {'value': 'cohort'}
    verdict = check.evaluate(manifest, state)
    result = next(r for r in verdict.results if r.id == 'env-equal:v3-stage:CONVERSATIONS_V3_STAGE')
    assert result.status == check.MISSING and '[pusher]' in result.detail and 'cohort' not in result.detail

    # An absent key takes the code default (beta), which agrees with the others.
    state = _state('state-ready.json')
    del state['services']['desktop-backend']['serving'][0]['env']['CONVERSATIONS_V3_STAGE']
    assert check.evaluate(manifest, state).verdict == check.READY


def test_placeholder_value_counts_as_unset(manifest):
    state = _state('state-ready.json')
    state['services']['backend-sync']['serving'][0]['env']['OMI_LLM_GATEWAY_URL'] = {'value': 'http://127.0.0.1:9'}
    verdict = check.evaluate(manifest, state)
    assert 'env:v3-gateway-endpoint:backend-sync:OMI_LLM_GATEWAY_URL' in _by_status(verdict, check.MISSING)


def test_any_of_and_secret_refs(manifest):
    state = _state('state-ready.json')
    env = state['services']['backend-listen']['serving'][0]['env']
    del env['SYNC_TASKS_HANDLER_URL']
    env['CONVERSATIONS_V3_TASKS_URL'] = {'value': 'https://sync.example'}
    assert check.evaluate(manifest, state).verdict == check.READY

    del env['CONVERSATIONS_V3_TASKS_URL']
    env['SYNC_TASKS_HANDLER_URL'] = {'unknown': 'may come from secret x'}
    verdict = check.evaluate(manifest, state)
    assert 'env:v3-task-target:backend-listen:CONVERSATIONS_V3_TASKS_URL|SYNC_TASKS_HANDLER_URL' in _by_status(
        verdict, check.UNKNOWN
    )

    state = _state('state-ready.json')
    for runtime in ('pusher', 'backend-listen'):
        state['services'][runtime]['serving'][0]['env']['SYNC_TASKS_INVOKER_SA'] = {'secret_ref': 's:invoker'}
    verdict = check.evaluate(manifest, state)
    result = next(r for r in verdict.results if r.id == 'env-equal:v3-task-binding:SYNC_TASKS_INVOKER_SA')
    assert result.status == check.MISSING  # a secret ref is not the literal the Cloud Run services carry


# ---------------------------------------------------------------------------------------------- order


def test_order_defers_the_moving_service_and_later_steps(manifest):
    state = _state('state-2026-11-17.json')

    before_pusher = check.evaluate(manifest, state, 'pusher')
    deferred = _by_status(before_pusher, check.DEFERRED)
    assert 'service:pusher:contains:012329830a9e' in deferred
    assert 'env:v3-task-binding:backend-listen:SYNC_TASKS_PROJECT' in deferred
    # The gateway moves before pusher, so its gaps already block pusher's move.
    assert 'lane:omi:auto:conversation-v3-outline' in _by_status(before_pusher, check.MISSING)
    # Infra objects depend on no service: due at every step.
    assert 'queue:conversations-v3' in _by_status(before_pusher, check.MISSING)

    before_gateway = check.evaluate(manifest, state, 'llm-gateway')
    assert 'lane:omi:auto:conversation-v3-outline' in _by_status(before_gateway, check.DEFERRED)

    with pytest.raises(check.InvalidInput):
        check.evaluate(manifest, state, 'diarizer')


def test_infra_before_field(manifest):
    data = copy.deepcopy(manifest)
    data['queues'][0]['before'] = 'backend-listen'
    state = _state('state-2026-11-17.json')
    assert 'queue:conversations-v3' in _by_status(check.evaluate(data, state, 'pusher'), check.DEFERRED)
    assert 'queue:conversations-v3' in _by_status(check.evaluate(data, state, 'backend-listen'), check.MISSING)


# ---------------------------------------------------------------------------------------------- manifest


def test_v3_manifest_matches_the_code_it_declares(manifest):
    """The manifest names real queues, jobs, lanes and env keys; drift from the code fails here."""
    import yaml

    ops = yaml.safe_load((BACKEND / 'deploy/ops/prod.yaml').read_text())
    assert {q['name'] for q in manifest['queues']} <= set(ops['cloud_tasks'])
    jobs = yaml.safe_load((BACKEND / 'deploy/scheduler/jobs.yaml').read_text())['environments']['prod']['jobs']
    assert {j['name'] for j in manifest['scheduler_jobs']} <= {job['name'] for job in jobs}
    overrides = yaml.safe_load((BACKEND / 'llm_gateway/config/generated_route_overrides.yaml').read_text())
    features = {item['feature'] for item in overrides['generated_route_overrides']}
    assert {lane.removeprefix('omi:auto:').replace('-', '_') for lane in manifest['gateway_lanes']['lanes']} <= features
    triggers = (BACKEND / 'utils/conversations/v3/triggers.py').read_text()
    assert "'conversations-v3'" in triggers and 'CONVERSATIONS_V3_TASKS_URL' in triggers
    models = (BACKEND / 'utils/conversations/v3/models.py').read_text()
    for feature in ('conversation_v3_outline', 'conversation_v3_summary', 'conv_action_items'):
        assert f"'{feature}'" in models


def test_v3_manifest_env_is_declared_in_the_prod_runtime_source(manifest):
    """Each required key reaches each runtime in the composed prod runtime env (direct, ConfigMap or envFrom)."""
    import yaml

    # The composed manifest is large enough to exceed the unit CPU budget with the pure Python parser.
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    prod = yaml.load((BACKEND / 'deploy/runtime_env.yaml').read_text(), Loader=loader)['environments']['prod']
    shared_config_map = set((prod['gke'].get('config_map') or {}).get('entries', {}))

    def declared(runtime):
        if runtime in prod['gke']:
            return set(prod['gke'][runtime].get('env', {})) | shared_config_map
        service = prod['cloud_run']['services'].get(runtime)
        return None if service is None else set(service.get('env', {}))

    for req in manifest['env']:
        # Keys with a code default are checked too: the source must still declare them for every runtime.
        for runtime in req['runtimes']:
            keys = declared(runtime)
            if keys is None:
                continue  # released outside runtime_env (desktop-backend)
            wanted = req.get('keys') or req.get('any_of')
            hits = [k for k in wanted if k in keys]
            assert hits if req.get('any_of') else hits == wanted, (req['id'], runtime, set(wanted) - keys)


@pytest.mark.parametrize(
    'mutate',
    [
        lambda m: m.update(schema_version=2),
        lambda m: m['services']['pusher']['contains'].append({'commit': 'abc1234'}),
        lambda m: m['order'].append(['pusher']),
        lambda m: m['order'].append(['nope']),
        lambda m: m['env'].append({'id': 'x', 'keys': ['A'], 'any_of': ['B'], 'runtimes': ['backend']}),
        lambda m: m['env'].append({'id': 'x', 'keys': ['A'], 'runtimes': ['nope']}),
        lambda m: m['queues'].append({'name': 'q', 'before': 'nope'}),
    ],
)
def test_invalid_manifest_is_refused(manifest, mutate):
    data = copy.deepcopy(manifest)
    mutate(data)
    with pytest.raises(check.InvalidInput):
        check.validate_manifest(data)


def test_invalid_state_exits_3(tmp_path):
    bad = tmp_path / 'state.json'
    bad.write_text(json.dumps({'schema_version': 9}))
    assert check.main(['--manifest', str(MANIFEST_PATH), '--state', str(bad)]) == check.EXIT_INVALID


# ---------------------------------------------------------------------------------------------- collector


class FakeGit:
    def __init__(self, ancestors, files=None):
        self.ancestors, self.files = ancestors, files or {}

    def resolve(self, ref):
        for sha in self.ancestors:
            if sha.startswith(ref):
                return sha
        raise collect.ReadError(f'commit {ref[:12]} not in local repo (git fetch origin)')

    def contains(self, source, commit):
        return commit in self.ancestors[self.resolve(source)]

    def show(self, sha, path):
        if (sha, path) not in self.files:
            raise collect.ReadError('git exit 128')
        return self.files[(sha, path)]


class FakeRegistry:
    def __init__(self, sources):
        self.sources = sources

    def source(self, repository, digest):
        if (repository, digest) not in self.sources:
            raise collect.ReadError('image has no single commit tag or revision label')
        return self.sources[(repository, digest)]


NEW = '1' * 40
OLD = '2' * 40
DIG_NEW = 'sha256:' + 'a' * 64
DIG_OLD = 'sha256:' + 'b' * 64


def _fake_runner(responses):
    calls = []

    def runner(argv):
        calls.append(argv)
        for key, value in responses.items():
            if all(part in argv for part in key):
                if isinstance(value, Exception):
                    raise value
                return json.dumps(value)
        raise collect.ReadError(f'{argv[0]} exit 1')

    return runner, calls


def _revision(name, image, env):
    return {'metadata': {'name': name}, 'spec': {'containers': [{'image': image, 'env': env}]}, 'status': {}}


def test_collector_reads_traffic_not_spec_and_never_secrets(manifest):
    service_doc = {
        'spec': {'traffic': [{'latestRevision': True, 'percent': 100}]},  # the spec is ignored
        'status': {
            'traffic': [
                {'revisionName': 'backend-00002-new', 'percent': 90},
                {'revisionName': 'backend-00001-old', 'percent': 10},
                {'revisionName': 'backend-00000-tag', 'percent': 0, 'tag': 'canary'},
            ]
        },
    }
    env = [
        {'name': 'SYNC_TASKS_PROJECT', 'value': 'p'},
        {'name': 'SYNC_TASKS_INVOKER_SA', 'valueFrom': {'secretKeyRef': {'name': 'sec', 'key': 'k'}}},
        {'name': 'UNRELATED_SECRET_TOKEN', 'value': 'do-not-copy'},
        {'name': 'OMI_BACKEND_RELEASE_SHA', 'value': 'stale-release'},
    ]
    runner, calls = _fake_runner(
        {
            ('services', 'describe', 'backend'): service_doc,
            ('revisions', 'describe', 'backend-00002-new'): _revision(
                'backend-00002-new', 'gcr.io/p/backend:' + NEW[:7], env
            ),
            ('revisions', 'describe', 'backend-00001-old'): _revision(
                'backend-00001-old', 'gcr.io/p/backend@' + DIG_OLD, env
            ),
        }
    )
    collector = collect.Collector(
        'proj',
        'us-central1',
        FakeGit({NEW: set(), OLD: set()}),
        runner,
        registry=FakeRegistry({('gcr.io/p/backend', DIG_OLD): OLD}),
    )

    result = collector.cloud_run('backend', {'SYNC_TASKS_PROJECT', 'SYNC_TASKS_INVOKER_SA'})

    by_name = {u['name']: u for u in result['serving']}
    assert set(by_name) == {'backend-00002-new', 'backend-00001-old'}
    assert by_name['backend-00002-new']['source_sha'] == NEW and by_name['backend-00001-old']['source_sha'] == OLD
    assert by_name['backend-00002-new']['env'] == {
        'SYNC_TASKS_PROJECT': {'value': 'p'},
        'SYNC_TASKS_INVOKER_SA': {'secret_ref': 'sec:k'},
    }
    assert by_name['backend-00002-new']['release_env'] == 'stale-release'  # recorded, never used as identity
    assert not any('secrets' in argv for argv in calls)


def _gke_pod(app, digest, phase='Running'):
    return {
        'spec': {'containers': [app]},
        'status': {
            'phase': phase,
            'containerStatuses': [{'name': app['name'], 'imageID': app['image'].split('@')[0] + '@' + digest}],
        },
    }


def test_collector_gke_counts_pods_and_resolves_promoted_digests():
    deployment = {'spec': {'selector': {'matchLabels': {'app': 'pusher'}}}}
    app = {
        'name': 'pusher',
        'image': 'gcr.io/prod/pusher@' + DIG_NEW,
        'envFrom': [{'configMapRef': {'name': 'shared'}, 'prefix': 'SYNC_'}],
        'env': [
            {'name': 'CONVERSATIONS_V3_STAGE', 'valueFrom': {'configMapKeyRef': {'name': 'shared', 'key': 'STAGE'}}},
            {'name': 'SYNC_TASKS_PROJECT', 'value': 'p'},
            {'name': 'INVOKER', 'valueFrom': {'secretKeyRef': {'name': 'invoker', 'key': 'email'}}},
            {
                'name': 'OPTIONAL',
                'valueFrom': {'secretKeyRef': {'name': 'invoker', 'key': 'optional', 'optional': True}},
            },
            {'name': 'EXPANDED', 'value': '$(SYNC_TASKS_PROJECT)'},
        ],
    }
    runner, calls = _fake_runner(
        {
            ('get', 'deployment', 'prod-omi-pusher'): deployment,
            ('get', 'pods'): {
                'items': [
                    _gke_pod(app, DIG_NEW),
                    _gke_pod(app, DIG_NEW),
                    _gke_pod(app, DIG_OLD),
                    _gke_pod(app, DIG_OLD, 'Pending'),
                ]
            },
        }
    )
    collector = collect.Collector(
        'proj',
        'us-central1',
        FakeGit({NEW: set(), OLD: set()}),
        runner,
        registry=FakeRegistry({('gcr.io/prod/pusher', DIG_OLD): OLD}),
        promoted_registry=FakeRegistry({('gcr.io/dev/pusher', DIG_NEW): NEW[:7]}),
    )

    result = collector.gke(
        'ns',
        'prod-omi-pusher',
        {
            'CONVERSATIONS_V3_STAGE',
            'SYNC_TASKS_PROJECT',
            'SYNC_TASKS_HANDLER_URL',
            'INVOKER',
            'UNRELATED',
            'EXPANDED',
            'OPTIONAL',
        },
        ['gcr.io/dev/pusher'],
    )

    units = {u['source_sha']: u for u in result['serving']}
    assert set(units) == {NEW, OLD}
    assert units[NEW]['pods'] == 2 and units[OLD]['pods'] == 1
    assert units[NEW]['env'] == {
        'CONVERSATIONS_V3_STAGE': {'unknown': 'ConfigMap value at container startup is unavailable'},
        'SYNC_TASKS_PROJECT': {'value': 'p'},
        'SYNC_TASKS_HANDLER_URL': {'unknown': 'envFrom value at container startup is unavailable'},
        'INVOKER': {'secret_ref': 'invoker:email'},
        'OPTIONAL': {'unknown': 'optional Secret binding at container startup is unavailable'},
        'EXPANDED': {'unknown': 'value depends on container startup'},
    }
    assert [argv[3:5] for argv in calls] == [['get', 'deployment'], ['get', 'pods']]


@pytest.mark.parametrize(
    ('old_binding', 'expected_verdict', 'expected_parity'),
    [
        ({'value': 'off'}, check.BLOCKED, check.MISSING),
        (
            {'valueFrom': {'configMapKeyRef': {'name': 'shared', 'key': 'STAGE'}}},
            check.UNDETERMINED,
            check.UNKNOWN,
        ),
    ],
)
def test_gke_mixed_generation_same_digest_cannot_pass_stage_parity(
    manifest, old_binding, expected_verdict, expected_parity
):
    state = _state('state-ready.json')
    ready_pusher = state['services']['pusher']['serving'][0]
    stage = 'CONVERSATIONS_V3_STAGE'
    new_app = {
        'name': 'pusher',
        'image': 'gcr.io/prod/pusher@' + DIG_NEW,
        'env': [{'name': name, **value} for name, value in ready_pusher['env'].items()],
    }
    old_app = {**new_app, 'env': [entry for entry in new_app['env'] if entry['name'] != stage]}
    old_app['env'].append({'name': stage, **old_binding})
    new_pod = _gke_pod(new_app, DIG_NEW)
    old_pod = _gke_pod(old_app, DIG_NEW)
    deployment = {
        'spec': {'selector': {'matchLabels': {'app': 'pusher'}}, 'template': {'spec': new_pod['spec']}},
    }
    runner, _ = _fake_runner(
        {
            ('get', 'deployment', 'pusher'): deployment,
            ('get', 'pods'): {'items': [new_pod, old_pod]},
            ('get', 'configmap', 'shared'): {'data': {'STAGE': 'beta'}},
        }
    )
    sha = ready_pusher['source_sha']
    collector = collect.Collector(
        'proj',
        'us-central1',
        FakeGit({sha: set()}),
        runner,
        registry=FakeRegistry({('gcr.io/prod/pusher', DIG_NEW): sha}),
    )

    state['services']['pusher'] = collector.gke('ns', 'pusher', collect.manifest_env_keys(manifest)['pusher'])
    units = state['services']['pusher']['serving']
    assert len({u['name'] for u in units}) == 2
    assert [u['pods'] for u in units] == [1, 1]
    verdict = check.evaluate(manifest, state)
    assert verdict.verdict == expected_verdict
    assert f'env-equal:v3-stage:{stage}' in _by_status(verdict, expected_parity)


def _render_prod_gke_deployment(helm, runtime, *values):
    chart = BACKEND / 'charts' / runtime
    return subprocess.run(
        [
            helm,
            'template',
            f'prod-omi-{runtime}',
            str(chart),
            '-f',
            str(chart / f"prod_omi_{runtime.replace('-', '_')}_values.yaml"),
            '--set-string',
            'image.tag=activation-test',
            '--show-only',
            'templates/deployment.yaml',
            *values,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.fixture(scope='module')
def helm():
    executable = shutil.which('helm')
    if executable is None:
        pytest.skip('Helm is required to verify the rendered pod spec')
    return executable


@pytest.fixture
def startup_values():
    env = _state('state-ready.json')['services']['pusher']['serving'][0]['env']
    return {
        **{key: entry['value'] for key, entry in env.items() if key != 'OMI_LLM_GATEWAY_URL'},
        'CONVERSATIONS_V3_TASKS_URL': '',
    }


@pytest.mark.parametrize('runtime', ['pusher', 'backend-listen'])
def test_release_pins_each_startup_value_in_the_pod_spec(manifest, helm, startup_values, runtime):
    import yaml

    baseline = _render_prod_gke_deployment(helm, runtime)
    pinned = _render_prod_gke_deployment(
        helm, runtime, '--set-json', f'conversationsV3StartupEnv={json.dumps(startup_values)}'
    )
    assert baseline.returncode == 0, baseline.stderr
    assert pinned.returncode == 0, pinned.stderr
    old_deployment = yaml.safe_load(baseline.stdout)
    deployment = yaml.safe_load(pinned.stdout)
    old_app = old_deployment['spec']['template']['spec']['containers'][0]
    app = deployment['spec']['template']['spec']['containers'][0]
    assert app['envFrom'] == old_app['envFrom']
    assert [entry for entry in app['env'] if entry['name'] not in startup_values] == [
        entry for entry in old_app['env'] if entry['name'] not in startup_values
    ]
    assert [entry for entry in app['env'] if entry['name'] in startup_values] == [
        {'name': key, 'value': value} for key, value in sorted(startup_values.items())
    ]

    repository = app['image'].rpartition(':')[0]
    state = _state('state-ready.json')
    sha = state['services'][runtime]['serving'][0]['source_sha']
    pods = {'items': [_gke_pod(app, DIG_NEW)]}
    runner, calls = _fake_runner({('get', 'deployment', runtime): deployment, ('get', 'pods'): pods})
    collector = collect.Collector(
        'proj', 'us-central1', FakeGit({sha: set()}), runner, registry=FakeRegistry({(repository, DIG_NEW): sha})
    )
    wanted = collect.manifest_env_keys(manifest)[runtime]
    state['services'][runtime] = collector.gke('ns', runtime, wanted)
    assert check.evaluate(manifest, state).verdict == check.READY

    # A same-image rollout cannot borrow the new spec's values for a legacy pod.
    pods['items'].append(_gke_pod(old_app, DIG_NEW))
    state['services'][runtime] = collector.gke('ns', runtime, wanted)
    verdict = check.evaluate(manifest, state)
    assert verdict.verdict == check.UNDETERMINED
    assert f'env:v3-stage:{runtime}:CONVERSATIONS_V3_STAGE' in _by_status(verdict, check.UNKNOWN)
    assert [argv[3:5] for argv in calls] == [['get', 'deployment'], ['get', 'pods']] * 2


@pytest.mark.parametrize('runtime', ['pusher', 'backend-listen'])
def test_chart_rejects_unapproved_startup_env_key(helm, startup_values, runtime):
    result = _render_prod_gke_deployment(
        helm, runtime, '--set-json', f'conversationsV3StartupEnv={json.dumps({**startup_values, "API_KEY": "test"})}'
    )
    assert result.returncode != 0
    assert 'accepts only the seven conversations-v3 startup keys' in result.stderr


@pytest.mark.parametrize(
    ('overrides', 'private_source'),
    [
        (
            ('--set-json', 'privateSecretEnv.keys=[]', '--set-string', 'privateEnv.CONVERSATIONS_V3_STAGE=off'),
            'privateEnv',
        ),
        (('--set-json', 'privateSecretEnv.keys=["CONVERSATIONS_V3_STAGE"]'), 'privateSecretEnv'),
    ],
)
def test_listen_chart_rejects_private_override_of_pinned_startup_env(helm, startup_values, overrides, private_source):
    result = _render_prod_gke_deployment(
        helm, 'backend-listen', '--set-json', f'conversationsV3StartupEnv={json.dumps(startup_values)}', *overrides
    )
    assert result.returncode != 0
    assert f'{private_source} cannot override a conversationsV3StartupEnv key' in result.stderr


def test_collect_end_to_end_marks_failures_unknown(manifest):
    git = FakeGit(
        {NEW: {c['commit'] for s in manifest['services'].values() for c in s.get('contains', [])}},
        files={
            (NEW, 'backend/llm_gateway/config/lanes.yaml'): 'lanes:\n  - lane_id: omi:auto:chat-agent\n',
            (NEW, 'backend/llm_gateway/config/generated_route_overrides.yaml'): (
                'generated_route_overrides:\n  - feature: conversation_v3_outline\n  - feature: conv_action_items\n'
            ),
        },
    )

    class Stub(collect.Collector):
        def cloud_run(self, service, wanted):
            raise collect.ReadError('gcloud exit 1')

        def gke(self, namespace, deployment, wanted, promoted_from=(), container=''):
            return {'kind': 'gke', 'serving': [{'name': deployment, 'percent': 100, 'source_sha': NEW, 'env': {}}]}

    runner, _ = _fake_runner(
        {
            ('tasks', 'queues', 'list'): [
                {'name': 'projects/p/locations/l/queues/conversations-v3', 'state': 'RUNNING'}
            ],
            ('scheduler', 'jobs', 'list'): collect.ReadError('gcloud exit 1'),
        }
    )
    state = collect.collect(manifest, Stub('proj', 'us-central1', git, runner, registry=FakeRegistry({})))

    assert state['services']['backend']['error'].startswith('ReadError')
    assert state['services']['llm-gateway']['serving'][0]['lanes'] == [
        'omi:auto:chat-agent',
        'omi:auto:conv-action-items',
        'omi:auto:conversation-v3-outline',
    ]
    assert state['queues'] == {
        'conversations-v3': {'exists': True, 'state': 'RUNNING'},
        'conversations-v3-backfill': {'exists': False},
    }
    assert state['scheduler_jobs']['conversations-v3-sweep'] == {'error': 'scheduler jobs list: gcloud exit 1'}

    verdict = check.evaluate(manifest, state)
    assert verdict.verdict == check.BLOCKED  # summary lanes are absent at the gateway's serving commit
    assert 'lane:omi:auto:conversation-v3-summary' in _by_status(verdict, check.MISSING)
    assert {'service:backend:contains:012329830a9e', 'scheduler-job:conversations-v3-sweep'} <= _by_status(
        verdict, check.UNKNOWN
    )


def test_split_image_and_google_only_registry():
    assert collect.split_image('gcr.io/p/backend:abc1234') == ('gcr.io/p/backend', 'abc1234', '')
    assert collect.split_image('gcr.io/p/backend@' + DIG_NEW) == ('gcr.io/p/backend', '', DIG_NEW)
    assert collect.split_image('localhost:5000/x:t@' + DIG_NEW) == ('localhost:5000/x', 't', DIG_NEW)
    registry = collect.Registry(lambda: 'token', opener=lambda *a, **k: pytest.fail('must not call out'))
    with pytest.raises(collect.ReadError):
        registry.get('evil.example.com', 'p/x', 'manifests', DIG_NEW)


# ---------------------------------------------------------------------------------------------- review fixes


def test_invalid_yaml_manifest_exits_3(tmp_path):
    bad = tmp_path / 'm.yaml'
    bad.write_text('services: [unclosed\n')
    state = FIXTURES / 'state-ready.json'
    assert check.main(['--manifest', str(bad), '--state', str(state)]) == check.EXIT_INVALID
    assert collect.main(['--manifest', str(bad)]) == check.EXIT_INVALID


@pytest.mark.parametrize(
    'mutate',
    [
        lambda s: s['queues'].update({'conversations-v3': 'RUNNING'}),
        lambda s: s['services'].update({'pusher': ['x']}),
        lambda s: s['services']['pusher'].update({'serving': ['x']}),
    ],
)
def test_malformed_state_values_exit_3(manifest, mutate):
    state = _state('state-ready.json')
    mutate(state)
    with pytest.raises(check.InvalidInput):
        check.evaluate(manifest, state)


def test_explicit_empty_stage_is_not_the_default(manifest):
    state = _state('state-ready.json')
    state['services']['pusher']['serving'][0]['env']['CONVERSATIONS_V3_STAGE'] = {'value': ''}
    verdict = check.evaluate(manifest, state)
    assert 'env-equal:v3-stage:CONVERSATIONS_V3_STAGE' in _by_status(verdict, check.MISSING)


def test_equal_is_unknown_when_one_unit_of_a_runtime_is_unreadable(manifest):
    state = _state('state-ready.json')
    units = state['services']['backend']['serving']
    second = copy.deepcopy(units[0])
    second['name'] = 'backend-00099-old'
    second['env']['SYNC_TASKS_PROJECT'] = {'unknown': 'unsupported valueFrom'}
    units.append(second)
    verdict = check.evaluate(manifest, state)
    unknown = _by_status(verdict, check.UNKNOWN)
    assert 'env:v3-task-binding:backend:SYNC_TASKS_PROJECT' in unknown
    assert 'env-equal:v3-task-binding:SYNC_TASKS_PROJECT' in unknown


def test_render_shows_state_age(manifest):
    verdict = check.evaluate(manifest, _state('state-2026-11-17.json'))
    assert 'state_collected_at=2026-11-17T07:30:00Z' in check.render_text(verdict)
    assert verdict.to_json()['collected_at'] == '2026-11-17T07:30:00Z'


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _registry(routes):
    def opener(req, timeout=None):
        for suffix, payload in routes.items():
            if req.full_url.endswith(suffix):
                return _Response(payload)
        raise collect.urllib.error.URLError('404')

    return collect.Registry(lambda: 'token', opener=opener)


CONFIG = 'sha256:' + 'c' * 64
AMD = 'sha256:' + 'd' * 64


def test_registry_source_label_index_and_tag_fallback():
    label = {'config': {'Labels': {collect.REVISION_LABEL: NEW}}}
    index = {
        'mediaType': collect.INDEX_TYPES[0],
        'manifests': [
            {'digest': AMD, 'platform': {'os': 'linux', 'architecture': 'amd64'}},
            {'digest': 'sha256:' + 'e' * 64, 'platform': {'os': 'unknown', 'architecture': 'unknown'}},
        ],
    }
    reg = _registry(
        {f'manifests/{DIG_NEW}': index, f'manifests/{AMD}': {'config': {'digest': CONFIG}}, f'blobs/{CONFIG}': label}
    )
    assert reg.source('gcr.io/p/pusher', DIG_NEW) == NEW

    no_label = {f'manifests/{DIG_NEW}': {'config': {'digest': CONFIG}}, f'blobs/{CONFIG}': {'config': {}}}
    one_tag = {'manifest': {DIG_NEW: {'tag': ['promotion-x', '95005e7']}}}
    assert _registry({**no_label, 'tags/list': one_tag}).source('gcr.io/p/pusher', DIG_NEW) == '95005e7'

    for tags in (['promotion-x'], ['95005e7', 'abcdef1']):
        reg = _registry({**no_label, 'tags/list': {'manifest': {DIG_NEW: {'tag': tags}}}})
        with pytest.raises(collect.ReadError, match='single commit tag'):
            reg.source('gcr.io/p/pusher', DIG_NEW)

    two_amd = dict(index, manifests=[index['manifests'][0], index['manifests'][0]])
    with pytest.raises(collect.ReadError, match='ambiguous'):
        _registry({f'manifests/{DIG_NEW}': two_amd}).source('gcr.io/p/pusher', DIG_NEW)
    with pytest.raises(collect.ReadError, match='config missing'):
        _registry({f'manifests/{DIG_NEW}': {'config': {}}}).source('gcr.io/p/pusher', DIG_NEW)


def test_registry_token_failure_is_a_read_error():
    def broken():
        raise collect.subprocess.TimeoutExpired('gcloud', 90)

    with pytest.raises(collect.ReadError, match='token'):
        collect.Registry(broken, opener=lambda *a, **k: None).get('gcr.io', 'p/x', 'manifests', DIG_NEW)


def test_gke_counts_pods_with_unreadable_digests_and_picks_the_named_container():
    deployment = {
        'spec': {
            'selector': {'matchLabels': {'app': 'x'}},
            'template': {
                'spec': {
                    'containers': [
                        {'name': 'sidecar', 'image': 'gcr.io/p/side:1'},
                        {'name': 'app', 'image': 'gcr.io/p/app@' + DIG_NEW, 'env': [{'name': 'K', 'value': 'v'}]},
                    ]
                }
            },
        }
    }
    bad_pod = {
        'spec': deployment['spec']['template']['spec'],
        'status': {'phase': 'Running', 'containerStatuses': [{'name': 'app', 'imageID': 'garbage'}]},
    }
    runner, _ = _fake_runner(
        {('get', 'deployment', 'd'): deployment, ('get', 'pods'): {'items': [bad_pod, copy.deepcopy(bad_pod)]}}
    )
    collector = collect.Collector('p', 'r', FakeGit({}), runner, registry=FakeRegistry({}))

    result = collector.gke('ns', 'd', {'K'}, (), 'app')

    (unit,) = result['serving']
    assert unit['pods'] == 2 and unit['env'] == {'K': {'value': 'v'}}
    assert unit['source_error'] == 'running image digest unknown'
    with pytest.raises(collect.ReadError, match='ambiguous'):
        collect.app_container(deployment['spec']['template']['spec']['containers'])
