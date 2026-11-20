"""Resolve this GPU process's image once, after model startup, from its own running Pod."""

import base64
from contextlib import closing
from http.client import HTTPSConnection
import json
from pathlib import Path
import re
import ssl
from urllib.parse import urlencode

_SERVICE_ACCOUNT = Path('/var/run/secrets/kubernetes.io/serviceaccount')
_MAX_RESPONSE = 256 * 1024


def _running_digest(pod: dict) -> str | None:
    container = next(c for c in pod['spec']['containers'] if c['name'] == 'worker')
    status = next(c for c in pod['status']['containerStatuses'] if c['name'] == 'worker')
    if not isinstance(status['state'].get('running'), dict):
        return None
    # Require agreement between the pin on THIS pod and its kubelet-reported
    # running image ID. Some runtimes prefix the latter with a repo or scheme.
    pin = re.fullmatch(r'[^@\s]+@(sha256:[0-9a-f]{64})', container['image'])
    if pin is None:
        return None
    digest = pin.group(1)
    runtime_id = status['imageID'].removeprefix('docker-pullable://').removeprefix('containerd://')
    if runtime_id.rsplit('@', 1)[-1] == digest:
        return digest
    # A bare runtime ID can identify the config instead of the pullable
    # manifest. In that case require the exact pin in the RUNNING image name.
    if re.fullmatch(r'sha256:[0-9a-f]{64}', runtime_id) and status.get('image') == container['image']:
        return digest
    return None


def running_worker_digest() -> str | None:
    """A single namespaced, field-selected PodList using the worker KSA's existing list permission."""
    try:
        token = (_SERVICE_ACCOUNT / 'token').read_text().strip()
        payload = token.split('.')[1]
        # These claims select a candidate only. The API authenticates this
        # same bound token over TLS, and the returned pod UID must match.
        claim = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))['kubernetes.io']
        namespace = (_SERVICE_ACCOUNT / 'namespace').read_text().strip()
        if namespace != claim['namespace'] or not re.fullmatch(r'[a-z0-9-]{1,63}', namespace):
            return None
        name, uid = claim['pod']['name'], claim['pod']['uid']
        if not uid or not re.fullmatch(r'[a-z0-9.-]{1,253}', name):
            return None
        query = urlencode({'fieldSelector': f'metadata.name={name}', 'limit': 1})
        context = ssl.create_default_context(cafile=str(_SERVICE_ACCOUNT / 'ca.crt'))
        with closing(HTTPSConnection('kubernetes.default.svc', timeout=2, context=context)) as api:
            api.request(
                'GET', f'/api/v1/namespaces/{namespace}/pods?{query}', headers={'Authorization': f'Bearer {token}'}
            )
            response = api.getresponse()
            if response.status != 200:
                return None
            body = response.read(_MAX_RESPONSE + 1)
        if len(body) > _MAX_RESPONSE:
            return None
        (pod,) = json.loads(body)['items']
        meta = pod['metadata']
        if (meta['namespace'], meta['name'], meta['uid']) == (namespace, name, uid):
            return _running_digest(pod)
    except Exception:
        # Optional telemetry must never prevent worker readiness or expose the
        # bearer token, the pod response, or exception text.
        pass
    return None
