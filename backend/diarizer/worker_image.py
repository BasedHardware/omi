"""Resolve the dedicated worker's own image once, after model startup."""

import base64
from contextlib import closing
from http.client import HTTPSConnection, HTTPException
import json
from pathlib import Path
import re
import ssl
from urllib.parse import urlencode

SERVICE_ACCOUNT = Path('/var/run/secrets/kubernetes.io/serviceaccount')
MAX_POD_BYTES = 1024 * 1024


def running_worker_digest(pod, namespace, name, uid):
    meta = pod['metadata']
    if (meta['namespace'], meta['name'], meta['uid']) != (namespace, name, uid) or not uid:
        return None
    (worker,) = [c for c in pod['spec']['containers'] if c['name'] == 'worker']
    (status,) = [c for c in pod['status']['containerStatuses'] if c['name'] == 'worker']
    image = worker['image']
    pin = re.fullmatch(r'[^@\s]+@(sha256:[0-9a-f]{64})', image)
    if not pin or not status['state'].get('running'):
        return None
    digest = pin[1]
    image_id = status['imageID']
    if image_id in (image, 'docker-pullable://' + image, digest, 'containerd://' + digest):
        return digest
    return None


def producing_image_digest() -> str | None:
    """One bounded read using the worker KSA's existing namespaced pods/list grant."""
    try:
        token = (SERVICE_ACCOUNT / 'token').read_text().strip()
        # These hints select the lookup. The API server authenticates the very
        # same bound token, and we check the returned Pod UID before attribution.
        _, payload, _ = token.split('.')
        claims = json.loads(base64.urlsafe_b64decode(payload + '==='))['kubernetes.io']
        namespace, pod = claims['namespace'], claims['pod']
        name, uid = pod['name'], pod['uid']
        if not re.fullmatch(r'[a-z0-9-]+', namespace) or not re.fullmatch(r'[a-z0-9.-]+', name) or not uid:
            return None
        query = urlencode({'fieldSelector': 'metadata.name=' + name, 'limit': 1})
        context = ssl.create_default_context(cafile=str(SERVICE_ACCOUNT / 'ca.crt'))
        with closing(HTTPSConnection('kubernetes.default.svc', context=context, timeout=2)) as api:
            api.request(
                'GET', f'/api/v1/namespaces/{namespace}/pods?{query}', headers={'Authorization': 'Bearer ' + token}
            )
            with api.getresponse() as response:
                if response.status != 200:
                    return None
                body = response.read(MAX_POD_BYTES + 1)
        if len(body) <= MAX_POD_BYTES:
            (own_pod,) = json.loads(body)['items']
            return running_worker_digest(own_pod, namespace, name, uid)
    except (OSError, HTTPException, ValueError, KeyError, TypeError, AttributeError):
        # Optional provenance must never prevent a fenced completion.
        pass
    return None
