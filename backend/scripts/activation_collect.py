#!/usr/bin/env python3
"""Collect live serving state for an activation manifest, read-only. Output feeds activation_check.py.

Reads only service metadata: Cloud Run services and the revisions receiving traffic (``status.traffic``,
never the service spec), GKE Deployment selectors and their running pods' specs and image digests,
Cloud Tasks queues and Cloud Scheduler jobs. It never reads Secrets, user data or request logs, and never writes.
Only the env keys the manifest names are recorded; a Secret-backed key is recorded as its reference.

Source identity is the image, not ``OMI_BACKEND_RELEASE_SHA``: env merges never remove a value, so that
variable can name a release the revision does not serve (recorded only as ``release_env``). A serving
unit's source commit comes from its image's OCI ``org.opencontainers.image.revision`` label, else from
a commit-hex tag on the digest (same rule as omi-workspace ``infra/rollout/bin/serving_has.py``).
Ancestry ("contains commit X") is answered by ``git merge-base --is-ancestor`` in ``--repo``; a commit
missing locally is unknown, never "no". Gateway lanes are the lanes declared at the gateway's serving
commit (``backend/llm_gateway/config/lanes.yaml`` plus the feature lanes of
``generated_route_overrides.yaml``).

Any read that fails is recorded as an error and becomes ``unknown`` in the checker. Choose a read-only
GCP tier first::

  source ~/.local/bin/gcp-agent-env.sh ro-prod
  python3 backend/scripts/activation_collect.py --manifest backend/deploy/activation/conversations-v3.yaml \\
      --cluster prod-omi-gke --out /tmp/v3-state.json
  python3 backend/scripts/activation_check.py --manifest backend/deploy/activation/conversations-v3.yaml \\
      --state /tmp/v3-state.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import activation_check  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r'[0-9a-f]{40}')
HEX_TAG = re.compile(r'[0-9a-f]{7,40}')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
REVISION_LABEL = 'org.opencontainers.image.revision'
LANE_PREFIX = 'omi:auto:'
INDEX_TYPES = ('application/vnd.oci.image.index.v1+json', 'application/vnd.docker.distribution.manifest.list.v2+json')
ACCEPT = ', '.join(
    INDEX_TYPES + ('application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json')
)

Runner = Callable[[list[str]], str]


class ReadError(RuntimeError):
    """One read failed; the requirement that needed it is unknown."""


def run(argv: list[str], timeout: int = 90) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReadError(f'{Path(argv[0]).name}: {type(error).__name__}') from error
    if proc.returncode:
        raise ReadError(f'{Path(argv[0]).name} exit {proc.returncode}')
    return proc.stdout


# ---------------------------------------------------------------------------------------------- env


def manifest_env_keys(manifest: dict[str, Any]) -> dict[str, set[str]]:
    """{runtime: keys the manifest asks about}."""
    keys: dict[str, set[str]] = {}
    for req in manifest.get('env', []):
        for runtime in req['runtimes']:
            keys.setdefault(runtime, set()).update(req.get('keys') or req.get('any_of') or [])
    return keys


def cloud_run_env(container: dict[str, Any], wanted: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for entry in container.get('env', []) or []:
        name = entry.get('name')
        if name not in wanted and name != 'OMI_BACKEND_RELEASE_SHA':
            continue
        ref = (entry.get('valueFrom') or {}).get('secretKeyRef')
        if ref:
            out[name] = {'secret_ref': f"{ref.get('name', '')}:{ref.get('key', '')}"}
        elif 'valueFrom' in entry:
            out[name] = {'unknown': 'unsupported valueFrom'}
        else:
            out[name] = {'value': entry.get('value', '')}
    return out


def gke_env(container: dict[str, Any], wanted: set[str]) -> dict[str, Any]:
    """Record evidence from the pod spec. Kubernetes resolves external env values at container startup."""
    out: dict[str, Any] = {}
    for source in container.get('envFrom', []) or []:
        prefix = source.get('prefix', '')
        for key in wanted:
            if key.startswith(prefix):
                out[key] = {'unknown': 'envFrom value at container startup is unavailable'}
    for entry in container.get('env', []) or []:
        name = entry.get('name')
        if name not in wanted:
            continue
        value_from = entry.get('valueFrom') or {}
        value = entry.get('value', '')
        if 'secretKeyRef' in value_from:
            ref = value_from['secretKeyRef']
            if ref.get('optional'):
                out[name] = {'unknown': 'optional Secret binding at container startup is unavailable'}
            else:
                out[name] = {'secret_ref': f"{ref.get('name', '')}:{ref.get('key', '')}"}
        elif 'configMapKeyRef' in value_from:
            out[name] = {'unknown': 'ConfigMap value at container startup is unavailable'}
        elif value_from or '$(' in value or '$$' in value:
            out[name] = {'unknown': 'value depends on container startup'}
        else:
            out[name] = {'value': value}
    return out


# ---------------------------------------------------------------------------------------------- images


def google_host(host: str) -> bool:
    host = host.lower().partition(':')[0]
    return host == 'gcr.io' or host.endswith(
        ('.gcr.io', '-docker.pkg.dev', '.googleapis.com', '.googleusercontent.com')
    )


class GoogleOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != 'https' or not google_host(target.hostname or ''):  # the token rides the redirect
            raise ReadError('registry redirect outside Google')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Registry:
    """Docker registry v2 reads with the active (read-only) gcloud token; Google registries only."""

    def __init__(self, token: Callable[[], str], opener=None):
        self._token_fn = token
        self._token: str | None = None
        self._open = opener or urllib.request.build_opener(GoogleOnlyRedirects()).open

    def get(self, host: str, path: str, kind: str, ref: str, accept: str = ACCEPT) -> dict[str, Any]:
        if not google_host(host):
            raise ReadError('registry host is not Google')
        if self._token is None:
            try:
                self._token = self._token_fn().strip()
            except (OSError, subprocess.SubprocessError, ReadError) as error:
                raise ReadError(f'registry token unavailable: {type(error).__name__}') from error
        req = urllib.request.Request(
            f'https://{host}/v2/{path}/{kind}/{ref}',
            headers={'Authorization': f'Bearer {self._token}', 'Accept': accept},
        )
        try:
            with self._open(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise ReadError(f'registry {kind} read failed') from error

    def source(self, repository: str, digest: str) -> str:
        host, _, path = repository.partition('/')
        manifest = self.get(host, path, 'manifests', digest)
        if manifest.get('mediaType') in INDEX_TYPES or 'manifests' in manifest:
            amd = [
                m
                for m in manifest.get('manifests', [])
                if (m.get('platform') or {}).get('os') == 'linux'
                and (m.get('platform') or {}).get('architecture') == 'amd64'
            ]
            if len(amd) != 1:
                raise ReadError('image index ambiguous')
            manifest = self.get(host, path, 'manifests', amd[0]['digest'])
        config = (manifest.get('config') or {}).get('digest', '')
        if not DIGEST.fullmatch(config):
            raise ReadError('image config missing')
        labels = (self.get(host, path, 'blobs', config, accept='*/*').get('config') or {}).get('Labels') or {}
        if SHA.fullmatch(labels.get(REVISION_LABEL, '')):
            return labels[REVISION_LABEL]
        tags = ((self.get(host, path, 'tags', 'list').get('manifest') or {}).get(digest) or {}).get('tag') or []
        hexes = sorted(t for t in tags if HEX_TAG.fullmatch(t))
        if len(hexes) != 1:
            raise ReadError('image has no single commit tag or revision label')
        return hexes[0]


def app_container(containers: list[dict[str, Any]], name: str = '') -> dict[str, Any]:
    """The application container: the manifest's ``container`` name, else the only one, else the only one with ports."""
    if name:
        named = [c for c in containers if c.get('name') == name]
        if len(named) != 1:
            raise ReadError(f'container {name} not found')
        return named[0]
    if len(containers) == 1:
        return containers[0]
    with_ports = [c for c in containers if c.get('ports')]
    if len(with_ports) != 1:
        raise ReadError('application container ambiguous')
    return with_ports[0]


