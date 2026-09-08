"""Pure multi-channel listen audio helpers.

Kept below the router layer so the websocket session and its unit tests use
one implementation instead of maintaining copies of PCM mixing logic.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ChannelConfig:
    channel_id: int
    label: str
    is_user: bool
    speaker_label: str


def build_channel_config(source: str) -> List[ChannelConfig]:
    if source == 'phone_call':
        return [
            ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
            ChannelConfig(channel_id=0x02, label='remote', is_user=False, speaker_label='SPEAKER_01'),
        ]
    if source == 'desktop':
        return [
            ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
            ChannelConfig(channel_id=0x02, label='system_audio', is_user=False, speaker_label='SPEAKER_01'),
        ]
    return [
        ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
        ChannelConfig(channel_id=0x02, label='remote', is_user=False, speaker_label='SPEAKER_01'),
    ]


def mix_n_channel_buffers(buffers: List[bytearray]) -> bytes:
    """Mix signed-16-bit mono buffers, clipping the result to int16."""
    min_len = min((len(buffer) for buffer in buffers), default=0)
    if min_len < 2:
        return b''
    min_len -= min_len % 2
    sample_count = min_len // 2
    channels = [struct.unpack(f'<{sample_count}h', buffer[:min_len]) for buffer in buffers]
    mixed = [max(-32768, min(32767, sum(channel[index] for channel in channels))) for index in range(sample_count)]
    return struct.pack(f'<{len(mixed)}h', *mixed)


def resample_pcm(pcm_data: bytes, source_rate: int, target_rate: int) -> bytes:
    """Resample PCM by deterministic duplication/decimation for stream routing."""
    if source_rate == target_rate or source_rate <= 0 or target_rate <= 0:
        return pcm_data
    sample_count = len(pcm_data) // 2
    if sample_count == 0:
        return pcm_data
    samples = struct.unpack(f'<{sample_count}h', pcm_data[: sample_count * 2])
    ratio = target_rate / source_rate
    output_count = int(sample_count * ratio)
    output = [samples[min(int(index / ratio), sample_count - 1)] for index in range(output_count)]
    return struct.pack(f'<{len(output)}h', *output)
