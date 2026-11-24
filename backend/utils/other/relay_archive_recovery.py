"""Bounded, generation-pinned original validation for cold playback recovery.

Only decoded frame unions become recovery candidates. The cache holds proof
metadata, never PCM, and is not custody or permission to release a producer.
"""

import threading
import time
import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass

from utils.other.private_sync_get_metrics import Reader, object_get_reader
from utils.other import raw_audio_read
from utils.other.audio_frame_table import (
    FRAME_SCHEMA,
    committed_frames,
    entries,
    gapped_frames,
    io_timeout,
    resampled_samples,
)
from utils.other.relay_recovery_metrics import SAMPLES

MAX_PACK_BYTES = 16 * 1024 * 1024
MAX_DECODED_BYTES = 128 * 1024 * 1024
MAX_NEW_PACKS = 64
MAX_PROOFS = 1024
MAX_PROOF_SPANS = 4096
PROOF_SECONDS = 300


@dataclass(frozen=True)
class ProofKey:
    bucket: str
    uid: str
    conversation: str
    path: str
    generation: int
    metageneration: int | None
    media_digest: str
    frame_digest: str


_proofs: OrderedDict[ProofKey, tuple[float, list[dict]]] = OrderedDict()
_lock = threading.Lock()


@object_get_reader(Reader.ARCHIVE_RECONCILE)
def validated_uncovered_packs(bucket, uid, cid, chunks):
    deadline = time.monotonic() + 20
    packs = raw_audio_read.list_packs(bucket, uid, cid, fresh=True, deadline=deadline, max_count=4096, strict=True)
    candidates = raw_audio_read.uncovered_raw_packs(packs, chunks)
    decoded_bytes = new_packs = 0
    validated = []
    sources = {pack['path']: pack for pack in candidates}
    try:
        for path, source in sources.items():
            io_timeout(deadline)
            if not path.startswith(f'raw-live/{uid}/{cid}/') or any(p in {'.', '..'} for p in path.split('/')):
                raise ValueError('recovery source owner mismatch')
            generation = int(source['generation'])
            blob = bucket.blob(path, generation=generation)
            blob.reload(if_generation_match=generation, timeout=io_timeout(deadline), retry=None)
            metadata = blob.metadata or {}
            if (
                not blob.size
                or blob.size > MAX_PACK_BYTES
                or metadata.get('conversation_id') != cid
                or metadata.get('clock_source') != 'server_projected'
                or int(metadata.get('channels', 0)) != 1
                or metadata.get('source_layout', 'mono') != 'mono'
                or metadata.get('custody_schema') != 'audio_custody_v1'
            ):
                raise ValueError('recovery source is not positioned custody audio')
            frames, rate = (
                committed_frames(bucket, blob, uid, deadline=deadline)
                if metadata.get('frame_schema') == FRAME_SCHEMA
                else gapped_frames(bucket, blob, uid, deadline=deadline)
            )
            if rate != int(metadata['sample_rate']):
                raise ValueError('recovery manifest sample rate mismatch')
            metageneration = getattr(blob, 'metageneration', None)
            frame_digest = hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest()
            key = ProofKey(bucket.name, uid, cid, path, generation, metageneration, metadata['sha256'], frame_digest)
            # A backend without metadata generation cannot lend its old proof
            # to a metadata-only update; validate again instead.
            with _lock:
                cached = _proofs.get(key) if metageneration is not None else None
            if cached and cached[0] > time.monotonic():
                needed = raw_audio_read.uncovered_raw_packs(cached[1], chunks)
                if len(validated) + len(needed) > 4096:
                    raise TimeoutError('recovery frame inventory budget exhausted')
                validated.extend(needed)
                continue
            if new_packs >= MAX_NEW_PACKS:
                raise TimeoutError('recovery decode pack budget exhausted')
            expected = resampled_samples(sum(frame['samples'] for frame in frames), rate) * 2
            if expected <= 0 or decoded_bytes + expected > MAX_DECODED_BYTES:
                raise TimeoutError('recovery decoded byte budget exhausted')
            # Pin media AND metadata. Frame helpers check owner, manifest hash,
            # media generation/hash and frame ordering before any read here.
            pcm = raw_audio_read.read_pack(
                bucket,
                path,
                uid,
                {
                    'if_generation_match': generation,
                    **({'if_metageneration_match': metageneration} if metageneration is not None else {}),
                    'timeout': io_timeout(deadline),
                },
                frames=frames,
            )
            if len(pcm) != expected:
                raise ValueError('recovery decoded frame coverage mismatch')
            del pcm
            decoded_bytes += expected
            new_packs += 1
            # Rebuild from the manifest, never the pack's envelope or a sliced
            # candidate. This preserves gaps and zero-sample diagnostic rows.
            full_source = {**source, 'timestamp': float(metadata['capture_start'])}
            for field in tuple(full_source):
                if field.startswith('raw_') and field not in {'raw_end', 'raw_created_at'}:
                    full_source.pop(field)
            proven = entries(frames, rate, full_source, allow_empty=True)
            needed = raw_audio_read.uncovered_raw_packs(proven, chunks)
            if len(validated) + len(needed) > 4096:
                raise TimeoutError('recovery frame inventory budget exhausted')
            validated.extend(needed)
            if metageneration is not None:
                with _lock:
                    _proofs[key] = (time.monotonic() + PROOF_SECONDS, proven)
                    _proofs.move_to_end(key)
                    while (
                        len(_proofs) > MAX_PROOFS or sum(len(value[1]) for value in _proofs.values()) > MAX_PROOF_SPANS
                    ):
                        _proofs.popitem(last=False)
        recovered = raw_audio_read.uncovered_raw_packs(validated, chunks)
        return recovered
    except Exception:
        # Known candidate samples remain debt. This is an observation of a
        # failed proof, never a claim that these source samples were lost.
        SAMPLES.labels(stage='missing').inc(sum(item['span']['samples'] for item in candidates))
        raise
