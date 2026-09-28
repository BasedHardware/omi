"""Read-side normalization of conversation photo documents.

``ConversationPhoto.base64`` is a required str, and every response that carries photos validates
against it: the photos list and, through ``@with_photos``, the conversation detail, in-progress and
developer reads. Legacy photo docs were stored without ``base64``. Such a doc has no inline pixels,
which the model spells ``''`` (as GCS-backed frame evidence does), so it is served that way rather
than failing the whole response. Every heal is logged and counted so the records stay visible.
"""

import logging
from typing import Any, Dict, Optional

from .read_boundary import record_fallback

logger = logging.getLogger(__name__)


def photo_doc_for_read(snapshot: Any) -> Optional[Dict[str, Any]]:
    """Return a stored photo doc, with a missing or null ``base64`` served as ``''``."""
    data = snapshot.to_dict()
    if not data or data.get('base64') is not None:
        return data
    # Document path and field name only: the doc body carries user content.
    path = getattr(getattr(snapshot, 'reference', None), 'path', '<unknown>')
    logger.warning('Conversation photo without base64 path=%s field=base64', path)
    record_fallback(
        component='firestore_read',
        from_mode='firestore_document',
        to_mode='empty_photo_base64',
        reason='malformed_doc',
        outcome='degraded',
        log=logger,
    )
    return {**data, 'base64': ''}
