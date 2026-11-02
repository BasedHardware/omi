"""Capture containers and provenance. No storage clients or import-time IO."""

import hashlib
import audioop
import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydub import AudioSegment

from utils.other.audio_opus import _get_opuslib  # type: ignore[reportPrivateUsage]  # shared lazy native binding

WAL_FORMAT = 'omi-wal-uint32le-opus-v1'
UNKNOWN = 'unknown'
MAX_PACK_BYTES = 16 * 1024 * 1024


def wal_packets(raw: bytes):
    offset = 0
    while offset < len(raw):
        if offset + 4 > len(raw):
            raise ValueError('truncated WAL length')
        size = struct.unpack_from('<I', raw, offset)[0]
        offset += 4
        if not 0 < size <= 65536 or offset + size > len(raw):
            raise ValueError('invalid WAL packet')
        yield raw[offset : offset + size]
        offset += size


def provenance(raw: bytes, supplied: dict[str, Any]) -> dict[str, str]:
    metadata = {
        key: UNKNOWN
        for key in (
            'codec',
            'sample_rate',
            'channels',
            'frame_size',
            'device_model',
            'firmware',
            'app_version',
            'capture_start',
            'capture_end',
            'sequence_count',
            'gap_count',
            'conversation_id',
            'consent_state',
            'consent_version',
        )
    }
    metadata.update({key: str(value) for key, value in supplied.items() if value is not None})
    metadata.update(schema_version='1', sha256=hashlib.sha256(raw).hexdigest())
    return metadata


def filename_provenance(path: str) -> dict[str, Any]:
    tokens = Path(path).stem.split('_')
    if len(tokens) < 7 or tokens[0] != 'audio':
        return {'format': 'as-captured-file-v1'}

    try:
        capture_start = float(tokens[6])
        if capture_start > 10_000_000_000:
            capture_start /= 1000
        return {
            'device_model': tokens[1],
            'codec': tokens[2],
            'sample_rate': int(tokens[3]),
            'channels': int(tokens[4]),
            'frame_size': int(tokens[5].removeprefix('fs')),
            'capture_start': capture_start,
            'format': WAL_FORMAT if tokens[2] == 'opus' else 'omi-wal-uint32le-pcm-v1',
        }
    except ValueError:
        return {'format': 'as-captured-file-v1'}


def packet_provenance(raw: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
    """Read framing/header provenance without decoding or transforming intake."""
    if metadata.get('format') != WAL_FORMAT:
        return metadata
    try:
        packets = list(wal_packets(raw))
        result = {**metadata, 'sequence_count': len(packets)}
        api = _get_opuslib().api.decoder
        rate = int(metadata['sample_rate'])
        samples = sum(
            api.packet_get_nb_frames(packet) * api.packet_get_samples_per_frame(packet, rate) for packet in packets
        )
        result['capture_end'] = float(metadata['capture_start']) + samples / rate
        result['frame_size'] = 'variable-opus-packet-header'
        return result
    except Exception:
        # Invalid captures are valuable diagnostic negatives too. Retain bytes;
        # do not fabricate timing/gap completeness for an unreadable capture.
        return metadata


def decode_capture(raw: bytes, metadata: dict[str, str], output_rate: int = 16000) -> bytes:
    rate = int(metadata['sample_rate'])
    channels = int(metadata['channels'])
    if metadata['format'] == 'pcm16le':
        if len(raw) % (2 * channels):
            raise ValueError('capture PCM is not sample-aligned')
        if channels == 1 and rate == output_rate:
            return raw
        audio = AudioSegment(raw, frame_rate=rate, channels=channels, sample_width=2)
    elif metadata['format'] == 'pcm8-u8':
        pcm = audioop.lin2lin(audioop.bias(raw, 1, -128), 1, 2)
        audio = AudioSegment(pcm, frame_rate=rate, channels=channels, sample_width=2)
    elif metadata['format'] == WAL_FORMAT:
        decoder = _get_opuslib().Decoder(rate, channels)
        pcm = b''.join(decoder.decode(packet, rate * 120 // 1000) for packet in wal_packets(raw))
        audio = AudioSegment(pcm, frame_rate=rate, channels=channels, sample_width=2)
    elif metadata['codec'] == 'flac':
        audio = AudioSegment.from_file(io.BytesIO(raw), format='flac')
    else:
        raise ValueError('capture format cannot serve playback')
    # Renditions may resample; the canonical bytes are never transformed.
    result = audio.set_frame_rate(output_rate).set_channels(1).set_sample_width(2).raw_data
    if result is None:
        raise ValueError('capture decoder produced no PCM')
    return bytes(result)


@dataclass
class CapturePack:
    codec: str
    sample_rate: int
    channels: int = 1
    conversation_id: str | None = None
    start: float | None = None
    end: float | None = None
    sequence_count: int = 0
    gap_count: int = 0
    data: bytearray = field(default_factory=bytearray)
    pcm_digest: Any = field(default_factory=hashlib.sha256)
    pcm_proven: bool = True

    def boundary(self, conversation_id: str | None, timestamp: float, incoming: int) -> bool:
        return bool(self.data) and (
            (self.conversation_id is not None and conversation_id != self.conversation_id)
            or int(timestamp // 3600) != int((self.start or timestamp) // 3600)
            or len(self.data) + incoming + 4 > MAX_PACK_BYTES
        )

    def append(
        self, payload: bytes, conversation_id: str | None, timestamp: float, samples: int, decoded: bytes | None = None
    ) -> None:
        if self.start is None:
            self.start = timestamp
        if self.conversation_id is None:
            self.conversation_id = conversation_id
        if self.end is not None and abs(timestamp - self.end) > 0.002:
            self.gap_count += 1
        self.end = timestamp + samples / self.sample_rate
        if samples == 0:
            self.gap_count += 1
        self.sequence_count += 1
        if decoded is None and self.codec == 'pcm16':
            decoded = payload
        if decoded is not None and len(decoded) == samples * 2:
            self.pcm_digest.update(decoded)
        else:
            self.pcm_proven = False
        self.data.extend(payload if self.codec in {'pcm16', 'pcm8'} else struct.pack('<I', len(payload)) + payload)

    def encoded(self, *, preserve_pcm: bool = False) -> tuple[bytes, dict[str, Any]]:
        raw = bytes(self.data)
        codec = self.codec
        if codec in {'pcm16', 'pcm8'} and not preserve_pcm:
            if codec == 'pcm8':
                raw = audioop.bias(raw, 1, -128)
            audio = AudioSegment(
                raw, frame_rate=self.sample_rate, channels=self.channels, sample_width=2 if codec == 'pcm16' else 1
            )
            output = io.BytesIO()
            audio.export(output, format='flac')
            raw = output.getvalue()
            codec = 'flac'
        return raw, {
            'codec': codec,
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'format': (
                WAL_FORMAT
                if codec == 'opus'
                else (
                    'pcm16le'
                    if codec == 'pcm16'
                    else 'pcm8-u8' if codec == 'pcm8' else 'flac' if codec == 'flac' else f'omi-wal-uint32le-{codec}-v1'
                )
            ),
            'capture_start': self.start,
            'capture_end': self.end,
            'sequence_count': self.sequence_count,
            'gap_count': self.gap_count,
            'conversation_id': self.conversation_id,
            'pcm_sha256': self.pcm_digest.hexdigest() if self.pcm_proven else None,
        }
