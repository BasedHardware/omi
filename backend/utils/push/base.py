"""Neutral push-notification transport port (ADR-0011).

Product code describes *what* to deliver as a backend-neutral :class:`PushMessage`;
the active *channel* selected by ``PUSH_NOTIFICATION_BACKEND`` decides *how*:

- ``fcm`` (default): Firebase Cloud Messaging / APNs. Its send path stays inline in
  ``utils.notifications`` — the 3-lane async architecture (DB pool vs postprocess pool)
  is guarded by tests that pin ``_send_messages``/``run_blocking``/the executors to that
  module, so the FCM code is not relocated. This port is the selection seam plus the
  non-FCM adapters.
- ``unifiedpush``: self-hosted push via UnifiedPush/ntfy (no Google).
- ``disabled``: no remote push at all — the backend runs fully, nothing is sent.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

# Push backend identifiers (value of PUSH_NOTIFICATION_BACKEND).
FCM = 'fcm'
UNIFIEDPUSH = 'unifiedpush'
DISABLED = 'disabled'
VALID_BACKENDS = frozenset({FCM, UNIFIEDPUSH, DISABLED})


@dataclass(frozen=True)
class PushMessage:
    """Backend-neutral push payload.

    ``title is None`` marks a data-only / silent message (no visible notification),
    mirroring the FCM ``notification is None`` convention. ``tag`` is the collapse /
    dedup key; ``is_background`` requests silent/content-available delivery.
    """

    tag: str
    title: Optional[str] = None
    body: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    is_background: bool = False
    priority: str = 'normal'

    @property
    def is_data_only(self) -> bool:
        return self.title is None
