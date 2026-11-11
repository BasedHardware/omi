"""
Omi Python SDK

A Python SDK for connecting to Omi wearable devices over Bluetooth,
decoding Opus-encoded audio, and transcribing it in real time.
"""

from __future__ import annotations

__version__ = "0.1.0"

from . import constants
from .constants import (
    AUDIO_CODEC_UUID,
    AUDIO_DATA_UUID,
    OMI_SERVICE_UUID,
    PACKET_HEADER_BYTES,
    PCM_SAMPLE_RATE_HZ,
)

__all__ = [
    "constants",
    "OMI_SERVICE_UUID",
    "AUDIO_DATA_UUID",
    "AUDIO_CODEC_UUID",
    "PACKET_HEADER_BYTES",
    "PCM_SAMPLE_RATE_HZ",
    "print_devices",
    "listen_to_omi",
    "scan",
    "listen",
    "listen_payload",
    "read_codec",
    "Device",
    "OmiOpusDecoder",
    "transcribe",
    "__version__",
]


def __getattr__(name: str):
    # Lazy imports so protocol constants work without bleak/opuslib installed.
    if name in {"print_devices", "listen_to_omi"}:
        from . import bluetooth as bluetooth

        return getattr(bluetooth, name)
    if name in {"scan", "listen", "listen_payload", "read_codec", "Device"}:
        from . import ble as ble

        return getattr(ble, name)
    if name == "OmiOpusDecoder":
        from .decoder import OmiOpusDecoder

        return OmiOpusDecoder
    if name == "transcribe":
        from .transcribe import transcribe

        return transcribe
    raise AttributeError(name)
