#!/usr/bin/env python3
"""Private backend-listen env: Secret Manager migration and the deploy guard.

Private listen values (uid-bearing cohorts) live in one Secret Manager JSON
document (LISTEN_PRIVATE_ENV). The backend-secrets chart syncs it into a
dedicated Kubernetes Secret and the listen chart references each declared name
(privateSecretEnv.keys) with a secretKeyRef, so no deploy render carries a value.

Subcommands (all print key names and same/changed/missing only, never a value,
a hash, or a subprocess's output):

  migrate  one-time, inside the protected prod job that holds the retired GitHub
           secret LISTEN_PRIVATE_VALUES_YAML: check its key set against the
           chart, then write the declared private keys as one new Secret
           Manager version. Folded public keys must already equal the chart.
  sync     force-sync the listen-private ExternalSecret and wait until it is Ready.
  guard    before the listen Helm upgrade: every declared key must be present
           and non-empty in the Kubernetes Secret, and where live still carries
           a literal value the two must be identical. Fails before any listen
           mutation otherwise.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from listen_helm_env_overrides import load_private_env, load_values  # noqa: E402

PRIVATE_SECRET_ENV = 'privateSecretEnv'
EXTERNAL_SECRET = 'listen-private-env'


class Refused(Exception):
    """A fixed message that never contains a value."""


def declared(values: dict) -> tuple[str, list[str]]:
    spec = values.get(PRIVATE_SECRET_ENV) or {}
    keys = list(spec.get('keys') or [])
    if not keys:
        return '', []
    name = spec.get('secretName')
    if not isinstance(name, str) or not name:
        raise Refused('privateSecretEnv.secretName is required')
    if len(set(keys)) != len(keys) or not all(isinstance(k, str) and k.isupper() for k in keys):
        raise Refused('privateSecretEnv.keys must be unique env var names')
    return name, keys


def public_literals(values: dict) -> dict[str, str]:
    return {e['name']: str(e['value']) for e in values.get('env') or []
            if isinstance(e, dict) and isinstance(e.get('name'), str) and 'value' in e}


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(a.encode()).digest(), hashlib.sha256(b.encode()).digest())


def run(argv: list[str], *, timeout: int = 60) -> bytes:
    try:
        # Output can carry secret data (kubectl get secret) and is never echoed.
        result = subprocess.run(argv, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Refused(f'{argv[0]} {argv[1] if len(argv) > 1 else ""} timed out') from None
    if result.returncode:
        raise Refused(f'{argv[0]} {" ".join(a for a in argv[1:4] if not a.startswith("-"))} failed (exit {result.returncode})')
    return result.stdout


def kube_json(namespace: str, kind: str, name: str) -> dict:
    return json.loads(run(['kubectl', '-n', namespace, 'get', kind, name, '-o', 'json']) or b'{}')


def secret_data(namespace: str, name: str) -> dict[str, str]:
    doc = kube_json(namespace, 'secret', name)
    return {k: base64.b64decode(v).decode('utf-8') for k, v in (doc.get('data') or {}).items()}


def container_env(pod_spec: dict, container: str) -> dict[str, dict]:
    for c in pod_spec.get('containers') or []:
        if c.get('name') == container:
            return {e['name']: e for e in c.get('env') or []}
    raise Refused('listen container not found in the live pod template')


def live_env(namespace: str, deployment: str, container: str) -> dict[str, dict]:
    doc = kube_json(namespace, 'deployment', deployment)
    return container_env(doc['spec']['template']['spec'], container)


def serving_envs(namespace: str, deployment: str, container: str) -> list[dict[str, dict]]:
    """The Deployment template plus every ReplicaSet that still has pods.

    A mixed rollout can serve an older template; each one must match, not just
    the newest.
    """
    doc = kube_json(namespace, 'deployment', deployment)
    envs = [container_env(doc['spec']['template']['spec'], container)]
    labels = (doc['spec'].get('selector') or {}).get('matchLabels') or {}
    if labels:
        selector = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
        sets = json.loads(run(['kubectl', '-n', namespace, 'get', 'replicaset', '-l', selector, '-o', 'json']) or b'{}')
        for rs in sets.get('items') or []:
            owners = {o.get('name') for o in rs['metadata'].get('ownerReferences') or []}
            if deployment in owners and (rs.get('status') or {}).get('replicas', 0) > 0:
                envs.append(container_env(rs['spec']['template']['spec'], container))
    return envs


def report(rows: list[tuple[str, str]]) -> None:
    for key, effect in rows:
        print(f'LISTEN_PRIVATE_ENV key={key} effect={effect}')


def compare_live(keys: list[str], secret_name: str, secret: dict[str, str], live: dict[str, dict]) -> list[tuple[str, str]]:
    rows = []
    for key in keys:
        value = secret.get(key)
        entry = live.get(key)
        if not value:
            rows.append((key, 'missing-from-secret'))
        elif entry is None:
            rows.append((key, 'added'))  # a newly declared private name: the reviewed Git change adds it
        elif 'valueFrom' in entry:
            ref = (entry['valueFrom'] or {}).get('secretKeyRef') or {}
            rows.append((key, 'same' if ref.get('name') == secret_name and ref.get('key') == key else 'changed-reference'))
        else:
            rows.append((key, 'same' if same(str(entry.get('value', '')), value) else 'changed'))
    return rows


def external_status(namespace: str, name: str) -> dict:
    return kube_json(namespace, 'externalsecret', name).get('status') or {}


def wait_ready(namespace: str, name: str, timeout: int, previous: str | None = None, sleep=time.sleep) -> None:
    """Ready, and (after a force-sync) synced past `previous`.

    ESO's syncedResourceVersion is generation plus a hash of the object's
    metadata, so the force-sync annotation changes it only once ESO has synced
    again; no runner/cluster clock comparison is involved.
    """
    deadline = time.monotonic() + timeout
    while True:
        status = external_status(namespace, name)
        ready = any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in status.get('conditions') or [])
        version = status.get('syncedResourceVersion') or ''
        if ready and version and version != previous:
            print(f'LISTEN_PRIVATE_ENV external_secret={name} ready refreshTime={status.get("refreshTime", "?")}')
            return
        if time.monotonic() >= deadline:
            raise Refused(f'ExternalSecret {name} not Ready{" after force-sync" if previous is not None else ""} within {timeout}s')
        sleep(5)


def cmd_migrate(a) -> int:
    raw = os.environ.pop('LISTEN_PRIVATE_VALUES_YAML', '')
    if not raw.strip():
        raise Refused('LISTEN_PRIVATE_VALUES_YAML is empty; nothing to migrate')
    values = load_values(a.values_file)
    secret_name, keys = declared(values)
    if not keys:
        raise Refused('the chart declares no privateSecretEnv keys')
    public = public_literals(values)
    with tempfile.TemporaryDirectory(prefix='listen-private-') as tmp:
        source = Path(tmp) / 'private.yaml'
        source.write_text(raw)
        del raw
        private = load_private_env(source)
        rows = []
        for name in sorted(private):
            if name in keys:
                continue
            if name in public:
                # Non-sensitive keys were folded into the public chart: they must match exactly.
                rows.append((name, 'public-same' if same(private[name], public[name]) else 'public-changed'))
            else:
                rows.append((name, 'undeclared'))
        rows += [(k, 'missing-from-source') for k in keys if k not in private]
        report(rows)
        if any(effect != 'public-same' for _, effect in rows):
            raise Refused('the GitHub secret does not match the chart declaration; nothing written')
        document = Path(tmp) / 'document.json'
        fd = os.open(document, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump({k: private[k] for k in keys}, handle, sort_keys=True)
        out = run(['gcloud', 'secrets', 'versions', 'add', a.secret_id, f'--project={a.project}',
                   f'--data-file={document}', '--format=value(name)'])
    version = out.decode().strip().rsplit('/', 1)[-1]
    print(f'LISTEN_PRIVATE_ENV secret={a.secret_id} version={version if version.isdigit() else "?"} keys={",".join(keys)}')
    # The same comparison the deploy guard makes, against the source document itself.
    live = live_env(a.namespace, a.deployment, a.container)
    report([(k, 'source-' + e) for k, e in compare_live(keys, secret_name, {k: private[k] for k in keys}, live)])
    return 0


def cmd_sync(a) -> int:
    values = load_values(a.values_file)
    _, keys = declared(values)
    if not keys:
        print('LISTEN_PRIVATE_ENV no privateSecretEnv keys declared; nothing to sync')
        return 0
    previous = external_status(a.namespace, a.external_secret).get('syncedResourceVersion') or ''
    run(['kubectl', '-n', a.namespace, 'annotate', 'externalsecret', a.external_secret,
         f'force-sync={int(time.time())}', '--overwrite'])
    wait_ready(a.namespace, a.external_secret, a.timeout, previous=previous)
    return 0


def cmd_guard(a) -> int:
    values = load_values(a.values_file)
    secret_name, keys = declared(values)
    if not keys:
        print('LISTEN_PRIVATE_ENV no privateSecretEnv keys declared; guard not applicable')
        return 0
    wait_ready(a.namespace, a.external_secret, a.timeout)
    secret = secret_data(a.namespace, secret_name)
    effects: dict[str, set[str]] = {k: set() for k in keys}
    for env in serving_envs(a.namespace, a.deployment, a.container):
        for key, effect in compare_live(keys, secret_name, secret, env):
            effects[key].add(effect)
    # One line per name; any serving template that differs makes the name differ.
    rows = [(k, next(iter(e)) if len(e) == 1 else '+'.join(sorted(e))) for k, e in effects.items()]
    report(rows)
    bad = [k for k, effect in rows if effect not in ('same', 'added')]
    if bad:
        raise Refused(f'private listen env would change or is missing for {",".join(bad)}; '
                      'nothing deployed (see backend/docs/runbooks/listen-private-env.md)')
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['migrate', 'sync', 'guard'])
    p.add_argument('--values-file', type=Path, required=True)
    p.add_argument('--namespace', default='prod-omi-backend')
    p.add_argument('--deployment', default='prod-omi-backend-listen')
    p.add_argument('--container', default='backend-listen')
    p.add_argument('--external-secret', default=f'prod-omi-backend-{EXTERNAL_SECRET}')
    p.add_argument('--project', default='')
    p.add_argument('--secret-id', default='LISTEN_PRIVATE_ENV')
    p.add_argument('--timeout', type=int, default=180)
    a = p.parse_args(argv)
    try:
        return {'migrate': cmd_migrate, 'sync': cmd_sync, 'guard': cmd_guard}[a.command](a)
    except Refused as error:
        print(f'LISTEN_PRIVATE_ENV REFUSED: {error}', file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - never stringify: YAML/kubectl errors can quote values
        print(f'LISTEN_PRIVATE_ENV REFUSED: {type(error).__name__}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
