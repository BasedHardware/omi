# LIFECYCLE: permanent
"""Fail-closed evidence gate for production raises. Uses the writer's credentials only.

No credential loading, fleet bus access, or production IO at import time. The CLI
is an operator diagnostic; writers call preflight in-process at the write boundary.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import math
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[3]
METRIC = re.compile(r'\bomi_[a-z0-9_]+\b')
SHA = re.compile(r'[0-9a-f]{7,40}')
RAMP_NAMES = frozenset(
    {
        'batch-pipeline',
        'first-summary',
        'batch-live-stt-retire',
        'legacy-sync',
        'batch-vendor-routing',
        'new-owner-cell1',
    }
)


class Unread(RuntimeError):
    def __init__(self, what: str, reason: str):
        self.what, self.reason = what, reason


def run(argv: list[str], *, timeout: float = 60) -> subprocess.CompletedProcess:
    """Single subprocess seam; never print subprocess stderr (may contain credentials)."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def read_json(request: urllib.request.Request, *, timeout: float = 60) -> dict:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def runtime_roster(reading_sites: list[str], inventory: dict) -> list[dict]:
    """Section 2 containment mapping, independent of Git, credentials and runtime IO."""
    families: set[str] = set()
    for site in reading_sites:
        path = site.removeprefix('backend/')
        if not path.endswith('.py') or path.startswith(('tests/', 'scripts/rollout/')):
            continue
        if path.startswith('diarizer/'):
            families.add('batch-pipeline-worker')
        else:
            families.add('backend')
            if path.startswith(('config/', 'database/', 'models/', 'utils/')):
                families.update(('pusher', 'batch-pipeline-worker'))
            elif path.startswith(('routers/', 'services/', 'pusher/', 'testing/parity_pack_v0/')):
                families.add('pusher')
            elif path.startswith('scripts/record_seal') or path == 'omi_logging.py':
                families.add('batch-pipeline-worker')
    services = dict(inventory['services'])
    # runtime_images.services also drives direct deploy admission. Record-seal
    # is a child in charts/batch-pipeline-worker/templates/record-seal-worker.yaml,
    # not a standalone deploy target: derive its identical image from the parent
    # rather than changing that registry's admission semantics.
    if 'batch-pipeline-worker' in services and 'record-seal-worker' not in services:
        seal = dict(services['batch-pipeline-worker'])
        seal.pop('deployed_as', None)
        services['record-seal-worker'] = seal
    return [
        {'name': name, **spec}
        for name, spec in sorted(services.items())
        if image_family(spec.get('current_image')) in families
        and 'No pilot is installed' not in spec.get('image_built_elsewhere', '')
        and spec.get('installed', True)
    ]


def image_family(image: str | None) -> str | None:
    # Include role-image migrations; moving one service to its admitted role
    # image must never silently remove it from the containment roster.
    if image in {
        'backend',
        'backend-api',
        'backend-workers',
        'backend-realtime',
        'backend-gateway',
        'backend-sync-backfill-worker',
    }:
        return 'backend'
    if image in {'pusher', 'backend-pusher'}:
        return 'pusher'
    return image


def serving_revision(service: dict) -> str | None:
    # Vendored algorithm from omi-workspace infra/rollout/bin/serving_revision.py.
    traffic = [t for t in service.get('status', {}).get('traffic', []) if t.get('percent')]
    if len(traffic) == 1 and traffic[0].get('percent') == 100:
        return traffic[0].get('revisionName')
    return None


class MixedWrite(ValueError):
    def __init__(self):
        super().__init__('RAMP_PREFLIGHT REFUSE mixed_write: run the narrowing change alone first, then the raise')


def widens_exposure(current: dict | None, change: dict | None) -> bool:
    """Classify a flag rule or _ramp patch before any liveness IO. Reject mixed writes.

    Omitted fields are unchanged. Deleting an Omi rule returns control to
    PostHog and can widen exposure unless it is active at 100% with no denied
    UIDs. A new rule starts inactive at zero percent with empty allow/deny sets.
    """
    before = current or {}
    if change is None:
        return not (
            before.get('active') is True and before.get('rollout_percentage') == 100 and not before.get('deny_uids')
        )
    pairs = [
        (float((before.get('percents') or {}).get(name, 0)), float(percent))
        for name, percent in (change.get('percents') or {}).items()
    ]
    if 'rollout_percentage' in change:
        pairs.append((float(before.get('rollout_percentage') or 0), float(change['rollout_percentage'] or 0)))
    if 'active' in change:
        pairs.append((float(before.get('active') is True), float(change['active'] is True)))
    widening = any(new > old for old, new in pairs)
    narrowing = any(new < old for old, new in pairs)
    for field, additions_widen in (('allow_uids', True), ('deny_uids', False)):
        old = set(before.get(field) or ())
        new = set(change.get(field) or ()) if field in change else old
        added, removed = bool(new - old), bool(old - new)
        widening |= added if additions_widen else removed
        narrowing |= removed if additions_widen else added
    if widening and narrowing:
        raise MixedWrite()
    return widening


