"""Bounded asynchronous OIDC client for the backfill control plane."""

import asyncio
import os
from urllib.parse import urlsplit
from typing import Protocol

import httpx

from utils.executors import critical_executor, run_blocking


def worker_endpoint() -> tuple[str, str]:
    base = os.environ['SYNC_BACKFILL_WORKER_API_URL'].rstrip('/')
    audience = os.environ['SYNC_BACKFILL_WORKER_AUDIENCE'].rstrip('/')
    url = urlsplit(base)
    if (
        url.scheme != 'https'
        or not url.hostname
        or not url.hostname.endswith('.run.app')
        or url.path
        or url.query
        or url.fragment
        or url.username
        or url.password
        or url.port
        or base != audience
    ):
        raise ValueError('worker requires a run.app service base and matching audience')
    return base, audience


def identity_token(audience: str) -> str:
    # Workload Identity's metadata server mints this for the dedicated GSA.
    # No exported JSON keys or interactive gcloud credential path.
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    token = fetch_id_token(Request(), audience)
    if not isinstance(token, str) or not token:
        raise RuntimeError('Workload Identity did not return an ID token')
    return token


class ControlClient(Protocol):
    async def call(self, operation: str, body: dict | None = None) -> dict: ...


class WorkerClient:
    def __init__(self, http: httpx.AsyncClient, base: str, audience: str):
        self.http, self.base, self.audience = http, base, audience

    async def call(self, operation: str, body: dict | None = None) -> dict:
        if operation not in {'claim', 'heartbeat', 'complete', 'fail'}:
            raise ValueError('invalid worker operation')
        async with asyncio.timeout(20):
            token = await run_blocking(critical_executor, identity_token, self.audience)
        response = await self.http.post(
            f'{self.base}/v2/sync-jobs/{operation}',
            json={'stage': 'prod', **(body or {})},
            headers={'Authorization': f'Bearer {token}'},
        )
        response.raise_for_status()
        return response.json()
