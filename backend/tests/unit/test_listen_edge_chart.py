"""listen-edge chart contract: shadow ingest only, drain budget, listen-only reachability."""

from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / 'charts' / 'listen-edge'
LISTEN_CHART = Path(__file__).resolve().parents[2] / 'charts' / 'backend-listen'
DIGEST = 'sha256:' + 'a' * 64

RELEASES = {
    'prod': ('prod-omi-listen-edge', 'prod-omi-backend', 'prod_omi_listen_edge_values.yaml'),
    'dev': ('dev-omi-listen-edge', 'dev-omi-backend', 'dev_omi_listen_edge_values.yaml'),
}


def render(environment, *arguments):
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('Helm unavailable; render check runs on the packaging host')
    release, namespace, values = RELEASES[environment]
    result = subprocess.run(
        [
            helm,
            'template',
            release,
            str(CHART),
            '--namespace',
            namespace,
            '-f',
            str(CHART / values),
            '--set-string',
            f'image.digest={DIGEST}',
            *arguments,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def doc_for(documents, kind, name):
    return next(doc for doc in documents if doc.get('kind') == kind and doc['metadata']['name'] == name)


@pytest.fixture(scope='module')
def prod_documents():
    return render('prod')


@pytest.fixture(scope='module')
def dev_documents():
    return render('dev')


def deployment(documents, environment):
    release = RELEASES[environment][0]
    return doc_for(documents, 'Deployment', release)


# The binary's worst-case drain at default knobs is 23 s; SIGTERM starts it
# directly, so the pod must outlive it and must not run a preStop hook first.
def test_grace_period_exceeds_the_drain_deadline(prod_documents, dev_documents):
    for documents, environment in ((prod_documents, 'prod'), (dev_documents, 'dev')):
        spec = deployment(documents, environment)['spec']['template']['spec']
        assert spec['terminationGracePeriodSeconds'] > 23, environment
        for container in spec['containers']:
            assert 'lifecycle' not in container, environment


def test_image_renders_by_digest_and_tag_is_required(prod_documents):
    image = deployment(prod_documents, 'prod')['spec']['template']['spec']['containers'][0]['image']
    assert image == f'gcr.io/based-hardware/listen-edge@{DIGEST}'
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('Helm unavailable')
    release, namespace, values = RELEASES['prod']
    result = subprocess.run(
        [helm, 'template', release, str(CHART), '--namespace', namespace, '-f', str(CHART / values)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, 'render without image tag/digest must fail'


def test_env_points_at_listen_and_the_baked_model(prod_documents, dev_documents):
    for documents, environment in ((prod_documents, 'prod'), (dev_documents, 'dev')):
        entries = deployment(documents, environment)['spec']['template']['spec']['containers'][0]['env']
        env = {entry['name']: entry.get('value') for entry in entries}
        assert env['EDGE_UPSTREAM_URL'] == f'ws://{environment}-omi-backend-listen:8080'
        assert env['EDGE_VAD_MODEL_PATH'] == '/models/silero_vad.onnx'
        # The shared token is a secret: never a committed env entry, only privateEnv.
        assert 'EDGE_SHADOW_TOKEN' not in env


def test_private_env_adds_the_secret_token_exactly_once():
    documents = render('prod', '--set-string', 'privateEnv.EDGE_SHADOW_TOKEN=secret-value')
    entries = deployment(documents, 'prod')['spec']['template']['spec']['containers'][0]['env']
    tokens = [entry for entry in entries if entry['name'] == 'EDGE_SHADOW_TOKEN']
    assert len(tokens) == 1 and tokens[0]['value'] == 'secret-value'
    # And a privateEnv key that matches a committed entry replaces it, never duplicates it.
    documents = render('prod', '--set-string', 'privateEnv.EDGE_SHADOW_MAX_SESSIONS=42')
    entries = deployment(documents, 'prod')['spec']['template']['spec']['containers'][0]['env']
    caps = [entry for entry in entries if entry['name'] == 'EDGE_SHADOW_MAX_SESSIONS']
    assert len(caps) == 1 and caps[0]['value'] == '42'


def test_service_is_clusterip_with_no_neg(prod_documents, dev_documents):
    for documents, environment in ((prod_documents, 'prod'), (dev_documents, 'dev')):
        service = doc_for(documents, 'Service', RELEASES[environment][0])
        assert service['spec']['type'] == 'ClusterIP'
        annotations = service['metadata'].get('annotations') or {}
        assert not any('neg' in key.lower() for key in annotations)
        assert {port['port'] for port in service['spec']['ports']} == {8080}


def test_network_policy_admits_only_listen_ingress(prod_documents):
    release = RELEASES['prod'][0]
    policy = doc_for(prod_documents, 'NetworkPolicy', release)
    assert policy['spec']['policyTypes'] == ['Ingress']
    assert len(policy['spec']['ingress']) == 1
    rule = policy['spec']['ingress'][0]
    assert rule['from'] == [
        {
            'podSelector': {
                'matchLabels': {
                    'app.kubernetes.io/name': 'backend-listen',
                    'app.kubernetes.io/instance': 'prod-omi-backend-listen',
                }
            }
        }
    ]
    assert rule['ports'] == [{'protocol': 'TCP', 'port': 8080}]
    disabled = render('prod', '--set', 'networkPolicy.enabled=false')
    assert not any(doc.get('kind') == 'NetworkPolicy' for doc in disabled)


def test_no_ingress_or_load_balancer_resource(prod_documents):
    kinds = {doc['kind'] for doc in prod_documents}
    assert 'Ingress' not in kinds
    assert 'BackendConfig' not in kinds


def test_service_account_mounts_no_token(prod_documents):
    release = RELEASES['prod'][0]
    account = doc_for(prod_documents, 'ServiceAccount', release)
    assert account['automountServiceAccountToken'] is False
    assert 'iam.gke.io/gcp-service-account' not in (account['metadata'].get('annotations') or {})


# The mirror must stay off in every environment's committed values until the
# lead ramps EDGE_SHADOW_PERCENT (feature-flag registry row of record). The
# percent is declared in the prod values only — the registry checker allows a
# ramp key exactly one declaration — so dev relies on the code default 0.
@pytest.mark.parametrize('environment', ['prod', 'dev'])
def test_listen_values_keep_the_mirror_off_by_default(environment):
    values = yaml.safe_load((LISTEN_CHART / f'{environment}_omi_backend_listen_values.yaml').read_text())
    env = {entry['name']: entry.get('value') for entry in values['env']}
    assert env.get('EDGE_SHADOW_PERCENT', '0') == '0'
    # Secret: privateEnv (LISTEN_PRIVATE_VALUES_YAML) only, never committed.
    assert 'EDGE_SHADOW_TOKEN' not in env
    assert env['EDGE_SHADOW_URL'] == (
        f'ws://{environment}-omi-listen-edge.{environment}-omi-backend.svc.cluster.local:8080/v1/shadow'
    )


def test_shadow_percent_is_declared_in_exactly_one_values_file():
    declaring = [
        path.name
        for path in LISTEN_CHART.glob('*_omi_backend_listen_values.yaml')
        if any(entry.get('name') == 'EDGE_SHADOW_PERCENT' for entry in yaml.safe_load(path.read_text())['env'])
    ]
    assert declaring == ['prod_omi_backend_listen_values.yaml']


# The edge's upstream must be exactly the listen chart's Service name in the
# shared namespace, or the passthrough path and the mirror break silently.
def test_upstream_matches_the_listen_service_name():
    for environment in ('prod', 'dev'):
        edge_values = yaml.safe_load((CHART / RELEASES[environment][2]).read_text())
        upstream = next(entry['value'] for entry in edge_values['env'] if entry['name'] == 'EDGE_UPSTREAM_URL')
        listen_service = f'{environment}-omi-backend-listen'
        assert upstream == f'ws://{listen_service}:8080'
        # The listen chart's fullname in the shared namespace is that release
        # name; a rename here must stay in lockstep with this assertion.
        helm = shutil.which('helm')
        if helm is None:
            pytest.skip('Helm unavailable')
        result = subprocess.run(
            [
                helm,
                'template',
                f'{environment}-omi-backend-listen',
                str(LISTEN_CHART),
                '--namespace',
                f'{environment}-omi-backend',
                '-f',
                str(LISTEN_CHART / f'{environment}_omi_backend_listen_values.yaml'),
                '--set-string',
                'image.tag=abc1234',
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        services = {
            doc['metadata']['name'] for doc in yaml.safe_load_all(result.stdout) if doc and doc.get('kind') == 'Service'
        }
        assert listen_service in services
