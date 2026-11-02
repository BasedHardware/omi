#!/usr/bin/env python3
"""Read-only caller audit. Print classifications, never environment values or secrets."""

import argparse
import json
import re
import subprocess
from urllib.parse import urlparse

RETIRED_HOSTS = frozenset({'dg.omi.me', 'dg.omiapi.com'})
RETIRED_ROUTES = re.compile(r'(?:deepgram-api|deepgram-engine|deepgram-license-proxy|omi-dg-self-hosted)(?:[-./:]|$)')
TRUTHY = frozenset({'true', '1', 'yes', 'on'})


def retired_endpoint(value):
    if not isinstance(value, str):
        return False
    return urlparse(value).hostname in RETIRED_HOSTS or bool(RETIRED_ROUTES.search(value))


def classify(env, env_from=()):
    """Fail closed on endpoint/enable references and uninspected envFrom sources."""
    findings = []
    indexed = {entry['name']: entry for entry in env}
    flag = indexed.get('DEEPGRAM_SELF_HOSTED_ENABLED', {})
    if str(flag.get('value', '')).lower() in TRUTHY:
        findings.append('self_hosted_enabled')
    for name, entry in indexed.items():
        if retired_endpoint(entry.get('value', '')):
            findings.append('retired_endpoint:' + name)
        if name.startswith('DEEPGRAM_SELF_HOSTED_') and ('valueFrom' in entry or 'valueSource' in entry):
            findings.append('unresolved_binding:' + name)
    # Even a disabled flag cannot prove other URL bindings in envFrom are clear.
    if env_from:
        findings.append('unresolved_envFrom')
    return sorted(set(findings))


def read_json(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError('read timed out') from None
    if result.returncode:
        # Do not echo upstream stderr: a CLI error may contain workload payloads.
        raise RuntimeError('read failed: ' + argv[0])
    return json.loads(result.stdout) if result.stdout.strip() else None


def effective_env(kubectl, namespace, container, cache):
    # Kubernetes expands envFrom first; direct env takes precedence. ConfigMaps
    # are read in memory and never printed. Secret envFrom remains unresolved.
    expanded, unresolved = {}, []
    for source in container.get('envFrom', []):
        reference = source.get('configMapRef')
        if not reference:
            unresolved.append(source)
            continue
        key = (namespace, reference['name'])
        if key not in cache:
            cache[key] = read_json(
                kubectl + ['-n', namespace, 'get', 'configmap', reference['name'], '--ignore-not-found', '-o', 'json']
            )
        if cache[key] is None:
            if reference.get('optional'):
                continue
            raise RuntimeError('required ConfigMap missing')
        for name, value in cache[key].get('data', {}).items():
            name = source.get('prefix', '') + name
            expanded[name] = {'name': name, 'value': value}
    for entry in container.get('env', []):
        item = dict(entry)
        reference = item.get('valueFrom', {}).get('configMapKeyRef')
        if reference:
            key = (namespace, reference['name'])
            if key not in cache:
                cache[key] = read_json(
                    kubectl
                    + ['-n', namespace, 'get', 'configmap', reference['name'], '--ignore-not-found', '-o', 'json']
                )
            data = (cache[key] or {}).get('data', {})
            if reference['key'] not in data:
                if reference.get('optional'):
                    continue
                raise RuntimeError('required ConfigMap binding missing')
            item = {'name': item['name'], 'value': data[reference['key']]}
        expanded[item['name']] = item
    return list(expanded.values()), unresolved


def audit(context, project, region):
    k = ['kubectl', '--context=' + context]
    workload = read_json(k + ['get', 'deployments,statefulsets,daemonsets,jobs,cronjobs,pods', '-A', '-o', 'json'])
    reports = []
    configmaps = {}
    for obj in workload['items']:
        # The retired namespace contains server config, not callers; checked separately below.
        ns, name = obj['metadata']['namespace'], obj['metadata']['name']
        if ns == 'prod-omi-dg-self-hosted':
            continue
        spec = obj['spec']
        if obj['kind'] == 'CronJob':
            spec = spec['jobTemplate']['spec']
        if obj['kind'] == 'Pod':
            if obj.get('status', {}).get('phase') in ('Succeeded', 'Failed'):
                continue
            pod = spec
        else:
            pod = spec['template']['spec']
        for container in pod.get('containers', []) + pod.get('initContainers', []):
            try:
                env, unresolved = effective_env(k, ns, container, configmaps)
                findings = classify(env, unresolved)
            except (RuntimeError, KeyError, ValueError):
                findings = classify(container.get('env', [])) + ['unresolved_runtime_config']
            reports.append({'workload': f'{ns}/{name}/{container["name"]}', 'findings': findings})
    run = ['gcloud', 'run']
    services = read_json(run + ['services', 'list', '--project=' + project, '--region=' + region, '--format=json'])
    for svc in services:
        name = svc['metadata']['name']
        # Inspect every traffic-serving revision, not just the latest template.
        detail = read_json(
            run + ['services', 'describe', name, '--project=' + project, '--region=' + region, '--format=json']
        )
        revisions = {
            target.get('revisionName') or detail['status'].get('latestReadyRevisionName')
            for target in detail['status'].get('traffic', [])
            if target.get('percent', 0) > 0
        }
        for revision in sorted(r for r in revisions if r):
            rev = read_json(
                run + ['revisions', 'describe', revision, '--project=' + project, '--region=' + region, '--format=json']
            )
            for index, container in enumerate(rev['spec']['containers']):
                reports.append(
                    {'workload': f'run/{name}/{revision}/{index}', 'findings': classify(container.get('env', []))}
                )
    retired = read_json(k + ['-n', 'prod-omi-dg-self-hosted', 'get', 'deployments', '-o', 'json'])
    active = [
        o['metadata']['name']
        for o in retired['items']
        if o['spec'].get('replicas', 1) or o.get('status', {}).get('readyReplicas', 0)
    ]
    routes = read_json(k + ['get', 'httproutes', '-A', '-o', 'json'])
    dg_routes = [
        o['metadata']['namespace'] + '/' + o['metadata']['name']
        for o in routes['items']
        if RETIRED_ROUTES.search(json.dumps(o['spec']))
    ]
    blocked = [r for r in reports if r['findings']]
    return {
        'context': context,
        'project': project,
        'region': region,
        'checked_containers': len(reports),
        'blocked_callers': blocked,
        'active_retired_deployments': active,
        'retired_gateway_routes': dg_routes,
        'safe_to_retire': not (blocked or active or dg_routes),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--region', default='us-central1')
    args = parser.parse_args()
    try:
        report = audit(args.context, args.project, args.region)
    except (RuntimeError, KeyError, ValueError):
        print(json.dumps({'safe_to_retire': False, 'error': 'audit incomplete; no teardown permitted'}))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report['safe_to_retire'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
