"""Immutable derived audio writes. GCS preconditions arbitrate cross-worker races."""

import json
import math
from typing import Any

from google.api_core.exceptions import NotFound, PreconditionFailed

from utils.sync.repeat_work_metrics import PLAYBACK_WRITES


def _valid_spans(spans: Any) -> bool:
    return (
        isinstance(spans, list)
        and bool(spans)
        and all(
            isinstance(span, dict)
            and isinstance(span.get('file_id'), str)
            and bool(span['file_id'])
            and all(
                isinstance(span.get(key), (int, float)) and not isinstance(span[key], bool) and math.isfinite(span[key])
                for key in ('wall_offset', 'artifact_offset', 'len')
            )
            and span['artifact_offset'] >= 0
            and span['len'] > 0
            for span in spans
        )
    )


def _discard_pair(blob: Any, generation: Any, manifest: Any) -> None:
    # Delete only the snapshots observed with the invalid manifest. Never remove
    # a replacement published by a concurrent repair; GCS has no pair transaction.
    for target, observed in ((blob, generation), (manifest, manifest.generation)):
        if observed is None:
            continue
        try:
            target.delete(if_generation_match=observed)
        except NotFound:
            pass
        except PreconditionFailed:
            return


def cached_manifest(blob: Any) -> tuple[int, list[dict[str, Any]]] | None:
    try:
        blob.reload()
        generation = blob.generation
    except NotFound:
        generation = None
    manifest = blob.bucket.blob(f'{blob.name}.manifest.json')
    try:
        manifest.reload()
        spans = json.loads(manifest.download_as_bytes(if_generation_match=manifest.generation))
        if not _valid_spans(spans):
            raise ValueError('invalid playback spans manifest')
    except (NotFound, PreconditionFailed):
        return None
    except (ValueError, OverflowError):
        # Corruption is a cache miss, not an encode failure that burns all task
        # attempts and pins an unavailable marker. Orphan sidecars heal too.
        _discard_pair(blob, generation, manifest)
        return None
    if generation is None:
        return None
    # Legacy MP3s need no metadata patch: a valid sidecar is sufficient proof.
    PLAYBACK_WRITES.labels('cache_hit').inc()
    return blob.size, spans


def write_once(blob: Any, data: bytes, *, spans: list[dict[str, Any]] | None = None) -> bool:
    if spans is not None:
        if cached_manifest(blob) is not None:
            return False
        # Publish first even for legacy MP3s missing their sidecar, so the next
        # stamp-failed retry can reuse the artifact without another encode.
        manifest = blob.bucket.blob(f'{blob.name}.manifest.json')
        try:
            manifest.upload_from_string(json.dumps(spans), content_type='application/json', if_generation_match=0)
        except PreconditionFailed:
            pass
        blob.metadata = {'playback_manifest': 'v1'}
    if blob.exists():
        PLAYBACK_WRITES.labels('cache_hit').inc()
        return False
    try:
        blob.upload_from_string(data, content_type='audio/mpeg', if_generation_match=0)
    except PreconditionFailed:
        PLAYBACK_WRITES.labels('cache_hit').inc()
        return False
    PLAYBACK_WRITES.labels('generated').inc()
    return True
