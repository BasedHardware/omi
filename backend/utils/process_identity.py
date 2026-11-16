"""Deployment identity for the process that is running.

Batch-stage behaviour is decided by the policy snapshot admitted with the work
(``config/policy``), never by ambient environment, which is why
``tests/unit/test_batch_stage_env_ratchet.py`` and the pipeline flag budget
scope ``utils/batch_pipeline/**``. Deployment identity is the one question the
environment alone can answer, so it lives here, outside those scopes, and is
read at the call boundary rather than snapshotted at import.

The marker split matches ``omi_logging.configure_logging``: Cloud Run injects
``K_SERVICE``/``CLOUD_RUN_JOB``/``K_REVISION``, GKE injects
``KUBERNETES_SERVICE_HOST``. Nothing here infers a plane from generic labels.
"""

import os

CLOUD_RUN_MARKERS = ('K_SERVICE', 'CLOUD_RUN_JOB', 'K_REVISION')
IN_CLUSTER_MARKER = 'KUBERNETES_SERVICE_HOST'
POD_NAMESPACE_ENV = 'POD_NAMESPACE'


def is_cloud_run() -> bool:
    """True when any Cloud Run marker is present."""
    return any(os.getenv(marker) for marker in CLOUD_RUN_MARKERS)


def is_in_cluster() -> bool:
    """True when the Kubernetes service host marker is present."""
    return bool(os.getenv(IN_CLUSTER_MARKER))


def pod_namespace() -> str:
    """The injected pod namespace, or an empty string when the chart omits it."""
    return os.getenv(POD_NAMESPACE_ENV, '').strip()
