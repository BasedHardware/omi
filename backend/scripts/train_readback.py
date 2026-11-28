#!/usr/bin/env python3
"""Read-only train completion gate. --plan is entirely offline; never deploys."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from serving_revision import serving_revision

PROJECT = 'based-hardware'
REGION = 'us-central1'
NAMESPACE = 'prod-omi-backend'
CONTEXT = 'gke_based-hardware_us-central1_prod-omi-gke'
STEP = 30
WINDOW = 300
SCRAPE_MAX_AGE_SECONDS = 120
NAME = re.compile(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')


class Refused(Exception):
    pass


def require(ok, token):
    if not ok:
        raise Refused(token)


def image_matches(image, sha, digest=None):
    if digest:
        return '@' in image and image.rsplit('@', 1)[-1] == digest
    return image.endswith(':' + sha[:7])


def check_revision(service, doc, revision, sha, digest=None):
    token = 'no_single_serving_revision:' + service
    try:
        name = serving_revision(doc)  # status.traffic only, including named backfill pins
    except ValueError:
        raise Refused(token) from None
    status = revision.get('status', {})
    require(
        revision.get('metadata', {}).get('name') == name
        and any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in status.get('conditions', [])),
        token,
    )
    containers = revision.get('spec', {}).get('containers', [])
    # The deploy contract places the application first, followed by optional collectors.
    require(bool(containers), 'sha_mismatch:' + service)
    image = containers[0].get('image', '')
    if digest:
        observed = status.get('imageDigest', '')
        if not observed:
            metadata = revision['metadata']
            conditions = {c.get('type'): c.get('status') for c in status.get('conditions', [])}
            require(
                metadata.get('generation') is not None
                and str(status.get('observedGeneration')) == str(metadata['generation'])
                and all(conditions.get(c) == 'True' for c in ('Ready', 'ContainerHealthy', 'ResourcesAvailable'))
                and metadata.get('annotations', {}).get('run.googleapis.com/health-check-disabled') != 'true',
                token,
            )
            observed = image  # Ready immutable multi-container revision, as in staging_image.py
        require(observed.rsplit('@', 1)[-1] == digest, 'sha_mismatch:' + service)
    else:
        require(image_matches(image, sha), 'sha_mismatch:' + service)


def matches(selector, labels):
    """Kubernetes LabelSelector (matchLabels and all four set operators)."""
    if any(labels.get(k) != v for k, v in selector.get('matchLabels', {}).items()):
        return False
    for expr in selector.get('matchExpressions', []):
        key, op, values = expr['key'], expr['operator'], expr.get('values', [])
        if op == 'In':
            ok = key in labels and labels[key] in values
        elif op == 'NotIn':
            ok = key not in labels or labels[key] not in values
        elif op == 'Exists':
            ok = key in labels
        elif op == 'DoesNotExist':
            ok = key not in labels
        else:
            raise ValueError('unsupported_selector')
        if not ok:
            return False
    return True


def workload_deployment(workload, deployments):
    token = 'no_pods:' + workload
    candidates = [
        d
        for d in deployments['items']
        if d['metadata']['name'] == workload
        or d['metadata'].get('labels', {}).get('app.kubernetes.io/name') == workload
        or d['spec']['template']['metadata'].get('labels', {}).get('app.kubernetes.io/name') == workload
    ]
    require(len(candidates) == 1, token)
    return candidates[0]


def check_workload(workload, deployments, pods, sha, digest=None):
    token = 'no_pods:' + workload
    deploy = workload_deployment(workload, deployments)
    spec, status = deploy['spec'], deploy.get('status', {})
    count = spec.get('replicas', 1)
    require(
        isinstance(count, int)
        and count > 0
        and deploy['metadata'].get('generation') is not None
        and status.get('observedGeneration', 0) >= deploy['metadata']['generation']
        and all(
            status.get(k, 0) == count for k in ('replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas')
        )
        and any(
            c.get('type') == 'Progressing' and c.get('status') == 'True' and c.get('reason') == 'NewReplicaSetAvailable'
            for c in status.get('conditions', [])
        ),
        token,
    )
    template = spec['template']['spec']['containers']
    require(bool(template) and image_matches(template[0].get('image', ''), sha, digest), token)
    selector = spec['selector']
    require(bool(selector), token)
    selected = [p for p in pods['items'] if matches(selector, p['metadata'].get('labels', {}))]
    matching = [
        p
        for p in selected
        if p.get('spec', {}).get('containers')
        and image_matches(p['spec']['containers'][0].get('image', ''), sha, digest)
    ]
    # Digest pins must cover every selected pod; tags keep the ready SHA-pod gate.
    require(any(pod_ready(p) for p in matching) and (not digest or len(matching) == len(selected)), token)
    return deploy['spec']['template']['metadata'].get('labels', {}), selected


def pod_ready(pod):
    return (
        not pod['metadata'].get('deletionTimestamp')
        and pod.get('status', {}).get('phase') == 'Running'
        and any(
            c.get('type') == 'Ready' and c.get('status') == 'True' for c in pod.get('status', {}).get('conditions', [])
        )
    )


def expected_targets(monitor, pods):
    """All ready pods selected by this monitor, including other workloads."""
    targets = []
    for pod in pods['items']:
        if not pod_ready(pod) or not matches(monitor['spec']['selector'], pod['metadata'].get('labels', {})):
            continue
        for endpoint in monitor['spec']['endpoints']:
            port = str(endpoint['port'])
            ports = {port}
            for container in pod.get('spec', {}).get('containers', []):
                for declared in container.get('ports', []):
                    if declared.get('name') == port:
                        ports.add(str(declared['containerPort']))
            targets.append((pod['metadata']['name'], port, ports))
    return targets


def series_labels(row):
    # PromQL functions can retain/drop __name__ differently; it is not a target label.
    return tuple(sorted((k, v) for k, v in row.get('metric', {}).items() if k != '__name__'))


def check_targets(monitor, series, expected):
    # Deduplicate identical label sets: the same target cannot cover two endpoints.
    metrics = {series_labels(row) for row in series}
    candidates = []
    for pod, endpoint, ports in expected:
        candidates.append(
            [
                i
                for i, labels in enumerate(metrics)
                if (m := dict(labels)).get('pod') == pod
                and ('endpoint' not in m or m['endpoint'] == endpoint)
                and ('port' not in m or m['port'] in ports)
            ]
        )
    # One-to-one matching also handles exporters without endpoint/port labels;
    # they must still return a distinct series for every endpoint on each pod.
    assigned = {}

    def assign(target, seen):
        for row in candidates[target]:
            if row in seen:
                continue
            seen.add(row)
            if row not in assigned or assign(assigned[row], seen):
                assigned[row] = target
                return True
        return False

    missing = sum(not assign(target, set()) for target in range(len(expected)))
    require(missing == 0, f'scrape_targets_missing:{monitor}:{missing}')


def scrape_series(monitor, payload, result_type):
    require(
        payload.get('status') == 'success' and payload.get('data', {}).get('resultType') == result_type,
        'scrape_up:' + monitor,
    )
    series = payload['data'].get('result')
    require(isinstance(series, list) and bool(series), 'scrape_targets_zero:' + monitor)
    return series


def check_scrape(monitor, payload, start, end, expected, now):
    zero, bad, stale = ('scrape_targets_zero:' + monitor, 'scrape_up:' + monitor, 'scrape_stale:' + monitor)
    require(bool(expected), zero)
    timestamps = scrape_series(monitor, payload['timestamps'], 'matrix')
    minimum = scrape_series(monitor, payload['minimum'], 'vector')
    for series in (timestamps, minimum):
        check_targets(monitor, series, expected)
    # Both queries must describe the same target identities, not disjoint subsets.
    require({series_labels(row) for row in timestamps} == {series_labels(row) for row in minimum}, bad)
    for row in timestamps:
        values = row.get('values', [])
        require(bool(values), zero)
        try:
            stamps = [float(x[0]) for x in values]
            sources = [float(x[1]) for x in values]
            good = (
                len(stamps) == WINDOW // STEP + 1
                and all(math.isfinite(t) and abs(t - (start + i * STEP)) < 1 for i, t in enumerate(stamps))
                and abs(stamps[-1] - end) < 1
            )
            fresh = all(
                math.isfinite(source) and 0 <= stamp - source < SCRAPE_MAX_AGE_SECONDS
                for stamp, source in zip(stamps, sources)
            ) and (0 <= now - sources[-1] < SCRAPE_MAX_AGE_SECONDS)
        except (ValueError, TypeError, IndexError, OverflowError):
            good = fresh = False
        require(good, bad)
        require(fresh, stale)
    for row in minimum:
        try:
            stamp, value = map(float, row['value'])
            good = math.isfinite(stamp) and abs(stamp - end) < 1 and value == 1
        except (KeyError, ValueError, TypeError, OverflowError):
            good = False
        require(good, bad)


class Reader:
    """All child reads source ro-prod and use our private, disposable config."""

    def __init__(self, kubeconfig, context, deadline):
        self.kubeconfig, self.context, self.deadline = kubeconfig, context, deadline

    def remaining(self):
        left = self.deadline - time.monotonic()
        require(left > 0, 'read_failed:deadline')
        return min(60, left)

    def run(self, argv):
        # Never inherit the caller's operator identity or default kube context.
        script = (
            'source "$HOME/.local/bin/gcp-agent-env.sh" ro-prod >/dev/null 2>&1 || exit 1\n'
            '[ "${GCP_AGENT_TIER:-}" = ro-prod ] || exit 1\n'
            'export KUBECONFIG="$1"; shift\nexec "$@"'
        )
        timeout = self.remaining()  # refuse before spawning after the deadline
        with subprocess.Popen(
            ['bash', '-c', script, 'train-readback', self.kubeconfig, *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        ) as process:
            try:
                out, _ = process.communicate(timeout=timeout)
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
            require(process.returncode == 0, 'read_failed:transport')
        return out

    def cloud(self, kind, name):
        return json.loads(
            self.run(
                ['gcloud', 'run', kind, 'describe', name, '--project=' + PROJECT, '--region=' + REGION, '--format=json']
            )
        )

    def kube(self, kind):
        return json.loads(
            self.run(
                [
                    'kubectl',
                    '--context',
                    self.context,
                    '--request-timeout=60s',
                    '-n',
                    NAMESPACE,
                    'get',
                    kind,
                    '-o',
                    'json',
                ]
            )
        )

    def prepare_kube(self):
        self.run(
            [
                'gcloud',
                'container',
                'clusters',
                'get-credentials',
                'prod-omi-gke',
                '--region=' + REGION,
                '--project=' + PROJECT,
            ]
        )

    def digest(self, image, sha):
        repository = image.split('@', 1)[0]
        if ':' in repository.rsplit('/', 1)[-1]:
            repository = repository.rsplit(':', 1)[0]
        tagged = repository + ':' + sha[:7]
        command = (
            ['gcloud', 'artifacts', 'docker', 'images'] if '.pkg.dev/' in tagged else ['gcloud', 'container', 'images']
        )
        value = self.run(
            [*command, 'describe', tagged, '--project=' + PROJECT, '--format=value(image_summary.digest)']
        ).strip()
        require(bool(DIGEST.fullmatch(value)), 'read_failed:registry')
        return value

    def metric(self, monitor, start, end):
        token = self.run(['gcloud', 'auth', 'print-access-token']).strip()
        require(bool(token), 'read_failed:metrics')
        query = 'up{namespace=' + json.dumps(NAMESPACE) + ',cluster="prod-omi-gke",job=' + json.dumps(monitor) + '}'
        base = f'https://monitoring.googleapis.com/v1/projects/{PROJECT}/location/global/' 'prometheus/api/v1/'
        payload = {}
        for key, path, params in (
            ('timestamps', 'query_range', dict(query=f'timestamp({query})', start=start, end=end, step=STEP)),
            ('minimum', 'query', dict(query=f'min_over_time({query}[5m])', time=end)),
        ):
            request = urllib.request.Request(
                base + path + '?' + urllib.parse.urlencode(params), headers={'Authorization': 'Bearer ' + token}
            )
            with urllib.request.urlopen(request, timeout=self.remaining()) as response:
                payload[key] = json.load(response)
        return payload


def attempt_start(args):
    """One durable revocation per command, before any observation or retry."""
    if not args.cloud_run or not os.environ.get('OMI_RELEASE_ISSUE') or not os.environ.get('OMI_TRAIN_NAME'):
        return None
    stamp = datetime.now(timezone.utc).isoformat()
    # Preserve the wire fallback even when the telemetry import/storage fails.
    print(
        'DEPLOY_ATTEMPT_HISTORY_V1\n```json\n'
        + json.dumps(dict(complete=False, observed_at=stamp, events=[]))
        + '\n```'
    )
    try:
        import deploy_attempt_receipt as attempts

        issue, train = attempts.issue_key(os.environ['OMI_RELEASE_ISSUE']), os.environ['OMI_TRAIN_NAME']
        if not attempts.contract.TRAIN.fullmatch(train):
            raise ValueError('invalid_train_identity')
        path = attempts.journal_path(issue)
        attempts.invalidate(path, issue, stamp)
        return attempts, issue, train, path
    except Exception:
        print('DEPLOY_ATTEMPT_RECEIPT_UNKNOWN')
        return None


def observe(args, reader):
    for service in args.cloud_run:
        try:
            doc = reader.cloud('services', service)
            try:
                name = serving_revision(doc)
            except ValueError:
                raise Refused('no_single_serving_revision:' + service) from None
            revision = reader.cloud('revisions', name)
            # Telemetry shares the train receipt storage. Missing provenance is
            # explicitly unknown; it never changes this existing serving gate.
            context = getattr(args, 'attempt_context', None)
            if context is not None:
                try:
                    attempts, issue, train, path = context
                    stamp = datetime.now(timezone.utc).isoformat()
                    source = attempts.serving_has.image_source(revision, attempts.serving_has.default_repo())
                    row = attempts.capture(revision, service, train, issue, source, args.sha, stamp)
                    attempts.update(path, row, observed_at=stamp)
                except Exception:
                    print('DEPLOY_ATTEMPT_RECEIPT_UNKNOWN')
            digest = args.image_digest.get(service)
            image = revision.get('spec', {}).get('containers', [{}])[0].get('image', '')
            if not image_matches(image, args.sha, digest) and '@sha256:' in image and not digest:
                digest = reader.digest(image, args.sha)
            check_revision(service, doc, revision, args.sha, digest)
        except Refused as exc:
            if not str(exc).startswith('read_failed:'):
                raise
            raise Refused('read_failed:' + service) from None
        except Exception:
            raise Refused('read_failed:' + service) from None
    if not args.gke:
        return
    try:
        deployments, pods, monitors = (reader.kube(kind) for kind in ('deployments', 'pods', 'podmonitorings'))
    except Exception:
        raise Refused('read_failed:gke') from None
    end = int(time.time())
    start = end - WINDOW
    checked = set()
    for workload in args.gke:
        try:
            digest = args.image_digest.get(workload)
            deploy = workload_deployment(workload, deployments)
            containers = deploy['spec']['template']['spec']['containers']
            image = containers[0].get('image', '') if containers else ''
            if '@sha256:' in image and not digest:
                try:
                    digest = reader.digest(image, args.sha)
                except Exception:
                    raise Refused('read_failed:' + workload) from None
            labels, selected = check_workload(workload, deployments, pods, args.sha, digest)
            matching = [
                m
                for m in monitors['items']
                if matches(m['spec']['selector'], labels)
                or any(matches(m['spec']['selector'], p['metadata'].get('labels', {})) for p in selected)
            ]
            require(bool(matching), 'scrape_targets_zero:' + workload)
            for monitor in matching:
                name = monitor['metadata']['name']
                require(bool(NAME.fullmatch(name)), 'read_failed:' + workload)
                if name not in checked:
                    try:
                        payload = reader.metric(name, start, end)
                    except Exception:
                        raise Refused('read_failed:' + name) from None
                    check_scrape(name, payload, start, end, expected_targets(monitor, pods), time.time())
                    checked.add(name)
        except Refused:
            raise
        except Exception:
            raise Refused('read_failed:' + workload) from None


def settle(args, reader, deadline):
    if not hasattr(args, 'attempt_context'):
        args.attempt_context = attempt_start(args)
    token = 'read_failed:deadline'
    repeated_reads = 0
    while time.monotonic() < deadline:
        try:
            observe(args, reader)
            if time.monotonic() < deadline:
                return
        except Refused as exc:
            repeated_reads = repeated_reads + 1 if token == str(exc) else 1
            token = str(exc)
            if token.startswith('read_failed:') and repeated_reads >= 3:
                raise
        left = deadline - time.monotonic()
        if left > 0:
            time.sleep(min(args.poll_seconds, left))
    raise Refused(token)


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha', required=True, help='full source SHA')
    parser.add_argument('--cloud-run', default='', help='comma-separated touched services')
    parser.add_argument('--gke', default='', help='comma-separated touched Deployment workloads')
    parser.add_argument(
        '--image-digest',
        action='append',
        default=[],
        metavar='SERVICE=sha256:HEX',
        help='expected Cloud Run or workload digest; otherwise resolve the sha7 tag when needed',
    )
    parser.add_argument('--context', default=CONTEXT, help='explicit production kubectl context')
    parser.add_argument('--settle-seconds', type=float, default=900)
    parser.add_argument('--poll-seconds', type=float, default=30)
    parser.add_argument('--plan', action='store_true', help='print expected matrix without any reads')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[0-9a-f]{40}', args.sha):
        parser.error('--sha must be a full lowercase 40-hex SHA')
    for field in ('cloud_run', 'gke'):
        raw = getattr(args, field)
        names = raw.split(',') if raw else []
        if any(not NAME.fullmatch(n) for n in names) or len(names) != len(set(names)):
            parser.error('invalid or duplicate surface name')
        setattr(args, field, names)
    if not args.cloud_run and not args.gke:
        parser.error('at least one touched surface is required')
    digests = {}
    for item in args.image_digest:
        service, sep, digest = item.partition('=')
        if not sep or service not in args.cloud_run + args.gke or service in digests or not DIGEST.fullmatch(digest):
            parser.error('invalid or duplicate --image-digest')
        digests[service] = digest
    args.image_digest = digests
    if (
        not args.context.strip()
        or any(not math.isfinite(n) or n <= 0 for n in (args.settle_seconds, args.poll_seconds))
        or args.settle_seconds > 900
    ):
        parser.error('context required; positive finite timers and settle <=900 seconds required')
    return args


def main(argv=None):
    args = arguments(argv)
    if args.plan:
        print('SURFACE TARGET EXPECTED CHECKS')
        for service in args.cloud_run:
            print('cloud-run', service, args.image_digest.get(service, args.sha[:7]), 'single-serving,ready,image')
        for workload in args.gke:
            print(
                'gke',
                workload,
                args.image_digest.get(workload, args.sha[:7]),
                f'ready-pod,rollout-complete,matching-PodMonitorings:all-targets,up=1/5m,source-age<{SCRAPE_MAX_AGE_SECONDS}s',
            )
        return 0
    deadline = time.monotonic() + args.settle_seconds
    args.attempt_context = attempt_start(args)
    try:
        with tempfile.TemporaryDirectory(prefix='train-readback-') as directory:
            reader = Reader(str(Path(directory) / 'config'), args.context, deadline)
            if args.gke:
                try:
                    reader.prepare_kube()
                except Exception:
                    raise Refused('read_failed:kube_credentials') from None
            settle(args, reader, deadline)
    except Exception as exc:
        token = str(exc) if isinstance(exc, Refused) else 'read_failed:transport'
        print('TRAIN_READBACK FAIL ' + token)
        return 7
    print('TRAIN_READBACK PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
