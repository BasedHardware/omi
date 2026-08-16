"""Instrumented Cloud Tasks worker entrypoint for durable finalization scenarios.

This is a separate process from the listener. The production FastAPI route,
Firestore leases, and finalizer ownership remain real; only JWT crypto and
provider-side work are replaced with deterministic local seams.
"""

from testing.listen_pusher_stack.cloud_tasks import install_loopback_task_auth
from testing.listen_pusher_stack.finalizer_leaves import install_finalizer_leaves

install_loopback_task_auth()
install_finalizer_leaves()

from main import app  # noqa: E402
