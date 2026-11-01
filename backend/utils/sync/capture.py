"""Retry-stable identity for a transcribed VAD segment."""

from uuid import NAMESPACE_URL, uuid5
import json


def chunk_identity(
    uid: str,
    source: str,
    device: str | None,
    locked: bool,
    timestamp: float,
    *,
    capture_partition: str | None = None,
    clock_run: str | None = None,
) -> str:
    # The same timestamp/provenance is the same input anchor across job retries.
    identity = [uid, source, device, bool(locked), float(timestamp)]
    if capture_partition is not None:
        identity.append(capture_partition)
    if clock_run is not None:
        # Two estimated runs can share an invented timestamp; never one anchor.
        identity.append(f'clock_run:{clock_run}')
    return str(uuid5(NAMESPACE_URL, json.dumps(identity)))
