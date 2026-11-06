#!/usr/bin/env python3
"""Lead-only streaming GPU teardown. Default is an offline, non-mutating plan.

Run only after the caller train, a measured 15-minute no-request drain, and
retirement of host scale-up writers. Removes only the retired production
Parakeet ingress and separately gated legacy Deepgram resources; never removes
storage, reservations, shared Gateway or dev LBs. VAD and LID stay untouched.
Node pools are retained at min=max=size zero only after ALL non-DaemonSet pods
have left them. Original autoscaling bounds are saved; batch/diarizer pools are
absent from the allowlist. Re-run after a partial failure with the same backup.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request

CONTEXT = 'gke_based-hardware_us-central1_prod-omi-gke'
NAMESPACE = 'prod-omi-backend'
PROJECT = 'based-hardware'
REGION = 'us-central1'
CLUSTER = 'prod-omi-gke'
POOLS = ('parakeet-pool', 'parakeet-pool-b', 'parakeet-pool-v2')
DEPLOYMENTS = ('prod-omi-parakeet',)
GUARD = 'prod-omi-incluster-guards'


def execute(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=1800)
    if result.returncode:
        # CLI errors may embed identifiers: keep stdout/stderr out of operator logs.
        raise RuntimeError(f'{args[0]} {args[1]} failed (exit {result.returncode}); no further steps run')
    return json.loads(result.stdout) if result.stdout.strip() else {}


def kubectl(*args):
    return execute(['kubectl', '--context', CONTEXT, '-n', NAMESPACE, *args])


def cloud(*args):
    return execute(['gcloud', 'container', *args, '--project', PROJECT, '--region', REGION, '--format=json'])


def legacy_kubectl(*args):
    return execute(['kubectl', '--context', CONTEXT, '-n', 'prod-omi-dg-self-hosted', *args])


def complete_zero_window(points, start, end):
    """Absence, gaps and nonzero traffic never authorize deleting an ingress."""
    expected = int((end - start).total_seconds() / 60)
    try:
        samples = {
            datetime.fromisoformat(p['interval']['endTime'].replace('Z', '+00:00')): int(p['value']['int64Value'])
            for p in points
        }
    except (KeyError, ValueError, TypeError):
        return False
    stamps = sorted(samples)
    return (
        len(stamps) >= expected
        and stamps[0] <= start + timedelta(minutes=1)
        and stamps[-1] >= end - timedelta(minutes=1)
        and all(value == 0 for value in samples.values())
        and all((b - a).total_seconds() <= 60 for a, b in zip(stamps, stamps[1:]))
    )


def legacy_traffic_proof(ingress):
    """Aggregate infrastructure counters only; never read logs or account data."""
    annotations = ingress.get('metadata', {}).get('annotations', {})
    rules = [
        annotations[k]
        for k in ('ingress.kubernetes.io/forwarding-rule', 'ingress.kubernetes.io/https-forwarding-rule')
        if annotations.get(k)
    ]
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=3)
    start = end - timedelta(hours=24)
    proof = {
        'from': start.isoformat(),
        'to': end.isoformat(),
        'zero_proven': False,
        'reason': 'missing_forwarding_rule',
    }
    if not rules:
        return proof
    token = subprocess.run(['gcloud', 'auth', 'print-access-token'], capture_output=True, text=True, timeout=60)
    if token.returncode:
        return {**proof, 'reason': 'credential_unavailable'}
    for rule in rules:
        params = {
            'filter': f'metric.type="loadbalancing.googleapis.com/https/internal/request_count" AND resource.type="internal_http_lb_rule" AND resource.labels.forwarding_rule_name="{rule}"',
            'interval.startTime': start.isoformat(),
            'interval.endTime': end.isoformat(),
            'aggregation.alignmentPeriod': '60s',
            'aggregation.perSeriesAligner': 'ALIGN_SUM',
            'aggregation.crossSeriesReducer': 'REDUCE_SUM',
            'pageSize': '100000',
        }
        request = urllib.request.Request(
            f'https://monitoring.googleapis.com/v3/projects/{PROJECT}/timeSeries?' + urllib.parse.urlencode(params),
            headers={'Authorization': 'Bearer ' + token.stdout.strip()},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
        except Exception as error:
            return {**proof, 'reason': 'metric_read_' + type(error).__name__}
        series = result.get('timeSeries', [])
        points = [p for series_ in series for p in series_.get('points', [])]
        if result.get('nextPageToken') or len(series) != 1 or not complete_zero_window(points, start, end):
            return {**proof, 'reason': 'traffic_nonzero_or_coverage_unknown', 'samples': len(points)}
    return {**proof, 'zero_proven': True, 'reason': 'complete_24h_zero_window', 'forwarding_rules': len(rules)}


def retire_legacy_deepgram(backup):
    deployments = legacy_kubectl('get', 'deployments', '-o', 'json')['items']
    for d in deployments:
        if d['metadata']['name'] in ('deepgram-api', 'deepgram-engine', 'deepgram-license-proxy') and d['spec'].get(
            'replicas', 0
        ):
            raise RuntimeError('Legacy Deepgram is active; preserve its resources and coordinate with lead')
    for name in ('deepgram-api-hpa', 'deepgram-engine-hpa'):
        hpa = legacy_kubectl('get', 'hpa', name, '--ignore-not-found', '-o', 'json')
        print(f'before legacy HPA {name}: present={bool(hpa)}')
        if hpa:
            save_once(
                backup / f'{name}.json',
                {
                    'apiVersion': hpa['apiVersion'],
                    'kind': hpa['kind'],
                    'metadata': {'name': name, 'namespace': 'prod-omi-dg-self-hosted'},
                    'spec': hpa['spec'],
                },
            )
        legacy_kubectl('delete', 'hpa', name, '--ignore-not-found', '-o', 'json')
        if legacy_kubectl('get', 'hpa', name, '--ignore-not-found', '-o', 'json'):
            raise RuntimeError('Legacy HPA still exists')
        print(f'after legacy HPA {name}: absent')
        print(
            f'ROLLBACK: kubectl --context {CONTEXT} -n prod-omi-dg-self-hosted apply -f {backup / (name + ".json")} only with new lead approval'
        )
    ingress = legacy_kubectl('get', 'ingress', 'deepgram-api-ingress', '--ignore-not-found', '-o', 'json')
    print(f'before legacy ingress: present={bool(ingress)}')
    if not ingress:
        print('after legacy ingress: already absent; ROLLBACK: no change')
        return
    proof = legacy_traffic_proof(ingress)
    (backup / 'deepgram-traffic-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    if not proof['zero_proven']:
        print(
            f'after legacy ingress: PRESERVED; 24h zero traffic not proven ({proof["reason"]}); lead owns follow-up. ROLLBACK: no change'
        )
        return
    save_once(
        backup / 'deepgram-ingress.json',
        {
            'apiVersion': ingress['apiVersion'],
            'kind': ingress['kind'],
            'metadata': {
                'name': 'deepgram-api-ingress',
                'namespace': 'prod-omi-dg-self-hosted',
                'annotations': {
                    k: v
                    for k, v in ingress['metadata'].get('annotations', {}).items()
                    if k.startswith(('kubernetes.io/', 'networking.gke.io/'))
                },
            },
            'spec': ingress['spec'],
        },
    )
    legacy_kubectl('delete', 'ingress', 'deepgram-api-ingress', '--ignore-not-found', '-o', 'json')
    if legacy_kubectl('get', 'ingress', 'deepgram-api-ingress', '--ignore-not-found', '-o', 'json'):
        raise RuntimeError('Legacy ingress still exists')
    print(
        f'after legacy ingress: absent; complete zero window {proof["from"]} to {proof["to"]} (3min telemetry delay); verify controller reclamation'
    )
    print(
        f'ROLLBACK: kubectl --context {CONTEXT} -n prod-omi-dg-self-hosted apply -f {backup / "deepgram-ingress.json"}'
    )


def save_once(path, obj):
    """Never overwrite the positive baseline on an idempotent second run."""
    if not path.exists():
        path.write_text(json.dumps(obj, indent=2) + '\n')
        path.chmod(0o600)


def selected_nodes(nodes):
    return {
        n['metadata']['name']: n['metadata']['labels']['cloud.google.com/gke-nodepool']
        for n in nodes
        if n['metadata']['labels'].get('cloud.google.com/gke-nodepool') in POOLS
    }


def assert_pool_role(name, pool):
    labels = pool.get('config', {}).get('labels', {})
    expected = 'parakeet' if name.startswith('parakeet-') else 'vad'
    if name not in POOLS or labels.get('service') != expected or labels.get('env') != 'prod':
        raise RuntimeError(
            'Pool is repurposed or ownership is unknown; preserve borrowed capacity and coordinate with lead'
        )


def autoscaling_bounds(pool, *, zero=False):
    spec = pool.get('autoscaling', {})
    if 'totalMaxNodeCount' in spec or 'totalMinNodeCount' in spec:
        low, high = (0, 0) if zero else (spec.get('totalMinNodeCount', 0), spec.get('totalMaxNodeCount', 0))
        return [f'--total-min-nodes={low}', f'--total-max-nodes={high}']
    low, high = (0, 0) if zero else (spec.get('minNodeCount', 0), spec.get('maxNodeCount', 0))
    return [f'--min-nodes={low}', f'--max-nodes={high}']


def assert_no_foreign_pods(nodes, pods, *, drained=False):
    """Owner references, not name prefixes, distinguish allowed streaming pods."""
    selected = selected_nodes(nodes)
    for pod in pods:
        scheduled = pod['spec'].get('nodeName') in selected
        pending_target = pod['spec'].get('nodeSelector', {}).get('cloud.google.com/gke-nodepool') in POOLS
        if not scheduled and not pending_target:
            continue
        owners = pod['metadata'].get('ownerReferences', [])
        daemon = any(o['kind'] == 'DaemonSet' for o in owners)
        streaming = (
            pod['metadata']['namespace'] == NAMESPACE
            and pod['metadata'].get('labels', {}).get('app.kubernetes.io/name') in ('parakeet', 'vad')
            and any(
                o['kind'] == 'ReplicaSet' and any(o['name'].startswith(d + '-') for d in DEPLOYMENTS) for o in owners
            )
        )
        if not daemon and (drained or not streaming):
            raise RuntimeError(
                'Target pool contains a non-retired workload; preserve this pool and coordinate with lead'
            )
        if not daemon and any(
            v.get('persistentVolumeClaim') or v.get('hostPath') for v in pod['spec'].get('volumes', [])
        ):
            raise RuntimeError('Streaming pod has persistent/host storage; inspect data custody before proceeding')


def assert_callers(deployments):
    required = {'prod-omi-backend-listen', 'prod-omi-pusher'}
    if not required.issubset({d['metadata']['name'] for d in deployments}):
        raise RuntimeError('Required caller deployment is missing')
    for d in deployments:
        name = d['metadata']['name']
        if name not in required and not (name.startswith('prod-omi-backend-listen-') and d['spec'].get('replicas', 0)):
            continue
        spec, status = d['spec'], d.get('status', {})
        if (
            spec.get('replicas', 0) < 1
            or status.get('replicas', 0) != spec['replicas']
            or status.get('updatedReplicas', 0) != spec['replicas']
            or status.get('readyReplicas', 0) != spec['replicas']
            or status.get('observedGeneration', 0) < d['metadata']['generation']
        ):
            raise RuntimeError('Caller rollout is not fully ready')
        env = {e['name']: e.get('value') for e in spec['template']['spec']['containers'][0].get('env', [])}
        if env.get('STT_GPU_FLEET_OFF', '').lower() != 'true':
            raise RuntimeError('Caller has not declared fleet-off')


def assert_cloud_run():
    for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        obj = execute(
            [
                'gcloud',
                'run',
                'services',
                'describe',
                service,
                '--project',
                PROJECT,
                '--region',
                REGION,
                '--format=json',
            ]
        )
        traffic = [t for t in obj['status']['traffic'] if t.get('percent', 0) > 0]
        if sum(t['percent'] for t in traffic) != 100:
            raise RuntimeError('Cloud Run traffic cannot be proven complete')
        for t in traffic:
            revision = execute(
                [
                    'gcloud',
                    'run',
                    'revisions',
                    'describe',
                    t['revisionName'],
                    '--project',
                    PROJECT,
                    '--region',
                    REGION,
                    '--format=json',
                ]
            )
            env = {e['name']: e.get('value') for e in revision['spec']['containers'][0].get('env', [])}
            if env.get('STT_GPU_FLEET_OFF', '').lower() != 'true':
                raise RuntimeError('A serving Cloud Run revision still permits streaming GPUs')
            print(
                f'caller {service} revision={t["revisionName"]} traffic={t["percent"]}% fleet_off=true release={env.get("OMI_BACKEND_RELEASE_SHA", "UNKNOWN")}'
            )


def cluster_state():
    nodes = execute(['kubectl', '--context', CONTEXT, 'get', 'nodes', '-o', 'json'])['items']
    pods = execute(['kubectl', '--context', CONTEXT, 'get', 'pods', '-A', '-o', 'json'])['items']
    return nodes, pods


def snapshot(backup):
    """Read-only cloud capture before charts turn the warm workloads off."""
    backup.mkdir(parents=True, exist_ok=True)
    for name in DEPLOYMENTS:
        deploy = kubectl('get', 'deployment', name, '-o', 'json')
        save_once(backup / f'{name}-replicas.json', {'replicas': deploy['spec']['replicas']})
        hpa = kubectl('get', 'hpa', name, '--ignore-not-found', '-o', 'json')
        if hpa:
            save_once(
                backup / f'{name}-hpa.json',
                {
                    'apiVersion': hpa['apiVersion'],
                    'kind': hpa['kind'],
                    'metadata': {'name': name, 'namespace': NAMESPACE},
                    'spec': hpa['spec'],
                },
            )
        ingress = kubectl('get', 'ingress', name, '--ignore-not-found', '-o', 'json')
        if ingress:
            save_once(
                backup / f'{name}-ingress.json',
                {
                    'apiVersion': ingress['apiVersion'],
                    'kind': ingress['kind'],
                    'metadata': {
                        'name': name,
                        'namespace': NAMESPACE,
                        'annotations': {
                            k: v
                            for k, v in ingress['metadata'].get('annotations', {}).items()
                            if k.startswith(('kubernetes.io/', 'networking.gke.io/'))
                        },
                    },
                    'spec': ingress['spec'],
                },
            )
    cm = kubectl('get', 'cm', GUARD + '-script', '-o', 'json')
    if 'floors.json' in cm.get('data', {}):
        save_once(backup / 'floors.json', json.loads(cm['data']['floors.json']))
    print(f'SNAPSHOT: capacity/floor baseline saved locally under {backup}; no cloud writes')


def apply(backup):
    backup.mkdir(parents=True, exist_ok=True)
    for name in DEPLOYMENTS:
        path = backup / f'{name}-replicas.json'
        if not path.exists() or json.loads(path.read_text()).get('replicas', 0) < 1:
            raise RuntimeError(
                'Positive rollback baseline missing; capture --snapshot before chart retirement or recover the approved original snapshot'
            )
    assert_callers(kubectl('get', 'deployments', '-o', 'json')['items'])
    assert_cloud_run()
    nodes, pods = cluster_state()
    assert_no_foreign_pods(nodes, pods)
    guard = kubectl('get', 'cronjob', GUARD, '-o', 'json')
    role = kubectl('get', 'role', GUARD, '-o', 'json')
    if not guard['spec'].get('suspend') or guard.get('status', {}).get('active'):
        raise RuntimeError('Apply reviewed guard retirement and wait for its active Jobs first')
    if any(
        'patch' in r.get('verbs', []) and 'horizontalpodautoscalers' in r.get('resources', []) for r in role['rules']
    ):
        raise RuntimeError('Guard still has HPA write permission; apply reviewed chart first')
    print('before guard: suspended=true active_jobs=0 hpa_patch=false')
    for name in DEPLOYMENTS:
        deploy = kubectl('get', 'deployment', name, '-o', 'json')
        save_once(backup / f'{name}-replicas.json', {'replicas': deploy['spec']['replicas']})
        hpas = kubectl('get', 'hpa', name, '--ignore-not-found', '-o', 'json')
        if hpas:
            save_once(
                backup / f'{name}-hpa.json',
                {
                    'apiVersion': hpas['apiVersion'],
                    'kind': hpas['kind'],
                    'metadata': {'name': name, 'namespace': NAMESPACE},
                    'spec': hpas['spec'],
                },
            )
        print(f'before {name}: replicas={deploy["spec"]["replicas"]} hpa_present={bool(hpas)}')
        kubectl('scale', 'deployment', name, '--replicas=0', '-o', 'json')
        kubectl('delete', 'hpa', name, '--ignore-not-found', '-o', 'json')
        after = kubectl('get', 'deployment', name, '-o', 'json')
        if after['spec']['replicas'] != 0:
            raise RuntimeError('Deployment did not stay at zero')
        print(f'after {name}: replicas=0 hpa_present=false')
        print(
            f'ROLLBACK: after approved capacity restoration, kubectl --context {CONTEXT} -n {NAMESPACE} apply -f {backup / (name + "-hpa.json")} and scale to replicas in {backup / (name + "-replicas.json")} (keep routing on vendors until Ready)'
        )
    cm = kubectl('get', 'cm', GUARD + '-script', '-o', 'json')
    floors = cm.get('data', {}).get('floors.json')
    if floors is not None:
        save_once(backup / 'floors.json', json.loads(floors))
    print(f'before floors: present={floors is not None}')
    kubectl(
        'patch',
        'cm',
        GUARD + '-script',
        '--type=merge',
        '-p',
        json.dumps({'data': {'floors.json': None}}),
        '-o',
        'json',
    )
    if 'floors.json' in kubectl('get', 'cm', GUARD + '-script', '-o', 'json').get('data', {}):
        raise RuntimeError('Floor removal did not persist')
    print('after floors: present=false; guard remains suspended')
    print('ROLLBACK: restore the saved floor only with an approved warm guard chart after GPU readiness')
    # Bounded foreground drain; no detached child or grep-based waiter.
    deadline = time.monotonic() + 900
    while True:
        nodes, pods = cluster_state()
        try:
            assert_no_foreign_pods(nodes, pods, drained=True)
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Pods did not leave target pools within 15 minutes; pools preserved') from None
            time.sleep(10)
    pools = cloud('node-pools', 'list', '--cluster', CLUSTER)
    by_name = {p['name']: p for p in pools}
    for name in POOLS:
        count = sum(v == name for v in selected_nodes(nodes).values())
        print(f'before pool {name}: present={name in by_name} nodes={count}')
        if name in by_name:
            obj = cloud('node-pools', 'describe', name, '--cluster', CLUSTER)
            assert_pool_role(name, obj)
            print(f'before pool {name} bounds: {" ".join(autoscaling_bounds(obj))}')
            save_once(
                backup / f'{name}-pool.json',
                {'name': name, 'autoscaling': obj.get('autoscaling', {}), 'observedNodes': count},
            )
            # Lead ruling 04:14Z: preserve pool objects; no pool deletion this pass.
            # If GKE refuses 0/0, stop. Never substitute a positive cap.
            cloud(
                'node-pools',
                'update',
                name,
                '--cluster',
                CLUSTER,
                '--enable-autoscaling',
                *autoscaling_bounds(obj, zero=True),
                '--quiet',
            )
            nodes, pods = cluster_state()
            assert_no_foreign_pods(nodes, pods, drained=True)
            assert_pool_role(name, cloud('node-pools', 'describe', name, '--cluster', CLUSTER))
            cloud('clusters', 'resize', CLUSTER, '--node-pool', name, '--num-nodes=0', '--quiet')
            after = cloud('node-pools', 'describe', name, '--cluster', CLUSTER)
            spec = after.get('autoscaling', {})
            if not spec.get('enabled') or any(
                spec.get(k, 0) != 0 for k in ('minNodeCount', 'maxNodeCount', 'totalMinNodeCount', 'totalMaxNodeCount')
            ):
                raise RuntimeError('Pool autoscaling did not retain min=max=0')
            print(f'after pool {name}: retained, autoscaling min=max=0, resize completed at 0')
            original = json.loads((backup / f'{name}-pool.json').read_text())
            flags = ' '.join(autoscaling_bounds(original))
            print(
                f'ROLLBACK: gcloud container node-pools update {name} --cluster {CLUSTER} --project {PROJECT} --region {REGION} --enable-autoscaling {flags}; restore saved workload replicas only after approved capacity recovery'
            )
        else:
            print(f'after pool {name}: already absent; no pool created')
    nodes, pods = cluster_state()
    if selected_nodes(nodes):
        raise RuntimeError('Streaming pool nodes still registered; completion NOT proven')
    for name in DEPLOYMENTS:
        ingress = kubectl('get', 'ingress', name, '--ignore-not-found', '-o', 'json')
        print(f'before dedicated ingress {name}: present={bool(ingress)}')
        if ingress:
            save_once(
                backup / f'{name}-ingress.json',
                {
                    'apiVersion': ingress['apiVersion'],
                    'kind': ingress['kind'],
                    'metadata': {
                        'name': name,
                        'namespace': NAMESPACE,
                        'annotations': {
                            k: v
                            for k, v in ingress['metadata'].get('annotations', {}).items()
                            if k.startswith(('kubernetes.io/', 'networking.gke.io/'))
                        },
                    },
                    'spec': ingress['spec'],
                },
            )
        kubectl('delete', 'ingress', name, '--ignore-not-found', '-o', 'json')
        if kubectl('get', 'ingress', name, '--ignore-not-found', '-o', 'json'):
            raise RuntimeError('Dedicated ingress still exists')
        print(f'after dedicated ingress {name}: absent; wait for GKE controller to reclaim forwarding rules/backends')
        print(
            f'ROLLBACK: kubectl --context {CONTEXT} -n {NAMESPACE} apply -f {backup / (name + "-ingress.json")} after capacity restoration'
        )
    retire_legacy_deepgram(backup)
    print(
        'DONE: zero streaming GPU nodes; retained pools min=max=0; dedicated Parakeet ingress absent; legacy ingress outcome above; data, batch, diarizer, reservations, shared Gateway and dev LBs untouched'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument(
        '--snapshot', action='store_true', help='read-only capacity baseline capture before chart retirement'
    )
    parser.add_argument('--caller-drain-approved', action='store_true')
    parser.add_argument('--host-writers-retired', action='store_true')
    parser.add_argument('--borrowed-pools-reviewed', action='store_true')
    parser.add_argument(
        '--check-legacy-traffic', action='store_true', help='read-only 24h legacy LB request-metric check'
    )
    parser.add_argument('--backup-dir', type=Path, default=Path('/Volumes/Ephemeral/scratch/teardown-1104/rollback'))
    args = parser.parse_args()
    if args.check_legacy_traffic:
        if args.apply:
            parser.error('read-only traffic check and --apply are separate steps')
        ingress = legacy_kubectl('get', 'ingress', 'deepgram-api-ingress', '--ignore-not-found', '-o', 'json')
        print(json.dumps(legacy_traffic_proof(ingress) if ingress else {'ingress': 'absent'}))
        return
    if args.snapshot:
        if args.apply:
            parser.error('--snapshot and --apply are separate steps')
        snapshot(args.backup_dir)
        return
    if not args.apply:
        print(
            'PLAN ONLY: verify caller train+drain and guard suspension/RBAC; scale Parakeet to 0; remove HPAs and floors; drain pods; retain exclusive pools at min=max=size 0: '
            + ', '.join(POOLS)
            + '; remove only their production Parakeet dedicated ingress'
            + '; remove dormant Deepgram HPAs; remove Deepgram ingress only with complete 24h zero-request proof'
        )
        print(
            'ROLLBACK: saved HPA/replica/floor/autoscaling bounds; restore capacity before routing. No commands executed.'
        )
        return
    if not args.caller_drain_approved or not args.host_writers_retired or not args.borrowed_pools_reviewed:
        parser.error(
            '--apply requires --caller-drain-approved, --host-writers-retired, --borrowed-pools-reviewed from lead'
        )
    if os.getenv('GCP_AGENT_TIER') != 'prod-operator':
        parser.error(
            'lead must select the approved prod-operator tier; read-only and human/default identities cannot execute teardown'
        )
    apply(args.backup_dir)


if __name__ == '__main__':
    main()
