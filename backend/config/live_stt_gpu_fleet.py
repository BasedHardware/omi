"""Retirement switch for the shared Parakeet API and hosted VAD GPUs.

Production sets this on only after vendor routing is deployed to every caller.
The dedicated batch worker owns its models and does not use either service.
Speaker embeddings are independent and must remain available.
"""

import os
from collections.abc import Mapping


def gpu_fleet_off(env: Mapping[str, str] | None = None) -> bool:
    raw = os.getenv('STT_GPU_FLEET_OFF', 'false') if env is None else env.get('STT_GPU_FLEET_OFF', 'false')
    return raw.strip().lower() in {'true', '1', 'on', 'yes'}


def streaming_parakeet_slot_enabled() -> bool:
    """Rollback only the plain streaming slot; window and PTT policies are separate."""
    return os.getenv('STT_STREAMING_PARAKEET_SLOT_ENABLED', 'false').strip().lower() in {'true', '1', 'on', 'yes'}
