"""Offline route90-v1 contract. Never instantiate a real writer/provider."""

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

from scripts import cloud_run_completion_canary as gate

ROOT = Path(__file__).resolve().parents[3]


class Clock:
    def __init__(self):
        self.value = 36007
        self.elapsed = 0

    def now(self):
        return self.value

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        assert 0 < seconds <= 30
        self.value += seconds
        self.elapsed += seconds


def series(service, revision, start, end, count, route='/v2/sync-jobs/run'):
    return {
        'metricKind': 'DELTA',
        'valueType': 'INT64',
        'metric': {'type': f'logging.googleapis.com/user/{service}_route_2xx', 'labels': {'route': route}},
        'resource': {'type': 'cloud_run_revision', 'labels': {'revision_name': revision}},
        'points': [
            {
                'interval': {'startTime': gate.timestamp(end - 60), 'endTime': gate.timestamp(end)},
                'value': {'int64Value': str(count)},
            }
        ],
    }


def descriptors(service):
    definition = {
        'metricKind': 'DELTA',
        'valueType': 'INT64',
        'unit': '1',
        'labels': [{'key': 'route'}, {'key': 'method'}],
    }
    metric = {
        'name': service + '_route_2xx',
        'metricDescriptor': definition,
        'filter': f'resource.type="cloud_run_revision" AND resource.labels.project_id="{gate.PROJECT}" '
        f'AND resource.labels.service_name="{service}" '
        f'AND logName="projects/{gate.PROJECT}/logs/run.googleapis.com%2Frequests" '
        'AND httpRequest.status >= 200 AND httpRequest.status < 300',
        'labelExtractors': gate.EXTRACTORS,
    }
    descriptor = {
        **definition,
        'type': f'logging.googleapis.com/user/{service}_route_2xx',
        'monitoredResourceTypes': ['cloud_run_revision'],
    }
    return copy.deepcopy((metric, descriptor))


class Provider:
    def __init__(self, clock):
        self.clock = clock
        self.candidates = {s: s + '-new' for s in gate.SERVICES}
        self.documents = {}
        self.writes = []
        self.queries = []
        self.pending = {}
        self.delay = 2
        self.mode = 'pass'
        self.failure = None
        self.journal = None
        self.observed_at = {}
        for service in gate.SERVICES:
            traffic = [{'revisionName': service + '-old', 'percent': 100}]
            self.documents[service] = {
                'apiVersion': 'serving.knative.dev/v1',
                'kind': 'Service',
                'metadata': {
                    'name': service,
                    'namespace': '123',
                    'resourceVersion': '1',
                    'generation': 1,
                    'labels': {'unchanged': 'yes'},
                    'annotations': {'unchanged': 'yes'},
                },
                'spec': {
                    'traffic': traffic,
                    'template': {
                        'metadata': {'name': self.candidates[service]},
                        'spec': {'containers': [{'env': [{'name': 'PRIVATE', 'value': 'NEVER-PRINT-ME'}]}]},
                    },
                },
                'status': {
                    'traffic': copy.deepcopy(traffic),
                    'observedGeneration': 1,
                    'latestCreatedRevisionName': self.candidates[service],
                },
            }

    def service(self, service):
        document = self.documents[service]
        if service in self.pending:
            self.pending[service] -= 1
            if self.pending[service] <= 0:
                document['status']['traffic'] = copy.deepcopy(document['spec']['traffic'])
                document['status']['observedGeneration'] = document['metadata']['generation']
                del self.pending[service]
                self.observed_at[service] = self.clock.now()
        return copy.deepcopy(document)

    def revision(self, service, revision):
        return {
            'metadata': {'name': revision, 'labels': {'serving.knative.dev/service': service}},
            'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]},
        }

    def descriptors(self, service):
        return descriptors(service)

    def replace(self, service, body, *, rollback=False):
        # Exercise the persisted pre-request intent and resourceVersion CAS.
        persisted = json.loads(self.journal.path.read_text())
        assert persisted['events'][-1]['reason'] == ('rollback_intent' if rollback else 'write_intent')
        current = self.documents[service]
        assert body['metadata']['resourceVersion'] == current['metadata']['resourceVersion']
        assert 'status' not in body and 'generation' not in body['metadata']
        assert gate.intent(body) == gate.intent(current)
        self.writes.append((service, copy.deepcopy(body), rollback, self.clock.now()))
        if self.failure:
            raise self.failure
        current['spec']['traffic'] = copy.deepcopy(body['spec']['traffic'])
        current['metadata']['resourceVersion'] = str(int(current['metadata']['resourceVersion']) + 1)
        current['metadata']['generation'] += 1
        self.pending[service] = self.delay

    def aggregate(self, service, start, end, *, idle=False):
        self.queries.append((service, start, end, idle, self.clock.now()))
        old, new = service + '-old', self.candidates[service]
        if idle:
            return [series(service, old, start, end, 0)]
        if end - start == 1800:
            if self.mode == 'idle_baseline' and service == 'backend-sync-backfill':
                return []
            return [series(service, old, start, end, 90), series(service, old, start, end, 30, '')]
        assert self.clock.now() >= end + gate.SETTLE
        if self.mode == 'empty':
            return []
        rows = [
            series(service, old, start, end, 900),
            series(service, new, start, end, 70),
            series(service, old, start, end, 900, ''),
            series(service, new, start, end, 70, ''),
        ]
        if self.mode == 'regression':
            rows[1]['points'][0]['value']['int64Value'] = '69'
        if self.mode == 'zero':
            rows[1]['points'][0]['value']['int64Value'] = '0'
        if self.mode == 'missing':
            rows.pop()
        return rows


