"""Instrumented listener entrypoint for durable finalization scenarios.

The production FastAPI application and task construction remain real. Only the
Cloud Tasks transport client is replaced by a strict loopback boundary.
"""

from testing.listen_pusher_stack.cloud_tasks import install_loopback_tasks_client

install_loopback_tasks_client()

from main import app  # noqa: E402
