"""Immutable media + generation-pinned manifest; local disk is never custody.

The media lives in raw-live, so existing playback discovery can recover it even
if the pusher disappears before projecting its legacy chunk/audio_files entry.
Manifests are content addressed and retained; no successful projection deletes
the original. A receipt exists only after BOTH immutable objects commit.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from utils.other import storage
from utils.other.raw_audio import CapturePack, decode_capture
from utils.other.audio_outbox_metrics import CUSTODY_COMMITS, record_failure


@dataclass(frozen=True)
class AudioReceipt:
    bucket: str
    path: str
    generation: str
    sha256: str
    manifest_path: str
    manifest_generation: str
    manifest_sha256: str
    pcm_sha256: str | None
    conversation_id: str | None
    start: float
    samples: int
    sample_rate: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AudioProjection:
    """Accepted derivative window; the custody receipt always covers the original."""

    receipt: AudioReceipt
    start: float
    offset_samples: int
    samples: int

    def __post_init__(self):
        if self.offset_samples < 0 or self.samples <= 0 or self.offset_samples + self.samples > self.receipt.samples:
            raise ValueError('projection falls outside its custody receipt')

    @property
    def conversation_id(self) -> str | None:
        return self.receipt.conversation_id

    @property
    def sample_rate(self) -> int:
        return self.receipt.sample_rate


def _generation(blob) -> str:
    blob.reload(timeout=10, retry=None)
    if not blob.generation:
        raise ValueError('audio custody requires an immutable generation')
    return str(blob.generation)


def commit_capture(
    uid: str,
    raw: bytes,
    name: str,
    metadata: dict[str, Any],
    frames: list[dict],
    *,
    data_protection_level: str | None = None,
) -> AudioReceipt:
    """Return an audio-only receipt, never a transcript-commit certificate."""
    try:
        metadata = {**metadata, 'custody_schema': 'audio_custody_v1'}
        protection = data_protection_level or storage.users_db.get_data_protection_level(uid)
        path = storage.archive_capture_bytes(uid, raw, 'raw-live', name, metadata, data_protection_level=protection)
        bucket = storage.get_private_cloud_sync_bucket()
        blob = bucket.blob(path)
        generation = _generation(blob)
        digest = hashlib.sha256(raw).hexdigest()
        if (blob.metadata or {}).get('sha256') != digest:
            raise ValueError('audio custody media digest mismatch')
        manifest = {
            'schema': 'audio_custody_v1',
            'media': {'bucket': bucket.name, 'path': path, 'generation': generation, 'sha256': digest},
            'capture': metadata,
            'frames': frames,
            # This is a checkpoint of captured frames, not a claim that the
            # device stopped recording or that no unseen frames exist.
            'capture_end_checkpoint': frames[-1] if frames else None,
        }
        payload = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        manifest_path = storage.archive_capture_bytes(
            uid,
            payload,
            'audio-outbox',
            name,
            {
                'format': 'audio-custody-manifest-v1',
                'custody_schema': 'audio_custody_v1',
                'conversation_id': metadata.get('conversation_id'),
            },
            data_protection_level=protection,
        )
        manifest_blob = bucket.blob(manifest_path)
        manifest_generation = _generation(manifest_blob)
        manifest_digest = hashlib.sha256(payload).hexdigest()
        if (manifest_blob.metadata or {}).get('sha256') != manifest_digest:
            raise ValueError('audio custody manifest digest mismatch')
        receipt = AudioReceipt(
            bucket=bucket.name,
            path=path,
            generation=generation,
            sha256=digest,
            manifest_path=manifest_path,
            manifest_generation=manifest_generation,
            manifest_sha256=manifest_digest,
            pcm_sha256=metadata.get('pcm_sha256'),
            conversation_id=metadata.get('conversation_id'),
            start=float(metadata['capture_start']),
            samples=sum(int(frame['samples']) for frame in frames),
            sample_rate=int(metadata['sample_rate']),
        )
        CUSTODY_COMMITS.inc()
        return receipt
    except Exception:
        record_failure('commit')
        raise


def read_pcm(uid: str, receipt: AudioReceipt) -> bytes:
    """Hydrate only the pinned generation and verify actual decoded PCM bytes."""
    bucket = storage.get_private_cloud_sync_bucket()
    if receipt.bucket != bucket.name or not receipt.path.startswith(f'raw-live/{uid}/'):
        raise ValueError('audio receipt owner mismatch')
    if not receipt.manifest_path.startswith(f'audio-outbox/{uid}/'):
        raise ValueError('audio manifest owner mismatch')
    manifest_blob = bucket.blob(receipt.manifest_path, generation=int(receipt.manifest_generation))
    manifest_blob.reload(timeout=10, retry=None)
    manifest_raw = manifest_blob.download_as_bytes(
        if_generation_match=int(receipt.manifest_generation), timeout=10, retry=None
    )
    if (manifest_blob.metadata or {}).get('encrypted') == 'true':
        manifest_raw = storage.encryption.decrypt_audio_file(manifest_raw, uid)
    if hashlib.sha256(manifest_raw).hexdigest() != receipt.manifest_sha256:
        raise ValueError('audio manifest checksum mismatch')
    manifest = json.loads(manifest_raw)
    if manifest.get('media') != {
        'bucket': receipt.bucket,
        'path': receipt.path,
        'generation': receipt.generation,
        'sha256': receipt.sha256,
    }:
        raise ValueError('audio manifest media mismatch')
    blob = bucket.blob(receipt.path, generation=int(receipt.generation))
    blob.reload(timeout=10, retry=None)
    raw = blob.download_as_bytes(if_generation_match=int(receipt.generation), timeout=10, retry=None)
    if (blob.metadata or {}).get('encrypted') == 'true':
        raw = storage.encryption.decrypt_audio_file(raw, uid)
    if hashlib.sha256(raw).hexdigest() != receipt.sha256:
        raise ValueError('audio receipt checksum mismatch')
    pcm = decode_capture(raw, blob.metadata or {}, output_rate=receipt.sample_rate)
    if receipt.pcm_sha256 is None or hashlib.sha256(pcm).hexdigest() != receipt.pcm_sha256:
        raise ValueError('audio receipt PCM checksum mismatch')
    return pcm


def commit_pcm_window(
    uid: str,
    pcm: bytes,
    conversation_id: str | None,
    start: float,
    sample_rate: int,
    source_root: str,
    first_sequence: int,
    frames: list[dict[str, Any]],
    *,
    data_protection_level: str | None = None,
    clock_source: str = 'server_projected',
) -> AudioReceipt:
    """Commit one immutable media+manifest pair for a window of PCM frames.

    ``frames`` are the caller's per-frame checkpoints (sequence, offsets,
    digests), pinned verbatim into the manifest; ``first_sequence`` names the
    window content-addressably like the single-frame path does.
    """
    if not pcm or len(pcm) % 2:
        raise ValueError('audio outbox requires sample-aligned PCM16')
    pack = CapturePack('pcm16', sample_rate)
    pack.append(pcm, conversation_id, start, len(pcm) // 2)
    raw, metadata = pack.encoded(preserve_pcm=True)
    metadata.update(
        capture_session_id=source_root,
        channel_index=0,
        clock_source=clock_source,
        source_position='unknown',
        consent_state='private_cloud_sync_enabled',
    )
    owner = conversation_id or 'unlinked'
    return commit_capture(
        uid,
        raw,
        f'{owner}/{int(start // 3600)}/0/{source_root}/{first_sequence}',
        metadata,
        frames,
        data_protection_level=data_protection_level,
    )


def commit_pcm(
    uid: str,
    pcm: bytes,
    conversation_id: str | None,
    timestamp: float,
    sample_rate: int,
    source_root: str,
    sequence: int,
    *,
    data_protection_level: str | None = None,
    clock_source: str = 'server_projected',
) -> AudioReceipt:
    frames = [
        {
            'sequence': sequence,
            'start': timestamp,
            'samples': len(pcm) // 2,
            'sha256': hashlib.sha256(pcm).hexdigest(),
            'gap_before': False,
        }
    ]
    return commit_pcm_window(
        uid,
        pcm,
        conversation_id,
        timestamp,
        sample_rate,
        source_root,
        sequence,
        frames,
        data_protection_level=data_protection_level,
        clock_source=clock_source,
    )
