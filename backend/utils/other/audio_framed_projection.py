"""One byte-exact PCM projection per framed custody window."""

import hashlib
import json

from google.api_core.exceptions import PreconditionFailed

from utils import encryption
from utils.other.audio_frame_table import receipt_frames
from utils.other.audio_chunk_replay import AudioChunkContentConflict


def upload_projection(
    bucket,
    private_bucket,
    uid,
    conversation_id,
    chunks,
    protection,
    sample_rate,
    write_gate,
    archive_capture=None,
    verify_overlap=None,
):
    paths = []
    for chunk in chunks:
        receipt = chunk['custody_receipt']
        frames, rate = receipt_frames(private_bucket, uid, receipt)
        payload = chunk['data']
        digest = hashlib.sha256(payload).hexdigest()
        if rate != sample_rate or digest != receipt['pcm_sha256'] or len(payload) != receipt['samples'] * 2:
            raise ValueError('framed projection differs from custody PCM')
        if verify_overlap is not None:
            verify_overlap(payload, frames, receipt=receipt)
        suffix = 'enc' if protection == 'enhanced' else 'bin'
        path = f'chunks/{uid}/{conversation_id}/{frames[0]["start"]:.3f}-{frames[-1]["start"]:.3f}.batch.{suffix}'
        blob = bucket.blob(path)
        blob.metadata = {
            'framed_receipt': json.dumps(receipt, sort_keys=True, separators=(',', ':')),
            'record_sample_rate': str(rate),
            'pcm_sha256': digest,
        }
        data = encryption.encrypt_audio_chunk(payload, uid) if protection == 'enhanced' else payload
        with write_gate(uid, bucket):
            try:
                blob.upload_from_string(data, if_generation_match=0, timeout=10, retry=None)
            except PreconditionFailed:
                blob.reload(timeout=10, retry=None)
                # Read actual bytes: projection metadata alone never proves identity.
                existing = blob.download_as_bytes(if_generation_match=int(blob.generation), timeout=10, retry=None)
                existing = encryption.decrypt_audio_file(existing, uid) if protection == 'enhanced' else existing
                if existing != payload or (blob.metadata or {}).get('framed_receipt') != json.dumps(
                    receipt, sort_keys=True, separators=(',', ':')
                ):
                    raise AudioChunkContentConflict('framed projection content conflict')
        paths.append(path)
        if archive_capture is not None:
            captures, offset = [], 0
            for frame in frames:
                size = frame['samples'] * 2
                captures.append(
                    {
                        'data': payload[offset : offset + size],
                        'timestamp': frame['start'],
                        'span': {'start': frame['start'], 'samples': frame['samples'], 'sample_rate': rate},
                    }
                )
                offset += size
            archive_capture(captures, uid, conversation_id, protection, sample_rate)
    return paths
