"""Operator-owned shape canary watcher. Dry-run by default; no workload deletion.

Only --apply renews/zeros the routing ConfigMap. An expired lease also routes
baseline when the watcher/owner disappears. Stdout contains aggregates only.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request

NAMESPACE = 'prod-omi-backend'
DEPLOYMENT = 'prod-omi-parakeet-g24'
CONFIGMAP = 'parakeet-shape-route'
CANDIDATE = 'http://prod-omi-parakeet-g24.prod-omi-backend.svc.cluster.local:8080'
WINDOW = 900


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Cluster:
    def __init__(self, context):
        if not os.getenv('KUBECONFIG') or not context:
            raise ValueError('fresh KUBECONFIG and explicit context required')
        self.context = context
        self.last_route_data = None

    def call(self, *args, payload=None):
        result = subprocess.run(
            ['kubectl', '--context', self.context, '--namespace', NAMESPACE, '--request-timeout=20s', *args],
            input=json.dumps(payload) if payload is not None else None,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        if result.returncode:
            raise RuntimeError('kubectl_failed')  # Never echo stderr or workload payloads.
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def identity(self, revision):
        candidate = self.call('get', 'pods', '-l', 'app.kubernetes.io/instance=prod-omi-parakeet-g24', '-o', 'json')[
            'items'
        ]
        baseline = self.call('get', 'pods', '-l', 'app.kubernetes.io/instance=prod-omi-parakeet', '-o', 'json')['items']
        if len(candidate) != 1 or not baseline:
            raise ValueError('candidate_one_pod_and_warm_baseline_required')
        pod = candidate[0]
        status = pod['status']['containerStatuses'][0]
        if not status['ready'] or status['restartCount']:
            raise ValueError('candidate_not_ready_or_restarted')
        node = self.call('get', 'node', pod['spec']['nodeName'], '-o', 'json')
        labels = node['metadata']['labels']
        if (
            labels.get('node.kubernetes.io/instance-type') != 'g2-standard-4'
            or labels.get('cloud.google.com/gke-nodepool') != 'parakeet-g24-canary'
            or labels.get('cloud.google.com/gke-gpu-sharing-strategy')
            or str(node['status']['allocatable'].get('nvidia.com/gpu')) != '1'
            or not any(
                t.get('key') == 'omi.ai/parakeet-shape-canary'
                and t.get('value') == 'g24'
                and t.get('effect') == 'NoSchedule'
                for t in node['spec'].get('taints', [])
            )
        ):
            raise ValueError('candidate_shape_or_isolation_mismatch')
        container = pod['spec']['containers'][0]
        if container['resources']['limits']['memory'] != '12Gi':
            raise ValueError('candidate_memory_limit_mismatch')
        config = lambda c: {k: c.get(k) for k in ('env', 'envFrom', 'command', 'args')}
        for control in baseline:
            states = control['status'].get('containerStatuses', [])
            if not states or not states[0]['ready'] or states[0]['imageID'] != status['imageID']:
                raise ValueError('baseline_image_or_readiness_mismatch')
            if config(control['spec']['containers'][0]) != config(container):
                raise ValueError('baseline_model_config_mismatch')
        listeners = self.call('get', 'pods', '-l', 'app.kubernetes.io/name=backend-listen', '-o', 'json')['items']
        listener_configs = set()
        if not listeners:
            raise ValueError('listeners_required')
        for listener in listeners:
            states = listener['status'].get('containerStatuses', [])
            if not states or not all(s['ready'] for s in states):
                raise ValueError('listener_not_ready')
            serving = listener['spec']['containers'][0]
            if not any(
                e.get('name') == 'PARAKEET_SHAPE_CANARY_FILE' and e.get('value') == '/var/run/parakeet-shape/route.json'
                for e in serving.get('env', [])
            ):
                raise ValueError('listener_route_mount_required')
            listener_configs.add(digest({'image': states[0]['imageID'], 'config': config(serving)}))
        if len(listener_configs) != 1:
            raise ValueError('listener_rollout_incomplete')
        return digest(
            {
                'pod': pod['metadata']['uid'],
                'image': status['imageID'],
                'spec': pod['spec'],
                'node': labels,
                'revision': revision,
                'listeners': sorted(listener_configs),
            }
        )

    def route(self, identity, percent):
        current = self.call('get', 'configmap', CONFIGMAP, '-o', 'json')
        uninterrupted = self.last_route_data is None or current.get('data') == self.last_route_data
        # A manual kill or Helm reset must never be overwritten by a later
        # renewal. A changed writer state can only be recovered by a new run.
        if not uninterrupted:
            percent = 0
        # Resource-version CAS: a concurrent operator kill/identity change wins.
        current['data'] = {
            'route.json': json.dumps(
                {'identity': identity, 'url': CANDIDATE, 'percent': percent, 'expires': time.time() + 300}
            )
        }
        self.call('replace', '-f', '-', '-o', 'json', payload=current)
        self.last_route_data = current['data']
        return uninterrupted


def queries():
    q = {}
    for arm in ('control', 'canary'):
        sel = '{job="backend-listen-metrics",arm="' + arm + '"}'
        for metric, short in (('omi_stt_shape_first_text_seconds', 'first'), ('omi_stt_shape_post_seconds', 'post')):
            q[f'{arm}_{short}_count'] = f'sum(increase({metric}_count{sel}[15m]))'
            q[f'{arm}_{short}_p95'] = f'histogram_quantile(0.95,sum by(le)(rate({metric}_bucket{sel}[15m])))'
            q[f'{arm}_{short}_stale'] = f'max(time()-timestamp({metric}_count{sel}))'
        q[f'{arm}_bad'] = (
            'sum(increase(omi_stt_shape_posts_total{job="backend-listen-metrics",arm="'
            + arm
            + '",outcome!="success"}[15m]))'
        )
    gpu = '{namespace="prod-omi-backend",pod=~"prod-omi-parakeet-g24-.*",container="parakeet"}'
    pod = '{namespace="prod-omi-backend",pod=~"prod-omi-parakeet-g24-.*"}'
    q.update(
        {
            'gpu_count': f'count(max by(UUID)(DCGM_FI_DEV_GPU_UTIL{gpu}))',
            'gpu_stale': f'max(time()-timestamp(DCGM_FI_DEV_GPU_UTIL{gpu}))',
            'gpu_nonzero': f'max(max_over_time(DCGM_FI_DEV_GPU_UTIL{gpu}[15m]))',
            'gpu_samples': f'min(count_over_time(DCGM_FI_DEV_GPU_UTIL{gpu}[15m]))',
            'gpu_oom': f'sum(increase(parakeet_gpu_oom_total{pod}[15m]))',
            'gpu_fatal': f'sum(increase(parakeet_gpu_fatal_errors_total{pod}[15m]))',
            'gpu_error_stale': f'max(time()-timestamp(parakeet_gpu_oom_total{pod}))',
            'gpu_fatal_stale': f'max(time()-timestamp(parakeet_gpu_fatal_errors_total{pod}))',
            'restarts': f'sum(increase(kube_pod_container_status_restarts_total{pod}[15m]))',
            'ready': f'min(kube_pod_container_status_ready{pod})',
            'ready_stale': f'max(time()-timestamp(kube_pod_container_status_ready{pod}))',
            'queue': f'max(parakeet_batch_lane_oldest_pending_seconds{{namespace="prod-omi-backend",pod=~"prod-omi-parakeet-g24-.*",lane="live"}})',
            'queue_stale': f'max(time()-timestamp(parakeet_batch_lane_oldest_pending_seconds{{namespace="prod-omi-backend",pod=~"prod-omi-parakeet-g24-.*",lane="live"}}))',
            'throttle': f'max(rate(container_cpu_cfs_throttled_periods_total{gpu}[15m])/rate(container_cpu_cfs_periods_total{gpu}[15m]))',
            'listeners_up': 'min(up{job="backend-listen-metrics"})',
            'listener_coverage': 'count(up{job="backend-listen-metrics"}) / sum(kube_deployment_status_replicas_available{namespace="prod-omi-backend",deployment=~"prod-omi-backend-listen(-.*)?"})',
        }
    )
    return q


def collect(base):
    values = {}
    for key, query in queries().items():
        url = base.rstrip('/') + '/api/v1/query?' + urllib.parse.urlencode({'query': query})
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.load(response)
        result = payload.get('data', {}).get('result', [])
        if payload.get('status') != 'success' or len(result) != 1:
            values[key] = None
        else:
            stamp, value = result[0]['value']
            number = float(value)
            values[key] = number if math.isfinite(number) and time.time() - float(stamp) <= 60 else None
    return values


def evaluate(values, age):
    """Safety thresholds are aborts; acceptance requires the separate strict test."""
    p95 = {f'{a}_{m}_p95' for a in ('control', 'canary') for m in ('first', 'post')}
    # An initialized histogram with no arrivals has NaN p95. Only warmup may
    # tolerate that; missing series/freshness still block immediately.
    missing = [k for k in queries() if values.get(k) is None and k not in p95]
    if missing or values.get('listeners_up') != 1 or values.get('listener_coverage') != 1:
        return 'HOLD', 'missing_or_incomplete_metrics'
    if any(values[k] > 60 for k in values if k.endswith('_stale')):
        return 'HOLD', 'stale_metrics'
    if values['gpu_count'] != 1 or values['ready'] != 1 or values['restarts'] > 0:
        return 'ABORT', 'gpu_identity_readiness_or_restart'
    if values['queue'] >= 0.75:
        return 'ABORT', 'queue_pressure'
    # Rolling counters and histograms may include the previous routing
    # revision, even on the same pod. Only current-state checks precede arming.
    if age < WINDOW:
        return 'WARMUP', 'full_new_identity_window_required'
    if values['throttle'] > 0.10 or values['canary_bad'] > 0 or values['gpu_oom'] > 0 or values['gpu_fatal'] > 0:
        return 'ABORT', 'throttling_bad_result_or_gpu_error'
    for metric, limit in (('first', 30), ('post', 3)):
        candidate = values.get(f'canary_{metric}_p95')
        control = values.get(f'control_{metric}_p95')
        if candidate is not None and (candidate >= limit or (control is not None and candidate > 1.2 * control)):
            return 'ABORT', 'latency_emergency'
    if values['gpu_nonzero'] <= 0 or values['gpu_samples'] < 54:
        return 'HOLD', 'unmeasured_or_unloaded'
    if min(values['canary_first_count'], values['control_first_count']) < 100:
        return 'HOLD', 'insufficient_first_text_samples'
    if any(values.get(k) is None for k in p95):
        return 'HOLD', 'unmeasured_latency'
    return 'ARMED', 'safety_only_not_acceptance'


def owner_ready(path):
    try:
        value = json.loads(Path(path).read_text())
        return time.time() < float(value['expires']) <= time.time() + 300
    except (OSError, ValueError, TypeError, KeyError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--prometheus', required=True)
    parser.add_argument('--owner-lease', required=True, help='Owner renewed JSON expires timestamp, outside worktree')
    parser.add_argument('--revision', required=True, help='New run/routing identity, never reuse after a ramp or HOLD')
    parser.add_argument('--percent', type=float, default=0)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--status-file', required=True, help='Aggregate receipt outside sweepable worktrees')
    parser.add_argument('--seconds', type=int, default=7200)
    args = parser.parse_args()
    if not math.isfinite(args.percent) or not 0 <= args.percent <= 5 or not 900 <= args.seconds <= 43200:
        parser.error('percent must be 0..5; duration 900..43200')
    cluster = Cluster(args.context)
    identity, started, finish = '', time.monotonic(), time.monotonic() + args.seconds
    try:
        while time.monotonic() < finish:
            new_identity = cluster.identity(args.revision + ':' + str(args.percent))
            if new_identity != identity:
                identity, started = new_identity, time.monotonic()
            if not owner_ready(args.owner_lease):
                state, reason = 'HOLD', 'owner_not_ready'
            else:
                state, reason = evaluate(collect(args.prometheus), time.monotonic() - started)
            if not owner_ready(args.owner_lease):
                state, reason = 'HOLD', 'owner_not_ready'
            if args.apply:
                if not cluster.route(identity, args.percent if state in ('WARMUP', 'ARMED') else 0):
                    state, reason = 'HOLD', 'external_routing_change'
            receipt = {
                'state': state,
                'reason': reason,
                'identity': identity,
                'apply': args.apply,
                'age': round(time.monotonic() - started),
                'observed_at': time.time(),
                'percent': args.percent,
            }
            path = Path(args.status_file)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(receipt))
            temporary.replace(path)
            print(json.dumps(receipt), flush=True)
            # At 0%, sparse listener samples are expected during independent
            # public-corpus qualification. It never authorizes live routing.
            observing = args.percent == 0 and state == 'HOLD' and reason == 'insufficient_first_text_samples'
            if state in ('ABORT', 'HOLD') and not observing:
                return 1
            time.sleep(30)
    except Exception as error:
        print(json.dumps({'state': 'HOLD', 'reason': type(error).__name__}), flush=True)
        return 1
    finally:
        Path(args.status_file).write_text(json.dumps({'state': 'STOPPED', 'observed_at': time.time()}))
        if args.apply:
            # If API is unavailable, the last lease still expires within 300s.
            cluster.route(identity, 0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