def split_image(image: str) -> tuple[str, str, str]:
    """'host/p/repo:tag@sha256:x' -> ('host/p/repo', 'tag', 'sha256:x'); missing parts are ''."""
    name, _, digest = image.partition('@')
    last = name.rpartition('/')[2]
    tag = ''
    if ':' in last:
        name, _, tag = name.rpartition(':')
    return name, tag, digest


class Git:
    def __init__(self, repo: Path, runner: Runner = run):
        self.repo, self.run = repo, runner

    def resolve(self, ref: str) -> str:
        try:
            out = self.run(
                ['git', '-C', str(self.repo), 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}']
            ).strip()
        except ReadError as error:
            raise ReadError(f'commit {ref[:12]} not in local repo (git fetch origin)') from error
        if not SHA.fullmatch(out):
            raise ReadError(f'commit {ref[:12]} ambiguous')
        return out

    def contains(self, source: str, commit: str) -> bool:
        source, commit = self.resolve(source), self.resolve(commit)
        try:
            proc = subprocess.run(
                ['git', '-C', str(self.repo), 'merge-base', '--is-ancestor', commit, source],
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ReadError(f'merge-base: {type(error).__name__}') from error
        if proc.returncode not in (0, 1):
            raise ReadError('merge-base failed')
        return proc.returncode == 0

    def show(self, sha: str, path: str) -> str:
        return self.run(['git', '-C', str(self.repo), 'show', f'{sha}:{path}'])


def lanes_at(git: Git, sha: str) -> list[str]:
    lanes = yaml.safe_load(git.show(sha, 'backend/llm_gateway/config/lanes.yaml')) or {}
    overrides = yaml.safe_load(git.show(sha, 'backend/llm_gateway/config/generated_route_overrides.yaml')) or {}
    ids = {lane['lane_id'] for lane in lanes.get('lanes', []) if isinstance(lane, dict) and lane.get('lane_id')}
    for item in overrides.get('generated_route_overrides', []) or []:
        if isinstance(item, dict) and item.get('feature'):
            ids.add(LANE_PREFIX + str(item['feature']).replace('_', '-'))
    return sorted(ids)


# ---------------------------------------------------------------------------------------------- readers


class Collector:
    def __init__(
        self,
        project: str,
        region: str,
        git: Git,
        runner: Runner = run,
        registry: Registry | None = None,
        kubectl: list[str] | None = None,
        promoted_registry: Registry | None = None,
        *,
        cluster: str | None = None,
    ):
        self.project, self.region, self.cluster = project, region, cluster
        self.git, self.run = git, runner
        self.registry = registry or Registry(lambda: self.run(['gcloud', 'auth', 'print-access-token']))
        # Promoted images (prod pusher) keep their commit tag only in the qualifying registry.
        self.promoted_registry = promoted_registry or self.registry
        self.kubectl = kubectl

    def gcloud_json(self, *args: str) -> Any:
        return json.loads(self.run(['gcloud', *args, '--project', self.project, '--format=json']))

    def source_of(self, image: str, running_digest: str = '') -> str:
        repository, tag, digest = split_image(image)
        digest = running_digest or digest
        if digest:
            return self.git.resolve(self.registry.source(repository, digest))
        if HEX_TAG.fullmatch(tag):
            return self.git.resolve(tag)
        raise ReadError('image is neither digest-pinned nor commit-tagged')

    def cloud_run(self, service: str, wanted: set[str]) -> dict[str, Any]:
        flags = ('--region', self.region)
        doc = self.gcloud_json('run', 'services', 'describe', service, *flags)
        traffic: dict[str, float] = {}
        for target in (doc.get('status') or {}).get('traffic') or []:
            if target.get('percent'):
                if not target.get('revisionName'):
                    raise ReadError('traffic target without revision')
                traffic[target['revisionName']] = traffic.get(target['revisionName'], 0) + target['percent']
        if not traffic or sum(traffic.values()) != 100:
            raise ReadError('status.traffic does not sum to 100')
        units = []
        for name, percent in sorted(traffic.items()):
            revision = self.gcloud_json('run', 'revisions', 'describe', name, *flags)
            app = app_container(revision['spec']['containers'])
            unit: dict[str, Any] = {'name': name, 'percent': percent}
            env = cloud_run_env(app, wanted)
            release = env.pop('OMI_BACKEND_RELEASE_SHA', {}).get('value')
            if release:
                unit['release_env'] = release
            unit['env'] = env
            image = app.get('image', '')
            digest = (revision.get('status') or {}).get('imageDigest', '')
            try:
                unit['source_sha'] = self.source_of(image, digest.rpartition('@')[2] if '@' in digest else '')
            except ReadError as error:
                unit['source_error'] = str(error)
            units.append(unit)
        return {'kind': 'cloud_run', 'serving': units}

    def digest_source(self, repository: str, digest: str, promoted_from: list[str]) -> str:
        try:
            return self.git.resolve(self.registry.source(repository, digest))
        except ReadError as error:
            for origin in promoted_from:
                try:
                    return self.git.resolve(self.promoted_registry.source(origin, digest))
                except ReadError:
                    continue
            raise ReadError(f'{error}; promoted_from unreadable' if promoted_from else str(error)) from error

    def gke(
        self, namespace: str, deployment: str, wanted: set[str], promoted_from: list[str] = (), container: str = ''
    ) -> dict[str, Any]:
        if not self.kubectl:
            raise ReadError('credentials for the manifest GKE cluster are unavailable')
        deploy = json.loads(self.run([*self.kubectl, '-n', namespace, 'get', 'deployment', deployment, '-o', 'json']))
        selector = ((deploy.get('spec') or {}).get('selector') or {}).get('matchLabels') or {}
        if not selector:
            raise ReadError('deployment selector unreadable')
        labels = ','.join(f'{k}={v}' for k, v in sorted(selector.items()))
        pods = json.loads(self.run([*self.kubectl, '-n', namespace, 'get', 'pods', '-l', labels, '-o', 'json']))
        groups: dict[tuple[str, str, str], int] = {}
        for pod in pods.get('items', []):
            status = pod.get('status') or {}
            if status.get('phase') != 'Running':
                continue
            app = app_container((pod.get('spec') or {}).get('containers') or [], container)
            repository = split_image(app.get('image', ''))[0]
            image_id = next(
                (
                    item.get('imageID', '').rpartition('@')[2]
                    for item in status.get('containerStatuses') or []
                    if item.get('name') == app['name']
                ),
                '',
            )
            digest = image_id if DIGEST.fullmatch(image_id) else ''
            # An env-only rollout can serve several configurations of the same image.
            key = (repository, digest, json.dumps(gke_env(app, wanted), sort_keys=True))
            groups[key] = groups.get(key, 0) + 1
        total = sum(groups.values())
        if not total:
            raise ReadError('no running pods')
        units = []
        sources: dict[tuple[str, str], dict[str, str]] = {}
        for index, ((repository, digest, env_json), count) in enumerate(sorted(groups.items()), start=1):
            unit: dict[str, Any] = {
                'name': f'{deployment}@{digest[7:19] or "unknown"}-{index}',
                'percent': round(100 * count / total, 1),
                'pods': count,
                'env': json.loads(env_json),
            }
            image = (repository, digest)
            if image not in sources:
                try:
                    if not digest:
                        raise ReadError('running image digest unknown')
                    sources[image] = {'source_sha': self.digest_source(repository, digest, list(promoted_from))}
                except ReadError as error:
                    sources[image] = {'source_error': str(error)}
            unit.update(sources[image])
            units.append(unit)
        return {'kind': 'gke', 'serving': units}

    def listed(self, kind: list[str], location: str, ready_field: str = 'state') -> dict[str, Any]:
        """{name: {exists, state}} from one list call. Absent from a successful list is "does not exist";
        a failed list (for example PERMISSION_DENIED, which also says "may not exist") is an error."""
        try:
            items = self.gcloud_json(*kind, 'list', '--location', location)
        except ReadError as error:
            return {'_error': f"{' '.join(kind)} list: {error}"}
        return {
            str(item.get('name', '')).rpartition('/')[2]: {'exists': True, 'state': item.get(ready_field, '')}
            for item in items or []
        }


def _objects(collector: Collector, kind: list[str], items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by_location: dict[str, dict[str, Any]] = {}
    for item in items:
        location = item.get('location', collector.region)
        if location not in by_location:
            by_location[location] = collector.listed(kind, location)
        listing = by_location[location]
        if '_error' in listing:
            out[item['name']] = {'error': listing['_error']}
        else:
            out[item['name']] = listing.get(item['name'], {'exists': False})
    return out


def collect(manifest: dict[str, Any], collector: Collector) -> dict[str, Any]:
    activation_check.validate_manifest(manifest)
    for name in ('project', 'region', 'cluster'):
        if getattr(collector, name) != manifest.get(name):
            raise activation_check.InvalidInput(f'collector {name} does not match manifest.{name}')
    wanted = manifest_env_keys(manifest)
    services: dict[str, Any] = {}
    for name, svc in manifest['services'].items():
        try:
            if svc['kind'] == 'cloud_run':
                services[name] = collector.cloud_run(svc.get('service', name), wanted.get(name, set()))
            else:
                services[name] = collector.gke(
                    svc['namespace'],
                    svc['deployment'],
                    wanted.get(name, set()),
                    svc.get('promoted_from', []),
                    svc.get('container', ''),
                )
        except (ReadError, KeyError, ValueError) as error:
            services[name] = {'kind': svc['kind'], 'error': f'{type(error).__name__}: {error}'}
    ancestry: dict[str, dict[str, bool]] = {}
    for name, svc in manifest['services'].items():
        for unit in services[name].get('serving', []):
            source = unit.get('source_sha')
            for item in svc.get('contains', []):
                if not source:
                    continue
                try:
                    ancestry.setdefault(source, {})[item['commit']] = collector.git.contains(source, item['commit'])
                except ReadError as error:
                    unit.setdefault('ancestry_errors', []).append(f"{item['commit'][:12]}: {error}")
    lanes = manifest.get('gateway_lanes')
    if lanes:
        for unit in services.get(lanes['service'], {}).get('serving', []):
            if not unit.get('source_sha'):
                unit['lanes_error'] = 'serving source unknown'
                continue
            try:
                unit['lanes'] = lanes_at(collector.git, unit['source_sha'])
            except (ReadError, ValueError, yaml.YAMLError) as error:
                unit['lanes_error'] = f'{type(error).__name__}: {error}'[:200]
    queues = _objects(collector, ['tasks', 'queues'], manifest.get('queues', []))
    jobs = _objects(collector, ['scheduler', 'jobs'], manifest.get('scheduler_jobs', []))
    return {
        'schema_version': activation_check.SCHEMA_VERSION,
        'feature': manifest['feature'],
        'environment': manifest['environment'],
        'collected_at': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'project': collector.project,
        'region': collector.region,
        'cluster': collector.cluster,
        'services': services,
        'queues': queues,
        'scheduler_jobs': jobs,
        'ancestry': ancestry,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--out', type=Path, help='write state JSON here (default stdout)')
    parser.add_argument('--project', help='assert the manifest project')
    parser.add_argument('--region', help='assert the manifest region')
    parser.add_argument('--cluster', help='assert the manifest GKE cluster')
    parser.add_argument(
        '--promoted-from-gcloud-config',
        default=os.environ.get('ACTIVATION_PROMOTED_FROM_CLOUDSDK_CONFIG', ''),
        help='CLOUDSDK_CONFIG of a read-only identity for promoted_from registries (e.g. the ro-dev tier)',
    )
    parser.add_argument('--repo', type=Path, default=REPO_ROOT, help='git checkout with the serving commits fetched')
    args = parser.parse_args(argv)
    try:
        manifest = activation_check.load_manifest(args.manifest)
    except (activation_check.InvalidInput, OSError) as error:
        print(f'activation_collect: invalid manifest: {error}', file=sys.stderr)
        return activation_check.EXIT_INVALID
    for name in ('project', 'region', 'cluster'):
        supplied = getattr(args, name)
        if supplied is not None and supplied != manifest.get(name):
            print(f'activation_collect: --{name} does not match manifest.{name}', file=sys.stderr)
            return activation_check.EXIT_INVALID

    project, region, cluster = manifest['project'], manifest['region'], manifest.get('cluster')
    with tempfile.TemporaryDirectory(prefix='activation-collect-') as scratch:
        kubectl = None
        if cluster:
            kubeconfig = str(Path(scratch) / 'config')
            env = {**os.environ, 'KUBECONFIG': kubeconfig}
            proc = subprocess.run(
                [
                    'gcloud',
                    'container',
                    'clusters',
                    'get-credentials',
                    cluster,
                    '--region',
                    region,
                    '--project',
                    project,
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )
            if proc.returncode:
                print(
                    'activation_collect: cluster credentials unavailable; GKE services will be unknown', file=sys.stderr
                )
            else:
                kubectl = ['kubectl', '--kubeconfig', kubeconfig]
        promoted = None
        if args.promoted_from_gcloud_config:
            promoted_env = {**os.environ, 'CLOUDSDK_CONFIG': args.promoted_from_gcloud_config}
            for key in ('GOOGLE_APPLICATION_CREDENTIALS', 'CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE'):
                promoted_env.pop(key, None)
            promoted = Registry(
                lambda: subprocess.run(
                    ['gcloud', 'auth', 'print-access-token'],
                    capture_output=True,
                    text=True,
                    env=promoted_env,
                    timeout=90,
                ).stdout
            )
        collector = Collector(
            project, region, Git(args.repo), kubectl=kubectl, promoted_registry=promoted, cluster=cluster
        )
        state = collect(manifest, collector)
    text = json.dumps(state, indent=2, sort_keys=True) + '\n'
    if args.out:
        args.out.write_text(text, encoding='utf-8')
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
