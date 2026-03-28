import json
import os
import logging

from google.cloud import tasks_v2
from google.protobuf import duration_pb2

logger = logging.getLogger(__name__)

CLOUD_TASKS_QUEUE = os.getenv('CLOUD_TASKS_QUEUE')
BACKEND_PUBLIC_URL = os.getenv('BACKEND_PUBLIC_URL')
CLOUD_TASKS_SECRET = os.getenv('CLOUD_TASKS_SECRET') or ''

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = tasks_v2.CloudTasksClient()
    return _client


def enqueue_offline_sync_task(job_id: str, uid: str) -> str:
    """
    Enqueue a Cloud Task to process an offline sync job.

    The task calls POST /v2/sync/process on the backend with the job_id.
    Cloud Tasks handles retry on failure (3 attempts, exponential backoff).

    Returns the created task name.
    """
    client = _get_client()

    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=f"{BACKEND_PUBLIC_URL}/v2/sync/process",
            headers={
                "Content-Type": "application/json",
                "X-Cloud-Tasks-Secret": CLOUD_TASKS_SECRET,
            },
            body=json.dumps({"job_id": job_id, "uid": uid}).encode(),
        ),
        # 15-minute dispatch deadline — covers Deepgram latency spikes
        dispatch_deadline=duration_pb2.Duration(seconds=900),
    )

    created = client.create_task(parent=CLOUD_TASKS_QUEUE, task=task)
    logger.info(f"Enqueued offline sync task for job {job_id}: {created.name}")
    return created.name
