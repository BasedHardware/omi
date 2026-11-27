"""serving_has: is commit SHA live on SERVICE? Answered from the image, never from OMI_BACKEND_RELEASE_SHA.

usage: serving_has.py SHA SERVICE [--repo REPO] [--json]          Cloud Run service (traffic from status.traffic)
       serving_has.py SHA WORKLOAD --gke [--repo REPO]             GKE running pod digests
       serving_has.py --image-revision IMAGE@sha256:...            print the image's source revision

For every revision that receives traffic in status.traffic (percent > 0), read the revision's pinned image digest,
read that image's OCI config label org.opencontainers.image.revision from the registry (gcp_backend.yml stamps it at
build time; one digest is one source tree), then ask `git merge-base --is-ancestor SHA <label>`.

OMI_BACKEND_RELEASE_SHA is not read: env merges never remove a value, so on sync/integration it reported 0a31a3ed
across many deploys (10-31..11-02) and misled five lanes. The revision's commit-sha label is printed as a cross-check
only; it is set by whoever deploys and is not proof of the image.

desktop-backend is the one exception (RELEASE_STAMP_ENV): its deploy workflow checks out the admitted DEPLOY_SHA,
verifies the checkout is exact, stamps OMI_DESKTOP_BACKEND_RELEASE_SHA with it and embeds the same sha12 in the
revision suffix, then removes the image's candidate tag -- so the registry carries no revision evidence at all and
the stamp validated against the workflow revision name is the image-independent source. Its commit-sha label is
dispatch-head metadata, not the build (SCA-3013: run 44937790094 labeled fb6048ce while serving a 24d814d9 build).

Prints one line per traffic revision and a verdict:
  REVISION <name> percent=<n> digest=<12> source=<sha12|unknown> has=<yes|no|unknown>
  SERVING_HAS yes|partial|no|unknown service=<s> sha=<sha12> traffic_with=<percent>
Exit 0 yes (all traffic contains SHA), 1 no or partial, 2 unknown (any read failed; fail closed).
Caller selects a read-only GCP agent tier first (gcp-agent-env.sh ro-prod). Prints no env values.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
SHA = re.compile(r'[0-9a-f]{40}')
REVISION_LABEL = 'org.opencontainers.image.revision'
# Services whose deploy pipeline stamps the verified release itself (desktop_backend_prod.yml), used when the
# registry proves nothing. Keys are also the services whose commit-sha revision label is dispatch-head metadata.
RELEASE_STAMP_ENV = {'desktop-backend': 'OMI_DESKTOP_BACKEND_RELEASE_SHA'}
WORKFLOW_REVISION_NAME = r'-([0-9a-f]{12})-[0-9]+(?:-[0-9]+)?(?:-base)?\Z'
GIT = os.environ.get('GIT', 'git')
GCLOUD = os.environ.get('GCLOUD', 'gcloud')
INDEX_TYPES = ('application/vnd.oci.image.index.v1+json', 'application/vnd.docker.distribution.manifest.list.v2+json')
ACCEPT = ', '.join(
    INDEX_TYPES + ('application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json')
)


class Unknown(ValueError):
    """A read failed or was ambiguous; the answer is unknown, never yes."""


def command(argv, timeout=90):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise Unknown(f'command_failed:{Path(argv[0]).name}')
    return r.stdout


def split_image(image):
    """gcr.io/p/repo@sha256:x -> ('gcr.io', 'p/repo', 'sha256:x'). Tag-only references are refused."""
    name, _, digest = str(image).partition('@')
    if not DIGEST.fullmatch(digest):
        raise Unknown('image_not_pinned_by_digest')
    host, _, path = name.partition('/')
    path = path.rpartition(':')[0] if ':' in path.rpartition('/')[2] else path
    if '.' not in host or not path:
        raise Unknown('image_reference_unparsed')
    return host, path, digest


def google_host(host):
    """Only Google registries (and the Google storage hosts they redirect blobs to) may see the gcloud token: a
    revision pinned to any other registry would otherwise receive it (Luna PR#36 P1)."""
    host = host.lower().partition(':')[0]
    return host == 'gcr.io' or host.endswith(
        ('.gcr.io', '-docker.pkg.dev', '.googleapis.com', '.googleusercontent.com')
    )


class GoogleOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != 'https' or not google_host(target.hostname or ''):  # the token rides the redirect
            raise Unknown('registry_redirect_not_google')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Registry:
    """Registry v2 reader with a bearer token from the active (read-only) gcloud account; Google registries only."""

    def __init__(self, token=None, opener=None, base=None):
        self._token = token
        self._open = opener or urllib.request.build_opener(GoogleOnlyRedirects()).open
        # SERVING_HAS_REGISTRY_URL (file://DIR only) serves <DIR>/v2/<path>/<kind>/<ref> for the train harness.
        self._base = base if base is not None else os.environ.get('SERVING_HAS_REGISTRY_URL', '')
        if self._base and not self._base.startswith('file:'):
            raise Unknown('registry_override_must_be_file_url')

    def token(self):
        if self._token is None:
            self._token = '' if self._base else command([GCLOUD, 'auth', 'print-access-token']).strip()
        return self._token

    def get(self, host, path, kind, ref, accept=ACCEPT):
        if not self._base and not google_host(host):
            raise Unknown('registry_host_not_google')
        req = urllib.request.Request(
            f'{self._base or "https://" + host}/v2/{path}/{kind}/{ref}',
            headers={'Authorization': f'Bearer {self.token()}', 'Accept': accept},
        )
        try:
            with self._open(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise Unknown(f'registry_{kind}_read_failed') from exc

    def revision(self, image):
        host, path, digest = split_image(image)
        manifest = self.get(host, path, 'manifests', digest)
        if manifest.get('mediaType') in INDEX_TYPES or 'manifests' in manifest:
            amd = [
                m
                for m in manifest.get('manifests', [])
                if (m.get('platform') or {}).get('os') == 'linux'
                and (m.get('platform') or {}).get('architecture') == 'amd64'
            ]
            if len(amd) != 1:
                raise Unknown('image_index_ambiguous')
            manifest = self.get(host, path, 'manifests', amd[0]['digest'])
        config = (manifest.get('config') or {}).get('digest', '')
        if not DIGEST.fullmatch(config):
            raise Unknown('image_config_missing')
        labels = (self.get(host, path, 'blobs', config, accept='*/*').get('config') or {}).get('Labels') or {}
        source = labels.get(REVISION_LABEL, '')
        if SHA.fullmatch(source):
            return source, 'label'
        return self.tag_revision(host, path, digest), 'tag'

    def tag_revision(self, host, path, digest):
        """Images built outside gcp_backend.yml (train/deploy-prod builds, 11-02: backend-sync 07f97ca) carry no
        label, only commit tags. Returns them comma-joined; resolve_source() accepts several only when they are
        one source tree."""
        tags = (((self.get(host, path, 'tags', 'list').get('manifest') or {}).get(digest) or {}).get('tag')) or []
        hexes = sorted(t for t in tags if re.fullmatch(r'[0-9a-f]{7,40}', t))
        if not hexes:
            raise Unknown('image_revision_label_missing')
        return ','.join(hexes)


def stamp_source(service, revision_name, value):
    """Full source commit from the deploy workflow's release stamp, for services in RELEASE_STAMP_ENV only.

    desktop_backend_prod.yml admits an exact DEPLOY_SHA (ancestor-of-main, release-eligibility proof), checks it
    out, verifies checked_out == DEPLOY_SHA, stamps the mapped env with it and embeds the same sha12 in
    --revision-suffix; the candidate image tag is removed after deploy. Both surviving marks come from that one
    verified checkout, so the stamp is accepted only when the workflow-shaped revision name carries the same
    sha12. The commit-sha label is the dispatch head and is never read (SCA-3013/SCA-3485)."""
    if service not in RELEASE_STAMP_ENV:
        raise Unknown('release_stamp_unconfigured')
    match = re.search(WORKFLOW_REVISION_NAME, revision_name or '') if isinstance(revision_name, str) else None
    if match is None or not isinstance(value, str) or not SHA.fullmatch(value) or not value.startswith(match.group(1)):
        raise Unknown('release_stamp_unverified')
    return value


def resolve_source(repo, source):
    """Full commit for an image source. Several commit tags on one digest are accepted only when they share one tree
    and one of them descends from all the others (that one is returned); anything else is ambiguous."""
    commits = sorted({resolve(repo, ref) for ref in source.split(',')})
    if len(commits) == 1:
        return commits[0]
    if len({resolve_tree(repo, c) for c in commits}) != 1:
        raise Unknown('image_commit_tag_ambiguous')
    tips = [c for c in commits if all(is_ancestor(repo, o, c) for o in commits if o != c)]
    if len(tips) != 1:
        raise Unknown('image_commit_tag_ambiguous')
    return tips[0]


def resolve(repo, ref, fetch=True):
    """Full commit SHA for ref. A commit deployed minutes ago may not be fetched yet: one `git fetch origin` retry,
    then Unknown (missing or an ambiguous abbreviation)."""
    r = subprocess.run(
        [GIT, '-C', repo, 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}'], capture_output=True, text=True
    )
    if r.returncode or not SHA.fullmatch(r.stdout.strip()):
        if (
            fetch
            and subprocess.run([GIT, '-C', repo, 'fetch', '-q', 'origin'], capture_output=True, timeout=180).returncode
            == 0
        ):
            return resolve(repo, ref, fetch=False)
        raise Unknown('commit_not_in_local_repo')
    return r.stdout.strip()


def resolve_tree(repo, commit):
    r = subprocess.run(
        [GIT, '-C', repo, 'rev-parse', '--verify', '--quiet', f'{commit}^{{tree}}'], capture_output=True, text=True
    )
    if r.returncode:
        raise Unknown('tree_unresolved')
    return r.stdout.strip()


def image_source(revision, repo, registry=None, service=None):
    """Full source commit of a Cloud Run revision's application image (digest -> OCI label or commit tag).

    For RELEASE_STAMP_ENV services whose registry evidence was stripped after deploy, the workflow-stamped
    release validated against the revision name is the fallback (see stamp_source)."""
    app = app_container(revision)
    try:
        source, _kind = (registry or Registry()).revision(app.get('image', ''))
        return resolve_source(repo, source)
    except Unknown:
        if service in RELEASE_STAMP_ENV:
            env = {e.get('name'): e.get('value') for e in app.get('env', [])}
            return stamp_source(
                service, (revision.get('metadata') or {}).get('name'), env.get(RELEASE_STAMP_ENV[service])
            )
        raise


def is_ancestor(repo, sha, source):
    """True/False from git; Unknown when either object is missing locally."""
    sha, source = resolve(repo, sha), resolve(repo, source)
    r = subprocess.run([GIT, '-C', repo, 'merge-base', '--is-ancestor', sha, source], capture_output=True)
    if r.returncode not in (0, 1):
        raise Unknown('merge_base_failed')
    return r.returncode == 0


def app_container(revision):
    containers = revision['spec']['containers']
    if len(containers) == 1:
        return containers[0]
    # Sidecars (OTel collector) declare no port; the ingress container is the application.
    apps = [c for c in containers if c.get('ports')]
    if len(apps) != 1:
        raise Unknown('application_container_ambiguous')
    return apps[0]


def traffic_revisions(doc):
    """[(revisionName, percent)] for every traffic target with percent > 0, from status.traffic only."""
    out = {}
    for t in (doc.get('status') or {}).get('traffic') or []:
        pct = t.get('percent') or 0
        if pct <= 0:
            continue
        name = t.get('revisionName')
        if not name:
            raise Unknown('traffic_target_without_revision')
        out[name] = out.get(name, 0) + pct
    if not out or sum(out.values()) != 100:
        raise Unknown('traffic_not_100_percent')
    return sorted(out.items())


def read_cloud_run(service, project, region, describe=None):
    """[{revision, percent, image, commit_label, stamp}] for traffic-receiving revisions."""
    flags = ['--project', project, '--region', region, '--format=json']
    describe = describe or (lambda kind, name: json.loads(command([GCLOUD, 'run', kind, 'describe', name, *flags])))
    doc = describe('services', service)
    rows = []
    stamp_key = RELEASE_STAMP_ENV.get(service)
    for name, pct in traffic_revisions(doc):
        rev = describe('revisions', name)
        if (rev.get('metadata') or {}).get('name') != name:
            raise Unknown('revision_identity_mismatch')
        app = app_container(rev)
        stamp = (
            next((e.get('value') for e in app.get('env', []) if e.get('name') == stamp_key), '') if stamp_key else ''
        )
        rows.append(
            dict(
                revision=name,
                percent=pct,
                image=app.get('image', ''),
                commit_label=((rev.get('metadata') or {}).get('labels') or {}).get('commit-sha', ''),
                stamp=stamp,
            )
        )
    if describe('services', service).get('status', {}).get('traffic') != doc.get('status', {}).get('traffic'):
        raise Unknown('traffic_changed_during_read')
    return rows


def deployment_intent(deploy):
    """Selector, scale, and template of one Deployment. Status heartbeats are not a rollout."""
    meta = deploy.get('metadata') or {}
    spec = deploy.get('spec') or {}
    return (
        meta.get('name'),
        meta.get('uid'),
        meta.get('generation'),
        spec.get('replicas'),
        spec.get('selector'),
        spec.get('template'),
    )


def workload_deployments(workload, deployments):
    """A runtime family can have multiple pool/Spot Deployments with one app label."""
    from train_readback import Refused, workload_deployment

    selected = []
    for deploy in deployments['items']:
        try:
            selected.append(workload_deployment(workload, {'items': [deploy]}))
        except Refused:
            continue
    if not selected:
        raise Unknown('gke_workload_missing')
    return selected


def deployment_rows(deploy, pods):
    from train_readback import matches, pod_ready

    selector = deploy['spec']['selector']
    count = deploy['spec'].get('replicas', 1)
    if not selector or not isinstance(count, int) or count < 0:
        raise Unknown('gke_invalid_replicas')
    selected = [
        p
        for p in pods['items']
        if matches(selector, p['metadata'].get('labels', {}))
        and p.get('status', {}).get('phase') not in ('Succeeded', 'Failed')
    ]
    if len(selected) < count:
        raise Unknown('gke_missing_replicas')
    template = deploy['spec']['template']['spec']['containers']
    # Same application-first contract as train_readback.check_workload.
    app = template[0]['name']
    rows = []
    for pod in selected:
        if not pod_ready(pod) and not pod['metadata'].get('deletionTimestamp'):
            raise Unknown('gke_pod_not_ready')
        containers = [c for c in pod['spec']['containers'] if c['name'] == app]
        statuses = [c for c in pod.get('status', {}).get('containerStatuses', []) if c['name'] == app]
        if len(containers) != 1 or len(statuses) != 1 or not statuses[0].get('ready'):
            raise Unknown('gke_application_unknown')
        image = containers[0]['image']
        running = statuses[0].get('imageID', '').removeprefix('docker-pullable://')
        digest = running.rpartition('@')[2] if '@' in running else running
        if not DIGEST.fullmatch(digest):
            raise Unknown('gke_running_digest_unknown')
        repository = image.split('@', 1)[0]
        if ':' in repository.rsplit('/', 1)[-1]:
            repository = repository.rsplit(':', 1)[0]
        if '@' in image and image.rpartition('@')[2] != digest:
            raise Unknown('gke_running_digest_mismatch')
        rows.append(dict(revision=pod['metadata']['name'], image=repository + '@' + digest, commit_label=''))
    return rows


def read_gke(workload, reader):
    """Every active replica across a family's Deployments, including draining pods.

    A scaled-to-zero sibling contributes no proof. At least one running pod is
    required, and every positive replica count must be accounted for.
    """
    deployments, pods = (reader.kube(k) for k in ('deployments', 'pods'))
    selected = workload_deployments(workload, deployments)
    rows = [row for deploy in selected for row in deployment_rows(deploy, pods)]
    if not rows:
        raise Unknown('gke_no_pods')
    if len({r['revision'] for r in rows}) != len(rows):
        raise Unknown('gke_overlapping_selectors')
    for row in rows:
        row['percent'] = 100 / len(rows)
    # Compare every member's intent; ignore unrelated workloads/status heartbeats.
    later = workload_deployments(workload, reader.kube('deployments'))
    identity = lambda items: {d['metadata']['name']: deployment_intent(d) for d in items}
    if identity(later) != identity(selected):
        raise Unknown('gke_deployment_changed_during_read')
    return rows


def _observe_gke(workload, repo, registry=None, reader=None):
    """Read-only identity rows for callers such as the standing drift alarm."""
    if reader is None:
        from train_readback import Reader, CONTEXT

        with tempfile.TemporaryDirectory(prefix='serving-has-') as directory:
            reader = Reader(str(Path(directory) / 'config'), CONTEXT, time.monotonic() + 240)
            reader.prepare_kube()
            # Use precisely the reader's ro-prod identity for registry reads too.
            registry = registry or Registry(token=reader.run(['gcloud', 'auth', 'print-access-token']).strip())
            return _observe_gke(workload, repo, registry, reader)
    rows = read_gke(workload, reader)
    images = {}
    for row in rows:
        if row['image'] not in images:
            source, kind = (registry or Registry()).revision(row['image'])
            images[row['image']] = (resolve_source(repo, source), kind)
        source, kind = images[row['image']]
        row.update(source=source, source_kind=kind)
    return rows


def observe_gke(workload, repo, registry=None, reader=None):
    try:
        return _observe_gke(workload, repo, registry, reader)
    except Unknown:
        raise
    except Exception as error:
        # train_readback.Refused and transport errors carry no serving proof.
        raise Unknown('gke_read_failed:' + type(error).__name__) from None


def judge_sources(sha, rows, repo):
    """Same ancestry rule for already observed runtime sources; empty is unknown."""
    if not rows:
        raise Unknown('runtime_no_revisions')
    with_pct, unknown = 0, False
    for row in rows:
        try:
            if not row.get('source'):
                raise Unknown('runtime_source_unknown')
            row['has'] = 'yes' if is_ancestor(repo, sha, row['source']) else 'no'
        except Unknown:
            row['has'] = 'unknown'
            unknown = True
        if row['has'] == 'yes':
            with_pct += row.get('percent', 100 / len(rows))
    verdict = (
        'unknown' if unknown else 'yes' if all(r['has'] == 'yes' for r in rows) else 'partial' if with_pct else 'no'
    )
    return verdict, with_pct


def judge(sha, rows, repo, registry, service=None):
    """Annotate rows with source/has; return (verdict, percent_with)."""
    with_pct, unknown = 0, False
    for row in rows:
        row['source'], row['source_kind'], row['has'] = None, None, 'unknown'
        try:
            try:
                source, row['source_kind'] = registry.revision(row['image'])
                row['source'] = resolve_source(repo, source)
            except Unknown:
                # A RELEASE_STAMP_ENV service whose registry evidence was stripped after deploy falls
                # back to its workflow-stamped release; every other service stays unknown (fail closed).
                row['source'] = stamp_source(service, row.get('revision'), row.get('stamp'))
                row['source_kind'] = 'stamp'
            row['has'] = 'yes' if is_ancestor(repo, sha, row['source']) else 'no'
        except Unknown as exc:
            row['why'] = str(exc)
            unknown = True
            continue
        if row['has'] == 'yes':
            with_pct += row['percent']
    if unknown:
        return 'unknown', with_pct
    return ('yes' if all(r['has'] == 'yes' for r in rows) and rows else 'partial' if with_pct else 'no'), with_pct


def default_repo():
    """Use the explicit repo or the product checkout containing this script."""
    override = os.environ.get('SERVING_HAS_REPO')
    if override:
        return override
    root = os.environ.get('OMI_WORKSPACE_ROOT')
    if root and (Path(root) / 'upstream-keep-clean').is_dir():
        return str(Path(root) / 'upstream-keep-clean')
    return str(Path(__file__).resolve().parents[2])


def main(argv=None, registry=None, describe=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('sha', nargs='?')
    p.add_argument('service', nargs='?')
    p.add_argument('--gke', action='store_true', help='SERVICE is a GKE Deployment workload')
    p.add_argument('--image-revision', metavar='IMAGE')
    p.add_argument('--repo', default=default_repo())
    p.add_argument('--project', default='based-hardware')
    p.add_argument('--region', default='us-central1')
    p.add_argument('--json', action='store_true')
    o = p.parse_args(argv)
    if o.image_revision:
        registry = registry or Registry()
        try:
            source, kind = registry.revision(o.image_revision)
            print(f'{source} {kind}')
            return 0
        except Unknown as exc:
            print(f'UNKNOWN {exc}', file=sys.stderr)
            return 2
    if not (o.sha and o.service):
        p.error('SHA and SERVICE are required')
    try:
        sha = resolve(o.repo, o.sha)
        rows = (
            observe_gke(o.service, o.repo, registry)
            if o.gke
            else read_cloud_run(o.service, o.project, o.region, describe)
        )
        if o.gke:
            verdict, with_pct = judge_sources(sha, rows, o.repo)
        else:
            verdict, with_pct = judge(sha, rows, o.repo, registry or Registry(), o.service)
    except (Unknown, KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'SERVING_HAS unknown service={o.service} sha={str(o.sha)[:12]} why={type(exc).__name__}:{str(exc)[:60]}')
        return 2
    coverage = (
        dict(replicas_with=sum(r['has'] == 'yes' for r in rows), replicas_total=len(rows))
        if o.gke
        else dict(traffic_with=with_pct)
    )
    if o.json:
        print(
            json.dumps(
                dict(
                    service=o.service,
                    sha=sha,
                    verdict=verdict,
                    **coverage,
                    revisions=[
                        {
                            k: r.get(k)
                            for k in ('revision', 'percent', 'source', 'source_kind', 'has', 'commit_label', 'why')
                        }
                        for r in rows
                    ],
                ),
                sort_keys=True,
            )
        )
    else:
        for r in rows:
            digest = r['image'].rpartition('@')[2][7:19]
            print(
                f"REVISION {r['revision']} percent={r['percent']} digest={digest} "
                f"source={(r['source'] or 'unknown')[:12]} via={r.get('source_kind') or '-'} has={r['has']}"
                + (f" why={r['why']}" if r.get('why') else '')
            )
        detail = ' '.join(f'{k}={v}' for k, v in coverage.items())
        print(f'SERVING_HAS {verdict} service={o.service} sha={sha[:12]} {detail}')
    return {'yes': 0, 'no': 1, 'partial': 1}.get(verdict, 2)


if __name__ == '__main__':
    sys.exit(main())
