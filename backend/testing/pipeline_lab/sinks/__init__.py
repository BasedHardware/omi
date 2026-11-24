"""Capture-only side-effect sinks (DESIGN L9). Nothing here ever delivers anything.

- **FCM**: one choke point, ``firebase_admin.messaging.send_each`` (plus ``send`` and
  the multicast variants). Every message becomes a would-have-fired row and the
  product gets a success response (the daily summary raises when 0 devices are
  reached, so a failure response would change control flow).
- **Webhooks**: ``utils.webhooks._post_dev_webhook`` answers 200 without IO.
- **Task sync**: ``utils.task_sync._sync_to_cloud_service`` records and reports synced.
- **App integrations / anything else over HTTP**: ``httpx`` and ``requests`` sends to a
  host outside the lab allowlist are recorded and answered ``200 {}``.
- **PostHog**: keys are blank in the lab env; ``emit_product_event`` is also captured.

Each captured row carries the conversation and stage from :func:`capture_scope`.
"""

from testing.pipeline_lab.sinks.capture import CaptureSinks, capture_scope, current_scope

__all__ = ['CaptureSinks', 'capture_scope', 'current_scope']
