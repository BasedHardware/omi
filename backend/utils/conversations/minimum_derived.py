"""Server minimums retain capture/webhooks but never request derived intelligence.

Use the persisted output marker rather than re-evaluating flags or thresholds:
deferred consumers must agree with the notes decision that actually served.
A later enriched replacement naturally removes this restriction.
"""

from collections.abc import Mapping
from typing import Any


def is_server_minimum(conversation: Any) -> bool:
    structured = (
        conversation.get('structured')
        if isinstance(conversation, Mapping)
        else getattr(conversation, 'structured', None)
    )
    provenance = (
        structured.get('title_provenance')
        if isinstance(structured, Mapping)
        else getattr(structured, 'title_provenance', None)
    )
    return provenance == 'server_minimum'
