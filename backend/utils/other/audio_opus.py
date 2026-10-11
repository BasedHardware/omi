import struct
from typing import Any, List, Optional

try:
    import opuslib
except Exception as e:
    opuslib = None
    _opus_import_error: Optional[Exception] = e
else:
    _opus_import_error = None

# Opus encoding constants
OPUS_SAMPLE_RATE = 16000
OPUS_CHANNELS = 1
OPUS_FRAME_DURATION_MS = 20  # 20ms frames (standard for voice)
OPUS_FRAME_SIZE = OPUS_SAMPLE_RATE * OPUS_FRAME_DURATION_MS // 1000  # 320 samples per frame


def _get_opuslib() -> Any:
    if opuslib is None:
        raise RuntimeError(
            'Opus support requires opuslib and the native libopus library. '
            'Install the OS-level Opus package before encoding or decoding .opus audio.'
        ) from _opus_import_error
    return opuslib


def encode_pcm_to_opus(pcm_data: bytes, sample_rate: int = OPUS_SAMPLE_RATE, channels: int = OPUS_CHANNELS) -> bytes:
    """
    Encode PCM16 audio to Opus.

    Format: 4-byte little-endian packet count, then for each packet:
    2-byte little-endian length prefix followed by the Opus packet bytes.
    This allows exact reconstruction on decode.

    Args:
        pcm_data: Raw PCM16 audio bytes
        sample_rate: Sample rate in Hz (default 16000)
        channels: Number of audio channels (default 1)

    Returns:
        Length-prefixed Opus packets as bytes
    """
    opus = _get_opuslib()
    encoder = opus.Encoder(sample_rate, channels, opus.APPLICATION_VOIP)
    frame_size = sample_rate * OPUS_FRAME_DURATION_MS // 1000
    bytes_per_frame = frame_size * channels * 2  # 16-bit = 2 bytes per sample

    packets: List[bytes] = []
    offset = 0
    while offset + bytes_per_frame <= len(pcm_data):
        frame = pcm_data[offset : offset + bytes_per_frame]
        encoded = encoder.encode(frame, frame_size)
        packets.append(encoded)
        offset += bytes_per_frame

    # Encode remaining samples (pad with silence)
    if offset < len(pcm_data):
        remaining = pcm_data[offset:]
        padded = remaining + b'\x00' * (bytes_per_frame - len(remaining))
        encoded = encoder.encode(padded, frame_size)
        packets.append(encoded)

    # Pack: [packet_count (4 bytes)] + [original_pcm_len (4 bytes)] + [len (2 bytes) + data] per packet
    output: bytes = struct.pack('<I', len(packets))
    output += struct.pack('<I', len(pcm_data))
    for pkt in packets:
        output += struct.pack('<H', len(pkt)) + pkt

    return output


def decode_opus_to_pcm(opus_data: bytes, sample_rate: int = OPUS_SAMPLE_RATE, channels: int = OPUS_CHANNELS) -> bytes:
    """
    Decode length-prefixed Opus packets back to PCM16.

    Args:
        opus_data: Length-prefixed Opus packets (from encode_pcm_to_opus)
        sample_rate: Sample rate in Hz (default 16000)
        channels: Number of audio channels (default 1)

    Returns:
        Raw PCM16 audio bytes

    Raises:
        ValueError: If opus_data is too short or has invalid header/packet structure
    """
    if len(opus_data) < 8:
        raise ValueError(f"Opus data too short: {len(opus_data)} bytes (need at least 8 for header)")

    frame_size = sample_rate * OPUS_FRAME_DURATION_MS // 1000

    offset = 0
    packet_count = struct.unpack_from('<I', opus_data, offset)[0]
    offset += 4
    original_pcm_len = struct.unpack_from('<I', opus_data, offset)[0]
    offset += 4

    packets: List[bytes] = []
    for i in range(packet_count):
        if offset + 2 > len(opus_data):
            raise ValueError(f"Truncated Opus data: expected packet {i}/{packet_count} length at offset {offset}")
        pkt_len = struct.unpack_from('<H', opus_data, offset)[0]
        offset += 2
        if offset + pkt_len > len(opus_data):
            raise ValueError(
                f"Truncated Opus data: packet {i} needs {pkt_len} bytes at offset {offset}, only {len(opus_data) - offset} available"
            )
        packets.append(opus_data[offset : offset + pkt_len])
        offset += pkt_len

    opus = _get_opuslib()
    decoder = opus.Decoder(sample_rate, channels)

    pcm_parts: List[bytes] = []
    for pkt_data in packets:
        decoded = decoder.decode(pkt_data, frame_size)
        pcm_parts.append(decoded)

    result = b''.join(pcm_parts)
    # Trim to original PCM length to remove padding from partial final frame
    if original_pcm_len > 0 and original_pcm_len < len(result):
        result = result[:original_pcm_len]
    return result