def override_reason(reason: str, accept: str | None) -> str:
    if accept is None:
        return reason
    if len(accept.strip()) < 15 or any(ord(c) < 32 for c in accept):
        raise ValueError('--accept-not-live requires at least 15 characters and no control characters')
    return reason + ' accept_not_live:' + accept


class Prover:
    def __init__(
        self, repo: Path, ref: str, project: str, region: str, deadline_min: float, runner: Callable, fetch: Callable
    ):
        self.repo, self.ref, self.project, self.region = repo, ref, project, region
        self.deadline = time.monotonic() + deadline_min * 60
        self.runner, self.fetch = runner, fetch
        self.access_token: str | None = None
        self.image_commits: dict[str, str | None] = {}

    def timeout(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Unread('deadline', 'deadline_exceeded')
        return min(60, left)

    def command(self, argv: list[str], *, empty_ok: bool = False) -> str:
        try:
            result = self.runner(argv, timeout=self.timeout())
        except (OSError, subprocess.SubprocessError):
            raise Unread(argv[0], 'command_failed') from None
        if result.returncode and not (empty_ok and result.returncode == 1):
            raise Unread(argv[0], 'command_failed')
        return result.stdout.strip()

    def git(self, *args: str, empty_ok: bool = False) -> str:
        return self.command(['git', '-C', str(self.repo), *args], empty_ok=empty_ok)

    def ancestor(self, older: str, newer: str) -> bool:
        result = self.runner(
            ['git', '-C', str(self.repo), 'merge-base', '--is-ancestor', older, newer], timeout=self.timeout()
        )
        if result.returncode not in (0, 1):
            raise Unread('git', 'ancestry_failed')
        return result.returncode == 0

    def source(self, path: str) -> Any:
        return yaml.safe_load(self.git('show', f'{self.ref}:{path}'))

    def json_command(self, argv: list[str]) -> dict:
        return json.loads(self.command(argv))

    def token(self) -> str:
        if self.access_token is None:
            self.access_token = self.command(['gcloud', 'auth', 'print-access-token'])
        if not self.access_token:
            raise Unread('credentials', 'token_empty')
        return self.access_token

    def request(self, url: str, *, registry: bool = False) -> dict:
        auth = 'Bearer ' + self.token()
        if registry:
            auth = 'Basic ' + base64.b64encode(('oauth2accesstoken:' + self.token()).encode()).decode()
        request = urllib.request.Request(
            url,
            headers={
                'Authorization': auth,
                'Accept': 'application/vnd.docker.distribution.manifest.v2+json',
            },
        )
        try:
            return self.fetch(request, timeout=self.timeout())
        except (OSError, ValueError, http.client.HTTPException):
            raise Unread('image' if registry else 'prometheus', 'transport_failed') from None

    def commit(self, value: str | None) -> str | None:
        if not value or not SHA.fullmatch(value):
            return None
        result = self.runner(
            ['git', '-C', str(self.repo), 'rev-parse', '--verify', value + '^{commit}'], timeout=self.timeout()
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def image_commit(self, image: str) -> str | None:
        if image in self.image_commits:
            return self.image_commits[image]
        if '@sha256:' not in image:
            tag = image.rsplit(':', 1)[-1]
            return self.commit(tag)
        # GCR/Artifact Registry Docker config holds omi.release.tree; gcloud's
        # image_summary does not expose Docker labels. Read manifest+config using
        # the very same operator access token, with no docker credential loader.
        host, _, path = image.partition('/')
        repository, _, digest = path.partition('@')
        if not (host == 'gcr.io' or host.endswith('.gcr.io') or host.endswith('-docker.pkg.dev')):
            return None
        manifest = self.request(f'https://{host}/v2/{repository}/manifests/{digest}', registry=True)
        if 'manifests' in manifest:
            candidates = [
                m
                for m in manifest['manifests']
                if m.get('platform', {}).get('os') == 'linux' and m.get('platform', {}).get('architecture') == 'amd64'
            ]
            if len(candidates) != 1:
                return None
            manifest = self.request(
                f"https://{host}/v2/{repository}/manifests/{candidates[0]['digest']}", registry=True
            )
        config_digest = manifest.get('config', {}).get('digest')
        if not config_digest:
            return None
        config = self.request(f'https://{host}/v2/{repository}/blobs/{config_digest}', registry=True)
        labels = config.get('config', {}).get('Labels') or {}
        sha = self.commit(labels.get('omi.release.sha') or labels.get('org.opencontainers.image.revision'))
        if sha is None:
            tree = labels.get('omi.release.tree')
            if tree and re.fullmatch(r'[0-9a-f]{40}', tree):
                witnesses = [
                    line.split()[0]
                    for line in self.git('log', '--format=%H %T', self.ref).splitlines()
                    if line.split()[1] == tree
                ]
                sha = witnesses[-1] if witnesses else None
        self.image_commits[image] = sha
        return sha

    @staticmethod
    def cloud_run_format(containers: str) -> str:
        # Project in gcloud itself: the subprocess must never return other env
        # values, including inline secrets. Keep the nested API response shape.
        return (
            f'--format=json({containers}[0].image,metadata.labels,'
            f'{containers}[0].env.filter("name=OMI_BACKEND_RELEASE_SHA"))'
        )

    def runtime_commits(self, runtime: dict) -> list[tuple[str | None, str]]:
        name, platform = runtime.get('deployed_as', runtime['name']), runtime['platform']
        gcloud = ['gcloud', 'run']
        options = ['--project', self.project, '--region', self.region]
        if platform == 'cloud-run':
            service = self.json_command(
                gcloud + ['services', 'describe', name, *options, '--format=json(status.traffic)']
            )
            revision = serving_revision(service)
            if not revision:
                return [(None, 'unknown')]
            doc = self.json_command(
                gcloud + ['revisions', 'describe', revision, *options, self.cloud_run_format('spec.containers')]
            )
            container = doc['spec']['containers'][0]
            env_sha = next(
                (e.get('value') for e in container.get('env', []) if e.get('name') == 'OMI_BACKEND_RELEASE_SHA'), None
            )
            image = container['image']
            if env_sha:
                return [(self.commit(env_sha), image)]
            sha = self.image_commit(image)
            return [(sha or self.commit(doc.get('metadata', {}).get('labels', {}).get('commit-sha')), image)]
        if platform == 'cloud-run-job':
            doc = self.json_command(
                gcloud
                + [
                    'jobs',
                    'describe',
                    name,
                    *options,
                    self.cloud_run_format('spec.template.spec.template.spec.containers'),
                ]
            )
            container = doc['spec']['template']['spec']['template']['spec']['containers'][0]
            image = container['image']
            env_sha = next(
                (e.get('value') for e in container.get('env', []) if e.get('name') == 'OMI_BACKEND_RELEASE_SHA'), None
            )
            return [(self.commit(env_sha) if env_sha else self.image_commit(image), image)]
        if platform != 'gke':
            raise Unread(name, 'platform_unknown')
        pods = self.json_command(
            [
                'kubectl',
                '--context',
                f'gke_{self.project}_{self.region}_prod-omi-gke',
                '-n',
                'prod-omi-backend',
                'get',
                'pods',
                '-l',
                f'app.kubernetes.io/name={name}',
                '-o',
                'json',
            ]
        )['items']
        # Check every nonterminated replica, including old images during a roll.
        pods = [p for p in pods if p.get('status', {}).get('phase') not in ('Succeeded', 'Failed')]
        if not pods:
            return [(None, 'unknown')]
        commits = []
        for pod in pods:
            containers = pod['spec']['containers']
            images = [
                c['image']
                for c in containers
                if c.get('name') == name
                or c['image'].split('@')[0].rsplit('/', 1)[-1].split(':')[0]
                in {runtime['current_image'], runtime.get('image'), name}
            ]
            if not images:
                commits.append((None, 'unknown'))
            for image in images:
                commits.append((self.image_commit(image), image))
        return commits

    def metric(self, query: str) -> list[list[float]]:
        end = time.time()
        params = urllib.parse.urlencode({'query': query, 'start': end - 1800, 'end': end, 'step': 60})
        data = self.request(
            f'https://monitoring.googleapis.com/v1/projects/{self.project}/location/global/'
            f'prometheus/api/v1/query_range?{params}'
        )
        if data.get('status') != 'success' or data.get('data', {}).get('resultType') != 'matrix':
            raise Unread('prometheus', 'invalid_matrix')
        values = [[float(point[1]) for point in series['values']] for series in data['data']['result']]
        if any(not math.isfinite(v) for series in values for v in series):
            raise Unread('prometheus', 'invalid_sample')
        return values

    def check(self, key: str) -> tuple[bool, str, dict]:
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]*', key):
            raise Unread('key', 'key_invalid')
        # The reader roster and introducing commits must come from fresh main,
        # even when the caller selects another named ref for diagnosis.
        try:
            self.git('fetch', '--quiet', 'origin', 'main')
        except Unread:
            raise Unread('origin', 'fetch_failed') from None
        ramp = key in RAMP_NAMES
        # _ramp readers must all understand a new name (store rejects unknown
        # names). Bind both the runtime reader and that name's writer schema.
        needle = 'utils.rollout.runtime_percent' if ramp else key
        sites = self.git('grep', '-l', '-w', '-F', needle, self.ref, '--', 'backend/', empty_ok=True)
        paths = [line.split(':', 1)[1] for line in sites.splitlines()]
        inventory = self.source('backend/runtime_images.json')
        roster = runtime_roster(paths, inventory)
        if not roster:
            return False, 'key_unread', {'key': key}
        commits = []
        for args in (
            (
                'log',
                '-1',
                '--format=%H',
                '-S' + key,
                self.ref,
                '--',
                'backend/database/rollout_cohorts.py' if ramp else 'backend/',
            ),
            ('log', '-1', '--format=%H', '-S"key":"' + key + '"', self.ref, '--', 'config/feature-flags.yaml'),
        ):
            commit = self.git(*args)
            if commit:
                commits.append(commit)
        if ramp:
            reader = self.git(
                'log', '-1', '--format=%H', '-Swrite_ramp', self.ref, '--', 'backend/utils/rollout/runtime_percent.py'
            )
            if reader:
                commits.append(reader)
        commits = list(dict.fromkeys(commits))
        if not commits:
            raise Unread('introducing_commit', 'commit_missing')
        # On one named main lineage, the descendant is newer even if commit
        # timestamps are out of order.
        required = commits[0]
        for commit in commits[1:]:
            if self.ancestor(required, commit):
                required = commit
        serving = []
        for runtime in roster:
            for commit, image in self.runtime_commits(runtime):
                if commit is None:
                    if image == 'unknown':
                        return (
                            False,
                            'not_live',
                            {
                                'key': key,
                                'runtime': runtime['platform'] + '/' + runtime['name'],
                                'serving': 'unknown',
                                'requires': required[:7],
                            },
                        )
                    return (
                        False,
                        'commit_unbound',
                        {
                            'key': key,
                            'runtime': runtime['name'],
                            'image': (
                                image.split('@sha256:')[-1][:12] if '@sha256:' in image else image.rsplit(':', 1)[-1]
                            ),
                        },
                    )
                # Reader and registry introductions can be on parallel merged
                # branches. Every source commit must be present in the serving
                # image; selecting one by timestamp would leave the other unproved.
                missing = next((source for source in commits if not self.ancestor(source, commit)), None)
                if missing is not None:
                    return (
                        False,
                        'not_live',
                        {
                            'key': key,
                            'runtime': runtime['platform'] + '/' + runtime['name'],
                            'serving': commit[:7],
                            'requires': missing[:7],
                        },
                    )
                serving.append(commit)
        jobs = self.source('backend/charts/monitoring/expected-targets.prod.yaml')['scrape_jobs']
        checked = set()
        for runtime in roster:
            if runtime['platform'] == 'cloud-run-job':
                print(f"RAMP_PREFLIGHT NOTE scrape_not_applicable runtime={runtime['name']}")
                continue
            candidates = [
                job['name']
                for job in jobs
                if (runtime['platform'] == 'cloud-run' and job.get('source') == 'prometheus.googleapis.com/omi_')
                or (runtime['platform'] == 'gke' and job['name'] == runtime['name'] + '-metrics')
            ]
            if len(candidates) != 1:
                return False, 'scrape_unknown', {'runtime': runtime['name']}
            job = candidates[0]
            if job in checked:
                continue
            checked.add(job)
            samples = self.metric('min(up{job=' + json.dumps(job) + '})')
            flat = [v for series in samples for v in series]
            if not flat or any(not points for points in samples) or any(v != 1 for v in flat):
                return False, 'scrape_dead', {'key': key, 'job': job, 'up': min(flat) if flat else 'absent'}
        rows = self.source('config/feature-flags.yaml')['flags']
        row = next((r for r in rows if r['key'] == key), {})
        clean = (row.get('ramp') or {}).get('clean_metric') or ''
        metrics = METRIC.findall(clean)
        metric, series = '-', 0
        if ramp:
            metric = 'omi_runtime_percent'
            selector = metric + '{name=' + json.dumps(key) + '}'
        elif metrics:
            metric = selector = metrics[0]
        else:
            selector = None
            if 'ramp' in row:
                print(f'RAMP_PREFLIGHT NOTE metric_unparsed key={key}')
        if selector:
            samples = self.metric(selector)
            series = sum(any(v != 0 for v in points) for points in samples)
            if not series:
                return False, 'metric_dead', {'key': key, 'metric': metric, 'window': '30m'}
        oldest = serving[0]
        for commit in serving[1:]:
            if self.ancestor(commit, oldest):
                oldest = commit
        return (
            True,
            'pass',
            {'key': key, 'runtimes': len(roster), 'oldest_serving': oldest[:7], 'metric': metric, 'series': series},
        )


def preflight(
    key: str,
    raise_to: float | None = None,
    repo: Path = ROOT,
    *,
    ref: str = 'origin/main',
    project: str = 'based-hardware',
    region: str = 'us-central1',
    deadline_min: float = 15,
    accept_not_live: str | None = None,
    runner: Callable = run,
    fetch: Callable = read_json,
) -> tuple[bool, str, dict]:
    """Return (ok, token, detail), without changing configuration or credentials."""
    override_reason('', accept_not_live)
    try:
        if not math.isfinite(deadline_min) or deadline_min <= 0:
            raise Unread('deadline', 'deadline_invalid')
        result = Prover(Path(repo), ref, project, region, deadline_min, runner, fetch).check(key)
    except Unread as error:
        result = False, 'unread', {'what': error.what, 'reason': error.reason}
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ):
        result = False, 'unread', {'what': 'evidence', 'reason': 'invalid_evidence'}
    ok, token, detail = result
    if not ok and accept_not_live is not None:
        return True, 'override', {**detail, 'key': key, 'reason': accept_not_live, 'failure': token}
    return result


