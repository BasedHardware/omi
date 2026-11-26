"""ASGI entrypoint of one backend service in a prod-parity stack.

Importing this module imports the backend, so only uvicorn loads it. The
service keeps production's dispatch code; this hands it the stack's shared task
queue (``dev_harness.local_task_queue``) in place of Cloud Tasks.
"""

from __future__ import annotations

from dev_harness import local_task_queue, log_timestamps
from main import app

log_timestamps.install()
task_queue = local_task_queue.install_client()

__all__ = ["app", "task_queue"]
