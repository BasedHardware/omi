from typing import Union
from opuslib import Decoder
from .constants import OPUS_FRAME_SAMPLES, PACKET_HEADER_BYTES, PCM_SAMPLE_RATE_HZ


class OmiOpusDecoder:
    """Opus audio decoder for Omi device audio packets."""

    def __init__(self) -> None:
        """Initialize decoder for 16kHz mono audio."""
        self.decoder = Decoder(PCM_SAMPLE_RATE_HZ, 1)  # 16kHz mono

    def decode_packet(self, data: Union[bytes, bytearray]) -> bytes:
        """
        Decode Opus-encoded audio packet to PCM.

        Args:
            data: Raw audio packet from Omi device (includes 3-byte header)

        Returns:
            PCM audio data as bytes, or empty bytes if decode fails
        """
        if len(data) <= PACKET_HEADER_BYTES:
            return b''

        # Remove 3-byte header
        clean_data = bytes(data[PACKET_HEADER_BYTES:])

        # Decode Opus to PCM 16-bit
        try:
            pcm: bytes = self.decoder.decode(clean_data, OPUS_FRAME_SAMPLES, decode_fec=False)
            return pcm
        except Exception as e:
            print("Opus decode error:", e)
            return b''