def fixture(tmp_path):
    clock = Clock()
    provider = Provider(clock)
    journal = gate.Journal(tmp_path / 'evidence.json', clock)
    provider.journal = journal
    canary = gate.Canary(provider, clock, journal, provider.candidates)
    return canary, provider, journal


def test_full_window_anchors_on_actual_reconciled_split_then_settles_and_promotes_once(tmp_path):
    canary, provider, journal = fixture(tmp_path)
    canary.run()
    assert len(provider.writes) == 8
    assert all(not rollback for _, _, rollback, _ in provider.writes)
    events = journal.data['events']
    for service in gate.SERVICES:
        window = next(e for e in events if e['reason'] == 'observation_window' and e['service'] == service)
        anchor, start, end, settled = [gate.epoch(window[k]) for k in ('anchor', 'start', 'end', 'settled')]
        split_write = next(w for w in provider.writes if w[0] == service)
        assert anchor >= split_write[3] + 30  # spec was changed before actual reconciled.
        assert start >= anchor and start % 60 == 0
        assert end - start == 900 and settled - end == 120
        writes = [w for w in provider.writes if w[0] == service]
        assert [w[1]['metadata']['resourceVersion'] for w in writes] == ['1', '2']
        assert writes[1][3] >= settled
        assert writes[0][1]['spec']['traffic'] == [
            {'revisionName': service + '-old', 'percent': 90},
            {'revisionName': service + '-new', 'percent': 10},
        ]
        assert writes[1][1]['spec']['traffic'] == [{'revisionName': service + '-new', 'percent': 100}]
    assert events[-1]['reason'] == 'CANARY_OK'
    rendered = journal.path.read_text()
    assert 'NEVER-PRINT-ME' not in rendered and '/v2/' not in rendered and 'https://' not in rendered
    assert journal.path.stat().st_mode & 0o777 == 0o600


def test_guarded_workflow_rollback_reconciles_owned_traffic_and_never_repeats(tmp_path):
    canary, provider, journal = fixture(tmp_path)
    canary.run()
    resumed = gate.Journal(journal.path, provider.clock, resume=True)
    provider.journal = resumed
    gate.rollback_recorded(provider, provider.clock, resumed, provider.candidates)
    assert len(provider.writes) == 12
    assert sum(w[2] for w in provider.writes) == 4
    gate.rollback_recorded(provider, provider.clock, resumed, provider.candidates)
    assert len(provider.writes) == 12


def test_guarded_workflow_rollback_does_not_undo_foreign_service_intent(tmp_path):
    canary, provider, journal = fixture(tmp_path)
    canary.run()
    provider.documents[gate.SERVICES[0]]['metadata']['annotations']['foreign-setting'] = 'changed'
    with pytest.raises(gate.Refusal, match='rollback_foreign_or_unreconciled_intent'):
        gate.rollback_recorded(provider, provider.clock, journal, provider.candidates)
    assert len(provider.writes) == 8


