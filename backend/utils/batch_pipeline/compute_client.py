"""Small OIDC spend-admission client for the GPU image; no legacy dependencies."""

import json
import math
import os
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import fetch_id_token

from utils.batch_pipeline.contracts import LeasedWork


class ComputeClient:
    def __init__(self, base_url: str, audience: str, stage: str, *, token=None, send=None):
        parsed = urlsplit(base_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('explicit HTTPS batch service URL required')
        if not audience or stage not in {'prod', 'dev'}:
            raise ValueError('explicit worker audience and runtime stage required')
        self.url = base_url.rstrip('/') + '/v2/batch-pipeline/authorize-compute'
        self.audience, self.stage = audience, stage
        self._token_source = token or (lambda: fetch_id_token(GoogleRequest(), audience))
        self._send = send or urlopen
        self._token, self._refresh_at = '', 0.0
        self._lock = threading.Lock()

    def __call__(self, leases: list[LeasedWork]) -> dict:
        with self._lock:
            if time.monotonic() >= self._refresh_at:
                self._token = self._token_source()
                self._refresh_at = time.monotonic() + 300
            token = self._token
        body = {
            'stage': self.stage,
            'leases': [{'segment_id': lease.item.segment_id, 'token': lease.token} for lease in leases],
        }
        request = Request(
            self.url,
            data=json.dumps(body).encode(),
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
            },
        )
        try:
            with self._send(request, timeout=5) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('oversized spend admission response')
            result = json.loads(raw)
            identities = {lease.item.segment_id for lease in leases}
            if not isinstance(result, dict) or not isinstance(result.get('allowed'), list):
                raise ValueError('invalid spend admission receipt')
            if any(not isinstance(value, str) or value not in identities for value in result['allowed']):
                raise ValueError('foreign spend admission receipt')
            retries = result.get('retry_after') or {}
            if not isinstance(retries, dict) or any(
                key not in identities
                or type(value) not in {int, float}
                or not math.isfinite(value)
                or not 1 <= value <= 86400
                for key, value in retries.items()
            ):
                raise ValueError('invalid spend admission retry receipt')
            return result
        except Exception:
            self._refresh_at = 0.0
            raise


def from_env() -> ComputeClient:
    return ComputeClient(
        os.getenv('BATCH_PIPELINE_API_URL', '').strip(),
        os.getenv('BATCH_PIPELINE_WORKER_AUDIENCE', '').strip(),
        os.getenv('OMI_ENV_STAGE', '').strip().lower(),
    )
