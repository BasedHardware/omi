"""Shared metadata parser for prefix listings and exact uploaded objects."""

from typing import Any, Dict, Optional

from config.repeat_work import playback_on_demand
from database.audio_timeline import parse_span_blob_metadata, strip_extension

PRIVATE_CLOUD_EXTENSIONS = ['.batch.enc', '.batch.bin', '.opus.enc', '.opus', '.enc', '.bin']


def audio_chunk_entry(blob: Any, *, source_identity: bool, primary_bucket: str) -> Optional[Dict[str, Any]]:
    """One shared parser for listings and exact-path metadata reads."""
    filename = blob.name.split('/')[-1]
    has_valid_ext = any(filename.endswith(ext) for ext in PRIVATE_CLOUD_EXTENSIONS)
    if has_valid_ext:
        try:
            timestamp_str = strip_extension(filename)
            is_batch = '.batch.' in filename

            if is_batch and '-' in timestamp_str:
                # Batch blob with timestamp range: "first_ts-last_ts"
                first_ts_str, _ = timestamp_str.split('-', 1)
                timestamp = float(first_ts_str)
            else:
                timestamp = float(timestamp_str)

            chunk_entry = {
                'timestamp': timestamp,
                'path': blob.name,
                'size': blob.size,
                'is_batch': is_batch,
                'generation': getattr(blob, 'generation', None),
            }
            if source_identity or playback_on_demand():
                chunk_entry['md5_hash'] = getattr(blob, 'md5_hash', None)
                chunk_entry['crc32c'] = getattr(blob, 'crc32c', None)
            blob_bucket = getattr(getattr(blob, 'bucket', None), 'name', primary_bucket)
            if blob_bucket != primary_bucket:
                chunk_entry['bucket'] = blob_bucket
            span = parse_span_blob_metadata(getattr(blob, 'metadata', None))
            if span is not None:
                chunk_entry['span'] = span
            return chunk_entry
        except ValueError:
            return None
    return None
