"""
Vertex AI direct attempt utilities.
"""

import json
from typing import Any


def request_body(body: bytes) -> Any:
    """
    Parse the incoming request body and safely handle generationConfig/thinkingConfig.

    If the parsed JSON is not a mapping (e.g., null, array, primitive), the body is
    returned unchanged to avoid raising AttributeError/TypeError on malformed input.
    When the payload is a mapping, we only inspect ``thinkingConfig`` when
    ``generationConfig`` is also a mapping, preventing errors when either field
    is explicitly ``null`` or missing.
    """
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        # Not valid JSON – return the raw bytes to let upstream handle it.
        return body

    if not isinstance(payload, dict):
        # Payload is a list, string, number, or None – pass through.
        return payload

    generation_config = payload.get("generationConfig")
    if isinstance(generation_config, dict):
        thinking_config = generation_config.get("thinkingConfig")
        if isinstance(thinking_config, dict):
            # Original logic that accessed thinking_config fields can go here.
            # For now we leave the payload untouched.
            pass

    return payload