def test_budget_allowance_survives_rollback_process_restart(tmp_path):
    clock = Clock()
    journal = gate.Journal(tmp_path / 'journal.json', clock)
    provider = gate.GoogleProvider(journal)
    provider.charge('backend', 'rollback', 1)
    restarted = gate.GoogleProvider(gate.Journal(journal.path, clock, resume=True))
    with pytest.raises(gate.Refusal, match='rollback_budget_exhausted'):
        restarted.charge('backend', 'rollback', 1)


def test_descriptor_lookup_uses_filtered_list_not_broken_type_get():
    provider = gate.GoogleProvider()
    metric, descriptor = descriptors('backend')
    calls = []

    def request(*args, **kwargs):
        calls.append(args[-1])
        return metric if len(calls) == 1 else dict(metricDescriptors=[descriptor])

    provider.request = request
    gate.validate_descriptors('backend', *provider.descriptors('backend'))
    assert '/metricDescriptors?' in calls[1]
    assert 'filter=' in calls[1]


def test_monitoring_default_log_label_does_not_invalidate_user_route_schema():
    metric, descriptor = descriptors('backend')
    descriptor['labels'] = [*descriptor['labels'], dict(key='log')]
    gate.validate_descriptors('backend', metric, descriptor)
    descriptor['labels'].append(dict(key='route'))
    with pytest.raises(gate.Refusal, match='metric_descriptor_schema_mismatch'):
        gate.validate_descriptors('backend', metric, descriptor)


def test_workflow_rerun_cannot_reset_unknown_canary_journal_or_budget(tmp_path):
    import os
    import subprocess

    action = yaml.load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text(), Loader=yaml.BaseLoader)
    steps = action['runs']['steps']
    guard = next(step for step in steps if step.get('name') == 'Require resolved first-attempt canary context')
    assert steps.index(guard) < next(i for i, step in enumerate(steps) if step.get('id') == 'shift-cloud-run-traffic')
    for environment, mode, attempt, code in [
        ('prod', 'on', '2', 75),
        ('prod', 'on', '1', 0),
        ('development', 'on', '2', 0),
        ('prod', 'off', '2', 0),
    ]:
        run = subprocess.run(
            ['bash', '-euo', 'pipefail', '-c', guard['run']],
            cwd=tmp_path,
            env={
                **os.environ,
                'CANARY_ENVIRONMENT': environment,
                'COMPLETIONS_CANARY': mode,
                'CANARY_RUN_ATTEMPT': attempt,
            },
            capture_output=True,
            text=True,
        )
        assert run.returncode == code


def test_server_output_annotations_do_not_look_like_foreign_operator_intent():
    original = Provider(Clock()).documents['backend']
    changed = copy.deepcopy(original)
    changed['metadata'].setdefault('annotations', {})['run.googleapis.com/operation-id'] = 'new-server-operation'
    changed['metadata']['annotations']['serving.knative.dev/lastModifier'] = 'writer'
    assert gate.intent_hash(changed) == gate.intent_hash(original)


@pytest.mark.parametrize(
    'mode,reason,rollbacks',
    [
        ('regression', 'completion_regression', 4),
        ('zero', 'completion_regression', 4),
        ('missing', 'missing_eligible_route_evidence', 0),
        ('empty', 'idle_refused', 0),
    ],
)
def test_failures_never_promote_and_only_explicit_regression_rolls_back(tmp_path, mode, reason, rollbacks):
    canary, provider, journal = fixture(tmp_path)
    provider.mode = mode
    with pytest.raises(gate.Refusal, match=reason):
        canary.run()
    assert sum(w[2] for w in provider.writes) == rollbacks
    assert not any(
        w[1]['spec']['traffic'] == [{'revisionName': w[0] + '-new', 'percent': 100}] for w in provider.writes
    )
    assert all(w[1]['metadata']['resourceVersion'] == '2' for w in provider.writes if w[2])
    assert 'CANARY_OK' not in journal.path.read_text()


def test_idle_backfill_refuses_all_writes_before_other_services_can_stage(tmp_path):
    canary, provider, _ = fixture(tmp_path)
    provider.mode = 'idle_baseline'
    with pytest.raises(gate.Refusal, match='idle_refused'):
        canary.run()
    assert provider.writes == []
    assert sum(q[3] for q in provider.queries) == 1


