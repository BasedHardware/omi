"""Retry-stable identity for a transcribed VAD segment."""

from uuid import NAMESPACE_URL, uuid5
import json


def chunk_identity(uid: str, source: str, device: str | None, locked: bool, timestamp: float) -> str:
    # The same timestamp/provenance is the same input anchor across job retries.
    return str(uuid5(NAMESPACE_URL, json.dumps([uid, source, device, bool(locked), float(timestamp)])))
