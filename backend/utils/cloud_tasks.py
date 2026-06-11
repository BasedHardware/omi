"""Cloud Tasks dispatch + OIDC verification for the v2 sync pipeline.

The /v2/sync-local-files fast path enqueues one named task per sync job;
Cloud Tasks POSTs it back to /v2/sync-jobs/run on the backend-sync service
with an OIDC token minted for SYNC_TASKS_INVOKER_SA.

All functions fail closed when the SYNC_TASKS_* env vars are unset: enqueue
raises (caller falls back to the inline pipeline) and verification returns
403 — the handler ships in the shared image to services that must never
accept task traffic.
"""

import json
import logging
import os
from typing import Optional

from fastapi import HTTPException, Request
from google.api_core.exceptions import AlreadyExists
from google.auth.transport import requests as google_auth_requests
from google.cloud import tasks_v2
from google.oauth2 import id_token
from google.protobuf import duration_pb2

logger = logging.getLogger(__name__)

# Must match the queue's dispatchDeadline and the handler's request timeout
# (HTTP_SYNC_JOBS_RUN_TIMEOUT); see the run-lock TTL invariant in sync_jobs.py.
DISPATCH_DEADLINE_SECONDS = 1500

_tasks_client: Optional[tasks_v2.CloudTasksClient] = None
_google_auth_request: Optional[google_auth_requests.Request] = None


def _get_tasks_client() -> tasks_v2.CloudTasksClient:
    global _tasks_client
    if _tasks_client is None:
        _tasks_client = tasks_v2.CloudTasksClient()
    return _tasks_client


def _get_auth_request() -> google_auth_requests.Request:
    global _google_auth_request
    if _google_auth_request is None:
        _google_auth_request = google_auth_requests.Request()
    return _google_auth_request


def _handler_url() -> str:
    return os.getenv('SYNC_TASKS_HANDLER_URL', '')


def _oidc_audience() -> str:
    return os.getenv('SYNC_TASKS_OIDC_AUDIENCE') or _handler_url()


def _invoker_sa() -> str:
    return os.getenv('SYNC_TASKS_INVOKER_SA', '')


def get_sync_tasks_max_attempts() -> int:
    # Must mirror the queue's maxAttempts (documented invariant).
    return int(os.getenv('SYNC_TASKS_MAX_ATTEMPTS', '5'))


def is_cloud_tasks_dispatch_enabled() -> bool:
    return os.getenv('SYNC_DISPATCH_MODE', 'inline') == 'cloud_tasks'


def enqueue_sync_job(payload: dict) -> None:
    """Enqueue one named HTTP task (task id = job_id) for a sync job.

    A duplicate enqueue of the same job_id is treated as success — Cloud Tasks
    deduplicates named tasks. Any other failure raises; the caller falls back
    to the inline pipeline.
    """
    project = os.getenv('SYNC_TASKS_PROJECT', '')
    location = os.getenv('SYNC_TASKS_LOCATION', '')
    queue = os.getenv('SYNC_TASKS_QUEUE', '')
    url = _handler_url()
    invoker_sa = _invoker_sa()
    if not all([project, location, queue, url, invoker_sa]):
        raise RuntimeError('Cloud Tasks dispatch enabled but SYNC_TASKS_* env vars are incomplete')

    client = _get_tasks_client()
    parent = client.queue_path(project, location, queue)
    task = tasks_v2.Task(
        name=client.task_path(project, location, queue, payload['job_id']),
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=url,
            headers={'Content-Type': 'application/json'},
            body=json.dumps(payload).encode(),
            oidc_token=tasks_v2.OidcToken(service_account_email=invoker_sa, audience=_oidc_audience()),
        ),
        dispatch_deadline=duration_pb2.Duration(seconds=DISPATCH_DEADLINE_SECONDS),
    )
    try:
        client.create_task(parent=parent, task=task)
    except AlreadyExists:
        logger.info('sync job task %s already enqueued, skipping duplicate', payload['job_id'])


def verify_cloud_tasks_oidc(request: Request) -> int:
    """FastAPI dependency for /v2/sync-jobs/run. Returns the task retry count.

    Sync function on purpose — verify_oauth2_token fetches Google certs over
    HTTP, and FastAPI runs sync dependencies in the threadpool.
    """
    audience = _oidc_audience()
    invoker_sa = _invoker_sa()
    if not audience or not invoker_sa:
        # Env unset: this service is not a task target (e.g. main backend
        # running the shared image) — never accept task traffic.
        raise HTTPException(status_code=403, detail='Task dispatch not configured on this service')

    auth_header = request.headers.get('authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=403, detail='Missing bearer token')

    try:
        claims = id_token.verify_oauth2_token(auth_header[len('Bearer ') :], _get_auth_request(), audience=audience)
    except Exception as e:
        # Distinguishes bad tokens from transient JWKS-fetch failures in logs
        logger.warning('OIDC token verification failed: %s', e)
        raise HTTPException(status_code=403, detail='Invalid OIDC token')

    if claims.get('email') != invoker_sa or not claims.get('email_verified'):
        raise HTTPException(status_code=403, detail='Unexpected token identity')

    try:
        return int(request.headers.get('x-cloudtasks-taskretrycount', '0'))
    except ValueError:
        return 0