@pytest.mark.parametrize('failure', [TimeoutError('PRIVATE URL'), RuntimeError('409 conflict')])
def test_unknown_or_conflict_writer_stops_without_retry_and_restart_refuses(tmp_path, failure):
    canary, provider, journal = fixture(tmp_path)
    provider.failure = failure
    with pytest.raises(gate.UnknownWrite):
        canary.run()
    assert len(provider.writes) == 1
    assert journal.data['events'][-1]['reason'] == 'unknown_write_outcome'
    assert 'PRIVATE' not in journal.path.read_text()
    with pytest.raises(gate.Refusal, match='existing_journal'):
        gate.Journal(journal.path, provider.clock)


@pytest.mark.parametrize('change', ['traffic', 'template', 'candidate', 'tags', 'latest'])
def test_foreign_drift_refuses_fresh_promotion_cas(tmp_path, change):
    canary, provider, _ = fixture(tmp_path)
    original = provider.aggregate

    def aggregate(service, start, end, **kwargs):
        result = original(service, start, end, **kwargs)
        if end - start == 900 and service == 'backend-integration':
            document = provider.documents['backend']
            if change == 'traffic':
                document['status']['traffic'] = [{'revisionName': 'backend-foreign', 'percent': 100}]
            if change == 'template':
                document['spec']['template']['spec']['containers'][0]['env'][0]['value'] = 'foreign'
            if change == 'candidate':
                document['status']['latestCreatedRevisionName'] = 'backend-foreign'
            if change == 'tags':
                document['spec']['traffic'][0]['tag'] = 'foreign'
            if change == 'latest':
                document['spec']['traffic'][0]['latestRevision'] = True
        return result

    provider.aggregate = aggregate
    with pytest.raises(gate.Refusal):
        canary.run()
    assert len(provider.writes) == 4


def test_rollback_requires_fresh_exact_owned_split(tmp_path):
    canary, provider, _ = fixture(tmp_path)
    provider.mode = 'regression'
    original = provider.aggregate

    def aggregate(service, start, end, **kwargs):
        rows = original(service, start, end, **kwargs)
        if end - start == 900:
            provider.documents[service]['status']['traffic'] = [{'revisionName': service + '-foreign', 'percent': 100}]
        return rows

    provider.aggregate = aggregate
    with pytest.raises(gate.Refusal, match='foreign_or_unreconciled'):
        canary.run()
    assert len(provider.writes) == 4


@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '-1', '1.5', True, None])
def test_nonfinite_or_bad_counts_refuse(bad):
    row = series('backend', 'backend-old', 0, 1800, 30)
    row['points'][0]['value']['int64Value'] = bad
    with pytest.raises(gate.Refusal, match='invalid_or_nonfinite'):
        gate.route_counts([row], 'backend', 0, 1800)


def test_default_omitted_and_named_unmatched_buckets_and_resource_revision_extraction():
    rows = [
        series('backend', 'backend-old', 0, 1800, 12, ''),
        series('backend', 'backend-new', 0, 1800, 18, ''),
        series('backend', 'backend-old', 0, 1800, 99, '/unmatched'),
    ]
    del rows[0]['metric']['labels']['route']
    counts = gate.route_counts(rows, 'backend', 0, 1800)
    assert sum(counts.values()) == 129
    assert counts['', 'backend-old'] == 12
    assert counts['/unmatched', 'backend-old'] == 99
    rows[0]['metric']['labels']['revision_name'] = rows[0]['resource']['labels'].pop('revision_name')
    with pytest.raises(gate.Refusal, match='aggregate_revision'):
        gate.route_counts(rows, 'backend', 0, 1800)


@pytest.mark.parametrize('route', ['https://private/path', '/v1/user/123', '/Upper', '/a?private', None])
def test_bad_nonempty_route_labels_refuse(route):
    with pytest.raises(gate.Refusal, match='invalid_route'):
        gate.route_counts([series('backend', 'backend-old', 0, 1800, 30, route)], 'backend', 0, 1800)


@pytest.mark.parametrize('kind', ['descriptor', 'read', 'empty', 'not_ready', 'ambiguous'])
def test_prewrite_validation_failure_never_mutates(tmp_path, kind):
    canary, provider, _ = fixture(tmp_path)
    if kind == 'descriptor':
        provider.descriptors = lambda service: ({}, {})
    if kind == 'read':
        provider.descriptors = lambda service: (_ for _ in ()).throw(gate.Refusal('unreadable_descriptor'))
    if kind == 'empty':
        provider.aggregate = lambda *args, **kwargs: []
    if kind == 'not_ready':
        provider.revision = lambda *args: {}
    if kind == 'ambiguous':
        provider.documents['backend']['spec']['traffic'][0]['latestRevision'] = True
    with pytest.raises(gate.Refusal):
        canary.run()
    assert provider.writes == []


