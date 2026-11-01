"""Staging-mirror envelope and source-audio codecs. Pure functions, no IO.

The mirror is the only staging resource that receives prod-derived bytes
(contract (i)). Every mirrored object is sealed with a key derived from the
staging-only secret; the object name is bound as AES-GCM associated data so a
ciphertext cannot be replayed under another name. Prod's per-uid scheme
(``utils.encryption``) is re-implemented here with an explicit secret so one
process can hold the prod and staging keys without touching the global
``ENCRYPTION_SECRET`` that ``utils.encryption`` reads at import.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MIRROR_MAGIC = b'OMSM1'  # omi staging mirror, envelope v1
MIRROR_KEY_SALT = b'omi-staging-mirror-v1'
MIRROR_KEY_INFO = b'staging-mirror-object-key'
MIRROR_GROUP_INFO = b'staging-mirror-group-key'
MIN_SECRET_BYTES = 32

# Source formats the mirror records; replay converts each to an upload file.
FORMAT_RAW_UPLOAD = 'raw-upload'  # bytes exactly as the client uploaded them (named audio_*.bin)
FORMAT_CHUNK_OPUS = 'chunk-opus-lp'  # utils.other.audio_opus.encode_pcm_to_opus container
FORMAT_CHUNK_PCM16 = 'chunk-pcm16'  # raw PCM16 mono 16 kHz
SOURCE_FORMATS = frozenset({FORMAT_RAW_UPLOAD, FORMAT_CHUNK_OPUS, FORMAT_CHUNK_PCM16})

PCM_SAMPLE_RATE = 16000
OPUS_FRAME_SAMPLES = 320  # 20 ms at 16 kHz, matches utils.other.audio_opus
WAL_PCM_FRAME_SAMPLES = 1600  # 100 ms frames, matches the sync stack fixtures


class MirrorFormatError(ValueError):
    """A mirror object or source payload does not have the expected shape."""


def _secret_bytes(secret: bytes | str) -> bytes:
    raw = secret.encode('utf-8') if isinstance(secret, str) else bytes(secret)
    if len(raw) < MIN_SECRET_BYTES:
        raise MirrorFormatError('secret must be at least 32 bytes')
    return raw


# --------------------------------------------------------------------------
# Prod per-uid scheme (byte-compatible with utils.encryption, explicit secret)
# --------------------------------------------------------------------------


def derive_prod_user_key(secret: bytes | str, uid: str) -> bytes:
    """utils.encryption.derive_key with an explicit master secret."""
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=uid.encode('utf-8'), info=b'user-data-encryption')
    return hkdf.derive(_secret_bytes(secret))


def decrypt_prod_audio(encrypted: bytes, key: bytes) -> bytes:
    """utils.encryption.decrypt_audio_file: concatenated [u32be len][nonce][ct+tag] chunks."""
    out = bytearray()
    offset = 0
    aes = AESGCM(key)
    while offset < len(encrypted):
        if offset + 4 > len(encrypted):
            raise MirrorFormatError('truncated encrypted chunk length')
        length = struct.unpack_from('>I', encrypted, offset)[0]
        offset += 4
        if length < 12 + 16 or offset + length > len(encrypted):
            raise MirrorFormatError('invalid encrypted chunk length')
        payload = encrypted[offset : offset + length]
        offset += length
        out.extend(aes.decrypt(payload[:12], payload[12:], None))
    return bytes(out)


# --------------------------------------------------------------------------
# Staging mirror envelope
# --------------------------------------------------------------------------


def derive_mirror_key(staging_secret: bytes | str) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=MIRROR_KEY_SALT, info=MIRROR_KEY_INFO)
    return hkdf.derive(_secret_bytes(staging_secret))


def derive_group_key(staging_secret: bytes | str) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=MIRROR_KEY_SALT, info=MIRROR_GROUP_INFO)
    return hkdf.derive(_secret_bytes(staging_secret))


def group_label(group_key: bytes, value: str) -> str:
    """Stable, keyed label for a source grouping (conversation/job id) that reveals nothing."""
    return hmac.new(group_key, value.encode('utf-8'), hashlib.sha256).hexdigest()[:32]


def seal_mirror_object(key: bytes, object_name: str, plaintext: bytes) -> bytes:
    if len(key) != 32:
        raise MirrorFormatError('mirror key must be 256-bit')
    nonce = os.urandom(12)
    return MIRROR_MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, object_name.encode('utf-8'))


def open_mirror_object(key: bytes, object_name: str, sealed: bytes) -> bytes:
    if not sealed.startswith(MIRROR_MAGIC) or len(sealed) < len(MIRROR_MAGIC) + 12 + 16:
        raise MirrorFormatError('not a staging mirror envelope')
    nonce = sealed[len(MIRROR_MAGIC) : len(MIRROR_MAGIC) + 12]
    return AESGCM(key).decrypt(nonce, sealed[len(MIRROR_MAGIC) + 12 :], object_name.encode('utf-8'))


# --------------------------------------------------------------------------
# Source audio -> upload file (WAL framing: u32le length + payload)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UploadAudio:
    """One upload-ready file body plus the filename fields it implies."""

    codec: str  # full filename codec token: 'opus' | 'opus_fs320' | 'pcm16' | ...
    sample_rate: int
    frame_size: int
    body: bytes
    duration_s: float


def chunk_opus_packets(container: bytes) -> tuple[list[bytes], int]:
    """Parse the encode_pcm_to_opus container: [u32 count][u32 pcm_len]([u16 len][packet])*."""
    if len(container) < 8:
        raise MirrorFormatError('opus container too short')
    count, pcm_len = struct.unpack_from('<II', container, 0)
    offset = 8
    packets: list[bytes] = []
    for _ in range(count):
        if offset + 2 > len(container):
            raise MirrorFormatError('truncated opus packet length')
        size = struct.unpack_from('<H', container, offset)[0]
        offset += 2
        if size == 0 or offset + size > len(container):
            raise MirrorFormatError('invalid opus packet')
        packets.append(container[offset : offset + size])
        offset += size
    return packets, pcm_len


def wal_frame(payloads: list[bytes]) -> bytes:
    return b''.join(struct.pack('<I', len(p)) + p for p in payloads)


def wal_payloads(body: bytes) -> list[bytes]:
    out: list[bytes] = []
    offset = 0
    while offset < len(body):
        if offset + 4 > len(body):
            raise MirrorFormatError('truncated WAL length')
        size = struct.unpack_from('<I', body, offset)[0]
        offset += 4
        if not 0 < size <= 65536 or offset + size > len(body):
            raise MirrorFormatError('invalid WAL frame')
        out.append(body[offset : offset + size])
        offset += size
    return out


def pcm16_wal(pcm: bytes, frame_samples: int = WAL_PCM_FRAME_SAMPLES) -> bytes:
    frame_bytes = frame_samples * 2
    usable = len(pcm) // 2 * 2
    return wal_frame([pcm[i : i + frame_bytes] for i in range(0, usable, frame_bytes) if pcm[i : i + frame_bytes]])


def to_upload_audio(source_format: str, plaintext: bytes, *, filename: str | None = None) -> UploadAudio:
    """Convert one mirrored payload to an upload body without decoding audio."""
    if source_format == FORMAT_CHUNK_OPUS:
        packets, pcm_len = chunk_opus_packets(plaintext)
        duration = (pcm_len / 2 / PCM_SAMPLE_RATE) if pcm_len else len(packets) * OPUS_FRAME_SAMPLES / PCM_SAMPLE_RATE
        return UploadAudio('opus', PCM_SAMPLE_RATE, OPUS_FRAME_SAMPLES, wal_frame(packets), duration)
    if source_format == FORMAT_CHUNK_PCM16:
        return UploadAudio(
            'pcm16', PCM_SAMPLE_RATE, WAL_PCM_FRAME_SAMPLES, pcm16_wal(plaintext), len(plaintext) / 2 / PCM_SAMPLE_RATE
        )
    if source_format == FORMAT_RAW_UPLOAD:
        fields = parse_upload_filename(filename or '')
        if fields is None:
            raise MirrorFormatError('raw upload needs its original audio_* filename')
        codec, rate, frame = fields['codec'], fields['sample_rate'], fields['frame_size']
        duration = estimate_wal_duration(codec, rate, frame, plaintext)
        return UploadAudio(codec, rate, frame, plaintext, duration)
    raise MirrorFormatError(f'unknown source format {source_format!r}')


def parse_upload_filename(name: str) -> dict | None:
    """audio_<device>_<codec...>_<rate>_<channels>_fs<frame>_<ts>.bin -> fields.

    The codec token may itself contain underscores: the pendant's
    ``opus_fs320`` gives ``audio_<dev>_opus_fs320_16000_1_fs320_<ts>.bin``.
    ``utils.sync.files`` takes the *first* ``_fs<N>`` as the opus decode frame
    size, so for those names the codec suffix is what the decoder uses.
    """
    stem = name.rsplit('/', 1)[-1]
    if stem.endswith('.bin'):
        stem = stem[:-4]
    tokens = stem.split('_')
    if len(tokens) < 7 or tokens[0] != 'audio':
        return None
    rate_index = next((i for i in range(3, len(tokens) - 3) if tokens[i].isdigit()), None)
    if rate_index is None or not tokens[rate_index + 2].startswith('fs'):
        return None
    try:
        ts = float(tokens[-1])
        return {
            'device': tokens[1],
            'codec': '_'.join(tokens[2:rate_index]),
            'sample_rate': int(tokens[rate_index]),
            'channels': int(tokens[rate_index + 1]),
            'frame_size': int(tokens[rate_index + 2][2:]),
            'capture_start': ts / 1000 if ts > 10_000_000_000 else ts,
        }
    except ValueError:
        return None


def estimate_wal_duration(codec: str, sample_rate: int, frame_size: int, body: bytes) -> float:
    try:
        frames = wal_payloads(body)
    except MirrorFormatError:
        return 0.0
    if codec.startswith('pcm'):
        width = 1 if codec.startswith('pcm8') else 2
        return sum(len(f) for f in frames) / width / max(sample_rate, 1)
    # Opus/LC3: one codec frame per WAL frame; an ``_fsN`` codec suffix is the frame size.
    suffix = codec.rsplit('_fs', 1)
    if len(suffix) == 2 and suffix[1].isdigit():
        frame_size = int(suffix[1])
    return len(frames) * frame_size / max(sample_rate, 1)


def upload_filename(device: str, audio: UploadAudio, capture_start: float) -> str:
    """Name in the production device format; millisecond timestamps keep names unique.

    ``audio.codec`` is the full codec token (``opus``, ``opus_fs320``, ``pcm16``).
    """
    millis = int(round(capture_start * 1000))
    return f'audio_{device}_{audio.codec}_{audio.sample_rate}_1_fs{audio.frame_size}_{millis}.bin'


def silence_payloads(audio: UploadAudio, seconds: float, opus_silence_packet: bytes | None) -> list[bytes]:
    """WAL payloads of digital silence in the same codec as ``audio``."""
    if seconds <= 0:
        return []
    if audio.codec.startswith('pcm'):
        frame = b'\x00' * (audio.frame_size * 2)
        return [frame] * max(1, int(round(seconds * audio.sample_rate / audio.frame_size)))
    if audio.codec.startswith('opus'):
        if not opus_silence_packet:
            raise MirrorFormatError('opus silence needs an encoded silence packet (libopus)')
        return [opus_silence_packet] * max(1, int(round(seconds * audio.sample_rate / audio.frame_size)))
    raise MirrorFormatError(f'cannot synthesize silence for codec {audio.codec!r}')


def pad_with_silence(
    audio: UploadAudio, lead_s: float, trail_s: float, opus_silence_packet: bytes | None = None
) -> UploadAudio:
    if lead_s <= 0 and trail_s <= 0:
        return audio
    body = (
        wal_frame(silence_payloads(audio, lead_s, opus_silence_packet))
        + audio.body
        + wal_frame(silence_payloads(audio, trail_s, opus_silence_packet))
    )
    return UploadAudio(audio.codec, audio.sample_rate, audio.frame_size, body, audio.duration_s + lead_s + trail_s)


def encoded_opus_silence_packet() -> bytes | None:
    """One 20 ms opus packet of silence, or None when libopus is unavailable (local Macs)."""
    try:
        from utils.other.audio_opus import _get_opuslib  # type: ignore[reportPrivateUsage]

        opus = _get_opuslib()
    except Exception:
        return None
    encoder = opus.Encoder(PCM_SAMPLE_RATE, 1, opus.APPLICATION_VOIP)
    return encoder.encode(b'\x00' * OPUS_FRAME_SAMPLES * 2, OPUS_FRAME_SAMPLES)
