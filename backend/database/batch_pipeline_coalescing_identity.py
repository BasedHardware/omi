"""Pure identity derivation shared by upload coalescing and packing telemetry."""

import hashlib
import json
from pathlib import Path


def digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def compatibility_key(arguments, *, privacy_level, generation, language, policy_id, priority):
    """Owner-local equality proof shared by upload grouping and its counterfactual."""
    upload_context = arguments.get('intake_context') or {}
    return digest(
        [
            arguments['uid'],
            upload_context.get('recording_session_id'),
            arguments['conversation_id'],
            arguments['source'],
            arguments['client_device_id'],
            arguments['client_platform'],
            arguments['should_lock'],
            privacy_level,
            generation,
            language,
            policy_id,
            arguments['lane'],
            int(priority),
            sorted({tuple(Path(p).name.split('_')[1:4]) for p in arguments['paths']}),
            upload_context.get('geolocation'),
        ]
    )