def fake_google():
    # Bypass construction: no auth, network, gcloud or real writer in these tests.
    provider = object.__new__(gate.GoogleProvider)
    provider.journal = None
    return provider


def test_aggregate_query_is_pinned_and_groups_resource_revision_and_route():
    provider = fake_google()
    calls = []

    def request(service, category, limit, url):
        calls.append((service, category, limit, url))
        return {'timeSeries': [], **({'nextPageToken': 'page2'} if len(calls) == 1 else {})}

    provider.request = request
    assert provider.aggregate('backend', 0, 1800) == []
    assert len(calls) == 2
    query = parse_qs(urlparse(calls[0][3]).query)
    assert query['aggregation.groupByFields'] == ['metric.labels.route', 'resource.labels.revision_name']
    assert query['aggregation.perSeriesAligner'] == ['ALIGN_SUM']
    assert 'project_id="based-hardware"' in query['filter'][0]
    assert 'location="us-central1"' in query['filter'][0]
    assert parse_qs(urlparse(calls[1][3]).query)['pageToken'] == ['page2']
    assert all(c[1:3] == ('route_query', 3) for c in calls)


def test_budgets_charge_failures_and_pages_before_io(monkeypatch):
    provider = fake_google()
    provider.budgets = gate.defaultdict(int)
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise TimeoutError('sensitive transport failure')

    monkeypatch.setattr(gate.subprocess, 'run', fail)
    for _ in range(3):
        with pytest.raises(gate.Refusal, match='unreadable_route_query'):
            provider.request('backend', 'route_query', 3, 'https://unused.invalid')
    with pytest.raises(gate.Refusal, match='route_query_budget_exhausted'):
        provider.request('backend', 'route_query', 3, 'https://unused.invalid')
    assert len(calls) == 3
    for category, limit in [('metadata', 60), ('idle', 1), ('normal_write', 2), ('rollback', 1)]:
        for _ in range(limit):
            provider.charge('backend', category, limit)
        with pytest.raises(gate.Refusal, match='budget_exhausted'):
            provider.charge('backend', category, limit)


def test_workflow_default_on_audited_bypass_and_mutually_exclusive_writers(tmp_path):
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    # PyYAML 1.1 treats the workflow key `on` as True.
    inputs = workflow.get('on', workflow.get(True))['workflow_dispatch']['inputs']
    assert inputs['completions_canary']['default'] == 'on'
    assert inputs['completions_canary']['options'] == ['on', 'off']
    assert workflow['env']['OMI_COMPLETIONS_CANARY_PROTOCOL'] == 'route90-v1'
    assert action['inputs']['completions_canary']['default'] == 'on'
    stack = next(
        s
        for j in workflow['jobs'].values()
        for s in j.get('steps', [])
        if s.get('uses') == './.github/actions/deploy-backend-stack'
    )
    assert stack['with']['completions_canary'] == "${{ github.event.inputs.completions_canary || 'on' }}"
    steps = action['runs']['steps']
    shift = next(s for s in steps if s.get('id') == 'shift-cloud-run-traffic')
    script = shift['run']
    assert script.count('cloud_run_completion_canary.py') == 1
    assert script.count('gcloud run services update-traffic') == 4
    assert script.index('cloud_run_completion_canary.py') < script.index('\nelse\n')
    assert script.index('COMPLETIONS_CANARY_BYPASS_EXPLICIT_WORKFLOW_INPUT_OFF') < script.index(
        'gcloud run services update-traffic'
    )
    assert script.count('--candidate ') == 4
    names = [s['name'] for s in steps]
    assert names.index('Capture Cloud Run pre-promotion traffic snapshot') < names.index(shift['name'])
    assert names.index('Verify validated revisions are still current') < names.index(shift['name'])
    restores = [s for s in steps if s['name'] == 'Restore Cloud Run traffic snapshot after failed promotion']
    assert len(restores) == 2 and all("steps.shift-cloud-run-traffic.outcome == 'failure'" in s['if'] for s in restores)
    assert workflow['concurrency']['cancel-in-progress'] is False
    artifact = next(s for s in steps if s['name'] == 'Upload backend release-vector evidence')
    assert 'artifacts/backend-completions-canary-*.json' in artifact['with']['path']


