"""Immutable derived audio writes. GCS preconditions arbitrate cross-worker races."""

import json

from google.api_core.exceptions import NotFound, PreconditionFailed

from utils.sync.repeat_work_metrics import PLAYBACK_WRITES


def write_once(blob, data: bytes, *, spans=None) -> bool:
    if blob.exists():
        PLAYBACK_WRITES.labels('cache_hit').inc()
        return False
    if spans is not None:
        # Publish the small manifest first: a crash after MP3 publication must
        # never require re-encoding to recover the Firestore stamp. A sidecar
        # avoids GCS's 8 KiB custom-metadata limit on long conversations.
        manifest = blob.bucket.blob(f'{blob.name}.manifest.json')
        try:
            manifest.upload_from_string(json.dumps(spans), content_type='application/json', if_generation_match=0)
        except PreconditionFailed:
            pass
        blob.metadata = {'playback_manifest': 'v1'}
    try:
        blob.upload_from_string(data, content_type='audio/mpeg', if_generation_match=0)
    except PreconditionFailed:
        PLAYBACK_WRITES.labels('cache_hit').inc()
        return False
    PLAYBACK_WRITES.labels('generated').inc()
    return True


def cached_manifest(blob):
    try:
        blob.reload()
        if (blob.metadata or {}).get('playback_manifest') != 'v1':
            return None
        spans = json.loads(blob.bucket.blob(f'{blob.name}.manifest.json').download_as_bytes())
    except NotFound:
        return None
    if not isinstance(spans, list) or not spans:
        raise ValueError('invalid playback spans manifest')
    PLAYBACK_WRITES.labels('cache_hit').inc()
    return blob.size, spans
