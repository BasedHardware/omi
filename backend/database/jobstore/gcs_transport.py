"""Actual SDK/HTTP session transport; no credentials, activation or lake authority.

Single whole-object PUT follows https://cloud.google.com/storage/docs/performing-resumable-uploads.
Terminal statuses are the approved G2/C4 allowlist, not a new remote qualification.
Missing generation metadata on finalized status is unknown; never GET a current
generation to substitute for the one returned by this original session.
"""

import math
from urllib.parse import urlsplit

from google.api_core.exceptions import NotFound

from database import rpc_deadline
from database.jobstore.authority import AuthorityRefused
from utils.batch_pipeline.retention import delete_batch_object
from utils.other.local_storage import LocalStorageClient

TERMINAL = frozenset({200, 201, 404, 410, 412, 499})


class GCSTransport:
    def __init__(self, client, *, timeout):
        if len(timeout) != 2 or any(not math.isfinite(n) or n <= 0 for n in timeout):
            raise ValueError('explicit positive bounded GCS socket timeouts required')
        self.client, self.timeout = client, timeout

    def _timeout(self):
        left = rpc_deadline.remaining()
        if left is not None:
            if left <= 0:
                raise TimeoutError('GCS request not sent: destructive unit deadline passed')
            return tuple(min(value, left / 2) for value in self.timeout)
        return self.timeout

    def create(self, blob, size):
        try:
            return blob.create_resumable_upload_session(
                content_type='application/octet-stream',
                size=size,
                if_generation_match=0,
                timeout=self._timeout(),
                retry=None,
            )
        except Exception:
            raise ConnectionError('GCS session creation unresolved; no bytes authorized') from None

    def request(self, session, method, *, body=b'', size=None):
        parsed = urlsplit(session)
        if not (
            (parsed.scheme == 'https' and parsed.netloc == 'storage.googleapis.com')
            or (parsed.scheme == 'local-session' and isinstance(self.client, LocalStorageClient))
        ):
            raise AuthorityRefused('unqualified GCS session endpoint')
        headers = {'Content-Length': str(len(body))}
        if method == 'PUT':
            headers['Content-Range'] = f'bytes 0-{len(body)-1}/{len(body)}' if body else f'bytes */{size}'
        try:
            # The GCS SDK exposes resumable capabilities through its authorized
            # HTTP session; it has no public whole-session PUT/status method.
            http = getattr(self.client, '_http', None)
            if http is None:
                raise ConnectionError('GCS SDK authorized transport unavailable')
            response = http.request(
                method,
                session,
                data=body,
                headers=headers,
                timeout=self._timeout(),
                allow_redirects=False,
            )
            try:
                status = response.status_code
                properties = response.json() if status in {200, 201} else {}
                generation = (properties or {}).get('generation')
                if generation is not None and (not str(generation).isdigit() or int(generation) <= 0):
                    raise ValueError('invalid original generation')
                return status, int(generation) if generation is not None else None
            finally:
                response.close()
        except Exception:
            # Capabilities are sensitive. Never retain/log the transport exception.
            raise ConnectionError('GCS session transport/outcome unresolved') from None

    def put(self, session, payload):
        status, generation = self.request(session, 'PUT', body=payload)
        if status not in {200, 201} or generation is None:
            raise ConnectionError('GCS finalize refused or original generation unresolved')
        return generation

    def fence(self, sink, *, uid, known_generation=None):
        self.request(sink['session'], 'DELETE')
        status, generation = self.request(sink['session'], 'PUT', size=sink['size'])
        if status not in TERMINAL:
            raise ConnectionError('GCS session is not definitively terminal')
        if generation is not None and known_generation is not None and generation != known_generation:
            raise AuthorityRefused('GCS original generation changed')
        generation = generation or known_generation
        if generation is None and status not in {412, 499}:
            # An expired/missing session is fenced against a future PUT, but
            # may previously have finalized an unobserved generation. Never
            # substitute the current object's metadata or absence for it.
            raise ConnectionError('terminal session original generation unavailable')
        if generation is not None:
            uri = f"gs://{sink['bucket']}/{sink['key']}#{generation}"
            delete_batch_object(
                uid,
                uri,
                timeout=max(self.timeout),
                storage_client=self.client,
                namespace=sink['namespace'],
            )
            blob = self.client.bucket(sink['bucket']).blob(sink['key'], generation=generation)
            try:
                blob.reload(if_generation_match=generation, timeout=self._timeout(), retry=None)
            except NotFound:
                return status, generation
            raise ConnectionError('original GCS generation absence not proved')
        return status, None