def test_omitted_and_explicit_default_rows_preserve_every_count():
    rows = [series('backend', 'backend-old', 0, 1800, 12, ''), series('backend', 'backend-old', 0, 1800, 18, '')]
    del rows[0]['metric']['labels']['route']
    assert gate.route_counts(rows, 'backend', 0, 1800) == {('', 'backend-old'): 30}


@pytest.mark.parametrize(
    'environment,mode,fail,expected',
    [
        ('prod', 'on', False, ['canary']),
        ('prod', 'on', True, ['canary']),
        ('prod', 'off', False, ['legacy'] * 4),
        ('development', 'on', False, ['legacy'] * 4),
        ('development', 'off', False, ['legacy'] * 4),
        ('prod', 'unknown', False, []),
    ],
)
def test_shift_shell_executes_exactly_one_writer_path(tmp_path, environment, mode, fail, expected):
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    script = next(s['run'] for s in action['runs']['steps'] if s.get('id') == 'shift-cloud-run-traffic')
    # Resolve GitHub expressions to inert pins; run the real shell against local recording fakes.
    script = gate.re.sub(r'\$\{\{[^}]+\}\}', 'fake-pin', script)
    (tmp_path / 'artifacts').mkdir()
    commands = tmp_path / 'commands'
    commands.mkdir()
    calls = tmp_path / 'calls'
    controls = tmp_path / 'controls'
    controls.mkdir()
    (controls / 'cloud_run_completion_canary.py').write_text(
        "import os\nfrom pathlib import Path\n"
        "with Path(os.environ['CALLS']).open('a') as f: f.write('canary\\n')\n"
        "raise SystemExit(int(os.environ['FAIL_CANARY']))\n"
    )
    gcloud = commands / 'gcloud'
    gcloud.write_text(
        '#!/bin/sh\n'
        'if [ "$CANARY_ENVIRONMENT" = prod ]; then\n'
        "  test -f artifacts/backend-completions-canary-bypass.json || exit 99\n"
        'fi\n'
        'echo legacy >> "$CALLS"\n'
    )
    gcloud.chmod(0o755)
    result = gate.subprocess.run(
        ['bash', '-c', script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **gate.os.environ,
            'COMPLETIONS_CANARY': mode,
            'CANARY_ENVIRONMENT': environment,
            'CANARY_ACTOR': 'test-actor',
            'CANARY_RUN_ID': '42',
            'CANARY_RUN_ATTEMPT': '1',
            'CALLS': str(calls),
            'DEPLOY_CONTROL_SCRIPTS': str(controls),
            'FAIL_CANARY': str(int(fail)),
            'PATH': str(commands) + ':' + gate.os.environ['PATH'],
        },
        timeout=10,
    )
    assert (calls.read_text().splitlines() if calls.exists() else []) == expected
    assert (result.returncode == 0) == (not fail and mode in ('on', 'off'))
    audit = tmp_path / 'artifacts/backend-completions-canary-bypass.json'
    assert audit.exists() == (environment == 'prod' and mode == 'off')
    if audit.exists():
        assert json.loads(audit.read_text()) == {
            'actor': 'test-actor',
            'reason': 'COMPLETIONS_CANARY_BYPASS_EXPLICIT_WORKFLOW_INPUT_OFF',
            'run_id': '42',
            'run_attempt': '1',
        }


def test_v1_put_wire_contract_uses_supplied_resource_version_without_reread(monkeypatch):
    provider = fake_google()
    provider.budgets = gate.defaultdict(int)
    sent = []
    token_calls = []

    def token(*args, **kwargs):
        token_calls.append(args)
        assert kwargs['timeout'] == 30 and kwargs['capture_output']
        return type('Token', (), {'stdout': 'PRIVATE-TOKEN\n'})()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            assert limit == gate.MAX_BODY + 1
            return b'{}'

    class Transport:
        def open(self, request, *, timeout):
            assert timeout == 30
            sent.append(request)
            return Response()

    provider.opener = Transport()
    monkeypatch.setattr(gate.subprocess, 'run', token)
    body = {
        'apiVersion': 'serving.knative.dev/v1',
        'kind': 'Service',
        'metadata': {'name': 'backend', 'resourceVersion': 'fresh-cas-123'},
        'spec': {'traffic': [{'revisionName': 'backend-new', 'percent': 100}]},
    }
    provider.replace('backend', body)
    assert len(sent) == len(token_calls) == 1
    assert sent[0].method == 'PUT'
    assert sent[0].full_url == (
        'https://us-central1-run.googleapis.com/apis/serving.knative.dev/v1/'
        'namespaces/based-hardware/services/backend'
    )
    assert json.loads(sent[0].data) == body
    assert dict(provider.budgets) == {('backend', 'normal_write'): 1}