def report(result: tuple[bool, str, dict]) -> int:
    ok, token, detail = result
    if token == 'override':
        detail = {'key': detail['key'], 'reason': detail['reason'], **detail}
    if token == 'unread':
        print(f"RAMP_PREFLIGHT UNREAD {detail['what']} reason={detail['reason']}")
    else:
        status = 'OVERRIDE' if token == 'override' else ('PASS' if ok else 'REFUSE ' + token)
        print('RAMP_PREFLIGHT ' + status + ' ' + ' '.join(f'{k}={v}' for k, v in detail.items()))
    return 0 if ok else (4 if token == 'unread' else 3)


def require(key: str, raise_to: float, accept_not_live: str | None = None) -> None:
    result = preflight(key, raise_to, accept_not_live=accept_not_live)
    code = report(result)
    if code:
        raise SystemExit(code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('key')
    parser.add_argument('--raise-to', type=float)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--ref', default='origin/main')
    parser.add_argument('--project', default='based-hardware')
    parser.add_argument('--region', default='us-central1')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--accept-not-live')
    parser.add_argument('--deadline-min', type=float, default=15)
    args = parser.parse_args(argv)
    try:
        result = preflight(
            args.key,
            args.raise_to,
            args.repo,
            ref=args.ref,
            project=args.project,
            region=args.region,
            deadline_min=args.deadline_min,
            accept_not_live=args.accept_not_live,
        )
    except ValueError as error:
        parser.error(str(error))
    code = report(result)
    if args.json:
        print(json.dumps({'ok': result[0], 'token': result[1], 'detail': result[2]}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