def test_unreconciled_generation_cannot_anchor_window(tmp_path):
    canary, provider, journal = fixture(tmp_path)
    original = provider.service

    def service(name):
        document = original(name)
        if len(provider.writes) == 1 and name == 'backend':
            # Actual 90/10 alone is insufficient; generation must also reconcile.
            if document['status']['traffic'] == document['spec']['traffic']:
                if not hasattr(provider, 'generation_lagged'):
                    provider.generation_lagged = True
                    document['status']['observedGeneration'] = 1
        return document

    provider.service = service
    canary.run()
    window = next(e for e in journal.data['events'] if e['reason'] == 'observation_window')
    assert gate.epoch(window['anchor']) >= provider.writes[0][3] + 60


def test_wall_clock_jump_cannot_shorten_observation(tmp_path):
    canary, provider, _ = fixture(tmp_path)
    original = provider.clock.sleep

    def jump(seconds):
        original(seconds)
        if len(provider.writes) == 4:
            provider.clock.value += 1000

    provider.clock.sleep = jump
    with pytest.raises(gate.Refusal, match='clock_drift'):
        canary.run()
    assert len(provider.writes) == 4


@pytest.mark.parametrize('promotion_timeout', [False, True])
def test_latest_normal_transitions_leave_full_guarded_rollback_read_allowance(tmp_path, promotion_timeout):
    canary, provider, journal = fixture(tmp_path)
    provider.delay = gate.MAX_TRANSITION_POLLS
    allowance = object.__new__(gate.GoogleProvider)
    allowance.budgets = gate.defaultdict(int)
    allowance.journal = journal
    for method in ('service', 'revision'):
        original = getattr(provider, method)

        def charged(service, *args, original=original):
            allowance.charge(service, 'metadata', 60)
            return original(service, *args)

        setattr(provider, method, charged)
    original_replace = provider.replace

    def replace(service, body, *, rollback=False):
        original_replace(service, body, rollback=rollback)
        if (
            promotion_timeout
            and not rollback
            and body['spec']['traffic'] == [{'revisionName': provider.candidates[service], 'percent': 100}]
        ):
            provider.pending[service] = gate.MAX_TRANSITION_POLLS + 1

    provider.replace = replace
    if promotion_timeout:
        with pytest.raises(gate.Refusal, match='traffic_reconcile_timeout'):
            canary.run()
    else:
        canary.run()
    # Includes a fresh read that reconciles the timed-out promotion, an old
    # revision Ready read, and the latest possible rollback reconciliation.
    gate.rollback_recorded(provider, provider.clock, journal, provider.candidates)
    assert max(allowance.budgets.values()) == (57 if promotion_timeout else 59)
    assert all(
        document['status']['traffic'] == [{'revisionName': service + '-old', 'percent': 100}]
        for service, document in provider.documents.items()
    )


@pytest.mark.parametrize(
    'shift,cancelled,failed,expected',
    [
        ('cancelled', True, False, True),
        ('success', True, False, True),
        ('skipped', True, False, False),
        ('failure', False, True, True),
        ('success', False, False, False),
    ],
)
def test_manual_restore_condition_covers_cancellation_during_and_after_canary(shift, cancelled, failed, expected):
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    restore = next(
        step
        for step in action['runs']['steps']
        if step['name'] == 'Restore Cloud Run traffic snapshot after failed promotion'
        and "inputs.deploy_profile == 'manual'" in step['if']
    )
    expression = restore['if'].removeprefix('${{').removesuffix('}}').strip()
    expression = expression.replace('inputs.deploy_profile', repr('manual'))
    outcomes = {'cloud-run-traffic-snapshot': 'success', 'shift-cloud-run-traffic': shift}
    expression = gate.re.sub(
        r'steps\.([a-z0-9-]+)\.outcome', lambda match: repr(outcomes.get(match[1], 'skipped')), expression
    )
    expression = expression.replace('cancelled()', repr(cancelled)).replace('failure()', repr(failed))
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
    assert eval(expression, {'__builtins__': {}}, {}) is expected
    assert 'cloud_run_completion_canary.py" --rollback' in restore['run']
